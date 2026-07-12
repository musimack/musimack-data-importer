from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Callable, Protocol

from src.client_report_ga4_ranked_exact_ranges import (
    GA4_RANKED_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
    METRIC_DEFINITIONS,
    RANKED_EXACT_RANGE_CONTRACTS,
    RankedExactRangeContract,
    contract_for_ranked_exact_section,
    validate_ga4_ranked_exact_range_contract,
)
from src.client_report_presentation_ranges import resolve_range_key
from src.config import DateRange
from src.ga4_client import Ga4ClientError


EXACT_RANGE_KEYS = ("last_7_days", "last_30_days", "this_month", "last_month")
QUERY_SHAPE_VERSION = "ga4_data_api_ranked_exact_range.v1"


class RankedExactRangeGa4Client(Protocol):
    def run_exact_range_channel_performance(self, date_range: DateRange) -> dict[str, Any]:
        ...

    def run_exact_range_top_sources(self, date_range: DateRange) -> dict[str, Any]:
        ...

    def run_exact_range_top_landing_pages(self, date_range: DateRange) -> dict[str, Any]:
        ...

    def run_exact_range_most_viewed_pages(self, date_range: DateRange) -> dict[str, Any]:
        ...


QUERY_BY_SECTION: dict[str, tuple[str, str, tuple[str, ...], Callable[[RankedExactRangeGa4Client, DateRange], dict[str, Any]]]] = {
    "ga4_channel_performance": (
        "run_exact_range_channel_performance",
        "sessionDefaultChannelGroup",
        ("activeUsers", "sessions", "screenPageViews", "engagementRate", "averageSessionDuration", "eventCount"),
        lambda client, date_range: client.run_exact_range_channel_performance(date_range),
    ),
    "ga4_top_sources": (
        "run_exact_range_top_sources",
        "sessionSourceMedium",
        ("activeUsers", "sessions", "engagementRate", "averageSessionDuration", "eventCount"),
        lambda client, date_range: client.run_exact_range_top_sources(date_range),
    ),
    "ga4_top_landing_pages": (
        "run_exact_range_top_landing_pages",
        "landingPagePlusQueryString",
        ("activeUsers", "sessions", "engagedSessions", "engagementRate", "averageSessionDuration", "eventCount"),
        lambda client, date_range: client.run_exact_range_top_landing_pages(date_range),
    ),
    "ga4_most_viewed_pages": (
        "run_exact_range_most_viewed_pages",
        "pageTitle,pagePath",
        ("screenPageViews", "activeUsers", "eventCount", "averageSessionDuration"),
        lambda client, date_range: client.run_exact_range_most_viewed_pages(date_range),
    ),
}

PROVIDER_METRIC_TO_CONTRACT = {
    "activeUsers": "users",
    "sessions": "sessions",
    "engagedSessions": "engaged_sessions",
    "engagementRate": "engagement_rate",
    "screenPageViews": "views",
    "eventCount": "event_count",
}


def build_all_ga4_ranked_exact_ranges_from_provider(
    *,
    client: RankedExactRangeGa4Client,
    profile: str,
    report_period_start: date,
    report_period_end: date,
    timezone: str = "America/Los_Angeles",
    generated_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        contract.schema_version: build_ga4_ranked_exact_range_from_provider(
            client=client,
            profile=profile,
            section_key=contract.section_key,
            report_period_start=report_period_start,
            report_period_end=report_period_end,
            timezone=timezone,
            generated_at=generated_at,
        )
        for contract in RANKED_EXACT_RANGE_CONTRACTS.values()
    }


def build_ga4_ranked_exact_range_from_provider(
    *,
    client: RankedExactRangeGa4Client,
    profile: str,
    section_key: str,
    report_period_start: date,
    report_period_end: date,
    timezone: str = "America/Los_Angeles",
    generated_at: str | None = None,
) -> dict[str, Any]:
    if report_period_start > report_period_end:
        raise ValueError("report_period_start must be on or before report_period_end")
    contract = contract_for_ranked_exact_section(section_key)
    if contract is None:
        raise ValueError("unsupported ranked exact-range section")
    method_name, provider_dimension, provider_metrics, runner = QUERY_BY_SECTION[section_key]
    generated = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ranges = []
    query_notes = [
        "Queried GA4 Data API directly for each ranked exact range; rows are not derived from report-period rankings."
    ]
    for range_key in EXACT_RANGE_KEYS:
        resolved = resolve_range_key(range_key, report_period_end)
        if resolved.start_date < report_period_start or resolved.end_date > report_period_end:
            raise ValueError(f"{range_key} must stay inside the report period")
        ranges.append(
            _range_entry(
                client=client,
                profile=profile,
                range_key=range_key,
                date_range=DateRange(resolved.start_date, resolved.end_date),
                contract=contract,
                runner=runner,
            )
        )

    payload = {
        "schema_version": contract.schema_version,
        "provider": "ga4",
        "report_type": contract.report_type,
        "data_scope": contract.data_scope,
        "section_key": contract.section_key,
        "dataset_version": contract.schema_version,
        "client_slug": profile,
        "report_period": {
            "start_date": report_period_start.isoformat(),
            "end_date": report_period_end.isoformat(),
        },
        "timezone": timezone,
        "inclusive_dates": True,
        "calculation_version": GA4_RANKED_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
        "generated_at": generated,
        "source_identity": {
            "source_kind": "ga4_data_api",
            "source_label": "GA4 Data API ranked exact-range rows",
            "profile": profile,
        },
        "query_identity": {
            "shape_id": f"{QUERY_SHAPE_VERSION}.{contract.section_key}",
            "method": method_name,
            "provider_dimension": provider_dimension,
            "provider_metrics": list(provider_metrics),
            "sort_metric": contract.sort_metric,
            "row_limit": contract.row_limit,
            "fingerprint": f"{contract.schema_version}:{provider_dimension}:{','.join(provider_metrics)}:{contract.sort_metric}:limit-{contract.row_limit}",
        },
        "dimension_definition": {
            "dimension_key": contract.dimension_key,
            "provider_dimension": provider_dimension,
            "required_fields": list(contract.required_dimension_fields),
        },
        "metric_definitions": [{"key": key, **METRIC_DEFINITIONS[key]} for key in contract.metric_order],
        "sort_definition": {"metric_key": contract.sort_metric, "direction": "desc"},
        "row_limit": contract.row_limit,
        "ranges": ranges,
        "quality_notes": query_notes,
    }
    validate_ga4_ranked_exact_range_contract(payload)
    return payload


def _range_entry(
    *,
    client: RankedExactRangeGa4Client,
    profile: str,
    range_key: str,
    date_range: DateRange,
    contract: RankedExactRangeContract,
    runner: Callable[[RankedExactRangeGa4Client, DateRange], dict[str, Any]],
) -> dict[str, Any]:
    try:
        response = runner(client, date_range)
    except Ga4ClientError:
        raise
    rows = _rows_from_response(response, contract)
    expected_days = (date_range.end - date_range.start).days + 1
    if rows:
        data_state = "available"
        coverage_state = "complete"
        quality_state = "passed"
    else:
        data_state = "empty"
        coverage_state = "empty"
        quality_state = "empty"
    return {
        "range_key": range_key,
        "requested_start_date": date_range.start.isoformat(),
        "requested_end_date": date_range.end.isoformat(),
        "inclusive_dates": True,
        "data_state": data_state,
        "coverage_state": coverage_state,
        "quality_state": quality_state,
        "expected_date_count": expected_days,
        "actual_date_count": expected_days,
        "row_count": len(rows),
        "rows": rows,
        "calculation_version": GA4_RANKED_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
        "source_identity": f"{profile}:{contract.section_key}:{range_key}:{date_range.start.isoformat()}:{date_range.end.isoformat()}:ga4_data_api_ranked_exact_range",
        "quality_notes": [
            "Queried GA4 Data API for the exact ranked section and date range; no report-period fallback was used."
        ],
    }


def _rows_from_response(response: dict[str, Any], contract: RankedExactRangeContract) -> list[dict[str, Any]]:
    dimension_headers = _header_names(response.get("dimensionHeaders"))
    metric_headers = _header_names(response.get("metricHeaders"))
    rows = []
    for row in response.get("rows") or []:
        if not isinstance(row, dict):
            raise ValueError("GA4 ranked exact-range response row is invalid")
        parsed = _row_from_provider_row(row, dimension_headers, metric_headers, contract)
        if parsed is not None:
            rows.append(parsed)
    rows.sort(key=lambda item: (-float(item["metrics"][contract.sort_metric]), str(item.get("label") or "")))
    for index, row in enumerate(rows[: contract.row_limit]):
        row["rank"] = index + 1
    return rows[: contract.row_limit]


def _row_from_provider_row(
    row: dict[str, Any],
    dimension_headers: list[str],
    metric_headers: list[str],
    contract: RankedExactRangeContract,
) -> dict[str, Any] | None:
    dimensions = _values(row.get("dimensionValues"))
    metric_values = _values(row.get("metricValues"))
    metrics = _metrics(metric_headers, metric_values, contract)
    if contract.sort_metric not in metrics:
        raise ValueError("GA4 ranked exact-range response missing sort metric")
    if contract.section_key == "ga4_channel_performance":
        channel = _dimension_value(dimension_headers, dimensions, "sessionDefaultChannelGroup").strip()
        if not channel:
            return None
        return {"rank": 0, "channel": channel, "label": channel, "metrics": metrics}
    if contract.section_key == "ga4_top_sources":
        source_medium = _dimension_value(dimension_headers, dimensions, "sessionSourceMedium").strip()
        if not source_medium:
            return None
        source, medium = _split_source_medium(source_medium)
        return {
            "rank": 0,
            "source": source,
            "medium": medium,
            "source_medium": source_medium,
            "label": source_medium,
            "metrics": metrics,
        }
    if contract.section_key == "ga4_top_landing_pages":
        path = _dimension_value(dimension_headers, dimensions, "landingPagePlusQueryString").strip()
        if not path:
            return None
        return {"rank": 0, "path": path, "label": path, "metrics": metrics}
    title = _dimension_value(dimension_headers, dimensions, "pageTitle").strip()
    path = _dimension_value(dimension_headers, dimensions, "pagePath").strip()
    if not path and not title:
        return None
    label = f"{title} ({path})" if title and path else title or path
    return {
        "rank": 0,
        "path": path or label,
        "page_title": title or label,
        "label": label,
        "metrics": metrics,
    }


def _metrics(metric_headers: list[str], values: list[str], contract: RankedExactRangeContract) -> dict[str, int | float]:
    parsed = {}
    for index, metric_name in enumerate(metric_headers):
        key = PROVIDER_METRIC_TO_CONTRACT.get(metric_name)
        if key is None or key not in contract.metric_order:
            continue
        parsed[key] = _coerce_metric_value(key, values[index] if index < len(values) else "0")
    return parsed


def _coerce_metric_value(metric_key: str, value: Any) -> int | float:
    try:
        number = float(str(value or "0"))
    except ValueError as exc:
        raise ValueError(f"GA4 ranked exact-range metric {metric_key} is not numeric") from exc
    if metric_key == "engagement_rate":
        return round(number, 6)
    return int(round(number))


def _header_names(headers: Any) -> list[str]:
    if not isinstance(headers, list):
        raise ValueError("GA4 ranked exact-range response headers are missing")
    return [str(item.get("name") or "") for item in headers if isinstance(item, dict)]


def _values(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("GA4 ranked exact-range response values are missing")
    return [str(item.get("value") or "") if isinstance(item, dict) else "" for item in values]


def _dimension_value(headers: list[str], values: list[str], name: str) -> str:
    try:
        index = headers.index(name)
    except ValueError as exc:
        raise ValueError(f"GA4 ranked exact-range response missing dimension {name}") from exc
    return values[index] if index < len(values) else ""


def _split_source_medium(value: str) -> tuple[str, str]:
    if " / " in value:
        source, medium = value.split(" / ", 1)
        return source, medium
    return value, "(not set)"
