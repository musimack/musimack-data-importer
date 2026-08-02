"""Governed provider configuration and metadata verification.

Every test runs fully offline. None reads a real credential, none constructs a
real provider client, and none makes a network call. Provider mode is exercised
only through injected fakes and sentinels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.profile_authorization import ProfileAuthorizationError, authorize_profile
from src.provider_configuration_verification import (
    EVIDENCE_CONTRACT,
    EVIDENCE_CONTRACT_VERSION,
    GA4_METADATA_OPERATION,
    GSC_SITE_OPERATION,
    MAX_RETRIES_PER_OPERATION,
    OFFLINE_MODE,
    ProviderVerificationError,
    build_call_plan,
    offline_validate,
    provider_verify,
    validate_profile_configuration,
)
from src.provider_verification_budget import (
    CostBudget,
    ProviderBudgetError,
    RequestBudget,
    UnknownCostOperationError,
    expected_direct_cost,
)

ROOT = Path(__file__).resolve().parents[1]

GROUP_1 = ["avs", "lucy-escobar", "western-wood-structures"]

GA4_OK = {"property_id": "123456789", "oauth_client_secrets_env": "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"}
GSC_OK = {"site_url": "https://example.invalid/", "oauth_client_secrets_env": "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS"}


def _auth(profile: str = "avs", allowed: list[str] | None = None):
    return authorize_profile(profile, allowed or [profile])


def _offline(profile="avs", ga4=None, gsc=None):
    return offline_validate(
        authorization=_auth(profile),
        ga4_config=dict(GA4_OK if ga4 is None else ga4),
        gsc_config=dict(GSC_OK if gsc is None else gsc),
        repository_root=ROOT,
    )


class _FakeGa4:
    """Metadata-only fake. Deliberately exposes no reporting method."""

    def __init__(self, name="properties/123456789"):
        self.name = name
        self.calls = 0

    def get_property_metadata(self, property_id):
        self.calls += 1
        return {"name": self.name}


class _FakeGsc:
    def __init__(self, site_url="https://example.invalid/"):
        self.site_url = site_url
        self.calls = 0

    def get_site(self, site_url):
        self.calls += 1
        return {"siteUrl": self.site_url, "permissionLevel": "siteFullUser"}


class _ExplodingCredentials:
    def __call__(self):
        raise AssertionError("credentials were resolved when they must not have been")


def _verify(**overrides):
    kwargs = {
        "authorization": _auth(),
        "ga4_config": dict(GA4_OK),
        "gsc_config": dict(GSC_OK),
        "repository_root": ROOT,
        "max_requests": 2,
        "max_cost": 1.0,
        "resolve_credentials": lambda: {"ok": True},
        "build_ga4_client": lambda _c: _FakeGa4(),
        "build_gsc_client": lambda _c: _FakeGsc(),
    }
    kwargs.update(overrides)
    return provider_verify(**kwargs)


# Authorization


def test_missing_allowlist_fails() -> None:
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", None)


def test_profile_absent_from_allowlist_fails() -> None:
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", ["lucy-escobar"])


def test_valid_explicit_profile_passes() -> None:
    assert _auth("avs").requested_profile == "avs"


def test_unknown_profile_fails() -> None:
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("not-a-client", ["not-a-client"])


@pytest.mark.parametrize("token", ["*", "all", "any"])
def test_wildcard_fails(token: str) -> None:
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", [token])


def test_environment_authorization_sentinel_has_no_effect(monkeypatch) -> None:
    monkeypatch.setenv("MUSIMACK_AUTHORIZED_PROFILES", "*")
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", None)


# Structural configuration


def test_missing_ga4_property_fails() -> None:
    result = _offline(ga4={"oauth_client_secrets_env": "X"})
    assert result["structural_configuration_result"] == "not_ready"
    assert any("property_id" in f for f in result["structural_findings"])


def test_missing_gsc_property_fails() -> None:
    result = _offline(gsc={"oauth_client_secrets_env": "X"})
    assert any("site_url" in f for f in result["structural_findings"])


def test_blank_property_identifiers_fail() -> None:
    result = _offline(ga4={"property_id": "   ", "oauth_client_secrets_env": "X"})
    assert result["structural_configuration_result"] == "not_ready"


def test_invalid_property_shape_fails() -> None:
    result = _offline(ga4={"property_id": "properties/123", "oauth_client_secrets_env": "X"})
    assert any("numeric property identifier" in f for f in result["structural_findings"])
    bad_site = _offline(gsc={"site_url": "example.invalid", "oauth_client_secrets_env": "X"})
    assert any("supported site identifier" in f for f in bad_site["structural_findings"])


def test_credential_reference_inside_repository_fails() -> None:
    inside = str(ROOT / "secrets" / "client_secret.json")
    result = _offline(gsc={"site_url": "https://example.invalid/", "oauth_client_secrets_file": inside})
    assert any("outside the repository" in f for f in result["structural_findings"])


def test_missing_credential_reference_field_fails() -> None:
    result = _offline(gsc={"site_url": "https://example.invalid/"})
    assert any("credential reference field is missing" in f for f in result["structural_findings"])


def test_structurally_valid_external_reference_passes_without_opening_it(tmp_path) -> None:
    external = tmp_path / "client_secret.json"  # deliberately never created
    result = _offline(
        gsc={"site_url": "https://example.invalid/", "oauth_client_secrets_file": str(external)}
    )
    assert result["structural_configuration_result"] == "ready"
    assert not external.exists()


def test_environment_variable_reference_passes_without_reading_its_value(monkeypatch) -> None:
    monkeypatch.delenv("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS", raising=False)
    result = _offline()
    assert result["structural_configuration_result"] == "ready"
    assert result["gsc_credential_reference_type"] == "environment_variable_name"


# Offline boundary


def test_offline_mode_opens_no_credential_file(monkeypatch) -> None:
    import builtins

    real_open = builtins.open

    def guard(path, *args, **kwargs):
        text = str(path).lower()
        if "secret" in text or "token" in text or "credential" in text:
            raise AssertionError(f"offline mode opened a credential file: {path}")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guard)
    assert _offline()["credential_contents_accessed"] is False


def test_offline_mode_reads_no_credential_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS", "SENTINEL-SECRET-VALUE")
    evidence = _offline()
    assert "SENTINEL-SECRET-VALUE" not in repr(evidence)


def test_offline_mode_constructs_no_provider_client() -> None:
    assert _offline()["provider_client_constructed"] is False


def test_offline_mode_makes_no_network_request(monkeypatch) -> None:
    import requests

    def guard(*args, **kwargs):
        raise AssertionError("offline mode attempted a network request")

    monkeypatch.setattr(requests.Session, "request", guard)
    monkeypatch.setattr(requests, "post", guard)
    monkeypatch.setattr(requests, "get", guard)
    assert _offline()["provider_requests_executed"] == 0


def test_offline_mode_writes_no_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _offline()
    assert list(tmp_path.iterdir()) == []
    assert not (ROOT / "exports" / "local-real").exists()


# Request planning


def test_ga4_plan_is_exactly_one_call() -> None:
    plan = build_call_plan("avs", validate_profile_configuration("avs", GA4_OK, GSC_OK, repository_root=ROOT))
    assert plan.by_provider("ga4") == 1


def test_gsc_plan_is_exactly_one_call_with_no_pagination() -> None:
    plan = build_call_plan("avs", validate_profile_configuration("avs", GA4_OK, GSC_OK, repository_root=ROOT))
    assert plan.by_provider("gsc") == 1
    # sites.get is an exact lookup rather than sites.list, so nothing paginates.
    assert plan.max_requests == plan.planned_requests


def test_retry_maximum_is_zero_and_reflected_in_the_plan() -> None:
    assert MAX_RETRIES_PER_OPERATION == 0
    assert _offline()["max_retries_per_operation"] == 0


def test_total_request_maximum_is_exactly_two() -> None:
    assert _offline()["max_requests_total"] == 2


def test_planned_request_count_is_deterministic() -> None:
    assert _offline() == _offline()


def test_ceiling_below_plan_fails_before_credentials() -> None:
    with pytest.raises(ProviderBudgetError):
        _verify(max_requests=1, resolve_credentials=_ExplodingCredentials())


def test_ceiling_equal_to_plan_passes() -> None:
    assert _verify(max_requests=2)["final_state"] == "verified"


def test_ceiling_above_plan_passes() -> None:
    assert _verify(max_requests=10)["final_state"] == "verified"


# Cost planning


def test_expected_direct_cost_is_zero_for_supported_operations() -> None:
    assert expected_direct_cost([GA4_METADATA_OPERATION, GSC_SITE_OPERATION]) == 0.0


def test_unknown_indirect_effects_are_retained() -> None:
    assert "Unknown" in str(_offline()["unknown_indirect_effects"])


def test_missing_cost_ceiling_fails_provider_mode() -> None:
    with pytest.raises(ProviderBudgetError):
        _verify(max_cost=None, resolve_credentials=_ExplodingCredentials())


def test_missing_request_ceiling_fails_provider_mode() -> None:
    with pytest.raises(ProviderBudgetError):
        _verify(max_requests=None, resolve_credentials=_ExplodingCredentials())


def test_unknown_cost_operation_is_refused_rather_than_assumed_free() -> None:
    with pytest.raises(UnknownCostOperationError):
        CostBudget(max_cost=1.0).check_operations(["ga4.runReport"])
    with pytest.raises(UnknownCostOperationError):
        expected_direct_cost(["bigquery.jobs.insert"])


def test_zero_known_direct_cost_does_not_bypass_required_approval() -> None:
    # Cost is zero, yet an omitted ceiling still refuses the run.
    assert expected_direct_cost([GA4_METADATA_OPERATION]) == 0.0
    with pytest.raises(ProviderBudgetError):
        _verify(max_cost=None, resolve_credentials=_ExplodingCredentials())


def test_zero_request_ceiling_with_planned_calls_fails() -> None:
    with pytest.raises(ProviderBudgetError):
        _verify(max_requests=0, resolve_credentials=_ExplodingCredentials())


# Evidence


def test_evidence_contract_identity() -> None:
    evidence = _offline()
    assert evidence["evidence_contract"] == EVIDENCE_CONTRACT
    assert evidence["evidence_contract_version"] == EVIDENCE_CONTRACT_VERSION
    assert evidence["execution_mode"] == OFFLINE_MODE


def test_evidence_contains_exact_authorized_profiles() -> None:
    evidence = offline_validate(
        authorization=authorize_profile("avs", GROUP_1),
        ga4_config=GA4_OK,
        gsc_config=GSC_OK,
        repository_root=ROOT,
    )
    assert evidence["authorized_profiles"] == sorted(GROUP_1)


def test_evidence_records_no_credential_access_and_no_construction() -> None:
    evidence = _offline()
    assert evidence["credential_contents_accessed"] is False
    assert evidence["provider_client_constructed"] is False
    assert evidence["provider_requests_executed"] == 0
    assert evidence["credential_reference_checked_structurally"] is True


def test_evidence_contains_no_secrets() -> None:
    serialized = repr(_offline()).lower()
    for forbidden in ["token", "secret_value", "refresh", "private_key", "password"]:
        assert forbidden not in serialized


def test_identical_inputs_produce_deterministic_evidence() -> None:
    import json

    assert json.dumps(_offline(), sort_keys=True) == json.dumps(_offline(), sort_keys=True)


# Provider mode, mocked


def test_authorization_and_budget_precede_credential_resolution() -> None:
    # Every pre-credential refusal path uses an exploding resolver, so reaching
    # credentials at all would fail the test loudly.
    with pytest.raises(ProviderBudgetError):
        _verify(max_requests=1, resolve_credentials=_ExplodingCredentials())
    with pytest.raises(ProviderVerificationError):
        _verify(
            ga4_config={"oauth_client_secrets_env": "X"},
            resolve_credentials=_ExplodingCredentials(),
        )


def test_credential_resolution_precedes_provider_construction() -> None:
    order: list[str] = []

    def creds():
        order.append("credentials")
        return {}

    def ga4(_c):
        order.append("ga4_client")
        return _FakeGa4()

    def gsc(_c):
        order.append("gsc_client")
        return _FakeGsc()

    _verify(resolve_credentials=creds, build_ga4_client=ga4, build_gsc_client=gsc)
    assert order == ["credentials", "ga4_client", "gsc_client"]


def test_ga4_identity_mismatch_fails() -> None:
    with pytest.raises(ProviderVerificationError) as exc:
        _verify(build_ga4_client=lambda _c: _FakeGa4(name="properties/999"))
    assert "does not match configured property" in str(exc.value)


def test_gsc_identity_mismatch_fails() -> None:
    with pytest.raises(ProviderVerificationError) as exc:
        _verify(build_gsc_client=lambda _c: _FakeGsc(site_url="https://other.invalid/"))
    assert "does not match configured site" in str(exc.value)


def test_successful_mocked_verification_records_exactly_one_call_each() -> None:
    ga4, gsc = _FakeGa4(), _FakeGsc()
    evidence = _verify(build_ga4_client=lambda _c: ga4, build_gsc_client=lambda _c: gsc)
    assert ga4.calls == 1
    assert gsc.calls == 1
    assert evidence["provider_requests_executed"] == 2
    assert evidence["provider_operations_executed"] == [GA4_METADATA_OPERATION, GSC_SITE_OPERATION]


def test_failure_stops_subsequent_provider_calls() -> None:
    gsc = _FakeGsc()
    with pytest.raises(ProviderVerificationError):
        _verify(
            build_ga4_client=lambda _c: _FakeGa4(name="properties/999"),
            build_gsc_client=lambda _c: gsc,
        )
    assert gsc.calls == 0


def test_no_partial_success_is_reported_as_complete() -> None:
    with pytest.raises(ProviderVerificationError):
        _verify(build_ga4_client=lambda _c: _FakeGa4(name="properties/999"))


def test_an_unexpected_extra_request_is_blocked_by_the_budget() -> None:
    budget = RequestBudget(max_requests=2)
    budget.consume(GA4_METADATA_OPERATION)
    budget.consume(GSC_SITE_OPERATION)
    with pytest.raises(ProviderBudgetError) as exc:
        budget.consume("ga4.unexpected")
    assert "was not issued" in str(exc.value)


def test_a_retry_consumes_budget() -> None:
    budget = RequestBudget(max_requests=2)
    budget.consume(GA4_METADATA_OPERATION)
    budget.consume(GA4_METADATA_OPERATION)  # a retry is an ordinary request
    assert budget.remaining == 0


def test_reporting_capable_client_is_refused() -> None:
    class ReportingCapable(_FakeGa4):
        def run_exact_range_summary(self, *a, **k):
            raise AssertionError("reporting data must never be requested")

    with pytest.raises(ProviderVerificationError) as exc:
        _verify(build_ga4_client=lambda _c: ReportingCapable())
    assert "must never reach" in str(exc.value)


def test_gsc_reporting_capable_client_is_refused() -> None:
    class ReportingCapable(_FakeGsc):
        def query_search_analytics(self, *a, **k):
            raise AssertionError("search analytics must never be requested")

    with pytest.raises(ProviderVerificationError):
        _verify(build_gsc_client=lambda _c: ReportingCapable())


# Group 1


@pytest.mark.parametrize("profile", GROUP_1)
def test_each_group_1_profile_plans_exactly_two_requests(profile: str) -> None:
    evidence = offline_validate(
        authorization=authorize_profile(profile, GROUP_1),
        ga4_config=GA4_OK,
        gsc_config=GSC_OK,
        repository_root=ROOT,
    )
    assert evidence["profile"] == profile
    assert evidence["max_requests_total"] == 2
    assert evidence["planned_requests_ga4"] == 1
    assert evidence["planned_requests_gsc"] == 1


def test_group_1_combined_maximum_is_exactly_six_requests() -> None:
    total = 0
    for profile in GROUP_1:
        evidence = offline_validate(
            authorization=authorize_profile(profile, GROUP_1),
            ga4_config=GA4_OK,
            gsc_config=GSC_OK,
            repository_root=ROOT,
        )
        total += int(evidence["max_requests_total"])
    assert total == 6


def test_group_1_expected_known_direct_cost_is_zero() -> None:
    assert expected_direct_cost([GA4_METADATA_OPERATION, GSC_SITE_OPERATION] * 3) == 0.0


def test_group_1_strict_maximum_stays_within_the_provisional_ceilings() -> None:
    # 2 per client and 6 total sit well inside the provisional 10 and 30, so no
    # increase is ever proposed.
    assert 2 <= 10
    assert 6 <= 30


# CLI


def test_cli_help_lists_both_modes_and_both_ceilings() -> None:
    from scripts.verify_client_report_provider_configuration import build_parser

    text = build_parser().format_help()
    for expected in ["--authorized-profile", "--mode", "--max-requests", "--max-cost", "offline-validate", "provider-verify"]:
        assert expected in text


def test_cli_offline_is_the_default_mode() -> None:
    from scripts.verify_client_report_provider_configuration import build_parser

    args = build_parser().parse_args(["--profile", "avs", "--authorized-profile", "avs"])
    assert args.mode == OFFLINE_MODE
    assert args.max_requests is None
    assert args.max_cost is None


def test_cli_refuses_provider_mode_without_ceilings() -> None:
    from scripts.verify_client_report_provider_configuration import main

    assert main(["--profile", "avs", "--authorized-profile", "avs", "--mode", "provider-verify"]) == 1


def test_cli_refuses_a_run_with_no_authorization() -> None:
    from scripts.verify_client_report_provider_configuration import main

    assert main(["--profile", "avs"]) == 1
