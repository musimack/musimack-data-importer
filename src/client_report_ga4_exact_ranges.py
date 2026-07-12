from __future__ import annotations

import math
from datetime import date
from typing import Any


GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION = "ga4_metric_display_exact_ranges.v1"
GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE = "metric_display_exact_ranges"
GA4_EXACT_RANGE_SUMMARY_DATA_SCOPE = "ga4_exact_range_summary"
GA4_EXACT_RANGE_SUMMARY_CALCULATION_VERSION = "ga4_summary_exact_ranges.synthetic.v1"
GA4_EXACT_RANGE_SUMMARY_PROVIDER_CALCULATION_VERSION = "ga4_summary_exact_ranges.provider.v1"
GA4_EXACT_RANGE_SUMMARY_CALCULATION_VERSIONS = {
    GA4_EXACT_RANGE_SUMMARY_CALCULATION_VERSION,
    GA4_EXACT_RANGE_SUMMARY_PROVIDER_CALCULATION_VERSION,
}

TOP_METRICS_SECTION = "ga4_top_metrics"
USER_ENGAGEMENT_SECTION = "ga4_user_engagement"
SUPPORTED_SECTIONS = {TOP_METRICS_SECTION, USER_ENGAGEMENT_SECTION}

REQUIRED_AVAILABLE_METRICS = ("users", "sessions", "views", "engagement_rate")


METRIC_DEFINITIONS: dict[str, dict[str, str | bool]] = {
    "users": {
        "provider_metric_name": "activeUsers",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": True,
        "formula_version": "provider_direct.v1",
    },
    "new_users": {
        "provider_metric_name": "newUsers",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": False,
        "formula_version": "provider_direct.v1",
    },
    "sessions": {
        "provider_metric_name": "sessions",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": True,
        "formula_version": "provider_direct.v1",
    },
    "views": {
        "provider_metric_name": "screenPageViews",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": True,
        "formula_version": "provider_direct.v1",
    },
    "engaged_sessions": {
        "provider_metric_name": "engagedSessions",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": False,
        "formula_version": "provider_direct.v1",
    },
    "engagement_rate": {
        "provider_metric_name": "engagementRate",
        "value_type": "ratio",
        "unit": "percent",
        "source_kind": "provider_ratio",
        "required_for_available": True,
        "formula_version": "provider_ratio.v1",
    },
    "average_session_duration_seconds": {
        "provider_metric_name": "averageSessionDuration",
        "value_type": "duration_seconds",
        "unit": "seconds",
        "source_kind": "provider_average",
        "required_for_available": False,
        "formula_version": "provider_average.v1",
    },
    "average_engagement_time_seconds": {
        "provider_metric_name": "averageEngagementTime",
        "value_type": "duration_seconds",
        "unit": "seconds",
        "source_kind": "provider_average",
        "required_for_available": False,
        "formula_version": "provider_average.v1",
    },
    "event_count": {
        "provider_metric_name": "eventCount",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": False,
        "formula_version": "provider_direct.v1",
    },
    "key_events": {
        "provider_metric_name": "keyEvents",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": False,
        "formula_version": "provider_direct.v1",
    },
    "conversions": {
        "provider_metric_name": "conversions",
        "value_type": "integer",
        "unit": "count",
        "source_kind": "direct",
        "required_for_available": False,
        "formula_version": "provider_direct.v1",
    },
}

TOP_METRICS_ORDER = (
    "users",
    "new_users",
    "sessions",
    "views",
    "engagement_rate",
    "average_session_duration_seconds",
    "average_engagement_time_seconds",
    "event_count",
    "key_events",
    "conversions",
)

USER_ENGAGEMENT_ORDER = (
    "engagement_rate",
    "average_engagement_time_seconds",
    "engaged_sessions",
    "event_count",
    "key_events",
    "conversions",
)

DISPLAY_LABELS = {
    "users": "Users",
    "new_users": "New Users",
    "sessions": "Sessions",
    "views": "Page Views",
    "engaged_sessions": "Engaged Sessions",
    "engagement_rate": "Engagement Rate",
    "average_session_duration_seconds": "Avg. Session Duration",
    "average_engagement_time_seconds": "Average Engagement Time",
    "event_count": "Events",
    "key_events": "Key Events",
    "conversions": "Conversions",
}

DISPLAY_KEYS = {
    "average_session_duration_seconds": "average_session_duration",
    "average_engagement_time_seconds": "average_engagement_time",
}


def metric_definitions_payload() -> list[dict[str, Any]]:
    return [
        {"key": key, **definition}
        for key, definition in METRIC_DEFINITIONS.items()
    ]


def validate_ga4_exact_range_summary_contract(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION:
        raise ValueError("exact-range GA4 summary schema_version is unsupported")
    if payload.get("provider") != "ga4":
        raise ValueError("exact-range GA4 summary provider must be ga4")
    if payload.get("report_type") != GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE:
        raise ValueError("exact-range GA4 summary report_type is invalid")
    if payload.get("data_scope") != GA4_EXACT_RANGE_SUMMARY_DATA_SCOPE:
        raise ValueError("exact-range GA4 summary data_scope is invalid")
    if payload.get("dataset_version") != GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION:
        raise ValueError("exact-range GA4 summary dataset_version is invalid")
    if payload.get("calculation_version") not in GA4_EXACT_RANGE_SUMMARY_CALCULATION_VERSIONS:
        raise ValueError("exact-range GA4 summary calculation_version is invalid")

    period = payload.get("report_period")
    if not isinstance(period, dict):
        raise ValueError("exact-range GA4 summary report_period is required")
    period_start = _parse_date(period.get("start_date"), "report_period.start_date")
    period_end = _parse_date(period.get("end_date"), "report_period.end_date")
    if period_start > period_end:
        raise ValueError("exact-range GA4 summary report_period is inverted")

    timezone = payload.get("timezone")
    if not isinstance(timezone, str) or "/" not in timezone:
        raise ValueError("exact-range GA4 summary timezone is invalid")
    if payload.get("inclusive_dates") is not True:
        raise ValueError("exact-range GA4 summary inclusive_dates must be true")
    if not isinstance(payload.get("source_identity"), dict):
        raise ValueError("exact-range GA4 summary source_identity is required")
    if not isinstance(payload.get("query_identity"), dict):
        raise ValueError("exact-range GA4 summary query_identity is required")

    definitions = payload.get("metric_definitions")
    if not isinstance(definitions, list):
        raise ValueError("exact-range GA4 summary metric_definitions must be a list")
    definition_keys = {
        definition.get("key")
        for definition in definitions
        if isinstance(definition, dict)
    }
    if set(METRIC_DEFINITIONS) - definition_keys:
        raise ValueError("exact-range GA4 summary metric_definitions are incomplete")

    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        raise ValueError("exact-range GA4 summary ranges must be a list")
    seen: set[tuple[str, date, date]] = set()
    for index, item in enumerate(ranges):
        _validate_range_entry(item, index, period_start, period_end, seen)


def exact_range_entry_for(
    payload: dict[str, Any],
    *,
    range_key: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any] | None:
    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        return None
    for item in ranges:
        if (
            isinstance(item, dict)
            and item.get("range_key") == range_key
            and item.get("requested_start_date") == start_date
            and item.get("requested_end_date") == end_date
        ):
            return item
    return None


def display_data_for_section(entry: dict[str, Any], section_key: str) -> dict[str, Any] | None:
    if section_key not in SUPPORTED_SECTIONS:
        return None
    if entry.get("data_state") != "available":
        return None
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        return None
    order = TOP_METRICS_ORDER if section_key == TOP_METRICS_SECTION else USER_ENGAGEMENT_ORDER
    cards = []
    for metric_key in order:
        if metric_key not in metrics:
            continue
        value = metrics.get(metric_key)
        if value is None:
            continue
        definition = METRIC_DEFINITIONS[metric_key]
        cards.append(
            {
                "key": DISPLAY_KEYS.get(metric_key, metric_key),
                "label": DISPLAY_LABELS[metric_key],
                "value": _format_metric(value, str(definition["value_type"])),
            }
        )
    return {"metrics": cards} if cards else None


def _validate_range_entry(
    item: Any,
    index: int,
    period_start: date,
    period_end: date,
    seen: set[tuple[str, date, date]],
) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] must be an object")
    range_key = item.get("range_key")
    if not isinstance(range_key, str) or not range_key:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].range_key is required")
    start = _parse_date(item.get("requested_start_date"), f"ranges[{index}].requested_start_date")
    end = _parse_date(item.get("requested_end_date"), f"ranges[{index}].requested_end_date")
    if start > end:
        raise ValueError(f"exact-range GA4 summary ranges[{index}] requested dates are inverted")
    if start < period_start or end > period_end:
        raise ValueError(f"exact-range GA4 summary ranges[{index}] must stay inside report period")
    identity = (range_key, start, end)
    if identity in seen:
        raise ValueError("duplicate exact-range GA4 summary identity")
    seen.add(identity)
    if item.get("inclusive_dates") is not True:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].inclusive_dates must be true")
    if item.get("calculation_version") not in GA4_EXACT_RANGE_SUMMARY_CALCULATION_VERSIONS:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].calculation_version is invalid")

    data_state = item.get("data_state")
    coverage_state = item.get("coverage_state")
    quality_state = item.get("quality_state")
    if data_state not in {"available", "empty", "partial", "unavailable"}:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].data_state is invalid")
    if coverage_state not in {"complete", "empty", "partial", "unavailable"}:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].coverage_state is invalid")
    if quality_state not in {"passed", "empty", "partial", "unavailable"}:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].quality_state is invalid")

    expected_days = (end - start).days + 1
    if item.get("expected_date_count") != expected_days:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].expected_date_count is inconsistent")
    actual_count = item.get("actual_date_count")
    if not isinstance(actual_count, int) or actual_count < 0 or actual_count > expected_days:
        raise ValueError(f"exact-range GA4 summary ranges[{index}].actual_date_count is invalid")
    if data_state == "available" and (coverage_state != "complete" or quality_state != "passed"):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] available state requires complete passed coverage")
    if data_state == "empty" and (coverage_state != "empty" or actual_count != expected_days):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] empty state contradicts coverage")
    if data_state == "partial" and (coverage_state != "partial" or actual_count >= expected_days):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] partial state contradicts coverage")
    if data_state == "unavailable" and coverage_state != "unavailable":
        raise ValueError(f"exact-range GA4 summary ranges[{index}] unavailable state contradicts coverage")

    metrics = item.get("metrics")
    if data_state == "unavailable":
        if metrics not in (None, {}):
            raise ValueError(f"exact-range GA4 summary ranges[{index}] unavailable state must not contain metrics")
        return
    if not isinstance(metrics, dict):
        raise ValueError(f"exact-range GA4 summary ranges[{index}].metrics must be an object")
    if data_state == "empty" and any(value not in (0, 0.0, None) for value in metrics.values()):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] empty state contains non-zero metrics")
    if data_state == "available":
        for metric_key in REQUIRED_AVAILABLE_METRICS:
            if metric_key not in metrics:
                raise ValueError(f"exact-range GA4 summary ranges[{index}] missing required metric {metric_key}")
    for metric_key, value in metrics.items():
        if metric_key not in METRIC_DEFINITIONS:
            raise ValueError(f"exact-range GA4 summary ranges[{index}] has unknown metric key")
        if value is None:
            continue
        _validate_metric_value(metric_key, value, index)


def _validate_metric_value(metric_key: str, value: Any, index: int) -> None:
    definition = METRIC_DEFINITIONS[metric_key]
    value_type = definition["value_type"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"exact-range GA4 summary ranges[{index}] metric value is invalid")
    if value < 0:
        raise ValueError(f"exact-range GA4 summary ranges[{index}] metric value must be non-negative")
    if value_type in {"integer", "duration_seconds"} and not float(value).is_integer():
        raise ValueError(f"exact-range GA4 summary ranges[{index}] metric value must be an integer")
    if value_type == "ratio" and value > 1:
        raise ValueError(f"exact-range GA4 summary ranges[{index}] ratio metric is out of range")


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _format_metric(value: Any, value_type: str) -> str:
    if value_type == "ratio":
        return f"{float(value) * 100:.2f}%"
    if value_type == "duration_seconds":
        return f"{int(round(float(value)))}s"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"
