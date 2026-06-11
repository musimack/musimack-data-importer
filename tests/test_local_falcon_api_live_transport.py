import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.local_falcon_api_live_transport import (
    COMPETITOR_REPORT_ENDPOINT,
    SCAN_REPORT_ENDPOINT,
    LocalFalconLiveConfig,
    LocalFalconLiveTransportError,
    LocalFalconReadOnlyLiveTransport,
)
from src.local_falcon_api_responses import merge_api_scan_into_summary, normalize_api_competitors
from src.local_falcon_importer import validate_local_falcon_summary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_local_falcon_api.py"


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"success": True, "data": {}}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, data, timeout, headers):
        self.calls.append({"url": url, "data": data, "timeout": timeout, "headers": headers})
        if "/v1/competitor-reports/" in url:
            return FakeResponse(payload={"success": True, "data": {"businesses": []}})
        return FakeResponse(payload={"success": True, "data": {"keyword": "demo", "data_points": []}})


def test_live_transport_requires_api_key_before_network():
    session = FakeSession()

    with pytest.raises(LocalFalconLiveTransportError, match="LOCAL_FALCON_API_KEY is missing"):
        LocalFalconReadOnlyLiveTransport.from_env(session=session, env={})

    assert session.calls == []


def test_live_transport_uses_read_only_report_endpoints_and_settings():
    session = FakeSession()
    transport = LocalFalconReadOnlyLiveTransport(
        LocalFalconLiveConfig(
            api_key="lf_live_secret_123456",
            base_url="https://api.localfalcon.test",
            timeout_seconds=7,
            max_retries=0,
        ),
        session=session,
    )

    transport.get_report_summary("report-abc")
    transport.get_grid_points("report-abc")
    transport.get_competitors("report-abc")

    assert len(session.calls) == 2
    assert session.calls[0]["url"].endswith(SCAN_REPORT_ENDPOINT.format(report_key="report-abc"))
    assert session.calls[1]["url"].endswith(COMPETITOR_REPORT_ENDPOINT.format(report_key="report-abc"))
    assert all(call["data"] == {"api_key": "lf_live_secret_123456"} for call in session.calls)
    assert all(call["timeout"] == 7 for call in session.calls)
    assert transport.config.api_key_redacted == "lf_****3456"


def test_live_transport_source_does_not_reference_on_demand_or_mutation_endpoints():
    text = (ROOT / "src" / "local_falcon_api_live_transport.py").read_text(encoding="utf-8")

    for forbidden in (
        "/v2/run-scan",
        "/v1/scan",
        "/v1/search",
        "/v1/result",
        "/v1/grid",
        "/v2/campaigns/create",
        "/v2/campaigns/run",
        "/v2/locations/add",
    ):
        assert forbidden not in text


def test_api_local_real_source_type_validates():
    payload = merge_api_scan_into_summary(
        profile="all-services-client",
        source_type="api_local_real",
        real_data=True,
        keyword_scan={
            "id": "demo",
            "keyword": "demo",
            "rendered_grid": {"rows": 1, "columns": 1},
            "data_points": {"total": 1, "found": 1, "top_3": 1, "top_10": 1, "top_20": 1, "not_found_or_20_plus": 0},
            "grid_points": [{"row": 0, "col": 0, "rank": 1, "status": "top_3"}],
            "competitors": [{"name": "Demo", "relationship": "client"}],
            "ai_analysis": {"available": True},
        },
    )
    validation = validate_local_falcon_summary(payload)

    assert payload["source_type"] == "api_local_real"
    assert payload["real_data"] is True
    assert validation.warnings == []


def test_live_competitor_normalizer_derives_counts_from_business_points():
    competitors = normalize_api_competitors(
        {
            "success": True,
            "data": {
                "businesses": [
                    {
                        "name": "Demo Clinic",
                        "solv": 12.5,
                        "data_points": [{"rank": 1}, {"rank": 8}, {"rank": "20+"}, {"rank": None}],
                    }
                ]
            },
        },
        "Demo Clinic",
    )

    assert competitors[0]["found_points"] == 2
    assert competitors[0]["top_3_points"] == 1
    assert competitors[0]["top_10_points"] == 2
    assert competitors[0]["relationship"] == "client"


def test_cli_live_without_execute_is_dry_run_without_api_key(monkeypatch):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--report-id",
            "real-report-id",
            "--transport",
            "live",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Local Falcon live read-only preflight" in completed.stdout
    assert "API key configured: no" in completed.stdout
    assert "No Local Falcon network request was made" in completed.stdout


def test_cli_live_execute_without_api_key_fails_before_network(monkeypatch):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--report-id",
            "real-report-id",
            "--transport",
            "live",
            "--execute",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "LOCAL_FALCON_API_KEY_ALUMA_SEO_GEO is missing" in completed.stderr
    assert "real-report-id" not in completed.stderr


def test_cli_live_missing_report_id_fails_before_network(monkeypatch):
    monkeypatch.setenv("LOCAL_FALCON_API_KEY", "lf_live_secret_123456")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--transport",
            "live",
            "--execute",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "--report-id is required" in completed.stderr
    assert "lf_live_secret" not in completed.stderr


def test_cli_live_unsafe_write_path_is_refused_before_network(monkeypatch):
    monkeypatch.setenv("LOCAL_FALCON_API_KEY", "lf_live_secret_123456")
    output = ROOT / "exports" / "dashboard-lab" / "aluma-seo-geo" / "local-falcon-summary.json"
    before = output.read_text(encoding="utf-8") if output.exists() else None
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--report-id",
            "real-report-id",
            "--transport",
            "live",
            "--execute",
            "--write",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "live writes only allow ignored exports/local-real" in completed.stderr
    if before is not None:
        assert output.read_text(encoding="utf-8") == before
    assert "lf_live_secret" not in completed.stderr
