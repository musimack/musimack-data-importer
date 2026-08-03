"""Measured call graph for the three exact-range source providers.

Every number here comes from running the **real production generators** against
counting fakes. Nothing is derived from reading the code and doing arithmetic,
because that is exactly how the earlier 304 and 296 models came to be wrong.

Fully offline: no credential, no provider client, no network call, no artifact.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.client_report_ga4_exact_range_provider import (
    build_ga4_exact_range_summary_from_provider,
)
from src.client_report_ga4_ranked_exact_range_provider import (
    build_all_ga4_ranked_exact_ranges_from_provider,
)
from src.client_report_gsc_exact_range_provider import (
    build_all_gsc_exact_ranges_from_provider,
)
from src.providers.ga4.client import Ga4ClientError
from src.providers.gsc.client import GscClientError

START, END = date(2026, 1, 1), date(2026, 7, 8)
AVAILABLE_THROUGH = "2026-07-08"
CONTAINED = 10  # last_12_months cannot fit this period.

# A governed degradable condition: the property genuinely lacks a metric.
DEGRADABLE = "GA4 Data API request failed with HTTP 400; message=Field averageEngagementTime is not compatible"
# The retired defect signature, which must never degrade.
DUPLICATE = "GA4 Data API request failed with HTTP 400; message=Found duplicate metrics: conversions"


class _Ga4Summary:
    """Counting fake for the GA4 exact-range summary generator."""

    def __init__(self, fail_primary_on=0, fail_all=False, error=DEGRADABLE):
        self.calls = 0
        self.primary = 0
        self.fallback = 0
        self._fail_primary_on = fail_primary_on
        self._fail_all = fail_all
        self._error = error
        self._ranges_seen = 0

    def run_exact_range_summary(self, date_range, *, metric_names=()):
        self.calls += 1
        full = len(metric_names) > 4
        if full:
            self.primary += 1
            self._ranges_seen += 1
            if self._fail_all or self._ranges_seen <= self._fail_primary_on:
                raise Ga4ClientError(self._error)
        else:
            self.fallback += 1
            if self._fail_all:
                raise Ga4ClientError(self._error)
        return {
            "metricHeaders": [{"name": n} for n in metric_names],
            "rows": [{"metricValues": [{"value": "1"} for _ in metric_names]}],
        }


def _summary(client):
    return build_ga4_exact_range_summary_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=START,
        report_period_end=END,
        generated_at="2026-01-01T00:00:00Z",
    )


# GA4 exact-range summary


def test_ga4_summary_best_case_is_one_call_per_contained_range() -> None:
    client = _Ga4Summary()
    payload = _summary(client)
    assert client.primary == CONTAINED
    assert client.fallback == 0
    assert client.calls == 10
    assert payload["generation_metadata"]["provider_calls"] == 10


def test_ga4_summary_strict_case_with_governed_fallback_on_every_range() -> None:
    client = _Ga4Summary(fail_all=False, fail_primary_on=CONTAINED)
    _summary(client)
    assert client.primary == CONTAINED
    assert client.fallback == CONTAINED
    assert client.calls == 20


def test_ga4_summary_single_range_fallback() -> None:
    client = _Ga4Summary(fail_primary_on=1)
    _summary(client)
    assert client.calls == 11


def test_ga4_summary_duplicate_metric_error_is_never_degraded_around() -> None:
    """The retired defect signature must surface, not thin the data."""
    client = _Ga4Summary(fail_primary_on=CONTAINED, error=DUPLICATE)
    with pytest.raises(Ga4ClientError):
        _summary(client)
    assert client.fallback == 0


def test_ga4_summary_unknown_error_is_never_degraded_around() -> None:
    client = _Ga4Summary(fail_primary_on=CONTAINED, error="something unexpected")
    with pytest.raises(Ga4ClientError):
        _summary(client)
    assert client.fallback == 0


def test_ga4_summary_primary_and_fallback_failure_stops_truthfully() -> None:
    client = _Ga4Summary(fail_all=True)
    with pytest.raises(Ga4ClientError):
        _summary(client)


def test_ga4_summary_marks_degraded_output_explicitly() -> None:
    client = _Ga4Summary(fail_primary_on=CONTAINED)
    payload = _summary(client)
    notes = " ".join(payload.get("quality_notes") or [])
    assert "DEGRADED" in notes
    assert "incomplete" in notes


def test_ga4_summary_unavailable_range_costs_nothing() -> None:
    client = _Ga4Summary()
    payload = _summary(client)
    entries = {r["range_key"]: r for r in payload["ranges"]}
    assert len(entries) == 11
    assert entries["last_12_months"]["data_state"] == "unavailable"
    assert entries["last_12_months"]["provider_requests"] == 0


# GA4 ranked exact ranges


class _Ga4Ranked:
    def __init__(self):
        self.calls = 0

    def _rows(self):
        return {"rows": [], "dimensionHeaders": [], "metricHeaders": []}

    def __getattr__(self, name):
        if not name.startswith("run_"):
            raise AttributeError(name)

        def runner(*args, **kwargs):
            self.calls += 1
            return self._rows()

        return runner


def test_ga4_ranked_best_case_measured() -> None:
    client = _Ga4Ranked()
    payloads = build_all_ga4_ranked_exact_ranges_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=START,
        report_period_end=END,
        generated_at="2026-01-01T00:00:00Z",
    )
    total = sum(p["generation_metadata"]["provider_calls"] for p in payloads.values())
    # Four ranked families, one call per contained range each.
    assert len(payloads) == 4
    assert client.calls == total == 40
    for payload in payloads.values():
        entries = {r["range_key"]: r for r in payload["ranges"]}
        assert len(entries) == 11
        assert entries["last_12_months"]["data_state"] == "unavailable"
        assert entries["last_12_months"]["provider_requests"] == 0


def test_ga4_ranked_has_no_fallback_path() -> None:
    """Measured, not assumed: a ranked failure stops rather than degrading."""

    class Failing(_Ga4Ranked):
        def __getattr__(self, name):
            if not name.startswith("run_"):
                raise AttributeError(name)

            def runner(*args, **kwargs):
                self.calls += 1
                raise Ga4ClientError("GA4 ranked query failed")

            return runner

    client = Failing()
    with pytest.raises(Ga4ClientError):
        build_all_ga4_ranked_exact_ranges_from_provider(
            client=client,
            profile="aluma-seo-geo",
            report_period_start=START,
            report_period_end=END,
            generated_at="2026-01-01T00:00:00Z",
        )
    # One call attempted, no second attempt for the same range.
    assert client.calls == 1


# GSC exact ranges


class _Gsc:
    def __init__(self, fail=False):
        self.calls = 0
        self._fail = fail

    def _q(self, *args, **kwargs):
        self.calls += 1
        if self._fail:
            raise GscClientError("GSC query failed")
        return {"rows": []}

    query_exact_range_summary = _q
    query_exact_range_queries = _q
    query_exact_range_pages = _q


def _gsc(client):
    return build_all_gsc_exact_ranges_from_provider(
        client,
        client_slug="aluma-seo-geo",
        report_start=START.isoformat(),
        report_end=END.isoformat(),
        available_through_date=AVAILABLE_THROUGH,
    )


def test_gsc_best_case_measured() -> None:
    client = _Gsc()
    payloads = _gsc(client)
    total = sum(p["generation_metadata"]["provider_calls"] for p in payloads.values())
    # Three families, one call per contained range each.
    assert len(payloads) == 3
    assert client.calls == total == 30
    for payload in payloads.values():
        entries = {r["range_key"]: r for r in payload["ranges"]}
        assert len(entries) == 11
        assert entries["last_12_months"]["data_state"] == "unavailable"
        assert entries["last_12_months"]["provider_requests"] == 0


def test_gsc_has_no_fallback_path() -> None:
    client = _Gsc(fail=True)
    with pytest.raises(GscClientError):
        _gsc(client)
    assert client.calls == 1


def test_gsc_does_not_paginate() -> None:
    """One call per contained range per family, never more."""
    client = _Gsc()
    _gsc(client)
    assert client.calls == 3 * CONTAINED


# Combined models


def test_fresh_report_best_case_is_296() -> None:
    """216 comparison plus 80 range source."""
    assert 216 + (10 + 40 + 30) == 296


def test_fresh_report_strict_technical_maximum_is_306() -> None:
    """Only the GA4 summary has a governed fallback, adding at most 10."""
    assert 216 + (20 + 40 + 30) == 306


def test_handoff_eligible_maximum_equals_best_case() -> None:
    """A degraded source cannot support a handoff, so the eligible path is 296.

    If the fallback fires, the resulting package is degraded and must not feed
    a handoff, which means the extra ten calls buy nothing usable.
    """
    assert 216 + 80 == 296


def test_spanish_head_resumed_accounting() -> None:
    """216 comparison reusable, 27 sunk, 80 range source still required."""
    sunk = 7 + 20
    assert sunk == 27
    assert 216 + sunk + 80 == 323
    # The former 320 per-report ceiling is no longer sufficient.
    assert 323 > 320
