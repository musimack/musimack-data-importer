from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.client_report_presentation_comparisons import (
    COMPARISON_SCHEMA_VERSION,
    align_trend_series,
    build_metric_comparison,
    build_presentation_comparison_package,
    comparison_entry,
    enumerate_comparison_ranges,
    lineage,
    match_ranked_rows,
    period_state,
    resolve_comparison_ranges,
    validate_presentation_comparison_package,
)
from src.client_report_presentation_comparison_provider import build_real_presentation_comparisons


REPORT_START = date(2025, 1, 1)
REPORT_END = date(2026, 7, 8)
IDENTITY = {"report_id": "report-1", "client_id": "client-1", "project_id": "project-1"}
LINEAGE = lineage(source_contract="fixture.v1", dataset_version="fixture-1", source_identity="fixture-safe")


def test_all_twelve_governed_range_pairs_are_exact() -> None:
    actual = {
        item["preset_key"]: (
            item["current_start_date"], item["current_end_date"],
            item["comparison_start_date"], item["comparison_end_date"],
        )
        for item in enumerate_comparison_ranges(report_start=REPORT_START, report_end=REPORT_END)
    }
    assert actual == {
        "report_period": ("2025-01-01", "2026-07-08", "2023-06-27", "2024-12-31"),
        "last_3_days": ("2026-07-06", "2026-07-08", "2026-07-03", "2026-07-05"),
        "last_7_days": ("2026-07-02", "2026-07-08", "2026-06-25", "2026-07-01"),
        "last_14_days": ("2026-06-25", "2026-07-08", "2026-06-11", "2026-06-24"),
        "last_30_days": ("2026-06-09", "2026-07-08", "2026-05-10", "2026-06-08"),
        "last_60_days": ("2026-05-10", "2026-07-08", "2026-03-11", "2026-05-09"),
        "last_90_days": ("2026-04-10", "2026-07-08", "2026-01-10", "2026-04-09"),
        "last_6_months": ("2026-01-09", "2026-07-08", "2025-07-09", "2026-01-08"),
        "last_12_months": ("2025-07-09", "2026-07-08", "2024-07-09", "2025-07-08"),
        "year_to_date": ("2026-01-01", "2026-07-08", "2025-01-01", "2025-07-08"),
        "this_month": ("2026-07-01", "2026-07-08", "2026-06-01", "2026-06-08"),
        "last_month": ("2026-06-01", "2026-06-30", "2026-05-01", "2026-05-31"),
    }


@pytest.mark.parametrize(
    ("current", "prior", "state", "relative"),
    [
        (120, 100, "increase", 20.0),
        (80, 100, "decrease", -20.0),
        (100, 100, "no_change", 0.0),
        (5, 0, "new", None),
        (0, 0, "no_change", None),
        (0, 5, "decrease", -100.0),
        (5, None, "not_comparable", None),
    ],
)
def test_count_metric_semantics(current, prior, state, relative) -> None:
    result = build_metric_comparison(key="sessions", label="Sessions", unit="count", current_value=current, prior_value=prior)
    assert result["change_state"] == state
    assert result["relative_change_percent"] == relative


@pytest.mark.parametrize(("current", "prior", "state", "points"), [(0.449, 0.4, "increase", 4.9), (0.35, 0.4, "decrease", -5.0), (0.4, 0.4, "no_change", 0.0)])
def test_rate_metric_uses_percentage_points_only(current, prior, state, points) -> None:
    result = build_metric_comparison(key="ctr", label="CTR", unit="rate", current_value=current, prior_value=prior)
    assert result["change_state"] == state
    assert result["percentage_point_change"] == points
    assert result["relative_change_percent"] is None


@pytest.mark.parametrize(("current", "prior", "state"), [(3.5, 4.2, "improved"), (5.1, 4.2, "declined"), (4.2, 4.2, "no_change")])
def test_average_position_has_inverse_direction(current, prior, state) -> None:
    result = build_metric_comparison(key="average_position", label="Average Position", unit="average_position", current_value=current, prior_value=prior)
    assert result["change_state"] == state
    assert result["direction"] == "lower_is_better"


def test_ranked_rows_match_by_semantic_identity_and_exclude_prior_only() -> None:
    metrics = [{"key": "sessions", "label": "Sessions", "unit": "count"}]
    rows = match_ranked_rows(
        current_rows=[
            {"identity": "organic", "label": "Organic", "rank": 1, "metrics": {"sessions": 20}},
            {"identity": "email", "label": "Email", "rank": 2, "metrics": {"sessions": 5}},
        ],
        prior_rows=[
            {"identity": "organic", "label": "Organic", "rank": 3, "metrics": {"sessions": 10}},
            {"identity": "paid", "label": "Paid", "rank": 1, "metrics": {"sessions": 40}},
        ],
        identity_key="identity",
        metric_definitions=metrics,
    )
    assert [row["stable_identity"] for row in rows] == ["organic", "email"]
    assert rows[0]["rank_movement"] == 2
    assert rows[1]["new_row"] is True
    assert rows[1]["prior_rank"] is None


def test_ranked_duplicate_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate current ranked identity"):
        match_ranked_rows(
            current_rows=[{"id": "x", "rank": 1}, {"id": "x", "rank": 2}],
            prior_rows=[], identity_key="id", metric_definitions=[]
        )


def test_trends_align_by_day_index_without_relabeling_dates() -> None:
    aligned = align_trend_series(
        current_series=[{"key": "sessions", "label": "Sessions", "points": [{"date": "2026-07-01", "value": 1}, {"date": "2026-07-02", "value": 2}]}],
        comparison_series=[{"key": "sessions", "label": "Sessions", "points": [{"date": "2026-06-01", "value": 3}]}],
    )
    assert aligned[0]["current_points"] == [{"date": "2026-07-01", "value": 1, "day_index": 1}, {"date": "2026-07-02", "value": 2, "day_index": 2}]
    assert aligned[0]["comparison_points"] == [{"date": "2026-06-01", "value": 3, "day_index": 1}]


@pytest.mark.parametrize(
    ("current_coverage", "prior_coverage", "eligible"),
    [("complete", "complete", True), ("partial", "complete", False), ("complete", "partial", False), ("partial", "partial", False)],
)
def test_complete_partial_coverage_states_validate(current_coverage, prior_coverage, eligible) -> None:
    package = _package(current_coverage=current_coverage, prior_coverage=prior_coverage, eligible=eligible)
    validate_presentation_comparison_package(package)


@pytest.mark.parametrize(("current_state", "prior_state"), [("empty", "complete"), ("complete", "empty"), ("unavailable", "complete"), ("complete", "unavailable")])
def test_empty_and_unavailable_states_validate(current_state, prior_state) -> None:
    package = _package(current_state=current_state, prior_state=prior_state, eligible=False)
    validate_presentation_comparison_package(package)


def test_missing_contract_is_optional_at_handoff_level() -> None:
    assert COMPARISON_SCHEMA_VERSION == "client_report_presentation_comparisons.v1"


def test_invalid_contract_version_is_rejected() -> None:
    package = _package()
    package["contract_version"] = 2
    with pytest.raises(ValueError, match="version"):
        validate_presentation_comparison_package(package)


def test_cross_section_and_cross_report_identity_mismatch_are_rejected() -> None:
    package = _package()
    package["comparisons"][0]["section_key"] = "not-a-section"
    with pytest.raises(ValueError, match="section"):
        validate_presentation_comparison_package(package)
    package = _package()
    package["comparisons"][0]["report_id"] = "other-report"
    with pytest.raises(ValueError, match="identity"):
        validate_presentation_comparison_package(package)


def test_unequal_partial_coverage_withholds_deltas() -> None:
    package = _package(current_coverage="partial", prior_coverage="partial", eligible=False)
    entry = package["comparisons"][0]
    assert entry["delta_eligible"] is False
    assert entry["delta_ineligible_reason"]


def test_fake_provider_builds_all_ten_sections_for_all_twelve_presets() -> None:
    ga4 = _FakeGa4()
    package = build_real_presentation_comparisons(
        ga4_client=ga4, gsc_client=_FakeGsc(), profile="aluma-seo-geo",
        report_id=IDENTITY["report_id"], client_id=IDENTITY["client_id"], project_id=IDENTITY["project_id"],
        report_start=REPORT_START, report_end=REPORT_END, gsc_available_through=date(2026, 7, 5),
        generated_at="2026-07-13T00:00:00Z",
    )
    assert len(package["comparisons"]) == 120
    assert {entry["section_key"] for entry in package["comparisons"]} == {
        "ga4_top_metrics", "ga4_website_traffic_trends", "ga4_channel_performance", "ga4_user_engagement",
        "ga4_top_sources", "ga4_top_landing_pages", "ga4_most_viewed_pages", "gsc_summary", "gsc_top_queries", "gsc_top_pages",
    }
    this_month_gsc = next(entry for entry in package["comparisons"] if entry["section_key"] == "gsc_summary" and entry["preset_key"] == "this_month")
    assert this_month_gsc["current"]["coverage_state"] == "partial"
    assert this_month_gsc["comparison"]["coverage_state"] == "complete"
    assert this_month_gsc["delta_eligible"] is False
    assert ga4.summary_metric_names
    assert set(ga4.summary_metric_names) == {
        ("activeUsers", "sessions", "screenPageViews", "engagementRate", "engagedSessions")
    }


class _FakeGa4:
    def __init__(self):
        self.summary_metric_names = []

    def run_exact_range_summary(self, date_range, *, metric_names):
        self.summary_metric_names.append(metric_names)
        return {"metricHeaders": [{"name": key} for key in metric_names], "rows": [{"metricValues": [{"value": "10" if key != "engagementRate" else "0.5"} for key in metric_names]}]}

    def run_exact_range_traffic_series(self, date_range):
        return {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": "activeUsers"}, {"name": "sessions"}], "rows": [
            {"dimensionValues": [{"value": date_range.start.strftime("%Y%m%d")}], "metricValues": [{"value": "5"}, {"value": "7"}]},
            {"dimensionValues": [{"value": date_range.end.strftime("%Y%m%d")}], "metricValues": [{"value": "6"}, {"value": "8"}]},
        ]}

    def run_exact_range_channel_performance(self, date_range):
        return _ranked_ga4(["sessionDefaultChannelGroup"], ["Organic Search"], ["activeUsers", "sessions", "engagementRate"], ["9", "10", "0.5"])

    def run_exact_range_top_sources(self, date_range):
        return _ranked_ga4(["sessionSourceMedium"], ["google / organic"], ["activeUsers", "sessions", "engagementRate"], ["9", "10", "0.5"])

    def run_exact_range_top_landing_pages(self, date_range):
        return _ranked_ga4(["landingPagePlusQueryString"], ["/services"], ["activeUsers", "sessions", "engagedSessions"], ["9", "10", "7"])

    def run_exact_range_most_viewed_pages(self, date_range):
        return _ranked_ga4(["pageTitle", "pagePath"], ["Services", "/services"], ["screenPageViews", "activeUsers", "eventCount"], ["20", "9", "30"])


class _FakeGsc:
    def query_exact_range_summary(self, start, end): return {"rows": [{"clicks": 10, "impressions": 100, "ctr": .1, "position": 4.0}]}
    def query_exact_range_queries(self, start, end): return {"rows": [{"keys": ["aluma"], "clicks": 8, "impressions": 80, "ctr": .1, "position": 3.0}]}
    def query_exact_range_pages(self, start, end): return {"rows": [{"keys": ["/services"], "clicks": 7, "impressions": 70, "ctr": .1, "position": 2.0}]}


def _ranked_ga4(dimension_headers, dimension_values, metric_headers, metric_values):
    return {"dimensionHeaders": [{"name": key} for key in dimension_headers], "metricHeaders": [{"name": key} for key in metric_headers], "rows": [{"dimensionValues": [{"value": value} for value in dimension_values], "metricValues": [{"value": value} for value in metric_values]}]}


def _package(
    *, current_coverage: str = "complete", prior_coverage: str = "complete",
    current_state: str = "complete", prior_state: str = "complete", eligible: bool = True,
):
    current_range, prior_range = resolve_comparison_ranges("last_7_days", report_start=REPORT_START, report_end=REPORT_END)
    current = _state(current_range.start_date, current_range.end_date, current_state, current_coverage, lag_days=1)
    prior = _state(prior_range.start_date, prior_range.end_date, prior_state, prior_coverage, lag_days=2)
    entry = comparison_entry(
        package_identity=IDENTITY,
        section_key="ga4_top_metrics",
        preset_key="last_7_days",
        current=current,
        comparison=prior,
        current_lineage=LINEAGE,
        comparison_lineage=LINEAGE,
        delta_eligible=eligible,
        delta_ineligible_reason=None if eligible else "Requested coverage is not equivalent.",
        metrics=[build_metric_comparison(key="sessions", label="Sessions", unit="count", current_value=10, prior_value=5)],
    )
    return build_presentation_comparison_package(
        **IDENTITY,
        client_slug="fixture-client",
        report_start=REPORT_START,
        report_end=REPORT_END,
        comparisons=[entry],
        source_identity={"source_kind": "validated_fixture", "contains_real_data": False},
        generated_at="2026-07-13T00:00:00Z",
    )


def _state(start: date, end: date, data_state: str, coverage_state: str, *, lag_days: int):
    if coverage_state == "complete":
        return period_state(requested_start=start, requested_end=end, data_state=data_state, coverage_state=coverage_state)
    if coverage_state == "partial":
        actual_end = end - timedelta(days=lag_days)
        return period_state(
            requested_start=start, requested_end=end, data_state=data_state, coverage_state=coverage_state,
            actual_start=start, actual_end=actual_end, available_through=actual_end,
        )
    return period_state(requested_start=start, requested_end=end, data_state=data_state, coverage_state=coverage_state)
