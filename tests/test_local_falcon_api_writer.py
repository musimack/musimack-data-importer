import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.local_falcon_api_fetcher import LocalFalconApiFetcherError, LocalFalconApiFetchRequest
from src.local_falcon_api_plan import LocalFalconApiReportPlan
from src.local_falcon_api_writer import (
    DisabledLiveLocalFalconTransport,
    SyntheticFixtureLocalFalconTransport,
    fetch_validate_and_write_summary,
    is_safe_local_falcon_api_write_path,
)
from src.local_falcon_importer import validate_local_falcon_summary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_local_falcon_api.py"
MANIFEST = ROOT / "tests" / "fixtures" / "local_falcon_api" / "demo_manifest.json"


def _request(output, reports=None, featured_keyword_id=None):
    return LocalFalconApiFetchRequest(
        profile="all-services-client",
        output=Path(output),
        featured_keyword_id=featured_keyword_id,
        reports=reports
        or [
            LocalFalconApiReportPlan(
                keyword="demo cosmetic service",
                report_id="demo-report-a",
            )
        ],
    )


def test_fake_transport_writes_valid_summary_to_tmp_path(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    result = fetch_validate_and_write_summary(_request(output), SyntheticFixtureLocalFalconTransport())
    payload = json.loads(output.read_text(encoding="utf-8"))
    validation = validate_local_falcon_summary(payload, output)

    assert result.created is True
    assert result.updated is False
    assert result.keyword_count == 1
    assert result.source_type == "api_fixture"
    assert result.no_network is True
    assert validation.warnings == []
    assert payload["real_data"] is False
    serialized = json.dumps(payload).lower()
    for forbidden in ("credential", "token", "authorization", "client_secret", "report_summary_response.json"):
        assert forbidden not in serialized


def test_fake_transport_writes_two_reports_into_one_summary(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    result = fetch_validate_and_write_summary(
        _request(
            output,
            featured_keyword_id="demo-weak-service",
            reports=[
                LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
                LocalFalconApiReportPlan(keyword="demo weak service", report_id="demo-report-b"),
            ],
        ),
        SyntheticFixtureLocalFalconTransport(),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.keyword_count == 2
    assert payload["summary"]["featured_keyword_id"] == "demo-weak-service"
    assert payload["summary"]["strongest_keyword_id"] == "demo-cosmetic-service"
    assert payload["summary"]["weakest_keyword_id"] == "demo-weak-service"


def test_existing_summary_appends_and_updates_without_losing_other_scans(tmp_path):
    output = tmp_path / "local-falcon-summary.json"
    transport = SyntheticFixtureLocalFalconTransport()
    fetch_validate_and_write_summary(
        _request(
            output,
            featured_keyword_id="demo-weak-service",
            reports=[
                LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
                LocalFalconApiReportPlan(keyword="demo weak service", report_id="demo-report-b"),
            ],
        ),
        transport,
    )

    result = fetch_validate_and_write_summary(
        _request(
            output,
            reports=[
                LocalFalconApiReportPlan(keyword="demo cosmetic service", report_id="demo-report-a"),
            ],
        ),
        transport,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.created is False
    assert result.updated is True
    assert [scan["id"] for scan in payload["keyword_scans"]] == [
        "demo-weak-service",
        "demo-cosmetic-service",
    ]
    assert payload["summary"]["featured_keyword_id"] == "demo-weak-service"


def test_fetch_failure_prevents_overwrite(tmp_path):
    class BadGridTransport(SyntheticFixtureLocalFalconTransport):
        def get_grid_points(self, report_id):
            return {"success": True, "data": {}}

    output = tmp_path / "local-falcon-summary.json"
    output.write_text('{"kept": true}\n', encoding="utf-8")

    with pytest.raises(LocalFalconApiFetcherError, match="grid points"):
        fetch_validate_and_write_summary(_request(output), BadGridTransport())

    assert output.read_text(encoding="utf-8") == '{"kept": true}\n'


def test_disabled_live_transport_refuses():
    with pytest.raises(LocalFalconApiFetcherError, match="fake transport failed"):
        fetch_validate_and_write_summary(
            _request(Path(".test-tmp-local-falcon-api") / "never-written.json"),
            DisabledLiveLocalFalconTransport(),
        )


def test_safe_write_path_guard():
    assert is_safe_local_falcon_api_write_path("exports/local-real/dashboard-lab/demo/local-falcon-summary.json", cwd=ROOT)
    assert is_safe_local_falcon_api_write_path(".test-tmp-local-falcon-api/local-falcon-summary.json", cwd=ROOT)
    assert not is_safe_local_falcon_api_write_path("exports/dashboard-lab/demo/local-falcon-summary.json", cwd=ROOT)
    assert not is_safe_local_falcon_api_write_path("public/fixtures/local-falcon-summary.json", cwd=ROOT)


def test_cli_fake_write_works_only_with_safe_output_path():
    safe_output = ROOT / ".test-tmp-local-falcon-api" / "writer-cli-summary.json"
    if safe_output.exists():
        safe_output.unlink()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "all-services-client",
            "--keyword",
            "demo cosmetic service",
            "--report-id",
            "demo-report-a",
            "--transport",
            "fake",
            "--write",
            "--output",
            str(safe_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Wrote synthetic Local Falcon API summary" in completed.stdout
    assert "No network requests were made" in completed.stdout
    assert json.loads(safe_output.read_text(encoding="utf-8"))["summary"]["keyword_count"] == 1

    unsafe = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "all-services-client",
            "--keyword",
            "demo cosmetic service",
            "--report-id",
            "demo-report-a",
            "--transport",
            "fake",
            "--write",
            "--output",
            "exports/dashboard-lab/all-services-client/local-falcon-summary.json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert unsafe.returncode == 1
    assert "ignored exports/local-real" in unsafe.stderr


def test_cli_requires_fake_transport_for_write():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "all-services-client",
            "--keyword",
            "demo cosmetic service",
            "--report-id",
            "demo-report-a",
            "--write",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "--write is only available with --transport fake" in completed.stderr


def test_cli_manifest_fake_write_uses_demo_manifest_output():
    output = ROOT / ".test-tmp-local-falcon-api" / "local-falcon-summary.json"
    if output.exists():
        output.unlink()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "fake",
            "--write",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["keyword_count"] == 2
    assert payload["summary"]["featured_keyword_id"] == "demo-weak-service"

    validate_only = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "all-services-client",
            "--validate-only",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert validate_only.returncode == 0
    assert "Validated existing Local Falcon summary output" in validate_only.stdout
    assert "No network requests were made" in validate_only.stdout


def test_cli_dry_run_and_execute_boundaries_still_hold():
    dry_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "fake",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert dry_run.returncode == 0
    assert "dry run only" in dry_run.stdout
    assert "No output was written" in dry_run.stdout

    execute = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "fake",
            "--write",
            "--execute",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert execute.returncode == 1
    assert "Live Local Falcon API execution requires --transport live" in execute.stderr


def test_writer_module_does_not_import_network_libraries():
    text = (ROOT / "src" / "local_falcon_api_writer.py").read_text(encoding="utf-8")

    assert "import requests" not in text
    assert "import httpx" not in text
    assert "urllib.request" not in text
