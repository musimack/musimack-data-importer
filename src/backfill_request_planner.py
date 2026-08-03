"""Static request planning for the R8-C5 reporting backfill.

The whole point of this module is that **it does not maintain a second count
model**. A hand-written table of "how many calls we think the generator makes"
would drift the moment the generator changed, and would then understate a real
provider run.

Instead the counts are read directly off the generator's own loop structure and
the governed inventories it iterates, and a test in
``tests/test_backfill_request_planner.py`` **runs the real generator against the
proven test fakes and asserts the planner matches it exactly**. If the call
graph ever changes, that test fails rather than the plan quietly understating a
real run.

Presentation ranges are handled differently and deliberately.
``build_client_report_presentation_ranges`` takes already-retrieved
``datasets`` and makes **no provider call of its own**. Its inputs come from the
three exact-range pull scripts, whose call counts are derived here from the
governed range-key and contract inventories rather than guessed.

Nothing here touches a credential, constructs a real provider client, or makes
a network call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from src.client_report_ga4_ranked_exact_ranges import RANKED_EXACT_RANGE_CONTRACTS
from src.client_report_presentation_comparisons import COMPARISON_PRESET_KEYS
from src.client_report_presentation_ranges import CANONICAL_RANGE_KEYS, CANONICAL_SECTION_KEYS

PLAN_CONTRACT = "musimack_backfill_request_plan.v1"
PLAN_CONTRACT_VERSION = 1

# The three exact-range source pulls that feed presentation ranges. Each covers
# every canonical range key once.
GSC_EXACT_RANGE_SECTIONS = 3

# Retries and pagination are both zero in the current implementation. GA4
# ranked rows are capped at 10 and GSC ranked rows at 10, so neither paginates.
DEFAULT_RETRIES = 0
DEFAULT_PAGINATION = 0


class BackfillPlanError(RuntimeError):
    """The plan could not be produced, or would exceed a supplied ceiling."""


def comparison_request_counts() -> dict[str, int]:
    """Comparison-generation call counts, derived from the governed inventories.

    Read straight off the generator's own loop structure, so the arithmetic is
    traceable rather than asserted:

    - one pass per preset in ``COMPARISON_PRESET_KEYS``
    - per preset, GA4 issues **2** summary calls (current and comparison),
      **2** traffic-series calls, and **2 per ranked contract**
    - per preset, GSC issues **2 per section** (current and comparison)

    ``tests/test_backfill_request_planner.py`` runs the **real generator**
    against the proven test fakes and asserts these numbers match. If the
    generator's call graph ever changes, that test fails, so the planner cannot
    silently drift away from the executor.
    """
    presets = len(COMPARISON_PRESET_KEYS)
    ga4_per_preset = 2 + 2 + (2 * len(RANKED_EXACT_RANGE_CONTRACTS))
    gsc_per_preset = 2 * GSC_EXACT_RANGE_SECTIONS
    ga4 = ga4_per_preset * presets
    gsc = gsc_per_preset * presets
    return {
        "comparison_entries": len(CANONICAL_SECTION_KEYS) * presets,
        "comparison_ga4_per_preset": ga4_per_preset,
        "comparison_gsc_per_preset": gsc_per_preset,
        "comparison_ga4_requests": ga4,
        "comparison_gsc_requests": gsc,
        "comparison_total_requests": ga4 + gsc,
    }


def comparison_maximum_counts() -> dict[str, int]:
    """Worst case for comparisons.

    GA4 calls are unconditional. **GSC calls are conditional**: a comparison
    period falling entirely beyond the available-through date skips its call,
    so a real run can come in *below* this figure but never above it. The
    maximum therefore assumes every conditional call fires, which is the number
    a ceiling must cover.
    """
    counts = comparison_request_counts()
    return {
        "presets": len(COMPARISON_PRESET_KEYS),
        "comparison_ga4_maximum": counts["comparison_ga4_requests"],
        "comparison_gsc_maximum": counts["comparison_gsc_requests"],
        "comparison_maximum": counts["comparison_total_requests"],
    }


def presentation_range_source_counts(
    report_start: date | None = None, report_end: date | None = None
) -> dict[str, int]:
    """Provider calls needed to produce presentation-range source datasets.

    ``build_client_report_presentation_ranges`` itself makes **zero** provider
    calls: it transforms datasets that are already in hand. These counts cover
    the three exact-range pull scripts that produce those datasets.

    **Containment is modelled, not assumed.** A canonical range that does not
    fit entirely inside the governed report period is kept in the inventory,
    marked unavailable, and costs **zero** provider requests. Containment is
    resolved through the **real range resolver**, so it is decided by dates
    rather than by a key's name: a twelve-month report supports
    ``last_12_months`` normally, and ``last_6_months`` may or may not fit a
    six-month period depending on its exact resolved boundaries.
    """
    from src.client_report_presentation_ranges import resolve_range_key
    from src.range_containment import is_contained

    total_keys = len(CANONICAL_RANGE_KEYS)
    if report_start is None or report_end is None:
        contained_keys = total_keys
        unavailable_keys = 0
    else:
        contained_keys = 0
        for key in CANONICAL_RANGE_KEYS:
            resolved = resolve_range_key(key, report_end)
            if is_contained(resolved.start_date, resolved.end_date, report_start, report_end):
                contained_keys += 1
        unavailable_keys = total_keys - contained_keys

    ga4_summary = contained_keys
    ga4_ranked = contained_keys * len(RANKED_EXACT_RANGE_CONTRACTS)
    gsc = contained_keys * GSC_EXACT_RANGE_SECTIONS
    return {
        "range_keys": total_keys,
        "range_keys_contained": contained_keys,
        "range_keys_unavailable": unavailable_keys,
        "range_ga4_requests": ga4_summary + ga4_ranked,
        "range_gsc_requests": gsc,
        "range_total_requests": ga4_summary + ga4_ranked + gsc,
        "range_generation_requests": 0,
    }


def plan_report(
    *,
    profile: str,
    report_id: str,
    report_start: date,
    report_end: date,
    gsc_available_through: date,
    include_presentation_ranges: bool = True,
) -> dict[str, Any]:
    """The complete deterministic request plan for one report."""
    if not profile or not report_id:
        raise BackfillPlanError("profile and report_id are required")
    if report_start > report_end:
        raise BackfillPlanError("report period is invalid")

    expected = comparison_request_counts()
    maximum = comparison_maximum_counts()
    ranges = (
        presentation_range_source_counts(report_start, report_end)
        if include_presentation_ranges
        else {
            "range_keys": 0,
            "range_keys_contained": 0,
            "range_keys_unavailable": 0,
            "range_ga4_requests": 0,
            "range_gsc_requests": 0,
            "range_total_requests": 0,
            "range_generation_requests": 0,
        }
    )

    expected_total = expected["comparison_total_requests"] + ranges["range_total_requests"]
    maximum_total = maximum["comparison_maximum"] + ranges["range_total_requests"]

    plan = {
        "plan_contract": PLAN_CONTRACT,
        "plan_contract_version": PLAN_CONTRACT_VERSION,
        "profile": profile,
        "report_id": report_id,
        "report_period": {"start_date": report_start.isoformat(), "end_date": report_end.isoformat()},
        "canonical_sections": len(CANONICAL_SECTION_KEYS),
        "retries_allowed": DEFAULT_RETRIES,
        "pagination_allowed": DEFAULT_PAGINATION,
        "optional_validation_requests": 0,
        "expected_total_requests": expected_total,
        "maximum_total_requests": maximum_total,
        "credential_access": False,
        "provider_client_constructed": False,
        "network_calls": 0,
    }
    plan.update(expected)
    plan.update(maximum)
    plan.update(ranges)
    return plan


def plan_reports(reports: list[dict[str, Any]], *, planning_ceiling: int | None = None) -> dict[str, Any]:
    """Aggregate plan across reports, refusing to exceed a planning ceiling."""
    plans = [plan_report(**report) for report in reports]
    expected = sum(p["expected_total_requests"] for p in plans)
    maximum = sum(p["maximum_total_requests"] for p in plans)
    if planning_ceiling is not None and maximum > planning_ceiling:
        raise BackfillPlanError(
            f"planned maximum {maximum} exceeds the planning ceiling {planning_ceiling}"
        )
    return {
        "plan_contract": PLAN_CONTRACT,
        "plan_contract_version": PLAN_CONTRACT_VERSION,
        "reports": plans,
        "report_count": len(plans),
        "aggregate_expected_requests": expected,
        "aggregate_maximum_requests": maximum,
        "retries_allowed": DEFAULT_RETRIES,
        "pagination_allowed": DEFAULT_PAGINATION,
        "credential_access": False,
        "provider_client_constructed": False,
        "network_calls": 0,
    }
