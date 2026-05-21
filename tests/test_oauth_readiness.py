from __future__ import annotations

import json

from src.oauth_readiness import build_oauth_readiness_report, report_has_failures


def _levels(checks):
    return [(check.level, check.check, check.message) for check in checks]


def test_readiness_reports_missing_env_vars():
    checks = build_oauth_readiness_report({})

    assert report_has_failures(checks)
    messages = [check.message for check in checks]
    assert "MUSIMACK_GA4_AUTH_METHOD is missing" in messages
    assert "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS is missing" in messages
    assert "MUSIMACK_GA4_OAUTH_TOKEN_FILE is missing" in messages
    assert "MUSIMACK_PORTAL_DATABASE_URL is missing" in messages


def test_readiness_fails_missing_client_secrets_path(tmp_path):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    env = {
        "MUSIMACK_GA4_AUTH_METHOD": "oauth",
        "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": str(tmp_path / "missing-client.json"),
        "MUSIMACK_GA4_OAUTH_TOKEN_FILE": str(token_dir / "token.json"),
        "MUSIMACK_PORTAL_DATABASE_URL": "postgresql://example",
    }

    checks = build_oauth_readiness_report(env)

    assert report_has_failures(checks)
    assert any(
        check.level == "FAIL"
        and check.check == "OAuth client secrets file"
        and "does not exist" in check.message
        for check in checks
    )


def test_readiness_passes_safe_shape_and_warns_missing_token(tmp_path):
    client_file = tmp_path / "client.json"
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id",
                    "auth_uri": "https://example.test/auth",
                    "token_uri": "https://example.test/token",
                    "client_secret": "do-not-print",
                }
            }
        ),
        encoding="utf-8",
    )
    env = {
        "MUSIMACK_GA4_AUTH_METHOD": "oauth",
        "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": str(client_file),
        "MUSIMACK_GA4_OAUTH_TOKEN_FILE": str(token_dir / "token.json"),
        "MUSIMACK_PORTAL_DATABASE_URL": "postgresql://example",
    }

    checks = build_oauth_readiness_report(env)

    assert not report_has_failures(checks)
    assert any(
        check.level == "PASS" and check.check == "OAuth client secrets JSON"
        for check in checks
    )
    assert any(
        check.level == "WARN"
        and check.check == "OAuth token cache file"
        and "does not exist" in check.message
        for check in checks
    )


def test_readiness_fails_missing_token_directory(tmp_path):
    client_file = tmp_path / "client.json"
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id",
                    "auth_uri": "https://example.test/auth",
                    "token_uri": "https://example.test/token",
                    "client_secret": "do-not-print",
                }
            }
        ),
        encoding="utf-8",
    )
    env = {
        "MUSIMACK_GA4_AUTH_METHOD": "oauth",
        "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": str(client_file),
        "MUSIMACK_GA4_OAUTH_TOKEN_FILE": str(tmp_path / "missing-dir" / "token.json"),
        "MUSIMACK_PORTAL_DATABASE_URL": "postgresql://example",
    }

    checks = build_oauth_readiness_report(env)

    assert report_has_failures(checks)
    assert any(
        check.level == "FAIL"
        and check.check == "OAuth token cache directory"
        and "does not exist" in check.message
        for check in checks
    )


def test_readiness_messages_do_not_include_secret_values(tmp_path):
    client_file = tmp_path / "client.json"
    token_file = tmp_path / "token.json"
    client_file.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "visible-field-name",
                    "auth_uri": "https://example.test/auth",
                    "token_uri": "https://example.test/token",
                    "client_secret": "super-sensitive-client-secret",
                }
            }
        ),
        encoding="utf-8",
    )
    token_file.write_text(
        '{"refresh_token": "super-sensitive-refresh-token"}',
        encoding="utf-8",
    )
    env = {
        "MUSIMACK_GA4_AUTH_METHOD": "oauth",
        "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS": str(client_file),
        "MUSIMACK_GA4_OAUTH_TOKEN_FILE": str(token_file),
        "MUSIMACK_PORTAL_DATABASE_URL": "postgresql://example",
    }

    text = "\n".join(check.line() for check in build_oauth_readiness_report(env))

    assert "super-sensitive-client-secret" not in text
    assert "super-sensitive-refresh-token" not in text
