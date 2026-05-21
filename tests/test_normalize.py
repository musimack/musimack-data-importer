from src.normalize import normalize_traffic_overview


def mocked_ga4_response():
    return {
        "dimensionHeaders": [
            {"name": "date"},
        ],
        "metricHeaders": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "eventCount"},
        ],
        "rows": [
            {
                "dimensionValues": [{"value": "20260401"}],
                "metricValues": [
                    {"value": "10"},
                    {"value": "12"},
                    {"value": "40"},
                    {"value": "0.75"},
                    {"value": "90"},
                    {"value": "30"},
                ],
            },
            {
                "dimensionValues": [{"value": "20260402"}],
                "metricValues": [
                    {"value": "5"},
                    {"value": "8"},
                    {"value": "12"},
                    {"value": "0.5"},
                    {"value": "30"},
                    {"value": "10"},
                ],
            },
        ],
    }


def mocked_richer_ga4_response():
    return {
        "traffic_overview": mocked_ga4_response(),
        "channel_breakdown": {
            "dimensionHeaders": [{"name": "sessionDefaultChannelGroup"}],
            "metricHeaders": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"},
                {"name": "engagementRate"},
                {"name": "averageSessionDuration"},
                {"name": "eventCount"},
            ],
            "rows": [
                {
                    "dimensionValues": [{"value": "Organic Search"}],
                    "metricValues": [
                        {"value": "9"},
                        {"value": "11"},
                        {"value": "32"},
                        {"value": "0.7"},
                        {"value": "80"},
                        {"value": "24"},
                    ],
                },
                {
                    "dimensionValues": [{"value": "Direct"}],
                    "metricValues": [
                        {"value": "6"},
                        {"value": "9"},
                        {"value": "20"},
                        {"value": "0.58"},
                        {"value": "48"},
                        {"value": "16"},
                    ],
                },
            ],
        },
        "top_pages": {
            "dimensionHeaders": [{"name": "pageTitle"}, {"name": "pagePath"}],
            "metricHeaders": [
                {"name": "screenPageViews"},
                {"name": "activeUsers"},
                {"name": "eventCount"},
                {"name": "averageSessionDuration"},
            ],
            "rows": [
                {
                    "dimensionValues": [{"value": "Home"}, {"value": "/"}],
                    "metricValues": [
                        {"value": "41"},
                        {"value": "12"},
                        {"value": "25"},
                        {"value": "75"},
                    ],
                },
                {
                    "dimensionValues": [{"value": "Services"}, {"value": "/services"}],
                    "metricValues": [
                        {"value": "11"},
                        {"value": "7"},
                        {"value": "15"},
                        {"value": "62"},
                    ],
                },
            ],
        },
    }


def test_mocked_ga4_response_normalizes_to_supported_metrics():
    normalized = normalize_traffic_overview(mocked_ga4_response())
    metrics = {metric.name: metric.value for metric in normalized.metrics}

    assert metrics["users"] == 15
    assert metrics["sessions"] == 20
    assert metrics["engagement_rate"] == 0.65
    assert metrics["average_session_duration_seconds"] == 66
    assert metrics["views"] == 52
    assert metrics["event_count"] == 40
    assert normalized.time_series[0]["date"] == "2026-04-01"
    assert normalized.channel_rows == []


def test_bad_numeric_values_are_sanitized_to_zero():
    response = mocked_ga4_response()
    response["rows"][0]["metricValues"][0]["value"] = "not-a-number"

    normalized = normalize_traffic_overview(response)
    metrics = {metric.name: metric.value for metric in normalized.metrics}

    assert metrics["users"] == 5


def test_richer_ga4_response_normalizes_channel_and_top_page_rows():
    normalized = normalize_traffic_overview(mocked_richer_ga4_response())

    assert normalized.channel_rows[0].kind == "traffic_channels"
    assert normalized.channel_rows[0].label == "Organic Search"
    assert {metric.name for metric in normalized.channel_rows[0].metrics}.issuperset(
        {"sessions", "users", "views", "engagement_rate"}
    )
    assert normalized.top_page_rows[0].kind == "top_pages"
    assert normalized.top_page_rows[0].label == "Home (/)"
    assert {metric.name for metric in normalized.top_page_rows[0].metrics}.issuperset(
        {"views", "users", "event_count", "average_session_duration_seconds"}
    )
