import json
from pathlib import Path

import pytest

from scripts.fetch_gsc_api import resolve_output_dir
from src.config import ConfigError
from src.providers.gsc.client import GSC_READONLY_SCOPE, GscFetchConfig, GscSearchConsoleClient
from src.providers.gsc.summary import (
    GscSummaryError,
    build_gsc_summary,
    real_output_dir,
    validate_aluma_combined_summary,
    validate_gsc_output_dir,
    write_gsc_dashboard_outputs,
)


class _FakeCredentials:
    token = "fake-token"
    valid = True
    expired = False
    refresh_token = None


class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "rows": [
                {
                    "keys": ["botox portland", "https://alumapdx.com/botox-portland", "2026-01-01"],
                    "clicks": 10,
                    "impressions": 100,
                    "ctr": 0.1,
                    "position": 4.2,
                }
            ]
        }


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse()


def _sample_gsc_response():
    return {
        "rows": [
            {
                "keys": ["botox portland", "https://alumapdx.com/botox-portland", "2026-01-01"],
                "clicks": 10,
                "impressions": 100,
                "ctr": 0.1,
                "position": 4.0,
            },
            {
                "keys": ["botox portland", "https://alumapdx.com/botox-portland", "2026-01-02"],
                "clicks": 12,
                "impressions": 120,
                "ctr": 0.1,
                "position": 5.0,
            },
            {
                "keys": ["lip filler portland", "https://alumapdx.com/lip-filler", "2026-01-01"],
                "clicks": 5,
                "impressions": 50,
                "ctr": 0.1,
                "position": 7.0,
            },
        ]
    }


def test_gsc_client_uses_readonly_scope_and_query_page_date_request(monkeypatch):
    captured = {}

    def fake_load(client_secrets_file, token_file):
        captured["client_secrets_file"] = client_secrets_file
        captured["token_file"] = token_file
        return _FakeCredentials()

    monkeypatch.setattr("src.providers.gsc.client.load_gsc_oauth_credentials", fake_load)
    session = _FakeSession()
    client = GscSearchConsoleClient(
        GscFetchConfig(
            client_secrets_file="client.json",
            token_file="gsc-token.json",
            site_url="https://alumapdx.com/",
            row_limit=500,
        ),
        session=session,
    )

    response = client.query_search_analytics("2026-01-01", "2026-05-19")

    assert response["rows"]
    assert captured == {"client_secrets_file": "client.json", "token_file": "gsc-token.json"}
    assert GSC_READONLY_SCOPE == "https://www.googleapis.com/auth/webmasters.readonly"
    call = session.calls[0]
    assert call["json"]["dimensions"] == ["query", "page", "date"]
    assert call["json"]["rowLimit"] == 500
    assert call["json"]["startDate"] == "2026-01-01"
    assert call["json"]["endDate"] == "2026-05-19"
    assert call["headers"]["Authorization"] == "Bearer fake-token"


def test_build_gsc_summary_aggregates_rows_without_secret_fields():
    payload = build_gsc_summary(
        "aluma-seo-geo",
        "https://alumapdx.com/",
        "2026-01-01",
        "2026-01-02",
        _sample_gsc_response(),
    )

    assert payload["schema_version"] == "dashboard_lab_provider_summary.v1"
    assert payload["provider"] == "gsc"
    assert payload["source_mode"] == "local_gsc_api"
    assert payload["local_only"] is True
    assert payload["mock_data"] is False
    assert payload["summary_metrics"] == {
        "clicks": 27,
        "impressions": 270,
        "ctr": 0.1,
        "average_position": 5.0,
    }
    assert payload["top_queries"][0]["query"] == "botox portland"
    assert payload["top_pages"][0]["path"] == "/botox-portland"
    serialized = json.dumps(payload).lower()
    assert "client_secret" not in serialized
    assert "refresh_token" not in serialized
    assert "gsc-token" not in serialized


def test_write_and_validate_aluma_gsc_outputs(tmp_path):
    summary = build_gsc_summary(
        "aluma-seo-geo",
        "https://alumapdx.com/",
        "2026-01-01",
        "2026-01-02",
        _sample_gsc_response(),
    )

    files = write_gsc_dashboard_outputs(tmp_path, summary)
    validated = validate_gsc_output_dir(tmp_path, "aluma-seo-geo")

    assert [path.name for path in files] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
    ]
    assert [path.name for path in validated] == [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
    ]
    combined = json.loads((tmp_path / "combined-dashboard-summary.json").read_text(encoding="utf-8"))
    assert combined["provider_summaries"] == {
        "ga4": "ga4-summary.json",
        "gsc": "gsc-summary.json",
    }
    assert "paid_search" not in combined["modules_enabled"]
    assert "lsa_performance" not in combined["modules_enabled"]
    assert "call_tracking" not in combined["modules_enabled"]
    assert (tmp_path / "client-profile.json").exists()
    assert (tmp_path / "ga4-summary.json").exists()


def test_gsc_validation_rejects_credential_paths(tmp_path):
    summary = build_gsc_summary(
        "aluma-seo-geo",
        "https://alumapdx.com/",
        "2026-01-01",
        "2026-01-02",
        _sample_gsc_response(),
    )
    write_gsc_dashboard_outputs(tmp_path, summary)
    payload = json.loads((tmp_path / "gsc-summary.json").read_text(encoding="utf-8"))
    payload["credential_path"] = "secrets/gsc_token.local.json"
    (tmp_path / "gsc-summary.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GscSummaryError, match="secret-like key"):
        validate_gsc_output_dir(tmp_path, "aluma-seo-geo")


def test_real_output_path_resolution_and_explicit_out_override(tmp_path):
    explicit = tmp_path / "custom-output"

    assert resolve_output_dir("aluma-seo-geo", None, True) == real_output_dir("aluma-seo-geo")
    assert resolve_output_dir("aluma-seo-geo", str(explicit), True) == explicit
    assert resolve_output_dir("aluma-seo-geo", str(explicit), False) == explicit

    with pytest.raises(ConfigError, match="--out is required"):
        resolve_output_dir("aluma-seo-geo", None, False)


def test_validate_real_output_folder_requires_complete_profile_files(tmp_path):
    summary = build_gsc_summary(
        "aluma-seo-geo",
        "https://alumapdx.com/",
        "2026-01-01",
        "2026-01-02",
        _sample_gsc_response(),
    )
    write_gsc_dashboard_outputs(tmp_path, summary)
    (tmp_path / "ga4-summary.json").unlink()

    with pytest.raises(GscSummaryError, match="support files"):
        validate_gsc_output_dir(tmp_path, "aluma-seo-geo")


def test_aluma_combined_validation_rejects_ads_modules():
    payload = {
        "fixture_profile": "aluma-seo-geo",
        "provider_summaries": {
            "ga4": "ga4-summary.json",
            "gsc": "gsc-summary.json",
            "google_ads_search": "google-ads-search-summary.json",
        },
        "modules_enabled": ["executive_summary", "paid_search"],
        "local_only": True,
    }

    with pytest.raises(GscSummaryError, match="only GA4 and GSC"):
        validate_aluma_combined_summary(payload, "aluma-seo-geo")
