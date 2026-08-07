from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.cloud_ingestion.cloud_adapters import (
    MountedGrant,
    MountedOAuthCredentialProvider,
    PortalConfigurationProvider,
)
from src.cloud_ingestion.domain import IngestionConfiguration, RunRequest
from src.cloud_ingestion.errors import CredentialError
from src.providers.ga4.client import GA4_DATA_API_SCOPE


class Tokens:
    def __init__(self):
        self.audiences = []

    def token_for_audience(self, audience):
        self.audiences.append(audience)
        return "header.payload.signature"


def request(provider="ga4"):
    return RunRequest(
        project_id="20000000-0000-0000-0000-000000000001",
        provider=provider,
        week_start=date(2026, 7, 27),
        idempotency_key="30000000-0000-0000-0000-000000000001",
        environment="production",
    )


def configuration(binding="google-oauth/inn-spanish-head/ga4"):
    return IngestionConfiguration(
        identity="40000000-0000-0000-0000-000000000001",
        version=1,
        client_id="10000000-0000-0000-0000-000000000001",
        project_id="20000000-0000-0000-0000-000000000001",
        project_slug="spanishhead.com",
        provider="ga4",
        environment="production",
        reporting_timezone="America/Los_Angeles",
        external_resource_type="ga4_property",
        external_resource_id="properties/460499108",
        credential_binding_key=binding,
        request_ceiling=6,
        enabled=True,
    )


def test_portal_configuration_uses_keyless_auth_and_parses_canonical_mapping(monkeypatch):
    captured = {}
    payload = {
        "schema_version": "project_ingestion_configuration.v1",
        "identity": "40000000-0000-0000-0000-000000000001",
        "version": 1,
        "client_id": "10000000-0000-0000-0000-000000000001",
        "project_id": "20000000-0000-0000-0000-000000000001",
        "project_slug": "spanishhead.com",
        "provider": "ga4",
        "environment": "production",
        "reporting_timezone": "America/Los_Angeles",
        "external_resource_type": "ga4_property",
        "external_resource_id": "properties/460499108",
        "credential_binding_key": "google-oauth/inn-spanish-head/ga4",
        "request_ceiling": 6,
        "authorized_retry_count": 0,
        "max_payload_bytes": 2097152,
        "enabled": True,
    }

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _):
            return json.dumps(payload).encode()

    def urlopen(call, timeout):
        captured["call"] = call
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    tokens = Tokens()
    result = PortalConfigurationProvider("https://portal.example", tokens).load(request())
    assert result.external_resource_id == "properties/460499108"
    assert result.credential_binding_key == "google-oauth/inn-spanish-head/ga4"
    assert tokens.audiences == ["https://portal.example"]
    assert captured["call"].headers["Authorization"] == "Bearer header.payload.signature"
    assert captured["call"].headers["X-serverless-authorization"] == "Bearer header.payload.signature"


def test_binding_mismatch_refuses_before_secret_file_read(monkeypatch, tmp_path):
    secret = tmp_path / "grant.json"
    secret.write_text("must-not-be-read", encoding="utf-8")
    provider = MountedOAuthCredentialProvider(
        {
            "google-oauth/other/ga4": MountedGrant(
                "google-oauth/other/ga4", "ga4", secret, "1"
            )
        }
    )
    monkeypatch.setattr(Path, "read_bytes", lambda *_: (_ for _ in ()).throw(AssertionError()))
    with pytest.raises(CredentialError, match="binding is unavailable"):
        provider.resolve(configuration())


def test_mounted_grant_requires_exact_scope_and_refreshes_only_in_memory(monkeypatch, tmp_path):
    secret = tmp_path / "grant.json"
    secret.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "fixture-client",
                "client_secret": "fixture-secret",
                "refresh_token": "fixture-refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": [GA4_DATA_API_SCOPE],
            }
        ),
        encoding="utf-8",
    )

    class FakeCredentials:
        valid = False
        token = None

        def refresh(self, _request):
            self.valid = True
            self.token = "fixture-access-token"

    fake = FakeCredentials()
    monkeypatch.setattr(
        "src.cloud_ingestion.cloud_adapters.Credentials.from_authorized_user_info",
        lambda info, scopes: fake,
    )
    provider = MountedOAuthCredentialProvider(
        {
            "google-oauth/inn-spanish-head/ga4": MountedGrant(
                "google-oauth/inn-spanish-head/ga4", "ga4", secret, "7"
            )
        }
    )
    material = provider.resolve(configuration())
    assert material.binding_key == "google-oauth/inn-spanish-head/ga4"
    assert material.version_label == "7"
    assert material.value is fake
    # No refreshed access token is ever written back to the mounted grant.
    assert "fixture-access-token" not in secret.read_text(encoding="utf-8")


def test_mounted_grant_rejects_broader_scope(monkeypatch, tmp_path):
    secret = tmp_path / "grant.json"
    secret.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "fixture-client",
                "client_secret": "fixture-secret",
                "refresh_token": "fixture-refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": [GA4_DATA_API_SCOPE, "https://www.googleapis.com/auth/drive.readonly"],
            }
        ),
        encoding="utf-8",
    )
    provider = MountedOAuthCredentialProvider(
        {
            "google-oauth/inn-spanish-head/ga4": MountedGrant(
                "google-oauth/inn-spanish-head/ga4", "ga4", secret, "1"
            )
        }
    )
    with pytest.raises(CredentialError, match="scopes are not exact"):
        provider.resolve(configuration())
