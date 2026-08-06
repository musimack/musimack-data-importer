from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.cloud_ingestion.application import IngestionApplication
from src.cloud_ingestion.budget import ProviderRequestBudget
from src.cloud_ingestion.contract import canonical_payload_hash, validate_result_payload
from src.cloud_ingestion.domain import ProviderOutput, RunRequest
from src.cloud_ingestion.errors import (
    BudgetError,
    ContractError,
    CredentialError,
    ProviderError,
    TerminationError,
)
from src.cloud_ingestion.exit_codes import ExitCode
from src.cloud_ingestion.fixture_adapters import (
    FixtureConfigurationProvider,
    FixtureCredentialProvider,
    FixtureIdentityTokenProvider,
    FixtureWeeklyProvider,
    MemoryIngestionSink,
)
from src.cloud_ingestion.structured_logging import SafeJsonLogger

FIXTURES = Path(__file__).parent / "fixtures" / "cloud_ingestion"
GA4_CONFIG = FIXTURES / "ga4_configuration.json"
GA4_PROVIDER = FIXTURES / "ga4_provider.json"
PROJECT_ID = "20000000-0000-0000-0000-000000000001"
IDEMPOTENCY_KEY = "30000000-0000-0000-0000-000000000001"
FIXED_TIME = datetime(2026, 8, 6, 12, 2, tzinfo=timezone.utc)


def _request(**overrides) -> RunRequest:
    values = {
        "project_id": PROJECT_ID,
        "provider": "ga4",
        "week_start": date(2026, 7, 27),
        "idempotency_key": IDEMPOTENCY_KEY,
        "environment": "development",
        "requested_at": datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return RunRequest(**values)


def _application(*, sink=None, credentials=None, provider=None, logger=None):
    return IngestionApplication(
        FixtureConfigurationProvider(GA4_CONFIG),
        credentials or FixtureCredentialProvider(),
        {"ga4": provider or FixtureWeeklyProvider(GA4_PROVIDER, "ga4")},
        sink or MemoryIngestionSink(),
        logger=logger or SafeJsonLogger(writer=lambda _: None),
        clock=lambda: FIXED_TIME,
    )


def test_fixture_run_builds_v1_contract_with_approved_request_evidence():
    sink = MemoryIngestionSink()
    credentials = FixtureCredentialProvider()
    logger = SafeJsonLogger(writer=lambda _: None)

    outcome = _application(sink=sink, credentials=credentials, logger=logger).run(_request())

    assert outcome.exit_code == ExitCode.SUCCESS
    assert credentials.resolutions == 1
    assert len(sink.begin_calls) == 1
    assert len(sink.completed) == 1
    assert sink.failed == []
    payload = sink.completed[0]
    assert payload["schema_version"] == "weekly_provider_ingestion.v1"
    assert payload["evidence"] == {
        "requests_consumed": 5,
        "retry_count": 0,
        "direct_cost_usd": 0.0,
        "bigquery_bytes_processed": None,
    }
    assert payload["normalized_payload_hash"] == canonical_payload_hash(payload)
    assert all("value" not in record for record in logger.captured)


def test_canonical_hash_ignores_transport_sent_at_but_not_metrics():
    first = _application().run(_request()).payload
    second = json.loads(json.dumps(first))
    second["sent_at"] = "2030-01-01T00:00:00Z"
    assert canonical_payload_hash(first) == canonical_payload_hash(second)
    second["metrics"][0]["value"] = 71
    assert canonical_payload_hash(first) != canonical_payload_hash(second)


def test_cross_repository_conformance_fixture_has_stable_canonical_hash():
    fixture = json.loads((FIXTURES / "contract_conformance.json").read_text(encoding="utf-8"))
    payload = fixture["payload"]
    expected = fixture["expected_canonical_sha256"]
    assert canonical_payload_hash(payload) == expected
    assert payload["normalized_payload_hash"] == expected
    validate_result_payload(payload, maximum_bytes=2 * 1024 * 1024)


def test_configuration_mismatch_refuses_before_begin_credentials_or_provider():
    sink = MemoryIngestionSink()
    credentials = FixtureCredentialProvider()

    outcome = _application(sink=sink, credentials=credentials).run(
        _request(project_id="20000000-0000-0000-0000-000000000099")
    )

    assert outcome.exit_code == ExitCode.CONFIGURATION_REFUSED
    assert credentials.resolutions == 0
    assert sink.begin_calls == []
    assert sink.completed == []
    assert sink.failed == []


def test_plan_over_ceiling_refuses_before_begin_and_credentials():
    class TooLargePlan:
        provider = "ga4"

        def planned_requests(self, request, configuration):
            return 7

        def retrieve(self, *args):
            raise AssertionError("retrieve must not run")

    sink = MemoryIngestionSink()
    credentials = FixtureCredentialProvider()
    outcome = _application(sink=sink, credentials=credentials, provider=TooLargePlan()).run(_request())

    assert outcome.exit_code == ExitCode.REQUEST_BUDGET_REFUSED
    assert credentials.resolutions == 0
    assert sink.begin_calls == []


def test_begin_precedes_credential_resolution_and_provider_retrieval():
    events = []

    class OrderedSink(MemoryIngestionSink):
        def begin(self, request, configuration):
            events.append("begin")
            return super().begin(request, configuration)

    class OrderedCredentials(FixtureCredentialProvider):
        def resolve(self, configuration):
            events.append("credential")
            return super().resolve(configuration)

    class OrderedProvider(FixtureWeeklyProvider):
        def retrieve(self, *args):
            events.append("provider")
            return super().retrieve(*args)

    outcome = _application(
        sink=OrderedSink(),
        credentials=OrderedCredentials(),
        provider=OrderedProvider(GA4_PROVIDER, "ga4"),
    ).run(_request())

    assert outcome.exit_code == ExitCode.SUCCESS
    assert events == ["begin", "credential", "provider"]


def test_credential_failure_creates_safe_failure_after_begin():
    class FailingCredentials:
        def resolve(self, configuration):
            raise CredentialError("private detail must not escape")

    sink = MemoryIngestionSink()
    logger = SafeJsonLogger(writer=lambda _: None)
    outcome = _application(sink=sink, credentials=FailingCredentials(), logger=logger).run(_request())

    assert outcome.exit_code == ExitCode.CREDENTIAL_RESOLUTION_FAILED
    assert sink.completed == []
    assert sink.failed[0]["error"] == {
        "code": "credential_resolution_failed",
        "message": "Credential resolution failed safely.",
        "phase": "credential_resolution",
    }
    serialized = json.dumps([sink.failed, logger.captured]).lower()
    assert "private detail" not in serialized
    assert "binding" not in serialized


def test_contract_rejects_raw_provider_or_credential_fields():
    payload = _application().run(_request()).payload
    payload["source"]["raw_response"] = {"rows": []}
    payload["normalized_payload_hash"] = canonical_payload_hash(payload)
    with pytest.raises(ContractError):
        validate_result_payload(payload, maximum_bytes=2 * 1024 * 1024)


def test_contract_rejects_daily_observation_outside_week():
    payload = _application().run(_request()).payload
    payload["daily"][0]["date"] = "2026-07-26"
    payload["normalized_payload_hash"] = canonical_payload_hash(payload)
    with pytest.raises(ContractError):
        validate_result_payload(payload, maximum_bytes=2 * 1024 * 1024)


def test_budget_default_retry_is_zero_and_refuses_before_issue():
    budget = ProviderRequestBudget("ga4", 6)
    with pytest.raises(BudgetError):
        budget.consume("ga4.runReport", retry=True)
    assert budget.requests_consumed == 0


def test_budget_allows_only_explicit_retries_within_total_twelve():
    budget = ProviderRequestBudget("ga4", 6, authorized_retry_count=2)
    for index in range(6):
        budget.consume(f"base-{index}")
    budget.consume("retry-1", retry=True)
    budget.consume("retry-2", retry=True)
    with pytest.raises(BudgetError):
        budget.consume("retry-3", retry=True)
    assert budget.requests_consumed == 8
    assert budget.retry_count == 2


def test_safe_logger_rejects_non_allowlisted_fields():
    logger = SafeJsonLogger(writer=lambda _: None)
    with pytest.raises(ValueError):
        logger.emit("unsafe", metric_value=42)


def test_identity_token_fixture_requires_exact_https_audience():
    provider = FixtureIdentityTokenProvider("https://portal.fixture.invalid/internal/ingestion")
    assert provider.token_for_audience("https://portal.fixture.invalid/internal/ingestion") == "fixture-identity-token"
    with pytest.raises(CredentialError):
        provider.token_for_audience("https://other.fixture.invalid/internal/ingestion")


def test_termination_after_begin_records_safe_failure_and_deterministic_exit():
    class TerminatedProvider(FixtureWeeklyProvider):
        def retrieve(self, *args):
            raise TerminationError()

    sink = MemoryIngestionSink()
    outcome = _application(
        sink=sink,
        provider=TerminatedProvider(GA4_PROVIDER, "ga4"),
    ).run(_request())
    assert outcome.exit_code == ExitCode.INTERNAL_FAILED
    assert outcome.error_code == "task_terminated"
    assert sink.failed[0]["error"]["code"] == "task_terminated"


def test_provider_failure_has_closed_exit_and_safe_failure_contract():
    class FailingProvider(FixtureWeeklyProvider):
        def retrieve(self, *args):
            raise ProviderError("provider body must not escape")

    sink = MemoryIngestionSink()
    outcome = _application(
        sink=sink,
        provider=FailingProvider(GA4_PROVIDER, "ga4"),
    ).run(_request())
    assert outcome.exit_code == ExitCode.PROVIDER_FAILED
    assert outcome.error_code == "provider_failed"
    assert "provider body" not in json.dumps(sink.failed)


def test_invalid_provider_normalization_has_contract_exit():
    class InvalidOutputProvider(FixtureWeeklyProvider):
        def retrieve(self, *args):
            return ProviderOutput(
                freshness={"state": "available"},
                source={"identity": "invalid", "contract_version": 1},
                metrics=[],
                daily=[],
                ranked=[],
            )

    sink = MemoryIngestionSink()
    outcome = _application(
        sink=sink,
        provider=InvalidOutputProvider(GA4_PROVIDER, "ga4"),
    ).run(_request())
    assert outcome.exit_code == ExitCode.CONTRACT_FAILED
    assert outcome.error_code == "contract_failed"
    assert sink.completed == []


def test_sink_begin_failure_has_sink_exit_and_never_resolves_credentials():
    class FailingSink(MemoryIngestionSink):
        def begin(self, request, configuration):
            raise OSError("database detail must not escape")

    credentials = FixtureCredentialProvider()
    outcome = _application(sink=FailingSink(), credentials=credentials).run(_request())
    assert outcome.exit_code == ExitCode.SINK_FAILED
    assert outcome.error_code == "sink_failed"
    assert credentials.resolutions == 0
