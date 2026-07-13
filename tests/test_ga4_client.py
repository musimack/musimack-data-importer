from datetime import date

from src.config import DateRange
from src.ga4_client import (
    GA4_EXACT_RANGE_SUMMARY_METRICS,
    GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS,
    build_exact_range_summary_request,
    build_channel_breakdown_request,
    build_landing_pages_request,
    build_source_medium_request,
    build_top_pages_request,
    build_traffic_overview_request,
    sanitized_google_api_error,
)


class FakeResponse:
    status_code = 400

    def json(self):
        return {
            "error": {
                "code": 400,
                "message": "Invalid metric name.",
                "status": "INVALID_ARGUMENT",
                "details": [{"reason": "badRequest"}],
            }
        }


def test_traffic_overview_request_is_minimal_date_trend():
    request = build_traffic_overview_request(DateRange(date(2026, 4, 1), date(2026, 4, 30)))

    assert request["dimensions"] == [{"name": "date"}]
    assert request["metrics"] == [
        {"name": "activeUsers"},
        {"name": "sessions"},
        {"name": "screenPageViews"},
        {"name": "engagementRate"},
        {"name": "averageSessionDuration"},
        {"name": "eventCount"},
    ]


def test_exact_range_summary_request_is_dimensionless_summary_row():
    request = build_exact_range_summary_request(DateRange(date(2026, 7, 2), date(2026, 7, 8)))

    assert "dimensions" not in request
    assert request["metrics"] == [{"name": name} for name in GA4_EXACT_RANGE_SUMMARY_METRICS]
    assert {"name": "activeUsers"} in request["metrics"]
    assert {"name": "newUsers"} in request["metrics"]
    assert {"name": "engagedSessions"} in request["metrics"]
    assert {"name": "averageEngagementTime"} not in request["metrics"]
    assert {"name": "keyEvents"} in request["metrics"]
    assert request["dateRanges"] == [{"startDate": "2026-07-02", "endDate": "2026-07-08"}]
    assert request["limit"] == 1


def test_exact_range_summary_request_can_use_required_metric_fallback():
    request = build_exact_range_summary_request(
        DateRange(date(2026, 7, 2), date(2026, 7, 8)),
        metric_names=GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS,
    )

    assert request["metrics"] == [{"name": name} for name in GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS]
    assert "dimensions" not in request


def test_channel_breakdown_request_uses_safe_channel_dimensions():
    request = build_channel_breakdown_request(DateRange(date(2026, 4, 1), date(2026, 4, 30)))

    assert request["dimensions"] == [{"name": "sessionDefaultChannelGroup"}]
    assert {"name": "sessions"} in request["metrics"]
    assert {"name": "screenPageViews"} in request["metrics"]
    assert request["limit"] == 10


def test_top_pages_request_uses_safe_page_dimensions():
    request = build_top_pages_request(DateRange(date(2026, 4, 1), date(2026, 4, 30)))

    assert request["dimensions"] == [{"name": "pageTitle"}, {"name": "pagePath"}]
    assert {"name": "screenPageViews"} in request["metrics"]
    assert {"name": "activeUsers"} in request["metrics"]
    assert request["limit"] == 10


def test_source_medium_request_uses_true_source_medium_dimension():
    request = build_source_medium_request(DateRange(date(2026, 4, 1), date(2026, 4, 30)))

    assert request["dimensions"] == [{"name": "sessionSourceMedium"}]
    assert {"name": "sessions"} in request["metrics"]
    assert {"name": "activeUsers"} in request["metrics"]
    assert request["orderBys"] == [{"metric": {"metricName": "sessions"}, "desc": True}]
    assert request["limit"] == 10


def test_landing_pages_request_uses_landing_page_dimension():
    request = build_landing_pages_request(DateRange(date(2026, 4, 1), date(2026, 4, 30)))

    assert request["dimensions"] == [{"name": "landingPagePlusQueryString"}]
    assert {"name": "sessions"} in request["metrics"]
    assert {"name": "engagedSessions"} in request["metrics"]
    assert request["orderBys"] == [{"metric": {"metricName": "sessions"}, "desc": True}]
    assert request["limit"] == 10


def test_google_api_error_is_sanitized():
    message = sanitized_google_api_error(FakeResponse())

    assert "HTTP 400" in message
    assert "status=INVALID_ARGUMENT" in message
    assert "reason=badRequest" in message
    assert "message=Invalid metric name." in message
    assert "authorization" not in message.lower()
    assert "access_token" not in message.lower()
