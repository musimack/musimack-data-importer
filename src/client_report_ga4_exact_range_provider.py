from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Protocol

from src.client_report_ga4_exact_ranges import (
    GA4_EXACT_RANGE_SUMMARY_DATA_SCOPE,
    GA4_EXACT_RANGE_SUMMARY_PROVIDER_CALCULATION_VERSION,
    GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE,
    GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
    METRIC_DEFINITIONS,
    REQUIRED_AVAILABLE_METRICS,
    metric_definitions_payload,
    validate_ga4_exact_range_summary_contract,
)
from src.client_report_presentation_ranges import resolve_range_key
from src.config import DateRange
from src.ga4_client import (
    GA4_EXACT_RANGE_SUMMARY_METRICS,
    GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS,
    Ga4ClientError,
)


EXACT_RANGE_KEYS = ("last_7_days", "last_30_days", "this_month", "last_month")
QUERY_SHAPE_ID = "ga4_data_api_exact_range_summary.dimensionless.v1"


class ExactRangeGa4Client(Protocol):
    def run_exact_range_summary(
        self,
        date_range: DateRange,
        *,
        metric_names: tuple[str, ...] = GA4_EXACT_RANGE_SUMMARY_METRICS,
    ) -> dict[str, Any]:
        ...


def build_ga4_exact_range_summary_from_provider(
    *,
    client: ExactRangeGa4Client,
    profile: str,
    report_period_start: date,
    report_period_end: date,
    timezone: str = "America/Los_Angeles",
    generated_at: str | None = None,
) -> dict[str, Any]:
    if report_period_start > report_period_end:
        raise ValueError("report_period_start must be on or before report_period_end")
    generated = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ranges = []
    query_notes: list[str] = []
    for range_key in EXACT_RANGE_KEYS:
        resolved = resolve_range_key(range_key, report_period_end)
        if resolved.start_date < report_period_start or resolved.end_date > report_period_end:
            raise ValueError(f"{range_key} must stay inside the report period")
        entry, notes = _range_entry(client=client, profile=profile, range_key=range_key, date_range=DateRange(resolved.start_date, resolved.end_date))
        ranges.append(entry)
        query_notes.extend(notes)

    payload = {
        "schema_version": GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
        "provider": "ga4",
        "report_type": GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE,
        "data_scope": GA4_EXACT_RANGE_SUMMARY_DATA_SCOPE,
        "dataset_version": GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
        "client_slug": profile,
        "report_period": {
            "start_date": report_period_start.isoformat(),
            "end_date": report_period_end.isoformat(),
        },
        "timezone": timezone,
        "inclusive_dates": True,
        "calculation_version": GA4_EXACT_RANGE_SUMMARY_PROVIDER_CALCULATION_VERSION,
        "generated_at": generated,
        "source_identity": {
            "source_kind": "ga4_data_api",
            "source_label": "GA4 Data API exact-range summary",
            "profile": profile,
        },
        "query_identity": {
            "shape_id": QUERY_SHAPE_ID,
            "metric_names": list(GA4_EXACT_RANGE_SUMMARY_METRICS),
            "required_metric_names": list(GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS),
            "fallback_policy": "retry_required_metrics_only_if_optional_metric_query_fails",
        },
        "metric_definitions": metric_definitions_payload(),
        "ranges": ranges,
    }
    if query_notes:
        payload["quality_notes"] = sorted(set(query_notes))
    validate_ga4_exact_range_summary_contract(payload)
    return payload


def _range_entry(
    *,
    client: ExactRangeGa4Client,
    profile: str,
    range_key: str,
    date_range: DateRange,
) -> tuple[dict[str, Any], list[str]]:
    notes = [
        "Queried GA4 Data API as a range-level summary row; values are not clipped or summed from report-period totals."
    ]
    response = None
    metric_names = GA4_EXACT_RANGE_SUMMARY_METRICS
    try:
        response = client.run_exact_range_summary(date_range, metric_names=metric_names)
    except Ga4ClientError as primary_exc:
        try:
            metric_names = GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS
            response = client.run_exact_range_summary(date_range, metric_names=metric_names)
            notes.append(f"Optional GA4 metrics omitted after safe retry: {_safe_failure_note(primary_exc)}")
        except Ga4ClientError as fallback_exc:
            raise Ga4ClientError(
                "exact-range GA4 summary failed safely; full metric query failed and required metric retry failed"
            ) from fallback_exc

    metrics = _metrics_from_run_report_response(response, metric_names=metric_names)
    expected_days = (date_range.end - date_range.start).days + 1
    required_values = [_number(metrics.get(key)) for key in REQUIRED_AVAILABLE_METRICS]
    if all(value == 0 for value in required_values):
        data_state = "empty"
        coverage_state = "empty"
        quality_state = "empty"
    else:
        data_state = "available"
        coverage_state = "complete"
        quality_state = "passed"
    return (
        {
            "range_key": range_key,
            "requested_start_date": date_range.start.isoformat(),
            "requested_end_date": date_range.end.isoformat(),
            "inclusive_dates": True,
            "data_state": data_state,
            "coverage_state": coverage_state,
            "quality_state": quality_state,
            "expected_date_count": expected_days,
            "actual_date_count": expected_days,
            "metrics": metrics,
            "calculation_version": GA4_EXACT_RANGE_SUMMARY_PROVIDER_CALCULATION_VERSION,
            "source_identity": f"{profile}:{range_key}:{date_range.start.isoformat()}:{date_range.end.isoformat()}:ga4_data_api_exact_range_summary",
            "quality_notes": notes,
        },
        notes,
    )


def _metrics_from_run_report_response(response: dict[str, Any], *, metric_names: tuple[str, ...]) -> dict[str, int | float]:
    headers = response.get("metricHeaders")
    if not isinstance(headers, list):
        raise ValueError("GA4 exact-range summary response is missing metricHeaders")
    names = [str(header.get("name") or "") for header in headers if isinstance(header, dict)]
    rows = response.get("rows") or []
    if not rows:
        return {_contract_key_for_provider_metric(name): 0 for name in names if _contract_key_for_provider_metric(name)}
    row = rows[0]
    if not isinstance(row, dict):
        raise ValueError("GA4 exact-range summary response row is invalid")
    values = row.get("metricValues")
    if not isinstance(values, list):
        raise ValueError("GA4 exact-range summary response row is missing metricValues")
    parsed: dict[str, int | float] = {}
    for index, metric_name in enumerate(names):
        if metric_name not in metric_names:
            continue
        key = _contract_key_for_provider_metric(metric_name)
        if not key or index >= len(values):
            continue
        raw_value = values[index].get("value") if isinstance(values[index], dict) else None
        parsed[key] = _coerce_metric_value(key, raw_value)
    for required in REQUIRED_AVAILABLE_METRICS:
        if required not in parsed:
            raise ValueError(f"GA4 exact-range summary response is missing required metric {required}")
    return parsed


def _contract_key_for_provider_metric(metric_name: str) -> str | None:
    for key, definition in METRIC_DEFINITIONS.items():
        if definition.get("provider_metric_name") == metric_name:
            return key
    return None


def _coerce_metric_value(metric_key: str, value: Any) -> int | float:
    try:
        number = float(str(value or "0"))
    except ValueError as exc:
        raise ValueError(f"GA4 exact-range summary metric {metric_key} is not numeric") from exc
    value_type = METRIC_DEFINITIONS[metric_key]["value_type"]
    if value_type in {"integer", "duration_seconds"}:
        return int(round(number))
    return round(number, 6)


def _number(value: Any) -> int | float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return 0


def _safe_failure_note(exc: Exception) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ").strip()
    if len(text) > 180:
        text = text[:177] + "..."
    return text
