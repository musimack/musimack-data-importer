import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.generate_google_ads_oauth_token as token_helper
from scripts.generate_google_ads_oauth_token import (
    DEFAULT_CLIENT_SECRETS,
    DEFAULT_TOKEN_OUTPUT,
    GOOGLE_ADS_SCOPE,
    GoogleAdsOAuthTokenError,
    generate_google_ads_oauth_token,
)
from src.providers.google_ads.config import load_google_ads_local_config


def test_default_paths_point_to_ignored_google_ads_secret_locations():
    assert DEFAULT_CLIENT_SECRETS.as_posix() == "secrets/google-ads/client_secrets.local.json"
    assert DEFAULT_TOKEN_OUTPUT.as_posix() == "secrets/google-ads/oauth_token.local.json"


def test_missing_client_secrets_file_fails_safely(tmp_path):
    with pytest.raises(GoogleAdsOAuthTokenError, match="client secrets file is missing"):
        generate_google_ads_oauth_token(
            client_secrets_path=tmp_path / "missing.json",
            token_output_path=tmp_path / "oauth_token.local.json",
        )


def test_existing_token_refuses_overwrite_before_browser_flow(tmp_path, monkeypatch):
    client_secrets = _write_client_secrets(tmp_path)
    token_output = tmp_path / "oauth_token.local.json"
    token_output.write_text(json.dumps({"refresh_token": "existing-refresh-token"}), encoding="utf-8")

    def fail_if_called(_path):
        raise AssertionError("browser flow should not run")

    monkeypatch.setattr(token_helper, "_run_local_browser_flow", fail_if_called)

    with pytest.raises(GoogleAdsOAuthTokenError, match="already exists"):
        generate_google_ads_oauth_token(client_secrets_path=client_secrets, token_output_path=token_output)


def test_helper_writes_mocked_token_data_without_printing_token_values(tmp_path, monkeypatch, capsys):
    client_secrets = _write_client_secrets(tmp_path)
    token_output = tmp_path / "oauth_token.local.json"

    class MockCredentials:
        refresh_token = "mock-refresh-token"
        token_uri = "https://oauth2.googleapis.com/token"

    monkeypatch.setattr(token_helper, "_run_local_browser_flow", lambda _path: MockCredentials())

    generate_google_ads_oauth_token(client_secrets_path=client_secrets, token_output_path=token_output)
    captured = capsys.readouterr()

    assert token_output.exists()
    payload = json.loads(token_output.read_text(encoding="utf-8"))
    assert payload["refresh_token"] == "mock-refresh-token"
    assert payload["scopes"] == [GOOGLE_ADS_SCOPE]
    assert "mock-refresh-token" not in captured.out + captured.err
    assert "client_secret" not in captured.out + captured.err


def test_helper_overwrite_replaces_existing_token_with_mocked_data(tmp_path, monkeypatch):
    client_secrets = _write_client_secrets(tmp_path)
    token_output = tmp_path / "oauth_token.local.json"
    token_output.write_text(json.dumps({"refresh_token": "old-refresh-token"}), encoding="utf-8")

    class MockCredentials:
        refresh_token = "new-refresh-token"
        token_uri = ""

    monkeypatch.setattr(token_helper, "_run_local_browser_flow", lambda _path: MockCredentials())

    generate_google_ads_oauth_token(client_secrets_path=client_secrets, token_output_path=token_output, overwrite=True)

    assert json.loads(token_output.read_text(encoding="utf-8"))["refresh_token"] == "new-refresh-token"


def test_generated_token_file_is_compatible_with_google_ads_config_loader(tmp_path, monkeypatch):
    client_secrets = _write_client_secrets(tmp_path)
    token_output = tmp_path / "oauth_token.local.json"

    class MockCredentials:
        refresh_token = "mock-refresh-token"
        token_uri = ""

    monkeypatch.setattr(token_helper, "_run_local_browser_flow", lambda _path: MockCredentials())
    generate_google_ads_oauth_token(client_secrets_path=client_secrets, token_output_path=token_output)

    config = load_google_ads_local_config(
        profile="inn-at-spanish-head",
        customer_id="1234567890",
        environ={
            "GOOGLE_ADS_DEVELOPER_TOKEN": "mock-developer-token",
            "GOOGLE_ADS_OAUTH_CLIENT_SECRETS": str(client_secrets),
            "GOOGLE_ADS_OAUTH_TOKEN_FILE": str(token_output),
        },
    )

    assert config.customer_id == "1234567890"
    assert config.to_google_ads_sdk_dict()["refresh_token"] == "mock-refresh-token"


def test_cli_missing_client_secrets_does_not_print_token_values(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path.cwd() / "scripts" / "generate_google_ads_oauth_token.py"),
            "--client-secrets",
            str(tmp_path / "missing.json"),
            "--token-output",
            str(tmp_path / "oauth_token.local.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "failed safely" in result.stderr
    assert "refresh_token" not in result.stdout + result.stderr
    assert "access_token" not in result.stdout + result.stderr


def _write_client_secrets(tmp_path):
    path = tmp_path / "client_secrets.local.json"
    path.write_text(
        json.dumps({"installed": {"client_id": "mock-client-id", "client_secret": "mock-client-secret"}}),
        encoding="utf-8",
    )
    return path
