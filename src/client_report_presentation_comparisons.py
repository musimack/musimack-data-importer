from __future__ import annotations

import hashlib
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.client_report_presentation_ranges import CANONICAL_SECTION_KEYS, ResolvedRange, _add_months


COMPARISON_SCHEMA_VERSION = "client_report_presentation_comparisons.v1"
COMPARISON_CONTRACT_VERSION = 1
COMPARISON_DATASET_VERSION = "presentation_comparisons.v1"
COMPARISON_TIMEZONE = "America/Los_Angeles"
COMPARISON_PRESET_KEYS = (
    "report_period",
    "last_3_days",
    "last_7_days",
    "last_14_days",
    "last_30_days",
    "last_60_days",
    "last_90_days",
    "last_6_months",
    "last_12_months",
    "year_to_date",
    "this_month",
    "last_month",
)
DATA_STATES = {"complete", "partial", "empty", "unavailable"}
COVERAGE_STATES = {"complete", "partial", "empty", "unavailable"}
METRIC_UNITS = {"count", "rate", "average_position"}

# Runaway guard for ranked stable identities. The portal imposes no length
# limit of its own; this exists only to refuse an unbounded payload, and sits
# far above any real GA4 path-plus-title or GSC URL value.
RANKED_IDENTITY_MAX_LENGTH = 2048


def resolve_comparison_ranges(
    preset_key: str,
    *,
    report_start: date,
    report_end: date,
) -> tuple[ResolvedRange, ResolvedRange]:
    if report_start > report_end:
        raise ValueError("report_start must be on or before report_end")
    if preset_key == "report_period":
        current = ResolvedRange(preset_key, report_start, report_end)
        days = (report_end - report_start).days + 1
        prior_end = report_start - timedelta(days=1)
        return current, ResolvedRange(preset_key, prior_end - timedelta(days=days - 1), prior_end)
    if preset_key in {"last_3_days", "last_7_days", "last_14_days", "last_30_days", "last_60_days", "last_90_days"}:
        days = int(preset_key.split("_")[1])
        current = ResolvedRange(preset_key, report_end - timedelta(days=days - 1), report_end)
        prior_end = current.start_date - timedelta(days=1)
        return current, ResolvedRange(preset_key, prior_end - timedelta(days=days - 1), prior_end)
    if preset_key in {"last_6_months", "last_12_months"}:
        months = 6 if preset_key == "last_6_months" else 12
        current = ResolvedRange(preset_key, _add_months(report_end, -months) + timedelta(days=1), report_end)
        prior_end = current.start_date - timedelta(days=1)
        prior_start = _add_months(prior_end, -months) + timedelta(days=1)
        return current, ResolvedRange(preset_key, prior_start, prior_end)
    if preset_key == "year_to_date":
        current = ResolvedRange(preset_key, report_end.replace(month=1, day=1), report_end)
        prior_end = _clamped_replace_year(report_end, report_end.year - 1)
        return current, ResolvedRange(preset_key, prior_end.replace(month=1, day=1), prior_end)
    if preset_key == "this_month":
        current = ResolvedRange(preset_key, report_end.replace(day=1), report_end)
        prior_month_end = current.start_date - timedelta(days=1)
        prior_end = prior_month_end.replace(day=min(report_end.day, prior_month_end.day))
        return current, ResolvedRange(preset_key, prior_end.replace(day=1), prior_end)
    if preset_key == "last_month":
        current_end = report_end.replace(day=1) - timedelta(days=1)
        current = ResolvedRange(preset_key, current_end.replace(day=1), current_end)
        prior_end = current.start_date - timedelta(days=1)
        return current, ResolvedRange(preset_key, prior_end.replace(day=1), prior_end)
    raise ValueError(f"unsupported comparison preset: {preset_key}")


def enumerate_comparison_ranges(*, report_start: date, report_end: date) -> list[dict[str, str]]:
    return [
        {
            "preset_key": key,
            "current_start_date": current.start_date.isoformat(),
            "current_end_date": current.end_date.isoformat(),
            "comparison_start_date": prior.start_date.isoformat(),
            "comparison_end_date": prior.end_date.isoformat(),
        }
        for key in COMPARISON_PRESET_KEYS
        for current, prior in [resolve_comparison_ranges(key, report_start=report_start, report_end=report_end)]
    ]


def build_presentation_comparison_package(
    *,
    report_id: str,
    client_id: str,
    project_id: str,
    client_slug: str,
    report_start: date,
    report_end: date,
    comparisons: list[dict[str, Any]],
    source_identity: dict[str, Any],
    timezone: str = COMPARISON_TIMEZONE,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    package = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "contract_identifier": COMPARISON_SCHEMA_VERSION,
        "contract_version": COMPARISON_CONTRACT_VERSION,
        "provider": "presentation",
        "report_type": "comparison_dataset",
        "dataset_version": f"{client_slug}:{report_id}:{report_end.isoformat()}:{COMPARISON_DATASET_VERSION}",
        "report_id": report_id,
        "client_id": client_id,
        "project_id": project_id,
        "client_slug": client_slug,
        "report_period": {"start_date": report_start.isoformat(), "end_date": report_end.isoformat()},
        "timezone": timezone,
        "inclusive_dates": True,
        "generated_at": generated,
        "source_identity": source_identity,
        "range_manifest": enumerate_comparison_ranges(report_start=report_start, report_end=report_end),
        "comparisons": comparisons,
    }
    validate_presentation_comparison_package(package)
    return package


def build_metric_comparison(
    *, key: str, label: str, unit: str, current_value: int | float | None, prior_value: int | float | None
) -> dict[str, Any]:
    if unit not in METRIC_UNITS:
        raise ValueError("comparison metric unit is unsupported")
    result: dict[str, Any] = {
        "key": key,
        "label": label,
        "unit": unit,
        "current_value": current_value,
        "prior_value": prior_value,
        "absolute_change": None,
        "relative_change_percent": None,
        "percentage_point_change": None,
        "change_state": "not_comparable",
        "direction": "lower_is_better" if unit == "average_position" else "neutral",
    }
    if current_value is None or prior_value is None or not _finite_number(current_value) or not _finite_number(prior_value):
        return result
    current = float(current_value)
    prior = float(prior_value)
    change = current - prior
    result["absolute_change"] = round(change, 6)
    if unit == "rate":
        result["percentage_point_change"] = round(change * 100, 2)
        result["change_state"] = "no_change" if change == 0 else "increase" if change > 0 else "decrease"
    elif unit == "average_position":
        result["change_state"] = "no_change" if change == 0 else "improved" if change < 0 else "declined"
    elif prior == 0:
        result["change_state"] = "no_change" if current == 0 else "new"
    else:
        result["relative_change_percent"] = round((change / prior) * 100, 2)
        result["change_state"] = "no_change" if change == 0 else "increase" if change > 0 else "decrease"
    return result


def match_ranked_rows(
    *,
    current_rows: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
    identity_key: str,
    metric_definitions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    current_by_id = _unique_ranked_rows(current_rows, identity_key, "current")
    prior_by_id = _unique_ranked_rows(prior_rows, identity_key, "comparison")
    matched = []
    for identity, current in current_by_id.items():
        prior = prior_by_id.get(identity)
        current_rank = _positive_int(current.get("rank"), "current rank")
        prior_rank = _positive_int(prior.get("rank"), "prior rank") if prior else None
        metric_results = []
        for definition in metric_definitions:
            key = definition["key"]
            metric_results.append(
                build_metric_comparison(
                    key=key,
                    label=definition["label"],
                    unit=definition["unit"],
                    current_value=_metric_value(current, key),
                    prior_value=_metric_value(prior, key) if prior else None,
                )
            )
        matched.append(
            {
                "stable_identity": identity,
                "label": str(current.get("label") or identity),
                "current_rank": current_rank,
                "prior_rank": prior_rank,
                "rank_movement": None if prior_rank is None else prior_rank - current_rank,
                "new_row": prior is None,
                "metrics": metric_results,
            }
        )
    return matched


def align_trend_series(
    *, current_series: list[dict[str, Any]], comparison_series: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    prior_by_key = _unique_series(comparison_series, "comparison")
    output = []
    for current in current_series:
        key = _required_text(current.get("key"), "current trend key")
        prior = prior_by_key.get(key)
        current_points = _trend_points(current.get("points"), "current")
        prior_points = _trend_points(prior.get("points"), "comparison") if prior else []
        output.append(
            {
                "key": key,
                "label": _required_text(current.get("label") or key, "trend label"),
                "unit": _required_text(current.get("unit") or current.get("value_kind") or "count", "trend unit"),
                "current_points": [dict(point, day_index=index + 1) for index, point in enumerate(current_points)],
                "comparison_points": [dict(point, day_index=index + 1) for index, point in enumerate(prior_points)],
            }
        )
    return output


def validate_presentation_comparison_package(package: dict[str, Any]) -> None:
    if package.get("schema_version") != COMPARISON_SCHEMA_VERSION or package.get("contract_identifier") != COMPARISON_SCHEMA_VERSION:
        raise ValueError("comparison contract identifier is unsupported")
    if package.get("contract_version") != COMPARISON_CONTRACT_VERSION:
        raise ValueError("comparison contract version is unsupported")
    for key in ("report_id", "client_id", "project_id", "client_slug", "dataset_version"):
        _required_text(package.get(key), key)
    period = package.get("report_period")
    if not isinstance(period, dict):
        raise ValueError("comparison report_period is required")
    report_start = _date(period.get("start_date"), "report_period.start_date")
    report_end = _date(period.get("end_date"), "report_period.end_date")
    if report_start > report_end:
        raise ValueError("comparison report period is invalid")
    if package.get("timezone") != COMPARISON_TIMEZONE or package.get("inclusive_dates") is not True:
        raise ValueError("comparison timezone or inclusive-date semantics are invalid")
    if not isinstance(package.get("source_identity"), dict):
        raise ValueError("comparison source_identity is required")
    manifest = package.get("range_manifest")
    expected = enumerate_comparison_ranges(report_start=report_start, report_end=report_end)
    if manifest != expected:
        raise ValueError("comparison range_manifest does not match governed preset definitions")
    comparisons = package.get("comparisons")
    if not isinstance(comparisons, list) or len(comparisons) > len(CANONICAL_SECTION_KEYS) * len(COMPARISON_PRESET_KEYS):
        raise ValueError("comparison entries are missing or too large")
    seen: set[tuple[str, str]] = set()
    for entry in comparisons:
        _validate_comparison_entry(entry, package, expected, seen)


def _validate_comparison_entry(
    entry: Any,
    package: dict[str, Any],
    manifest: list[dict[str, str]],
    seen: set[tuple[str, str]],
) -> None:
    if not isinstance(entry, dict):
        raise ValueError("comparison entry must be an object")
    section_key = entry.get("section_key")
    preset_key = entry.get("preset_key")
    if section_key not in CANONICAL_SECTION_KEYS or preset_key not in COMPARISON_PRESET_KEYS:
        raise ValueError("comparison section or preset is unsupported")
    identity = (section_key, preset_key)
    if identity in seen:
        raise ValueError("duplicate comparison section/preset identity")
    seen.add(identity)
    if entry.get("report_id") != package["report_id"] or entry.get("client_id") != package["client_id"] or entry.get("project_id") != package["project_id"]:
        raise ValueError("comparison entry identity does not match package")
    governed = next(item for item in manifest if item["preset_key"] == preset_key)
    current = _validate_period_state(entry.get("current"), "current")
    prior = _validate_period_state(entry.get("comparison"), "comparison")
    if (current[0], current[1], prior[0], prior[1]) != (
        governed["current_start_date"], governed["current_end_date"],
        governed["comparison_start_date"], governed["comparison_end_date"],
    ):
        raise ValueError("comparison entry requested ranges do not match governed definition")
    eligible = entry.get("delta_eligible")
    if not isinstance(eligible, bool):
        raise ValueError("comparison delta_eligible must be boolean")
    if eligible and not (
        (current[2] in {"complete", "empty"} and prior[2] in {"complete", "empty"})
        or (current[2] == "partial" and prior[2] == "partial")
    ):
        raise ValueError("comparison deltas require equivalent exact or partial coverage")
    if not eligible and not _required_text(entry.get("delta_ineligible_reason"), "delta_ineligible_reason"):
        raise ValueError("ineligible comparison requires a reason")
    for lineage_key in ("current_lineage", "comparison_lineage"):
        lineage = entry.get(lineage_key)
        if not isinstance(lineage, dict):
            raise ValueError("comparison lineage is required")
        for key in ("source_contract", "dataset_version", "source_identity"):
            _required_text(lineage.get(key), f"{lineage_key}.{key}")
        fingerprint = lineage.get("query_fingerprint")
        if fingerprint is not None:
            _required_text(fingerprint, f"{lineage_key}.query_fingerprint")
    metrics = entry.get("metrics", [])
    ranked = entry.get("ranked_rows", [])
    trends = entry.get("trend_series", [])
    if not all(isinstance(value, list) for value in (metrics, ranked, trends)):
        raise ValueError("comparison display collections must be arrays")
    _validate_metric_results(metrics)
    stable_ids = set()
    for row in ranked:
        if not isinstance(row, dict):
            raise ValueError("comparison ranked row must be an object")
        stable_id = _required_identity_text(row.get("stable_identity"), "stable ranked identity")
        if stable_id in stable_ids:
            raise ValueError("duplicate ranked stable identity")
        stable_ids.add(stable_id)
        _positive_int(row.get("current_rank"), "current rank")
        if row.get("new_row") is True and row.get("prior_rank") is not None:
            raise ValueError("new ranked row cannot carry a prior rank")
        if row.get("prior_rank") is not None:
            _positive_int(row.get("prior_rank"), "prior rank")
        _validate_metric_results(row.get("metrics"))
    for series in trends:
        if not isinstance(series, dict):
            raise ValueError("comparison trend series must be an object")
        _required_text(series.get("key"), "trend key")
        for side in ("current_points", "comparison_points"):
            points = series.get(side)
            if not isinstance(points, list):
                raise ValueError("comparison trend points must be arrays")
            for index, point in enumerate(points):
                if not isinstance(point, dict) or point.get("day_index") != index + 1:
                    raise ValueError("comparison trend day indexes must be contiguous")
                _date(point.get("date"), "trend point date")
                if not _finite_number(point.get("value")):
                    raise ValueError("comparison trend value must be finite")


def _validate_period_state(value: Any, label: str) -> tuple[str, str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} comparison period is required")
    requested_start = _date(value.get("requested_start_date"), f"{label}.requested_start_date").isoformat()
    requested_end = _date(value.get("requested_end_date"), f"{label}.requested_end_date").isoformat()
    if requested_start > requested_end:
        raise ValueError(f"{label} requested dates are invalid")
    data_state = value.get("data_state")
    coverage_state = value.get("coverage_state")
    if data_state not in DATA_STATES or coverage_state not in COVERAGE_STATES:
        raise ValueError(f"{label} state is unsupported")
    actual_start = value.get("actual_coverage_start_date")
    actual_end = value.get("actual_coverage_end_date")
    available = value.get("available_through_date")
    if coverage_state in {"complete", "partial"}:
        actual_start = _date(actual_start, f"{label}.actual_coverage_start_date").isoformat()
        actual_end = _date(actual_end, f"{label}.actual_coverage_end_date").isoformat()
        available = _date(available, f"{label}.available_through_date").isoformat()
        if not (requested_start <= actual_start <= actual_end <= requested_end) or available < actual_end:
            raise ValueError(f"{label} actual coverage is invalid")
        if coverage_state == "complete" and (actual_start != requested_start or actual_end != requested_end):
            raise ValueError(f"{label} complete coverage must equal requested coverage")
    elif any(item is not None for item in (actual_start, actual_end)):
        raise ValueError(f"{label} non-data state cannot claim actual coverage")
    return requested_start, requested_end, coverage_state


def _validate_metric_results(metrics: Any) -> None:
    if not isinstance(metrics, list):
        raise ValueError("comparison metrics must be an array")
    seen = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("comparison metric must be an object")
        key = _required_text(metric.get("key"), "metric key")
        if key in seen:
            raise ValueError("duplicate comparison metric key")
        seen.add(key)
        if metric.get("unit") not in METRIC_UNITS:
            raise ValueError("comparison metric unit is unsupported")
        for field in ("current_value", "prior_value", "absolute_change", "relative_change_percent", "percentage_point_change"):
            if metric.get(field) is not None and not _finite_number(metric[field]):
                raise ValueError("comparison metric values must be finite")
        if metric.get("unit") == "rate" and metric.get("relative_change_percent") is not None:
            raise ValueError("rate metrics cannot carry relative percentage change")
        if metric.get("unit") != "rate" and metric.get("percentage_point_change") is not None:
            raise ValueError("only rate metrics may carry percentage-point change")


def _unique_ranked_rows(rows: list[dict[str, Any]], identity_key: str, label: str) -> dict[str, dict[str, Any]]:
    output = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} ranked row must be an object")
        identity = _required_identity_text(row.get(identity_key), f"{label} ranked identity")
        if identity in output:
            raise ValueError(f"duplicate {label} ranked identity")
        output[identity] = row
    return output


def _unique_series(series: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    output = {}
    for item in series:
        if not isinstance(item, dict):
            raise ValueError(f"{label} trend series must be an object")
        key = _required_text(item.get("key"), f"{label} trend key")
        if key in output:
            raise ValueError(f"duplicate {label} trend key")
        output[key] = item
    return output


def _trend_points(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} trend points must be an array")
    output = []
    previous = None
    for point in value:
        if not isinstance(point, dict):
            raise ValueError(f"{label} trend point must be an object")
        observed = _date(point.get("date"), f"{label} trend date")
        if previous is not None and observed <= previous:
            raise ValueError(f"{label} trend dates must be strictly increasing")
        if not _finite_number(point.get("value")):
            raise ValueError(f"{label} trend value must be finite")
        output.append({"date": observed.isoformat(), "value": point["value"]})
        previous = observed
    return output


def lineage(*, source_contract: str, dataset_version: str, source_identity: str, query_fingerprint: str | None = None) -> dict[str, str]:
    value = {"source_contract": source_contract, "dataset_version": dataset_version, "source_identity": source_identity}
    if query_fingerprint:
        value["query_fingerprint"] = query_fingerprint
    return value


def period_state(
    *, requested_start: date, requested_end: date, data_state: str = "complete", coverage_state: str = "complete",
    actual_start: date | None = None, actual_end: date | None = None, available_through: date | None = None,
) -> dict[str, Any]:
    if coverage_state == "complete":
        actual_start, actual_end, available_through = requested_start, requested_end, requested_end
    return {
        "requested_start_date": requested_start.isoformat(),
        "requested_end_date": requested_end.isoformat(),
        "actual_coverage_start_date": actual_start.isoformat() if actual_start else None,
        "actual_coverage_end_date": actual_end.isoformat() if actual_end else None,
        "available_through_date": available_through.isoformat() if available_through else None,
        "data_state": data_state,
        "coverage_state": coverage_state,
    }


def comparison_entry(
    *, package_identity: dict[str, str], section_key: str, preset_key: str, current: dict[str, Any], comparison: dict[str, Any],
    current_lineage: dict[str, Any], comparison_lineage: dict[str, Any], delta_eligible: bool,
    metrics: list[dict[str, Any]] | None = None, ranked_rows: list[dict[str, Any]] | None = None,
    trend_series: list[dict[str, Any]] | None = None, delta_ineligible_reason: str | None = None,
) -> dict[str, Any]:
    return {
        **package_identity,
        "section_key": section_key,
        "preset_key": preset_key,
        "current": current,
        "comparison": comparison,
        "delta_eligible": delta_eligible,
        "delta_ineligible_reason": None if delta_eligible else (delta_ineligible_reason or "Coverage is not comparable."),
        "current_lineage": current_lineage,
        "comparison_lineage": comparison_lineage,
        "metrics": metrics or [],
        "ranked_rows": ranked_rows or [],
        "trend_series": trend_series or [],
    }


def comparison_query_fingerprint(section_key: str, preset_key: str, start: date, end: date) -> str:
    return hashlib.sha256(f"{COMPARISON_SCHEMA_VERSION}:{section_key}:{preset_key}:{start}:{end}".encode()).hexdigest()


def _metric_value(row: dict[str, Any] | None, key: str) -> int | float | None:
    if row is None:
        return None
    metrics = row.get("metrics")
    value = metrics.get(key) if isinstance(metrics, dict) else row.get(key)
    return value if _finite_number(value) else None


def _clamped_replace_year(value: date, year: int) -> date:
    return value.replace(year=year, day=min(value.day, monthrange(year, value.month)[1]))


def _date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError(f"{label} is required")
    return value.strip()


def _required_identity_text(value: Any, label: str) -> str:
    """Validate a ranked stable identity.

    Identities are not ordinary labels. A GA4 page identity is a path joined to
    its page title, and real pages exceed the generic 240 character text guard:
    a Pinnacle Contractors case-study page produced 253. The portal accepts any
    non-empty unique string here and imposes no length limit of its own, so the
    generic ceiling was rejecting rows the consumer would have accepted.

    The value is preserved exactly. Truncating or hashing is not an option,
    because identities are matched across periods and a shortened identity can
    silently pair two different pages. The remaining ceiling is a runaway guard
    only, set far above any real provider value.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    trimmed = value.strip()
    if len(trimmed) > RANKED_IDENTITY_MAX_LENGTH:
        raise ValueError(
            f"{label} exceeds {RANKED_IDENTITY_MAX_LENGTH} characters (length {len(trimmed)})"
        )
    return trimmed


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float("-inf") < float(value) < float("inf")


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value
