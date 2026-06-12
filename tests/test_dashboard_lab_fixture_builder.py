import json

import pytest

from src.dashboard_lab.fixture_builder import (
    EXPECTED_FILES,
    FixtureValidationError,
    build_all_profiles,
    build_all_services_fixture,
    build_profile_fixture,
    list_profile_slugs,
    profile_payloads,
    validate_dashboard_lab_export_folder,
    validate_dashboard_lab_fixture,
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_all_services_fixture_writes_expected_files(tmp_path):
    result = build_all_services_fixture(tmp_path)

    assert [path.name for path in result.files] == EXPECTED_FILES
    for filename in EXPECTED_FILES:
        assert (tmp_path / filename).exists()

    combined = _read_json(tmp_path / "combined-dashboard-summary.json")
    assert combined["client_name"] == "Riverside Home Services Demo"
    assert combined["domain"] == "riversidehomeservices.example"
    assert set(combined["provider_summaries"]) == {
        "ga4",
        "gsc",
        "google_ads_search",
        "google_ads_lsa",
        "local_falcon",
        "callrail",
    }


def test_build_aluma_seo_geo_excludes_paid_and_callrail_modules(tmp_path):
    result = build_profile_fixture("aluma-seo-geo", tmp_path)

    assert [path.name for path in result.files] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
    ]
    assert not (tmp_path / "google-ads-search-summary.json").exists()
    assert not (tmp_path / "google-ads-lsa-summary.json").exists()
    assert not (tmp_path / "callrail-summary.json").exists()

    combined = _read_json(tmp_path / "combined-dashboard-summary.json")
    assert combined["client_name"] == "Aluma Aesthetic Medicine"
    assert combined["provider_summaries"] == {
        "ga4": "ga4-summary.json",
        "gsc": "gsc-summary.json",
    }
    assert "paid_search" not in combined["modules_enabled"]
    assert "lsa_performance" not in combined["modules_enabled"]
    assert "call_tracking" not in combined["modules_enabled"]


def test_build_inn_at_spanish_head_fixture_is_organic_local_profile(tmp_path):
    result = build_profile_fixture("inn-at-spanish-head", tmp_path)

    assert [path.name for path in result.files] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "local-falcon-summary.json",
        "combined-dashboard-summary.json",
    ]
    assert not (tmp_path / "google-ads-search-summary.json").exists()
    assert not (tmp_path / "google-ads-lsa-summary.json").exists()
    assert not (tmp_path / "callrail-summary.json").exists()

    combined = _read_json(tmp_path / "combined-dashboard-summary.json")
    assert combined["fixture_profile"] == "inn-at-spanish-head"
    assert combined["client_name"] == "Spanish Head"
    assert combined["domain"] == "spanishhead.com"
    assert combined["provider_summaries"] == {
        "ga4": "ga4-summary.json",
        "gsc": "gsc-summary.json",
        "local_falcon": "local-falcon-summary.json",
    }
    assert "local_map_rankings" in combined["modules_enabled"]
    assert "paid_search" not in combined["modules_enabled"]
    assert "lsa_performance" not in combined["modules_enabled"]
    assert "call_tracking" not in combined["modules_enabled"]

    gsc = _read_json(tmp_path / "gsc-summary.json")
    assert gsc["top_queries"][0]["query"] == "lincoln city oceanfront hotel"
    local_falcon = _read_json(tmp_path / "local-falcon-summary.json")
    assert "lincoln city oceanfront hotel" in local_falcon["grid_metadata"]["keywords_tracked"]


def test_build_wc_land_renewal_fixture_uses_current_paid_search_filename(tmp_path):
    result = build_profile_fixture("wc-land-renewal", tmp_path)

    assert [path.name for path in result.files] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "local-falcon-summary.json",
        "google-ads-summary.json",
        "callrail-summary.json",
        "combined-dashboard-summary.json",
    ]
    assert not (tmp_path / "google-ads-search-summary.json").exists()

    combined = _read_json(tmp_path / "combined-dashboard-summary.json")
    assert combined["fixture_profile"] == "wc-land-renewal"
    assert combined["client_name"] == "WC Land Renewal"
    assert combined["provider_summaries"] == {
        "ga4": "ga4-summary.json",
        "gsc": "gsc-summary.json",
        "local_falcon": "local-falcon-summary.json",
        "google_ads_search": "google-ads-summary.json",
        "callrail": "callrail-summary.json",
    }


def test_build_all_profiles_writes_each_profile_folder(tmp_path):
    results = build_all_profiles(tmp_path)

    assert [result.profile.slug for result in results] == list_profile_slugs()
    for profile_slug in list_profile_slugs():
        profile_dir = tmp_path / profile_slug
        assert (profile_dir / "client-profile.json").exists()
        assert (profile_dir / "combined-dashboard-summary.json").exists()
        validate_dashboard_lab_fixture(profile_dir)


def test_combined_summary_only_references_generated_provider_files(tmp_path):
    build_all_profiles(tmp_path)

    for profile_slug in list_profile_slugs():
        profile_dir = tmp_path / profile_slug
        combined = _read_json(profile_dir / "combined-dashboard-summary.json")
        for filename in combined["provider_summaries"].values():
            assert (profile_dir / filename).exists()


def test_maintenance_hosting_profile_validates_without_marketing_files(tmp_path):
    build_profile_fixture("maintenance-hosting-client", tmp_path)

    assert not (tmp_path / "ga4-summary.json").exists()
    assert not (tmp_path / "gsc-summary.json").exists()
    assert not (tmp_path / "google-ads-search-summary.json").exists()
    files = validate_dashboard_lab_fixture(tmp_path)
    assert [path.name for path in files] == [
        "client-profile.json",
        "website-maintenance-summary.json",
        "hosting-summary.json",
        "combined-dashboard-summary.json",
    ]


def test_validate_inn_dashboard_lab_export_folder_shape(tmp_path):
    payloads = profile_payloads("inn-at-spanish-head")
    for filename, payload in payloads.items():
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")

    files = validate_dashboard_lab_export_folder(tmp_path, "inn-at-spanish-head")

    assert [path.name for path in files] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "local-falcon-summary.json",
        "combined-dashboard-summary.json",
    ]


def test_validate_dashboard_lab_export_folder_rejects_missing_inn_file(tmp_path):
    payloads = profile_payloads("inn-at-spanish-head")
    for filename, payload in payloads.items():
        if filename != "local-falcon-summary.json":
            (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="local-falcon-summary.json"):
        validate_dashboard_lab_export_folder(tmp_path, "inn-at-spanish-head")


def test_validate_dashboard_lab_export_folder_rejects_secret_like_keys(tmp_path):
    payloads = profile_payloads("inn-at-spanish-head")
    payloads["gsc-summary.json"]["refresh_token"] = "not-allowed"
    for filename, payload in payloads.items():
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="secret-like key"):
        validate_dashboard_lab_export_folder(tmp_path, "inn-at-spanish-head")


def test_validate_dashboard_lab_fixture_rejects_secret_like_keys(tmp_path):
    build_all_services_fixture(tmp_path)
    ga4_path = tmp_path / "ga4-summary.json"
    payload = _read_json(ga4_path)
    payload["api_key"] = "not-allowed"
    ga4_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="secret-like key"):
        validate_dashboard_lab_fixture(tmp_path)


def test_validate_dashboard_lab_fixture_rejects_callrail_phone_numbers(tmp_path):
    build_all_services_fixture(tmp_path)
    callrail_path = tmp_path / "callrail-summary.json"
    payload = _read_json(callrail_path)
    payload["safe_call_examples"][0]["caller_label"] = "503-555-0199"
    callrail_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="phone number"):
        validate_dashboard_lab_fixture(tmp_path)


def test_validate_dashboard_lab_fixture_rejects_callrail_recordings(tmp_path):
    build_all_services_fixture(tmp_path)
    callrail_path = tmp_path / "callrail-summary.json"
    payload = _read_json(callrail_path)
    payload["safe_call_examples"][0]["recording_url"] = "https://example.invalid/audio"
    callrail_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="forbidden call data key"):
        validate_dashboard_lab_fixture(tmp_path)
