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


def test_presentation_range_exact_summary_references_must_resolve(tmp_path):
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    manifest = {
        "schema_version": "client_report_publisher_handoff_manifest.v1",
        "client_slug": "sample-client",
        "period_start": "2026-01-01",
        "period_end": "2026-07-08",
        "generated_at": "2026-07-09T12:00:00Z",
        "files": [
            {
                "path": "client_report_presentation_ranges.v2.json",
                "provider": "presentation",
                "report_type": "range_dataset",
                "schema_version": "client_report_presentation_ranges.v2",
            }
        ],
        "display_contract_versions": ["client_report_presentation_ranges.v2"],
        "validation_status": "fixture_only_not_real_export",
    }
    package = _minimal_exact_summary_range_package()
    _write_json(handoff_dir / "manifest.json", manifest)
    _write_json(handoff_dir / "client_report_presentation_ranges.v2.json", package)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("references missing GA4 exact-range source" in error for error in result.errors)

    manifest["files"].append(
        {
            "path": "ga4_metric_display_exact_ranges.v1.json",
            "provider": "ga4",
            "report_type": "metric_display_exact_ranges",
            "schema_version": "ga4_metric_display_exact_ranges.v1",
        }
    )
    manifest["display_contract_versions"].append("ga4_metric_display_exact_ranges.v1")
    _write_json(handoff_dir / "manifest.json", manifest)
    _write_json(handoff_dir / "ga4_metric_display_exact_ranges.v1.json", _minimal_exact_summary_source())

    valid = validate_handoff_directory(handoff_dir)

    assert valid.valid is True


def test_presentation_range_exact_summary_wrong_section_reference_fails(tmp_path):
    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    manifest = {
        "schema_version": "client_report_publisher_handoff_manifest.v1",
        "client_slug": "sample-client",
        "period_start": "2026-01-01",
        "period_end": "2026-07-08",
        "generated_at": "2026-07-09T12:00:00Z",
        "files": [
            {
                "path": "client_report_presentation_ranges.v2.json",
                "provider": "presentation",
                "report_type": "range_dataset",
                "schema_version": "client_report_presentation_ranges.v2",
            },
            {
                "path": "ga4_metric_display_exact_ranges.v1.json",
                "provider": "ga4",
                "report_type": "metric_display_exact_ranges",
                "schema_version": "ga4_metric_display_exact_ranges.v1",
            },
        ],
        "display_contract_versions": [
            "client_report_presentation_ranges.v2",
            "ga4_metric_display_exact_ranges.v1",
        ],
        "validation_status": "fixture_only_not_real_export",
    }
    package = _minimal_exact_summary_range_package()
    package["section_buckets"][0]["source_contract"] = "ga4_top_sources_display.v1"
    _write_json(handoff_dir / "manifest.json", manifest)
    _write_json(handoff_dir / "client_report_presentation_ranges.v2.json", package)
    _write_json(handoff_dir / "ga4_metric_display_exact_ranges.v1.json", _minimal_exact_summary_source())

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("source_contract does not match section" in error for error in result.errors)


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


def _minimal_exact_summary_range_package() -> dict:
    return {
        "schema_version": "client_report_presentation_ranges.v2",
        "provider": "presentation",
        "report_type": "range_dataset",
        "client_slug": "sample-client",
        "report_period": {"start_date": "2026-01-01", "end_date": "2026-07-08"},
        "reference_date": "2026-07-08",
        "anchor_rule": "report_period_end",
        "timezone": "America/Los_Angeles",
        "dataset_version": "sample-client:2026-01-01:2026-07-08:presentation-ranges.v2",
        "generated_at": "2026-07-09T12:00:00Z",
        "source_snapshot_identity": {},
        "range_manifest": [
            _range_manifest("last_3_days", "2026-07-06", "2026-07-08"),
            _range_manifest("last_7_days", "2026-07-02", "2026-07-08"),
            _range_manifest("last_14_days", "2026-06-25", "2026-07-08"),
            _range_manifest("last_30_days", "2026-06-09", "2026-07-08"),
            _range_manifest("last_90_days", "2026-04-10", "2026-07-08"),
            _range_manifest("last_6_months", "2026-01-09", "2026-07-08"),
            _range_manifest("last_12_months", "2025-07-09", "2026-07-08", coverage="partial", effective_start="2026-01-01"),
            _range_manifest("this_month", "2026-07-01", "2026-07-08"),
            _range_manifest("last_month", "2026-06-01", "2026-06-30"),
        ],
        "section_capabilities": [{"section_key": key} for key in [
            "ga4_top_metrics",
            "ga4_website_traffic_trends",
            "ga4_channel_performance",
            "ga4_user_engagement",
            "ga4_top_sources",
            "ga4_top_landing_pages",
            "ga4_most_viewed_pages",
            "gsc_summary",
            "gsc_top_queries",
            "gsc_top_pages",
        ]],
        "section_buckets": [
            {
                "section_key": "ga4_top_metrics",
                "range_key": "last_7_days",
                "preset_key": "last_7_days",
                "requested_start_date": "2026-07-02",
                "requested_end_date": "2026-07-08",
                "effective_start_date": "2026-07-02",
                "effective_end_date": "2026-07-08",
                "source_contract": "ga4_metric_display.v1",
                "dataset_version": "presentation_ranges.v2",
                "precomputed_status": "ready",
                "aggregation_status": "importer_sanitized_precomputed",
                "display_schema_version": "generated_section_display.v1",
                "row_count": 1,
                "observation_count": 0,
                "quality_notes": [],
                "coverage_state": "complete",
                "data_state": "available",
                "exact_source": {
                    "source_contract": "ga4_metric_display_exact_ranges.v1",
                    "dataset_version": "ga4_metric_display_exact_ranges.v1",
                    "range_key": "last_7_days",
                    "requested_start_date": "2026-07-02",
                    "requested_end_date": "2026-07-08",
                    "source_identity": "sample-client:last_7_days:2026-07-02:2026-07-08",
                },
                "display_data": {"metrics": [{"key": "users", "label": "Users", "value": "707"}]},
            }
        ],
        "validation_summary": {"status": "generated_not_validated", "warnings": []},
    }


def _minimal_exact_summary_source() -> dict:
    return {
        "schema_version": "ga4_metric_display_exact_ranges.v1",
        "provider": "ga4",
        "report_type": "metric_display_exact_ranges",
        "data_scope": "ga4_exact_range_summary",
        "dataset_version": "ga4_metric_display_exact_ranges.v1",
        "client_slug": "sample-client",
        "report_period": {"start_date": "2026-01-01", "end_date": "2026-07-08"},
        "timezone": "America/Los_Angeles",
        "inclusive_dates": True,
        "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
        "generated_at": "2026-07-09T12:00:00Z",
        "source_identity": {"source_kind": "synthetic_fixture"},
        "query_identity": {"shape_id": "synthetic", "fingerprint": "synthetic"},
        "metric_definitions": [
            {"key": "users"},
            {"key": "new_users"},
            {"key": "sessions"},
            {"key": "views"},
            {"key": "engaged_sessions"},
            {"key": "engagement_rate"},
            {"key": "average_session_duration_seconds"},
            {"key": "average_engagement_time_seconds"},
            {"key": "event_count"},
            {"key": "key_events"},
            {"key": "conversions"},
        ],
        "ranges": [
            {
                "range_key": "last_7_days",
                "requested_start_date": "2026-07-02",
                "requested_end_date": "2026-07-08",
                "inclusive_dates": True,
                "data_state": "available",
                "coverage_state": "complete",
                "quality_state": "passed",
                "expected_date_count": 7,
                "actual_date_count": 7,
                "metrics": {"users": 707, "sessions": 814, "views": 1401, "engagement_rate": 0.62},
                "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
                "source_identity": "sample-client:last_7_days:2026-07-02:2026-07-08",
                "quality_notes": ["Synthetic exact-range summary fixture."],
            }
        ],
    }


def _range_manifest(
    range_key: str,
    start: str,
    end: str,
    *,
    coverage: str = "complete",
    effective_start: str | None = None,
) -> dict:
    return {
        "range_key": range_key,
        "preset_key": range_key,
        "requested_start_date": start,
        "requested_end_date": end,
        "effective_start_date": effective_start or start,
        "effective_end_date": end,
        "coverage_state": coverage,
        "required": True,
    }
