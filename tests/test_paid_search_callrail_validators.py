import pytest

from src.dashboard_lab.paid_callrail_validators import (
    DashboardLabFixtureValidationError,
    validate_callrail_summary,
    validate_google_ads_summary,
)


def test_valid_empty_google_ads_placeholder_passes():
    result = validate_google_ads_summary(_google_ads_placeholder())

    assert result.provider == "google_ads"
    assert result.profile == "inn-at-spanish-head"
    assert result.warnings == []


def test_invalid_google_ads_provider_fails():
    payload = _google_ads_placeholder()
    payload["provider"] = "google_ads_search"

    with pytest.raises(DashboardLabFixtureValidationError, match="provider must be google_ads"):
        validate_google_ads_summary(payload)


def test_google_ads_formatted_currency_string_fails():
    payload = _google_ads_placeholder()
    payload["summary"]["spend"] = "$1,234.56"

    with pytest.raises(DashboardLabFixtureValidationError, match="summary.spend must be numeric"):
        validate_google_ads_summary(payload)


def test_google_ads_formatted_ctr_string_fails():
    payload = _google_ads_placeholder()
    payload["keyword_rows"] = [{"keyword": "hotel", "impressions": 100, "clicks": 4, "ctr": "4.25%", "avg_cpc": 2.5, "cost": 10.0}]

    with pytest.raises(DashboardLabFixtureValidationError, match="keyword_rows\\[1\\].ctr must be numeric"):
        validate_google_ads_summary(payload)


def test_google_ads_formatted_integer_string_fails():
    payload = _google_ads_placeholder()
    payload["campaign_rows"] = [{"campaign": "Brand", "impressions": "1,234", "clicks": 12, "ctr": 0.01, "avg_cpc": 2.5, "spend": 30.0}]

    with pytest.raises(DashboardLabFixtureValidationError, match="campaign_rows\\[1\\].impressions must be numeric"):
        validate_google_ads_summary(payload)


def test_valid_empty_callrail_placeholder_passes():
    result = validate_callrail_summary(_callrail_placeholder())

    assert result.provider == "callrail"
    assert result.profile == "inn-at-spanish-head"
    assert result.warnings == []


def test_invalid_callrail_provider_fails():
    payload = _callrail_placeholder()
    payload["provider"] = "call_rail"

    with pytest.raises(DashboardLabFixtureValidationError, match="provider must be callrail"):
        validate_callrail_summary(payload)


def test_callrail_phone_number_key_fails():
    payload = _callrail_placeholder()
    payload["keyword_rows"] = [{"keyword": "hotel", "calls": 2, "phone_number": "503-555-0199"}]

    with pytest.raises(DashboardLabFixtureValidationError, match="phone_number"):
        validate_callrail_summary(payload)


def test_callrail_recording_url_key_fails():
    payload = _callrail_placeholder()
    payload["recording_url"] = "https://example.invalid/recording"

    with pytest.raises(DashboardLabFixtureValidationError, match="recording_url"):
        validate_callrail_summary(payload)


def test_callrail_tracking_number_row_with_phone_number_value_fails():
    payload = _callrail_placeholder()
    payload["tracking_number_rows"] = [
        {"tracking_number_label": "503-555-0199", "calls": 12},
    ]

    with pytest.raises(DashboardLabFixtureValidationError, match="phone-number-looking value"):
        validate_callrail_summary(payload)


def test_callrail_aggregate_tracking_number_label_passes():
    payload = _callrail_placeholder()
    payload["tracking_number_rows"] = [
        {"tracking_number_label": "Main paid search line", "source": "google_ads", "calls": 12},
    ]

    validate_callrail_summary(payload)


def test_forbidden_secret_key_fails_for_both_validators():
    google_ads = _google_ads_placeholder()
    google_ads["provider_metadata"] = {"api_key": "not-allowed"}
    callrail = _callrail_placeholder()
    callrail["provider_metadata"] = {"refresh_token": "not-allowed"}

    with pytest.raises(DashboardLabFixtureValidationError, match="api_key"):
        validate_google_ads_summary(google_ads)
    with pytest.raises(DashboardLabFixtureValidationError, match="refresh_token"):
        validate_callrail_summary(callrail)


def _google_ads_placeholder():
    return {
        "schema_version": "google_ads_summary.v1",
        "provider": "google_ads",
        "profile": "inn-at-spanish-head",
        "client_label": "Spanish Head",
        "source": "synthetic_demo",
        "is_real_data": False,
        "generated_at": "2026-06-10T00:00:00Z",
        "date_range": {"start_date": None, "end_date": None},
        "currency": "USD",
        "summary": {
            "spend": None,
            "clicks": None,
            "impressions": None,
            "ctr": None,
            "avg_cpc": None,
            "conversions": None,
            "cost_per_conversion": None,
            "calls": None,
            "cost_per_call": None,
        },
        "keyword_rows": [],
        "search_term_rows": [],
        "campaign_rows": [],
        "landing_page_rows": [],
        "paid_search_call_signal": {},
        "budget_pacing": {},
        "time_series": [],
        "data_quality_notes": [],
    }


def _callrail_placeholder():
    return {
        "schema_version": "callrail_summary.v1",
        "provider": "callrail",
        "profile": "inn-at-spanish-head",
        "client_label": "Spanish Head",
        "source": "synthetic_demo",
        "is_real_data": False,
        "generated_at": "2026-06-10T00:00:00Z",
        "date_range": {"start_date": None, "end_date": None},
        "summary": {
            "total_calls": None,
            "google_ads_calls": None,
            "first_time_callers": None,
            "answered_calls": None,
            "missed_calls": None,
            "avg_duration_seconds": None,
            "qualified_calls": None,
            "calls_with_keyword_attribution": None,
            "calls_without_keyword_attribution": None,
        },
        "paid_search_attribution": {},
        "keyword_rows": [],
        "campaign_rows": [],
        "landing_page_rows": [],
        "source_rows": [],
        "tracking_number_rows": [],
        "missed_call_opportunities": [],
        "time_series": [],
        "data_quality_notes": [],
    }
