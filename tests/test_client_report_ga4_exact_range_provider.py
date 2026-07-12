from __future__ import annotations

from datetime import date

import pytest

from src.client_report_ga4_exact_range_provider import build_ga4_exact_range_summary_from_provider
from src.client_report_ga4_exact_ranges import validate_ga4_exact_range_summary_contract
from src.config import DateRange
from src.ga4_client import GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS, Ga4ClientError


class FakeExactRangeClient:
    def __init__(self, *, fail_full: bool = False):
        self.fail_full = fail_full
        self.calls: list[tuple[DateRange, tuple[str, ...]]] = []

    def run_exact_range_summary(self, date_range: DateRange, *, metric_names: tuple[str, ...]):
        self.calls.append((date_range, metric_names))
        if self.fail_full and metric_names != GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS:
            raise Ga4ClientError("GA4 Data API request failed with HTTP 400; status=INVALID_ARGUMENT")
        return _response(metric_names)


def test_provider_builds_valid_exact_range_contract_with_four_required_ranges():
    client = FakeExactRangeClient()

    payload = build_ga4_exact_range_summary_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    validate_ga4_exact_range_summary_contract(payload)
    assert payload["dataset_version"] == "ga4_metric_display_exact_ranges.v1"
    assert payload["calculation_version"] == "ga4_summary_exact_ranges.provider.v1"
    assert [item["range_key"] for item in payload["ranges"]] == [
        "last_7_days",
        "last_30_days",
        "this_month",
        "last_month",
    ]
    assert payload["ranges"][0]["requested_start_date"] == "2026-07-02"
    assert payload["ranges"][0]["requested_end_date"] == "2026-07-08"
    assert payload["ranges"][3]["requested_start_date"] == "2026-06-01"
    assert payload["ranges"][3]["requested_end_date"] == "2026-06-30"
    assert payload["ranges"][0]["metrics"]["users"] == 101
    assert payload["ranges"][0]["metrics"]["engagement_rate"] == 0.642857
    assert "property" not in str(payload).lower()
    assert len(client.calls) == 4


def test_provider_retries_required_metrics_when_optional_metric_query_fails():
    client = FakeExactRangeClient(fail_full=True)

    payload = build_ga4_exact_range_summary_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    validate_ga4_exact_range_summary_contract(payload)
    assert len(client.calls) == 8
    assert all(call[1] == GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS for call in client.calls[1::2])
    assert "new_users" not in payload["ranges"][0]["metrics"]
    assert payload["ranges"][0]["metrics"]["users"] == 101
    assert payload["ranges"][0]["data_state"] == "available"


def test_provider_rejects_period_that_cannot_contain_required_ranges():
    with pytest.raises(ValueError, match="last_30_days must stay inside the report period"):
        build_ga4_exact_range_summary_from_provider(
            client=FakeExactRangeClient(),
            profile="aluma-seo-geo",
            report_period_start=date(2026, 7, 1),
            report_period_end=date(2026, 7, 8),
        )


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
