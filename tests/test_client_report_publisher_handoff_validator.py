import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from src.client_report_publisher_handoff_validator import validate_handoff_directory


FIXTURE_DIR = Path("dev/fixtures/client_report_publisher_handoff")


def test_fake_fixture_directory_validates_successfully():
    result = validate_handoff_directory(FIXTURE_DIR)

    assert result.valid is True
    assert result.errors == []
    assert "manifest.json" in result.files_checked
    assert "ga4_metric_display.v1" in result.contracts_seen
    assert "local_falcon_display.v1" in result.contracts_seen


def test_manifest_missing_required_field_fails_safely(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    del manifest["client_slug"]
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.client_slug is required" in result.errors
    assert _safe_error_text(result.errors)


def test_manifest_path_traversal_is_rejected(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["files"][0]["path"] = "../outside.json"
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("must stay inside" in error for error in result.errors)


def test_missing_referenced_file_fails_safely(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    (handoff_dir / "ga4_metric_display.v1.json").unlink()

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "referenced file is missing: ga4_metric_display.v1.json" in result.errors


def test_forbidden_keys_are_rejected_deeply(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "gsc_summary_display.v1.json"
    payload = _load_json(payload_path)
    payload["nested"] = {"safe": [{"api_token_label": "redacted-in-test"}]}
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("forbidden key" in error and "api_token_label" in error for error in result.errors)
    assert _safe_error_text(result.errors)


def test_secret_like_values_are_rejected_without_echoing_value(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    payload["notes"] = ["Bearer abcdefghijklmnopqrstuvwxyz123456"]
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("secret-like value" in error for error in result.errors)
    assert all("abcdefghijklmnopqrstuvwxyz" not in error for error in result.errors)


def test_invalid_date_range_fails(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["period_start"] = "2026-05-01"
    manifest["period_end"] = "2026-04-01"
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.period_start must be on or before period_end" in result.errors


def test_invalid_json_fails_safely_without_dumping_content(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "local_falcon_display.v1.json"
    payload_path.write_text('{"schema_version": "local_falcon_display.v1", bad', encoding="utf-8")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "local_falcon_display.v1.json is not valid JSON" in result.errors
    assert all("schema_version" not in error for error in result.errors)


def test_auto_publish_is_rejected(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_top_sources_display.v1.json"
    payload = _load_json(payload_path)
    payload["auto_publish"] = False
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("auto_publish" in error for error in result.errors)


def test_unrecognized_contract_fails(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    payload["schema_version"] = "ga4_raw_payload.v1"
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("schema_version is not recognized" in error for error in result.errors)


def test_manifest_contracts_must_match_referenced_files(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["display_contract_versions"].remove("gsc_summary_display.v1")
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.display_contract_versions is missing referenced contract gsc_summary_display.v1" in result.errors


def test_list_count_limit_is_enforced(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_top_sources_display.v1.json"
    payload = _load_json(payload_path)
    payload["rows"] = [{"rank": index + 1, "label": f"Sample Source {index}"} for index in range(101)]
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir, max_list_items=100)

    assert result.valid is False
    assert any("list exceeds maximum item count" in error for error in result.errors)


def test_valid_189_day_daily_series_passes_contract_specific_limit(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-07-08")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 189, state="complete")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is True
    assert not any("maximum item count" in error for error in result.errors)


def test_valid_leap_year_daily_series_passes(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2024-01-01", "2024-12-31")
    _set_ga4_daily_series(handoff_dir, "2024-01-01", 366, state="complete")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is True


def test_truncated_series_cannot_claim_complete_coverage(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-07-08")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 100, state="complete")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("claims complete daily coverage" in error for error in result.errors)


def test_explicit_partial_100_point_series_is_valid(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-07-08")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 100, state="partial")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is True


def test_known_truncated_legacy_series_fails_safely(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-07-08")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 100, state="partial")
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    del payload["daily_series_coverage"]
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("possible silent truncation" in error for error in result.errors)


def test_daily_series_duplicate_unordered_and_out_of_period_dates_fail(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-01-07")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 3, state="partial")
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    points = payload["trend_charts"][0]["series"][0]["points"]
    points[1]["date"] = points[0]["date"]
    points[2]["date"] = "2025-12-31"
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("unique" in error for error in result.errors)
    assert any("ascending" in error for error in result.errors)
    assert any("inside the requested period" in error for error in result.errors)


def test_daily_coverage_count_and_timezone_contradictions_fail(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    _set_manifest_period(handoff_dir, "2026-01-01", "2026-01-07")
    _set_ga4_daily_series(handoff_dir, "2026-01-01", 7, state="complete")
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    payload["daily_series_coverage"]["actual_observation_count"] = 6
    payload["daily_series_coverage"]["timezone"] = "not a timezone"
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("actual_observation_count is inconsistent" in error for error in result.errors)
    assert any("timezone is invalid" in error for error in result.errors)


def test_legacy_dataset_without_scope_or_state_remains_explicitly_compatible(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_top_sources_display.v1.json"
    payload = _load_json(payload_path)
    payload.pop("data_scope")
    payload.pop("data_state")
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is True
    assert any("without explicit data_scope" in warning for warning in result.warnings)
    assert any("without explicit data_state" in warning for warning in result.warnings)


def test_semantic_substitution_between_ga4_contracts_fails(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    sources_path = handoff_dir / "ga4_top_sources_display.v1.json"
    sources = _load_json(sources_path)
    sources["rows"][0]["path"] = "/not-a-source/"
    _write_json(sources_path, sources)
    landing_path = handoff_dir / "ga4_top_landing_pages_display.v1.json"
    landing = _load_json(landing_path)
    landing["rows"][0]["views"] = 100
    _write_json(landing_path, landing)
    popularity_path = handoff_dir / "ga4_most_viewed_pages_display.v1.json"
    popularity = _load_json(popularity_path)
    popularity["rows"][0].pop("views")
    popularity["rows"][0]["sessions"] = 100
    _write_json(popularity_path, popularity)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("non-source scoped fields" in error for error in result.errors)
    assert any("non-landing-page scoped fields" in error for error in result.errors)
    assert any("page-popularity path and views" in error for error in result.errors)


def test_gsc_query_and_page_scopes_cannot_substitute_for_each_other(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "gsc_queries_display.v1.json"
    payload = _load_json(payload_path)
    payload["query_rows"][0]["page"] = payload["query_rows"][0].pop("query")
    payload["page_rows"][0]["query"] = payload["page_rows"][0].pop("page")
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("requires query scope" in error for error in result.errors)
    assert any("requires page scope" in error for error in result.errors)


def test_empty_ranked_dataset_is_distinct_from_available_or_unavailable(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "gsc_queries_display.v1.json"
    payload = _load_json(payload_path)
    payload["query_rows"] = []
    payload["page_rows"] = []
    payload["data_state"] = "empty"
    _write_json(payload_path, payload)

    empty_result = validate_handoff_directory(handoff_dir)
    assert empty_result.valid is True

    payload["data_state"] = "available"
    _write_json(payload_path, payload)
    invalid_result = validate_handoff_directory(handoff_dir)
    assert invalid_result.valid is False
    assert any("available requires scoped rows" in error for error in invalid_result.errors)


def test_cli_returns_success_on_fake_fixture():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_client_report_publisher_handoff.py",
            str(FIXTURE_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "validation: valid" in completed.stdout
    assert "ga4_metric_display.v1" in completed.stdout
    assert completed.stderr == ""


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "handoff"
    shutil.copytree(FIXTURE_DIR, target)
    return target


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _safe_error_text(errors: list[str]) -> bool:
    joined = "\n".join(errors).lower()
    return all(term not in joined for term in ("bearer ", "ya29.", "private_key_value"))


def _set_manifest_period(handoff_dir: Path, start: str, end: str) -> None:
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["period_start"] = start
    manifest["period_end"] = end
    _write_json(manifest_path, manifest)
    gsc_path = handoff_dir / "gsc_summary_display.v1.json"
    gsc = _load_json(gsc_path)
    gsc["report_period"]["start"] = start
    gsc["report_period"]["end"] = end
    gsc["trend_points"] = []
    gsc.pop("daily_series_coverage", None)
    _write_json(gsc_path, gsc)


def _set_ga4_daily_series(
    handoff_dir: Path,
    start: str,
    count: int,
    *,
    state: str,
) -> None:
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    first = date.fromisoformat(start)
    dates = [(first + timedelta(days=index)).isoformat() for index in range(count)]
    for chart in payload["trend_charts"]:
        chart["grain"] = "day"
        for series in chart["series"]:
            series["points"] = [
                {"date": observed, "value": index + 1}
                for index, observed in enumerate(dates)
            ]
    period_start = date.fromisoformat(_load_json(handoff_dir / "manifest.json")["period_start"])
    period_end = date.fromisoformat(_load_json(handoff_dir / "manifest.json")["period_end"])
    expected = (period_end - period_start).days + 1
    payload["daily_series_coverage"] = {
        "schema_version": "daily_series_coverage.v1",
        "grain": "day",
        "timezone": "provider_local_unspecified",
        "requested_period_start": period_start.isoformat(),
        "requested_period_end": period_end.isoformat(),
        "expected_observation_count": expected,
        "actual_observation_count": count,
        "first_observation_date": dates[0] if dates else None,
        "last_observation_date": dates[-1] if dates else None,
        "coverage_state": state,
        "gap_state": "none" if state == "complete" else "gaps_present",
        "missing_observation_count": expected - count,
        "quality_notes": [] if state == "complete" else ["Fake partial coverage fixture."],
    }
    _write_json(payload_path, payload)
