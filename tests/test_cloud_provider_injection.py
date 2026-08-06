from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from src.cloud_ingestion.budget import ProviderRequestBudget
from src.cloud_ingestion.domain import CredentialMaterial, IngestionConfiguration, RunRequest
from src.cloud_ingestion.errors import BudgetError
from src.cloud_ingestion.google_providers import GoogleGa4WeeklyProvider, GoogleGscWeeklyProvider
from src.config import DateRange, Ga4Config
from src.providers.ga4.client import Ga4DataClient
from src.providers.gsc.client import GscFetchConfig, GscSearchConsoleClient


class FakeCredentials:
    token = "fixture-token"
    valid = True


class InvalidCredentials:
    token = None
    valid = False


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def json(self):
        return self.payload


class Ga4Session:
    def __init__(self):
        self.calls = []

    def post(self, url, headers, json, timeout):
        self.calls.append({"url": url, "body": json, "timeout": timeout})
        return FakeResponse({"dimensionHeaders": [], "metricHeaders": [], "rows": []})


class GscSession:
    def __init__(self):
        self.calls = []

    def post(self, url, headers, json, timeout):
        self.calls.append({"url": url, "body": json, "timeout": timeout})
        return FakeResponse({"rows": []})


def _ga4_config() -> Ga4Config:
    return Ga4Config(
        auth_method="in_memory",
        property_id="fixture-property",
        oauth_client_secrets_file=None,
        oauth_token_file=None,
        service_account_file=None,
        service_account_info=None,
    )


def _configuration(provider: str) -> IngestionConfiguration:
    return IngestionConfiguration(
        identity=f"fixture-{provider}",
        version=1,
        client_id="10000000-0000-0000-0000-000000000001",
        project_id="20000000-0000-0000-0000-000000000001",
        project_slug="fixture-project",
        provider=provider,
        environment="development",
        reporting_timezone="America/Los_Angeles",
        external_resource_type="ga4_property" if provider == "ga4" else "gsc_site",
        external_resource_id="fixture-property" if provider == "ga4" else "https://fixture.invalid/",
        credential_binding_key="fixture/google/development",
        request_ceiling=6 if provider == "ga4" else 4,
        enabled=True,
    )


def _request(provider: str) -> RunRequest:
    return RunRequest(
        project_id="20000000-0000-0000-0000-000000000001",
        provider=provider,
        week_start=date(2026, 7, 27),
        idempotency_key="30000000-0000-0000-0000-000000000001",
        environment="development",
    )


def test_ga4_in_memory_credentials_and_budget_wrap_every_transport_request(monkeypatch):
    monkeypatch.setattr(
        "src.providers.ga4.client.load_oauth_credentials",
        lambda *_: (_ for _ in ()).throw(AssertionError("file credential loader must not run")),
    )
    budget = ProviderRequestBudget("ga4", 6)
    session = Ga4Session()
    client = Ga4DataClient(
        _ga4_config(),
        session=session,
        credential_loader=lambda: FakeCredentials(),
        request_counter=budget,
    )

    client.run_traffic_overview(DateRange(date(2026, 7, 27), date(2026, 8, 2)))

    assert len(session.calls) == 5
    assert budget.requests_consumed == 5
    assert budget.operations == ["ga4.runReport"] * 5


def test_ga4_budget_refuses_seventh_request_before_transport():
    budget = ProviderRequestBudget("ga4", 6)
    session = Ga4Session()
    client = Ga4DataClient(
        _ga4_config(),
        session=session,
        credential_loader=lambda: FakeCredentials(),
        request_counter=budget,
    )
    period = DateRange(date(2026, 7, 27), date(2026, 8, 2))
    client.run_traffic_overview(period)
    client.run_exact_range_summary(period)
    with pytest.raises(BudgetError):
        client.run_exact_range_summary(period)
    assert len(session.calls) == 6


def test_gsc_in_memory_credentials_and_budget_wrap_transport(monkeypatch):
    monkeypatch.setattr(
        "src.providers.gsc.client.load_gsc_oauth_credentials",
        lambda *_: (_ for _ in ()).throw(AssertionError("file credential loader must not run")),
    )
    budget = ProviderRequestBudget("gsc", 4)
    session = GscSession()
    client = GscSearchConsoleClient(
        GscFetchConfig("", "", "https://fixture.invalid/"),
        session=session,
        credential_loader=lambda: FakeCredentials(),
        request_counter=budget,
    )

    client.query_search_analytics("2026-07-27", "2026-08-02")

    assert len(session.calls) == 1
    assert budget.requests_consumed == 1
    assert budget.operations == ["gsc.searchAnalytics.query"]


def test_injected_invalid_credentials_never_trigger_interactive_or_implicit_refresh():
    ga4_session = Ga4Session()
    ga4 = Ga4DataClient(
        _ga4_config(),
        session=ga4_session,
        credential_loader=lambda: InvalidCredentials(),
        request_counter=ProviderRequestBudget("ga4", 6),
    )
    with pytest.raises(Exception, match="noninteractive credential resolution"):
        ga4.run_exact_range_summary(DateRange(date(2026, 7, 27), date(2026, 8, 2)))
    assert ga4_session.calls == []

    gsc_session = GscSession()
    gsc = GscSearchConsoleClient(
        GscFetchConfig("", "", "https://fixture.invalid/"),
        session=gsc_session,
        credential_loader=lambda: InvalidCredentials(),
        request_counter=ProviderRequestBudget("gsc", 4),
    )
    with pytest.raises(Exception, match="noninteractive credential resolution"):
        gsc.query_search_analytics("2026-07-27", "2026-08-02")
    assert gsc_session.calls == []


def test_ga4_weekly_adapter_uses_injected_client_and_five_request_plan():
    session = Ga4Session()
    adapter = GoogleGa4WeeklyProvider(
        client_factory=lambda config, **kwargs: Ga4DataClient(config, session=session, **kwargs)
    )
    budget = ProviderRequestBudget("ga4", 6)
    request = _request("ga4")
    configuration = _configuration("ga4")

    output = adapter.retrieve(
        request,
        configuration,
        CredentialMaterial(configuration.credential_binding_key, "fixture-v1", FakeCredentials()),
        budget,
    )

    assert adapter.planned_requests(request, configuration) == 5
    assert budget.requests_consumed == 5
    assert len(session.calls) == 5
    assert output.source["identity"] == "ga4.weekly_traffic_overview.v1"
    assert output.freshness["state"] == "unavailable"


def test_gsc_weekly_adapter_normalizes_fake_transport_without_file_credentials():
    class SevenDayGscSession(GscSession):
        def post(self, url, headers, json, timeout):
            self.calls.append({"url": url, "body": json, "timeout": timeout})
            rows = [
                {
                    "keys": ["fixture query", "https://fixture.invalid/page", date(2026, 7, 27 + offset).isoformat()],
                    "clicks": 1,
                    "impressions": 10,
                    "ctr": 0.1,
                    "position": 2,
                }
                for offset in range(5)
            ]
            rows.extend(
                [
                    {
                        "keys": ["fixture query", "https://fixture.invalid/page", "2026-08-01"],
                        "clicks": 1,
                        "impressions": 10,
                        "ctr": 0.1,
                        "position": 2,
                    },
                    {
                        "keys": ["fixture query", "https://fixture.invalid/page", "2026-08-02"],
                        "clicks": 1,
                        "impressions": 10,
                        "ctr": 0.1,
                        "position": 2,
                    },
                ]
            )
            return FakeResponse({"rows": rows})

    session = SevenDayGscSession()
    adapter = GoogleGscWeeklyProvider(
        client_factory=lambda config, **kwargs: GscSearchConsoleClient(config, session=session, **kwargs)
    )
    budget = ProviderRequestBudget("gsc", 4)
    request = _request("gsc")
    configuration = _configuration("gsc")

    output = adapter.retrieve(
        request,
        configuration,
        CredentialMaterial(configuration.credential_binding_key, "fixture-v1", FakeCredentials()),
        budget,
    )

    assert adapter.planned_requests(request, configuration) == 1
    assert budget.requests_consumed == 1
    assert output.freshness["state"] == "available"
    assert {metric["metric_key"] for metric in output.metrics} == {
        "clicks",
        "impressions",
        "ctr",
        "average_position",
    }
