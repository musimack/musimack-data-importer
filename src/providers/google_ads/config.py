from __future__ import annotations

import os
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DEVELOPER_TOKEN_ENV = "GOOGLE_ADS_DEVELOPER_TOKEN"
DEFAULT_OAUTH_CLIENT_SECRETS_ENV = "GOOGLE_ADS_OAUTH_CLIENT_SECRETS"
DEFAULT_OAUTH_TOKEN_FILE_ENV = "GOOGLE_ADS_OAUTH_TOKEN_FILE"
DEFAULT_REFRESH_TOKEN_ENV = "GOOGLE_ADS_REFRESH_TOKEN"
DEFAULT_LOGIN_CUSTOMER_ID_ENV = "GOOGLE_ADS_LOGIN_CUSTOMER_ID"
PROFILE_CUSTOMER_ID_ENV_OVERRIDES = {
    "inn-at-spanish-head": "SPANISH_HEAD_GOOGLE_ADS_CUSTOMER_ID",
}


@dataclass(frozen=True)
class GoogleAdsReadiness:
    ready: bool
    missing: list[str]
    profile: str
    customer_id_source: str
    has_login_customer_id: bool
    present: list[str]

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "missing": list(self.missing),
            "profile": self.profile,
            "customer_id_source": self.customer_id_source,
            "has_login_customer_id": self.has_login_customer_id,
            "present": list(self.present),
        }


@dataclass(frozen=True)
class GoogleAdsLocalConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str
    login_customer_id: str | None = None

    def to_google_ads_sdk_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "developer_token": self.developer_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "use_proto_plus": True,
        }
        if self.login_customer_id:
            payload["login_customer_id"] = self.login_customer_id
        return payload


class GoogleAdsConfigError(ValueError):
    pass


def check_google_ads_readiness(
    *,
    profile: str,
    customer_id: str | None = None,
    login_customer_id: str | None = None,
    developer_token_env: str = DEFAULT_DEVELOPER_TOKEN_ENV,
    oauth_client_secrets_env: str = DEFAULT_OAUTH_CLIENT_SECRETS_ENV,
    oauth_token_file_env: str = DEFAULT_OAUTH_TOKEN_FILE_ENV,
    environ: Mapping[str, str] | None = None,
) -> GoogleAdsReadiness:
    env = environ if environ is not None else os.environ
    profile_customer_id_env = profile_customer_id_env_name(profile)
    missing = []
    present = []

    for env_name in (developer_token_env, oauth_client_secrets_env, oauth_token_file_env):
        if _has_value(env, env_name):
            present.append(env_name)
        else:
            missing.append(env_name)

    if customer_id:
        customer_id_source = "cli"
    elif _has_value(env, profile_customer_id_env):
        customer_id_source = "env"
        present.append(profile_customer_id_env)
    else:
        customer_id_source = "missing"
        missing.append(profile_customer_id_env)

    has_login_customer_id = bool(login_customer_id) or _has_value(env, DEFAULT_LOGIN_CUSTOMER_ID_ENV)
    if has_login_customer_id and not login_customer_id:
        present.append(DEFAULT_LOGIN_CUSTOMER_ID_ENV)

    return GoogleAdsReadiness(
        ready=not missing,
        missing=missing,
        profile=profile,
        customer_id_source=customer_id_source,
        has_login_customer_id=has_login_customer_id,
        present=present,
    )


def load_google_ads_local_config(
    *,
    profile: str,
    customer_id: str | None = None,
    login_customer_id: str | None = None,
    developer_token_env: str = DEFAULT_DEVELOPER_TOKEN_ENV,
    oauth_client_secrets_env: str = DEFAULT_OAUTH_CLIENT_SECRETS_ENV,
    oauth_token_file_env: str = DEFAULT_OAUTH_TOKEN_FILE_ENV,
    environ: Mapping[str, str] | None = None,
) -> GoogleAdsLocalConfig:
    env = environ if environ is not None else os.environ
    developer_token = _required_env_value(env, developer_token_env)
    resolved_customer_id = customer_id or _required_env_value(
        env,
        profile_customer_id_env_name(profile),
    )
    client_secret_payload = _read_json_path(_required_env_value(env, oauth_client_secrets_env), oauth_client_secrets_env)
    token_payload = _read_json_path(_required_env_value(env, oauth_token_file_env), oauth_token_file_env)
    client_id, client_secret = _client_credentials_from_payload(client_secret_payload, oauth_client_secrets_env)
    refresh_token = _refresh_token_from_payload(token_payload, oauth_token_file_env)
    resolved_login_customer_id = login_customer_id or _optional_env_value(env, DEFAULT_LOGIN_CUSTOMER_ID_ENV)
    return GoogleAdsLocalConfig(
        developer_token=developer_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        customer_id=resolved_customer_id,
        login_customer_id=resolved_login_customer_id,
    )


def _has_value(environ: Mapping[str, str], name: str) -> bool:
    return bool(str(environ.get(name, "")).strip())


def profile_customer_id_env_name(profile: str) -> str:
    return PROFILE_CUSTOMER_ID_ENV_OVERRIDES.get(
        profile,
        f"{profile.upper().replace('-', '_')}_GOOGLE_ADS_CUSTOMER_ID",
    )


def _required_env_value(environ: Mapping[str, str], name: str) -> str:
    value = str(environ.get(name, "")).strip()
    if not value:
        raise GoogleAdsConfigError(f"missing required local configuration: {name}")
    return value


def _optional_env_value(environ: Mapping[str, str], name: str) -> str | None:
    value = str(environ.get(name, "")).strip()
    return value or None


def _read_json_path(path_value: str, env_name: str) -> dict[str, object]:
    path = Path(path_value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GoogleAdsConfigError(f"{env_name} points to a local file that could not be read") from exc
    except json.JSONDecodeError as exc:
        raise GoogleAdsConfigError(f"{env_name} points to a file that is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise GoogleAdsConfigError(f"{env_name} must point to a JSON object")
    return payload


def _client_credentials_from_payload(payload: dict[str, object], source_name: str) -> tuple[str, str]:
    candidates = []
    for key in ("installed", "web"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    candidates.append(payload)
    for candidate in candidates:
        client_id = str(candidate.get("client_id", "")).strip()
        client_secret = str(candidate.get("client_secret", "")).strip()
        if client_id and client_secret:
            return client_id, client_secret
    raise GoogleAdsConfigError(f"{source_name} does not contain required OAuth client fields")


def _refresh_token_from_payload(payload: dict[str, object], source_name: str) -> str:
    refresh_token = str(payload.get("refresh_token", "")).strip()
    if not refresh_token:
        raise GoogleAdsConfigError(f"{source_name} does not contain a refresh token")
    return refresh_token
