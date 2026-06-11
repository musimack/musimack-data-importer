import json
import subprocess
import sys
from pathlib import Path

from src.local_falcon_api_fetcher import LocalFalconApiFetcher, LocalFalconApiFetchRequest
from src.local_falcon_api_plan import build_manifest_plan
from src.local_falcon_api_writer import SyntheticFixtureLocalFalconTransport
from src.local_falcon_importer import validate_local_falcon_summary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_local_falcon_api.py"
MANIFEST = ROOT / "tests" / "fixtures" / "local_falcon_api" / "source_manifest.json"


def _write_manifest(path: Path, *, report_count: int = 17) -> None:
    reports = []
    for index in range(report_count):
        source = "Google Maps" if index < 7 else "ChatGPT"
        reports.append(
            {
                "source": source,
                "keyword": f"private prompt {index}",
                "report_id": f"private-report-id-{index:02d}",
            }
        )
    path.write_text(
        json.dumps(
            {
                "profile": "all-services-client",
                "reports": reports,
            }
        ),
        encoding="utf-8",
    )


def test_source_aware_manifest_parses_multiple_reports():
    plan = build_manifest_plan(MANIFEST, env={})

    assert plan.profile == "all-services-client"
    assert len(plan.reports) == 2
    assert plan.featured_keyword_id == "google-maps-demo-cosmetic-service"
    assert plan.reports[0].source_id == "google_maps"
    assert plan.reports[0].query_type == "map_keyword"
    assert plan.reports[1].source_id == "chatgpt"
    assert plan.reports[1].query_type == "ai_visibility_prompt"


def test_source_metadata_is_attached_to_keyword_scans(tmp_path):
    plan = build_manifest_plan(MANIFEST, output_override=str(tmp_path / "local-falcon-summary.json"), env={})
    result = LocalFalconApiFetcher(SyntheticFixtureLocalFalconTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile=plan.profile,
            reports=plan.reports,
            output=plan.output,
            featured_keyword_id=plan.featured_keyword_id,
        )
    )
    payload = result.summary
    scans = payload["keyword_scans"]

    assert [scan["source_id"] for scan in scans] == ["google_maps", "chatgpt"]
    assert scans[0]["id"] == "google-maps-demo-cosmetic-service"
    assert scans[0]["query_type"] == "map_keyword"
    assert scans[0]["scan_kind"] == "map_visibility"
    assert scans[0]["keyword"] == "demo cosmetic service"
    assert scans[1]["id"] == "chatgpt-can-you-recommend-a-good-demo-provider"
    assert scans[1]["query_type"] == "ai_visibility_prompt"
    assert scans[1]["scan_kind"] == "ai_visibility_map"
    assert scans[1]["prompt"] == "can you recommend a good demo provider?"
    assert "report_id" not in scans[0]
    assert scans[0]["report_id_redacted"] == "fake****rt-a"


def test_source_aware_summary_preserves_legacy_and_source_fields(tmp_path):
    plan = build_manifest_plan(MANIFEST, output_override=str(tmp_path / "local-falcon-summary.json"), env={})
    result = LocalFalconApiFetcher(SyntheticFixtureLocalFalconTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile=plan.profile,
            reports=plan.reports,
            output=plan.output,
            featured_keyword_id=plan.featured_keyword_id,
        )
    )
    summary = result.summary["summary"]

    assert summary["keyword_count"] == 2
    assert summary["scan_count"] == 2
    assert summary["featured_keyword_id"] == "google-maps-demo-cosmetic-service"
    assert summary["featured_scan_id"] == "google-maps-demo-cosmetic-service"
    assert summary["strongest_keyword_id"] == summary["strongest_scan_id"]
    assert summary["weakest_keyword_id"] == summary["weakest_scan_id"]
    assert summary["default_source_id"] == "google_maps"
    assert [source["source_id"] for source in summary["available_sources"]] == ["google_maps", "chatgpt"]


def test_validator_accepts_source_aware_scans(tmp_path):
    plan = build_manifest_plan(MANIFEST, output_override=str(tmp_path / "local-falcon-summary.json"), env={})
    result = LocalFalconApiFetcher(SyntheticFixtureLocalFalconTransport()).fetch(
        LocalFalconApiFetchRequest(
            profile=plan.profile,
            reports=plan.reports,
            output=plan.output,
            featured_keyword_id=plan.featured_keyword_id,
        )
    )

    validation = validate_local_falcon_summary(result.summary, plan.output)

    assert "can you recommend ... [redacted AI prompt]: AI visibility brand observations are missing." in validation.warnings
    assert "can you recommend ... [redacted AI prompt]: AI visibility brand phrases are missing." in validation.warnings
    assert not any("data point counts" in warning for warning in validation.warnings)
    assert validation.keyword_summaries[0]["source_id"] == "google_maps"
    assert validation.keyword_summaries[1]["query_type"] == "ai_visibility_prompt"


def test_cli_live_manifest_dry_run_lists_sources_without_network(monkeypatch):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "live",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Reports planned: 2" in completed.stdout
    assert "- Google Maps: 1" in completed.stdout
    assert "- ChatGPT: 1" in completed.stdout
    assert "No Local Falcon network request was made" in completed.stdout
    assert "Report ID:" not in completed.stdout
    assert "fake-report-a" not in completed.stdout
    assert "demo cosmetic service" not in completed.stdout
    assert "API key:" not in completed.stdout


def test_cli_live_manifest_allows_seventeen_reports_with_explicit_max(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=17)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--max-reports",
            "17",
            "--out",
            ".test-tmp-local-falcon-api/raw",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Reports planned: 17" in completed.stdout
    assert "- Google Maps: 7" in completed.stdout
    assert "- ChatGPT: 10" in completed.stdout
    assert "Dry run only. No Local Falcon network request was made." in completed.stdout
    assert "private-report-id-00" not in completed.stdout
    assert "private prompt 0" not in completed.stdout
    assert "Report ID:" not in completed.stdout
    assert "API key:" not in completed.stdout


def test_cli_live_manifest_verbose_plan_redacts_sensitive_values(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=17)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--max-reports",
            "17",
            "--out",
            ".test-tmp-local-falcon-api/raw",
            "--verbose-plan",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Verbose report plan:" in completed.stdout
    assert "Report ID: ****d-00" in completed.stdout
    assert "Query: private p... [redacted]" in completed.stdout
    assert "private-report-id-00" not in completed.stdout
    assert "private prompt 0" not in completed.stdout
    assert "API key:" not in completed.stdout


def test_cli_live_manifest_over_explicit_cap_fails_safely(tmp_path):
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=18)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--max-reports",
            "17",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "selected 18 reports" in completed.stderr
    assert "private-report-id-00" not in completed.stderr
    assert "private prompt 0" not in completed.stderr


def test_cli_live_manifest_execute_with_raw_output_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT", raising=False)
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=17)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--execute",
            "--max-reports",
            "17",
            "--out",
            ".test-tmp-local-falcon-api/raw",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT is missing" in completed.stderr
    assert "private-report-id-00" not in completed.stderr
    assert "private prompt 0" not in completed.stderr


def test_cli_live_manifest_does_not_silently_use_global_api_key_for_execute(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_FALCON_API_KEY", "global-secret")
    monkeypatch.delenv("LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT", raising=False)
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=17)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--execute",
            "--max-reports",
            "17",
            "--out",
            ".test-tmp-local-falcon-api/raw",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT is missing" in completed.stderr
    assert "global-secret" not in completed.stderr


def test_cli_live_manifest_explicit_api_key_env_is_used_for_preflight(monkeypatch, tmp_path):
    monkeypatch.setenv("CUSTOM_LOCAL_FALCON_KEY", "custom-secret")
    manifest = tmp_path / "large-manifest.json"
    _write_manifest(manifest, report_count=17)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--transport",
            "live",
            "--max-reports",
            "17",
            "--out",
            ".test-tmp-local-falcon-api/raw",
            "--api-key-env",
            "CUSTOM_LOCAL_FALCON_KEY",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "API key env: CUSTOM_LOCAL_FALCON_KEY" in completed.stdout
    assert "API key configured: yes" in completed.stdout
    assert "custom-secret" not in completed.stdout


def test_cli_live_manifest_execute_requires_write(monkeypatch):
    monkeypatch.setenv("LOCAL_FALCON_API_KEY", "lf_live_secret_123456")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
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
    assert "live manifest execution requires --write or --out" in completed.stderr
    assert "lf_live_secret" not in completed.stderr


def test_cli_live_manifest_missing_api_key_fails_before_network(monkeypatch):
    monkeypatch.delenv("LOCAL_FALCON_API_KEY", raising=False)
    monkeypatch.delenv("LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT", raising=False)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "live",
            "--execute",
            "--write",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "LOCAL_FALCON_API_KEY_ALL_SERVICES_CLIENT is missing" in completed.stderr


def test_cli_live_manifest_unsafe_output_is_refused_before_network(monkeypatch):
    monkeypatch.setenv("LOCAL_FALCON_API_KEY", "lf_live_secret_123456")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(MANIFEST),
            "--transport",
            "live",
            "--execute",
            "--write",
            "--allow-global-api-key",
            "--output",
            "exports/dashboard-lab/all-services-client/local-falcon-summary.json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "live writes only allow ignored exports/local-real" in completed.stderr
    assert "lf_live_secret" not in completed.stderr


def test_source_manifest_contains_only_synthetic_report_ids():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report_ids = [report["report_id"] for report in payload["reports"]]

    assert report_ids == ["fake-report-a", "fake-report-b"]
