from datetime import date

import pytest

from src.config import ConfigError, DateRange, load_ga4_config
from src.normalize import normalize_traffic_overview
from src.snapshot_builder import build_traffic_overview_snapshot
from tests.test_normalize import mocked_ga4_response


FORBIDDEN = [
    "access_token",
    "refresh_token",
    "private_key",
    "authorization",
    "client_secret",
]


def test_snapshot_output_does_not_include_secret_terms():
    payload = build_traffic_overview_snapshot(
        normalize_traffic_overview(mocked_ga4_response()),
        "properties/123456789",
        DateRange(date(2026, 4, 1), date(2026, 4, 30)),
    )
    text = str(payload).lower()

    for forbidden in FORBIDDEN:
        assert forbidden not in text


def test_missing_env_vars_fail_safely_without_secret_output(monkeypatch, capsys):
    monkeypatch.delenv("MUSIMACK_GA4_PROPERTY_ID", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_AUTH_METHOD", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_TOKEN_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_SERVICE_ACCOUNT_JSON", raising=False)

    with pytest.raises(ConfigError):
        load_ga4_config()

    captured = capsys.readouterr()
    output = (captured.out + captured.err).lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in output
