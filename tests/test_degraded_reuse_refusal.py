"""Reuse must never carry a degraded exact-range entry forward.

Reproduces the exact defect observed live on Inn At Spanish Head. A
regeneration reported ``GA4 Data API calls: 0; reused ranges: 10`` and silently
returned the degraded four-metric entries, because reuse matched on
``(range_key, start, end)`` identity alone. A degraded entry has the right key
and the right dates, so identity could not distinguish it from a good one.

Fully offline. No credential, no provider client, no network call, and no real
client payload.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest

from src.client_report_ga4_exact_range_provider import (
    _reusable_entries,
    build_ga4_exact_range_summary_from_provider,
)
from src.range_containment import OUT_OF_PERIOD_REASON

START, END = date(2026, 1, 1), date(2026, 7, 8)
PROFILE = "inn-at-spanish-head"

NINE_METRICS = {
    "users": 10, "new_users": 4, "sessions": 12, "views": 30,
    "engaged_sessions": 8, "engagement_rate": 0.7,
    "average_session_duration_seconds": 60, "event_count": 90, "key_events": 2,
}
# The exact degraded shape the retired fallback produced: four metrics only.
FOUR_METRICS = {"users": 10, "sessions": 12, "views": 30, "engagement_rate": 0.7}
DEGRADED_NOTE = (
    "DEGRADED: optional GA4 metrics omitted after a governed safe retry; "
    "metric coverage is incomplete"
)


def _entry(state="available", metrics=None, notes=None, key="last_7_days"):
    return {
        "range_key": key,
        "requested_start_date": "2026-07-02",
        "requested_end_date": "2026-07-08",
        "inclusive_dates": True,
        "data_state": state,
        "coverage_state": "complete" if state == "available" else state,
        "quality_state": "passed",
        "expected_date_count": 7,
        "actual_date_count": 7,
        "metrics": NINE_METRICS if metrics is None else metrics,
        "quality_notes": notes or [],
    }


def _payload(entries):
    return {
        "client_slug": PROFILE,
        "report_period": {"start_date": START.isoformat(), "end_date": END.isoformat()},
        "ranges": entries,
    }


def _reuse(entries):
    # Bypasses contract validation to test the reuse filter in isolation.
    payload = _payload(entries)
    import src.client_report_ga4_exact_range_provider as provider

    original = provider.validate_ga4_exact_range_summary_contract
    provider.validate_ga4_exact_range_summary_contract = lambda _p: None
    try:
        return _reusable_entries(payload, PROFILE, START, END)
    finally:
        provider.validate_ga4_exact_range_summary_contract = original


# The exact live defect


def test_a_degraded_entry_with_matching_identity_is_refused_for_reuse() -> None:
    """The Spanish Head defect: right key, right dates, four metrics."""
    degraded = _entry(metrics=FOUR_METRICS, notes=[DEGRADED_NOTE])
    assert _reuse([degraded]) == {}


def test_refusing_reuse_forces_a_fresh_provider_call(monkeypatch) -> None:
    """The whole point: a dropped entry must be re-fetched, not skipped."""
    import src.client_report_ga4_exact_range_provider as provider

    # The minimal existing payload here exercises the reuse filter, not the
    # full contract, so contract validation is stubbed for this test only.
    monkeypatch.setattr(provider, "validate_ga4_exact_range_summary_contract", lambda _p: None)

    class _Counting:
        def __init__(self):
            self.calls = 0

        def run_exact_range_summary(self, date_range, *, metric_names=()):
            self.calls += 1
            return {
                "metricHeaders": [{"name": n} for n in metric_names],
                "rows": [{"metricValues": [{"value": "1"} for _ in metric_names]}],
            }

    client = _Counting()
    degraded_existing = _payload(
        [_entry(metrics=FOUR_METRICS, notes=[DEGRADED_NOTE], key=key)
         for key in ("last_3_days", "last_7_days")]
    )
    build_ga4_exact_range_summary_from_provider(
        client=client,
        profile=PROFILE,
        report_period_start=START,
        report_period_end=END,
        generated_at="2026-01-01T00:00:00Z",
        existing_payload=degraded_existing,
    )
    # Ten contained ranges, none reusable, so every one is fetched fresh.
    assert client.calls == 10


# What may still be reused


def test_a_full_nine_metric_entry_is_reusable() -> None:
    assert len(_reuse([_entry()])) == 1


def test_a_truthful_unavailable_entry_is_reusable() -> None:
    unavailable = {
        "range_key": "last_12_months",
        "requested_start_date": "2025-07-09",
        "requested_end_date": "2026-07-08",
        "data_state": "unavailable",
        "coverage_state": "unavailable",
        "availability_reason": OUT_OF_PERIOD_REASON,
        "contained_in_report_period": False,
        "provider_requests": 0,
    }
    assert len(_reuse([unavailable])) == 1


def test_a_truthful_provider_empty_entry_is_reusable() -> None:
    assert len(_reuse([_entry(state="empty", metrics={})])) == 1


# What else is refused


def test_a_failed_entry_is_refused() -> None:
    bad = _entry()
    bad["data_state"] = "unavailable"
    bad["availability_reason"] = ""
    assert _reuse([bad]) == {}


def test_an_unknown_status_is_refused() -> None:
    assert _reuse([_entry(state="something_new")]) == {}


def test_a_missing_status_is_refused() -> None:
    entry = _entry()
    entry.pop("data_state")
    assert _reuse([entry]) == {}


def test_reuse_is_allowlisted_not_denylisted() -> None:
    """Only known-safe states survive, so a novel state is never reused."""
    assert _reuse([_entry(state="probationary")]) == {}


def test_mixed_entries_keep_only_the_eligible_ones() -> None:
    entries = [
        _entry(key="last_3_days"),
        _entry(key="last_7_days", metrics=FOUR_METRICS, notes=[DEGRADED_NOTE]),
    ]
    reusable = _reuse(entries)
    assert len(reusable) == 1
    assert all(key[0] == "last_3_days" for key in reusable)


# The source artifact is never mutated


def test_refusing_reuse_does_not_mutate_the_source_artifact() -> None:
    degraded = _entry(metrics=FOUR_METRICS, notes=[DEGRADED_NOTE])
    before = copy.deepcopy(degraded)
    _reuse([degraded])
    assert degraded == before


def test_the_reuse_filter_makes_no_network_call(monkeypatch) -> None:
    import requests

    def guard(*args, **kwargs):
        raise AssertionError("the reuse filter attempted a network request")

    monkeypatch.setattr(requests.Session, "request", guard)
    monkeypatch.setattr(requests, "get", guard)
    assert len(_reuse([_entry()])) == 1
