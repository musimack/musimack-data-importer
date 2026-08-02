"""Real-loader coverage for provider configuration verification.

These tests exist because of a specific defect. The original suite handcrafted
configuration dictionaries the loader never produces, so a contract mismatch
between ``as_safe_dict()`` and the structural validator went undetected: the
loader exposes ``property_id`` as a **boolean presence flag**, and the validator
was comparing that flag against a numeric-property regex. Every correctly
configured profile would have failed structural validation.

Every test here drives the **real loader** against synthetic local
configuration files written to a temporary directory. No real credential, real
client identifier, or real provider is used, and nothing touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.profile_authorization import authorize_profile
from src.profile_local_config import load_profile_local_config
from src.provider_configuration_verification import (
    build_call_plan,
    offline_validate,
    resolve_provider_applicability,
    validate_profile_configuration,
)

ROOT = Path(__file__).resolve().parents[1]

# Synthetic values. Not real client identifiers.
SYNTHETIC_PROPERTY_ID = "987654321"
SYNTHETIC_SITE_URL = "https://synthetic-test-site.invalid/"

BOTH_APPLICABLE = {
    "status": "applicable_providers_declared",
    "ga4_applicable": True,
    "gsc_applicable": True,
    "reason": "test fixture",
}


def _write_config(tmp_path: Path, slug: str, payload: dict) -> Path:
    path = tmp_path / f"{slug}.local.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _complete_payload(tmp_path: Path, slug: str = "aluma-seo-geo") -> dict:
    outside = tmp_path / "outside-repo-secrets"
    outside.mkdir(exist_ok=True)
    secrets = outside / "client-secret.json"
    token = outside / "token.json"
    # Files are created so the loader's own existence check passes. Their
    # contents are never read by the validator.
    secrets.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")
    return {
        # Must match the slug the loader is asked for, or it refuses the file.
        "profile": slug,
        "ga4": {
            "property_id": SYNTHETIC_PROPERTY_ID,
            "oauth_client_secrets_file": str(secrets),
            "oauth_token_file": str(token),
        },
        "gsc": {
            "site_url": SYNTHETIC_SITE_URL,
            "oauth_client_secrets_file": str(secrets),
            "oauth_token_file": str(token),
        },
    }


def _load(tmp_path: Path, slug: str, payload: dict, env: dict | None = None) -> tuple[dict, dict]:
    """Load through the real loader.

    ``env`` defaults to empty. The loader never reads ``os.environ``
    implicitly: an environment mapping must be handed to it explicitly, which
    is a stronger credential boundary than merely not resolving secrets.
    """
    _write_config(tmp_path, slug, payload)
    config = load_profile_local_config(slug, config_dir=tmp_path, env=env or {})
    providers = config.as_safe_dict().get("providers") or {}
    return dict(providers.get("ga4") or {}), dict(providers.get("gsc") or {})


def _validate(ga4, gsc):
    return validate_profile_configuration(
        "synthetic", ga4, gsc, repository_root=ROOT, ga4_applicable=True, gsc_applicable=True
    )


# The safe contract


def test_real_loader_exposes_safe_property_id_for_a_direct_local_value(tmp_path) -> None:
    ga4, _ = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    assert ga4["_safe_property_id"] == SYNTHETIC_PROPERTY_ID


def test_real_loader_exposes_safe_property_id_for_an_environment_reference(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["ga4"].pop("property_id")
    payload["ga4"]["property_id_env"] = "SYNTHETIC_GA4_PROPERTY_ID"
    env = {
        "SYNTHETIC_GA4_PROPERTY_ID": SYNTHETIC_PROPERTY_ID,
        "UNRELATED_SECRET": "must-not-appear",
    }
    ga4, _ = _load(tmp_path, "aluma-seo-geo", payload, env=env)
    assert ga4["_safe_property_id"] == SYNTHETIC_PROPERTY_ID
    # An unrelated environment secret must never be carried into the safe dict.
    assert "must-not-appear" not in json.dumps(ga4)


def test_loader_never_reads_process_environment_implicitly(tmp_path, monkeypatch) -> None:
    """A process-level variable must not silently satisfy configuration."""
    monkeypatch.setenv("SYNTHETIC_GA4_PROPERTY_ID", SYNTHETIC_PROPERTY_ID)
    payload = _complete_payload(tmp_path)
    payload["ga4"].pop("property_id")
    payload["ga4"]["property_id_env"] = "SYNTHETIC_GA4_PROPERTY_ID"
    ga4, _ = _load(tmp_path, "aluma-seo-geo", payload)  # no env passed
    assert not ga4.get("_safe_property_id")


def test_resolved_property_id_is_absent_from_the_safe_dictionary(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    assert "_resolved_property_id" not in ga4
    assert not [key for key in ga4 if key.startswith("_resolved_")]
    assert not [key for key in gsc if key.startswith("_resolved_")]


def test_boolean_presence_flag_is_never_treated_as_the_identifier(tmp_path) -> None:
    """The exact defect. ``property_id`` is a bool, and must never be the ID."""
    ga4, _ = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    assert ga4["property_id"] is True
    result = _validate(ga4, _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))[1])
    assert not any("True" in finding for finding in result.findings)


def test_real_loader_preserves_safe_site_url(tmp_path) -> None:
    _, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    assert gsc["_safe_site_url"] == SYNTHETIC_SITE_URL


def test_credential_environment_values_remain_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SYNTHETIC_SECRET_ENV", "SENTINEL-SECRET")
    payload = _complete_payload(tmp_path)
    payload["gsc"]["oauth_client_secrets_env"] = "SYNTHETIC_SECRET_ENV"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert "SENTINEL-SECRET" not in json.dumps({"ga4": ga4, "gsc": gsc})


def test_credential_file_contents_are_never_opened(tmp_path, monkeypatch) -> None:
    payload = _complete_payload(tmp_path)
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)

    import builtins

    real_open = builtins.open

    def guard(path, *args, **kwargs):
        if "client-secret" in str(path) or "token.json" in str(path):
            raise AssertionError(f"credential file was opened: {path}")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guard)
    _validate(ga4, gsc)


# Structural validation against the real loader


def test_a_fully_valid_synthetic_configuration_reaches_structurally_ready(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    result = _validate(ga4, gsc)
    assert result.ready, result.findings
    assert result.ga4_property_id == SYNTHETIC_PROPERTY_ID
    assert result.gsc_site_url == SYNTHETIC_SITE_URL


def test_incorrect_ga4_property_id_fails(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["ga4"]["property_id"] = "properties/987654321"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert any("numeric property identifier" in f for f in _validate(ga4, gsc).findings)


def test_incorrect_gsc_site_url_fails(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["gsc"]["site_url"] = "synthetic-test-site.invalid"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert any("supported site identifier" in f for f in _validate(ga4, gsc).findings)


def test_placeholder_ga4_property_id_fails(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["ga4"]["property_id"] = "REQUIRES_DAVID_GA4_PROPERTY_ID"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert any("placeholder" in f for f in _validate(ga4, gsc).findings)


def test_placeholder_gsc_site_url_fails(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["gsc"]["site_url"] = "REQUIRES_DAVID_GSC_SITE_URL"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert any("placeholder" in f for f in _validate(ga4, gsc).findings)


def test_missing_local_file_fails_truthfully(tmp_path) -> None:
    config = load_profile_local_config("aluma-seo-geo", config_dir=tmp_path)
    providers = config.as_safe_dict().get("providers") or {}
    result = _validate(dict(providers.get("ga4") or {}), dict(providers.get("gsc") or {}))
    assert not result.ready
    assert any("missing" in f or "not configured" in f for f in result.findings)


def test_sc_domain_property_is_accepted(tmp_path) -> None:
    payload = _complete_payload(tmp_path)
    payload["gsc"]["site_url"] = "sc-domain:synthetic-test-site.invalid"
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", payload)
    assert _validate(ga4, gsc).ready


# Applicability drives planning


def test_provider_applicability_absent_prevents_provider_planning() -> None:
    """An unregistered profile is unresolved and plans nothing.

    AVS previously served as this fixture. David classified it on 2026-08-02,
    so an unknown slug is used instead and the behavior is still asserted.
    """
    applicability = resolve_provider_applicability("not-a-registered-profile")
    assert applicability["status"] == "provider_applicability_unresolved"
    assert applicability["ga4_applicable"] is False
    assert applicability["gsc_applicable"] is False


def test_avs_is_now_classified_as_using_both_providers() -> None:
    applicability = resolve_provider_applicability("avs")
    assert applicability["status"] == "applicable_providers_declared"
    assert applicability["ga4_applicable"] is True
    assert applicability["gsc_applicable"] is True


def test_ga4_only_applicability_plans_one_request(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    structural = validate_profile_configuration(
        "synthetic", ga4, gsc, repository_root=ROOT, ga4_applicable=True, gsc_applicable=False
    )
    plan = build_call_plan("synthetic", structural, ga4_applicable=True, gsc_applicable=False)
    assert plan.max_requests == 1
    assert plan.operation_names == ["ga4.properties.getMetadata"]


def test_gsc_only_applicability_plans_one_request(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    structural = validate_profile_configuration(
        "synthetic", ga4, gsc, repository_root=ROOT, ga4_applicable=False, gsc_applicable=True
    )
    plan = build_call_plan("synthetic", structural, ga4_applicable=False, gsc_applicable=True)
    assert plan.max_requests == 1
    assert plan.operation_names == ["gsc.sites.get"]


def test_both_applicable_plans_two_requests(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    plan = build_call_plan("synthetic", _validate(ga4, gsc))
    assert plan.max_requests == 2


def test_no_applicable_provider_plans_zero_and_cannot_claim_completion(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    structural = validate_profile_configuration(
        "synthetic", ga4, gsc, repository_root=ROOT, ga4_applicable=False, gsc_applicable=False
    )
    plan = build_call_plan("synthetic", structural, ga4_applicable=False, gsc_applicable=False)
    assert plan.max_requests == 0
    assert not structural.ready
    assert any("nothing to verify" in f for f in structural.findings)


@pytest.mark.parametrize("profile", ["lucy-escobar", "western-wood-structures"])
def test_group_1_declared_profiles_would_plan_exactly_two_when_complete(profile: str) -> None:
    applicability = resolve_provider_applicability(profile)
    assert applicability["status"] == "applicable_providers_declared"
    planned = int(applicability["ga4_applicable"]) + int(applicability["gsc_applicable"])
    assert planned == 2


def test_offline_validate_reports_structural_and_provider_readiness_separately(tmp_path) -> None:
    ga4, gsc = _load(tmp_path, "aluma-seo-geo", _complete_payload(tmp_path))
    evidence = offline_validate(
        authorization=authorize_profile("lucy-escobar", ["lucy-escobar"]),
        ga4_config=ga4,
        gsc_config=gsc,
        repository_root=ROOT,
        applicability=BOTH_APPLICABLE,
    )
    assert evidence["final_state"] == "structurally_ready"
    # Structurally ready is never described as provider verified.
    assert evidence["provider_verified"] is False
    assert evidence["provider_execution_authorized"] is False
    assert evidence["required_request_ceiling"] == 2
