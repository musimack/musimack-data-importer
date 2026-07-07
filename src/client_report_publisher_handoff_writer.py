from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HANDOFF_MANIFEST_VERSION = "client_report_publisher_handoff_manifest.v1"
DEFAULT_OUTPUT_ROOT = Path("exports") / "local-real" / "client-report-publisher-handoff"
DEFAULT_SOURCE_ROOT = Path("exports") / "local-real" / "dashboard-lab"


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

    generated.append(
        (
            output / "ga4_metric_display.v1.json",
            _build_ga4_metric_display(profile, client_name, ga4_summary, period),
            "ga4",
            "metric_display",
            "ga4_metric_display.v1",
        )
    )

    page_rows = list(ga4_summary.get("top_pages") or [])
    if page_rows:
        generated.append(
            (
                output / "ga4_most_viewed_pages_display.v1.json",
                _build_ga4_most_viewed_pages(profile, ga4_summary, period),
                "ga4",
                "most_viewed_pages_display",
                "ga4_most_viewed_pages_display.v1",
            )
        )
    else:
        skipped.append("ga4_most_viewed_pages_display.v1: no sanitized top page rows available")

    source_rows = _top_sources_from_summary_or_snapshot(ga4_summary, ga4_snapshot)
    if source_rows:
        generated.append(
            (
                output / "ga4_top_sources_display.v1.json",
                _build_ga4_top_sources(profile, source_rows, period),
                "ga4",
                "top_sources_display",
                "ga4_top_sources_display.v1",
            )
        )
    else:
        skipped.append("ga4_top_sources_display.v1: true source/source-medium rows unavailable")

    landing_page_rows = _top_landing_pages_from_summary_or_snapshot(ga4_summary, ga4_snapshot)
    if landing_page_rows:
        generated.append(
            (
                output / "ga4_top_landing_pages_display.v1.json",
                _build_ga4_top_landing_pages(profile, landing_page_rows, period),
                "ga4",
                "top_landing_pages_display",
                "ga4_top_landing_pages_display.v1",
            )
        )
    else:
        skipped.append("ga4_top_landing_pages_display.v1: landing-page scoped rows unavailable")

    generated.append(
        (
            output / "gsc_summary_display.v1.json",
            _build_gsc_summary_display(profile, gsc_summary, period),
            "gsc",
            "summary_display",
            "gsc_summary_display.v1",
        )
    )
    generated.append(
        (
            output / "gsc_queries_display.v1.json",
            _build_gsc_queries_display(profile, gsc_summary, period),
            "gsc",
            "queries_display",
            "gsc_queries_display.v1",
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
    return {
        "schema_version": "ga4_metric_display.v1",
        "provider": "ga4",
        "report_type": "metric_display",
        "client_slug": profile,
        "client_name": client_name,
        "report_period": _report_period(period),
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
                        "points": _trend_points(ga4_summary.get("time_series") or [], "users"),
                    },
                    {
                        "key": "sessions",
                        "label": "Visits",
                        "unit": "count",
                        "points": _trend_points(ga4_summary.get("time_series") or [], "sessions"),
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
    return {
        "schema_version": "ga4_most_viewed_pages_display.v1",
        "provider": "ga4",
        "report_type": "most_viewed_pages_display",
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
    return {
        "schema_version": "ga4_top_sources_display.v1",
        "provider": "ga4",
        "report_type": "top_sources_display",
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
    return {
        "schema_version": "ga4_top_landing_pages_display.v1",
        "provider": "ga4",
        "report_type": "top_landing_pages_display",
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
    return {
        "schema_version": "gsc_summary_display.v1",
        "provider": "gsc",
        "report_type": "summary_display",
        "client_slug": profile,
        "site_label": "spanishhead.com",
        "report_period": _report_period(period),
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
            for row in (gsc_summary.get("time_series") or [])[:100]
        ],
        "notes": ["Generated from sanitized local-real GSC summary output."],
    }


def _build_gsc_queries_display(
    profile: str,
    gsc_summary: dict[str, Any],
    period: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "gsc_queries_display.v1",
        "provider": "gsc",
        "report_type": "queries_display",
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
            for index, row in enumerate((gsc_summary.get("top_queries") or [])[:20])
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
            for index, row in enumerate((gsc_summary.get("top_pages") or [])[:20])
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
        for row in rows[:100]
        if row.get("date")
    ]


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
