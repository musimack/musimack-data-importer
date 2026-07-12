from __future__ import annotations

import hashlib
import math
from datetime import date
from typing import Any, Protocol

from src.client_report_gsc_exact_ranges import (
    GSC_EXACT_RANGE_CONTRACTS,
    GSC_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
    PROTOTYPE_RANGES,
    validate_gsc_exact_range_contract,
)


class GscExactRangeClient(Protocol):
    def query_exact_range_summary(self, start_date: str, end_date: str) -> dict[str, Any]: ...
    def query_exact_range_queries(self, start_date: str, end_date: str) -> dict[str, Any]: ...
    def query_exact_range_pages(self, start_date: str, end_date: str) -> dict[str, Any]: ...


def build_all_gsc_exact_ranges_from_provider(
    client: GscExactRangeClient,
    *,
    client_slug: str,
    report_start: str,
    report_end: str,
    available_through_date: str,
    timezone: str = "America/Los_Angeles",
) -> dict[str, dict[str, Any]]:
    return {
        schema: build_gsc_exact_range_from_provider(
            client,
            schema_version=schema,
            client_slug=client_slug,
            report_start=report_start,
            report_end=report_end,
            available_through_date=available_through_date,
            timezone=timezone,
        )
        for schema in GSC_EXACT_RANGE_CONTRACTS
    }


def build_gsc_exact_range_from_provider(
    client: GscExactRangeClient,
    *,
    schema_version: str,
    client_slug: str,
    report_start: str,
    report_end: str,
    available_through_date: str,
    timezone: str,
) -> dict[str, Any]:
    contract = GSC_EXACT_RANGE_CONTRACTS[schema_version]
    available_through = date.fromisoformat(available_through_date)
    ranges = []
    provider_calls = 0
    for range_key, start_raw, end_raw in PROTOTYPE_RANGES:
        start, requested_end = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
        entry: dict[str, Any] = {
            "range_key": range_key,
            "requested_start_date": start_raw,
            "requested_end_date": end_raw,
            "inclusive_dates": True,
            "search_type": "web",
            "available_through_date": available_through_date,
            "expected_lag_days": 3,
            "source_identity": _range_identity(client_slug, contract.section_key, range_key, start_raw, end_raw),
        }
        if available_through < start:
            entry.update(
                actual_coverage_start_date=None,
                actual_coverage_end_date=None,
                data_state="unavailable",
                coverage_state="unavailable",
                freshness_state="unavailable",
                quality_state="unavailable",
            )
            entry["summary_metrics" if contract.row_field is None else contract.row_field] = {} if contract.row_field is None else []
            ranges.append(entry)
            continue
        effective_end = min(requested_end, available_through)
        response = _query(client, contract.dimension, start_raw, effective_end.isoformat())
        provider_calls += 1
        partial = effective_end < requested_end
        entry.update(
            actual_coverage_start_date=start_raw,
            actual_coverage_end_date=effective_end.isoformat(),
            data_state="partial" if partial else "available",
            coverage_state="partial" if partial else "complete",
            freshness_state="partial" if partial else "complete",
            quality_state="partial" if partial else "passed",
        )
        if contract.row_field is None:
            rows = _response_rows(response)
            metrics = _provider_metrics(rows[0]) if rows else _zero_metrics()
            entry["summary_metrics"] = metrics
            entry["summary_source"] = "provider_total_row_equivalent"
            if not rows and not partial:
                entry.update(data_state="empty", coverage_state="empty", quality_state="empty")
        else:
            rows = [_ranked_row(row, contract.dimension or "") for row in _response_rows(response)]
            rows = sorted(rows, key=lambda row: (-row["clicks"], row[contract.dimension or ""]))[: contract.row_limit]
            entry[contract.row_field] = rows
            if not rows and not partial:
                entry.update(data_state="empty", coverage_state="empty", quality_state="empty")
        ranges.append(entry)

    fingerprint = hashlib.sha256(
        f"{schema_version}:web:{contract.dimension or 'total'}:{contract.row_limit}:provider.v1".encode()
    ).hexdigest()
    payload = {
        "schema_version": schema_version,
        "dataset_version": schema_version,
        "provider": "gsc",
        "provider_family": "google_search_console",
        "report_type": contract.report_type,
        "data_scope": contract.data_scope,
        "dataset_purpose": contract.section_key,
        "section_key": contract.section_key,
        "search_type": "web",
        "report_period": {"start_date": report_start, "end_date": report_end},
        "inclusive_dates": True,
        "timezone": timezone,
        "provider_date_semantics": "property_local_date",
        "calculation_version": GSC_EXACT_RANGE_PROVIDER_CALCULATION_VERSION,
        "source_identity": {"source_kind": "provider_exact_range", "client_slug": client_slug},
        "query_identity": {"shape_id": f"{schema_version}.provider", "fingerprint": fingerprint},
        "dimensions": [] if contract.dimension is None else [contract.dimension],
        "metrics": ["clicks", "impressions", "ctr", "average_position"],
        "sort": None if contract.sort_metric is None else {"metric": "clicks", "direction": "descending", "tie_breaker": contract.dimension, "tie_direction": "ascending"},
        "row_limit": contract.row_limit,
        "ranges": ranges,
        "generation_metadata": {"mode": "provider_exact_range", "provider_calls": provider_calls},
        "sanitized_source_metadata": {"contains_real_data": True, "raw_provider_payload_included": False},
    }
    validate_gsc_exact_range_contract(payload)
    return payload


def _query(client: GscExactRangeClient, dimension: str | None, start: str, end: str) -> dict[str, Any]:
    if dimension is None:
        return client.query_exact_range_summary(start, end)
    if dimension == "query":
        return client.query_exact_range_queries(start, end)
    return client.query_exact_range_pages(start, end)


def _response_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = response.get("rows", [])
    if rows is None:
        return []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("GSC exact-range provider response rows are malformed")
    return rows


def _ranked_row(row: dict[str, Any], dimension: str) -> dict[str, Any]:
    keys = row.get("keys")
    if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str) or not keys[0].strip():
        raise ValueError("GSC exact-range provider row dimension is malformed")
    return {dimension: keys[0], **_provider_metrics(row)}


def _provider_metrics(row: dict[str, Any]) -> dict[str, Any]:
    values = {key: row.get(source) for key, source in (("clicks", "clicks"), ("impressions", "impressions"), ("ctr", "ctr"), ("average_position", "position"))}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
        raise ValueError("GSC exact-range provider metric values are malformed")
    clicks, impressions = int(round(values["clicks"])), int(round(values["impressions"]))
    ctr = 0.0 if impressions == 0 else clicks / impressions
    return {"clicks": clicks, "impressions": impressions, "ctr": ctr, "average_position": float(values["average_position"])}


def _zero_metrics() -> dict[str, Any]:
    return {"clicks": 0, "impressions": 0, "ctr": 0.0, "average_position": 0.0}


def _range_identity(client_slug: str, section: str, key: str, start: str, end: str) -> str:
    return hashlib.sha256(f"{client_slug}:{section}:{key}:{start}:{end}:provider.v1".encode()).hexdigest()
