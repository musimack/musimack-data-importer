from __future__ import annotations

import json
from datetime import date

from src.console_ops import (
    ConsoleClient,
    build_console_readiness_report,
    load_clients,
    output_path_for,
    redact_sensitive_text,
)
from src.oauth_readiness import report_has_failures


def test_load_clients_from_config_file(tmp_path):
    config = tmp_path / "clients.json"
    config.write_text(
        json.dumps(
            {
                "aluma": {
                    "client_label": "Aluma Aesthetic Medicine",
                    "domain": "alumapdx.com",
                    "portal_project_id": "project-id",
                    "portal_report_id": "report-id",
                    "ga4_property_id": "341923472",
                    "suggested_export_slug": "aluma",
                    "suggested_ytd_start_date": "2026-01-01",
                    "suggested_ytd_end_date": "2026-05-19",
                    "assigned_client_email": "aluma.client@musimack.local",
                }
            }
        ),
        encoding="utf-8",
    )

    clients = load_clients(config)

    assert len(clients) == 1
    assert clients[0].client_label == "Aluma Aesthetic Medicine"
    assert clients[0].portal_report_id == "report-id"
    assert clients[0].assigned_client_email == "aluma.client@musimack.local"


def test_output_path_uses_ytd_filename_pattern():
    client = ConsoleClient(
        key="aluma",
        client_label="Aluma Aesthetic Medicine",
        domain="alumapdx.com",
        portal_project_id="project-id",
        ga4_property_id="341923472",
        suggested_export_slug="aluma",
        suggested_ytd_start_date="2026-01-01",
        suggested_ytd_end_date="2026-05-19",
    )

    path = output_path_for(client, date(2026, 1, 1), date(2026, 5, 19))

    assert str(path) == "exports\\ytd_2026\\aluma_ga4_ytd_2026_2026-01-01_to_2026-05-19.json"


def test_output_path_uses_smoke_filename_for_aluma_smoke_range():
    client = ConsoleClient(
        key="aluma",
        client_label="Aluma Aesthetic Medicine",
        domain="alumapdx.com",
        portal_project_id="project-id",
        ga4_property_id="341923472",
        suggested_export_slug="aluma",
        suggested_ytd_start_date="2026-01-01",
        suggested_ytd_end_date="2026-05-19",
    )

    path = output_path_for(client, date(2026, 5, 1), date(2026, 5, 2))

    assert str(path) == "exports\\smoke\\aluma_ga4_smoke_2026-05-01_to_2026-05-02.json"


def test_redaction_helper_masks_secret_like_output():
    text = (
        "Authorization: Bearer abc123\n"
        '"refresh_token": "refresh-value",\n'
        '"client_secret": "secret-value",\n'
        '"private_key": "private-value"\n'
    )

    redacted = redact_sensitive_text(text)

    assert "abc123" not in redacted
    assert "refresh-value" not in redacted
    assert "secret-value" not in redacted
    assert "private-value" not in redacted
    assert "[redacted]" in redacted


def test_console_readiness_includes_exports_directory(tmp_path):
    client_file = tmp_path / "client.json"
    token_dir = tmp_path / "tokens"
    exports_dir = tmp_path / "exports"
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

    checks = build_console_readiness_report(env=env, exports_dir=exports_dir)

    assert not report_has_failures(checks)
    assert any(
        check.level == "PASS"
        and check.check == "exports directory"
        and "writable" in check.message
        for check in checks
    )
