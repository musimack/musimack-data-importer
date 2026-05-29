from __future__ import annotations

from pathlib import Path

from src.local_config import load_local_operator_config
from src.oauth_readiness import build_oauth_readiness_report


def test_loads_env_local_without_overriding_existing_env(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "MUSIMACK_GA4_AUTH_METHOD=oauth",
                "MUSIMACK_PORTAL_DATABASE_URL=postgresql://from-file",
            ]
        ),
        encoding="utf-8",
    )
    env = {"MUSIMACK_PORTAL_DATABASE_URL": "postgresql://from-os"}

    status = load_local_operator_config(env_file, environ=env)

    assert status.found
    assert status.loaded_names == ("MUSIMACK_GA4_AUTH_METHOD",)
    assert status.skipped_existing_names == ("MUSIMACK_PORTAL_DATABASE_URL",)
    assert env["MUSIMACK_GA4_AUTH_METHOD"] == "oauth"
    assert env["MUSIMACK_PORTAL_DATABASE_URL"] == "postgresql://from-os"


def test_missing_env_local_is_warning_not_crash(tmp_path):
    status = load_local_operator_config(tmp_path / ".env.local", environ={})

    assert not status.found
    assert status.error is None
    assert ".env.local was not found" in "\n".join(status.safe_summary_lines())


def test_empty_env_local_is_helpful_warning(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("", encoding="utf-8")

    status = load_local_operator_config(env_file, environ={})

    assert status.found
    assert "no settings were loaded" in "\n".join(status.safe_summary_lines())


def test_loads_utf16_env_local_created_by_windows_tools(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("MUSIMACK_GA4_AUTH_METHOD=oauth\n", encoding="utf-16")
    env = {}

    status = load_local_operator_config(env_file, environ=env)

    assert status.loaded_names == ("MUSIMACK_GA4_AUTH_METHOD",)
    assert env["MUSIMACK_GA4_AUTH_METHOD"] == "oauth"


def test_readiness_can_see_values_loaded_from_local_config(tmp_path):
    client_file = tmp_path / "client.json"
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    client_file.write_text(
        """
        {
          "installed": {
            "client_id": "client-id",
            "auth_uri": "https://example.test/auth",
            "token_uri": "https://example.test/token",
            "client_secret": "do-not-print"
          }
        }
        """,
        encoding="utf-8",
    )
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "MUSIMACK_GA4_AUTH_METHOD=oauth",
                f"MUSIMACK_GA4_OAUTH_CLIENT_SECRETS={client_file}",
                f"MUSIMACK_GA4_OAUTH_TOKEN_FILE={token_dir / 'token.json'}",
                "MUSIMACK_PORTAL_DATABASE_URL=postgresql://from-file",
            ]
        ),
        encoding="utf-8",
    )
    env = {}

    load_local_operator_config(env_file, environ=env)
    checks = build_oauth_readiness_report(env)

    assert not any(check.failed for check in checks)


def test_safe_summary_does_not_print_loaded_values(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "MUSIMACK_GA4_AUTH_METHOD=oauth",
                "MUSIMACK_PORTAL_DATABASE_URL=postgresql://secret-user:secret-pass@localhost/db",
            ]
        ),
        encoding="utf-8",
    )

    status = load_local_operator_config(env_file, environ={})
    text = "\n".join(status.safe_summary_lines())

    assert "secret-user" not in text
    assert "secret-pass" not in text
    assert "oauth" not in text


def test_ga4_config_loads_local_config_before_reading_env(monkeypatch):
    from src.config import load_ga4_config

    for name in (
        "MUSIMACK_GA4_PROPERTY_ID",
        "MUSIMACK_GA4_AUTH_METHOD",
        "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS",
        "MUSIMACK_GA4_OAUTH_TOKEN_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    def fake_load_local_operator_config():
        monkeypatch.setenv("MUSIMACK_GA4_PROPERTY_ID", "341923472")
        monkeypatch.setenv("MUSIMACK_GA4_AUTH_METHOD", "oauth")
        monkeypatch.setenv("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", "C:\\outside\\client.json")
        monkeypatch.setenv("MUSIMACK_GA4_OAUTH_TOKEN_FILE", "C:\\outside\\token.json")

    monkeypatch.setattr("src.config.load_local_operator_config", fake_load_local_operator_config)

    config = load_ga4_config()

    assert config.property_id == "341923472"
    assert config.auth_method == "oauth"


def test_database_config_loads_local_config_before_reading_env(monkeypatch):
    from src.config import load_database_config

    monkeypatch.delenv("MUSIMACK_PORTAL_DATABASE_URL", raising=False)
    monkeypatch.delenv("MUSIMACK_PORTAL_PROJECT_ID", raising=False)

    def fake_load_local_operator_config():
        monkeypatch.setenv("MUSIMACK_PORTAL_DATABASE_URL", "postgresql://from-local")
        monkeypatch.setenv("MUSIMACK_PORTAL_PROJECT_ID", "project-from-local")

    monkeypatch.setattr("src.config.load_local_operator_config", fake_load_local_operator_config)

    config = load_database_config()

    assert config.database_url == "postgresql://from-local"
    assert config.project_id == "project-from-local"
