"""Handoff eligibility for presentation-range source packages.

A completed handoff must never be built from a source package that returned
less than its governed coverage. The duplicate-metric defect showed why: a
fallback silently reduced a GA4 exact-range summary from nine provider metrics
to four, and the package still validated and still reported ranges as
``available``. Nothing downstream could tell the difference.

This module makes the difference explicit and refuses the ineligible cases.

Five states, deliberately not collapsed into a boolean:

``FULL``
    Complete governed coverage. Eligible.

``UNAVAILABLE``
    A canonical range that cannot be supported, such as one falling outside the
    governed report period. Requires a non-empty reason, zero provider calls,
    and no data payload. **Eligible**, because a truthful absence is not a
    defect.

``EMPTY``
    The provider was asked and truthfully returned no rows. **Eligible** where
    section semantics already allow provider-empty data. Emptiness is a fact
    about the client, not a gap in retrieval.

``DEGRADED``
    A fallback or limitation produced less than governed coverage. **Not
    eligible**, because no versioned accepted-limitation contract exists to
    authorize publishing partial coverage as though it were complete.

``FAILED``
    The call or validation failed. **Not eligible.**

An unknown or missing state is refused rather than assumed benign, so a future
source shape cannot slip through by omitting its status.
"""

from __future__ import annotations

from typing import Any

FULL = "full"
UNAVAILABLE = "unavailable"
EMPTY = "empty"
DEGRADED = "degraded"
FAILED = "failed"

ELIGIBLE_STATES = frozenset({FULL, UNAVAILABLE, EMPTY})
INELIGIBLE_STATES = frozenset({DEGRADED, FAILED})

# Set only when a versioned contract explicitly authorizes publishing a
# degraded package. None exists, so degraded always rejects today.
ACCEPTED_LIMITATION_CONTRACTS: frozenset[str] = frozenset()

# Markers the generators write when a fallback narrowed coverage.
DEGRADED_MARKERS = ("DEGRADED", "after safe retry", "metric coverage is incomplete")


class DegradedSourceError(RuntimeError):
    """A source package cannot support a completed handoff."""


def classify_range_entry(entry: dict[str, Any]) -> str:
    """Classify one range entry from a source package.

    Order matters. A range is only ``UNAVAILABLE`` if it is *properly*
    unavailable: an entry claiming that state while carrying data is refused as
    ``FAILED`` rather than quietly accepted.
    """
    state = str(entry.get("data_state") or "").strip().lower()

    if state == "unavailable":
        if not str(entry.get("availability_reason") or "").strip():
            return FAILED
        if entry.get("metrics") or entry.get("rows"):
            return FAILED
        return UNAVAILABLE

    if state == "empty":
        return EMPTY

    if state in {"available", "partial"}:
        notes = " ".join(str(n) for n in (entry.get("quality_notes") or []))
        if any(marker in notes for marker in DEGRADED_MARKERS):
            return DEGRADED
        return FULL

    # Missing or unrecognized status is never assumed benign.
    return FAILED


def classify_source_package(payload: dict[str, Any]) -> str:
    """Classify a whole source package by its weakest range.

    A package is only eligible if every one of its ranges is. One degraded
    range degrades the package, because the handoff is all-or-nothing.
    """
    if not isinstance(payload, dict):
        return FAILED

    notes = " ".join(str(n) for n in (payload.get("quality_notes") or []))
    if any(marker in notes for marker in DEGRADED_MARKERS):
        return DEGRADED

    ranges = payload.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        return FAILED

    states = {classify_range_entry(entry) for entry in ranges if isinstance(entry, dict)}
    if len(states) != len([e for e in ranges if isinstance(e, dict)]) and not states:
        return FAILED
    if FAILED in states:
        return FAILED
    if DEGRADED in states:
        return DEGRADED
    if states <= {UNAVAILABLE}:
        # Every range unavailable means nothing was retrieved at all.
        return FAILED
    return FULL


def assert_handoff_eligible(
    packages: dict[str, dict[str, Any]],
    *,
    report_id: str = "",
    accepted_limitation_contract: str | None = None,
) -> dict[str, str]:
    """Refuse a handoff built from any ineligible source package.

    Returns the per-package classification on success. Raises
    :class:`DegradedSourceError` naming the report, the package, the state, and
    the missing coverage on refusal, so an operator can act without guessing.

    The guard lives here rather than in a CLI so a direct library caller cannot
    bypass it.
    """
    if accepted_limitation_contract is not None and (
        accepted_limitation_contract not in ACCEPTED_LIMITATION_CONTRACTS
    ):
        raise DegradedSourceError(
            f"accepted-limitation contract {accepted_limitation_contract!r} is not a "
            "recognized versioned contract. No handoff was written."
        )

    classifications: dict[str, str] = {}
    problems: list[str] = []

    for name, payload in (packages or {}).items():
        state = classify_source_package(payload)
        classifications[name] = state
        if state in INELIGIBLE_STATES:
            problems.append(f"{name} is {state}{_detail(payload)}")

    if problems:
        raise DegradedSourceError(
            f"handoff refused for report {report_id or 'unknown'}: "
            + "; ".join(problems)
            + ". A degraded or failed presentation-range source cannot support a "
            "completed handoff, and no versioned accepted-limitation contract "
            "authorizes one. No handoff was written and the source artifacts are "
            "unchanged."
        )

    return classifications


def _detail(payload: Any) -> str:
    """A short, non-secret reason naming the affected ranges."""
    if not isinstance(payload, dict):
        return ""
    ranges = payload.get("ranges")
    if not isinstance(ranges, list):
        return ""
    affected = [
        str(entry.get("range_key"))
        for entry in ranges
        if isinstance(entry, dict) and classify_range_entry(entry) in INELIGIBLE_STATES
    ]
    if not affected:
        return ""
    return " (ranges: " + ", ".join(sorted(affected)) + ")"
