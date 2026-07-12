from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.client_report_ga4_exact_ranges import (
    GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE,
    GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
    validate_ga4_exact_range_summary_contract,
)
from src.client_report_ga4_ranked_exact_ranges import (
    RANKED_EXACT_RANGE_SOURCE_FILES,
    contract_for_ranked_exact_schema,
    validate_ga4_ranked_exact_range_contract,
)
from src.client_report_presentation_ranges import build_client_report_presentation_ranges
from src.client_report_publisher_contracts import CANONICAL_DATASET_CONTRACTS


HANDOFF_MANIFEST_VERSION = "client_report_publisher_handoff_manifest.v1"
DEFAULT_OUTPUT_ROOT = Path("exports") / "local-real" / "client-report-publisher-handoff"
DEFAULT_SOURCE_ROOT = Path("exports") / "local-real" / "dashboard-lab"
DAILY_SERIES_COVERAGE_VERSION = "daily_series_coverage.v1"
DAILY_SERIES_TIMEZONE = "provider_local_unspecified"


@dataclass(frozen=True)
class HandoffWriteResult:
    output_dir: Path
    files: list[Path]
    skipped: list[str]


def write_client_report_publisher_handoff(
    *,
    profile: str,
    client_name: str,
    source_dir: Path | None = None,
    output_dir: Path | None = None,
    ga4_summary_path: Path | None = None,
    ga4_snapshot_path: Path | None = None,
    gsc_summary_path: Path | None = None,
) -> HandoffWriteResult:
    source = source_dir or DEFAULT_SOURCE_ROOT / profile
    output = output_dir or DEFAULT_OUTPUT_ROOT / profile
    ga4_snapshot = _load_json_object(ga4_snapshot_path or source / "ga4-snapshot.json")
    if ga4_summary_path:
        ga4_summary = _load_json_object(ga4_summary_path)
    elif ga4_snapshot_path:
        ga4_summary = _ga4_summary_from_snapshot(ga4_snapshot)
    else:
        ga4_summary = _load_json_object(source / "ga4-summary.json")
    gsc_summary = _load_json_object(gsc_summary_path or source / "gsc-summary.json")

    period = _period_from_payloads(ga4_summary, gsc_summary)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output.mkdir(parents=True, exist_ok=True)

    generated: list[tuple[Path, dict[str, Any], str, str, str]] = []
    skipped: list[str] = []
    generated_datasets: dict[str, dict[str, Any]] = {}

    ga4_metric_display = _build_ga4_metric_display(profile, client_name, ga4_summary, period)
    generated_datasets["ga4_metric_display.v1"] = ga4_metric_display
    generated.append(
        (
            output / "ga4_metric_display.v1.json",
            ga4_metric_display,
            "ga4",
            "metric_display",
            "ga4_metric_display.v1",
        )
    )

    page_rows = list(ga4_summary.get("top_pages") or [])
    if page_rows:
        most_viewed_pages = _build_ga4_most_viewed_pages(profile, ga4_summary, period)
        generated_datasets["ga4_most_viewed_pages_display.v1"] = most_viewed_pages
        generated.append(
            (
                output / "ga4_most_viewed_pages_display.v1.json",
                most_viewed_pages,
                "ga4",
                "most_viewed_pages_display",
                "ga4_most_viewed_pages_display.v1",
            )
        )
    else:
        skipped.append("ga4_most_viewed_pages_display.v1: no sanitized top page rows available")

    source_rows = _top_sources_from_summary_or_snapshot(ga4_summary, ga4_snapshot)
    if source_rows:
        top_sources = _build_ga4_top_sources(profile, source_rows, period)
        generated_datasets["ga4_top_sources_display.v1"] = top_sources
        generated.append(
            (
                output / "ga4_top_sources_display.v1.json",
                top_sources,
                "ga4",
                "top_sources_display",
                "ga4_top_sources_display.v1",
            )
        )
    else:
        skipped.append("ga4_top_sources_display.v1: true source/source-medium rows unavailable")

    landing_page_rows = _top_landing_pages_from_summary_or_snapshot(ga4_summary, ga4_snapshot)
    if landing_page_rows:
        top_landing_pages = _build_ga4_top_landing_pages(profile, landing_page_rows, period)
        generated_datasets["ga4_top_landing_pages_display.v1"] = top_landing_pages
        generated.append(
            (
                output / "ga4_top_landing_pages_display.v1.json",
                top_landing_pages,
                "ga4",
                "top_landing_pages_display",
                "ga4_top_landing_pages_display.v1",
            )
        )
    else:
        skipped.append("ga4_top_landing_pages_display.v1: landing-page scoped rows unavailable")

    gsc_summary_display = _build_gsc_summary_display(profile, gsc_summary, period)
    generated_datasets["gsc_summary_display.v1"] = gsc_summary_display
    generated.append(
        (
            output / "gsc_summary_display.v1.json",
            gsc_summary_display,
            "gsc",
            "summary_display",
            "gsc_summary_display.v1",
        )
    )
    gsc_queries_display = _build_gsc_queries_display(profile, gsc_summary, period)
    generated_datasets["gsc_queries_display.v1"] = gsc_queries_display
    ga4_exact_ranges_path = source / "ga4_metric_display_exact_ranges.v1.json"
    if ga4_exact_ranges_path.exists():
        ga4_exact_ranges = _load_json_object(ga4_exact_ranges_path)
        validate_ga4_exact_range_summary_contract(ga4_exact_ranges)
        _require_exact_source_period(ga4_exact_ranges, period)
        generated_datasets[GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION] = ga4_exact_ranges
        generated.append(
            (
                output / "ga4_metric_display_exact_ranges.v1.json",
                ga4_exact_ranges,
                "ga4",
                GA4_EXACT_RANGE_SUMMARY_REPORT_TYPE,
                GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
            )
        )
    for schema_version, file_name in RANKED_EXACT_RANGE_SOURCE_FILES.items():
        ranked_exact_ranges_path = source / file_name
        if not ranked_exact_ranges_path.exists():
            continue
        ranked_exact_ranges = _load_json_object(ranked_exact_ranges_path)
        validate_ga4_ranked_exact_range_contract(ranked_exact_ranges)
        _require_exact_source_period(ranked_exact_ranges, period)
        contract = contract_for_ranked_exact_schema(schema_version)
        if contract is None:
            raise ValueError(f"unsupported ranked exact-range source: {schema_version}")
        generated_datasets[schema_version] = ranked_exact_ranges
        generated.append(
            (
                output / file_name,
                ranked_exact_ranges,
                "ga4",
                contract.report_type,
                schema_version,
            )
        )
    exact_ranges_path = source / "presentation-exact-ranges.v1.json"
    if exact_ranges_path.exists():
        generated_datasets["presentation_exact_ranges.v1"] = _load_json_object(exact_ranges_path)
    generated.append(
        (
            output / "gsc_queries_display.v1.json",
            gsc_queries_display,
            "gsc",
            "queries_display",
            "gsc_queries_display.v1",
        )
    )
    presentation_ranges = build_client_report_presentation_ranges(
        client_slug=profile,
        period=period,
        datasets=generated_datasets,
    )
    generated.append(
        (
            output / "client_report_presentation_ranges.v2.json",
            presentation_ranges,
            "presentation",
            "range_dataset",
            "client_report_presentation_ranges.v2",
        )
    )

    files: list[Path] = []
    manifest_files = []
    versions = []
    for path, payload, provider, report_type, schema_version in generated:
        _write_json(path, payload)
        files.append(path)
        manifest_files.append(
            {
                "path": path.name,
                "provider": provider,
                "report_type": report_type,
                "schema_version": schema_version,
            }
        )
        versions.append(schema_version)

    manifest = {
        "schema_version": HANDOFF_MANIFEST_VERSION,
        "client_slug": profile,
        "client_name": client_name,
        "period_start": period["start"],
        "period_end": period["end"],
        "generated_at": generated_at,
        "files": sorted(manifest_files, key=lambda item: item["path"]),
        "display_contract_versions": sorted(versions),
        "validation_status": "generated_not_validated",
        "warnings": skipped,
        "sanitized_source_names": ["ga4", "gsc"],
    }
    manifest_path = output / "manifest.json"
    _write_json(manifest_path, manifest)
    files.insert(0, manifest_path)
    return HandoffWriteResult(output_dir=output, files=files, skipped=skipped)


def _build_ga4_metric_display(
    profile: str,
    client_name: str,
    ga4_summary: dict[str, Any],
    period: dict[str, str],
) -> dict[str, Any]:
    metrics = ga4_summary.get("summary_metrics") or {}
    daily_rows, daily_coverage = _daily_series_rows_and_coverage(ga4_summary, period)
    contract = CANONICAL_DATASET_CONTRACTS["ga4_metric_display.v1"]
    return {
        "schema_version": "ga4_metric_display.v1",
        "provider": "ga4",
        "report_type": "metric_display",
        "data_scope": contract.data_scope,
        "data_state": "available" if metrics or daily_rows or ga4_summary.get("traffic_channels") else "empty",
        "client_slug": profile,
        "client_name": client_name,
        "report_period": _report_period(period),
        "daily_series_coverage": daily_coverage,
        "metric_cards": [
            _metric_card("users", "Website Visitors", metrics.get("users"), "count"),
            _metric_card("sessions", "Visits", metrics.get("sessions"), "count"),
            _metric_card("views", "Page Views", metrics.get("views"), "count"),
            _metric_card("engagement_rate", "Engagement Rate", metrics.get("engagement_rate"), "percent"),
            _metric_card(
                "average_session_duration_seconds",
                "Average Session Duration",
                metrics.get("average_session_duration_seconds"),
                "seconds",
            ),
            _metric_card("key_events", "Key Actions", metrics.get("key_events"), "count"),
            _metric_card("conversions", "Conversions", metrics.get("conversions"), "count"),
        ],
        "trend_charts": [
            {
                "key": "website_traffic_trend",
                "title": "Website traffic trend",
                "chart_type": "line",
                "grain": "day",
                "series": [
                    {
                        "key": "users",
                        "label": "Website Visitors",
                        "unit": "count",
                        "points": _trend_points(daily_rows, "users"),
                    },
                    {
                        "key": "sessions",
                        "label": "Visits",
                        "unit": "count",
                        "points": _trend_points(daily_rows, "sessions"),
                    },
                ],
                "availability": "available",
            }
        ],
        "breakdowns": [
            {
                "key": "top_traffic_channels",
                "title": "Top traffic channels",
                "display_type": "ranked_list",
                "rows": [
                    {
                        "rank": index + 1,
                        "label": str(row.get("channel") or "Unknown"),
                        "metrics": [
                            _compact_metric("sessions", "Visits", row.get("sessions"), "count"),
                            _compact_metric("users", "Website Visitors", row.get("users"), "count"),
                            _compact_metric("engagement_rate", "Engagement Rate", row.get("engagement_rate"), "percent"),
                        ],
                    }
                    for index, row in enumerate((ga4_summary.get("traffic_channels") or [])[:10])
                ],
                "availability": "available",
            }
        ],
        "notes": [
            "Generated from sanitized local-real GA4 summary output.",
            "Top Traffic Channels are broad channel rows and are not labeled as Top Sources.",
        ],
    }


def _build_ga4_most_viewed_pages(
    profile: str,
    ga4_summary: dict[str, Any],
    period: dict[str, str],
) -> dict[str, Any]:
    contract = CANONICAL_DATASET_CONTRACTS["ga4_most_viewed_pages_display.v1"]
    return {
        "schema_version": "ga4_most_viewed_pages_display.v1",
        "provider": "ga4",
        "report_type": "most_viewed_pages_display",
        "data_scope": contract.data_scope,
        "data_state": "available",
        "client_slug": profile,
        "report_period": _report_period(period),
        "rows": [
            {
                "rank": index + 1,
                "path": str(row.get("path") or ""),
                "label": str(row.get("label") or row.get("title") or row.get("path") or "Untitled page"),
                "views": _number_or_none(row.get("views")),
                "users": _number_or_none(row.get("users")),
                "event_count": _number_or_none(row.get("event_count")),
            }
            for index, row in enumerate((ga4_summary.get("top_pages") or [])[:10])
        ],
        "notes": [
            "Generated from broad page popularity rows.",
            "These rows are not labeled as Top Landing Pages.",
        ],
    }


def _build_ga4_top_sources(
    profile: str,
    source_rows: list[dict[str, Any]],
    period: dict[str, str],
) -> dict[str, Any]:
    contract = CANONICAL_DATASET_CONTRACTS["ga4_top_sources_display.v1"]
    return {
        "schema_version": "ga4_top_sources_display.v1",
        "provider": "ga4",
        "report_type": "top_sources_display",
        "data_scope": contract.data_scope,
        "data_state": "available",
        "client_slug": profile,
        "report_period": _report_period(period),
        "rows": [
            {
                "rank": index + 1,
                "label": str(row.get("label") or "(not set)"),
                "sessions": _number_or_none(row.get("sessions")),
                "users": _number_or_none(row.get("users")),
                "engagement_rate": _number_or_none(row.get("engagement_rate")),
                "average_session_duration_seconds": _number_or_none(
                    row.get("average_session_duration_seconds")
                ),
                "event_count": _number_or_none(row.get("event_count")),
                "key_events": _number_or_none(row.get("key_events")),
                "conversions": _number_or_none(row.get("conversions")),
            }
            for index, row in enumerate(source_rows[:10])
        ],
        "notes": [
            "Generated from GA4 sessionSourceMedium rows.",
            "These rows are true source/source-medium rows and are not broad traffic channels.",
        ],
    }


def _build_ga4_top_landing_pages(
    profile: str,
    landing_page_rows: list[dict[str, Any]],
    period: dict[str, str],
) -> dict[str, Any]:
    contract = CANONICAL_DATASET_CONTRACTS["ga4_top_landing_pages_display.v1"]
    return {
        "schema_version": "ga4_top_landing_pages_display.v1",
        "provider": "ga4",
        "report_type": "top_landing_pages_display",
        "data_scope": contract.data_scope,
        "data_state": "available",
        "client_slug": profile,
        "report_period": _report_period(period),
        "rows": [
            {
                "rank": index + 1,
                "path": str(row.get("path") or ""),
                "label": str(row.get("label") or row.get("path") or "Untitled landing page"),
                "sessions": _number_or_none(row.get("sessions")),
                "users": _number_or_none(row.get("users")),
                "engaged_sessions": _number_or_none(row.get("engaged_sessions")),
                "engagement_rate": _number_or_none(row.get("engagement_rate")),
                "average_session_duration_seconds": _number_or_none(
                    row.get("average_session_duration_seconds")
                ),
                "event_count": _number_or_none(row.get("event_count")),
                "key_events": _number_or_none(row.get("key_events")),
                "conversions": _number_or_none(row.get("conversions")),
            }
            for index, row in enumerate(landing_page_rows[:10])
        ],
        "notes": [
            "Generated from GA4 landingPagePlusQueryString rows.",
            "These rows are landing-page scoped rows and are not broad most-viewed page rows.",
        ],
    }


def _build_gsc_summary_display(
    profile: str,
    gsc_summary: dict[str, Any],
    period: dict[str, str],
) -> dict[str, Any]:
    metrics = gsc_summary.get("summary_metrics") or {}
    daily_rows, daily_coverage = _daily_series_rows_and_coverage(gsc_summary, period)
    contract = CANONICAL_DATASET_CONTRACTS["gsc_summary_display.v1"]
    return {
        "schema_version": "gsc_summary_display.v1",
        "provider": "gsc",
        "report_type": "summary_display",
        "data_scope": contract.data_scope,
        "data_state": "available" if metrics or daily_rows else "empty",
        "client_slug": profile,
        "report_period": _report_period(period),
        "daily_series_coverage": daily_coverage,
        "summary_metrics": {
            "clicks": _number_or_none(metrics.get("clicks")),
            "impressions": _number_or_none(metrics.get("impressions")),
            "ctr": _number_or_none(metrics.get("ctr")),
            "average_position": _number_or_none(metrics.get("average_position")),
        },
        "trend_points": [
            {
                "date": row.get("date"),
                "clicks": _number_or_none(row.get("clicks")),
                "impressions": _number_or_none(row.get("impressions")),
                "ctr": _number_or_none(row.get("ctr")),
                "average_position": _number_or_none(row.get("average_position")),
            }
            for row in daily_rows
        ],
        "notes": ["Generated from sanitized local-real GSC summary output."],
    }


def _build_gsc_queries_display(
    profile: str,
    gsc_summary: dict[str, Any],
    period: dict[str, str],
) -> dict[str, Any]:
    query_rows = gsc_summary.get("top_queries") or []
    page_rows = gsc_summary.get("top_pages") or []
    contract = CANONICAL_DATASET_CONTRACTS["gsc_queries_display.v1"]
    return {
        "schema_version": "gsc_queries_display.v1",
        "provider": "gsc",
        "report_type": "queries_display",
        "data_scope": contract.data_scope,
        "data_state": "available" if query_rows or page_rows else "empty",
        "client_slug": profile,
        "report_period": _report_period(period),
        "query_rows": [
            {
                "rank": index + 1,
                "query": str(row.get("query") or ""),
                "clicks": _number_or_none(row.get("clicks")),
                "impressions": _number_or_none(row.get("impressions")),
                "ctr": _number_or_none(row.get("ctr")),
                "average_position": _number_or_none(row.get("average_position")),
            }
            for index, row in enumerate(query_rows[:20])
        ],
        "page_rows": [
            {
                "rank": index + 1,
                "page": str(row.get("path") or ""),
                "clicks": _number_or_none(row.get("clicks")),
                "impressions": _number_or_none(row.get("impressions")),
                "ctr": _number_or_none(row.get("ctr")),
                "average_position": _number_or_none(row.get("average_position")),
            }
            for index, row in enumerate(page_rows[:20])
        ],
        "notes": ["Generated from sanitized local-real GSC query and page rows."],
    }


def _period_from_payloads(*payloads: dict[str, Any]) -> dict[str, str]:
    periods = [payload.get("reporting_period") or payload.get("date_range") for payload in payloads]
    starts = [period.get("start") for period in periods if isinstance(period, dict) and period.get("start")]
    ends = [period.get("end") for period in periods if isinstance(period, dict) and period.get("end")]
    if not starts or not ends:
        raise ValueError("source summaries must include reporting_period or date_range")
    return {"start": max(starts), "end": min(ends)}


def _report_period(period: dict[str, str]) -> dict[str, str]:
    return {
        "label": f"{period['start']} through {period['end']}",
        "start": period["start"],
        "end": period["end"],
        "grain": "day",
        "data_freshness_label": "Imported local-real data",
    }


def _metric_card(key: str, label: str, value: Any, unit: str) -> dict[str, Any]:
    normalized = _number_or_none(value)
    return {
        "key": key,
        "label": label,
        "value": normalized,
        "formatted_value": _format_value(normalized, unit),
        "unit": unit,
        "availability": "available" if normalized is not None else "missing",
    }


def _compact_metric(key: str, label: str, value: Any, unit: str) -> dict[str, Any]:
    normalized = _number_or_none(value)
    return {
        "key": key,
        "label": label,
        "value": normalized,
        "formatted_value": _format_value(normalized, unit),
        "unit": unit,
    }


def _trend_points(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [
        {"date": row.get("date"), "value": _number_or_none(row.get(metric))}
        for row in rows
        if row.get("date")
    ]


def _daily_series_rows_and_coverage(
    payload: dict[str, Any],
    period: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start = _parse_iso_date(period["start"], "report period start")
    end = _parse_iso_date(period["end"], "report period end")
    expected_dates = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]

    source_present = "time_series" in payload
    raw_rows = payload.get("time_series")
    if raw_rows is None:
        rows: list[dict[str, Any]] = []
    elif not isinstance(raw_rows, list):
        raise ValueError("time_series must be a list when provided")
    else:
        rows = []
        dates: list[str] = []
        for index, row in enumerate(raw_rows):
            if not isinstance(row, dict):
                raise ValueError(f"time_series[{index}] must be an object")
            raw_date = row.get("date")
            observed_date = _parse_iso_date(raw_date, f"time_series[{index}].date")
            date_text = observed_date.isoformat()
            if observed_date < start or observed_date > end:
                raise ValueError(f"time_series[{index}].date must stay inside the report period")
            dates.append(date_text)
            rows.append(row)
        if dates != sorted(dates):
            raise ValueError("time_series dates must be in ascending order")
        if len(dates) != len(set(dates)):
            raise ValueError("time_series dates must be unique")

    serialized_dates = [str(row["date"]) for row in rows]
    expected_count = len(expected_dates)
    actual_count = len(serialized_dates)
    missing_count = expected_count - actual_count
    if not source_present:
        coverage_state = "unavailable"
        gap_state = "not_applicable"
        quality_notes = ["Source did not provide a daily observation series."]
    elif actual_count == 0:
        coverage_state = "empty"
        gap_state = "not_applicable"
        quality_notes = ["Source returned no daily observations for the requested period."]
    elif serialized_dates == expected_dates:
        coverage_state = "complete"
        gap_state = "none"
        quality_notes = []
    else:
        coverage_state = "partial"
        gap_state = "gaps_present"
        quality_notes = ["Daily observations do not cover every requested date."]

    coverage = {
        "schema_version": DAILY_SERIES_COVERAGE_VERSION,
        "grain": "day",
        "timezone": DAILY_SERIES_TIMEZONE,
        "requested_period_start": start.isoformat(),
        "requested_period_end": end.isoformat(),
        "expected_observation_count": expected_count,
        "actual_observation_count": actual_count,
        "first_observation_date": serialized_dates[0] if serialized_dates else None,
        "last_observation_date": serialized_dates[-1] if serialized_dates else None,
        "coverage_state": coverage_state,
        "gap_state": gap_state,
        "missing_observation_count": missing_count,
        "quality_notes": quality_notes,
    }
    return rows, coverage


def _parse_iso_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def _format_value(value: int | float | None, unit: str) -> str:
    if value is None:
        return "Not available"
    if unit == "percent":
        return f"{value * 100:.1f}%"
    if unit == "seconds":
        return f"{value:.0f}s"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 6)
    return None


def _top_sources_from_summary_or_snapshot(
    ga4_summary: dict[str, Any],
    ga4_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = ga4_summary.get("top_sources")
    if isinstance(rows, list) and rows:
        return [row for row in rows if isinstance(row, dict)]
    return [
        {"label": row.get("label") or "(not set)", **_dimension_metrics(row)}
        for row in _dimension_rows(ga4_snapshot, "source_medium")
    ]


def _top_landing_pages_from_summary_or_snapshot(
    ga4_summary: dict[str, Any],
    ga4_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = ga4_summary.get("top_landing_pages")
    if isinstance(rows, list) and rows:
        return [row for row in rows if isinstance(row, dict)]
    return [
        {
            "path": str(row.get("label") or ""),
            "label": str(row.get("label") or "Untitled landing page"),
            **_dimension_metrics(row),
        }
        for row in _dimension_rows(ga4_snapshot, "landing_pages")
    ]


def _dimension_rows(snapshot: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        row
        for row in snapshot.get("dimension_rows") or []
        if isinstance(row, dict) and row.get("kind") == kind
    ]


def _dimension_metrics(row: dict[str, Any]) -> dict[str, Any]:
    raw_metrics = row.get("metrics")
    if isinstance(raw_metrics, dict):
        return raw_metrics
    if not isinstance(raw_metrics, list):
        return {}
    return {
        metric.get("name"): metric.get("value")
        for metric in raw_metrics
        if isinstance(metric, dict) and metric.get("name")
    }


def _ga4_summary_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary_metrics = {
        row.get("name"): row.get("value")
        for row in snapshot.get("metrics") or []
        if isinstance(row, dict) and row.get("name")
    }
    traffic_channels = []
    top_pages = []
    top_sources = []
    top_landing_pages = []
    for row in snapshot.get("dimension_rows") or []:
        if not isinstance(row, dict):
            continue
        metrics = _dimension_metrics(row)
        if row.get("kind") == "traffic_channels":
            traffic_channels.append(
                {
                    "channel": row.get("label"),
                    **metrics,
                }
            )
        elif row.get("kind") == "top_pages":
            top_pages.append(
                {
                    "label": row.get("label"),
                    "path": row.get("path") or metrics.get("path") or "",
                    **metrics,
                }
            )
        elif row.get("kind") == "source_medium":
            top_sources.append(
                {
                    "label": row.get("label"),
                    **metrics,
                }
            )
        elif row.get("kind") == "landing_pages":
            top_landing_pages.append(
                {
                    "label": row.get("label"),
                    "path": row.get("label") or "",
                    **metrics,
                }
            )
    return {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "ga4",
        "reporting_period": snapshot.get("date_range") or {},
        "summary_metrics": summary_metrics,
        "time_series": snapshot.get("time_series") or [],
        "traffic_channels": traffic_channels,
        "top_pages": top_pages,
        "top_sources": top_sources,
        "top_landing_pages": top_landing_pages,
    }


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def _require_exact_source_period(payload: dict[str, Any], period: dict[str, str]) -> None:
    source_period = payload.get("report_period")
    if not isinstance(source_period, dict):
        raise ValueError("exact-range source report_period is required")
    if source_period.get("start_date") != period["start"] or source_period.get("end_date") != period["end"]:
        raise ValueError("exact-range source period does not match handoff report period")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
