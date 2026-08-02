"""Explicit per-run profile authorization.

Every test here runs fully offline. None sets or reads a real credential, and
none constructs a real provider client.
"""

from __future__ import annotations

import argparse

import pytest

from src.profile_authorization import (
    AUTHORIZATION_CONTRACT,
    ProfileAuthorization,
    ProfileAuthorizationError,
    add_authorized_profile_argument,
    authorize_profile,
    refusal_evidence,
)

ALUMA = "aluma-seo-geo"
GROUP_1 = ["avs", "lucy-escobar", "western-wood-structures"]


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    add_authorized_profile_argument(parser)
    return parser.parse_args(argv)


# Default deny


def test_omitted_allowlist_rejects_provider_backed_execution() -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile(ALUMA, None)
    assert "no reporting profile is authorized" in str(exc.value)
    assert "no provider client was constructed" in str(exc.value)


def test_empty_allowlist_rejects_provider_backed_execution() -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile(ALUMA, [])
    assert "authorizes nothing" in str(exc.value)


def test_parsed_cli_without_the_option_yields_no_authorization() -> None:
    args = _parse(["--profile", ALUMA])
    assert args.authorized_profiles is None
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile(args.profile, args.authorized_profiles)


# Explicit authorization


def test_aluma_only_allowlist_permits_aluma() -> None:
    result = authorize_profile(ALUMA, [ALUMA])
    assert result.requested_profile == ALUMA
    assert result.authorized_profiles == (ALUMA,)
    assert result.contract == AUTHORIZATION_CONTRACT


def test_aluma_only_allowlist_rejects_every_other_governed_profile() -> None:
    for other in GROUP_1 + ["pinnacle-contractors", "inn-at-spanish-head", "steadfast-decks-and-fences"]:
        with pytest.raises(ProfileAuthorizationError) as exc:
            authorize_profile(other, [ALUMA])
        assert "is not authorized for this run" in str(exc.value)


def test_multiple_explicitly_listed_profiles_pass() -> None:
    for requested in GROUP_1:
        result = authorize_profile(requested, list(GROUP_1))
        assert result.requested_profile == requested
        assert result.authorized_profiles == tuple(sorted(GROUP_1))


def test_requested_profile_absent_from_allowlist_fails() -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile("avs", ["lucy-escobar", "western-wood-structures"])
    assert "avs is not authorized" in str(exc.value)


def test_repeatable_cli_argument_collects_each_profile() -> None:
    args = _parse(
        ["--profile", "avs", "--authorized-profile", "avs", "--authorized-profile", "lucy-escobar"]
    )
    assert args.authorized_profiles == ["avs", "lucy-escobar"]
    result = authorize_profile(args.profile, args.authorized_profiles)
    assert result.authorized_profiles == ("avs", "lucy-escobar")


# Unknown profiles


def test_unknown_requested_profile_fails() -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile("not-a-real-client", [ALUMA])
    assert "not a configured reporting profile" in str(exc.value)


def test_unknown_allowlisted_profile_fails() -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile(ALUMA, [ALUMA, "not-a-real-client"])
    assert "cannot be authorized" in str(exc.value)


# Wildcards and blanks


@pytest.mark.parametrize("token", ["*", "all", "ALL", "Any", "any", "everything", "-", "_"])
def test_wildcard_like_values_fail(token: str) -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile(ALUMA, [token])
    assert "wildcard authorization is not supported" in str(exc.value)


@pytest.mark.parametrize("token", ["", "   ", "\t", "\n"])
def test_blank_and_whitespace_only_entries_fail(token: str) -> None:
    with pytest.raises(ProfileAuthorizationError) as exc:
        authorize_profile(ALUMA, [token])
    assert "blank or whitespace-only" in str(exc.value)


def test_a_wildcard_entry_poisons_an_otherwise_valid_allowlist() -> None:
    # Refusing the whole run is the fail-closed choice. Silently ignoring the
    # wildcard and honoring the rest would let a typo widen authorization.
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile(ALUMA, [ALUMA, "*"])


# Determinism


def test_duplicate_entries_collapse_deterministically() -> None:
    result = authorize_profile(ALUMA, [ALUMA, ALUMA, ALUMA])
    assert result.authorized_profiles == (ALUMA,)


def test_argument_order_does_not_change_evidence() -> None:
    forward = authorize_profile("avs", ["avs", "lucy-escobar", "western-wood-structures"])
    reverse = authorize_profile("avs", ["western-wood-structures", "lucy-escobar", "avs"])
    assert forward.authorized_profiles == reverse.authorized_profiles
    assert forward.evidence() == reverse.evidence()


def test_aliases_resolve_in_both_the_request_and_the_allowlist() -> None:
    result = authorize_profile("aluma", ["aluma"])
    assert result.requested_profile == ALUMA
    assert result.authorized_profiles == (ALUMA,)


# Ordering relative to credentials and provider clients


def test_authorization_failure_precedes_credential_and_provider_access(monkeypatch) -> None:
    """Authorization must refuse without touching credentials or providers.

    The environment is emptied of every credential variable first. If
    authorization tried to resolve a credential it would have to read one of
    these, and the refusal below proves it did not get that far.
    """
    for name in [
        "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS",
        "MUSIMACK_GSC_OAUTH_TOKEN_FILE",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ]:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", None)


def test_authorization_reads_no_environment_variable(monkeypatch) -> None:
    # A sentinel that would authorize everything if any environment-wide
    # authorization path existed. It must have no effect.
    monkeypatch.setenv("MUSIMACK_AUTHORIZED_PROFILES", "*")
    monkeypatch.setenv("MUSIMACK_AUTHORIZE_ALL", "1")
    with pytest.raises(ProfileAuthorizationError):
        authorize_profile("avs", None)


def test_comparison_provider_refuses_without_an_authorization_object() -> None:
    from src.client_report_presentation_comparison_provider import (
        build_real_presentation_comparisons,
    )

    with pytest.raises(TypeError):
        build_real_presentation_comparisons(  # type: ignore[call-arg]
            ga4_client=object(),
            gsc_client=object(),
            profile=ALUMA,
            report_id="r",
            client_id="c",
            project_id="p",
            report_start=None,
            report_end=None,
            gsc_available_through=None,
        )


def test_comparison_provider_refuses_an_authorization_for_another_profile() -> None:
    from src.client_report_presentation_comparison_provider import (
        build_real_presentation_comparisons,
    )

    mismatched = ProfileAuthorization(requested_profile="avs", authorized_profiles=("avs",))
    with pytest.raises(ValueError) as exc:
        build_real_presentation_comparisons(
            ga4_client=object(),
            gsc_client=object(),
            profile=ALUMA,
            report_id="r",
            client_id="c",
            project_id="p",
            report_start=None,
            report_end=None,
            gsc_available_through=None,
            authorization=mismatched,
        )
    assert "not covered by the run authorization" in str(exc.value)


# Run evidence


def test_evidence_records_the_exact_allowlist_and_requested_profile() -> None:
    evidence = authorize_profile("avs", list(GROUP_1)).evidence()
    assert evidence["authorization_contract"] == AUTHORIZATION_CONTRACT
    assert evidence["requested_profile"] == "avs"
    assert evidence["authorized_profiles"] == sorted(GROUP_1)
    assert evidence["authorization_result"] == "authorized"
    assert evidence["credential_access_started"] is False
    assert evidence["provider_client_construction_started"] is False


def test_refusal_evidence_never_implies_a_successful_run() -> None:
    evidence = refusal_evidence("avs", "profile not authorized")
    assert evidence["authorization_result"] == "refused"
    assert evidence["authorized_profiles"] == []
    assert evidence["provider_calls"] == 0
    assert evidence["credential_access_started"] is False


def test_evidence_contains_no_credential_value_or_path() -> None:
    evidence = authorize_profile(ALUMA, [ALUMA]).evidence()
    serialized = repr(evidence).lower()
    for forbidden in ["secret", "token", "credential_path", "oauth", ".json", "c:\\", "/users/"]:
        assert forbidden not in serialized


def test_previous_aluma_only_boundary_is_reproducible_explicitly() -> None:
    """Naming only Aluma reproduces the retired hard-coded gate exactly."""
    assert authorize_profile(ALUMA, [ALUMA]).authorized_profiles == (ALUMA,)
    for other in GROUP_1:
        with pytest.raises(ProfileAuthorizationError):
            authorize_profile(other, [ALUMA])


def test_no_hard_coded_aluma_gate_remains_in_governed_generators() -> None:
    """The governed provider-backed entry points no longer name one profile."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    governed = [
        "scripts/pull_client_report_presentation_comparisons.py",
        "scripts/pull_ga4_exact_range_summary.py",
        "scripts/pull_ga4_ranked_exact_ranges.py",
        "scripts/pull_gsc_exact_ranges.py",
        "src/client_report_presentation_comparison_provider.py",
    ]
    for rel in governed:
        text = (root / rel).read_text(encoding="utf-8")
        assert "AUTHORIZED_PROFILE" not in text, rel
        assert "aluma-seo-geo" not in text, rel
