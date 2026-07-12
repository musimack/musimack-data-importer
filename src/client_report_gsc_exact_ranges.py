from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from typing import Any


GSC_EXACT_RANGE_CALCULATION_VERSION = "gsc_exact_ranges.synthetic.v1"
GSC_EXACT_RANGE_PROVIDER_CALCULATION_VERSION = "gsc_exact_ranges.provider.v1"
GSC_EXACT_RANGE_CALCULATION_VERSIONS = {
    GSC_EXACT_RANGE_CALCULATION_VERSION,
    GSC_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
}
PROTOTYPE_RANGES = (
    ("last_7_days", "2026-07-02", "2026-07-08"),
    ("last_30_days", "2026-06-09", "2026-07-08"),
    ("this_month", "2026-07-01", "2026-07-08"),
    ("last_month", "2026-06-01", "2026-06-30"),
)


@dataclass(frozen=True)
class GscExactRangeContract:
    schema_version: str
    section_key: str
    report_type: str
    data_scope: str
    dimension: str | None
    row_field: str | None
    sort_metric: str | None
    row_limit: int


GSC_EXACT_RANGE_CONTRACTS = {
    "gsc_summary_exact_ranges.v1": GscExactRangeContract(
        "gsc_summary_exact_ranges.v1", "gsc_summary", "summary_exact_ranges",
        "search_summary", None, None, None, 0,
    ),
    "gsc_top_queries_exact_ranges.v1": GscExactRangeContract(
        "gsc_top_queries_exact_ranges.v1", "gsc_top_queries", "top_queries_exact_ranges",
        "query", "query", "query_rows", "clicks", 10,
    ),
    "gsc_top_pages_exact_ranges.v1": GscExactRangeContract(
        "gsc_top_pages_exact_ranges.v1", "gsc_top_pages", "top_pages_exact_ranges",
        "page", "page", "page_rows", "clicks", 10,
    ),
}
GSC_EXACT_RANGE_SOURCE_BY_SECTION = {v.section_key: k for k, v in GSC_EXACT_RANGE_CONTRACTS.items()}
GSC_EXACT_RANGE_SOURCE_FILES = {k: f"{k}.json" for k in GSC_EXACT_RANGE_CONTRACTS}


def build_fake_gsc_exact_range_dataset(
    schema_version: str, *, client_slug: str = "synthetic-client",
    report_start: str = "2026-01-01", report_end: str = "2026-07-08",
) -> dict[str, Any]:
    contract = _contract(schema_version)
    ranges = []
    for index, (range_key, start, end) in enumerate(PROTOTYPE_RANGES):
        clicks = 710 + index * 137
        impressions = 7100 + index * 911
        entry: dict[str, Any] = {
            "range_key": range_key, "requested_start_date": start, "requested_end_date": end,
            "inclusive_dates": True, "search_type": "web",
            "available_through_date": end, "actual_coverage_start_date": start,
            "actual_coverage_end_date": end, "expected_lag_days": 3,
            "data_state": "available", "coverage_state": "complete",
            "freshness_state": "complete", "quality_state": "passed",
            "source_identity": f"{client_slug}:{contract.section_key}:{range_key}:{start}:{end}",
        }
        if contract.row_field is None:
            entry["summary_metrics"] = _metrics(clicks, impressions, 4.25 + index / 10)
            entry["summary_source"] = "provider_total_row_equivalent"
        else:
            prefix = "synthetic query" if contract.dimension == "query" else "https://synthetic.example/gsc-page"
            rows = []
            for row_index in range(3):
                row_clicks = 90 - row_index * 20 + index
                row_impressions = 900 - row_index * 100 + index * 10
                identity = f"{prefix}-{index + 1}-{row_index + 1}"
                rows.append({contract.dimension: identity, **_metrics(row_clicks, row_impressions, 2.1 + row_index)})
            entry[contract.row_field] = rows
        ranges.append(entry)
    fingerprint = hashlib.sha256(f"{schema_version}:{client_slug}:web:v1".encode()).hexdigest()
    payload = {
        "schema_version": schema_version, "dataset_version": schema_version,
        "provider": "gsc", "provider_family": "google_search_console",
        "report_type": contract.report_type, "data_scope": contract.data_scope,
        "dataset_purpose": contract.section_key, "section_key": contract.section_key,
        "search_type": "web", "report_period": {"start_date": report_start, "end_date": report_end},
        "inclusive_dates": True, "timezone": "America/Los_Angeles",
        "provider_date_semantics": "property_local_date",
        "calculation_version": GSC_EXACT_RANGE_CALCULATION_VERSION,
        "source_identity": {"source_kind": "synthetic_fixture", "client_slug": client_slug},
        "query_identity": {"shape_id": f"{schema_version}.synthetic", "fingerprint": fingerprint},
        "dimensions": [] if contract.dimension is None else [contract.dimension],
        "metrics": ["clicks", "impressions", "ctr", "average_position"],
        "sort": None if contract.sort_metric is None else {"metric": contract.sort_metric, "direction": "descending", "tie_breaker": contract.dimension, "tie_direction": "ascending"},
        "row_limit": contract.row_limit, "ranges": ranges,
        "generation_metadata": {"mode": "synthetic_fixture", "provider_calls": 0},
        "sanitized_source_metadata": {"contains_real_data": False, "raw_provider_payload_included": False},
    }
    validate_gsc_exact_range_contract(payload)
    return payload


def validate_gsc_exact_range_contract(payload: dict[str, Any]) -> None:
    contract = _contract(payload.get("schema_version"))
    required_equal = {
        "dataset_version": contract.schema_version, "provider": "gsc",
        "provider_family": "google_search_console", "report_type": contract.report_type,
        "data_scope": contract.data_scope, "section_key": contract.section_key,
        "search_type": "web", "inclusive_dates": True,
        "calculation_version": payload.get("calculation_version"),
        "row_limit": contract.row_limit,
    }
    for key, expected in required_equal.items():
        if payload.get(key) != expected:
            raise ValueError(f"GSC exact-range {key} is invalid")
    if payload.get("calculation_version") not in GSC_EXACT_RANGE_CALCULATION_VERSIONS:
        raise ValueError("GSC exact-range calculation_version is invalid")
    if payload.get("dimensions") != ([] if contract.dimension is None else [contract.dimension]):
        raise ValueError("GSC exact-range dimensions do not match section scope")
    if payload.get("metrics") != ["clicks", "impressions", "ctr", "average_position"]:
        raise ValueError("GSC exact-range metrics are invalid")
    if not isinstance(payload.get("source_identity"), dict) or not isinstance(payload.get("query_identity"), dict):
        raise ValueError("GSC exact-range deterministic identities are required")
    period = payload.get("report_period")
    if not isinstance(period, dict): raise ValueError("GSC exact-range report_period is required")
    period_start, period_end = _date(period.get("start_date")), _date(period.get("end_date"))
    ranges = payload.get("ranges")
    if not isinstance(ranges, list): raise ValueError("GSC exact-range ranges must be a list")
    seen = set()
    for index, entry in enumerate(ranges):
        _validate_entry(entry, index, contract, period_start, period_end, seen)


def exact_range_entry_for(payload: dict[str, Any], *, range_key: str, start_date: str, end_date: str) -> dict[str, Any] | None:
    return next((x for x in payload.get("ranges", []) if isinstance(x, dict) and x.get("range_key") == range_key and x.get("requested_start_date") == start_date and x.get("requested_end_date") == end_date), None)


def display_data_for_section(entry: dict[str, Any], section_key: str) -> dict[str, Any] | None:
    if entry.get("data_state") != "available": return None
    if section_key == "gsc_summary":
        metrics = entry.get("summary_metrics")
        if not isinstance(metrics, dict): return None
        return {"metrics": [
            {"key": "clicks", "label": "Clicks", "value": f"{metrics['clicks']:,}"},
            {"key": "impressions", "label": "Impressions", "value": f"{metrics['impressions']:,}"},
            {"key": "ctr", "label": "CTR", "value": f"{metrics['ctr'] * 100:.2f}%"},
            {"key": "average_position", "label": "Average Position", "value": f"{metrics['average_position']:.2f}"},
        ]}
    contract = _contract(GSC_EXACT_RANGE_SOURCE_BY_SECTION.get(section_key))
    rows = entry.get(contract.row_field or "")
    return {"queries" if section_key == "gsc_top_queries" else "pages": rows} if isinstance(rows, list) else None


def _validate_entry(entry: Any, index: int, contract: GscExactRangeContract, period_start: date, period_end: date, seen: set) -> None:
    if not isinstance(entry, dict): raise ValueError(f"GSC exact-range ranges[{index}] must be an object")
    start, end = _date(entry.get("requested_start_date")), _date(entry.get("requested_end_date"))
    identity = (entry.get("range_key"), start, end)
    if start > end or start < period_start or end > period_end: raise ValueError("GSC exact-range dates are invalid")
    if identity in seen: raise ValueError("duplicate GSC exact-range identity")
    seen.add(identity)
    if entry.get("search_type") != "web" or entry.get("inclusive_dates") is not True: raise ValueError("GSC exact-range search/date semantics are invalid")
    state, coverage, freshness = entry.get("data_state"), entry.get("coverage_state"), entry.get("freshness_state")
    allowed = {"available", "empty", "partial", "unavailable"}
    if state not in allowed or coverage not in {"complete", "empty", "partial", "unavailable"} or freshness not in {"complete", "partial", "unavailable"}: raise ValueError("GSC exact-range state is invalid")
    available_through = entry.get("available_through_date")
    actual_end = entry.get("actual_coverage_end_date")
    if state == "available" and (coverage != "complete" or freshness != "complete" or actual_end != entry.get("requested_end_date") or not isinstance(available_through, str) or _date(available_through) < end): raise ValueError("complete GSC exact-range has a freshness gap")
    if state == "partial" and (coverage != "partial" or freshness != "partial" or not isinstance(actual_end, str) or actual_end >= entry.get("requested_end_date")): raise ValueError("partial GSC exact-range freshness is contradictory")
    content_key = "summary_metrics" if contract.row_field is None else contract.row_field
    content = entry.get(content_key)
    if state == "unavailable":
        if content not in (None, {}, []): raise ValueError("unavailable GSC exact-range contains data")
        return
    if contract.row_field is None:
        if entry.get("summary_source") != "provider_total_row_equivalent": raise ValueError("GSC summary must use total-level source metrics")
        _validate_metrics(content, "summary")
        if state == "empty" and any(content.values()): raise ValueError("empty GSC summary contains activity")
    else:
        if not isinstance(content, list): raise ValueError("GSC ranked rows must be a list")
        if state == "empty" and content: raise ValueError("empty GSC ranked dataset contains rows")
        if len(content) > contract.row_limit: raise ValueError("GSC ranked row limit exceeded")
        identities = []
        for row in content:
            if not isinstance(row, dict) or not isinstance(row.get(contract.dimension), str) or not row[contract.dimension].strip(): raise ValueError("GSC ranked row dimension is missing")
            if ("page" if contract.dimension == "query" else "query") in row: raise ValueError("GSC ranked row uses wrong scope")
            identities.append(row[contract.dimension])
            _validate_metrics(row, "row")
        if len(identities) != len(set(identities)): raise ValueError("duplicate GSC ranked row identity")
        expected = sorted(content, key=lambda row: (-row["clicks"], row[contract.dimension]))
        if content != expected: raise ValueError("GSC ranked rows are not deterministically sorted")


def _validate_metrics(metrics: Any, label: str) -> None:
    if not isinstance(metrics, dict): raise ValueError(f"GSC {label} metrics are required")
    for key in ("clicks", "impressions", "ctr", "average_position"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0: raise ValueError(f"GSC {label} {key} is invalid")
    if not float(metrics["clicks"]).is_integer() or not float(metrics["impressions"]).is_integer() or metrics["clicks"] > metrics["impressions"]: raise ValueError("GSC clicks/impressions are contradictory")
    expected_ctr = 0.0 if metrics["impressions"] == 0 else metrics["clicks"] / metrics["impressions"]
    if metrics["ctr"] > 1 or not math.isclose(metrics["ctr"], expected_ctr, abs_tol=1e-9): raise ValueError("GSC CTR is inconsistent")


def _metrics(clicks: int, impressions: int, average_position: float) -> dict[str, Any]:
    return {"clicks": clicks, "impressions": impressions, "ctr": 0.0 if impressions == 0 else clicks / impressions, "average_position": average_position}


def _contract(schema_version: Any) -> GscExactRangeContract:
    contract = GSC_EXACT_RANGE_CONTRACTS.get(schema_version)
    if contract is None: raise ValueError("unsupported GSC exact-range schema_version")
    return contract


def _date(value: Any) -> date:
    if not isinstance(value, str): raise ValueError("GSC exact-range date must be ISO")
    try: return date.fromisoformat(value)
    except ValueError as exc: raise ValueError("GSC exact-range date must be ISO") from exc
