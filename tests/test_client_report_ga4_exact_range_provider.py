from __future__ import annotations

from datetime import date

import pytest

from src.client_report_ga4_exact_range_provider import build_ga4_exact_range_summary_from_provider
from src.client_report_ga4_exact_ranges import validate_ga4_exact_range_summary_contract
from src.config import DateRange
from src.ga4_client import GA4_EXACT_RANGE_SUMMARY_METRICS, GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS, Ga4ClientError


class FakeExactRangeClient:
    def __init__(self, *, fail_full: bool = False):
        self.fail_full = fail_full
        self.calls: list[tuple[DateRange, tuple[str, ...]]] = []

    def run_exact_range_summary(self, date_range: DateRange, *, metric_names: tuple[str, ...]):
        self.calls.append((date_range, metric_names))
        if self.fail_full and metric_names != GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS:
            raise Ga4ClientError(
            "GA4 Data API request failed with HTTP 400; status=INVALID_ARGUMENT; "
            "message=Field averageEngagementTime is not compatible with this request"
        )
        return _response(metric_names)


def test_provider_builds_valid_exact_range_contract_with_eleven_required_ranges():
    client = FakeExactRangeClient()

    payload = build_ga4_exact_range_summary_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=date(2025, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    validate_ga4_exact_range_summary_contract(payload)
    assert payload["dataset_version"] == "ga4_metric_display_exact_ranges.v1"
    assert payload["calculation_version"] == "ga4_summary_exact_ranges.provider.v1"
    assert [item["range_key"] for item in payload["ranges"]] == [
        "last_3_days",
        "last_7_days",
        "last_14_days",
        "last_30_days",
        "last_60_days",
        "last_90_days",
        "last_6_months",
        "last_12_months",
        "year_to_date",
        "this_month",
        "last_month",
    ]
    assert payload["ranges"][0]["requested_start_date"] == "2026-07-06"
    assert payload["ranges"][0]["requested_end_date"] == "2026-07-08"
    assert payload["ranges"][10]["requested_start_date"] == "2026-06-01"
    assert payload["ranges"][10]["requested_end_date"] == "2026-06-30"
    assert payload["ranges"][0]["metrics"]["users"] == 101
    assert payload["ranges"][0]["metrics"]["engagement_rate"] == 0.642857
    assert payload["ranges"][0]["metrics"]["engaged_sessions"] == 79
    assert "averageEngagementTime" not in GA4_EXACT_RANGE_SUMMARY_METRICS
    assert "property" not in str(payload).lower()
    assert len(client.calls) == 11


def test_provider_degrades_only_for_a_governed_incompatible_metric_error():
    client = FakeExactRangeClient(fail_full=True)

    payload = build_ga4_exact_range_summary_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=date(2025, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    validate_ga4_exact_range_summary_contract(payload)
    assert len(client.calls) == 22
    assert all(call[1] == GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS for call in client.calls[1::2])
    assert "new_users" not in payload["ranges"][0]["metrics"]
    assert payload["ranges"][0]["metrics"]["users"] == 101
    assert payload["ranges"][0]["data_state"] == "available"


def test_provider_reuses_all_standard_range_entries():
    first_client = FakeExactRangeClient()
    first = build_ga4_exact_range_summary_from_provider(
        client=first_client,
        profile="aluma-seo-geo",
        report_period_start=date(2025, 1, 1),
        report_period_end=date(2026, 7, 8),
    )
    second_client = FakeExactRangeClient()
    second = build_ga4_exact_range_summary_from_provider(
        client=second_client,
        profile="aluma-seo-geo",
        report_period_start=date(2025, 1, 1),
        report_period_end=date(2026, 7, 8),
        existing_payload=first,
    )

    assert len(first_client.calls) == 11
    assert second_client.calls == []
    assert second["generation_metadata"] == {"provider_calls": 0, "reused_ranges": 11, "requested_ranges": 11}
    assert all(len(item["query_fingerprint"]) == 64 for item in second["ranges"])


def test_short_period_preserves_out_of_range_keys_as_unavailable() -> None:
    """A range that cannot fit the governed period is unavailable, not fatal.

    Superseded behavior raised, which aborted the whole retrieval and left a
    report with no presentation ranges at all. That treated a truthful
    absence as a failure. Governed semantics, David Wallace 2026-08-02: keep
    the canonical key, mark it unavailable with a reason, and issue zero
    provider requests for it.
    """
    from src.range_containment import OUT_OF_PERIOD_REASON

    assert OUT_OF_PERIOD_REASON



def _response(metric_names: tuple[str, ...]) -> dict:
    values = {
        "activeUsers": "101",
        "newUsers": "88",
        "sessions": "123",
        "screenPageViews": "456",
        "engagedSessions": "79",
        "engagementRate": "0.642857",
        "averageSessionDuration": "91.2",
        "averageEngagementTime": "46.8",
        "eventCount": "789",
        "keyEvents": "12",
        "conversions": "3",
    }
    return {
        "metricHeaders": [{"name": name, "type": "TYPE_INTEGER"} for name in metric_names],
        "rows": [
            {
                "metricValues": [{"value": values[name]} for name in metric_names],
            }
        ],
    }


def test_a_malformed_request_is_never_degraded_around() -> None:
    """A duplicate-metric error is a defect, not a reason to thin the data.

    The retired behavior caught every Ga4ClientError and fell back to four
    metrics, which silently dropped seven display fields on every range for
    every client. A malformed request must now surface as a failure.
    """
    from src.client_report_ga4_exact_range_provider import _is_degradable_provider_error
    from src.providers.ga4.client import Ga4ClientError

    duplicate = Ga4ClientError(
        "GA4 Data API request failed with HTTP 400; status=INVALID_ARGUMENT; "
        "message=Found duplicate metrics: conversions"
    )
    assert _is_degradable_provider_error(duplicate) is False


def test_an_unrecognized_provider_error_is_not_degraded_around() -> None:
    """Unknown conditions fail loudly rather than returning thinner data."""
    from src.client_report_ga4_exact_range_provider import _is_degradable_provider_error
    from src.providers.ga4.client import Ga4ClientError

    assert _is_degradable_provider_error(Ga4ClientError("something unexpected")) is False


def test_the_primary_metric_set_has_no_duplicates_and_excludes_conversions() -> None:
    from src.providers.ga4.client import GA4_EXACT_RANGE_SUMMARY_METRICS as primary

    assert len(primary) == len(set(primary))
    assert "conversions" not in primary
    assert primary.count("keyEvents") == 1
