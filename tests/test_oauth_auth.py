from __future__ import annotations

from pathlib import Path

from src.config import load_ga4_config
from src.ga4_client import GA4_DATA_API_SCOPE, load_oauth_credentials


class FakeCredentials:
    def __init__(self, valid=True, expired=False, refresh_token=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refreshed = False

    def refresh(self, _request):
        self.valid = True
        self.expired = False
        self.refreshed = True

    def to_json(self):
        return '{"token": "stored-by-google-auth"}'


class FakeFlow:
    launched = False

    def run_local_server(self, port=0):
        FakeFlow.launched = True
        return FakeCredentials(valid=True)


def test_oauth_is_default_auth_method(monkeypatch, tmp_path):
    token_file = tmp_path / "token.json"
    client_file = tmp_path / "client.json"
    monkeypatch.setenv("MUSIMACK_GA4_PROPERTY_ID", "123456789")
    monkeypatch.setenv("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", str(client_file))
    monkeypatch.setenv("MUSIMACK_GA4_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("MUSIMACK_GA4_AUTH_METHOD", raising=False)

    config = load_ga4_config()

    assert config.auth_method == "oauth"
    assert config.oauth_client_secrets_file == str(client_file)
    assert config.oauth_token_file == str(token_file)


def test_service_account_remains_optional_fallback(monkeypatch):
    monkeypatch.setenv("MUSIMACK_GA4_AUTH_METHOD", "service_account")
    monkeypatch.setenv("MUSIMACK_GA4_PROPERTY_ID", "123456789")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "C:\\fake\\service-account.json")
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", raising=False)
    monkeypatch.delenv("MUSIMACK_GA4_OAUTH_TOKEN_FILE", raising=False)

    config = load_ga4_config()

    assert config.auth_method == "service_account"
    assert config.service_account_file == "C:\\fake\\service-account.json"


def test_existing_valid_token_file_is_reused(monkeypatch, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    fake = FakeCredentials(valid=True)

    monkeypatch.setattr(
        "src.ga4_client.oauth_credentials.Credentials.from_authorized_user_file",
        lambda path, scopes: fake,
    )
    monkeypatch.setattr(
        "src.ga4_client.InstalledAppFlow.from_client_secrets_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("browser flow should not launch")),
    )

    credentials = load_oauth_credentials("client.json", str(token_file))

    assert credentials is fake
    assert not fake.refreshed


def test_expired_refreshable_token_is_refreshed_and_saved(monkeypatch, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("{}", encoding="utf-8")
    fake = FakeCredentials(valid=False, expired=True, refresh_token="refresh-value")

    monkeypatch.setattr(
        "src.ga4_client.oauth_credentials.Credentials.from_authorized_user_file",
        lambda path, scopes: fake,
    )

    credentials = load_oauth_credentials("client.json", str(token_file))

    assert credentials is fake
    assert fake.refreshed
    assert token_file.read_text(encoding="utf-8") == '{"token": "stored-by-google-auth"}'


def test_missing_token_file_launches_local_browser_flow(monkeypatch, tmp_path):
    FakeFlow.launched = False
    token_file = tmp_path / "token.json"
    seen = {}

    def fake_from_client_secrets_file(path, scopes):
        seen["path"] = path
        seen["scopes"] = scopes
        return FakeFlow()

    monkeypatch.setattr(
        "src.ga4_client.InstalledAppFlow.from_client_secrets_file",
        fake_from_client_secrets_file,
    )

    credentials = load_oauth_credentials("client.json", str(token_file))

    assert credentials.valid
    assert FakeFlow.launched
    assert seen == {"path": "client.json", "scopes": [GA4_DATA_API_SCOPE]}
    assert token_file.exists()
