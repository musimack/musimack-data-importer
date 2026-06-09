from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validate import validate_snapshot_payload


SCHEMA_VERSION = "dashboard_lab_provider_summary.v1"
SOURCE_MODE = "local_ga4_snapshot"
SOURCE_TYPE = "local_real"
PROVIDER = "ga4"
PROVIDER_KEY = "google_analytics"
SUMMARY_METRICS = [
    "users",
    "sessions",
    "views",
    "engagement_rate",
    "average_session_duration_seconds",
    "event_count",
    "conversions",
    "key_events",
]
FORBIDDEN_OUTPUT_TERMS = {
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "credential",
    "credentials",
    "authorization",
    "private_key",
    "api_key",
    "property_resource",
}


class Ga4DashboardSummaryError(ValueError):
    pass


def build_ga4_dashboard_summary(
    profile_slug: str,
    snapshot_payload: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_snapshot_payload(snapshot_payload)
    metrics = _metric_lookup(snapshot_payload.get("metrics", []))
    warnings = [str(item) for item in snapshot_payload.get("warnings", []) if str(item).strip()]

    summary_metrics: dict[str, int | float | None] = {}
    for name in SUMMARY_METRICS:
        summary_metrics[name] = metrics.get(name)
        if name not in metrics:
            warnings.append(f"GA4 snapshot did not include optional metric: {name}.")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "provider_key": PROVIDER_KEY,
        "fixture_profile": profile_slug,
        "source_mode": SOURCE_MODE,
        "source_type": SOURCE_TYPE,
        "real_data": True,
        "local_only": True,
        "mock_data": False,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "reporting_period": _reporting_period(snapshot_payload),
        "summary_metrics": summary_metrics,
        "time_series": _time_series(snapshot_payload.get("time_series", [])),
        "traffic_channels": _traffic_channels(snapshot_payload.get("dimension_rows", [])),
        "top_pages": _top_pages(snapshot_payload.get("dimension_rows", [])),
        "insights": _insights(snapshot_payload),
        "warnings": sorted(set(warnings)),
    }
    validate_ga4_dashboard_summary(payload, expected_profile_slug=profile_slug)
    return payload


def write_ga4_dashboard_summary(output_dir: Path, summary_payload: dict[str, Any]) -> Path:
    profile_slug = str(summary_payload.get("fixture_profile") or "")
    validate_ga4_dashboard_summary(summary_payload, expected_profile_slug=profile_slug or None)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ga4-summary.json"
    path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_ga4_dashboard_summary(
    payload: dict[str, Any],
    *,
    expected_profile_slug: str | None = None,
) -> None:
    if not isinstance(payload, dict):
        raise Ga4DashboardSummaryError("ga4-summary.json must contain a JSON object")
    _reject_secret_like(payload, "ga4-summary.json")
    _require_fields(
        payload,
        [
            "schema_version",
            "provider",
            "fixture_profile",
            "source_mode",
            "local_only",
            "mock_data",
            "reporting_period",
            "summary_metrics",
            "time_series",
            "traffic_channels",
            "top_pages",
            "warnings",
        ],
    )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise Ga4DashboardSummaryError("ga4-summary.json has unexpected schema_version")
    if payload.get("provider") != PROVIDER:
        raise Ga4DashboardSummaryError("ga4-summary.json provider must be ga4")
    if expected_profile_slug and payload.get("fixture_profile") != expected_profile_slug:
        raise Ga4DashboardSummaryError("ga4-summary.json fixture_profile mismatch")
    if payload.get("source_mode") != SOURCE_MODE:
        raise Ga4DashboardSummaryError("ga4-summary.json source_mode must be local_ga4_snapshot")
    if payload.get("local_only") is not True or payload.get("mock_data") is not False:
        raise Ga4DashboardSummaryError("ga4-summary.json must be local_only and non-mock")
    if "real_data" in payload and payload.get("real_data") is not True:
        raise Ga4DashboardSummaryError("ga4-summary.json real_data must be true when present")
    _validate_period(payload.get("reporting_period"))
    _validate_summary_metrics(payload.get("summary_metrics"))
    _validate_time_series(payload.get("time_series"))
    _validate_rows(payload.get("traffic_channels"), "traffic_channels", "channel")
    _validate_rows(payload.get("top_pages"), "top_pages", "label")


def real_output_dir(profile_slug: str) -> Path:
    return Path("exports") / "local-real" / "dashboard-lab" / profile_slug


def _reporting_period(snapshot_payload: dict[str, Any]) -> dict[str, str]:
    date_range = snapshot_payload.get("date_range")
    if not isinstance(date_range, dict):
        raise Ga4DashboardSummaryError("GA4 snapshot date_range is required")
    return {"start": str(date_range.get("start") or ""), "end": str(date_range.get("end") or "")}


def _metric_lookup(rows: Any) -> dict[str, int | float]:
    lookup: dict[str, int | float] = {}
    if not isinstance(rows, list):
        return lookup
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        value = _number_or_none(row.get("value"))
        if name and value is not None:
            lookup[name] = value
    return lookup


def _time_series(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        output: dict[str, Any] = {"date": str(row["date"])}
        for name in ("users", "sessions", "views", "event_count", "conversions", "key_events"):
            if name in row:
                output[name] = _number_or_none(row.get(name))
        normalized.append(output)
    return normalized


def _traffic_channels(rows: Any) -> list[dict[str, Any]]:
    output = []
    for row in _dimension_rows(rows, "traffic_channels"):
        metrics = _metric_lookup(row.get("metrics", []))
        output.append(
            {
                "channel": str(row.get("label") or "Unassigned"),
                "sessions": metrics.get("sessions"),
                "users": metrics.get("users"),
                "views": metrics.get("views"),
                "engagement_rate": metrics.get("engagement_rate"),
                "key_events": metrics.get("key_events"),
                "conversions": metrics.get("conversions"),
            }
        )
    return output


def _top_pages(rows: Any) -> list[dict[str, Any]]:
    output = []
    for row in _dimension_rows(rows, "top_pages"):
        metrics = _metric_lookup(row.get("metrics", []))
        label = str(row.get("label") or "")
        title, path = _split_page_label(label)
        output.append(
            {
                "label": label,
                "title": title,
                "path": path,
                "views": metrics.get("views"),
                "users": metrics.get("users"),
                "event_count": metrics.get("event_count"),
                "average_session_duration_seconds": metrics.get("average_session_duration_seconds"),
                "conversions": metrics.get("conversions"),
            }
        )
    return output


def _dimension_rows(rows: Any, kind: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("kind") == kind]


def _insights(snapshot_payload: dict[str, Any]) -> list[str]:
    channels = _traffic_channels(snapshot_payload.get("dimension_rows", []))
    pages = _top_pages(snapshot_payload.get("dimension_rows", []))
    insights = []
    if channels:
        top_channel = max(channels, key=lambda item: float(item.get("sessions") or 0))
        insights.append(f"Top GA4 traffic channel by sessions: {top_channel['channel']}.")
    if pages:
        top_page = max(pages, key=lambda item: float(item.get("views") or 0))
        insights.append(f"Top GA4 page by views: {top_page['path'] or top_page['title'] or top_page['label']}.")
    if not insights:
        insights.append("GA4 snapshot converted for dashboard-lab display; detailed channel or page rows were not available.")
    return insights


def _split_page_label(label: str) -> tuple[str, str]:
    if label.endswith(")") and " (" in label:
        title, raw_path = label.rsplit(" (", 1)
        return title, raw_path[:-1]
    return label, ""


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return None
    if not math.isfinite(number):
        return None
    rounded = round(number, 6)
    if abs(rounded - round(rounded)) < 0.000001:
        return int(round(rounded))
    return rounded


def _validate_period(value: Any) -> None:
    if not isinstance(value, dict) or not value.get("start") or not value.get("end"):
        raise Ga4DashboardSummaryError("ga4-summary.json reporting_period is required")


def _validate_summary_metrics(value: Any) -> None:
    if not isinstance(value, dict):
        raise Ga4DashboardSummaryError("ga4-summary.json summary_metrics must be an object")
    for name in SUMMARY_METRICS:
        if name not in value:
            raise Ga4DashboardSummaryError(f"ga4-summary.json summary_metrics missing {name}")
        if value[name] is not None and not isinstance(value[name], (int, float)):
            raise Ga4DashboardSummaryError(f"ga4-summary.json summary_metrics {name} must be a number or null")


def _validate_time_series(value: Any) -> None:
    if not isinstance(value, list):
        raise Ga4DashboardSummaryError("ga4-summary.json time_series must be an array")
    for row in value:
        if not isinstance(row, dict) or not row.get("date"):
            raise Ga4DashboardSummaryError("ga4-summary.json time_series rows need a date")
        for key, nested in row.items():
            if key != "date" and nested is not None and not isinstance(nested, (int, float)):
                raise Ga4DashboardSummaryError("ga4-summary.json time_series metrics must be numbers or null")


def _validate_rows(value: Any, field: str, label_key: str) -> None:
    if not isinstance(value, list):
        raise Ga4DashboardSummaryError(f"ga4-summary.json {field} must be an array")
    for row in value:
        if not isinstance(row, dict) or label_key not in row:
            raise Ga4DashboardSummaryError(f"ga4-summary.json {field} rows need {label_key}")
        for key, nested in row.items():
            if key in {"channel", "label", "title", "path"}:
                continue
            if nested is not None and not isinstance(nested, (int, float)):
                raise Ga4DashboardSummaryError(f"ga4-summary.json {field} metrics must be numbers or null")


def _require_fields(payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise Ga4DashboardSummaryError(f"ga4-summary.json missing required fields: {', '.join(missing)}")


def _reject_secret_like(value: Any, filename: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
            if any(term in normalized_key for term in FORBIDDEN_OUTPUT_TERMS):
                raise Ga4DashboardSummaryError(f"{filename} contains forbidden provider/internal key: {key}")
            _reject_secret_like(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_like(item, filename)
    elif isinstance(value, str):
        normalized = value.lower().replace("-", "_").replace(" ", "_")
        if any(term in normalized for term in FORBIDDEN_OUTPUT_TERMS):
            raise Ga4DashboardSummaryError(f"{filename} contains forbidden provider/internal text")
