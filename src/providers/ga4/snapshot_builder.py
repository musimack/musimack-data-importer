from __future__ import annotations

from typing import Any

from ...config import DateRange
from .normalize import NormalizedTrafficOverview

SCHEMA_VERSION = "ga4_snapshot.v1"
SNAPSHOT_PROVIDER = "ga4"
PROVIDER_KEY = "google_analytics"
REPORT_TYPE = "traffic_overview"


def build_traffic_overview_snapshot(
    normalized: NormalizedTrafficOverview,
    property_resource: str,
    date_range: DateRange,
) -> dict[str, Any]:
    dimension_rows = [
        row.as_dict() for row in [*normalized.channel_rows, *normalized.top_page_rows]
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "provider": SNAPSHOT_PROVIDER,
        "provider_key": PROVIDER_KEY,
        "report_type": REPORT_TYPE,
        "property_resource": property_resource,
        "date_range": {
            "start": date_range.start.isoformat(),
            "end": date_range.end.isoformat(),
        },
        "comparison_date_range": None,
        "source": "future_live",
        "summary": _summary(normalized),
        "metrics": [metric.as_dict() for metric in normalized.metrics],
        "dimension_rows": dimension_rows,
        "time_series": normalized.time_series,
        "summary_counts": {
            "metric_count": len(normalized.metrics),
            "dimension_row_count": len(dimension_rows),
            "time_series_count": len(normalized.time_series),
        },
        "warnings": normalized.warnings,
    }
    return payload


def _summary(normalized: NormalizedTrafficOverview) -> str:
    lookup = {metric.name: metric.value for metric in normalized.metrics}
    users = int(round(lookup.get("users", 0)))
    sessions = int(round(lookup.get("sessions", 0)))
    views = int(round(lookup.get("views", 0)))
    return (
        "Sanitized GA4 traffic overview for local Musimack internal review: "
        f"{users} users, {sessions} sessions, and {views} views."
    )
