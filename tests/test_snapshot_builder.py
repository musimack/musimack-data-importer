from datetime import date

from src.config import DateRange
from src.normalize import normalize_traffic_overview
from src.snapshot_builder import build_traffic_overview_snapshot
from tests.test_normalize import mocked_ga4_response, mocked_richer_ga4_response


def test_snapshot_builder_creates_ga4_snapshot_v1_payload():
    date_range = DateRange(date(2026, 4, 1), date(2026, 4, 30))
    normalized = normalize_traffic_overview(mocked_ga4_response())
    payload = build_traffic_overview_snapshot(
        normalized,
        "properties/123456789",
        date_range,
    )

    assert payload["schema_version"] == "ga4_snapshot.v1"
    assert payload["provider"] == "ga4"
    assert payload["provider_key"] == "google_analytics"
    assert payload["report_type"] == "traffic_overview"
    assert payload["property_resource"] == "properties/123456789"
    assert payload["date_range"] == {"start": "2026-04-01", "end": "2026-04-30"}
    assert payload["source"] == "future_live"
    assert payload["summary_counts"]["metric_count"] == len(payload["metrics"])
    assert payload["dimension_rows"] == []


def test_snapshot_payload_has_display_compatible_metric_names():
    date_range = DateRange(date(2026, 4, 1), date(2026, 4, 30))
    normalized = normalize_traffic_overview(mocked_ga4_response())
    payload = build_traffic_overview_snapshot(normalized, "properties/123456789", date_range)
    names = {metric["name"] for metric in payload["metrics"]}

    assert {"users", "sessions", "engagement_rate", "views", "event_count"}.issubset(names)


def test_snapshot_payload_includes_richer_channel_and_top_page_rows():
    date_range = DateRange(date(2026, 4, 1), date(2026, 4, 30))
    normalized = normalize_traffic_overview(mocked_richer_ga4_response())
    payload = build_traffic_overview_snapshot(normalized, "properties/123456789", date_range)

    kinds = {row.get("kind") for row in payload["dimension_rows"]}
    assert {"traffic_channels", "top_pages", "source_medium", "landing_pages"}.issubset(kinds)
    assert payload["summary_counts"]["dimension_row_count"] == len(payload["dimension_rows"])
