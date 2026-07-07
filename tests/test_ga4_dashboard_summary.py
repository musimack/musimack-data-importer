import json
from datetime import date

import pytest

from scripts.write_ga4_dashboard_lab_summary import resolve_output_dir
from src.config import DateRange
from src.normalize import normalize_traffic_overview
from src.providers.ga4.dashboard_summary import (
    Ga4DashboardSummaryError,
    build_ga4_dashboard_summary,
    real_output_dir,
    validate_ga4_dashboard_summary,
    write_ga4_dashboard_summary,
)
from src.snapshot_builder import build_traffic_overview_snapshot
from tests.test_normalize import mocked_ga4_response, mocked_richer_ga4_response


def test_ga4_dashboard_summary_transforms_snapshot_to_provider_summary_shape():
    snapshot = _snapshot(mocked_richer_ga4_response())

    payload = build_ga4_dashboard_summary(
        "inn-at-spanish-head",
        snapshot,
        generated_at="2026-06-08T12:00:00+00:00",
    )

    assert payload["schema_version"] == "dashboard_lab_provider_summary.v1"
    assert payload["provider"] == "ga4"
    assert payload["provider_key"] == "google_analytics"
    assert payload["fixture_profile"] == "inn-at-spanish-head"
    assert payload["source_mode"] == "local_ga4_snapshot"
    assert payload["source_type"] == "local_real"
    assert payload["real_data"] is True
    assert payload["local_only"] is True
    assert payload["mock_data"] is False
    assert payload["reporting_period"] == {"start": "2026-04-01", "end": "2026-04-30"}
    assert payload["summary_metrics"]["users"] == 15
    assert payload["summary_metrics"]["sessions"] == 20
    assert payload["summary_metrics"]["views"] == 52
    assert payload["traffic_channels"][0]["channel"] == "Organic Search"
    assert payload["traffic_channels"][0]["sessions"] == 11
    assert payload["top_pages"][0]["label"] == "Home (/)"
    assert payload["top_pages"][0]["path"] == "/"
    assert payload["top_sources"][0]["label"] == "google / organic"
    assert payload["top_sources"][0]["sessions"] == 10
    assert payload["top_landing_pages"][0]["path"] == "/rooms/"
    assert payload["top_landing_pages"][0]["sessions"] == 12
    assert payload["time_series"][0]["date"] == "2026-04-01"
    assert payload["time_series"][0]["event_count"] == 30
    assert "property_resource" not in json.dumps(payload)


def test_ga4_dashboard_summary_handles_missing_optional_metrics_without_fake_data():
    snapshot = _snapshot(mocked_ga4_response())
    snapshot["metrics"] = [item for item in snapshot["metrics"] if item["name"] != "event_count"]

    payload = build_ga4_dashboard_summary("aluma-seo-geo", snapshot)

    assert payload["summary_metrics"]["event_count"] is None
    assert payload["summary_metrics"]["conversions"] is None
    assert "GA4 snapshot did not include optional metric: event_count." in payload["warnings"]
    assert "GA4 snapshot did not include optional metric: conversions." in payload["warnings"]
    validate_ga4_dashboard_summary(payload, expected_profile_slug="aluma-seo-geo")


def test_ga4_dashboard_summary_write_is_profile_scoped(tmp_path):
    snapshot = _snapshot(mocked_richer_ga4_response())
    payload = build_ga4_dashboard_summary("inn-at-spanish-head", snapshot)

    path = write_ga4_dashboard_summary(tmp_path / "exports" / "local-real" / "dashboard-lab" / "inn-at-spanish-head", payload)

    assert path.name == "ga4-summary.json"
    assert path.parent.as_posix().endswith("exports/local-real/dashboard-lab/inn-at-spanish-head")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["fixture_profile"] == "inn-at-spanish-head"
    assert "aluma-seo-geo" not in path.as_posix()


def test_ga4_dashboard_summary_validation_rejects_profile_mismatch():
    payload = build_ga4_dashboard_summary("inn-at-spanish-head", _snapshot(mocked_ga4_response()))

    with pytest.raises(Ga4DashboardSummaryError, match="fixture_profile mismatch"):
        validate_ga4_dashboard_summary(payload, expected_profile_slug="aluma-seo-geo")


def test_ga4_dashboard_summary_rejects_provider_internal_identifiers():
    payload = build_ga4_dashboard_summary("inn-at-spanish-head", _snapshot(mocked_ga4_response()))
    payload["property_resource"] = "properties/123456789"

    with pytest.raises(Ga4DashboardSummaryError, match="forbidden provider/internal key"):
        validate_ga4_dashboard_summary(payload, expected_profile_slug="inn-at-spanish-head")


def test_ga4_dashboard_summary_real_output_path_resolution(tmp_path):
    explicit = tmp_path / "custom-output"

    assert resolve_output_dir("inn-at-spanish-head", None, True) == real_output_dir("inn-at-spanish-head")
    assert resolve_output_dir("inn-at-spanish-head", str(explicit), True) == explicit
    assert resolve_output_dir("inn-at-spanish-head", str(explicit), False) == explicit

    with pytest.raises(Ga4DashboardSummaryError, match="--out is required"):
        resolve_output_dir("inn-at-spanish-head", None, False)


def _snapshot(response):
    normalized = normalize_traffic_overview(response)
    return build_traffic_overview_snapshot(
        normalized,
        "properties/123456789",
        DateRange(date(2026, 4, 1), date(2026, 4, 30)),
    )
