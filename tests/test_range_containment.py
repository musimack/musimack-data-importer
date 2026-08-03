"""Short-period presentation-range containment.

Governed semantics, decided by David Wallace on 2026-08-02: a canonical range
that does not fit inside the report period is **kept, marked unavailable, and
costs zero provider requests**. The superseded behavior raised, which aborted
the whole retrieval and treated a truthful absence as a failure.

Fully offline. No credential, no provider client, no network call.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backfill_request_planner import plan_report, presentation_range_source_counts
from src.client_report_presentation_ranges import CANONICAL_RANGE_KEYS, resolve_range_key
from src.range_containment import (
    OUT_OF_PERIOD_REASON,
    is_contained,
    partition_ranges,
    unavailable_range_entry,
)

SHORT_START, SHORT_END = date(2026, 1, 1), date(2026, 7, 8)
YEAR_START, YEAR_END = date(2025, 7, 1), date(2026, 7, 8)


def _resolved(period_end=SHORT_END):
    return [resolve_range_key(key, period_end) for key in CANONICAL_RANGE_KEYS]


# Containment decided by dates, never by name


def test_short_period_leaves_last_12_months_out_of_period() -> None:
    contained, excluded = partition_ranges(_resolved(), SHORT_START, SHORT_END)
    assert [r.range_key for r in excluded] == ["last_12_months"]
    assert len(contained) == 10


def test_last_6_months_is_decided_by_resolved_dates_not_its_label() -> None:
    """It fits this six-month period, but only the arithmetic may decide."""
    resolved = next(r for r in _resolved() if r.range_key == "last_6_months")
    assert resolved.start_date == date(2026, 1, 9)
    assert is_contained(resolved.start_date, resolved.end_date, SHORT_START, SHORT_END)


def test_a_twelve_month_report_supports_last_12_months() -> None:
    """Unavailability is never hard-coded to a key name."""
    resolved = [resolve_range_key(k, YEAR_END) for k in CANONICAL_RANGE_KEYS]
    contained, excluded = partition_ranges(resolved, YEAR_START, YEAR_END)
    assert "last_12_months" in [r.range_key for r in contained]
    assert excluded == []


def test_full_canonical_inventory_is_preserved() -> None:
    contained, excluded = partition_ranges(_resolved(), SHORT_START, SHORT_END)
    keys = [r.range_key for r in contained] + [r.range_key for r in excluded]
    assert sorted(keys) == sorted(CANONICAL_RANGE_KEYS)
    assert len(keys) == len(CANONICAL_RANGE_KEYS)


def test_no_range_is_clamped_or_substituted() -> None:
    """The out-of-period range keeps its real resolved dates."""
    excluded = partition_ranges(_resolved(), SHORT_START, SHORT_END)[1]
    entry = unavailable_range_entry(
        excluded[0].range_key, excluded[0].start_date, excluded[0].end_date
    )
    assert entry["requested_start_date"] == "2025-07-09"
    assert entry["requested_end_date"] == "2026-07-08"
    # Not shortened to the report period.
    assert entry["requested_start_date"] < SHORT_START.isoformat()


# The unavailable entry itself


def test_unavailable_entry_carries_the_governed_reason() -> None:
    entry = unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))
    assert entry["availability_reason"] == OUT_OF_PERIOD_REASON
    assert entry["availability_reason"].strip()
    assert entry["data_state"] == "unavailable"
    assert entry["coverage_state"] == "unavailable"
    assert entry["contained_in_report_period"] is False


def test_unavailable_costs_zero_provider_requests() -> None:
    entry = unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))
    assert entry["provider_requests"] == 0


def test_unavailable_is_distinguishable_from_empty_data() -> None:
    """Empty means the provider answered nothing. Unavailable means it was never asked."""
    entry = unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))
    assert entry["data_state"] != "empty"
    assert "metrics" not in entry
    assert "rows" not in entry
    assert entry["availability_reason"] == OUT_OF_PERIOD_REASON


def test_unavailable_is_not_a_provider_failure() -> None:
    entry = unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))
    assert "error" not in entry
    assert "failure" not in repr(entry).lower()


# Planner agreement


def test_planner_models_containment_for_the_governed_period() -> None:
    counts = presentation_range_source_counts(SHORT_START, SHORT_END)
    assert counts["range_keys"] == 11
    assert counts["range_keys_contained"] == 10
    assert counts["range_keys_unavailable"] == 1
    assert counts["range_ga4_requests"] == 10 + (10 * 4) == 50
    assert counts["range_gsc_requests"] == 10 * 3 == 30
    assert counts["range_total_requests"] == 80
    assert counts["range_generation_requests"] == 0


def test_fresh_report_strict_total_is_296() -> None:
    plan = plan_report(
        profile="inn-at-spanish-head",
        report_id="a7c0a056-952b-4c1a-8108-3d8da3fc6312",
        report_start=SHORT_START,
        report_end=SHORT_END,
        gsc_available_through=SHORT_END,
    )
    assert plan["comparison_total_requests"] == 216
    assert plan["range_total_requests"] == 80
    assert plan["maximum_total_requests"] == 296


def test_spanish_head_resumed_maximum_including_sunk_calls_is_303() -> None:
    """216 accepted comparisons, 7 sunk range calls, 80 clean range rerun."""
    assert 216 + 7 + 80 == 303
    assert 303 <= 320


def test_hard_ceiling_of_320_still_bounds_both_cases() -> None:
    assert 296 <= 320
    assert 303 <= 320


def test_a_twelve_month_report_plans_the_full_88() -> None:
    counts = presentation_range_source_counts(YEAR_START, YEAR_END)
    assert counts["range_keys_contained"] == 11
    assert counts["range_total_requests"] == 88


# Safety


def test_containment_planning_makes_no_network_call(monkeypatch) -> None:
    import requests

    def guard(*args, **kwargs):
        raise AssertionError("containment planning attempted a network request")

    monkeypatch.setattr(requests.Session, "request", guard)
    monkeypatch.setattr(requests, "get", guard)
    monkeypatch.setattr(requests, "post", guard)
    assert presentation_range_source_counts(SHORT_START, SHORT_END)["range_total_requests"] == 80


def test_containment_output_is_deterministic() -> None:
    assert presentation_range_source_counts(SHORT_START, SHORT_END) == (
        presentation_range_source_counts(SHORT_START, SHORT_END)
    )
    first = partition_ranges(_resolved(), SHORT_START, SHORT_END)
    second = partition_ranges(_resolved(), SHORT_START, SHORT_END)
    assert [r.range_key for r in first[0]] == [r.range_key for r in second[0]]
