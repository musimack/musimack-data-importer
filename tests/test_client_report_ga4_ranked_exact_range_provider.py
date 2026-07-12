from __future__ import annotations

from datetime import date

import pytest

from src.client_report_ga4_ranked_exact_range_provider import (
    build_all_ga4_ranked_exact_ranges_from_provider,
    build_ga4_ranked_exact_range_from_provider,
)
from src.client_report_ga4_ranked_exact_ranges import (
    RANKED_EXACT_RANGE_SOURCE_BY_SECTION,
    validate_ga4_ranked_exact_range_contract,
)
from src.config import DateRange
from src.ga4_client import Ga4ClientError


class FakeRankedClient:
    def __init__(self, *, mode: str = "ok"):
        self.mode = mode
        self.calls: list[tuple[str, DateRange]] = []

    def run_exact_range_channel_performance(self, date_range: DateRange) -> dict:
        self.calls.append(("channel", date_range))
        return _channel_response() if self.mode != "empty" else _empty_response(["sessionDefaultChannelGroup"], ["sessions"])

    def run_exact_range_top_sources(self, date_range: DateRange) -> dict:
        self.calls.append(("sources", date_range))
        if self.mode == "permission":
            raise Ga4ClientError("GA4 Data API request failed with HTTP 403; status=PERMISSION_DENIED")
        if self.mode == "duplicate":
            return _source_response(duplicate=True)
        if self.mode == "malformed":
            return _source_response(malformed=True)
        return _source_response()

    def run_exact_range_top_landing_pages(self, date_range: DateRange) -> dict:
        self.calls.append(("landing", date_range))
        return _landing_response()

    def run_exact_range_most_viewed_pages(self, date_range: DateRange) -> dict:
        self.calls.append(("pages", date_range))
        return _page_response()


def test_provider_builds_four_ranked_contracts_with_four_ranges_each():
    client = FakeRankedClient()

    payloads = build_all_ga4_ranked_exact_ranges_from_provider(
        client=client,
        profile="aluma-seo-geo",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    assert set(payloads) == set(RANKED_EXACT_RANGE_SOURCE_BY_SECTION.values())
    assert len(client.calls) == 16
    assert [name for name, _ in client.calls[:4]] == ["channel", "channel", "channel", "channel"]
    for payload in payloads.values():
        validate_ga4_ranked_exact_range_contract(payload)
        assert payload["calculation_version"] == "ga4_ranked_exact_ranges.provider.v1"
        assert "synthetic" not in payload["calculation_version"]
        assert "property" not in str(payload).lower()
        assert [item["range_key"] for item in payload["ranges"]] == [
            "last_7_days",
            "last_30_days",
            "this_month",
            "last_month",
        ]
        assert all(item["data_state"] == "available" for item in payload["ranges"])
        assert all(item["requested_start_date"] <= item["requested_end_date"] for item in payload["ranges"])
        assert payload["query_identity"]["fingerprint"]


def test_provider_uses_correct_exact_dates_and_section_specific_rows():
    client = FakeRankedClient()

    payload = build_ga4_ranked_exact_range_from_provider(
        client=client,
        profile="aluma-seo-geo",
        section_key="ga4_top_sources",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 7, 8),
        generated_at="2026-07-09T12:00:00Z",
    )

    first = payload["ranges"][0]
    assert first["requested_start_date"] == "2026-07-02"
    assert first["requested_end_date"] == "2026-07-08"
    assert first["rows"][0]["source"] == "google"
    assert first["rows"][0]["medium"] == "organic"
    assert first["rows"][0]["metrics"]["sessions"] == 20
    assert first["rows"][1]["metrics"]["sessions"] == 10
    assert payload["query_identity"]["provider_dimension"] == "sessionSourceMedium"


def test_provider_empty_result_becomes_empty_not_unavailable():
    payload = build_ga4_ranked_exact_range_from_provider(
        client=FakeRankedClient(mode="empty"),
        profile="aluma-seo-geo",
        section_key="ga4_channel_performance",
        report_period_start=date(2026, 1, 1),
        report_period_end=date(2026, 7, 8),
    )

    assert all(item["data_state"] == "empty" for item in payload["ranges"])
    validate_ga4_ranked_exact_range_contract(payload)


def test_provider_permission_failure_is_not_reported_as_empty():
    with pytest.raises(Ga4ClientError, match="PERMISSION_DENIED"):
        build_ga4_ranked_exact_range_from_provider(
            client=FakeRankedClient(mode="permission"),
            profile="aluma-seo-geo",
            section_key="ga4_top_sources",
            report_period_start=date(2026, 1, 1),
            report_period_end=date(2026, 7, 8),
        )


def test_provider_malformed_and_duplicate_rows_fail_contract_validation():
    with pytest.raises(ValueError, match="not numeric"):
        build_ga4_ranked_exact_range_from_provider(
            client=FakeRankedClient(mode="malformed"),
            profile="aluma-seo-geo",
            section_key="ga4_top_sources",
            report_period_start=date(2026, 1, 1),
            report_period_end=date(2026, 7, 8),
        )
    with pytest.raises(ValueError, match="duplicate dimension identity"):
        build_ga4_ranked_exact_range_from_provider(
            client=FakeRankedClient(mode="duplicate"),
            profile="aluma-seo-geo",
            section_key="ga4_top_sources",
            report_period_start=date(2026, 1, 1),
            report_period_end=date(2026, 7, 8),
        )


def test_provider_rejects_period_that_cannot_contain_required_ranges():
    with pytest.raises(ValueError, match="last_30_days must stay inside the report period"):
        build_ga4_ranked_exact_range_from_provider(
            client=FakeRankedClient(),
            profile="aluma-seo-geo",
            section_key="ga4_top_sources",
            report_period_start=date(2026, 7, 1),
            report_period_end=date(2026, 7, 8),
        )


def _empty_response(dimensions: list[str], metrics: list[str]) -> dict:
    return {
        "dimensionHeaders": [{"name": item} for item in dimensions],
        "metricHeaders": [{"name": item} for item in metrics],
        "rows": [],
    }


def _channel_response() -> dict:
    return {
        "dimensionHeaders": [{"name": "sessionDefaultChannelGroup"}],
        "metricHeaders": [{"name": "activeUsers"}, {"name": "sessions"}, {"name": "engagementRate"}],
        "rows": [
            {"dimensionValues": [{"value": "Organic Search"}], "metricValues": [{"value": "9"}, {"value": "11"}, {"value": "0.7"}]},
            {"dimensionValues": [{"value": "Direct"}], "metricValues": [{"value": "6"}, {"value": "9"}, {"value": "0.58"}]},
        ],
    }


def _source_response(*, duplicate: bool = False, malformed: bool = False) -> dict:
    rows = [
        {"dimensionValues": [{"value": "google / organic"}], "metricValues": [{"value": "20"}, {"value": "18"}, {"value": "0.7"}]},
        {"dimensionValues": [{"value": "newsletter / email" if not duplicate else "google / organic"}], "metricValues": [{"value": "10" if not malformed else "oops"}, {"value": "9"}, {"value": "0.5"}]},
    ]
    return {
        "dimensionHeaders": [{"name": "sessionSourceMedium"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}, {"name": "engagementRate"}],
        "rows": rows,
    }


def _landing_response() -> dict:
    return {
        "dimensionHeaders": [{"name": "landingPagePlusQueryString"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}, {"name": "engagedSessions"}],
        "rows": [
            {"dimensionValues": [{"value": "/"}], "metricValues": [{"value": "21"}, {"value": "16"}, {"value": "12"}]},
            {"dimensionValues": [{"value": "/contact/"}], "metricValues": [{"value": "9"}, {"value": "7"}, {"value": "4"}]},
        ],
    }


def _page_response() -> dict:
    return {
        "dimensionHeaders": [{"name": "pageTitle"}, {"name": "pagePath"}],
        "metricHeaders": [{"name": "screenPageViews"}, {"name": "activeUsers"}, {"name": "eventCount"}],
        "rows": [
            {"dimensionValues": [{"value": "Home"}, {"value": "/"}], "metricValues": [{"value": "50"}, {"value": "20"}, {"value": "8"}]},
            {"dimensionValues": [{"value": "Services"}, {"value": "/services/"}], "metricValues": [{"value": "30"}, {"value": "14"}, {"value": "5"}]},
        ],
    }
