from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .profile_local_config import (
    DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
    ProfileLocalConfigError,
    profile_local_config_path,
    safe_path_label,
)


ENV_VAR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SITE_URL_RE = re.compile(r"^(https?://[^\s{}]+|sc-domain:[A-Za-z0-9.-]+)$")
LOCAL_INPUT_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(csv|json)$")
SECRET_MARKERS = (
    "refresh_token",
    "client_secret",
    "api_key",
    "developer_token",
    "private_key",
    "access_token",
    "bearer",
    "password",
)
RAW_MARKERS = ("name,email", "phone", "message", "form payload", "recording", "transcript")
PII_MARKERS = (
    "caller",
    "call recording",
    "recording url",
    "transcription",
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "utm_",
    "ip_address",
    "user_agent",
)
WARNING_TEXT = (
    "This writes only ignored local config metadata. Do not enter secret values, OAuth JSON, API keys, "
    "customer IDs, phone numbers, raw CSV rows, form payloads, or customer data."
)

FIELD_DEFINITIONS = [
    {
        "provider": "ga4",
        "key": "property_id_env",
        "label": "GA4 property ID env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "ga4",
        "key": "oauth_client_secrets_env",
        "label": "GA4 OAuth client secrets env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "ga4",
        "key": "oauth_token_file_env",
        "label": "GA4 OAuth token file env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "gsc",
        "key": "site_url",
        "label": "GSC site URL",
        "kind": "site_url",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "gsc",
        "key": "oauth_client_secrets_env",
        "label": "GSC OAuth client secrets env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "gsc",
        "key": "oauth_token_file_env",
        "label": "GSC OAuth token file env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "local_falcon",
        "key": "manifest_path",
        "label": "Local Falcon manifest path",
        "kind": "path_reference",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "local_falcon",
        "key": "api_key_env",
        "label": "Local Falcon API key env var",
        "kind": "env_var_name",
        "required": True,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "status",
        "label": "Google Ads Search status",
        "kind": "planned_status",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "customer_id_env",
        "label": "Google Ads customer ID env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "developer_token_env",
        "label": "Google Ads developer token env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "oauth_client_secrets_env",
        "label": "Google Ads OAuth client secrets env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "oauth_token_file_env",
        "label": "Google Ads OAuth token file env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "google_ads_search",
        "key": "login_customer_id_env",
        "label": "Google Ads login customer ID env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "callrail",
        "key": "local_input_filename",
        "label": "CallRail local input filename",
        "kind": "local_input_filename",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "callrail",
        "key": "account_id_env",
        "label": "CallRail account ID env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "callrail",
        "key": "company_id_env",
        "label": "CallRail company ID env var",
        "kind": "env_var_name",
        "required": False,
        "secret_value_allowed": False,
    },
    {
        "provider": "form_fills",
        "key": "local_input_filename",
        "label": "Form Fills local input filename",
        "kind": "local_input_filename",
        "required": False,
        "secret_value_allowed": False,
    },
]

ALLOWED_FIELDS = {(item["provider"], item["key"]): item for item in FIELD_DEFINITIONS}
DEFAULT_DRAFT = {
    "ga4": {},
    "gsc": {},
    "local_falcon": {},
    "google_ads_search": {"status": "planned"},
    "callrail": {},
    "form_fills": {},
}


class ProfileLocalConfigWriteError(ValueError):
    pass


@dataclass(frozen=True)
class LocalConfigWritePreview:
    profile: str
    path: Path
    exists: bool
    normalized_config: dict[str, Any]
    safe_config: dict[str, Any]
    changes: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]

    @property
    def blocked(self) -> bool:
        return bool(self.errors)

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "path_label": safe_path_label(self.path),
            "would_create": not self.exists,
            "would_update": self.exists,
            "normalized_config": self.safe_config,
            "changes": self.changes,
            "blocked": self.blocked,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def build_local_config_draft(
    profile_slug: str,
    *,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> dict[str, Any]:
    path = _safe_target_path(profile_slug, config_dir=config_dir)
    existing = _load_existing_raw_config(profile_slug, path)
    draft = _draft_from_existing(profile_slug, existing)
    return {
        "profile": profile_slug,
        "path_label": safe_path_label(path),
        "exists": path.exists() and path.is_file(),
        "editable": True,
        "draft": _safe_config_for_response(draft),
        "fields": FIELD_DEFINITIONS,
        "warnings": [WARNING_TEXT],
    }


def preview_local_config_update(
    profile_slug: str,
    draft: Mapping[str, Any],
    *,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> LocalConfigWritePreview:
    path = _safe_target_path(profile_slug, config_dir=config_dir)
    existing = _load_existing_raw_config(profile_slug, path)
    base = _draft_from_existing(profile_slug, existing)
    normalized, errors = _normalize_config(profile_slug, draft)
    merged = _merge_config(base, normalized)
    changes = _safe_changes(base, merged)
    return LocalConfigWritePreview(
        profile=profile_slug,
        path=path,
        exists=path.exists() and path.is_file(),
        normalized_config=merged,
        safe_config=_safe_config_for_response(merged),
        changes=changes,
        errors=errors,
        warnings=[WARNING_TEXT],
    )


def write_local_config_update(
    profile_slug: str,
    draft: Mapping[str, Any],
    *,
    confirmed: bool,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> dict[str, Any]:
    preview = preview_local_config_update(profile_slug, draft, config_dir=config_dir)
    if not confirmed:
        raise ProfileLocalConfigWriteError("saving local profile config requires confirmation")
    if preview.blocked:
        raise ProfileLocalConfigWriteError("local profile config draft has validation errors")
    _write_json_atomic(preview.path, preview.normalized_config, config_dir=config_dir)
    response = preview.as_safe_dict()
    response["saved"] = True
    return response


def _safe_target_path(profile_slug: str, *, config_dir: Path) -> Path:
    path = profile_local_config_path(profile_slug, config_dir=config_dir)
    resolved_dir = config_dir.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_dir)
    except ValueError as exc:
        raise ProfileLocalConfigError("local profile config path must stay inside config dir") from exc
    return path


def _load_existing_raw_config(profile_slug: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"profile": profile_slug}
    if not path.is_file():
        raise ProfileLocalConfigWriteError("local profile config path is not a file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileLocalConfigWriteError("local profile config could not be read safely") from exc
    if not isinstance(payload, dict):
        raise ProfileLocalConfigWriteError("local profile config must contain a JSON object")
    configured_profile = str(payload.get("profile") or "").strip()
    if configured_profile and configured_profile != profile_slug:
        raise ProfileLocalConfigWriteError("local profile config profile does not match requested slug")
    return payload


def _draft_from_existing(profile_slug: str, existing: Mapping[str, Any]) -> dict[str, Any]:
    draft: dict[str, Any] = {"profile": profile_slug}
    for provider, defaults in DEFAULT_DRAFT.items():
        source = existing.get(provider)
        provider_payload = dict(source) if isinstance(source, Mapping) else {}
        if defaults:
            provider_payload = {**defaults, **provider_payload}
        draft[provider] = {
            key: str(value).strip()
            for key, value in provider_payload.items()
            if (provider, key) in ALLOWED_FIELDS and str(value).strip()
        }
    if "status" not in draft["google_ads_search"]:
        draft["google_ads_search"]["status"] = "planned"
    return draft


def _normalize_config(profile_slug: str, draft: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    normalized: dict[str, Any] = {"profile": profile_slug}
    if not isinstance(draft, Mapping):
        return normalized, ["draft must be a JSON object"]
    if str(draft.get("profile") or profile_slug).strip() != profile_slug:
        errors.append("draft profile must match selected profile")
    for provider in DEFAULT_DRAFT:
        provider_payload = draft.get(provider)
        if provider_payload is None:
            continue
        if not isinstance(provider_payload, Mapping):
            errors.append(f"{provider} config must be an object")
            continue
        normalized_provider: dict[str, str] = {}
        for key, value in provider_payload.items():
            field = ALLOWED_FIELDS.get((provider, str(key)))
            if field is None:
                errors.append(f"{provider} contains a field that is not editable in v1")
                continue
            text = _clean_text(value)
            if not text:
                continue
            field_errors = _validate_field(field, text)
            if field_errors:
                errors.extend(f"{provider}.{key}: {error}" for error in field_errors)
                continue
            normalized_provider[str(key)] = text
        if normalized_provider:
            normalized[provider] = normalized_provider
    if "google_ads_search" in normalized:
        normalized["google_ads_search"]["status"] = "planned"
    return normalized, errors


def _merge_config(base: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    merged = _draft_from_existing(str(base.get("profile") or update.get("profile") or ""), base)
    for provider in DEFAULT_DRAFT:
        update_provider = update.get(provider)
        if isinstance(update_provider, Mapping):
            current = dict(merged.get(provider) if isinstance(merged.get(provider), Mapping) else {})
            current.update({str(key): str(value) for key, value in update_provider.items()})
            merged[provider] = current
    return merged


def _safe_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for provider in DEFAULT_DRAFT:
        before_provider = before.get(provider) if isinstance(before.get(provider), Mapping) else {}
        after_provider = after.get(provider) if isinstance(after.get(provider), Mapping) else {}
        for key in sorted(set(before_provider.keys()) | set(after_provider.keys())):
            if (provider, key) not in ALLOWED_FIELDS:
                continue
            before_value = str(before_provider.get(key) or "")
            after_value = str(after_provider.get(key) or "")
            if before_value == after_value:
                continue
            changes.append(
                {
                    "provider": provider,
                    "key": key,
                    "action": "set" if after_value else "clear",
                    "safe_value": _safe_value(provider, key, after_value),
                }
            )
    return changes


def _safe_config_for_response(config: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {"profile": str(config.get("profile") or "")}
    for provider in DEFAULT_DRAFT:
        provider_payload = config.get(provider)
        safe_provider: dict[str, str] = {}
        if isinstance(provider_payload, Mapping):
            for key, value in provider_payload.items():
                if (provider, key) in ALLOWED_FIELDS and str(value).strip():
                    safe_provider[str(key)] = _safe_value(provider, str(key), str(value))
        safe[provider] = safe_provider
    if "status" not in safe["google_ads_search"]:
        safe["google_ads_search"]["status"] = "planned"
    return safe


def _validate_field(field: Mapping[str, Any], value: str) -> list[str]:
    errors: list[str] = []
    kind = str(field["kind"])
    if kind == "env_var_name" and not ENV_VAR_RE.match(value):
        errors.append("must be an uppercase environment variable name")
    if kind == "site_url" and not SITE_URL_RE.match(value):
        errors.extend(_reject_secret_like(value))
        errors.append("must be an https URL or sc-domain property")
    if kind == "path_reference":
        errors.extend(_reject_secret_like(value))
        errors.extend(_validate_path_reference(value))
    if kind == "local_input_filename":
        errors.extend(_reject_secret_like(value))
        errors.extend(_validate_local_input_filename(value))
    if kind == "planned_status" and value != "planned":
        errors.extend(_reject_secret_like(value))
        errors.append("must remain planned in v1")
    if kind == "env_var_name" and any(token in value for token in ("{", "}", "\n", "\r")):
        errors.append("must not contain JSON, OAuth payloads, or multiline content")
    return errors


def _validate_path_reference(value: str) -> list[str]:
    errors: list[str] = []
    if "\n" in value or "\r" in value:
        errors.append("must be a single-line path reference")
    path = Path(value)
    if path.is_absolute() or path.drive:
        errors.append("must be a relative ignored path reference")
    if any(part == ".." for part in path.parts):
        errors.append("must not traverse parent directories")
    if "," in value or len(value) > 240:
        errors.append("looks like raw data instead of a path reference")
    return errors


def _validate_local_input_filename(value: str) -> list[str]:
    errors: list[str] = []
    path = Path(value)
    if path.name != value or path.is_absolute() or path.drive:
        errors.append("must be a simple filename under the provider input folder")
    if any(part == ".." for part in path.parts):
        errors.append("must not traverse parent directories")
    if not LOCAL_INPUT_FILENAME_RE.match(value):
        errors.append("must be a .csv or .json filename using letters, numbers, dots, dashes, or underscores")
    if len(value) > 120:
        errors.append("looks too long for a local input filename")
    return errors


def _reject_secret_like(value: str) -> list[str]:
    lowered = value.lower()
    errors: list[str] = []
    if any(marker in lowered for marker in SECRET_MARKERS):
        errors.append("looks like a secret value; use an env var name or path reference instead")
    if any(marker in lowered for marker in RAW_MARKERS):
        errors.append("looks like raw provider/customer data")
    if any(marker in lowered for marker in PII_MARKERS):
        errors.append("looks like raw PII or provider payload metadata")
    if any(token in value for token in ("{", "}", "\n", "\r")):
        errors.append("must not contain JSON, OAuth payloads, or multiline content")
    return errors


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _safe_value(provider: str, key: str, value: str) -> str:
    if not value:
        return ""
    if ALLOWED_FIELDS[(provider, key)]["kind"] in {"path_reference", "local_input_filename"}:
        return safe_path_label(Path(value))
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any], *, config_dir: Path) -> None:
    _safe_target_path(str(payload.get("profile") or ""), config_dir=config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)
