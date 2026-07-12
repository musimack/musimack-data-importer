from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any


GA4_RANKED_EXACT_RANGE_CALCULATION_VERSION = "ga4_ranked_exact_ranges.synthetic.v1"
GA4_RANKED_EXACT_RANGE_PROVIDER_CALCULATION_VERSION = "ga4_ranked_exact_ranges.provider.v1"
GA4_RANKED_EXACT_RANGE_CALCULATION_VERSIONS = {
    GA4_RANKED_EXACT_RANGE_CALCULATION_VERSION,
    GA4_RANKED_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
}


@dataclass(frozen=True)
class RankedExactRangeContract:
    schema_version: str
    section_key: str
    report_type: str
    data_scope: str
    dimension_key: str
    required_dimension_fields: tuple[str, ...]
    forbidden_dimension_fields: tuple[str, ...]
    sort_metric: str
    metric_order: tuple[str, ...]
    row_limit: int = 10


RANKED_EXACT_RANGE_CONTRACTS: dict[str, RankedExactRangeContract] = {
    "ga4_channel_performance_exact_ranges.v1": RankedExactRangeContract(
        schema_version="ga4_channel_performance_exact_ranges.v1",
        section_key="ga4_channel_performance",
        report_type="channel_performance_exact_ranges",
        data_scope="channel_group",
        dimension_key="channel_group",
        required_dimension_fields=("channel",),
        forbidden_dimension_fields=("source", "medium", "source_medium", "landing_page", "path", "page_title"),
        sort_metric="sessions",
        metric_order=("sessions", "users", "engagement_rate"),
    ),
    "ga4_top_sources_exact_ranges.v1": RankedExactRangeContract(
        schema_version="ga4_top_sources_exact_ranges.v1",
        section_key="ga4_top_sources",
        report_type="top_sources_exact_ranges",
        data_scope="source_medium",
        dimension_key="source_medium",
        required_dimension_fields=("source", "medium", "source_medium"),
        forbidden_dimension_fields=("channel", "landing_page", "path", "page_title"),
        sort_metric="sessions",
        metric_order=("sessions", "users", "engagement_rate"),
    ),
    "ga4_top_landing_pages_exact_ranges.v1": RankedExactRangeContract(
        schema_version="ga4_top_landing_pages_exact_ranges.v1",
        section_key="ga4_top_landing_pages",
        report_type="top_landing_pages_exact_ranges",
        data_scope="landing_page",
        dimension_key="landing_page",
        required_dimension_fields=("path",),
        forbidden_dimension_fields=("source", "medium", "source_medium", "channel", "views"),
        sort_metric="sessions",
        metric_order=("sessions", "users", "engaged_sessions"),
    ),
    "ga4_most_viewed_pages_exact_ranges.v1": RankedExactRangeContract(
        schema_version="ga4_most_viewed_pages_exact_ranges.v1",
        section_key="ga4_most_viewed_pages",
        report_type="most_viewed_pages_exact_ranges",
        data_scope="page_popularity",
        dimension_key="page_popularity",
        required_dimension_fields=("path", "page_title"),
        forbidden_dimension_fields=("source", "medium", "source_medium", "landing_page", "channel"),
        sort_metric="views",
        metric_order=("views", "users", "event_count"),
    ),
}

RANKED_EXACT_RANGE_SOURCE_BY_SECTION = {
    contract.section_key: contract.schema_version
    for contract in RANKED_EXACT_RANGE_CONTRACTS.values()
}
RANKED_EXACT_RANGE_SOURCE_FILES = {
    schema_version: f"{schema_version}.json"
    for schema_version in RANKED_EXACT_RANGE_CONTRACTS
}

METRIC_DEFINITIONS = {
    "sessions": {"value_type": "integer", "unit": "count"},
    "users": {"value_type": "integer", "unit": "count"},
    "engaged_sessions": {"value_type": "integer", "unit": "count"},
    "views": {"value_type": "integer", "unit": "count"},
    "event_count": {"value_type": "integer", "unit": "count"},
    "engagement_rate": {"value_type": "ratio", "unit": "percent"},
}

METRIC_LABELS = {
    "sessions": "Visits",
    "users": "Website Visitors",
    "engaged_sessions": "Engaged Sessions",
    "views": "Views",
    "event_count": "Events",
    "engagement_rate": "Engagement Rate",
}

PROTOTYPE_RANGES = (
    ("last_7_days", "2026-07-02", "2026-07-08"),
    ("last_30_days", "2026-06-09", "2026-07-08"),
    ("this_month", "2026-07-01", "2026-07-08"),
    ("last_month", "2026-06-01", "2026-06-30"),
)


def contract_for_ranked_exact_schema(schema_version: str) -> RankedExactRangeContract | None:
    return RANKED_EXACT_RANGE_CONTRACTS.get(schema_version)


def contract_for_ranked_exact_section(section_key: str) -> RankedExactRangeContract | None:
    schema_version = RANKED_EXACT_RANGE_SOURCE_BY_SECTION.get(section_key)
    return RANKED_EXACT_RANGE_CONTRACTS.get(schema_version or "")


def validate_ga4_ranked_exact_range_contract(payload: dict[str, Any]) -> None:
    schema_version = payload.get("schema_version")
    contract = RANKED_EXACT_RANGE_CONTRACTS.get(schema_version)
    if contract is None:
        raise ValueError("ranked exact-range GA4 schema_version is unsupported")
    if payload.get("provider") != "ga4":
        raise ValueError("ranked exact-range GA4 provider must be ga4")
    if payload.get("report_type") != contract.report_type:
        raise ValueError("ranked exact-range GA4 report_type is invalid")
    if payload.get("data_scope") != contract.data_scope:
        raise ValueError("ranked exact-range GA4 data_scope is invalid")
    if payload.get("section_key") != contract.section_key:
        raise ValueError("ranked exact-range GA4 section_key is invalid")
    if payload.get("dataset_version") != contract.schema_version:
        raise ValueError("ranked exact-range GA4 dataset_version is invalid")
    if payload.get("calculation_version") not in GA4_RANKED_EXACT_RANGE_CALCULATION_VERSIONS:
        raise ValueError("ranked exact-range GA4 calculation_version is invalid")
    if payload.get("inclusive_dates") is not True:
        raise ValueError("ranked exact-range GA4 inclusive_dates must be true")
    if not isinstance(payload.get("source_identity"), dict):
        raise ValueError("ranked exact-range GA4 source_identity is required")
    if not isinstance(payload.get("query_identity"), dict):
        raise ValueError("ranked exact-range GA4 query_identity is required")
    if not isinstance(payload.get("dimension_definition"), dict):
        raise ValueError("ranked exact-range GA4 dimension_definition is required")
    if payload["dimension_definition"].get("dimension_key") != contract.dimension_key:
        raise ValueError("ranked exact-range GA4 dimension_definition does not match section")
    sort_definition = payload.get("sort_definition")
    if not isinstance(sort_definition, dict) or sort_definition.get("metric_key") != contract.sort_metric:
        raise ValueError("ranked exact-range GA4 sort_definition is invalid")
    if payload.get("row_limit") != contract.row_limit:
        raise ValueError("ranked exact-range GA4 row_limit is invalid")

    period = payload.get("report_period")
    if not isinstance(period, dict):
        raise ValueError("ranked exact-range GA4 report_period is required")
    period_start = _parse_date(period.get("start_date"), "report_period.start_date")
    period_end = _parse_date(period.get("end_date"), "report_period.end_date")
    if period_start > period_end:
        raise ValueError("ranked exact-range GA4 report_period is inverted")
    timezone = payload.get("timezone")
    if not isinstance(timezone, str) or "/" not in timezone:
        raise ValueError("ranked exact-range GA4 timezone is invalid")

    definitions = payload.get("metric_definitions")
    if not isinstance(definitions, list):
        raise ValueError("ranked exact-range GA4 metric_definitions must be a list")
    definition_keys = {item.get("key") for item in definitions if isinstance(item, dict)}
    if set(contract.metric_order) - definition_keys:
        raise ValueError("ranked exact-range GA4 metric_definitions are incomplete")

    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        raise ValueError("ranked exact-range GA4 ranges must be a list")
    seen: set[tuple[str, date, date]] = set()
    for index, item in enumerate(ranges):
        _validate_range_entry(item, index, period_start, period_end, contract, seen)


def exact_ranked_range_entry_for(
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


def display_data_for_ranked_section(entry: dict[str, Any], section_key: str) -> dict[str, Any] | None:
    contract = contract_for_ranked_exact_section(section_key)
    if contract is None or entry.get("data_state") != "available":
        return None
    rows = entry.get("rows")
    if not isinstance(rows, list):
        return None
    display_rows = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            return None
        display_row = {
            "rank": row.get("rank"),
            "label": row.get("label") or _display_label(row, contract),
            "metrics": [
                _compact_metric(metric_key, metrics[metric_key])
                for metric_key in contract.metric_order
                if metric_key in metrics
            ],
        }
        if "path" in row:
            display_row["path"] = row["path"]
        display_rows.append(display_row)
    return {"rows": display_rows} if display_rows else None


def build_fake_ga4_ranked_exact_range_dataset(
    *,
    section_key: str,
    client_slug: str,
    period: dict[str, str],
    generated_at: str = "2026-07-09T12:00:00Z",
    timezone: str = "America/Los_Angeles",
) -> dict[str, Any]:
    contract = contract_for_ranked_exact_section(section_key)
    if contract is None:
        raise ValueError("unsupported ranked exact-range section")
    ranges = []
    for range_index, (range_key, start, end) in enumerate(PROTOTYPE_RANGES):
        ranges.append(_fake_range_entry(contract, client_slug, range_index, range_key, start, end))
    payload = {
        "schema_version": contract.schema_version,
        "provider": "ga4",
        "report_type": contract.report_type,
        "data_scope": contract.data_scope,
        "section_key": contract.section_key,
        "dataset_version": contract.schema_version,
        "client_slug": client_slug,
        "report_period": {"start_date": period["start"], "end_date": period["end"]},
        "timezone": timezone,
        "inclusive_dates": True,
        "calculation_version": GA4_RANKED_EXACT_RANGE_CALCULATION_VERSION,
        "generated_at": generated_at,
        "source_identity": {"source_kind": "synthetic_fixture", "client_slug": client_slug},
        "query_identity": {
            "shape_id": f"{contract.schema_version}.synthetic",
            "dimension_key": contract.dimension_key,
            "sort_metric": contract.sort_metric,
            "fingerprint": f"{client_slug}:{contract.section_key}:ranked-exact-ranges",
        },
        "dimension_definition": {
            "dimension_key": contract.dimension_key,
            "required_fields": list(contract.required_dimension_fields),
        },
        "metric_definitions": [{"key": key, **METRIC_DEFINITIONS[key]} for key in contract.metric_order],
        "sort_definition": {"metric_key": contract.sort_metric, "direction": "desc"},
        "row_limit": contract.row_limit,
        "ranges": ranges,
    }
    validate_ga4_ranked_exact_range_contract(payload)
    return payload


def _validate_range_entry(
    item: Any,
    index: int,
    period_start: date,
    period_end: date,
    contract: RankedExactRangeContract,
    seen: set[tuple[str, date, date]],
) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] must be an object")
    range_key = item.get("range_key")
    if not isinstance(range_key, str) or not range_key:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].range_key is required")
    start = _parse_date(item.get("requested_start_date"), f"ranges[{index}].requested_start_date")
    end = _parse_date(item.get("requested_end_date"), f"ranges[{index}].requested_end_date")
    if start > end or start < period_start or end > period_end:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] dates are invalid for report period")
    identity = (range_key, start, end)
    if identity in seen:
        raise ValueError("duplicate ranked exact-range GA4 identity")
    seen.add(identity)
    if item.get("inclusive_dates") is not True:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].inclusive_dates must be true")
    if item.get("calculation_version") not in GA4_RANKED_EXACT_RANGE_CALCULATION_VERSIONS:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].calculation_version is invalid")

    data_state = item.get("data_state")
    coverage_state = item.get("coverage_state")
    quality_state = item.get("quality_state")
    if data_state not in {"available", "empty", "partial", "unavailable"}:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].data_state is invalid")
    if coverage_state not in {"complete", "empty", "partial", "unavailable"}:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].coverage_state is invalid")
    if quality_state not in {"passed", "empty", "partial", "unavailable"}:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].quality_state is invalid")
    expected_days = (end - start).days + 1
    if item.get("expected_date_count") != expected_days:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].expected_date_count is inconsistent")
    actual_count = item.get("actual_date_count")
    if not isinstance(actual_count, int) or actual_count < 0 or actual_count > expected_days:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].actual_date_count is invalid")
    rows = item.get("rows")
    if data_state == "available" and (coverage_state != "complete" or quality_state != "passed"):
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] available state requires complete passed coverage")
    if data_state == "empty" and (coverage_state != "empty" or rows not in ([], None)):
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] empty state contradicts rows")
    if data_state == "partial" and (coverage_state != "partial" or actual_count >= expected_days):
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] partial state contradicts coverage")
    if data_state == "unavailable" and (coverage_state != "unavailable" or rows not in ([], None)):
        raise ValueError(f"ranked exact-range GA4 ranges[{index}] unavailable state contradicts rows")
    if data_state != "available":
        return
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].rows must be a non-empty list")
    if len(rows) > contract.row_limit:
        raise ValueError(f"ranked exact-range GA4 ranges[{index}].rows exceeds row_limit")
    seen_dimensions: set[tuple[Any, ...]] = set()
    previous_sort_value: float | None = None
    previous_label = ""
    for row_index, row in enumerate(rows):
        _validate_ranked_row(row, index, row_index, contract)
        identity_key = tuple(row.get(field) for field in contract.required_dimension_fields)
        if identity_key in seen_dimensions:
            raise ValueError(f"ranked exact-range GA4 ranges[{index}].rows duplicate dimension identity")
        seen_dimensions.add(identity_key)
        if row.get("rank") != row_index + 1:
            raise ValueError(f"ranked exact-range GA4 ranges[{index}].rows ranks must be sequential")
        sort_value = float(row["metrics"][contract.sort_metric])
        label = str(row.get("label") or "")
        if previous_sort_value is not None and (
            sort_value > previous_sort_value or (sort_value == previous_sort_value and label < previous_label)
        ):
            raise ValueError(f"ranked exact-range GA4 ranges[{index}].rows are not sorted")
        previous_sort_value = sort_value
        previous_label = label


def _validate_ranked_row(
    row: Any,
    range_index: int,
    row_index: int,
    contract: RankedExactRangeContract,
) -> None:
    if not isinstance(row, dict):
        raise ValueError(f"ranked exact-range GA4 ranges[{range_index}].rows[{row_index}] must be an object")
    for field in contract.required_dimension_fields:
        if not isinstance(row.get(field), str) or not row[field]:
            raise ValueError(f"ranked exact-range GA4 row missing required dimension field {field}")
    for field in contract.forbidden_dimension_fields:
        if field in row:
            raise ValueError("ranked exact-range GA4 row contains mismatched section scope")
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("ranked exact-range GA4 row metrics must be an object")
    if contract.sort_metric not in metrics:
        raise ValueError("ranked exact-range GA4 row missing sort metric")
    for metric_key, value in metrics.items():
        if metric_key not in METRIC_DEFINITIONS:
            raise ValueError("ranked exact-range GA4 row has unknown metric")
        _validate_metric_value(metric_key, value)


def _validate_metric_value(metric_key: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("ranked exact-range GA4 metric value is invalid")
    value_type = METRIC_DEFINITIONS[metric_key]["value_type"]
    if value_type == "integer" and not float(value).is_integer():
        raise ValueError("ranked exact-range GA4 integer metric value is invalid")
    if value_type == "ratio" and value > 1:
        raise ValueError("ranked exact-range GA4 ratio metric is invalid")


def _fake_range_entry(
    contract: RankedExactRangeContract,
    client_slug: str,
    range_index: int,
    range_key: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    days = (end_date - start_date).days + 1
    rows = [_fake_row(contract, range_index, row_index) for row_index in range(3)]
    rows.sort(key=lambda row: (-float(row["metrics"][contract.sort_metric]), str(row["label"])))
    for row_index, row in enumerate(rows):
        row["rank"] = row_index + 1
    return {
        "range_key": range_key,
        "requested_start_date": start,
        "requested_end_date": end,
        "inclusive_dates": True,
        "data_state": "available",
        "coverage_state": "complete",
        "quality_state": "passed",
        "expected_date_count": days,
        "actual_date_count": days,
        "row_count": len(rows),
        "rows": rows,
        "calculation_version": GA4_RANKED_EXACT_RANGE_CALCULATION_VERSION,
        "source_identity": f"{client_slug}:{contract.section_key}:{range_key}:{start}:{end}",
        "quality_notes": ["Synthetic ranked exact-range fixture; no provider call was made."],
    }


def _fake_row(contract: RankedExactRangeContract, range_index: int, row_index: int) -> dict[str, Any]:
    base = (range_index + 2) * 100 - row_index * 17
    if contract.section_key == "ga4_channel_performance":
        label = ["Organic Search", "Direct", "Referral"][row_index]
        return {
            "rank": row_index + 1,
            "channel": label,
            "label": label,
            "metrics": {"sessions": base, "users": base - 11, "engagement_rate": 0.62 - row_index * 0.03},
        }
    if contract.section_key == "ga4_top_sources":
        source, medium = [("google", "organic"), ("newsletter", "email"), ("example.com", "referral")][row_index]
        return {
            "rank": row_index + 1,
            "source": source,
            "medium": medium,
            "source_medium": f"{source} / {medium}",
            "label": f"{source} / {medium}",
            "metrics": {"sessions": base, "users": base - 13, "engagement_rate": 0.58 - row_index * 0.02},
        }
    if contract.section_key == "ga4_top_landing_pages":
        path, title = [("/", "Home"), ("/services/", "Services"), ("/contact/", "Contact")][row_index]
        return {
            "rank": row_index + 1,
            "path": path,
            "label": f"{title} ({path})",
            "metrics": {"sessions": base, "users": base - 19, "engaged_sessions": base - 31},
        }
    path, title = [("/", "Home"), ("/blog/local-seo/", "Local SEO Guide"), ("/services/web-design/", "Web Design")][row_index]
    return {
        "rank": row_index + 1,
        "path": path,
        "page_title": title,
        "label": f"{title} ({path})",
        "metrics": {"views": base + 75, "users": base - 7, "event_count": base + 21},
    }


def _compact_metric(metric_key: str, value: Any) -> dict[str, str]:
    value_type = METRIC_DEFINITIONS[metric_key]["value_type"]
    return {
        "key": metric_key,
        "label": METRIC_LABELS[metric_key],
        "value": _format_metric(value, str(value_type)),
    }


def _display_label(row: dict[str, Any], contract: RankedExactRangeContract) -> str:
    if contract.section_key == "ga4_top_sources":
        return str(row.get("source_medium") or f"{row.get('source')} / {row.get('medium')}")
    if contract.section_key in {"ga4_top_landing_pages", "ga4_most_viewed_pages"}:
        title = row.get("page_title")
        path = row.get("path")
        return f"{title} ({path})" if title else str(path)
    return str(row.get("channel"))


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
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"
