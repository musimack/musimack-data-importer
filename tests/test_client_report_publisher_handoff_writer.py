import json
from pathlib import Path

from src.client_report_publisher_handoff_validator import validate_handoff_directory
from src.client_report_publisher_handoff_writer import write_client_report_publisher_handoff


def test_handoff_writer_generates_valid_supported_contracts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_json(source / "ga4-summary.json", _ga4_summary())
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "gsc-summary.json", _gsc_summary())

    result = write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    generated_names = sorted(path.name for path in result.files)
    assert generated_names == [
        "ga4_metric_display.v1.json",
        "ga4_most_viewed_pages_display.v1.json",
        "gsc_queries_display.v1.json",
        "gsc_summary_display.v1.json",
        "manifest.json",
    ]
    assert any("source/source-medium rows unavailable" in item for item in result.skipped)
    assert any("landing-page scoped rows unavailable" in item for item in result.skipped)

    validation = validate_handoff_directory(tmp_path / "handoff")
    assert validation.valid is True


def test_handoff_writer_preserves_channel_source_distinction(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_json(source / "ga4-summary.json", _ga4_summary())
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "gsc-summary.json", _gsc_summary())

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    assert not (tmp_path / "handoff" / "ga4_top_sources_display.v1.json").exists()
    assert not (tmp_path / "handoff" / "ga4_top_landing_pages_display.v1.json").exists()
    metric_display = json.loads((tmp_path / "handoff" / "ga4_metric_display.v1.json").read_text())
    assert metric_display["breakdowns"][0]["key"] == "top_traffic_channels"


def test_handoff_writer_can_use_ga4_snapshot_override_for_weekly_period(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4_snapshot = _ga4_snapshot()
    ga4_snapshot["date_range"] = {"start": "2026-06-29", "end": "2026-07-05"}
    ga4_snapshot["time_series"] = [{"date": "2026-06-29", "users": 1, "sessions": 2}]
    _write_json(source / "ga4-summary.json", _ga4_summary())
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "ga4-snapshot-weekly.json", ga4_snapshot)
    _write_json(source / "gsc-summary.json", _gsc_summary())

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        ga4_snapshot_path=source / "ga4-snapshot-weekly.json",
        gsc_summary_path=source / "gsc-summary.json",
        output_dir=tmp_path / "handoff",
    )

    metric_display = json.loads((tmp_path / "handoff" / "ga4_metric_display.v1.json").read_text())
    assert metric_display["report_period"]["start"] == "2026-06-29"
    assert metric_display["trend_charts"][0]["series"][0]["points"] == [
        {"date": "2026-06-29", "value": 1}
    ]


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ga4_summary() -> dict:
    return {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "ga4",
        "reporting_period": {"start": "2026-01-01", "end": "2026-01-07"},
        "summary_metrics": {
            "users": 100,
            "sessions": 120,
            "views": 240,
            "engagement_rate": 0.5,
            "average_session_duration_seconds": 60,
            "event_count": 20,
            "key_events": 4,
            "conversions": 3,
        },
        "time_series": [{"date": "2026-01-01", "users": 10, "sessions": 12}],
        "traffic_channels": [{"channel": "Organic Search", "sessions": 80, "users": 70, "engagement_rate": 0.6}],
        "top_pages": [{"path": "/", "label": "Home", "views": 90, "users": 50, "event_count": 8}],
    }


def _ga4_snapshot() -> dict:
    return {
        "schema_version": "ga4_snapshot.v1",
        "date_range": {"start": "2026-01-01", "end": "2026-01-07"},
        "metrics": [
            {"name": "users", "value": 100},
            {"name": "sessions", "value": 120},
            {"name": "views", "value": 240},
            {"name": "engagement_rate", "value": 0.5},
            {"name": "average_session_duration_seconds", "value": 60},
            {"name": "key_events", "value": 4},
            {"name": "conversions", "value": 3},
        ],
        "time_series": [{"date": "2026-01-01", "users": 10, "sessions": 12}],
        "dimension_rows": [
            {"kind": "traffic_channels", "label": "Organic Search", "metrics": {"sessions": 80, "users": 70, "engagement_rate": 0.6}},
            {"kind": "top_pages", "label": "Home", "metrics": {"views": 90, "users": 50, "event_count": 8}},
        ],
    }


def _gsc_summary() -> dict:
    return {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "gsc",
        "reporting_period": {"start": "2026-01-01", "end": "2026-01-07"},
        "summary_metrics": {"clicks": 10, "impressions": 100, "ctr": 0.1, "average_position": 4.2},
        "time_series": [{"date": "2026-01-01", "clicks": 1, "impressions": 10, "ctr": 0.1, "average_position": 4.0}],
        "top_queries": [{"query": "sample query", "clicks": 5, "impressions": 50, "ctr": 0.1, "average_position": 3.0}],
        "top_pages": [{"path": "https://example.com/", "clicks": 6, "impressions": 60, "ctr": 0.1, "average_position": 2.5}],
    }
