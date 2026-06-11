from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .local_falcon_api_plan import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT_SECONDS, redacted_api_key


SCAN_REPORT_ENDPOINT = "/v1/reports/{report_key}/"
COMPETITOR_REPORT_ENDPOINT = "/v1/competitor-reports/{report_key}"


class LocalFalconLiveTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalFalconLiveConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @property
    def api_key_redacted(self) -> str:
        return redacted_api_key(self.api_key)


class LocalFalconReadOnlyLiveTransport:
    """Read-only Local Falcon Data Retrieval transport for one existing report at a time."""

    def __init__(self, config: LocalFalconLiveConfig, session: Any | None = None):
        if not config.api_key:
            raise LocalFalconLiveTransportError("LOCAL_FALCON_API_KEY is required for live read-only transport")
        self.config = config
        self._session = session or requests.Session()
        self._scan_reports: dict[str, dict[str, Any]] = {}
        self._competitor_reports: dict[str, dict[str, Any] | None] = {}

    @classmethod
    def from_env(
        cls,
        *,
        session: Any | None = None,
        env: dict[str, str] | None = None,
        api_key_env: str = "LOCAL_FALCON_API_KEY",
        allow_global_fallback: bool = True,
    ) -> "LocalFalconReadOnlyLiveTransport":
        source = os.environ if env is None else env
        env_name = (api_key_env or "").strip()
        api_key = (source.get(env_name) or "").strip() if env_name else ""
        if not api_key and allow_global_fallback and env_name != "LOCAL_FALCON_API_KEY":
            api_key = (source.get("LOCAL_FALCON_API_KEY") or "").strip()
        if not api_key:
            missing_name = env_name or "profile-specific Local Falcon API key env"
            raise LocalFalconLiveTransportError(
                f"{missing_name} is missing; no live Local Falcon request was attempted"
            )
        return cls(
            LocalFalconLiveConfig(
                api_key=api_key,
                base_url=(source.get("LOCAL_FALCON_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
                timeout_seconds=_positive_int(source.get("LOCAL_FALCON_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS),
                max_retries=_non_negative_int(source.get("LOCAL_FALCON_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
            ),
            session=session,
        )

    def get_report_summary(self, report_id: str) -> dict[str, Any]:
        return self._get_scan_report(report_id)

    def get_grid_points(self, report_id: str) -> dict[str, Any]:
        return self._get_scan_report(report_id)

    def get_competitors(self, report_id: str) -> dict[str, Any] | None:
        if report_id not in self._competitor_reports:
            self._competitor_reports[report_id] = self._post_json(
                COMPETITOR_REPORT_ENDPOINT.format(report_key=report_id),
                optional=True,
            )
        return self._competitor_reports[report_id]

    def get_ai_analysis(self, report_id: str) -> dict[str, Any] | None:
        return self._get_scan_report(report_id)

    def _get_scan_report(self, report_id: str) -> dict[str, Any]:
        if report_id not in self._scan_reports:
            self._scan_reports[report_id] = self._post_json(
                SCAN_REPORT_ENDPOINT.format(report_key=report_id),
                optional=False,
            )
        return self._scan_reports[report_id]

    def _post_json(self, path: str, *, optional: bool) -> dict[str, Any] | None:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        form = {"api_key": self.config.api_key}
        attempts = max(1, self.config.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.post(
                    url,
                    data=form,
                    timeout=self.config.timeout_seconds,
                    headers={"Accept": "application/json"},
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(_retry_delay(attempt))
                    continue
                raise LocalFalconLiveTransportError(
                    f"Local Falcon read-only request failed for {path}: {exc.__class__.__name__}"
                ) from exc

            if optional and response.status_code in {400, 404}:
                return None
            if response.status_code == 202:
                raise LocalFalconLiveTransportError(
                    f"Local Falcon report is still processing for {path}: HTTP 202"
                )
            if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                time.sleep(_retry_delay(attempt))
                continue
            if response.status_code >= 400:
                raise LocalFalconLiveTransportError(
                    f"Local Falcon read-only request failed for {path}: HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise LocalFalconLiveTransportError(
                    f"Local Falcon read-only request returned non-JSON for {path}"
                ) from exc
            if not isinstance(payload, dict):
                raise LocalFalconLiveTransportError(
                    f"Local Falcon read-only response for {path} was not a JSON object"
                )
            return payload

        raise LocalFalconLiveTransportError(
            f"Local Falcon read-only request failed for {path}: {last_error.__class__.__name__ if last_error else 'retry limit exceeded'}"
        )


def _positive_int(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LocalFalconLiveTransportError("LOCAL_FALCON_TIMEOUT_SECONDS must be an integer") from exc
    if parsed < 1:
        raise LocalFalconLiveTransportError("LOCAL_FALCON_TIMEOUT_SECONDS must be at least 1")
    return parsed


def _non_negative_int(value: str | None, default: int) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise LocalFalconLiveTransportError("LOCAL_FALCON_MAX_RETRIES must be an integer") from exc
    if parsed < 0:
        raise LocalFalconLiveTransportError("LOCAL_FALCON_MAX_RETRIES cannot be negative")
    return parsed


def _retry_delay(attempt: int) -> float:
    return min(2.0, 0.25 * attempt)
