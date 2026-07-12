import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.client_report_publisher_handoff_validator import validate_handoff_directory
from src.client_report_publisher_handoff_writer import write_client_report_publisher_handoff
from src.client_report_presentation_ranges import resolve_range_key


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
        "client_report_presentation_ranges.v2.json",
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


def test_handoff_writer_generates_production_presentation_ranges(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4_summary = _ga4_summary_with_scoped_rows()
    ga4_snapshot = _ga4_snapshot_with_scoped_rows()
    gsc_summary = _gsc_summary()
    period = {"start": "2026-01-01", "end": "2026-07-08"}
    daily_rows = _daily_rows(period["start"], 189)
    ga4_summary["reporting_period"] = period
    ga4_summary["time_series"] = daily_rows
    ga4_snapshot["date_range"] = period
    ga4_snapshot["time_series"] = daily_rows
    gsc_summary["reporting_period"] = period
    gsc_summary["time_series"] = daily_rows
    _write_json(source / "ga4-summary.json", ga4_summary)
    _write_json(source / "ga4-snapshot.json", ga4_snapshot)
    _write_json(source / "gsc-summary.json", gsc_summary)

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    ranges = json.loads((tmp_path / "handoff" / "client_report_presentation_ranges.v2.json").read_text())
    assert ranges["schema_version"] == "client_report_presentation_ranges.v2"
    assert ranges["reference_date"] == "2026-07-08"
    assert ranges["anchor_rule"] == "report_period_end"
    assert len(ranges["range_manifest"]) == 9
    assert len(ranges["section_capabilities"]) == 10
    trend_last_30 = next(
        bucket
        for bucket in ranges["section_buckets"]
        if bucket["section_key"] == "ga4_website_traffic_trends"
        and bucket["range_key"] == "last_30_days"
    )
    assert trend_last_30["data_state"] == "available"
    assert trend_last_30["aggregation_status"] == "existing_daily_observation_slice"
    assert trend_last_30["display_data"]["trends"][0]["points"][0]["date"] == "2026-06-09"
    assert trend_last_30["display_data"]["trends"][0]["points"][-1]["date"] == "2026-07-08"
    assert len(trend_last_30["display_data"]["trends"][0]["points"]) == 30
    top_sources_last_30 = next(
        bucket
        for bucket in ranges["section_buckets"]
        if bucket["section_key"] == "ga4_top_sources" and bucket["range_key"] == "last_30_days"
    )
    assert top_sources_last_30["data_state"] == "unavailable"
    assert top_sources_last_30["display_data"] is None
    assert "full-period data" in top_sources_last_30["unsupported_reason"]
    assert validate_handoff_directory(tmp_path / "handoff").valid is True


def test_handoff_writer_emits_ga4_exact_range_summary_buckets_for_two_sections(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4_summary = _ga4_summary_with_scoped_rows()
    ga4_snapshot = _ga4_snapshot_with_scoped_rows()
    gsc_summary = _gsc_summary()
    period = {"start": "2026-01-01", "end": "2026-07-08"}
    daily_rows = _daily_rows(period["start"], 189)
    ga4_summary["reporting_period"] = period
    ga4_summary["time_series"] = daily_rows
    ga4_snapshot["date_range"] = period
    ga4_snapshot["time_series"] = daily_rows
    gsc_summary["reporting_period"] = period
    gsc_summary["time_series"] = daily_rows
    _write_json(source / "ga4-summary.json", ga4_summary)
    _write_json(source / "ga4-snapshot.json", ga4_snapshot)
    _write_json(source / "gsc-summary.json", gsc_summary)
    _write_json(source / "ga4_metric_display_exact_ranges.v1.json", _ga4_exact_ranges())

    result = write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    generated_names = sorted(path.name for path in result.files)
    assert "ga4_metric_display_exact_ranges.v1.json" in generated_names
    ranges = json.loads((tmp_path / "handoff" / "client_report_presentation_ranges.v2.json").read_text())
    ready = [
        bucket
        for bucket in ranges["section_buckets"]
        if bucket["section_key"] in {"ga4_top_metrics", "ga4_user_engagement"}
        and bucket["data_state"] == "available"
    ]
    assert len(ready) == 8
    assert {bucket["range_key"] for bucket in ready} == {
        "last_7_days",
        "last_30_days",
        "this_month",
        "last_month",
    }
    top_metrics_last_7 = next(
        bucket
        for bucket in ready
        if bucket["section_key"] == "ga4_top_metrics" and bucket["range_key"] == "last_7_days"
    )
    assert top_metrics_last_7["requested_start_date"] == "2026-07-02"
    assert top_metrics_last_7["requested_end_date"] == "2026-07-08"
    assert top_metrics_last_7["source_contract"] == "ga4_metric_display.v1"
    assert top_metrics_last_7["exact_source"]["source_contract"] == "ga4_metric_display_exact_ranges.v1"
    assert top_metrics_last_7["display_data"]["metrics"][0] == {
        "key": "users",
        "label": "Users",
        "value": "707",
    }
    user_engagement_last_7 = next(
        bucket
        for bucket in ready
        if bucket["section_key"] == "ga4_user_engagement" and bucket["range_key"] == "last_7_days"
    )
    assert any(
        metric == {"key": "average_engagement_time", "label": "Average Engagement Time", "value": "74s"}
        for metric in user_engagement_last_7["display_data"]["metrics"]
    )
    traffic_trend_last_7 = next(
        bucket
        for bucket in ranges["section_buckets"]
        if bucket["section_key"] == "ga4_website_traffic_trends" and bucket["range_key"] == "last_7_days"
    )
    assert traffic_trend_last_7["aggregation_status"] == "existing_daily_observation_slice"
    assert not any(
        bucket["section_key"] in {"ga4_top_sources", "ga4_top_landing_pages", "ga4_most_viewed_pages"}
        and bucket["data_state"] == "available"
        for bucket in ranges["section_buckets"]
    )
    assert validate_handoff_directory(tmp_path / "handoff").valid is True


def test_presentation_range_resolution_uses_report_end_anchor():
    reference = date.fromisoformat("2026-07-08")
    assert resolve_range_key("last_3_days", reference).start_date.isoformat() == "2026-07-06"
    assert resolve_range_key("last_3_days", reference).end_date.isoformat() == "2026-07-08"
    assert resolve_range_key("this_month", reference).start_date.isoformat() == "2026-07-01"
    assert resolve_range_key("last_month", reference).start_date.isoformat() == "2026-06-01"
    assert resolve_range_key("last_month", reference).end_date.isoformat() == "2026-06-30"


def test_presentation_range_resolution_handles_leap_year_month_boundary():
    reference = date.fromisoformat("2024-03-31")
    assert resolve_range_key("last_month", reference).start_date.isoformat() == "2024-02-01"
    assert resolve_range_key("last_month", reference).end_date.isoformat() == "2024-02-29"
    assert resolve_range_key("last_6_months", reference).start_date.isoformat() == "2023-10-01"


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


def test_handoff_writer_generates_scoped_source_and_landing_page_contracts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_json(source / "ga4-summary.json", _ga4_summary_with_scoped_rows())
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot_with_scoped_rows())
    _write_json(source / "gsc-summary.json", _gsc_summary())

    result = write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    generated_names = sorted(path.name for path in result.files)
    assert "ga4_top_sources_display.v1.json" in generated_names
    assert "ga4_top_landing_pages_display.v1.json" in generated_names
    assert not any("source/source-medium rows unavailable" in item for item in result.skipped)
    assert not any("landing-page scoped rows unavailable" in item for item in result.skipped)

    sources = json.loads((tmp_path / "handoff" / "ga4_top_sources_display.v1.json").read_text())
    landing_pages = json.loads(
        (tmp_path / "handoff" / "ga4_top_landing_pages_display.v1.json").read_text()
    )
    assert sources["rows"][0]["label"] == "google / organic"
    assert sources["notes"][1].endswith("not broad traffic channels.")
    assert landing_pages["rows"][0]["path"] == "/rooms/"
    assert landing_pages["notes"][1].endswith("not broad most-viewed page rows.")

    validation = validate_handoff_directory(tmp_path / "handoff")
    assert validation.valid is True


def test_handoff_writer_can_use_ga4_snapshot_override_for_weekly_period(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4_snapshot = _ga4_snapshot()
    ga4_snapshot["date_range"] = {"start": "2026-06-29", "end": "2026-07-05"}
    ga4_snapshot["time_series"] = [{"date": "2026-06-29", "users": 1, "sessions": 2}]
    gsc_summary = _gsc_summary()
    gsc_summary["reporting_period"] = {"start": "2026-06-29", "end": "2026-07-05"}
    gsc_summary["time_series"] = [
        {"date": "2026-06-29", "clicks": 1, "impressions": 10, "ctr": 0.1, "average_position": 4.0}
    ]
    _write_json(source / "ga4-summary.json", _ga4_summary())
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "ga4-snapshot-weekly.json", ga4_snapshot)
    _write_json(source / "gsc-summary.json", gsc_summary)

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


def test_handoff_writer_preserves_complete_189_day_series_and_coverage(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4_summary = _ga4_summary()
    ga4_snapshot = _ga4_snapshot()
    gsc_summary = _gsc_summary()
    period = {"start": "2026-01-01", "end": "2026-07-08"}
    daily_rows = _daily_rows(period["start"], 189)
    for payload in (ga4_summary, gsc_summary):
        payload["reporting_period"] = period
        payload["time_series"] = daily_rows
    ga4_snapshot["date_range"] = period
    ga4_snapshot["time_series"] = daily_rows
    _write_json(source / "ga4-summary.json", ga4_summary)
    _write_json(source / "ga4-snapshot.json", ga4_snapshot)
    _write_json(source / "gsc-summary.json", gsc_summary)

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    ga4 = json.loads((tmp_path / "handoff" / "ga4_metric_display.v1.json").read_text())
    gsc = json.loads((tmp_path / "handoff" / "gsc_summary_display.v1.json").read_text())
    for series in ga4["trend_charts"][0]["series"]:
        assert len(series["points"]) == 189
        assert series["points"][0]["date"] == "2026-01-01"
        assert series["points"][-1]["date"] == "2026-07-08"
    assert len(gsc["trend_points"]) == 189
    for payload in (ga4, gsc):
        coverage = payload["daily_series_coverage"]
        assert coverage["expected_observation_count"] == 189
        assert coverage["actual_observation_count"] == 189
        assert coverage["coverage_state"] == "complete"
        assert coverage["gap_state"] == "none"
        assert coverage["first_observation_date"] == "2026-01-01"
        assert coverage["last_observation_date"] == "2026-07-08"
    assert len(ga4["breakdowns"][0]["rows"]) <= 10
    assert validate_handoff_directory(tmp_path / "handoff").valid is True


def test_writer_emits_only_canonical_dataset_metadata(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4 = _ga4_summary()
    ga4["top_sources"] = [{"label": "example / organic", "sessions": 5, "users": 4}]
    ga4["top_landing_pages"] = [{"path": "/", "label": "Home", "sessions": 5}]
    _write_json(source / "ga4-summary.json", ga4)
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "gsc-summary.json", _gsc_summary())

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    expected = {
        "ga4_metric_display.v1.json": ("ga4_report_summary", "available"),
        "ga4_top_sources_display.v1.json": ("source_medium", "available"),
        "ga4_top_landing_pages_display.v1.json": ("landing_page", "available"),
        "ga4_most_viewed_pages_display.v1.json": ("page_popularity", "available"),
        "gsc_summary_display.v1.json": ("search_summary", "available"),
        "gsc_queries_display.v1.json": ("search_query_and_page", "available"),
    }
    for filename, (scope, state) in expected.items():
        payload = json.loads((tmp_path / "handoff" / filename).read_text())
        assert payload["data_scope"] == scope
        assert payload["data_state"] == state
        assert "site_label" not in payload


def test_handoff_writer_marks_partial_and_empty_daily_coverage(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ga4 = _ga4_summary()
    ga4["time_series"] = [
        {"date": "2026-01-01", "users": 1, "sessions": 1},
        {"date": "2026-01-03", "users": 2, "sessions": 2},
    ]
    gsc = _gsc_summary()
    gsc["time_series"] = []
    _write_json(source / "ga4-summary.json", ga4)
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "gsc-summary.json", gsc)

    write_client_report_publisher_handoff(
        profile="sample-client",
        client_name="Sample Client",
        source_dir=source,
        output_dir=tmp_path / "handoff",
    )

    ga4_output = json.loads((tmp_path / "handoff" / "ga4_metric_display.v1.json").read_text())
    gsc_output = json.loads((tmp_path / "handoff" / "gsc_summary_display.v1.json").read_text())
    assert ga4_output["daily_series_coverage"]["coverage_state"] == "partial"
    assert ga4_output["daily_series_coverage"]["gap_state"] == "gaps_present"
    assert gsc_output["daily_series_coverage"]["coverage_state"] == "empty"
    assert gsc_output["daily_series_coverage"]["gap_state"] == "not_applicable"


@pytest.mark.parametrize(
    "rows,error_text",
    [
        ([{"date": "2026-01-01"}, {"date": "2026-01-01"}], "unique"),
        ([{"date": "2026-01-02"}, {"date": "2026-01-01"}], "ascending"),
        ([{"date": "2025-12-31"}], "inside the report period"),
    ],
)
def test_handoff_writer_rejects_unsafe_daily_dates(tmp_path, rows, error_text):
    source = tmp_path / "source"
    source.mkdir()
    ga4 = _ga4_summary()
    ga4["time_series"] = rows
    _write_json(source / "ga4-summary.json", ga4)
    _write_json(source / "ga4-snapshot.json", _ga4_snapshot())
    _write_json(source / "gsc-summary.json", _gsc_summary())

    with pytest.raises(ValueError, match=error_text):
        write_client_report_publisher_handoff(
            profile="sample-client",
            client_name="Sample Client",
            source_dir=source,
            output_dir=tmp_path / "handoff",
        )


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


def _ga4_summary_with_scoped_rows() -> dict:
    payload = _ga4_summary()
    payload["top_sources"] = [
        {
            "label": "google / organic",
            "sessions": 70,
            "users": 60,
            "engagement_rate": 0.64,
            "average_session_duration_seconds": 82,
            "event_count": 12,
        }
    ]
    payload["top_landing_pages"] = [
        {
            "path": "/rooms/",
            "label": "/rooms/",
            "sessions": 40,
            "users": 35,
            "engaged_sessions": 27,
            "engagement_rate": 0.67,
            "event_count": 9,
        }
    ]
    return payload


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


def _ga4_snapshot_with_scoped_rows() -> dict:
    payload = _ga4_snapshot()
    payload["dimension_rows"].extend(
        [
            {
                "kind": "source_medium",
                "label": "google / organic",
                "metrics": {
                    "sessions": 70,
                    "users": 60,
                    "engagement_rate": 0.64,
                    "average_session_duration_seconds": 82,
                    "event_count": 12,
                },
            },
            {
                "kind": "landing_pages",
                "label": "/rooms/",
                "metrics": {
                    "sessions": 40,
                    "users": 35,
                    "engaged_sessions": 27,
                    "engagement_rate": 0.67,
                    "event_count": 9,
                },
            },
        ]
    )
    return payload


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


def _daily_rows(start: str, count: int) -> list[dict]:
    first = date.fromisoformat(start)
    return [
        {
            "date": (first + timedelta(days=index)).isoformat(),
            "users": index + 1,
            "sessions": index + 2,
            "clicks": index,
            "impressions": index * 10,
            "ctr": 0.1,
            "average_position": 4.0,
        }
        for index in range(count)
    ]


def _ga4_exact_ranges() -> dict:
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
        "source_identity": {
            "source_kind": "synthetic_fixture",
            "source_label": "Synthetic GA4 exact-range summary fixture",
        },
        "query_identity": {
            "shape_id": "ga4_summary_exact_range.synthetic.v1",
            "fingerprint": "sample-client-ga4-summary-exact-ranges-v1",
        },
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
            _ga4_exact_range("last_7_days", "2026-07-02", "2026-07-08", 7, users=707, sessions=814, views=1401),
            _ga4_exact_range("last_30_days", "2026-06-09", "2026-07-08", 30, users=3000, sessions=3510, views=7090, key_events=0),
            _ga4_exact_range("this_month", "2026-07-01", "2026-07-08", 8, users=808, sessions=922, views=1600),
            _ga4_exact_range("last_month", "2026-06-01", "2026-06-30", 30, users=2900, sessions=3300, views=6800, include_new_users=False),
        ],
    }


def _ga4_exact_range(
    range_key: str,
    start: str,
    end: str,
    expected: int,
    *,
    users: int,
    sessions: int,
    views: int,
    key_events: int = 42,
    include_new_users: bool = True,
) -> dict:
    metrics = {
        "users": users,
        "sessions": sessions,
        "views": views,
        "engaged_sessions": int(sessions * 0.62),
        "engagement_rate": 0.62,
        "average_engagement_time_seconds": 74,
        "average_session_duration_seconds": 118,
        "event_count": views * 2,
        "key_events": key_events,
        "conversions": 9,
    }
    if include_new_users:
        metrics["new_users"] = users - 100
    return {
        "range_key": range_key,
        "requested_start_date": start,
        "requested_end_date": end,
        "inclusive_dates": True,
        "data_state": "available",
        "coverage_state": "complete",
        "quality_state": "passed",
        "expected_date_count": expected,
        "actual_date_count": expected,
        "metrics": metrics,
        "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
        "source_identity": f"sample-client:{range_key}:{start}:{end}",
        "quality_notes": ["Synthetic exact-range summary fixture."],
    }
