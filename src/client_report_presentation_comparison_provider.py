from __future__ import annotations

from datetime import date
from typing import Any

from src.client_report_ga4_exact_range_provider import _range_entry as ga4_summary_entry
from src.client_report_ga4_ranked_exact_range_provider import QUERY_BY_SECTION, _range_entry as ga4_ranked_entry
from src.client_report_ga4_ranked_exact_ranges import METRIC_LABELS, RANKED_EXACT_RANGE_CONTRACTS
from src.client_report_presentation_comparisons import (
    COMPARISON_PRESET_KEYS,
    align_trend_series,
    build_metric_comparison,
    build_presentation_comparison_package,
    comparison_entry,
    comparison_query_fingerprint,
    lineage,
    match_ranked_rows,
    period_state,
    resolve_comparison_ranges,
)
from src.config import DateRange


SUMMARY_METRICS = {
    "ga4_top_metrics": (
        ("users", "Website Visitors", "count"),
        ("new_users", "New Visitors", "count"),
        ("sessions", "Visits", "count"),
        ("views", "Views", "count"),
        ("engagement_rate", "Engagement Rate", "rate"),
    ),
    "ga4_user_engagement": (
        ("engagement_rate", "Engagement Rate", "rate"),
        ("engaged_sessions", "Engaged Sessions", "count"),
        ("event_count", "Events", "count"),
    ),
}
GSC_METRICS = (
    ("clicks", "Clicks", "count"),
    ("impressions", "Impressions", "count"),
    ("ctr", "CTR", "rate"),
    ("average_position", "Average Position", "average_position"),
)
GSC_SECTIONS = {
    "gsc_summary": (None, None),
    "gsc_top_queries": ("query", "query_rows"),
    "gsc_top_pages": ("page", "page_rows"),
}


def build_real_presentation_comparisons(
    *,
    ga4_client: Any,
    gsc_client: Any,
    profile: str,
    report_id: str,
    client_id: str,
    project_id: str,
    report_start: date,
    report_end: date,
    gsc_available_through: date,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if profile != "aluma-seo-geo":
        raise ValueError("controlled R4 comparison retrieval is authorized only for aluma-seo-geo")
    identity = {"report_id": report_id, "client_id": client_id, "project_id": project_id}
    comparisons: list[dict[str, Any]] = []
    provider_calls = {"ga4": 0, "gsc": 0}
    for preset in COMPARISON_PRESET_KEYS:
        current, prior = resolve_comparison_ranges(preset, report_start=report_start, report_end=report_end)
        current_range = DateRange(current.start_date, current.end_date)
        prior_range = DateRange(prior.start_date, prior.end_date)

        current_summary, _, calls = ga4_summary_entry(client=ga4_client, profile=profile, range_key=preset, date_range=current_range)
        provider_calls["ga4"] += calls
        prior_summary, _, calls = ga4_summary_entry(client=ga4_client, profile=profile, range_key=f"{preset}_comparison", date_range=prior_range)
        provider_calls["ga4"] += calls
        current_state = _ga4_state(current_summary, current)
        prior_state = _ga4_state(prior_summary, prior)
        eligible = _exactly_comparable(current_state, prior_state)
        for section, definitions in SUMMARY_METRICS.items():
            comparisons.append(comparison_entry(
                package_identity=identity,
                section_key=section,
                preset_key=preset,
                current=current_state,
                comparison=prior_state,
                current_lineage=_ga4_lineage(section, preset, current.start_date, current.end_date, current_summary),
                comparison_lineage=_ga4_lineage(section, preset, prior.start_date, prior.end_date, prior_summary),
                delta_eligible=eligible,
                delta_ineligible_reason=None if eligible else "Exact current and comparison coverage is not equivalent.",
                metrics=[
                    build_metric_comparison(
                        key=key, label=label, unit=unit,
                        current_value=current_summary["metrics"].get(key),
                        prior_value=prior_summary["metrics"].get(key),
                    ) for key, label, unit in definitions
                ],
            ))

        current_trends = _ga4_trends(ga4_client.run_exact_range_traffic_series(current_range))
        prior_trends = _ga4_trends(ga4_client.run_exact_range_traffic_series(prior_range))
        provider_calls["ga4"] += 2
        comparisons.append(comparison_entry(
            package_identity=identity,
            section_key="ga4_website_traffic_trends",
            preset_key=preset,
            current=current_state,
            comparison=prior_state,
            current_lineage=_simple_lineage("ga4_daily_traffic_series.v1", "ga4", "ga4_website_traffic_trends", preset, current.start_date, current.end_date),
            comparison_lineage=_simple_lineage("ga4_daily_traffic_series.v1", "ga4", "ga4_website_traffic_trends", preset, prior.start_date, prior.end_date),
            delta_eligible=eligible and len(current_trends[0]["points"]) == len(prior_trends[0]["points"]),
            delta_ineligible_reason="Daily-series coverage is not equivalent." if len(current_trends[0]["points"]) != len(prior_trends[0]["points"]) else None,
            trend_series=align_trend_series(current_series=current_trends, comparison_series=prior_trends),
        ))

        for contract in RANKED_EXACT_RANGE_CONTRACTS.values():
            runner = QUERY_BY_SECTION[contract.section_key][3]
            current_rows = ga4_ranked_entry(client=ga4_client, profile=profile, range_key=preset, date_range=current_range, contract=contract, runner=runner)
            prior_rows = ga4_ranked_entry(client=ga4_client, profile=profile, range_key=f"{preset}_comparison", date_range=prior_range, contract=contract, runner=runner)
            provider_calls["ga4"] += 2
            identity_key = _ga4_identity_key(contract.section_key)
            definitions = [{"key": key, "label": METRIC_LABELS[key], "unit": "rate" if key == "engagement_rate" else "count"} for key in contract.metric_order]
            comparisons.append(comparison_entry(
                package_identity=identity,
                section_key=contract.section_key,
                preset_key=preset,
                current=_ga4_state(current_rows, current),
                comparison=_ga4_state(prior_rows, prior),
                current_lineage=_simple_lineage(contract.schema_version, "ga4", contract.section_key, preset, current.start_date, current.end_date),
                comparison_lineage=_simple_lineage(contract.schema_version, "ga4", contract.section_key, preset, prior.start_date, prior.end_date),
                delta_eligible=True,
                ranked_rows=match_ranked_rows(
                    current_rows=[dict(row, stable_identity=_stable_ga4_identity(row, identity_key)) for row in current_rows["rows"]],
                    prior_rows=[dict(row, stable_identity=_stable_ga4_identity(row, identity_key)) for row in prior_rows["rows"]],
                    identity_key="stable_identity",
                    metric_definitions=definitions,
                ),
            ))

        for section, (dimension, _) in GSC_SECTIONS.items():
            current_gsc = _gsc_period(gsc_client, dimension, current.start_date, current.end_date, gsc_available_through)
            prior_gsc = _gsc_period(gsc_client, dimension, prior.start_date, prior.end_date, gsc_available_through)
            provider_calls["gsc"] += int(current_gsc["provider_called"]) + int(prior_gsc["provider_called"])
            gsc_eligible = _gsc_comparable(current_gsc, prior_gsc)
            common = dict(
                package_identity=identity,
                section_key=section,
                preset_key=preset,
                current=current_gsc["state"],
                comparison=prior_gsc["state"],
                current_lineage=_simple_lineage(f"{section}_comparison_source.v1", "gsc", section, preset, current.start_date, current.end_date),
                comparison_lineage=_simple_lineage(f"{section}_comparison_source.v1", "gsc", section, preset, prior.start_date, prior.end_date),
                delta_eligible=gsc_eligible,
                delta_ineligible_reason=None if gsc_eligible else "Change is withheld because actual Search Console coverage is not comparable.",
            )
            if dimension is None:
                comparisons.append(comparison_entry(
                    **common,
                    metrics=[build_metric_comparison(key=key, label=label, unit=unit, current_value=current_gsc["metrics"].get(key), prior_value=prior_gsc["metrics"].get(key)) for key, label, unit in GSC_METRICS],
                ))
            else:
                definitions = [{"key": key, "label": label, "unit": unit} for key, label, unit in GSC_METRICS]
                comparisons.append(comparison_entry(
                    **common,
                    ranked_rows=match_ranked_rows(
                        current_rows=[dict(row, rank=index + 1, stable_identity=row[dimension], label=row[dimension]) for index, row in enumerate(current_gsc["rows"])],
                        prior_rows=[dict(row, rank=index + 1, stable_identity=row[dimension], label=row[dimension]) for index, row in enumerate(prior_gsc["rows"])],
                        identity_key="stable_identity",
                        metric_definitions=definitions,
                    ),
                ))

    return build_presentation_comparison_package(
        report_id=report_id, client_id=client_id, project_id=project_id, client_slug=profile,
        report_start=report_start, report_end=report_end, comparisons=comparisons,
        source_identity={
            "source_kind": "bounded_provider_exact_ranges",
            "profile": profile,
            "ga4_provider_calls": provider_calls["ga4"],
            "gsc_provider_calls": provider_calls["gsc"],
            "raw_provider_payload_included": False,
        },
        generated_at=generated_at,
    )


def _ga4_state(entry: dict[str, Any], resolved: Any) -> dict[str, Any]:
    empty = entry.get("data_state") == "empty"
    return period_state(
        requested_start=resolved.start_date,
        requested_end=resolved.end_date,
        data_state="empty" if empty else "complete",
        coverage_state="empty" if empty else "complete",
    )


def _exactly_comparable(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    return current["coverage_state"] in {"complete", "empty"} and prior["coverage_state"] in {"complete", "empty"}


def _ga4_lineage(section: str, preset: str, start: date, end: date, entry: dict[str, Any]) -> dict[str, str]:
    return lineage(
        source_contract="ga4_metric_display_exact_ranges.v1",
        dataset_version="ga4_metric_display_exact_ranges.v1",
        source_identity=str(entry["source_identity"]),
        query_fingerprint=str(entry["query_fingerprint"]),
    )


def _simple_lineage(contract: str, provider: str, section: str, preset: str, start: date, end: date) -> dict[str, str]:
    return lineage(
        source_contract=contract,
        dataset_version=contract,
        source_identity=f"{provider}:{section}:{preset}:{start}:{end}:sanitized",
        query_fingerprint=comparison_query_fingerprint(section, preset, start, end),
    )


def _ga4_identity_key(section: str) -> str:
    return {"ga4_channel_performance": "channel", "ga4_top_sources": "source_medium", "ga4_top_landing_pages": "path", "ga4_most_viewed_pages": "path"}[section]


def _stable_ga4_identity(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if key == "path" and row.get("page_title"):
        value = f"{value}\u001f{str(row['page_title']).strip()}"
    if not value:
        raise ValueError("GA4 ranked comparison row is missing stable semantic identity")
    return value


def _ga4_trends(response: dict[str, Any]) -> list[dict[str, Any]]:
    dimension_headers = [item.get("name") for item in response.get("dimensionHeaders") or []]
    metric_headers = [item.get("name") for item in response.get("metricHeaders") or []]
    if "date" not in dimension_headers or "activeUsers" not in metric_headers or "sessions" not in metric_headers:
        raise ValueError("GA4 traffic series response is missing required headers")
    date_index = dimension_headers.index("date")
    users_index = metric_headers.index("activeUsers")
    sessions_index = metric_headers.index("sessions")
    points = {"users": [], "sessions": []}
    for row in response.get("rows") or []:
        dimensions = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        raw_date = str(dimensions[date_index].get("value") or "")
        observed = date.fromisoformat(f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}")
        points["users"].append({"date": observed.isoformat(), "value": int(round(float(metrics[users_index].get("value") or 0)))})
        points["sessions"].append({"date": observed.isoformat(), "value": int(round(float(metrics[sessions_index].get("value") or 0)))})
    for values in points.values(): values.sort(key=lambda item: item["date"])
    return [{"key": key, "label": key.title(), "unit": "count", "points": values} for key, values in points.items()]


def _gsc_period(client: Any, dimension: str | None, start: date, end: date, available_through: date) -> dict[str, Any]:
    if available_through < start:
        return {"provider_called": False, "state": period_state(requested_start=start, requested_end=end, data_state="unavailable", coverage_state="unavailable"), "metrics": {}, "rows": []}
    effective_end = min(end, available_through)
    response = client.query_exact_range_summary(start.isoformat(), effective_end.isoformat()) if dimension is None else client.query_exact_range_queries(start.isoformat(), effective_end.isoformat()) if dimension == "query" else client.query_exact_range_pages(start.isoformat(), effective_end.isoformat())
    rows = response.get("rows") or []
    if not isinstance(rows, list): raise ValueError("GSC comparison response rows are invalid")
    partial = effective_end < end
    state = period_state(
        requested_start=start, requested_end=end,
        data_state="partial" if partial else "empty" if not rows else "complete",
        coverage_state="partial" if partial else "empty" if not rows else "complete",
        actual_start=start if partial else None, actual_end=effective_end if partial else None, available_through=available_through if partial else None,
    )
    if dimension is None:
        metrics = _gsc_metrics(rows[0]) if rows else {"clicks": 0, "impressions": 0, "ctr": 0.0, "average_position": 0.0}
        return {"provider_called": True, "state": state, "metrics": metrics, "rows": []}
    normalized = []
    for row in rows:
        keys = row.get("keys")
        if not isinstance(keys, list) or len(keys) != 1 or not str(keys[0]).strip(): raise ValueError("GSC comparison dimension identity is invalid")
        normalized.append({dimension: str(keys[0]), "metrics": _gsc_metrics(row), **_gsc_metrics(row)})
    normalized.sort(key=lambda item: (-item["clicks"], item[dimension]))
    return {"provider_called": True, "state": state, "metrics": {}, "rows": normalized[:10]}


def _gsc_metrics(row: dict[str, Any]) -> dict[str, int | float]:
    clicks = int(round(float(row.get("clicks") or 0)))
    impressions = int(round(float(row.get("impressions") or 0)))
    return {"clicks": clicks, "impressions": impressions, "ctr": 0.0 if impressions == 0 else clicks / impressions, "average_position": float(row.get("position") or 0)}


def _gsc_comparable(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    current_state, prior_state = current["state"], prior["state"]
    exact = {"complete", "empty"}
    if current_state["coverage_state"] in exact and prior_state["coverage_state"] in exact: return True
    if current_state["coverage_state"] != "partial" or prior_state["coverage_state"] != "partial": return False
    current_days = (date.fromisoformat(current_state["actual_coverage_end_date"]) - date.fromisoformat(current_state["actual_coverage_start_date"])).days + 1
    prior_days = (date.fromisoformat(prior_state["actual_coverage_end_date"]) - date.fromisoformat(prior_state["actual_coverage_start_date"])).days + 1
    return current_days == prior_days
