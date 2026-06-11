import json
from pathlib import Path

import pytest

from src.local_falcon_api_responses import (
    LocalFalconApiResponseError,
    load_synthetic_api_fixture,
    merge_api_scan_into_summary,
    normalize_api_ai_analysis,
    normalize_api_competitors,
    normalize_api_grid_points,
    normalize_api_report_to_keyword_scan,
)
from src.local_falcon_importer import validate_local_falcon_summary


FIXTURES = Path(__file__).parent / "fixtures" / "local_falcon_api"


def _fixture(name):
    return load_synthetic_api_fixture(FIXTURES / name)


def test_synthetic_report_response_normalizes_to_keyword_scan():
    scan = normalize_api_report_to_keyword_scan(
        _fixture("report_summary_response.json"),
        grid_response=_fixture("report_grid_points_response.json"),
        competitor_response=_fixture("competitor_report_response.json"),
        ai_response=_fixture("ai_analysis_response.json"),
    )

    assert scan["id"] == "demo-cosmetic-service"
    assert scan["keyword"] == "demo cosmetic service"
    assert scan["scan_date"] == "2026-05-12T13:52:00"
    assert scan["grid_size_label"] == "3x3"
    assert scan["rendered_grid"] == {"rows": 3, "columns": 3}
    assert scan["radius_miles"] == 5.0
    assert scan["center"] == {"latitude": 35.1, "longitude": -101.2}
    assert scan["business"]["name"] == "Demo Visibility Clinic"
    assert scan["local_falcon_metrics"] == {"arp": 6.4, "atrp": 9.8, "solv": 22.5}
    assert scan["action_bridge"]


def test_grid_points_and_counts_normalize_consistently():
    points = normalize_api_grid_points(
        _fixture("report_grid_points_response.json"),
        "Demo Visibility Clinic",
    )
    summary = merge_api_scan_into_summary(
        profile="demo-profile",
        keyword_scan=normalize_api_report_to_keyword_scan(
            _fixture("report_summary_response.json"),
            grid_response=_fixture("report_grid_points_response.json"),
            competitor_response=_fixture("competitor_report_response.json"),
            ai_response=_fixture("ai_analysis_response.json"),
        ),
    )
    scan = summary["keyword_scans"][0]

    assert len(points) == 9
    assert points[0]["status"] == "top_3"
    assert points[2]["status"] == "weak"
    assert points[3]["status"] == "not_found"
    assert scan["data_points"] == {
        "total": 9,
        "found": 6,
        "top_3": 3,
        "top_10": 5,
        "top_20": 6,
        "not_found_or_20_plus": 3,
    }


def test_competitors_normalize_and_relationships_are_assigned():
    competitors = normalize_api_competitors(
        _fixture("competitor_report_response.json"),
        "Demo Visibility Clinic",
    )

    assert competitors[0]["name"] == "Strong Demo Spa"
    assert competitors[0]["relationship"] == "market_leader"
    assert any(item["relationship"] == "client" for item in competitors)
    assert any(item["relationship"] == "watch" for item in competitors)


def test_ai_analysis_normalizes_when_present_and_missing():
    present = normalize_api_ai_analysis(_fixture("ai_analysis_response.json"))
    missing = normalize_api_ai_analysis({"success": True, "data": {}})

    assert present["available"] is True
    assert present["issues"] == ["East edge points are weak or missing."]
    assert present["recommendations"] == ["Refresh the tracked service page with clearer local relevance."]
    assert missing == {"available": False}


def test_combined_synthetic_response_normalizes_to_valid_summary():
    scan = normalize_api_report_to_keyword_scan(_fixture("combined_report_response.json"))
    payload = merge_api_scan_into_summary(profile="demo-profile", keyword_scan=scan)
    validation = validate_local_falcon_summary(payload)

    assert payload["schema_version"] == "local_falcon_summary.v2"
    assert payload["provider"] == "local_falcon"
    assert payload["source_type"] == "api_fixture"
    assert payload["real_data"] is False
    assert payload["summary"]["keyword_count"] == 1
    assert validation.keyword_scan_count == 1
    assert validation.warnings == []


def test_merge_api_scan_replaces_existing_keyword_scan():
    first = normalize_api_report_to_keyword_scan(_fixture("combined_report_response.json"))
    second = dict(first)
    second["data_points"] = dict(first["data_points"], top_3=1)

    payload = merge_api_scan_into_summary(profile="demo-profile", keyword_scan=first)
    payload = merge_api_scan_into_summary(profile="demo-profile", keyword_scan=second, existing_summary=payload)

    assert len(payload["keyword_scans"]) == 1
    assert payload["keyword_scans"][0]["data_points"]["top_3"] == 1


def test_malformed_required_report_fields_fail_clearly():
    payload = _fixture("report_summary_response.json")
    payload["data"]["report"].pop("keyword")

    with pytest.raises(LocalFalconApiResponseError, match="keyword"):
        normalize_api_report_to_keyword_scan(
            payload,
            grid_response=_fixture("report_grid_points_response.json"),
        )


def test_api_response_module_does_not_import_network_libraries():
    source = Path(__file__).resolve().parents[1] / "src" / "local_falcon_api_responses.py"
    text = source.read_text(encoding="utf-8")

    assert "import requests" not in text
    assert "import httpx" not in text
    assert "urllib.request" not in text
