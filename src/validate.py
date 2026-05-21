from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

FORBIDDEN_TERMS = [
    "credential",
    "credentials_ref",
    "token",
    "secret",
    "encrypted",
    "refresh",
    "access_token",
    "id_token",
    "api_key",
    "private_key",
    "authorization",
    "raw_provider",
    "google_response",
    "stack_trace",
]


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotInspection:
    schema_version: str | None
    provider: str | None
    provider_key: str | None
    period_start: str | None
    period_end: str | None
    metric_count: int
    trend_point_count: int
    channel_row_count: int
    top_page_row_count: int
    dimension_row_count: int
    warning_count: int

    def lines(self) -> list[str]:
        return [
            f"schema/version: {self.schema_version}",
            f"provider/provider_key: {self.provider}/{self.provider_key}",
            f"date range: {self.period_start} through {self.period_end}",
            f"metrics: {self.metric_count}",
            f"daily trend points: {self.trend_point_count}",
            f"traffic channel rows: {self.channel_row_count}",
            f"top page rows: {self.top_page_row_count}",
            f"total dimension rows: {self.dimension_row_count}",
            f"warnings: {self.warning_count}",
        ]


def validate_snapshot_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("snapshot payload must be a JSON object")
    reject_secret_like_fields(payload)
    _expect(payload, "schema_version", "ga4_snapshot.v1")
    _expect(payload, "provider", "ga4")
    _expect(payload, "provider_key", "google_analytics")
    _expect(payload, "report_type", "traffic_overview")
    _validate_property(payload.get("property_resource"))
    _validate_date_range(payload.get("date_range"))
    _validate_metrics(payload.get("metrics"))
    _validate_dimension_rows(payload.get("dimension_rows"))
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValidationError("summary is required")


def reject_secret_like_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if _contains_forbidden(str(key)):
                raise ValidationError("snapshot contains unsafe secret-like fields")
            reject_secret_like_fields(nested)
    elif isinstance(value, list):
        for item in value:
            reject_secret_like_fields(item)
    elif isinstance(value, str) and _contains_forbidden(value):
        raise ValidationError("snapshot contains unsafe secret-like text")


def safe_summary(payload: dict[str, Any]) -> dict[str, Any]:
    inspection = inspect_snapshot_payload(payload)
    return {
        "schema_version": inspection.schema_version,
        "report_type": payload.get("report_type"),
        "period_start": inspection.period_start,
        "period_end": inspection.period_end,
        "metric_count": inspection.metric_count,
        "dimension_row_count": inspection.dimension_row_count,
        "time_series_count": inspection.trend_point_count,
        "channel_row_count": inspection.channel_row_count,
        "top_page_row_count": inspection.top_page_row_count,
        "warning_count": inspection.warning_count,
    }


def inspect_snapshot_payload(payload: dict[str, Any]) -> SnapshotInspection:
    validate_snapshot_payload(payload)
    rows = payload.get("dimension_rows", [])
    return SnapshotInspection(
        schema_version=payload.get("schema_version"),
        provider=payload.get("provider"),
        provider_key=payload.get("provider_key"),
        period_start=payload.get("date_range", {}).get("start"),
        period_end=payload.get("date_range", {}).get("end"),
        metric_count=len(payload.get("metrics", [])),
        trend_point_count=len(payload.get("time_series", [])),
        channel_row_count=sum(1 for row in rows if row.get("kind") == "traffic_channels"),
        top_page_row_count=sum(1 for row in rows if row.get("kind") == "top_pages"),
        dimension_row_count=len(rows),
        warning_count=len(payload.get("warnings", [])),
    )


def _expect(payload: dict[str, Any], key: str, expected: str) -> None:
    if payload.get(key) != expected:
        raise ValidationError(f"{key} must be {expected}")


def _validate_property(value: Any) -> None:
    if not isinstance(value, str) or not value.startswith("properties/"):
        raise ValidationError("property_resource must use properties/{id} format")
    property_id = value.removeprefix("properties/")
    if not property_id.isdigit():
        raise ValidationError("property_resource must use properties/{id} format")


def _validate_date_range(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValidationError("date_range is required")
    try:
        start = date.fromisoformat(value["start"])
        end = date.fromisoformat(value["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("date_range dates must use YYYY-MM-DD format") from exc
    if end < start:
        raise ValidationError("date_range end cannot be before start")


def _validate_metrics(value: Any) -> None:
    if not isinstance(value, list):
        raise ValidationError("metrics must be an array")
    for metric in value:
        if not isinstance(metric, dict):
            raise ValidationError("metric rows must be objects")
        if not metric.get("name") or not metric.get("unit"):
            raise ValidationError("metric name and unit are required")
        number = metric.get("value")
        if not isinstance(number, (int, float)) or number != number:
            raise ValidationError("metric value must be finite")


def _validate_dimension_rows(value: Any) -> None:
    if not isinstance(value, list):
        raise ValidationError("dimension_rows must be an array")
    for row in value:
        if not isinstance(row, dict) or not row.get("label"):
            raise ValidationError("dimension row label is required")
        _validate_metrics(row.get("metrics"))


def _contains_forbidden(value: str) -> bool:
    normalized = value.lower().replace("-", "_").replace(" ", "_")
    return any(term in normalized for term in FORBIDDEN_TERMS)
