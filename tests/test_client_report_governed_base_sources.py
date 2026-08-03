"""Governed-period base sourcing for Client Report Publisher handoffs.

Every test runs fully offline against synthetic fixtures. No real client
artifact is read, copied, edited, or relabeled, and no provider client is
constructed.

These cover R8C5-HANDOFF-PERIOD-01: the handoff writer derived its report
period from the wide dashboard-lab provider summaries, so a governed six-month
report would have been populated with roughly eighteen months of totals while
still validating.
"""

from __future__ import annotations

import pytest

from src.client_report_governed_base_sources import (
    GA4_CHANNEL_SOURCE,
    GA4_MOST_VIEWED_PAGES_SOURCE,
    GA4_SUMMARY_SOURCE,
    GA4_TOP_LANDING_PAGES_SOURCE,
    GA4_TOP_SOURCES_SOURCE,
    GOVERNED_BASE_SOURCES,
    GSC_SUMMARY_SOURCE,
    GSC_TOP_PAGES_SOURCE,
    GSC_TOP_QUERIES_SOURCE,
    GovernedBaseSourceError,
    build_governed_ga4_summary,
    build_governed_gsc_summary,
    clip_time_series,
    governed_base_available,
    governed_base_entry,
    governed_report_period,
)

PERIOD = {"start": "2026-01-01", "end": "2026-07-08"}
WIDE_PERIOD = {"start_date": "2025-01-01", "end_date": "2026-07-08"}


def _package(entry_extra: dict[str, object], *, period: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "report_period": period or {"start_date": PERIOD["start"], "end_date": PERIOD["end"]},
        "ranges": [
            {
                "range_key": "last_30_days",
                "requested_start_date": "2026-06-09",
                "requested_end_date": "2026-07-08",
                "data_state": "available",
            },
            {
                "range_key": "year_to_date",
                "requested_start_date": PERIOD["start"],
                "requested_end_date": PERIOD["end"],
                "data_state": "available",
                "source_identity": "synthetic",
                **entry_extra,
            },
        ],
    }


def _ga4_sources() -> dict[str, dict[str, object]]:
    return {
        GA4_SUMMARY_SOURCE: _package(
            {"metrics": {"users": 91526, "sessions": 146444, "views": 252206, "key_events": 0}}
        ),
        GA4_CHANNEL_SOURCE: _package(
            {"rows": [{"channel": "Organic Search", "rank": 1, "metrics": {"sessions": 71527, "users": 38320}}]}
        ),
        GA4_MOST_VIEWED_PAGES_SOURCE: _package(
            {"rows": [{"path": "/", "label": "Home", "page_title": "Home", "metrics": {"views": 84824}}]}
        ),
        GA4_TOP_SOURCES_SOURCE: _package(
            {"rows": [{"label": "google / organic", "metrics": {"sessions": 63582}}]}
        ),
        GA4_TOP_LANDING_PAGES_SOURCE: _package(
            {"rows": [{"path": "/", "label": "/", "metrics": {"sessions": 67233}}]}
        ),
    }


def _gsc_sources() -> dict[str, dict[str, object]]:
    return {
        GSC_SUMMARY_SOURCE: _package(
            {"summary_metrics": {"clicks": 35332, "impressions": 879519, "ctr": 0.04, "average_position": 9.05}}
        ),
        GSC_TOP_PAGES_SOURCE: _package({"page_rows": [{"page": "https://example.test/a", "clicks": 15501}]}),
        GSC_TOP_QUERIES_SOURCE: _package({"query_rows": [{"query": "example", "clicks": 3612}]}),
    }


def _all_sources() -> dict[str, dict[str, object]]:
    return {**_ga4_sources(), **_gsc_sources()}


# Report period


def test_governed_period_is_taken_from_the_sources_that_state_it() -> None:
    assert governed_report_period(_all_sources()) == PERIOD


def test_absent_governed_sources_leave_the_period_to_the_caller() -> None:
    assert governed_report_period({}) is None
    assert governed_report_period({"legacy": {"reporting_period": {"start": "2025-01-01"}}}) is None


def test_disagreeing_sources_are_refused_rather_than_reconciled() -> None:
    sources = _all_sources()
    sources[GSC_SUMMARY_SOURCE] = _package(
        {"summary_metrics": {"clicks": 1}},
        period=WIDE_PERIOD,
    )
    with pytest.raises(GovernedBaseSourceError) as excinfo:
        governed_report_period(sources)
    assert "disagree on the report period" in str(excinfo.value)


def test_a_wide_source_period_never_widens_a_governed_report() -> None:
    """The exact defect: the wide window must not become the report period."""
    period = governed_report_period(_all_sources())
    assert period == PERIOD
    assert period != {"start": WIDE_PERIOD["start_date"], "end": WIDE_PERIOD["end_date"]}


# Base entry selection


def test_base_entry_requires_the_exact_governed_period() -> None:
    package = _package({"metrics": {"users": 1}})
    assert governed_base_entry(package, PERIOD) is not None
    assert governed_base_entry(package, {"start": "2026-01-02", "end": PERIOD["end"]}) is None
    assert governed_base_entry(package, {"start": PERIOD["start"], "end": "2026-07-07"}) is None


def test_base_entry_refuses_a_range_that_is_not_available() -> None:
    package = _package({"metrics": {"users": 1}})
    package["ranges"][1]["data_state"] = "unavailable"
    assert governed_base_entry(package, PERIOD) is None


def test_base_entry_ignores_non_canonical_range_keys() -> None:
    package = {"ranges": [{"range_key": "last_30_days", "data_state": "available"}]}
    assert governed_base_entry(package, PERIOD) is None


def test_every_governed_source_must_offer_a_base_entry() -> None:
    assert governed_base_available(_all_sources(), PERIOD) is True
    for name in GOVERNED_BASE_SOURCES:
        partial = _all_sources()
        del partial[name]
        assert governed_base_available(partial, PERIOD) is False, name


# Adapted summaries


def test_governed_ga4_summary_carries_governed_period_figures() -> None:
    summary = build_governed_ga4_summary(_ga4_sources(), PERIOD)
    assert summary["reporting_period"] == {"start": PERIOD["start"], "end": PERIOD["end"]}
    assert summary["summary_metrics"]["users"] == 91526
    assert summary["traffic_channels"][0] == {
        "channel": "Organic Search",
        "sessions": 71527,
        "users": 38320,
    }
    assert summary["top_pages"][0]["views"] == 84824
    assert summary["top_sources"][0]["sessions"] == 63582
    assert summary["top_landing_pages"][0]["sessions"] == 67233
    assert summary["governed_base_source"]["provider_requests"] == 0


def test_absent_metrics_stay_absent_rather_than_being_substituted() -> None:
    summary = build_governed_ga4_summary(_ga4_sources(), PERIOD)
    assert "conversions" not in summary["summary_metrics"]
    assert "average_session_duration_seconds" not in summary["summary_metrics"]


def test_governed_gsc_summary_renames_page_to_path_without_altering_values() -> None:
    summary = build_governed_gsc_summary(_gsc_sources(), PERIOD)
    assert summary["summary_metrics"]["clicks"] == 35332
    assert summary["top_pages"][0]["path"] == "https://example.test/a"
    assert summary["top_pages"][0]["clicks"] == 15501
    assert summary["top_queries"][0]["query"] == "example"


def test_a_missing_governed_source_refuses_rather_than_falling_back() -> None:
    sources = _ga4_sources()
    del sources[GA4_CHANNEL_SOURCE]
    with pytest.raises(GovernedBaseSourceError):
        build_governed_ga4_summary(sources, PERIOD)


# Daily series clipping


def test_clipping_drops_out_of_period_rows_and_invents_none() -> None:
    legacy = {
        "time_series": [
            {"date": "2025-12-31", "users": 1},
            {"date": "2026-01-01", "users": 2},
            {"date": "2026-07-08", "users": 3},
            {"date": "2026-07-09", "users": 4},
        ]
    }
    clipped = clip_time_series(legacy, PERIOD)
    assert [row["date"] for row in clipped] == ["2026-01-01", "2026-07-08"]
    assert [row["users"] for row in clipped] == [2, 3]


def test_clipping_a_partly_covered_period_returns_fewer_rows() -> None:
    legacy = {"time_series": [{"date": "2026-01-01"}, {"date": "2026-07-06"}]}
    assert len(clip_time_series(legacy, PERIOD)) == 2


def test_clipping_tolerates_an_absent_series() -> None:
    assert clip_time_series({}, PERIOD) == []
    assert clip_time_series(None, PERIOD) == []


def test_clipped_rows_are_ordered_by_date() -> None:
    legacy = {"time_series": [{"date": "2026-03-01"}, {"date": "2026-02-01"}]}
    assert [row["date"] for row in clip_time_series(legacy, PERIOD)] == ["2026-02-01", "2026-03-01"]
