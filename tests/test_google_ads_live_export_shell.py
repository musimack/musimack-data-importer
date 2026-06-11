import json

from src.dashboard_lab.paid_callrail_validators import validate_google_ads_summary
from src.providers.google_ads.client import GoogleAdsReadOnlyClient
from scripts.fetch_google_ads_api import _run_query_area
from src.providers.google_ads.client import GoogleAdsReadOnlyQueryError
from src.providers.google_ads.config import load_google_ads_local_config
from src.providers.google_ads.normalize import (
    normalize_campaign_rows,
    normalize_keyword_rows,
    normalize_search_term_rows,
    normalize_time_series,
)
from src.providers.google_ads.summary import build_google_ads_summary_payload, write_google_ads_summary


def test_live_client_layer_imports_without_network_calls():
    assert GoogleAdsReadOnlyClient.__name__ == "GoogleAdsReadOnlyClient"


def test_local_config_loads_ignored_style_json_without_exposing_values(tmp_path):
    client_secrets = tmp_path / "client-secrets.json"
    token_file = tmp_path / "token.json"
    client_secrets.write_text(
        json.dumps({"installed": {"client_id": "mock-client-id", "client_secret": "mock-client-secret"}}),
        encoding="utf-8",
    )
    token_file.write_text(json.dumps({"refresh_token": "mock-refresh-token"}), encoding="utf-8")

    config = load_google_ads_local_config(
        profile="inn-at-spanish-head",
        customer_id="1234567890",
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "mock-developer-token",
            "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": str(client_secrets),
            "GOOGLE_ADS_OAUTH_TOKEN_FILE": str(token_file),
        },
    )

    assert config.customer_id == "1234567890"
    assert config.login_customer_id is None
    assert "mock-client-secret" in config.to_google_ads_sdk_dict()["client_secret"]


def test_mocked_api_rows_build_valid_google_ads_summary(tmp_path):
    campaign_rows = normalize_campaign_rows(
        [
            {
                "campaign": {"name": "Brand"},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_500_000, "conversions": 2, "ctr": 0.1},
            }
        ]
    )
    keyword_rows = normalize_keyword_rows(
        [
            {
                "campaign": {"name": "Brand"},
                "ad_group_criterion": {"keyword": {"text": "spanish head", "match_type": "EXACT"}},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_500_000, "conversions": 2, "ctr": 0.1},
                "gclid": "must-not-output",
            }
        ]
    )
    search_term_rows = normalize_search_term_rows(
        [
            {
                "search_term_view": {"search_term": "spanish head hotel"},
                "campaign": {"name": "Brand"},
                "ad_group_criterion": {"keyword": {"text": "spanish head"}},
                "metrics": {"impressions": 50, "clicks": 5, "cost_micros": 1_000_000, "conversions": 1, "ctr": 0.1},
            }
        ]
    )
    time_series = normalize_time_series(
        [
            {
                "segments": {"date": "2026-01-01"},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_500_000, "conversions": 2},
            }
        ]
    )

    payload = build_google_ads_summary_payload(
        profile="inn-at-spanish-head",
        start_date="2026-01-01",
        end_date="2026-05-31",
        campaign_rows=campaign_rows,
        keyword_rows=keyword_rows,
        search_term_rows=search_term_rows,
        landing_page_rows=[],
        time_series=time_series,
        data_quality_notes=["Mocked read-only API response normalization."],
    )

    validate_google_ads_summary(payload)
    assert payload["schema_version"] == "google_ads_summary.v1"
    assert payload["client_label"] == "Spanish Head"
    assert payload["budget_pacing"] == {}
    assert any("Budget pacing deferred" in note for note in payload["data_quality_notes"])
    assert "gclid" not in json.dumps(payload).lower()

    output_path = tmp_path / "exports" / "local-real" / "dashboard-lab" / "inn-at-spanish-head" / "google-ads-summary.json"
    write_google_ads_summary(output_path, payload)
    validate_google_ads_summary(json.loads(output_path.read_text(encoding="utf-8")))


def test_query_area_wrapper_reports_area_without_query_or_customer_id():
    class MockClient:
        def run_gaql_query(self, customer_id, query):
            raise GoogleAdsReadOnlyQueryError("Google Ads API request failed; request_id=request-123; message=bad field")

    try:
        _run_query_area(MockClient(), "1234567890", "search term performance", "SELECT secret-ish query")
    except GoogleAdsReadOnlyQueryError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected query error")

    assert "search term performance" in message
    assert "request-123" in message
    assert "1234567890" not in message
    assert "SELECT secret-ish query" not in message
