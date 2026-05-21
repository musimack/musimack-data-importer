from datetime import date

from src.config import DateRange
from src.ga4_client import (
    build_channel_breakdown_request,
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


def test_google_api_error_is_sanitized():
    message = sanitized_google_api_error(FakeResponse())

    assert "HTTP 400" in message
    assert "status=INVALID_ARGUMENT" in message
    assert "reason=badRequest" in message
    assert "message=Invalid metric name." in message
    assert "authorization" not in message.lower()
    assert "access_token" not in message.lower()
