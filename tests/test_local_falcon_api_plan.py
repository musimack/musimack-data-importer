import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.local_falcon_api_plan import (
    LocalFalconApiPlanError,
    build_direct_plan,
    build_manifest_plan,
    default_output_path,
    mask_report_id,
    redact_query_text,
    redacted_api_key,
    render_plan,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_local_falcon_api.py"


def test_direct_dry_run_plan_defaults_to_local_real_output():
    plan = build_direct_plan(
        profile="aluma-seo-geo",
        keyword="sculptra treatment",
        report_id="example-report-id",
        env={},
    )

    assert plan.output == Path("exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json")
    assert plan.reports[0].keyword == "sculptra treatment"
    assert plan.reports[0].report_id == "example-report-id"
    assert plan.merge_mode == "append/update keyword scans"
    assert plan.api_key_configured is False


def test_inn_direct_dry_run_plan_defaults_to_local_real_output():
    plan = build_direct_plan(
        profile="inn-at-spanish-head",
        keyword="lincoln city oceanfront hotel",
        report_id="example-report-id",
        env={},
    )

    assert plan.output == Path("exports/local-real/dashboard-lab/inn-at-spanish-head/local-falcon-summary.json")
    assert plan.reports[0].keyword == "lincoln city oceanfront hotel"
    assert plan.api_key_configured is False


def test_manifest_dry_run_plan_validates_shape(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "profile": "aluma-seo-geo",
                "featured_keyword_id": "sculptra-treatment",
                "reports": [
                    {
                        "keyword": "sculptra treatment",
                        "report_id": "example-report-id",
                        "relationship": "monthly-local-visibility",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = build_manifest_plan(manifest, append=True, env={"LOCAL_FALCON_API_KEY": "lf_live_123456"})

    assert plan.featured_keyword_id == "sculptra-treatment"
    assert plan.merge_mode == "append new keyword scans"
    assert plan.api_key_configured is True
    assert plan.api_key_redacted == "lf_****3456"
    assert plan.reports[0].relationship == "monthly-local-visibility"


def test_manifest_dry_run_rejects_missing_report_id(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"profile": "aluma-seo-geo", "reports": [{"keyword": "sculptra treatment"}]}),
        encoding="utf-8",
    )

    with pytest.raises(LocalFalconApiPlanError, match="report_id"):
        build_manifest_plan(manifest, env={})


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"profile": None, "keyword": "x", "report_id": "id"}, "--profile"),
        ({"profile": "aluma-seo-geo", "keyword": None, "report_id": "id"}, "--keyword"),
        ({"profile": "aluma-seo-geo", "keyword": "x", "report_id": None}, "--report-id"),
    ],
)
def test_direct_plan_rejects_missing_required_inputs(kwargs, message):
    with pytest.raises(LocalFalconApiPlanError, match=message):
        build_direct_plan(**kwargs, env={})


def test_redacted_api_key_does_not_leak_full_value():
    redacted = redacted_api_key("lf_live_supersecret1234")

    assert redacted == "lf_****1234"
    assert "supersecret" not in redacted


def test_report_id_and_query_helpers_do_not_leak_full_values():
    assert mask_report_id("example-report-id") == "****t-id"
    assert "example-report-id" not in mask_report_id("example-report-id")

    redacted_query = redact_query_text("lincoln city oceanfront hotel near the beach")
    assert "lincoln city oceanfront hotel near the beach" not in redacted_query
    assert redacted_query.endswith("[redacted]")


def test_render_plan_redacts_report_ids_and_queries_by_default():
    plan = build_direct_plan(
        profile="inn-at-spanish-head",
        keyword="lincoln city oceanfront hotel near the beach",
        report_id="example-report-id",
        env={"LOCAL_FALCON_API_KEY": "lf_live_supersecret1234"},
    )

    rendered = render_plan(plan)

    assert "Reports planned: 1" in rendered
    assert "- Local Falcon: 1" in rendered
    assert "- map_keyword: 1" in rendered
    assert "API key configured: yes" in rendered
    assert "example-report-id" not in rendered
    assert "lincoln city oceanfront hotel near the beach" not in rendered
    assert "lf_live_supersecret1234" not in rendered
    assert "lf_****1234" not in rendered


def test_render_plan_verbose_still_redacts_report_ids_and_queries():
    plan = build_direct_plan(
        profile="inn-at-spanish-head",
        keyword="lincoln city oceanfront hotel near the beach",
        report_id="example-report-id",
        env={},
    )

    rendered = render_plan(plan, verbose=True)

    assert "Verbose report plan:" in rendered
    assert "Report ID: ****t-id" in rendered
    assert "Query: lincoln city ocean... [redacted]" in rendered
    assert "example-report-id" not in rendered
    assert "lincoln city oceanfront hotel near the beach" not in rendered


def test_cli_direct_dry_run_succeeds_without_network_or_writes(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--report-id",
            "example-report-id",
            "--dry-run",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "No network requests will be made" in completed.stdout
    assert "Live API fetching is not implemented" in completed.stdout
    assert "sculptra treatment" not in completed.stdout
    assert "example-report-id" not in completed.stdout
    assert not (tmp_path / "exports").exists()


def test_cli_manifest_dry_run_succeeds(tmp_path):
    manifest = tmp_path / "local-falcon-manifests" / "demo.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "profile": "aluma-seo-geo",
                "output": "exports/local-real/dashboard-lab/aluma-seo-geo/local-falcon-summary.json",
                "reports": [{"keyword": "sculptra treatment", "report_id": "example-report-id"}],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Reports planned: 1" in completed.stdout
    assert "- Local Falcon: 1" in completed.stdout
    assert "sculptra treatment" not in completed.stdout
    assert "example-report-id" not in completed.stdout


def test_cli_refuses_execute(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--keyword",
            "sculptra treatment",
            "--report-id",
            "example-report-id",
            "--execute",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "Live Local Falcon API execution requires --transport live" in completed.stderr


def test_cli_validate_only_missing_output_fails_safely(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "aluma-seo-geo",
            "--validate-only",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "validation cannot run" in completed.stderr


def test_default_output_path_requires_known_profile():
    with pytest.raises(LocalFalconApiPlanError, match="unknown profile"):
        default_output_path("missing-profile")
