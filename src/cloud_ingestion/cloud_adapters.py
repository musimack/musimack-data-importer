"""Production cloud adapters for Portal configuration and mounted OAuth grants.

Secret payloads are read only after the Portal has authorized an exact
project/provider configuration. They are parsed and refreshed in memory, never
logged, written back, or exposed through application evidence.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src.providers.ga4.client import GA4_DATA_API_SCOPE
from src.providers.gsc.client import GSC_READONLY_SCOPE

from .domain import CredentialMaterial, IngestionConfiguration, RunRequest
from .errors import ConfigurationError, CredentialError
from .fixture_adapters import CONFIGURATION_SCHEMA
from .ports import IdentityTokenProvider

_SCOPES = {"ga4": GA4_DATA_API_SCOPE, "gsc": GSC_READONLY_SCOPE}
_MAX_CONFIGURATION_BYTES = 64 * 1024
_MAX_GRANT_BYTES = 64 * 1024


@dataclass(frozen=True)
class MountedGrant:
    binding_key: str
    provider: str
    path: Path
    version_label: str


class PortalConfigurationProvider:
    """Load the canonical non-secret mapping from the private Portal."""

    def __init__(self, portal_url: str, identity_tokens: IdentityTokenProvider) -> None:
        base = portal_url.rstrip("/")
        if not base.startswith("https://") or "*" in base:
            raise ConfigurationError("the Portal URL must be an exact https URL")
        self._portal_url = base
        self._identity_tokens = identity_tokens

    def load(self, request: RunRequest) -> IngestionConfiguration:
        token = self._identity_tokens.token_for_audience(self._portal_url)
        url = (
            f"{self._portal_url}/api/service/v1/projects/{request.project_id}"
            f"/providers/{request.provider}/configuration"
        )
        call = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Serverless-Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(call, timeout=30) as response:
                body = response.read(_MAX_CONFIGURATION_BYTES + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(_MAX_CONFIGURATION_BYTES + 1)
        except Exception as exc:
            raise ConfigurationError("Portal configuration transport failed") from exc
        if status != 200 or len(body) > _MAX_CONFIGURATION_BYTES:
            raise ConfigurationError("Portal configuration was refused")
        try:
            payload = json.loads(body)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("Portal configuration response was malformed") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != CONFIGURATION_SCHEMA:
            raise ConfigurationError("Portal configuration schema is unsupported")
        try:
            return IngestionConfiguration(
                identity=payload["identity"],
                version=payload["version"],
                client_id=payload["client_id"],
                project_id=payload["project_id"],
                project_slug=payload["project_slug"],
                provider=payload["provider"],
                environment=payload["environment"],
                reporting_timezone=payload["reporting_timezone"],
                external_resource_type=payload["external_resource_type"],
                external_resource_id=payload["external_resource_id"],
                credential_binding_key=payload["credential_binding_key"],
                request_ceiling=payload["request_ceiling"],
                authorized_retry_count=payload.get("authorized_retry_count", 0),
                max_payload_bytes=payload.get("max_payload_bytes", 2 * 1024 * 1024),
                enabled=payload["enabled"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("Portal configuration is incomplete") from exc


class MountedOAuthCredentialProvider:
    """Resolve exactly one Portal-bound OAuth grant from a read-only mount."""

    def __init__(self, grants: Mapping[str, MountedGrant]) -> None:
        self._grants = dict(grants)
        if not self._grants or any(key != grant.binding_key for key, grant in self._grants.items()):
            raise CredentialError("credential binding configuration is malformed")

    def resolve(self, configuration: IngestionConfiguration) -> CredentialMaterial:
        grant = self._grants.get(configuration.credential_binding_key)
        if grant is None or grant.provider != configuration.provider:
            raise CredentialError("the authorized credential binding is unavailable")
        if not grant.version_label or not grant.version_label.isdigit():
            raise CredentialError("the credential secret version is not pinned")
        try:
            raw = grant.path.read_bytes()
        except OSError as exc:
            raise CredentialError("the mounted credential grant is unavailable") from exc
        if not raw or len(raw) > _MAX_GRANT_BYTES:
            raise CredentialError("the mounted credential grant is malformed")
        try:
            info = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise CredentialError("the mounted credential grant is malformed") from exc
        if not isinstance(info, dict) or info.get("type") not in (None, "authorized_user"):
            raise CredentialError("the mounted credential grant type is unsupported")
        required = ("client_id", "client_secret", "refresh_token", "token_uri")
        if any(not isinstance(info.get(key), str) or not info[key].strip() for key in required):
            raise CredentialError("the mounted credential grant is incomplete")
        expected_scope = _SCOPES.get(configuration.provider)
        scopes = info.get("scopes")
        if expected_scope is None or not isinstance(scopes, list) or set(scopes) != {expected_scope}:
            raise CredentialError("the mounted credential grant scopes are not exact")
        try:
            credentials = Credentials.from_authorized_user_info(info, scopes=[expected_scope])
            credentials.refresh(Request())
        except (GoogleAuthError, OSError, ValueError) as exc:
            raise CredentialError("the mounted credential grant could not be refreshed") from exc
        if not credentials.valid or not credentials.token:
            raise CredentialError("the mounted credential grant did not produce a usable credential")
        return CredentialMaterial(grant.binding_key, grant.version_label, credentials)
