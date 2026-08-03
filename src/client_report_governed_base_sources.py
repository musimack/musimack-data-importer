"""Governed-period base sourcing for Client Report Publisher handoffs.

A handoff's base display datasets are the numbers a client sees for the report
as a whole. They must therefore describe **the governed report period and
nothing else**.

The legacy path derived the handoff period from the wide dashboard-lab provider
summaries and populated the base datasets from them. Those summaries are
retained evidence covering a much wider window than a governed report period,
so on the R8-C5 backfill they would have put roughly eighteen months of totals
into a six-month report while still validating. The handoff writer refused
rather than publishing that, which is the correct behavior and is preserved.

This module supplies the truthful alternative. Every exact-range source package
already carries a ``year_to_date`` entry, and for a report period that begins on
January 1 that entry resolves to **exactly** the governed period. Those entries
were retrieved from the real providers at real cost, carry full governed metric
coverage, and need no further provider call. They are therefore the correct
source for the base datasets.

Two rules keep this honest:

- **Nothing is inferred.** A metric the exact-range source does not carry stays
  absent, so it renders as unavailable rather than as a substituted value.
- **Daily observations are clipped, never synthesized.** The dated daily series
  is retained evidence at day grain, so restricting it to the governed period
  removes rows without inventing any. A period the series only partly covers
  reports as partial coverage rather than as complete.

Nothing here touches a credential, constructs a provider client, or makes a
network call.
"""

from __future__ import annotations

from datetime import date
from typing import Any

GOVERNED_BASE_RANGE_KEY = "year_to_date"

# Exact-range source contracts that can carry a governed base entry, mapped to
# the role each one plays in the base datasets.
GA4_SUMMARY_SOURCE = "ga4_metric_display_exact_ranges.v1"
GA4_CHANNEL_SOURCE = "ga4_channel_performance_exact_ranges.v1"
GA4_MOST_VIEWED_PAGES_SOURCE = "ga4_most_viewed_pages_exact_ranges.v1"
GA4_TOP_SOURCES_SOURCE = "ga4_top_sources_exact_ranges.v1"
GA4_TOP_LANDING_PAGES_SOURCE = "ga4_top_landing_pages_exact_ranges.v1"
GSC_SUMMARY_SOURCE = "gsc_summary_exact_ranges.v1"
GSC_TOP_PAGES_SOURCE = "gsc_top_pages_exact_ranges.v1"
GSC_TOP_QUERIES_SOURCE = "gsc_top_queries_exact_ranges.v1"

GOVERNED_BASE_SOURCES = (
    GA4_SUMMARY_SOURCE,
    GA4_CHANNEL_SOURCE,
    GA4_MOST_VIEWED_PAGES_SOURCE,
    GA4_TOP_SOURCES_SOURCE,
    GA4_TOP_LANDING_PAGES_SOURCE,
    GSC_SUMMARY_SOURCE,
    GSC_TOP_PAGES_SOURCE,
    GSC_TOP_QUERIES_SOURCE,
)


class GovernedBaseSourceError(ValueError):
    """The governed sources disagree, so no handoff period can be trusted."""


def governed_report_period(sources: dict[str, dict[str, Any]]) -> dict[str, str] | None:
    """Return the governed report period agreed by every governed source.

    ``sources`` maps a contract name to its already-loaded payload. Only
    payloads carrying a ``report_period`` participate. If none do, the caller
    keeps its existing behavior and this returns ``None``.

    **Disagreement is refused, never reconciled.** Silently taking the widest or
    narrowest span across sources is exactly how a report acquires a period no
    single source actually supports.
    """
    periods: dict[str, tuple[str, str]] = {}
    for name, payload in sources.items():
        if not isinstance(payload, dict):
            continue
        period = payload.get("report_period")
        if not isinstance(period, dict):
            continue
        start = period.get("start_date")
        end = period.get("end_date")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        periods[name] = (start, end)

    if not periods:
        return None

    distinct = set(periods.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={start}..{end}" for name, (start, end) in sorted(periods.items()))
        raise GovernedBaseSourceError(
            f"governed sources disagree on the report period: {detail}"
        )

    start, end = distinct.pop()
    if _parse_date(start) > _parse_date(end):
        raise GovernedBaseSourceError("governed report period start is after its end")
    return {"start": start, "end": end}


def governed_base_entry(payload: Any, period: dict[str, str]) -> dict[str, Any] | None:
    """Return the exact-range entry that covers exactly the governed period.

    The entry must be the canonical base range key, resolve to precisely the
    requested period, and report itself available. Anything else returns
    ``None`` so the caller falls back rather than presenting a near-miss range
    as if it were the report period.
    """
    if not isinstance(payload, dict):
        return None
    for entry in payload.get("ranges") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("range_key") != GOVERNED_BASE_RANGE_KEY:
            continue
        if entry.get("requested_start_date") != period["start"]:
            return None
        if entry.get("requested_end_date") != period["end"]:
            return None
        if entry.get("data_state") != "available":
            return None
        return entry
    return None


def governed_base_available(sources: dict[str, dict[str, Any]], period: dict[str, str]) -> bool:
    """True only when every governed source offers a usable base entry.

    Partial adoption is deliberately refused. Mixing governed-period figures
    with wide-window ones inside a single handoff would produce a report whose
    sections silently describe different spans.
    """
    return all(
        governed_base_entry(sources.get(name), period) is not None
        for name in GOVERNED_BASE_SOURCES
    )


def build_governed_ga4_summary(
    sources: dict[str, dict[str, Any]],
    period: dict[str, str],
    legacy_ga4_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a GA4 base summary scoped to exactly the governed report period."""
    summary_entry = _require_entry(sources, GA4_SUMMARY_SOURCE, period)
    channel_entry = _require_entry(sources, GA4_CHANNEL_SOURCE, period)
    pages_entry = _require_entry(sources, GA4_MOST_VIEWED_PAGES_SOURCE, period)
    top_sources_entry = _require_entry(sources, GA4_TOP_SOURCES_SOURCE, period)
    landing_entry = _require_entry(sources, GA4_TOP_LANDING_PAGES_SOURCE, period)

    metrics = summary_entry.get("metrics")
    if not isinstance(metrics, dict):
        raise GovernedBaseSourceError("governed GA4 summary entry carries no metrics")

    return {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "ga4",
        "reporting_period": {"start": period["start"], "end": period["end"]},
        "summary_metrics": dict(metrics),
        "time_series": clip_time_series(legacy_ga4_summary, period),
        "traffic_channels": [
            {
                "channel": row.get("channel") or row.get("label"),
                **_row_metrics(row),
            }
            for row in _rows(channel_entry, "rows")
        ],
        "top_pages": [
            {
                "path": row.get("path"),
                "label": row.get("label") or row.get("page_title") or row.get("path"),
                **_row_metrics(row),
            }
            for row in _rows(pages_entry, "rows")
        ],
        "top_sources": [
            {
                "label": row.get("label") or row.get("source_medium"),
                **_row_metrics(row),
            }
            for row in _rows(top_sources_entry, "rows")
        ],
        "top_landing_pages": [
            {
                "path": row.get("path"),
                "label": row.get("label") or row.get("path"),
                **_row_metrics(row),
            }
            for row in _rows(landing_entry, "rows")
        ],
        "governed_base_source": _provenance(
            [
                (GA4_SUMMARY_SOURCE, summary_entry),
                (GA4_CHANNEL_SOURCE, channel_entry),
                (GA4_MOST_VIEWED_PAGES_SOURCE, pages_entry),
                (GA4_TOP_SOURCES_SOURCE, top_sources_entry),
                (GA4_TOP_LANDING_PAGES_SOURCE, landing_entry),
            ],
            period,
        ),
    }


def build_governed_gsc_summary(
    sources: dict[str, dict[str, Any]],
    period: dict[str, str],
    legacy_gsc_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a GSC base summary scoped to exactly the governed report period."""
    summary_entry = _require_entry(sources, GSC_SUMMARY_SOURCE, period)
    pages_entry = _require_entry(sources, GSC_TOP_PAGES_SOURCE, period)
    queries_entry = _require_entry(sources, GSC_TOP_QUERIES_SOURCE, period)

    metrics = summary_entry.get("summary_metrics")
    if not isinstance(metrics, dict):
        raise GovernedBaseSourceError("governed GSC summary entry carries no summary_metrics")

    return {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "gsc",
        "reporting_period": {"start": period["start"], "end": period["end"]},
        "summary_metrics": dict(metrics),
        "time_series": clip_time_series(legacy_gsc_summary, period),
        "top_queries": [
            {
                "query": row.get("query"),
                "clicks": row.get("clicks"),
                "impressions": row.get("impressions"),
                "ctr": row.get("ctr"),
                "average_position": row.get("average_position"),
            }
            for row in _rows(queries_entry, "query_rows")
        ],
        # The display builder reads ``path``; the exact-range contract names the
        # same field ``page``. Renaming here keeps the contract untouched.
        "top_pages": [
            {
                "path": row.get("page") or row.get("path"),
                "clicks": row.get("clicks"),
                "impressions": row.get("impressions"),
                "ctr": row.get("ctr"),
                "average_position": row.get("average_position"),
            }
            for row in _rows(pages_entry, "page_rows")
        ],
        "governed_base_source": _provenance(
            [
                (GSC_SUMMARY_SOURCE, summary_entry),
                (GSC_TOP_PAGES_SOURCE, pages_entry),
                (GSC_TOP_QUERIES_SOURCE, queries_entry),
            ],
            period,
        ),
    }


def clip_time_series(payload: Any, period: dict[str, str]) -> list[dict[str, Any]]:
    """Restrict a dated daily series to the governed period.

    Rows are dropped, never altered and never generated. A period the series
    covers only partly therefore yields fewer rows, which the coverage summary
    reports as partial rather than complete.
    """
    if not isinstance(payload, dict):
        return []
    rows = payload.get("time_series")
    if not isinstance(rows, list):
        return []
    start = _parse_date(period["start"])
    end = _parse_date(period["end"])
    kept = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_date = row.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            observed = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if start <= observed <= end:
            kept.append(row)
    kept.sort(key=lambda row: str(row.get("date")))
    return kept


def _require_entry(
    sources: dict[str, dict[str, Any]],
    name: str,
    period: dict[str, str],
) -> dict[str, Any]:
    entry = governed_base_entry(sources.get(name), period)
    if entry is None:
        raise GovernedBaseSourceError(
            f"{name} has no available {GOVERNED_BASE_RANGE_KEY} entry covering "
            f"{period['start']}..{period['end']}"
        )
    return entry


def _rows(entry: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = entry.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _row_metrics(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics")
    if isinstance(metrics, dict):
        return dict(metrics)
    return {}


def _provenance(
    entries: list[tuple[str, dict[str, Any]]],
    period: dict[str, str],
) -> dict[str, Any]:
    return {
        "sourcing": "governed_exact_range_base",
        "range_key": GOVERNED_BASE_RANGE_KEY,
        "report_period": {"start": period["start"], "end": period["end"]},
        "provider_requests": 0,
        "contracts": [
            {
                "source_contract": name,
                "range_key": entry.get("range_key"),
                "requested_start_date": entry.get("requested_start_date"),
                "requested_end_date": entry.get("requested_end_date"),
                "source_identity": entry.get("source_identity"),
            }
            for name, entry in entries
        ],
    }


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        raise GovernedBaseSourceError("governed period bounds must be ISO dates")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GovernedBaseSourceError("governed period bounds must be ISO dates") from exc
