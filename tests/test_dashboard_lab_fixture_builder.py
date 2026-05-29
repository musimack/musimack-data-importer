import json

import pytest

from src.dashboard_lab.fixture_builder import (
    EXPECTED_FILES,
    FixtureValidationError,
    build_all_services_fixture,
    validate_dashboard_lab_fixture,
)


def test_build_all_services_fixture_writes_expected_files(tmp_path):
    result = build_all_services_fixture(tmp_path)

    assert [path.name for path in result.files] == EXPECTED_FILES
    for filename in EXPECTED_FILES:
        assert (tmp_path / filename).exists()

    combined = json.loads((tmp_path / "combined-dashboard-summary.json").read_text())
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


def test_validate_dashboard_lab_fixture_rejects_secret_like_keys(tmp_path):
    build_all_services_fixture(tmp_path)
    ga4_path = tmp_path / "ga4-summary.json"
    payload = json.loads(ga4_path.read_text())
    payload["api_key"] = "not-allowed"
    ga4_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="secret-like key"):
        validate_dashboard_lab_fixture(tmp_path)


def test_validate_dashboard_lab_fixture_rejects_callrail_phone_numbers(tmp_path):
    build_all_services_fixture(tmp_path)
    callrail_path = tmp_path / "callrail-summary.json"
    payload = json.loads(callrail_path.read_text())
    payload["safe_call_examples"][0]["caller_label"] = "503-555-0199"
    callrail_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="phone number"):
        validate_dashboard_lab_fixture(tmp_path)


def test_validate_dashboard_lab_fixture_rejects_callrail_recordings(tmp_path):
    build_all_services_fixture(tmp_path)
    callrail_path = tmp_path / "callrail-summary.json"
    payload = json.loads(callrail_path.read_text())
    payload["safe_call_examples"][0]["recording_url"] = "https://example.invalid/audio"
    callrail_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FixtureValidationError, match="forbidden call data key"):
        validate_dashboard_lab_fixture(tmp_path)
