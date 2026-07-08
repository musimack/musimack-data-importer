from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .local_config import load_local_operator_config
from .profile_local_config import DEFAULT_LOCAL_PROFILE_CONFIG_DIR, load_profile_local_config


ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def as_ga4(self) -> dict[str, str]:
        return {"startDate": self.start.isoformat(), "endDate": self.end.isoformat()}


@dataclass(frozen=True)
class Ga4Config:
    auth_method: str
    property_id: str
    oauth_client_secrets_file: str | None
    oauth_token_file: str | None
    service_account_file: str | None
    service_account_info: dict | None

    @property
    def property_resource(self) -> str:
        return f"properties/{self.property_id}"


@dataclass(frozen=True)
class DatabaseConfig:
    database_url: str
    project_id: str


def default_date_range(today: date | None = None) -> DateRange:
    today = today or date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=29)
    return DateRange(start=start, end=end)


def parse_date_range(start_date: str | None, end_date: str | None) -> DateRange:
    if not start_date and not end_date:
        return default_date_range()
    if not start_date or not end_date:
        raise ConfigError("--start-date and --end-date must be provided together")
    try:
        parsed = DateRange(
            start=date.fromisoformat(start_date),
            end=date.fromisoformat(end_date),
        )
    except ValueError as exc:
        raise ConfigError("dates must use YYYY-MM-DD format") from exc
    if parsed.end < parsed.start:
        raise ConfigError("--end-date must be on or after --start-date")
    return parsed


def env_value(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    if required:
        raise ConfigError(f"{name} is required")
    return None


def load_ga4_config(profile_slug: str | None = None) -> Ga4Config:
    load_local_operator_config()
    profile_ga4 = {}
    if profile_slug:
        profile_ga4 = load_profile_local_config(
            profile_slug,
            config_dir=DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
            env=os.environ,
        ).provider("ga4")
    property_id_env = str(profile_ga4.get("property_id_env") or "MUSIMACK_GA4_PROPERTY_ID")
    oauth_client_env = str(profile_ga4.get("oauth_client_secrets_env") or "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS")
    oauth_token_env = str(profile_ga4.get("oauth_token_file_env") or "MUSIMACK_GA4_OAUTH_TOKEN_FILE")

    property_id = _env_or_profile_value(
        property_id_env, profile_ga4.get("_resolved_property_id"), required=True
    )
    if not property_id or not property_id.isdigit():
        raise ConfigError(f"{property_id_env} must contain only digits")

    auth_method = (env_value("MUSIMACK_GA4_AUTH_METHOD", required=False) or "oauth").lower()
    if auth_method not in {"oauth", "service_account"}:
        raise ConfigError("MUSIMACK_GA4_AUTH_METHOD must be oauth or service_account")

    oauth_client_secrets_file = _env_or_profile_value(
        oauth_client_env, profile_ga4.get("_resolved_oauth_client_secrets_file"), required=False
    )
    oauth_token_file = _env_or_profile_value(
        oauth_token_env, profile_ga4.get("_resolved_oauth_token_file"), required=False
    )
    service_account_file = env_value("GOOGLE_APPLICATION_CREDENTIALS", required=False)
    service_account_json = env_value("MUSIMACK_GA4_SERVICE_ACCOUNT_JSON", required=False)
    service_account_info = None
    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as exc:
            raise ConfigError("MUSIMACK_GA4_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    if auth_method == "oauth" and (not oauth_client_secrets_file or not oauth_token_file):
        raise ConfigError(
            f"{oauth_client_env} and {oauth_token_env} are required for oauth"
        )
    if auth_method == "oauth":
        _reject_repo_secret_path(oauth_client_secrets_file, "GA4 OAuth client secrets file")
        _reject_repo_secret_path(oauth_token_file, "GA4 OAuth token file")

    if auth_method == "service_account" and not service_account_file and not service_account_info:
        raise ConfigError(
            "GOOGLE_APPLICATION_CREDENTIALS or MUSIMACK_GA4_SERVICE_ACCOUNT_JSON is required"
        )

    return Ga4Config(
        auth_method=auth_method,
        property_id=property_id,
        oauth_client_secrets_file=oauth_client_secrets_file,
        oauth_token_file=oauth_token_file,
        service_account_file=service_account_file,
        service_account_info=service_account_info,
    )


def _env_or_profile_value(env_name: str, profile_value: object, *, required: bool) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value.strip()
    text = str(profile_value or "").strip()
    if text:
        return text
    if required:
        raise ConfigError(f"{env_name} is required")
    return None


def _reject_repo_secret_path(path_text: str | None, label: str) -> None:
    if not path_text:
        return
    try:
        Path(path_text).expanduser().resolve(strict=False).relative_to(ROOT.resolve(strict=False))
    except ValueError:
        return
    raise ConfigError(f"{label} must be outside the repo")


def load_database_config(project_id_override: str | None = None) -> DatabaseConfig:
    load_local_operator_config()
    database_url = env_value("MUSIMACK_PORTAL_DATABASE_URL")
    project_id = project_id_override or env_value("MUSIMACK_PORTAL_PROJECT_ID")
    if not project_id:
        raise ConfigError("project id is required")
    return DatabaseConfig(database_url=database_url, project_id=project_id)


def add_date_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format")


def resolve_output_path(path_text: str | None, date_range: DateRange) -> Path:
    if path_text:
        return Path(path_text)
    filename = f"musimack_ga4_{date_range.start.isoformat()}_{date_range.end.isoformat()}.json"
    return Path("exports") / filename
