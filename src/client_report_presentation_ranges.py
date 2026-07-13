from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from src.client_report_ga4_exact_ranges import (
    GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
    TOP_METRICS_SECTION,
    USER_ENGAGEMENT_SECTION,
    display_data_for_section,
    exact_range_entry_for,
    validate_ga4_exact_range_summary_contract,
)
from src.client_report_ga4_ranked_exact_ranges import (
    RANKED_EXACT_RANGE_SOURCE_BY_SECTION,
    display_data_for_ranked_section,
    exact_ranked_range_entry_for,
    validate_ga4_ranked_exact_range_contract,
)
from src.client_report_gsc_exact_ranges import (
    GSC_EXACT_RANGE_SOURCE_BY_SECTION,
    display_data_for_section as display_data_for_gsc_section,
    exact_range_entry_for as gsc_exact_range_entry_for,
    validate_gsc_exact_range_contract,
)
from src.client_report_publisher_contracts import CANONICAL_SECTION_SOURCE_MATRIX


PRESENTATION_RANGES_SCHEMA_VERSION = "client_report_presentation_ranges.v2"
PRESENTATION_BUCKET_SCHEMA_VERSION = "presentation_ranges.v1"
DEFAULT_PRESENTATION_TIMEZONE = "America/Los_Angeles"

CANONICAL_RANGE_KEYS = (
    "last_3_days",
    "last_7_days",
    "last_14_days",
    "last_30_days",
    "last_90_days",
    "last_6_months",
    "last_12_months",
    "this_month",
    "last_month",
)

CANONICAL_SECTION_KEYS = tuple(CANONICAL_SECTION_SOURCE_MATRIX.keys())

TREND_CLIPPABLE_SECTION_KEYS = {"ga4_website_traffic_trends"}


@dataclass(frozen=True)
class ResolvedRange:
    range_key: str
    start_date: date
    end_date: date


def build_client_report_presentation_ranges(
    *,
    client_slug: str,
    period: dict[str, str],
    datasets: dict[str, dict[str, Any]],
    timezone: str = DEFAULT_PRESENTATION_TIMEZONE,
    custom_ranges: list[dict[str, str]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a sanitized production range package without provider calls.

    Only data that is already exact for the requested range may become a ready
    bucket. Daily trend sections may be clipped because the individual dated
    observations are already display-ready values.
    """
    period_start = _parse_date(period["start"], "period.start")
    period_end = _parse_date(period["end"], "period.end")
    if period_start > period_end:
        raise ValueError("period.start must be on or before period.end")
    reference_date = period_end
    generated = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    range_manifest = [
        _range_manifest_entry(resolved, period_start, period_end, required=True)
        for resolved in resolve_standard_ranges(reference_date)
    ]
    for custom in custom_ranges or []:
        resolved = resolve_custom_range(custom)
        range_manifest.append(_range_manifest_entry(resolved, period_start, period_end, required=False))

    section_buckets: list[dict[str, Any]] = []
    capabilities = []
    for section_key in CANONICAL_SECTION_KEYS:
        supported: list[str] = []
        unavailable: list[str] = []
        partial: list[str] = []
        empty: list[str] = []
        for range_entry in range_manifest:
            resolved = ResolvedRange(
                range_key=range_entry["range_key"],
                start_date=_parse_date(range_entry["requested_start_date"], "requested_start_date"),
                end_date=_parse_date(range_entry["requested_end_date"], "requested_end_date"),
            )
            bucket = _bucket_for_section(section_key, resolved, period_start, period_end, datasets)
            section_buckets.append(bucket)
            state = bucket["data_state"]
            if state == "available":
                supported.append(resolved.range_key)
            elif state == "partial":
                partial.append(resolved.range_key)
            elif state == "empty":
                empty.append(resolved.range_key)
            else:
                unavailable.append(resolved.range_key)
        capability = (
            "trend_point_clippable"
            if section_key in TREND_CLIPPABLE_SECTION_KEYS
            else "exact_range_source_required"
        )
        capabilities.append(
            {
                "section_key": section_key,
                "capability": capability,
                "supported_range_keys": supported,
                "partial_range_keys": partial,
                "empty_range_keys": empty,
                "unavailable_range_keys": unavailable,
                "coverage_status": "complete" if not partial else "partial",
            }
        )

    package = {
        "schema_version": PRESENTATION_RANGES_SCHEMA_VERSION,
        "provider": "presentation",
        "report_type": "range_dataset",
        "client_slug": client_slug,
        "report_period": {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
        },
        "reference_date": reference_date.isoformat(),
        "anchor_rule": "report_period_end",
        "timezone": timezone,
        "dataset_version": f"{client_slug}:{period_start.isoformat()}:{period_end.isoformat()}:presentation-ranges.v2",
        "generated_at": generated,
        "source_snapshot_identity": _source_identity(datasets),
        "range_manifest": range_manifest,
        "section_capabilities": capabilities,
        "section_buckets": section_buckets,
        "validation_summary": {
            "status": "generated_not_validated",
            "warnings": [
                "Summary and ranked sections require exact-range source data; full-period rows are not reused for shorter ranges."
            ],
        },
    }
    validate_presentation_range_package(package)
    return package


def resolve_standard_ranges(reference_date: date) -> list[ResolvedRange]:
    return [resolve_range_key(range_key, reference_date) for range_key in CANONICAL_RANGE_KEYS]


def resolve_range_key(range_key: str, reference_date: date) -> ResolvedRange:
    if range_key == "this_month":
        return ResolvedRange(range_key, reference_date.replace(day=1), reference_date)
    if range_key == "last_month":
        first_this_month = reference_date.replace(day=1)
        last_month_end = first_this_month - timedelta(days=1)
        return ResolvedRange(range_key, last_month_end.replace(day=1), last_month_end)
    trailing_days = {
        "last_3_days": 3,
        "last_7_days": 7,
        "last_14_days": 14,
        "last_30_days": 30,
        "last_90_days": 90,
    }
    if range_key in trailing_days:
        days = trailing_days[range_key]
        return ResolvedRange(range_key, reference_date - timedelta(days=days - 1), reference_date)
    if range_key == "last_6_months":
        return ResolvedRange(range_key, _add_months(reference_date, -6) + timedelta(days=1), reference_date)
    if range_key == "last_12_months":
        return ResolvedRange(range_key, _add_months(reference_date, -12) + timedelta(days=1), reference_date)
    raise ValueError(f"unsupported range key: {range_key}")


def resolve_custom_range(value: dict[str, str]) -> ResolvedRange:
    start = _parse_date(value.get("start_date"), "custom.start_date")
    end = _parse_date(value.get("end_date"), "custom.end_date")
    if start > end:
        raise ValueError("custom range start_date must be on or before end_date")
    label = value.get("range_key") or f"custom:{start.isoformat()}:{end.isoformat()}"
    if not str(label).startswith("custom"):
        raise ValueError("custom range key must start with custom")
    return ResolvedRange(str(label), start, end)


def validate_presentation_range_package(package: dict[str, Any]) -> None:
    if package.get("schema_version") != PRESENTATION_RANGES_SCHEMA_VERSION:
        raise ValueError("presentation range package schema_version is unsupported")
    period = package.get("report_period")
    if not isinstance(period, dict):
        raise ValueError("presentation range package report_period is required")
    period_start = _parse_date(period.get("start_date"), "report_period.start_date")
    period_end = _parse_date(period.get("end_date"), "report_period.end_date")
    reference = _parse_date(package.get("reference_date"), "reference_date")
    if reference != period_end:
        raise ValueError("reference_date must match report period end")
    if not isinstance(package.get("timezone"), str) or "/" not in package["timezone"]:
        raise ValueError("timezone must be an IANA-style label")
    seen_bucket_identity = set()
    for bucket in package.get("section_buckets") or []:
        if not isinstance(bucket, dict):
            raise ValueError("section_buckets must contain objects")
        section_key = bucket.get("section_key")
        if section_key not in CANONICAL_SECTION_KEYS:
            raise ValueError("section bucket has unknown section_key")
        range_key = bucket.get("range_key")
        if not isinstance(range_key, str) or not range_key:
            raise ValueError("section bucket range_key is required")
        start = _parse_date(bucket.get("requested_start_date"), "bucket.requested_start_date")
        end = _parse_date(bucket.get("requested_end_date"), "bucket.requested_end_date")
        if start > end:
            raise ValueError("bucket requested dates are invalid")
        identity = (section_key, range_key, start, end)
        if identity in seen_bucket_identity:
            raise ValueError("duplicate presentation range bucket identity")
        seen_bucket_identity.add(identity)
        coverage = bucket.get("coverage_state")
        data_state = bucket.get("data_state")
        if coverage not in {"complete", "partial", "empty", "unavailable", "unsupported"}:
            raise ValueError("bucket coverage_state is invalid")
        if data_state not in {"available", "partial", "empty", "unavailable", "unsupported"}:
            raise ValueError("bucket data_state is invalid")
        display_data = bucket.get("display_data")
        if data_state == "available" and not isinstance(display_data, dict):
            raise ValueError("available bucket requires display_data")
        if data_state in {"unavailable", "unsupported"} and display_data is not None:
            raise ValueError("unavailable bucket must not carry display_data")
        if data_state == "partial":
            if display_data is not None:
                raise ValueError("partial bucket must not carry presentation display_data")
            actual_start = _parse_date(bucket.get("actual_coverage_start_date"), "bucket.actual_coverage_start_date")
            actual_end = _parse_date(bucket.get("actual_coverage_end_date"), "bucket.actual_coverage_end_date")
            available_through = _parse_date(bucket.get("available_through_date"), "bucket.available_through_date")
            if not (start <= actual_start <= actual_end < end) or available_through < actual_end:
                raise ValueError("partial bucket actual coverage is invalid")
            if bucket.get("precomputed_status") != "not_ready":
                raise ValueError("partial bucket cannot be presentation-ready")
        if coverage == "complete" and data_state not in {"available", "empty"}:
            raise ValueError("complete coverage contradicts bucket data_state")
        if start < period_start or end > period_end:
            if coverage == "complete" or data_state == "available":
                raise ValueError("out-of-period bucket cannot claim complete available data")


def _range_manifest_entry(
    resolved: ResolvedRange,
    period_start: date,
    period_end: date,
    *,
    required: bool,
) -> dict[str, Any]:
    if resolved.end_date < period_start or resolved.start_date > period_end:
        coverage = "unavailable"
    elif resolved.start_date < period_start or resolved.end_date > period_end:
        coverage = "partial"
    else:
        coverage = "complete"
    return {
        "range_key": resolved.range_key,
        "preset_key": "custom_range" if resolved.range_key.startswith("custom") else resolved.range_key,
        "requested_start_date": resolved.start_date.isoformat(),
        "requested_end_date": resolved.end_date.isoformat(),
        "effective_start_date": max(resolved.start_date, period_start).isoformat(),
        "effective_end_date": min(resolved.end_date, period_end).isoformat(),
        "coverage_state": coverage,
        "required": required,
    }


def _bucket_for_section(
    section_key: str,
    resolved: ResolvedRange,
    period_start: date,
    period_end: date,
    datasets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    base = {
        "section_key": section_key,
        "range_key": resolved.range_key,
        "preset_key": "custom_range" if resolved.range_key.startswith("custom") else resolved.range_key,
        "requested_start_date": resolved.start_date.isoformat(),
        "requested_end_date": resolved.end_date.isoformat(),
        "effective_start_date": max(resolved.start_date, period_start).isoformat(),
        "effective_end_date": min(resolved.end_date, period_end).isoformat(),
        "source_contract": CANONICAL_SECTION_SOURCE_MATRIX[section_key][0],
        "dataset_version": "presentation_ranges.v2",
        "precomputed_status": "not_ready",
        "aggregation_status": "not_computed",
        "row_count": 0,
        "observation_count": 0,
        "quality_notes": [],
    }
    if resolved.start_date < period_start or resolved.end_date > period_end:
        return {
            **base,
            "coverage_state": "partial" if resolved.end_date >= period_start and resolved.start_date <= period_end else "unavailable",
            "data_state": "unavailable",
            "unsupported_reason": "Requested range is not fully covered by the base report-period source data.",
            "display_data": None,
        }
    if section_key == "ga4_website_traffic_trends":
        display_data = _clipped_ga4_trends(datasets.get("ga4_metric_display.v1"), resolved)
        if display_data is None:
            return {
                **base,
                "coverage_state": "empty",
                "data_state": "empty",
                "unsupported_reason": "No existing trend observations are available for this range.",
                "display_data": None,
            }
        point_count = min(len(trend["points"]) for trend in display_data["trends"])
        return {
            **base,
            "coverage_state": "complete",
            "data_state": "available",
            "precomputed_status": "ready",
            "aggregation_status": "existing_daily_observation_slice",
            "display_schema_version": "ga4_draft_section_display.v1",
            "observation_count": point_count,
            "display_data": display_data,
        }
    exact_bucket = _exact_range_bucket_from_source(section_key, resolved, datasets)
    if exact_bucket is not None:
        exact_source = exact_bucket.pop("_exact_source", None)
        count = _display_count(exact_bucket)
        return {
            **base,
            "coverage_state": "complete",
            "data_state": "empty" if count == 0 else "available",
            "precomputed_status": "ready",
            "aggregation_status": "importer_sanitized_precomputed",
            "display_schema_version": "generated_section_display.v1",
            "row_count": count,
            **({"exact_source": exact_source} if isinstance(exact_source, dict) else {}),
            "display_data": exact_bucket,
        }
    partial_coverage = _partial_gsc_range_from_source(section_key, resolved, datasets)
    if partial_coverage is not None:
        return {
            **base,
            **partial_coverage,
            "coverage_state": "partial",
            "data_state": "partial",
            "precomputed_status": "not_ready",
            "aggregation_status": "provider_partial_exact_range_withheld",
            "unsupported_reason": "Provider data covers only part of the requested range; partial metrics are not presented as a complete result.",
            "display_data": None,
        }
    return {
        **base,
        "coverage_state": "unsupported",
        "data_state": "unavailable",
        "unsupported_reason": "This section requires exact-range sanitized source data; the importer did not reuse full-period data.",
        "display_data": None,
    }


def _clipped_ga4_trends(payload: dict[str, Any] | None, resolved: ResolvedRange) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    charts = payload.get("trend_charts")
    if not isinstance(charts, list) or not charts:
        return None
    chart = charts[0]
    if not isinstance(chart, dict):
        return None
    series = chart.get("series")
    if not isinstance(series, list):
        return None
    trends = []
    for item in series:
        if not isinstance(item, dict) or item.get("key") not in {"users", "sessions"}:
            continue
        points = []
        for point in item.get("points") or []:
            if not isinstance(point, dict):
                return None
            observed = _parse_date(point.get("date"), "trend point date")
            if resolved.start_date <= observed <= resolved.end_date:
                value = point.get("value")
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return None
                points.append({"date": observed.isoformat(), "value": value})
        if len(points) < 2:
            return None
        trends.append(
            {
                "key": f"{item['key']}_trend",
                "label": item.get("label") or item["key"].title(),
                "value_kind": "integer",
                "points": points,
            }
        )
    return {"trends": trends} if len(trends) == 2 else None


def _exact_range_bucket_from_source(
    section_key: str,
    resolved: ResolvedRange,
    datasets: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if section_key in {TOP_METRICS_SECTION, USER_ENGAGEMENT_SECTION}:
        ga4_exact_ranges = datasets.get(GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION)
        if isinstance(ga4_exact_ranges, dict):
            validate_ga4_exact_range_summary_contract(ga4_exact_ranges)
            entry = exact_range_entry_for(
                ga4_exact_ranges,
                range_key=resolved.range_key,
                start_date=resolved.start_date.isoformat(),
                end_date=resolved.end_date.isoformat(),
            )
            if isinstance(entry, dict):
                display_data = display_data_for_section(entry, section_key)
                if display_data is not None:
                    display_data["_exact_source"] = {
                        "source_contract": GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
                        "dataset_version": ga4_exact_ranges.get("dataset_version"),
                        "range_key": entry.get("range_key"),
                        "requested_start_date": entry.get("requested_start_date"),
                        "requested_end_date": entry.get("requested_end_date"),
                        "source_identity": entry.get("source_identity"),
                    }
                    return display_data

    ranked_schema = RANKED_EXACT_RANGE_SOURCE_BY_SECTION.get(section_key)
    if ranked_schema:
        ranked_exact_ranges = datasets.get(ranked_schema)
        if isinstance(ranked_exact_ranges, dict):
            validate_ga4_ranked_exact_range_contract(ranked_exact_ranges)
            entry = exact_ranked_range_entry_for(
                ranked_exact_ranges,
                range_key=resolved.range_key,
                start_date=resolved.start_date.isoformat(),
                end_date=resolved.end_date.isoformat(),
            )
            if isinstance(entry, dict):
                display_data = display_data_for_ranked_section(entry, section_key)
                if display_data is not None:
                    display_data["_exact_source"] = {
                        "source_contract": ranked_schema,
                        "dataset_version": ranked_exact_ranges.get("dataset_version"),
                        "range_key": entry.get("range_key"),
                        "requested_start_date": entry.get("requested_start_date"),
                        "requested_end_date": entry.get("requested_end_date"),
                        "source_identity": entry.get("source_identity"),
                    }
                    return display_data

    gsc_schema = GSC_EXACT_RANGE_SOURCE_BY_SECTION.get(section_key)
    if gsc_schema:
        gsc_exact_ranges = datasets.get(gsc_schema)
        if isinstance(gsc_exact_ranges, dict):
            validate_gsc_exact_range_contract(gsc_exact_ranges)
            entry = gsc_exact_range_entry_for(
                gsc_exact_ranges,
                range_key=resolved.range_key,
                start_date=resolved.start_date.isoformat(),
                end_date=resolved.end_date.isoformat(),
            )
            if isinstance(entry, dict):
                display_data = display_data_for_gsc_section(entry, section_key)
                if display_data is not None:
                    display_data["_exact_source"] = {
                        "source_contract": gsc_schema,
                        "dataset_version": gsc_exact_ranges.get("dataset_version"),
                        "range_key": entry.get("range_key"),
                        "requested_start_date": entry.get("requested_start_date"),
                        "requested_end_date": entry.get("requested_end_date"),
                        "source_identity": entry.get("source_identity"),
                    }
                    return display_data

    range_sources = datasets.get("presentation_exact_ranges.v1")
    if not isinstance(range_sources, dict):
        return None
    sections = range_sources.get("sections")
    if not isinstance(sections, list):
        return None
    for section in sections:
        if not isinstance(section, dict) or section.get("section_key") != section_key:
            continue
        for bucket in section.get("buckets") or []:
            if (
                isinstance(bucket, dict)
                and bucket.get("range_key") == resolved.range_key
                and bucket.get("start_date") == resolved.start_date.isoformat()
                and bucket.get("end_date") == resolved.end_date.isoformat()
                and isinstance(bucket.get("display_data"), dict)
            ):
                return bucket["display_data"]
    return None


def _partial_gsc_range_from_source(
    section_key: str,
    resolved: ResolvedRange,
    datasets: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    schema = GSC_EXACT_RANGE_SOURCE_BY_SECTION.get(section_key)
    payload = datasets.get(schema) if schema else None
    if not isinstance(payload, dict):
        return None
    validate_gsc_exact_range_contract(payload)
    entry = gsc_exact_range_entry_for(
        payload,
        range_key=resolved.range_key,
        start_date=resolved.start_date.isoformat(),
        end_date=resolved.end_date.isoformat(),
    )
    if not isinstance(entry, dict) or entry.get("data_state") != "partial":
        return None
    return {
        "actual_coverage_start_date": entry.get("actual_coverage_start_date"),
        "actual_coverage_end_date": entry.get("actual_coverage_end_date"),
        "available_through_date": entry.get("available_through_date"),
        "freshness_state": entry.get("freshness_state"),
        "observation_count": entry.get("actual_date_count", 0),
        "exact_source": {
            "source_contract": schema,
            "dataset_version": payload.get("dataset_version"),
            "range_key": entry.get("range_key"),
            "requested_start_date": entry.get("requested_start_date"),
            "requested_end_date": entry.get("requested_end_date"),
            "source_identity": entry.get("source_identity"),
        },
    }


def _display_count(display_data: dict[str, Any]) -> int:
    if "_exact_source" in display_data and len(display_data) == 2:
        for key in ("metrics",):
            value = display_data.get(key)
            if isinstance(value, list):
                return len(value)
    for key in ("rows", "queries", "pages", "metrics", "summary_metrics"):
        value = display_data.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
    return 0


def _source_identity(datasets: dict[str, dict[str, Any]]) -> dict[str, str]:
    identity = {}
    for contract_name in sorted(key for key in datasets if key != "presentation_exact_ranges.v1"):
        payload = datasets[contract_name]
        period = payload.get("report_period") if isinstance(payload, dict) else None
        start = period.get("start") if isinstance(period, dict) else None
        end = period.get("end") if isinstance(period, dict) else None
        if start is None and isinstance(period, dict):
            start = period.get("start_date")
            end = period.get("end_date")
        identity[contract_name] = f"{contract_name}:{start or 'unknown'}:{end or 'unknown'}"
    return identity


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _last_day_of_month(year, month))
    return date(year, month, day)


def _last_day_of_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc
