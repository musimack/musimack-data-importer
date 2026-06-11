import copy
import subprocess
import sys
from pathlib import Path

import pytest

from src.local_falcon_api_fetcher import (
    LocalFalconApiFetcher,
    LocalFalconApiFetcherError,
    LocalFalconApiFetchRequest,
    fetch_report_bundle,
    normalize_report_bundle_to_summary,
)
from src.local_falcon_api_plan import LocalFalconApiReportPlan
from src.local_falcon_api_responses import load_synthetic_api_fixture


FIXTURES = Path(__file__).parent / "fixtures" / "local_falcon_api"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_local_falcon_api.py"


class FakeLocalFalconTransport:
    def __init__(self):
        self.calls = []
        self._base_summary = _fixture("report_summary_response.json")
        self._base_grid = _fixture("report_grid_points_response.json")
        self._base_competitors = _fixture("competitor_report_response.json")
        self._base_ai = _fixture("ai_analysis_response.json")

    def get_report_summary(self, report_id):
        self.calls.append(("summary", report_id))
        payload = copy.deepcopy(self._base_summary)
        payload["data"]["report"]["report_key"] = report_id
        if report_id == "demo-report-b":
            payload["data"]["report"]["keyword"] = "demo weak service"
            payload["data"]["report"]["arp"] = 18.4
            payload["data"]["report"]["atrp"] = 21.9
            payload["data"]["report"]["solv"] = 3.2
        return payload

    def get_grid_points(self, report_id):
        self.calls.append(("grid", report_id))
        payload = copy.deepcopy(self._base_grid)
        if report_id == "demo-report-b":
            for point in payload["data"]["grid_points"]:
                point["rank"] = None
        return payload

    def get_competitors(self, report_id):
        self.calls.append(("competitors", report_id))
        return copy.deepcopy(self._base_competitors)

    def get_ai_analysis(self, report_id):
        self.calls.append(("ai", report_id))
        return copy.deepcopy(self._base_ai)


class MissingAiTransport(FakeLocalFalconTransport):
    def get_ai_analysis(self, report_id):
        self.calls.append(("ai", report_id))
        return None


class MissingGridTransport(FakeLocalFalconTransport):
    def get_grid_points(self, report_id):
        self.calls.append(("grid", report_id))
        return {"success": True, "data": {}}


def _fixture(name):
    return load_synthetic_api_fixture(FIXTURES / name)


def test_fetcher_without_transport_refuses_live_execution():
    fetcher = LocalFalconApiFetcher()

    with pytest.raises(LocalFalconApiFetcherError, match="Live Local Falcon API transport is not implemented"):
        fetcher.fetch_report_bundle(LocalFalconApiReportPlan(keyword="demo", report_id="demo-report-a"))


def test_fetch_report_bundle_uses_injected_fake_transport():
    transport = FakeLocalFalconTransport()
    bundle = fetch_report_bundle(
        LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
        transport,
    )

    assert bundle.report_summary["data"]["report"]["report_key"] == "demo-report-a"
    assert transport.calls == [
        ("summary", "demo-report-a"),
        ("grid", "demo-report-a"),
        ("competitors", "demo-report-a"),
        ("ai", "demo-report-a"),
    ]


def test_fetcher_normalizes_one_report_into_valid_summary(tmp_path):
    fetcher = LocalFalconApiFetcher(FakeLocalFalconTransport())
    result = fetcher.fetch(
        LocalFalconApiFetchRequest(
            profile="demo-profile",
            output=tmp_path / "local-falcon-summary.json",
            reports=[
                LocalFalconApiReportPlan(
                    keyword="demo cosmetic service",
                    report_id="demo-report-a",
                )
            ],
        )
    )

    assert result.report_count == 1
    assert result.summary["schema_version"] == "local_falcon_summary.v2"
    assert result.summary["source_type"] == "api_fixture"
    assert result.summary["real_data"] is False
    assert result.validation.warnings == []
    assert result.keyword_scans[0]["keyword"] == "demo cosmetic service"
    assert result.keyword_scans[0]["data_points"]["total"] == 9
    assert not (tmp_path / "local-falcon-summary.json").exists()


def test_fetcher_normalizes_two_reports_and_preserves_featured_keyword(tmp_path):
    fetcher = LocalFalconApiFetcher(FakeLocalFalconTransport())
    result = fetcher.fetch(
        LocalFalconApiFetchRequest(
            profile="demo-profile",
            output=tmp_path / "local-falcon-summary.json",
            featured_keyword_id="demo-weak-service",
            reports=[
                LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
                LocalFalconApiReportPlan(keyword="demo weak service", report_id="demo-report-b"),
            ],
        )
    )

    assert result.report_count == 2
    assert result.summary["summary"]["keyword_count"] == 2
    assert result.summary["summary"]["featured_keyword_id"] == "demo-weak-service"
    assert result.summary["summary"]["strongest_keyword_id"] == "demo-cosmetic-service"
    assert result.summary["summary"]["weakest_keyword_id"] == "demo-weak-service"
    assert result.validation.keyword_scan_count == 2


def test_missing_optional_ai_analysis_is_allowed_with_warning(tmp_path):
    fetcher = LocalFalconApiFetcher(MissingAiTransport())
    result = fetcher.fetch(
        LocalFalconApiFetchRequest(
            profile="demo-profile",
            output=tmp_path / "local-falcon-summary.json",
            reports=[LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a")],
        )
    )

    assert result.keyword_scans[0]["ai_analysis"] == {"available": False}
    assert any("AI analysis" in warning for warning in result.warnings)
    assert not (tmp_path / "local-falcon-summary.json").exists()


def test_missing_required_grid_points_fails_clearly():
    fetcher = LocalFalconApiFetcher(MissingGridTransport())

    with pytest.raises(LocalFalconApiFetcherError, match="grid points"):
        fetcher.fetch(
            LocalFalconApiFetchRequest(
                profile="demo-profile",
                reports=[LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a")],
            )
        )


def test_malformed_report_summary_fails_clearly():
    class MalformedSummaryTransport(FakeLocalFalconTransport):
        def get_report_summary(self, report_id):
            self.calls.append(("summary", report_id))
            payload = super().get_report_summary(report_id)
            payload["data"]["report"].pop("keyword")
            return payload

    fetcher = LocalFalconApiFetcher(MalformedSummaryTransport())

    with pytest.raises(LocalFalconApiFetcherError, match="keyword"):
        fetcher.fetch(
            LocalFalconApiFetchRequest(
                profile="demo-profile",
                reports=[LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a")],
            )
        )


def test_normalize_report_bundle_to_summary_returns_validator_compatible_payload():
    bundle = fetch_report_bundle(
        LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
        FakeLocalFalconTransport(),
    )
    payload = normalize_report_bundle_to_summary(profile="demo-profile", bundle=bundle)

    assert payload["summary"]["keyword_count"] == 1
    assert payload["keyword_scans"][0]["id"] == "demo-cosmetic-service"


def test_fetcher_module_does_not_import_network_libraries():
    source = Path(__file__).resolve().parents[1] / "src" / "local_falcon_api_fetcher.py"
    text = source.read_text(encoding="utf-8")

    assert "import requests" not in text
    assert "import httpx" not in text
    assert "urllib.request" not in text


def test_dry_run_cli_still_refuses_execute(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "demo cosmetic service",
            "--report-id",
            "demo-report-a",
            "--execute",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "Live Local Falcon API execution requires --transport live" in completed.stderr
