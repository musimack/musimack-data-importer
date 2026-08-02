"""R8-C5 Group 1 provider classification and configuration.

Covers the product-owner supplied identifiers and the recovered credential
reference convention. Every test is offline: no credential file is opened, no
secret environment value is resolved, no provider client is constructed, and no
network call is made.

Tests that depend on the operator's ignored local configuration skip with an
explicit reason when it is absent, so a skip can never be mistaken for a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.provider_configuration_verification import (
    APPROVED_COST_PER_PROFILE,
    APPROVED_GROUP_COST,
    APPROVED_GROUP_REQUESTS,
    APPROVED_REQUESTS_PER_PROFILE,
    GA4_METADATA_OPERATION,
    GROUP_1_PROFILES,
    GSC_SITE_OPERATION,
    MAX_RETRIES_PER_OPERATION,
    SUPPORTED_OPERATIONS,
    ProviderVerificationError,
    plan_group_1,
    resolve_provider_applicability,
)

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIGS = ROOT / "local-profile-configs"

# Product-owner supplied by David Wallace on 2026-08-02. Authoritative.
GROUP_1_IDENTIFIERS = {
    "avs": ("285955540", "https://avselevator.com/"),
    "lucy-escobar": ("508902753", "https://lucyescobar.com/"),
    "western-wood-structures": ("309883914", "https://westernwoodstructures.com/"),
}

# The eight clients David named as sharing one retrieval mechanism. Seven have
# governed registry profiles. BeWell does not, and that discrepancy is asserted
# explicitly below rather than quietly dropped from the list.
SHARED_MECHANISM_PROFILES = [
    "aluma-seo-geo",
    "avs",
    "bewell",
    "lucy-escobar",
    "pinnacle-contractors",
    "inn-at-spanish-head",
    "steadfast-decks-and-fences",
    "western-wood-structures",
]

REGISTERED_SHARED_MECHANISM_PROFILES = [
    slug for slug in SHARED_MECHANISM_PROFILES if slug != "bewell"
]


def _local_config(slug: str) -> dict:
    path = LOCAL_CONFIGS / f"{slug}.local.json"
    if not path.exists():
        pytest.skip(f"operator local config {path.name} is absent; identifiers NOT verified")
    return json.loads(path.read_text(encoding="utf-8"))


# Provider classification


@pytest.mark.parametrize("slug", GROUP_1_PROFILES)
def test_every_group_1_profile_declares_both_providers(slug: str) -> None:
    applicability = resolve_provider_applicability(slug)
    assert applicability["status"] == "applicable_providers_declared"
    assert applicability["ga4_applicable"] is True
    assert applicability["gsc_applicable"] is True


def test_avs_is_no_longer_unresolved() -> None:
    """David classified AVS as using both providers on 2026-08-02."""
    assert resolve_provider_applicability("avs")["status"] == "applicable_providers_declared"


def test_avs_registry_domain_is_no_longer_a_placeholder() -> None:
    registry = json.loads((ROOT / "config" / "dashboard_lab_profiles.json").read_text(encoding="utf-8"))
    avs = next(item for item in registry["profiles"] if item["slug"] == "avs")
    assert avs["domain"] == "avselevator.com"
    assert avs["data_sources"] == ["ga4", "gsc"]


# Exact identifiers


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_exact_ga4_property_id_is_recorded(slug: str) -> None:
    expected, _ = GROUP_1_IDENTIFIERS[slug]
    assert _local_config(slug)["ga4"]["property_id"] == expected


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_exact_gsc_site_url_is_recorded(slug: str) -> None:
    _, expected = GROUP_1_IDENTIFIERS[slug]
    assert _local_config(slug)["gsc"]["site_url"] == expected


# Recovered credential-reference convention


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_credential_references_are_paths_outside_the_repository(slug: str) -> None:
    payload = _local_config(slug)
    for provider in ("ga4", "gsc"):
        for field in ("oauth_client_secrets_file", "oauth_token_file"):
            reference = payload[provider][field]
            resolved = Path(reference).expanduser().resolve(strict=False)
            with pytest.raises(ValueError):
                resolved.relative_to(ROOT.resolve(strict=False))


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_the_oauth_client_secret_reference_is_shared(slug: str) -> None:
    """One OAuth client secret is shared across clients and both providers."""
    payload = _local_config(slug)
    assert payload["ga4"]["oauth_client_secrets_file"] == payload["gsc"]["oauth_client_secrets_file"]


def test_all_group_1_profiles_share_one_oauth_client_secret_reference() -> None:
    references = {
        _local_config(slug)["ga4"]["oauth_client_secrets_file"] for slug in GROUP_1_IDENTIFIERS
    }
    assert len(references) == 1


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_token_references_are_client_and_provider_specific(slug: str) -> None:
    """Tokens are per client and per provider, unlike the shared client secret."""
    payload = _local_config(slug)
    ga4_token = payload["ga4"]["oauth_token_file"]
    gsc_token = payload["gsc"]["oauth_token_file"]
    assert ga4_token != gsc_token
    assert ga4_token.endswith("ga4-token.json")
    assert gsc_token.endswith("gsc-token.json")


def test_no_two_group_1_profiles_share_a_token_reference() -> None:
    tokens: list[str] = []
    for slug in GROUP_1_IDENTIFIERS:
        payload = _local_config(slug)
        tokens.append(payload["ga4"]["oauth_token_file"])
        tokens.append(payload["gsc"]["oauth_token_file"])
    assert len(set(tokens)) == len(tokens)


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_local_config_contains_no_secret_material(slug: str) -> None:
    serialized = json.dumps(_local_config(slug)).lower()
    for forbidden in [
        "refresh_token",
        "private_key",
        "client_secret\"",
        "access_token",
        "-----begin",
        "_resolved_",
    ]:
        assert forbidden not in serialized


# Shared mechanism across the eight named clients


def test_seven_of_the_eight_named_profiles_exist_in_the_governed_registry() -> None:
    registry = json.loads((ROOT / "config" / "dashboard_lab_profiles.json").read_text(encoding="utf-8"))
    slugs = {item["slug"] for item in registry["profiles"]}
    missing = [slug for slug in REGISTERED_SHARED_MECHANISM_PROFILES if slug not in slugs]
    assert not missing, missing


def test_bewell_is_named_by_david_but_absent_from_the_governed_registry() -> None:
    """A recorded discrepancy, not a silent omission.

    David named BeWell among the eight clients sharing one retrieval mechanism,
    and the operator token directory carries BeWell tokens, but no BeWell
    profile exists in the governed registry. BeWell is outside Group 1 so it
    blocks nothing here, and it needs David's direction before any BeWell work.
    """
    registry = json.loads((ROOT / "config" / "dashboard_lab_profiles.json").read_text(encoding="utf-8"))
    slugs = {item["slug"] for item in registry["profiles"]}
    assert "bewell" not in slugs
    assert "bewell" in SHARED_MECHANISM_PROFILES


def test_the_same_governed_architecture_serves_every_profile() -> None:
    """One code path, one schema, one operation set for all profiles.

    "Same mechanism" means the same governed architecture and workflow. It does
    not require identical secret files: tokens are legitimately per client.
    """
    assert SUPPORTED_OPERATIONS == (GA4_METADATA_OPERATION, GSC_SITE_OPERATION)
    assert len(REGISTERED_SHARED_MECHANISM_PROFILES) == 7
    for slug in GROUP_1_PROFILES:
        applicability = resolve_provider_applicability(slug)
        assert applicability["status"] == "applicable_providers_declared"


# Group plan


def test_group_1_plans_exactly_six_requests() -> None:
    plan = plan_group_1(list(GROUP_1_PROFILES))
    assert plan["potential_maximum_requests"] == APPROVED_GROUP_REQUESTS == 6
    assert plan["group_request_ceiling"] == 6
    assert plan["group_cost_ceiling"] == APPROVED_GROUP_COST == 3.0
    assert [item["planned_requests_when_configured"] for item in plan["profiles"]] == [2, 2, 2]


def test_group_1_order_is_deterministic() -> None:
    forward = plan_group_1(list(GROUP_1_PROFILES))
    reverse = plan_group_1(list(reversed(GROUP_1_PROFILES)))
    assert forward["execution_order"] == reverse["execution_order"] == list(GROUP_1_PROFILES)


def test_group_1_enforces_zero_retries_and_no_pagination() -> None:
    plan = plan_group_1(list(GROUP_1_PROFILES))
    assert plan["max_retries_per_operation"] == MAX_RETRIES_PER_OPERATION == 0
    # sites.get is an exact lookup, so nothing paginates and the plan equals the max.
    assert plan["potential_maximum_requests"] == 2 * len(GROUP_1_PROFILES)


def test_group_1_allows_only_the_two_approved_operations() -> None:
    assert plan_group_1(list(GROUP_1_PROFILES))["approved_operations"] == list(SUPPORTED_OPERATIONS)


def test_group_1_rejects_a_fourth_profile() -> None:
    with pytest.raises(ProviderVerificationError):
        plan_group_1(list(GROUP_1_PROFILES) + ["aluma-seo-geo"])


def test_group_1_cannot_claim_completion_with_a_missing_profile() -> None:
    plan = plan_group_1(["avs", "lucy-escobar"])
    assert plan["group_complete"] is False
    assert "western-wood-structures" in plan["missing_profiles"]


def test_group_plan_never_reports_execution_as_authorized() -> None:
    plan = plan_group_1(list(GROUP_1_PROFILES))
    assert plan["provider_execution_authorized"] is False
    assert plan["executable_requests_now"] == 0
    assert all(item["can_enter_provider_verification"] is False for item in plan["profiles"])


def test_approved_per_client_envelope_is_recorded() -> None:
    assert APPROVED_REQUESTS_PER_PROFILE == 2
    assert APPROVED_COST_PER_PROFILE == 1.0


# Offline boundary through the real CLI


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_cli_offline_reports_structural_readiness_without_touching_credentials(slug: str) -> None:
    _local_config(slug)  # skips when the operator config is absent
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_client_report_provider_configuration.py"),
            "--profile",
            slug,
            "--authorized-profile",
            slug,
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["final_state"] == "structurally_ready"
    assert evidence["max_requests_total"] == 2
    assert evidence["required_request_ceiling"] == 2
    assert evidence["credential_contents_accessed"] is False
    assert evidence["provider_client_constructed"] is False
    assert evidence["provider_requests_executed"] == 0
    assert evidence["provider_verified"] is False
    assert evidence["provider_execution_authorized"] is False


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_cli_evidence_never_contains_a_credential_path(slug: str) -> None:
    _local_config(slug)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_client_report_provider_configuration.py"),
            "--profile",
            slug,
            "--authorized-profile",
            slug,
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    for forbidden in ["importer-private-tokens", "oauth-client-secret", "ga4-token.json", "gsc-token.json"]:
        assert forbidden not in result.stdout


# Git safety


@pytest.mark.parametrize("slug", sorted(GROUP_1_IDENTIFIERS))
def test_local_configs_are_ignored_by_git(slug: str) -> None:
    path = LOCAL_CONFIGS / f"{slug}.local.json"
    if not path.exists():
        pytest.skip("operator local config absent; ignore status NOT verified")
    result = subprocess.run(
        ["git", "check-ignore", "-v", f"local-profile-configs/{slug}.local.json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, "local profile config is NOT ignored by Git"


def test_no_local_config_is_tracked_by_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", "local-profile-configs/"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    tracked = [line for line in result.stdout.splitlines() if line.endswith(".local.json")]
    assert tracked == [], tracked
