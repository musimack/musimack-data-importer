from __future__ import annotations

import hashlib
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
from src.client_report_presentation_ranges import CANONICAL_RANGE_KEYS, resolve_range_key
from src.range_containment import is_contained, unavailable_range_entry
from src.config import DateRange
from src.ga4_client import (
    GA4_EXACT_RANGE_SUMMARY_METRICS,
    GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS,
    Ga4ClientError,
)


EXACT_RANGE_KEYS = CANONICAL_RANGE_KEYS
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
    existing_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if report_period_start > report_period_end:
        raise ValueError("report_period_start must be on or before report_period_end")
    generated = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ranges = []
    query_notes: list[str] = []
    provider_calls = 0
    reused_ranges = 0
    existing = _reusable_entries(existing_payload, profile, report_period_start, report_period_end)
    resolved_ranges = [resolve_range_key(key, report_period_end) for key in EXACT_RANGE_KEYS]
    for resolved in resolved_ranges:
        range_key = resolved.range_key
        if not is_contained(
            resolved.start_date, resolved.end_date, report_period_start, report_period_end
        ):
            # Truthful absence, not a failure. The canonical key is kept, the
            # range is marked unavailable with a governed reason, and no
            # provider request is issued for it.
            ranges.append(
                unavailable_range_entry(range_key, resolved.start_date, resolved.end_date)
            )
            continue
        identity = (range_key, resolved.start_date.isoformat(), resolved.end_date.isoformat())
        if identity in existing:
            reused = dict(existing[identity])
            reused["query_fingerprint"] = _query_fingerprint(
                range_key, DateRange(resolved.start_date, resolved.end_date)
            )
            ranges.append(reused)
            reused_ranges += 1
            continue
        entry, notes, calls = _range_entry(client=client, profile=profile, range_key=range_key, date_range=DateRange(resolved.start_date, resolved.end_date))
        ranges.append(entry)
        query_notes.extend(notes)
        provider_calls += calls

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
        "generation_metadata": {
            "provider_calls": provider_calls,
            "reused_ranges": reused_ranges,
            "requested_ranges": len(resolved_ranges),
        },
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
    metric_names: tuple[str, ...] = GA4_EXACT_RANGE_SUMMARY_METRICS,
) -> tuple[dict[str, Any], list[str], int]:
    notes = [
        "Queried GA4 Data API as a range-level summary row; values are not clipped or summed from report-period totals."
    ]
    response = None
    provider_calls = 0
    try:
        provider_calls += 1
        response = client.run_exact_range_summary(date_range, metric_names=metric_names)
    except Ga4ClientError as primary_exc:
        # The fallback narrows metric coverage from nine metrics to four, so it
        # must never be a catch-all. A malformed request is a defect to fix, not
        # a condition to degrade around: the duplicate-metric error previously
        # triggered this path on every range and silently dropped seven display
        # fields. Only the governed classes below may degrade.
        if not _is_degradable_provider_error(primary_exc):
            raise
        try:
            metric_names = GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS
            provider_calls += 1
            response = client.run_exact_range_summary(date_range, metric_names=metric_names)
            notes.append(
                "DEGRADED: optional GA4 metrics omitted after a governed safe retry; "
                f"metric coverage is incomplete: {_safe_failure_note(primary_exc)}"
            )
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
            "query_fingerprint": _query_fingerprint(range_key, date_range),
            "quality_notes": notes,
        },
        notes,
        provider_calls,
    )


def _reusable_entries(
    payload: dict[str, Any] | None,
    profile: str,
    report_start: date,
    report_end: date,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    validate_ga4_exact_range_summary_contract(payload)
    if payload.get("client_slug") != profile or payload.get("report_period") != {
        "start_date": report_start.isoformat(),
        "end_date": report_end.isoformat(),
    }:
        raise ValueError("existing GA4 exact-range summary does not match the requested profile/report period")
    # Reuse must never carry a degraded entry forward. Identity alone is not
    # sufficient: an entry produced by the retired duplicate-metric fallback has
    # the right range_key and dates but only four of nine metrics, so reusing it
    # would silently reintroduce the exact defect the guard exists to stop.
    # Degraded entries are dropped here, which forces a fresh provider call.
    # Allowlisted rather than denylisted: only states known to be safe are
    # reused. A degraded, failed, unknown, or status-less entry is dropped, so a
    # future source shape cannot be reused merely because it is not recognizably
    # bad.
    from src.source_package_state import ELIGIBLE_STATES, classify_range_entry

    return {
        (entry["range_key"], entry["requested_start_date"], entry["requested_end_date"]): entry
        for entry in payload["ranges"]
        if classify_range_entry(entry) in ELIGIBLE_STATES
    }


def _query_fingerprint(range_key: str, date_range: DateRange) -> str:
    material = f"{QUERY_SHAPE_ID}:{range_key}:{date_range.start.isoformat()}:{date_range.end.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()


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


# Provider conditions that may legitimately degrade metric coverage. A property
# can genuinely lack an optional metric, and that is worth a reduced answer. A
# malformed request is not: it is a defect, and degrading around it hides the
# defect while silently reducing what every client sees.
DEGRADABLE_ERROR_MARKERS = (
    "metric not found",
    "did not have any value",
    "is not compatible",
    "incompatible",
    "user does not have sufficient permissions for this metric",
)

# Never degraded. These indicate a request this repository constructed wrongly.
#
# Deliberately narrow. `INVALID_ARGUMENT` is *not* listed: GA4 returns that
# status for both malformed requests and genuine property limitations, so
# treating the status itself as non-degradable would block the legitimate
# incompatible-metric case too. Only the specific defect signature is refused.
NON_DEGRADABLE_ERROR_MARKERS = (
    "duplicate metric",
    "duplicate metrics",
)


def _is_degradable_provider_error(exc: Exception) -> bool:
    """May this provider error reduce metric coverage?

    Deliberately allowlist-driven and defect-hostile. An unrecognized error is
    **not** degradable, so an unexpected condition surfaces as a failure rather
    than as quietly thinner data.
    """
    text = str(exc).lower()
    if any(marker in text for marker in NON_DEGRADABLE_ERROR_MARKERS):
        return False
    return any(marker in text for marker in DEGRADABLE_ERROR_MARKERS)
