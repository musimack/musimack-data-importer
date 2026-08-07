from __future__ import annotations

import base64
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.cloud_ingestion.domain import IngestionConfiguration, RunRequest
from src.cloud_ingestion.errors import ConfigurationError, CredentialError, InputError
from src.cloud_ingestion.manual_weekly_runner import (
    ManualRunInputs,
    parse_grants,
    parse_inputs,
    validate_grant_readiness,
    validate_manual_configuration,
)

INN_CLIENT = "8088f3af-256d-4d5f-900f-b19d24dd8bef"
INN_PROJECT = "cd39f3ec-58b7-4ecc-8691-8415e29e9545"
ALUMA_CLIENT = "11111111-1111-4111-8111-111111111111"
ALUMA_PROJECT = "4cb10985-5506-4789-8e68-de90a1025da7"
IDEMPOTENCY = "22222222-2222-4222-8222-222222222222"


def _inputs(**changes) -> ManualRunInputs:
    values = {
        "client_id": INN_CLIENT,
        "project_id": INN_PROJECT,
        "provider": "ga4",
        "week_start": date(2026, 7, 20),
        "idempotency_key": IDEMPOTENCY,
        "mode": "execute",
    }
    values.update(changes)
    return ManualRunInputs(**values)


def _request(inputs: ManualRunInputs) -> RunRequest:
    return RunRequest(
        project_id=inputs.project_id,
        provider=inputs.provider,
        week_start=inputs.week_start,
        idempotency_key=inputs.idempotency_key,
        environment="production",
    )


def _configuration(inputs: ManualRunInputs, **changes) -> IngestionConfiguration:
    values = {
        "identity": "mapping-1",
        "version": 1,
        "client_id": inputs.client_id,
        "project_id": inputs.project_id,
        "project_slug": "example.invalid",
        "provider": inputs.provider,
        "environment": "production",
        "reporting_timezone": "America/Los_Angeles",
        "external_resource_type": "ga4_property" if inputs.provider == "ga4" else "gsc_url_prefix",
        "external_resource_id": "123456789" if inputs.provider == "ga4" else "https://example.invalid/",
        "credential_binding_key": f"google-oauth/client/{inputs.provider}",
        "request_ceiling": 6 if inputs.provider == "ga4" else 4,
        "authorized_retry_count": 0,
        "enabled": True,
    }
    values.update(changes)
    return IngestionConfiguration(**values)


def _environment(**changes) -> dict[str, str]:
    values = {
        "INTERNAL_REPORTING_CLIENT_ID": INN_CLIENT,
        "INTERNAL_REPORTING_PROJECT_ID": INN_PROJECT,
        "INTERNAL_REPORTING_PROVIDER": "ga4",
        "INTERNAL_REPORTING_WEEK_START": "2026-07-20",
        "INTERNAL_REPORTING_IDEMPOTENCY_KEY": IDEMPOTENCY,
        "INTERNAL_REPORTING_MODE": "execute",
        "INTERNAL_REPORTING_ENVIRONMENT": "production",
    }
    values.update(changes)
    return values


def _encoded_manifest(payload: object) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_manual_inputs_require_canonical_client_project_and_idempotency_uuids():
    with pytest.raises(InputError):
        _inputs(client_id="Inn At Spanish Head")
    with pytest.raises(InputError):
        _inputs(project_id="not-a-project")
    with pytest.raises(InputError):
        _inputs(idempotency_key="not-an-idempotency-key")


@pytest.mark.parametrize("provider", ["google_search_console", "ads", "gbp", "bigquery", ""])
def test_manual_inputs_refuse_every_provider_outside_ga4_and_gsc(provider):
    with pytest.raises(InputError):
        _inputs(provider=provider)


def test_manual_inputs_refuse_non_monday_and_unknown_mode():
    with pytest.raises(InputError):
        _inputs(week_start=date(2026, 7, 21))
    with pytest.raises(InputError):
        _inputs(mode="scheduled")


def test_environment_parser_rejects_malformed_dates_and_environment():
    with pytest.raises(InputError):
        parse_inputs(_environment(INTERNAL_REPORTING_WEEK_START="07/20/2026"))
    with pytest.raises(InputError):
        parse_inputs(_environment(INTERNAL_REPORTING_ENVIRONMENT="prod"))


def test_environment_parser_accepts_an_explicit_completed_week_shape():
    inputs = parse_inputs(_environment())
    assert inputs.week_start == date(2026, 7, 20)
    assert inputs.week_end == date(2026, 7, 26)


def test_completed_week_validation_uses_configuration_timezone_and_rejects_current_week():
    inputs = _inputs(week_start=date(2026, 8, 3))
    with pytest.raises(InputError):
        validate_manual_configuration(
            inputs,
            _request(inputs),
            _configuration(inputs),
            now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        )


def test_completed_week_validation_accepts_a_prior_monday_through_sunday_week():
    inputs = _inputs()
    validate_manual_configuration(
        inputs,
        _request(inputs),
        _configuration(inputs),
        now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("change", "value"),
    [
        ("client_id", ALUMA_CLIENT),
        ("project_id", ALUMA_PROJECT),
        ("provider", "gsc"),
        ("environment", "development"),
        ("request_ceiling", 7),
        ("authorized_retry_count", 1),
        ("external_resource_type", "gsc_url_prefix"),
    ],
)
def test_configuration_cross_wiring_and_policy_drift_fail_before_provider_work(change, value):
    inputs = _inputs()
    configuration = _configuration(inputs, **{change: value})
    with pytest.raises(ConfigurationError):
        validate_manual_configuration(
            inputs,
            _request(inputs),
            configuration,
            now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        )


def test_ga4_and_gsc_keep_exact_independent_resource_kinds():
    ga4 = _inputs(provider="ga4")
    validate_manual_configuration(
        ga4,
        _request(ga4),
        _configuration(ga4, external_resource_type="ga4_property"),
        now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
    )
    gsc = _inputs(provider="gsc")
    for kind in ("gsc_site", "gsc_domain_property", "gsc_url_prefix"):
        validate_manual_configuration(
            gsc,
            _request(gsc),
            _configuration(gsc, external_resource_type=kind),
            now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        )


def test_grant_manifest_is_structured_pinned_and_contains_no_operator_resource_override(tmp_path):
    grant = tmp_path / "grant.json"
    grant.write_text("{}", encoding="utf-8")
    binding = "google-oauth/inn/ga4"
    grants = parse_grants(
        _encoded_manifest({binding: {"provider": "ga4", "path": str(grant), "version": "1"}})
    )
    assert grants[binding].path == grant
    assert "resource" not in json.loads(base64.b64decode(_encoded_manifest({binding: {"provider": "ga4", "path": str(grant), "version": "1"}})))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"binding": {"provider": "ads", "path": "/grant", "version": "1"}},
        {"binding": {"provider": "ga4", "path": "relative", "version": "1"}},
        {"binding": {"provider": "ga4", "path": "/grant", "version": "latest"}},
        {"binding": {"provider": "ga4", "path": "/grant", "version": "1", "resource": "123"}},
    ],
)
def test_grant_manifest_fails_closed_on_incomplete_or_contradictory_configuration(payload):
    with pytest.raises(CredentialError):
        parse_grants(_encoded_manifest(payload))


def test_cross_client_grants_are_selected_only_by_portal_returned_binding(tmp_path):
    inn_file = tmp_path / "inn.json"
    aluma_file = tmp_path / "aluma.json"
    inn_file.write_text("{}", encoding="utf-8")
    aluma_file.write_text("{}", encoding="utf-8")
    manifest = {
        "google-oauth/inn/ga4": {"provider": "ga4", "path": str(inn_file), "version": "1"},
        "google-oauth/aluma/ga4": {"provider": "ga4", "path": str(aluma_file), "version": "2"},
    }
    grants = parse_grants(_encoded_manifest(manifest))
    inn = _inputs()
    aluma = _inputs(client_id=ALUMA_CLIENT, project_id=ALUMA_PROJECT)
    assert validate_grant_readiness(
        _configuration(inn, credential_binding_key="google-oauth/inn/ga4"), grants
    ).path == inn_file
    assert validate_grant_readiness(
        _configuration(aluma, credential_binding_key="google-oauth/aluma/ga4"), grants
    ).path == aluma_file


def test_wrong_client_binding_or_provider_cannot_rescue_configuration(tmp_path):
    inn_file = tmp_path / "inn.json"
    inn_file.write_text("{}", encoding="utf-8")
    grants = parse_grants(
        _encoded_manifest(
            {"google-oauth/inn/ga4": {"provider": "ga4", "path": str(inn_file), "version": "1"}}
        )
    )
    aluma = _inputs(client_id=ALUMA_CLIENT, project_id=ALUMA_PROJECT)
    with pytest.raises(CredentialError):
        validate_grant_readiness(
            _configuration(aluma, credential_binding_key="google-oauth/aluma/ga4"), grants
        )
    with pytest.raises(CredentialError):
        validate_grant_readiness(
            _configuration(aluma, provider="gsc", credential_binding_key="google-oauth/inn/ga4"), grants
        )


def test_grant_readiness_refuses_missing_mount_without_reading_a_secret(tmp_path):
    missing = tmp_path / "missing.json"
    binding = "google-oauth/inn/ga4"
    grants = parse_grants(
        _encoded_manifest({binding: {"provider": "ga4", "path": str(missing), "version": "1"}})
    )
    with pytest.raises(CredentialError):
        validate_grant_readiness(_configuration(_inputs(), credential_binding_key=binding), grants)


def test_manual_runner_source_contains_no_original_client_week_or_resource_identity():
    source = (Path(__file__).parents[1] / "src" / "cloud_ingestion" / "manual_weekly_runner.py").read_text()
    for forbidden in ("Inn At Spanish Head", "2026-07-27", "460499108", "spanishhead.com"):
        assert forbidden not in source
