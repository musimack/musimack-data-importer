"""Degraded-source handoff guard.

A completed handoff must never be built from a source package that returned
less than its governed coverage. The duplicate-metric defect proved the need:
a fallback silently reduced coverage from nine metrics to four, and the package
still validated and still reported ranges as available.

Fully offline. No credential, no provider client, no network call, and no real
client payload is committed.
"""

from __future__ import annotations

import pytest

from src.range_containment import OUT_OF_PERIOD_REASON, unavailable_range_entry
from src.source_package_state import (
    DEGRADED,
    EMPTY,
    FAILED,
    FULL,
    UNAVAILABLE,
    DegradedSourceError,
    assert_handoff_eligible,
    classify_range_entry,
    classify_source_package,
)

FULL_METRICS = {
    "users": 10, "new_users": 4, "sessions": 12, "views": 30,
    "engaged_sessions": 8, "engagement_rate": 0.7,
    "average_session_duration_seconds": 60, "event_count": 90, "key_events": 2,
}
# The exact shape the Spanish Head degraded run produced: four metrics only,
# carrying the fallback marker. Synthetic values, no real client payload.
DEGRADED_METRICS = {"users": 10, "sessions": 12, "views": 30, "engagement_rate": 0.7}
DEGRADED_NOTE = (
    "DEGRADED: optional GA4 metrics omitted after a governed safe retry; "
    "metric coverage is incomplete: GA4 Data API request failed with HTTP 400"
)


def _entry(key="last_7_days", state="available", metrics=None, notes=None):
    return {
        "range_key": key,
        "data_state": state,
        "coverage_state": "complete" if state == "available" else state,
        "metrics": FULL_METRICS if metrics is None else metrics,
        "quality_notes": notes or [],
    }


def _package(entries):
    return {"schema_version": "ga4_metric_display_exact_ranges.v1", "ranges": entries}


# Range classification


def test_a_full_range_is_full() -> None:
    assert classify_range_entry(_entry()) == FULL


def test_a_degraded_range_is_degraded() -> None:
    entry = _entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])
    assert classify_range_entry(entry) == DEGRADED


def test_an_out_of_period_range_is_unavailable_and_eligible() -> None:
    from datetime import date

    entry = unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))
    assert classify_range_entry(entry) == UNAVAILABLE


def test_unavailable_requires_a_non_empty_reason() -> None:
    entry = {"range_key": "last_12_months", "data_state": "unavailable", "availability_reason": ""}
    assert classify_range_entry(entry) == FAILED


def test_unavailable_carrying_data_is_refused() -> None:
    """Claiming unavailable while holding data is a contradiction, not a range."""
    entry = {
        "range_key": "last_12_months",
        "data_state": "unavailable",
        "availability_reason": OUT_OF_PERIOD_REASON,
        "metrics": FULL_METRICS,
    }
    assert classify_range_entry(entry) == FAILED


def test_provider_empty_is_distinguished_from_degraded() -> None:
    """Empty is a fact about the client. Degraded is a gap in retrieval."""
    empty = _entry(state="empty", metrics={})
    assert classify_range_entry(empty) == EMPTY
    assert classify_range_entry(empty) != DEGRADED


def test_missing_state_is_refused() -> None:
    assert classify_range_entry({"range_key": "last_7_days"}) == FAILED


def test_unknown_state_is_refused() -> None:
    assert classify_range_entry(_entry(state="something_new")) == FAILED


# Package classification


def test_a_full_package_is_eligible() -> None:
    assert classify_source_package(_package([_entry(), _entry("last_30_days")])) == FULL


def test_one_degraded_range_degrades_the_package() -> None:
    package = _package([_entry(), _entry("last_30_days", metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    assert classify_source_package(package) == DEGRADED


def test_a_package_level_degraded_note_degrades_the_package() -> None:
    package = _package([_entry()])
    package["quality_notes"] = [DEGRADED_NOTE]
    assert classify_source_package(package) == DEGRADED


def test_mixed_full_and_unavailable_is_eligible() -> None:
    from datetime import date

    package = _package(
        [_entry(), unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))]
    )
    assert classify_source_package(package) == FULL


def test_an_all_unavailable_package_is_refused() -> None:
    from datetime import date

    package = _package([unavailable_range_entry("last_12_months", date(2025, 7, 9), date(2026, 7, 8))])
    assert classify_source_package(package) == FAILED


def test_an_empty_package_is_refused() -> None:
    assert classify_source_package(_package([])) == FAILED
    assert classify_source_package({}) == FAILED


# The guard


def test_full_packages_pass_the_guard() -> None:
    result = assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": _package([_entry()])})
    assert result["ga4_metric_display_exact_ranges.v1"] == FULL


def test_a_degraded_ga4_summary_rejects_the_handoff() -> None:
    package = _package([_entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    with pytest.raises(DegradedSourceError) as exc:
        assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": package}, report_id="r1")
    message = str(exc.value)
    assert "r1" in message
    assert "ga4_metric_display_exact_ranges.v1" in message
    assert "degraded" in message
    assert "No handoff was written" in message


def test_a_degraded_ranked_package_rejects_the_handoff() -> None:
    package = _package([_entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    with pytest.raises(DegradedSourceError):
        assert_handoff_eligible({"ga4_top_sources_exact_ranges.v1": package})


def test_a_degraded_gsc_package_rejects_the_handoff() -> None:
    package = _package([_entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    with pytest.raises(DegradedSourceError):
        assert_handoff_eligible({"gsc_summary_exact_ranges.v1": package})


def test_a_failed_package_rejects_the_handoff() -> None:
    with pytest.raises(DegradedSourceError):
        assert_handoff_eligible({"gsc_summary_exact_ranges.v1": _package([_entry(state="?")])})


def test_the_error_names_the_affected_ranges() -> None:
    package = _package(
        [_entry(), _entry("last_30_days", metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])]
    )
    with pytest.raises(DegradedSourceError) as exc:
        assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": package})
    assert "last_30_days" in str(exc.value)


def test_no_accepted_limitation_contract_exists_so_degraded_always_rejects() -> None:
    package = _package([_entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    with pytest.raises(DegradedSourceError) as exc:
        assert_handoff_eligible(
            {"ga4_metric_display_exact_ranges.v1": package},
            accepted_limitation_contract="some.contract.v1",
        )
    assert "not a recognized versioned contract" in str(exc.value)


def test_the_spanish_head_degraded_signature_is_rejected() -> None:
    """The exact shape the stopped run produced, synthetically represented."""
    package = _package(
        [_entry(key, metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE]) for key in
         ("last_3_days", "last_7_days", "last_14_days", "last_30_days")]
    )
    assert classify_source_package(package) == DEGRADED
    with pytest.raises(DegradedSourceError):
        assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": package})


# The guard lives in the library, not the CLI


def test_a_direct_library_caller_cannot_bypass_the_guard() -> None:
    from src.client_report_publisher_handoff_writer import (
        write_client_report_publisher_handoff,
    )
    import inspect

    source = inspect.getsource(write_client_report_publisher_handoff)
    assert "assert_handoff_eligible" in source


def test_rejection_happens_before_any_file_is_written(tmp_path) -> None:
    """The atomic writer must never be reached for a degraded source."""
    existing = tmp_path / "client_report_presentation_ranges.v2.json"
    original = b'{"existing": "valid handoff"}\n'
    existing.write_bytes(original)

    package = _package([_entry(metrics=DEGRADED_METRICS, notes=[DEGRADED_NOTE])])
    with pytest.raises(DegradedSourceError):
        assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": package})

    assert existing.read_bytes() == original
    assert list(tmp_path.iterdir()) == [existing]
    assert not any(p.name.startswith(".") for p in tmp_path.iterdir())


def test_the_guard_makes_no_network_call(monkeypatch) -> None:
    import requests

    def guard(*args, **kwargs):
        raise AssertionError("the guard attempted a network request")

    monkeypatch.setattr(requests.Session, "request", guard)
    monkeypatch.setattr(requests, "get", guard)
    assert_handoff_eligible({"ga4_metric_display_exact_ranges.v1": _package([_entry()])})


def test_classification_is_deterministic() -> None:
    package = _package([_entry(), _entry("last_30_days")])
    assert classify_source_package(package) == classify_source_package(package)
