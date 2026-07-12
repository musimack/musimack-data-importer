from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google_auth_oauthlib.flow import InstalledAppFlow


GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_SEARCH_ANALYTICS_URL = (
    "https://searchconsole.googleapis.com/webmasters/v3/sites/{site_url}/searchAnalytics/query"
)
DEFAULT_GSC_TOKEN_FILE = Path("secrets") / "gsc_token.local.json"


class GscClientError(RuntimeError):
    pass


class GscOAuthError(GscClientError):
    pass


@dataclass(frozen=True)
class GscFetchConfig:
    client_secrets_file: str
    token_file: str
    site_url: str
    row_limit: int = 25000


class GscSearchConsoleClient:
    def __init__(
        self,
        config: GscFetchConfig,
        session: requests.Session | None = None,
        timeout_seconds: int = 30,
    ):
        self._config = config
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds

    def query_search_analytics(
        self,
        start_date: str,
        end_date: str,
        *,
        dimensions: list[str] | None = None,
        row_limit: int | None = None,
        search_type: str = "web",
    ) -> dict[str, Any]:
        credentials = load_gsc_oauth_credentials(
            self._config.client_secrets_file,
            self._config.token_file,
        )
        url = GSC_SEARCH_ANALYTICS_URL.format(site_url=requests.utils.quote(self._config.site_url, safe=""))
        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query", "page", "date"] if dimensions is None else dimensions,
            "type": search_type,
            "rowLimit": row_limit or self._config.row_limit,
            "startRow": 0,
        }
        try:
            response = self._session.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {credentials.token}"},
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as exc:
            raise GscClientError("GSC API request failed before a response was received") from exc
        if response.status_code >= 400:
            raise GscClientError(sanitized_google_api_error(response))
        try:
            data = response.json()
        except ValueError as exc:
            raise GscClientError("GSC API response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise GscClientError("GSC API response did not contain a JSON object")
        return data

    def query_exact_range_summary(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self.query_search_analytics(start_date, end_date, dimensions=[], row_limit=1)

    def query_exact_range_queries(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self.query_search_analytics(start_date, end_date, dimensions=["query"], row_limit=10)

    def query_exact_range_pages(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self.query_search_analytics(start_date, end_date, dimensions=["page"], row_limit=10)


def load_gsc_oauth_credentials(client_secrets_file: str, token_file: str):
    token_path = Path(token_file)
    credentials = None
    if token_path.exists():
        try:
            credentials = oauth_credentials.Credentials.from_authorized_user_file(
                str(token_path),
                scopes=[GSC_READONLY_SCOPE],
            )
        except (ValueError, OSError, GoogleAuthError) as exc:
            raise GscOAuthError(
                "GSC OAuth token cache is not usable as authorized-user credentials; "
                "refresh or recreate MUSIMACK_GSC_OAUTH_TOKEN_FILE"
            ) from exc
    if credentials and credentials.valid:
        return credentials
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            save_gsc_oauth_credentials(token_path, credentials)
        except (OSError, GoogleAuthError, RefreshError) as exc:
            raise GscOAuthError(
                "GSC OAuth token refresh failed or token cache write was blocked; "
                "confirm the GSC token path is writable"
            ) from exc
        return credentials

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file,
            scopes=[GSC_READONLY_SCOPE],
        )
        credentials = flow.run_local_server(port=0)
        save_gsc_oauth_credentials(token_path, credentials)
    except FileNotFoundError as exc:
        raise GscOAuthError(
            "GSC OAuth client secrets file was not found; check MUSIMACK_GSC_OAUTH_CLIENT_SECRETS "
            "or pass --credentials"
        ) from exc
    except (OSError, ValueError, GoogleAuthError) as exc:
        raise GscOAuthError(
            "GSC OAuth browser login or token cache write failed; confirm the client secrets "
            "and separate GSC token cache paths are readable/writable"
        ) from exc
    return credentials


def save_gsc_oauth_credentials(token_path: Path, credentials) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def sanitized_google_api_error(response) -> str:
    parts = [f"GSC API request failed with HTTP {response.status_code}"]
    try:
        payload = response.json()
    except ValueError:
        return "; ".join(parts)

    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "; ".join(parts)

    status = error.get("status")
    reason = _google_error_reason(error)
    message = error.get("message")
    if status:
        parts.append(f"status={_safe_error_text(status)}")
    if reason:
        parts.append(f"reason={_safe_error_text(reason)}")
    if message:
        parts.append(f"message={_safe_error_text(message)}")
    return "; ".join(parts)


def _google_error_reason(error: dict[str, Any]) -> str | None:
    for detail in error.get("details", []):
        if not isinstance(detail, dict):
            continue
        reason = detail.get("reason")
        if reason:
            return str(reason)
        violations = detail.get("fieldViolations")
        if isinstance(violations, list) and violations:
            first = violations[0]
            if isinstance(first, dict):
                return first.get("reason") or first.get("field")
    return None


def _safe_error_text(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    forbidden = [
        "access_token",
        "refresh_token",
        "authorization",
        "client_secret",
        "private_key",
        "credential",
    ]
    lowered = text.lower()
    if any(term in lowered for term in forbidden):
        return "[redacted]"
    return text[:500]
