"""R8-C5 reporting backfill request planner.

Fully offline: no credential is read, no provider client is constructed, and no
network call is made.

The most important test here is the drift guard. It runs the **real** comparison
generator against the proven fakes and asserts the planner's arithmetic matches
the calls the generator actually issues.
"""

from __future__ import annotations

import json
import sys
from datetime import date

import pytest

from src.backfill_request_planner import (
    DEFAULT_PAGINATION,
    DEFAULT_RETRIES,
    PLAN_CONTRACT,
    BackfillPlanError,
    comparison_maximum_counts,
    comparison_request_counts,
    plan_report,
    plan_reports,
    presentation_range_source_counts,
)

PERIOD = dict(report_start=date(2026, 1, 1), report_end=date(2026, 7, 8), gsc_available_through=date(2026, 7, 5))


def _report(profile="aluma-seo-geo", report_id="r1", **overrides):
    return dict(profile=profile, report_id=report_id, **{**PERIOD, **overrides})


# The drift guard


def test_planner_matches_the_real_generator_call_graph() -> None:
    """The planner must not drift from the executor.

    Runs the real generator with the proven test fakes and compares the calls
    it actually issues against the planner's arithmetic. GSC is compared as an
    upper bound because its calls are conditional on the available-through
    date, so a real run can fall below the maximum but never above it.
    """
    sys.path.insert(0, "tests")
    import test_client_report_presentation_comparisons as fixtures

    from src.client_report_presentation_comparison_provider import (
        build_real_presentation_comparisons,
    )
    from src.profile_authorization import ProfileAuthorization

    package = build_real_presentation_comparisons(
        ga4_client=fixtures._FakeGa4(),
        gsc_client=fixtures._FakeGsc(),
        profile="aluma-seo-geo",
        report_id=fixtures.IDENTITY["report_id"],
        client_id=fixtures.IDENTITY["client_id"],
        project_id=fixtures.IDENTITY["project_id"],
        report_start=fixtures.REPORT_START,
        report_end=fixtures.REPORT_END,
        gsc_available_through=date(2026, 7, 5),
        generated_at="2026-07-13T00:00:00Z",
        authorization=ProfileAuthorization(
            requested_profile="aluma-seo-geo", authorized_profiles=("aluma-seo-geo",)
        ),
    )
    actual_ga4 = package["source_identity"]["ga4_provider_calls"]
    actual_gsc = package["source_identity"]["gsc_provider_calls"]
    planned = comparison_request_counts()

    assert len(package["comparisons"]) == planned["comparison_entries"] == 120
    # GA4 calls are unconditional, so the plan must match exactly.
    assert actual_ga4 == planned["comparison_ga4_requests"] == 144
    # GSC calls are conditional, so the plan is an upper bound that must hold.
    assert actual_gsc <= planned["comparison_gsc_requests"] == 72
    assert actual_gsc > 0


# Counts


def test_comparison_counts_are_deterministic() -> None:
    assert comparison_request_counts() == comparison_request_counts()


def test_comparison_per_preset_arithmetic_is_explicit() -> None:
    counts = comparison_request_counts()
    # 2 summary + 2 traffic series + 2 per ranked contract, over 12 presets.
    assert counts["comparison_ga4_per_preset"] == 12
    assert counts["comparison_gsc_per_preset"] == 6
    assert counts["comparison_ga4_requests"] == 12 * 12
    assert counts["comparison_gsc_requests"] == 6 * 12


def test_comparison_maximum_covers_the_expected_plan() -> None:
    assert comparison_maximum_counts()["comparison_maximum"] >= (
        comparison_request_counts()["comparison_total_requests"]
    )


def test_presentation_range_generation_makes_no_provider_call() -> None:
    """Range generation transforms datasets already in hand."""
    ranges = presentation_range_source_counts()
    assert ranges["range_generation_requests"] == 0
    # Its source pulls do cost calls: 11 range keys across the three sources.
    assert ranges["range_keys"] == 11
    assert ranges["range_ga4_requests"] == 11 + (11 * 4)
    assert ranges["range_gsc_requests"] == 11 * 3
    assert ranges["range_total_requests"] == 88


def test_per_report_total_is_exactly_304() -> None:
    plan = plan_report(**_report())
    assert plan["expected_total_requests"] == 304
    assert plan["maximum_total_requests"] == 304


def test_retries_and_pagination_are_zero() -> None:
    plan = plan_report(**_report())
    assert plan["retries_allowed"] == DEFAULT_RETRIES == 0
    assert plan["pagination_allowed"] == DEFAULT_PAGINATION == 0


def test_optional_validation_is_separated_and_zero() -> None:
    assert plan_report(**_report())["optional_validation_requests"] == 0


# Aggregation


def test_per_client_totals_sum_to_the_aggregate() -> None:
    reports = [_report(report_id=f"r{i}") for i in range(5)]
    aggregate = plan_reports(reports)
    assert aggregate["report_count"] == 5
    assert aggregate["aggregate_maximum_requests"] == sum(
        p["maximum_total_requests"] for p in aggregate["reports"]
    )
    assert aggregate["aggregate_maximum_requests"] == 5 * 304 == 1520


def test_group_totals_are_deterministic() -> None:
    reports = [_report(report_id=f"r{i}") for i in range(3)]
    assert json.dumps(plan_reports(reports), sort_keys=True) == json.dumps(
        plan_reports(reports), sort_keys=True
    )


def test_identical_inputs_produce_byte_identical_plans() -> None:
    assert json.dumps(plan_report(**_report()), sort_keys=True) == json.dumps(
        plan_report(**_report()), sort_keys=True
    )


# Failure modes


def test_missing_report_identity_fails() -> None:
    with pytest.raises(BackfillPlanError):
        plan_report(**_report(report_id=""))


def test_missing_profile_fails() -> None:
    with pytest.raises(BackfillPlanError):
        plan_report(**_report(profile=""))


def test_invalid_period_fails() -> None:
    with pytest.raises(BackfillPlanError):
        plan_report(**_report(report_start=date(2026, 8, 1), report_end=date(2026, 1, 1)))


def test_planning_ceiling_is_enforced() -> None:
    with pytest.raises(BackfillPlanError) as exc:
        plan_reports([_report()], planning_ceiling=100)
    assert "exceeds the planning ceiling" in str(exc.value)


def test_a_sufficient_planning_ceiling_passes() -> None:
    assert plan_reports([_report()], planning_ceiling=304)["aggregate_maximum_requests"] == 304


# Safety boundaries


def test_plan_records_that_nothing_was_contacted() -> None:
    plan = plan_report(**_report())
    assert plan["credential_access"] is False
    assert plan["provider_client_constructed"] is False
    assert plan["network_calls"] == 0
    assert plan["plan_contract"] == PLAN_CONTRACT


def test_planning_writes_no_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plan_report(**_report())
    plan_reports([_report()])
    assert list(tmp_path.iterdir()) == []


def test_planning_makes_no_network_call(monkeypatch) -> None:
    import requests

    def guard(*args, **kwargs):
        raise AssertionError("planning attempted a network request")

    monkeypatch.setattr(requests.Session, "request", guard)
    monkeypatch.setattr(requests, "get", guard)
    monkeypatch.setattr(requests, "post", guard)
    assert plan_report(**_report())["network_calls"] == 0


def test_planning_generates_no_contract_or_range_or_handoff() -> None:
    """Planning is arithmetic. It produces no artifact of any kind."""
    plan = plan_report(**_report())
    assert "comparisons" not in plan
    assert "section_buckets" not in plan
    assert "schema_version" not in plan
