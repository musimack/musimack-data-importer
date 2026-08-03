"""Report-period containment for canonical presentation ranges.

A canonical range key such as ``last_12_months`` resolves to a concrete
inclusive date range. When a governed report period is shorter than that range,
the range genuinely cannot exist inside the period.

The previous behavior raised, which aborted the whole retrieval and left a
report with no presentation ranges at all. That was wrong in a specific way: it
treated a **truthful absence** as a **failure**.

The governed semantics, decided by David Wallace on 2026-08-02, are:

- **Keep the canonical key.** The inventory stays complete, so a consumer can
  see that the range was considered.
- **Mark it unavailable**, with a non-empty governed reason.
- **Make zero provider requests for it.**
- **Never clamp, shorten, or substitute** the range, and never change the
  report period.

Containment is decided from **resolved dates**, never from the key's name. A
twelve-month report period supports ``last_12_months`` normally, and
``last_6_months`` may or may not fit a six-month report depending on its exact
resolved boundaries. Only the arithmetic decides.

An unavailable range is deliberately distinguishable from empty provider data,
provider failure, missing credentials, partial coverage, and unknown errors.
"""

from __future__ import annotations

from datetime import date
from typing import Any

OUT_OF_PERIOD_REASON = "Requested range falls outside the governed report period."

# Marks a range excluded by containment rather than by any provider outcome.
OUT_OF_PERIOD_STATE = "unavailable"


def is_contained(start_date: date, end_date: date, period_start: date, period_end: date) -> bool:
    """Is this resolved range fully inside the governed report period?

    Decided purely by the resolved inclusive dates.
    """
    return start_date >= period_start and end_date <= period_end


def unavailable_range_entry(
    range_key: str,
    start_date: date,
    end_date: date,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A truthful out-of-period range entry that cost no provider request.

    Carries no metrics and no rows, which is what distinguishes it from an
    empty result: empty means the provider was asked and returned nothing,
    while this means the provider was never asked because the question was not
    answerable inside the governed period.
    """
    entry: dict[str, Any] = {
        "range_key": range_key,
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "expected_date_count": (end_date - start_date).days + 1,
        "data_state": OUT_OF_PERIOD_STATE,
        "coverage_state": OUT_OF_PERIOD_STATE,
        "availability_reason": OUT_OF_PERIOD_REASON,
        "contained_in_report_period": False,
        "provider_requests": 0,
    }
    if extra:
        entry.update(extra)
    return entry


def partition_ranges(
    resolved_ranges: list[Any], period_start: date, period_end: date
) -> tuple[list[Any], list[Any]]:
    """Split resolved ranges into contained and out-of-period, order preserved.

    Order is preserved so the emitted inventory keeps its canonical sequence
    and evidence stays deterministic.
    """
    contained: list[Any] = []
    excluded: list[Any] = []
    for resolved in resolved_ranges:
        if is_contained(resolved.start_date, resolved.end_date, period_start, period_end):
            contained.append(resolved)
        else:
            excluded.append(resolved)
    return contained, excluded
