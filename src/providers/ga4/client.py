from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow

from ...config import DateRange, Ga4Config

GA4_DATA_API_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GA4_RUN_REPORT_URL = "https://analyticsdata.googleapis.com/v1beta/{property_resource}:runReport"
GA4_EXACT_RANGE_SUMMARY_METRICS = (
    "activeUsers",
    "newUsers",
    "sessions",
    "screenPageViews",
    "engagedSessions",
    "engagementRate",
    "averageSessionDuration",
    "averageEngagementTime",
    "eventCount",
    "keyEvents",
    "conversions",
)
GA4_EXACT_RANGE_SUMMARY_REQUIRED_METRICS = (
    "activeUsers",
    "sessions",
    "screenPageViews",
    "engagementRate",
)


class Ga4ClientError(RuntimeError):
    pass


class OAuthCredentialError(Ga4ClientError):
    pass


class Ga4DataClient:
    def __init__(self, config: Ga4Config, timeout_seconds: int = 30):
        self._config = config
        self._timeout_seconds = timeout_seconds

    def run_traffic_overview(self, date_range: DateRange) -> dict[str, Any]:
        trend = self._run_report(build_traffic_overview_request(date_range))
        warnings = []
        channel_breakdown = _empty_report()
        top_pages = _empty_report()
        source_medium = _empty_report()
        landing_pages = _empty_report()
        try:
            channel_breakdown = self._run_report(build_channel_breakdown_request(date_range))
        except Ga4ClientError as exc:
            warnings.append(f"Channel breakdown omitted: {exc}")
        try:
            top_pages = self._run_report(build_top_pages_request(date_range))
        except Ga4ClientError as exc:
            warnings.append(f"Top pages omitted: {exc}")
        try:
            source_medium = self._run_report(build_source_medium_request(date_range))
        except Ga4ClientError as exc:
            warnings.append(f"Source/source-medium rows omitted: {exc}")
        try:
            landing_pages = self._run_report(build_landing_pages_request(date_range))
        except Ga4ClientError as exc:
            warnings.append(f"Landing pages omitted: {exc}")
        return {
            "traffic_overview": trend,
            "channel_breakdown": channel_breakdown,
            "top_pages": top_pages,
            "source_medium": source_medium,
            "landing_pages": landing_pages,
            "warnings": warnings,
        }

    def run_exact_range_summary(
        self,
        date_range: DateRange,
        *,
        metric_names: tuple[str, ...] = GA4_EXACT_RANGE_SUMMARY_METRICS,
    ) -> dict[str, Any]:
        return self._run_report(build_exact_range_summary_request(date_range, metric_names=metric_names))

    def run_exact_range_channel_performance(self, date_range: DateRange) -> dict[str, Any]:
        return self._run_report(build_channel_breakdown_request(date_range))

    def run_exact_range_top_sources(self, date_range: DateRange) -> dict[str, Any]:
        return self._run_report(build_source_medium_request(date_range))

    def run_exact_range_top_landing_pages(self, date_range: DateRange) -> dict[str, Any]:
        return self._run_report(build_landing_pages_request(date_range))

    def run_exact_range_most_viewed_pages(self, date_range: DateRange) -> dict[str, Any]:
        return self._run_report(build_top_pages_request(date_range))

    def _run_report(self, body: dict[str, Any]) -> dict[str, Any]:
        credentials = self._credentials()
        if not credentials.valid:
            credentials.refresh(Request())
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }
        url = GA4_RUN_REPORT_URL.format(property_resource=self._config.property_resource)
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise Ga4ClientError(sanitized_google_api_error(response))
        return response.json()

    def _credentials(self):
        if self._config.auth_method == "oauth":
            return load_oauth_credentials(
                self._config.oauth_client_secrets_file,
                self._config.oauth_token_file,
            )
        if self._config.service_account_info:
            return service_account.Credentials.from_service_account_info(
                self._config.service_account_info,
                scopes=[GA4_DATA_API_SCOPE],
            )
        return service_account.Credentials.from_service_account_file(
            self._config.service_account_file,
            scopes=[GA4_DATA_API_SCOPE],
        )


def load_oauth_credentials(client_secrets_file: str, token_file: str):
    token_path = Path(token_file)
    credentials = None
    if token_path.exists():
        try:
            credentials = oauth_credentials.Credentials.from_authorized_user_file(
                str(token_path),
                scopes=[GA4_DATA_API_SCOPE],
            )
        except (ValueError, OSError, GoogleAuthError) as exc:
            raise OAuthCredentialError(
                "OAuth token cache is not usable as authorized-user credentials; "
                "refresh or recreate MUSIMACK_GA4_OAUTH_TOKEN_FILE with the bootstrap command"
            ) from exc
    if credentials and credentials.valid:
        return credentials
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            save_oauth_credentials(token_path, credentials)
        except (OSError, GoogleAuthError, RefreshError) as exc:
            raise OAuthCredentialError(
                "OAuth token refresh failed or token cache write was blocked; "
                "run bootstrap from normal local PowerShell and confirm the token path is writable"
            ) from exc
        return credentials

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file,
            scopes=[GA4_DATA_API_SCOPE],
        )
        credentials = flow.run_local_server(port=0)
        save_oauth_credentials(token_path, credentials)
    except FileNotFoundError as exc:
        raise OAuthCredentialError(
            "OAuth client secrets file was not found; check MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"
        ) from exc
    except (OSError, ValueError, GoogleAuthError) as exc:
        raise OAuthCredentialError(
            "OAuth browser login or token cache write failed; run bootstrap from normal local PowerShell "
            "and confirm the client secrets and token cache paths are readable/writable"
        ) from exc
    return credentials


def save_oauth_credentials(token_path, credentials) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def sanitized_google_api_error(response) -> str:
    parts = [f"GA4 Data API request failed with HTTP {response.status_code}"]
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
    ]
    lowered = text.lower()
    if any(term in lowered for term in forbidden):
        return "[redacted]"
    return text[:500]


def build_traffic_overview_request(date_range: DateRange) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "dimensions": [{"name": "date"}],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "eventCount"},
        ],
        "limit": 10000,
        "keepEmptyRows": False,
    }


def build_exact_range_summary_request(
    date_range: DateRange,
    *,
    metric_names: tuple[str, ...] = GA4_EXACT_RANGE_SUMMARY_METRICS,
) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "metrics": [{"name": name} for name in metric_names],
        "limit": 1,
        "keepEmptyRows": False,
    }


def build_channel_breakdown_request(date_range: DateRange) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "dimensions": [{"name": "sessionDefaultChannelGroup"}],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "eventCount"},
        ],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 10,
        "keepEmptyRows": False,
    }


def build_top_pages_request(date_range: DateRange) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "dimensions": [{"name": "pageTitle"}, {"name": "pagePath"}],
        "metrics": [
            {"name": "screenPageViews"},
            {"name": "activeUsers"},
            {"name": "eventCount"},
            {"name": "averageSessionDuration"},
        ],
        "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        "limit": 10,
        "keepEmptyRows": False,
    }


def build_source_medium_request(date_range: DateRange) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "dimensions": [{"name": "sessionSourceMedium"}],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "eventCount"},
        ],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 10,
        "keepEmptyRows": False,
    }


def build_landing_pages_request(date_range: DateRange) -> dict[str, Any]:
    return {
        "dateRanges": [date_range.as_ga4()],
        "dimensions": [{"name": "landingPagePlusQueryString"}],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
            {"name": "eventCount"},
        ],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 10,
        "keepEmptyRows": False,
    }


def _empty_report() -> dict[str, Any]:
    return {"dimensionHeaders": [], "metricHeaders": [], "rows": []}
