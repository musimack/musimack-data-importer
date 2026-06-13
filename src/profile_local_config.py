from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_PROFILE_CONFIG_DIR = ROOT / "local-profile-configs"
PROFILE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ProfileLocalConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileLocalConfig:
    profile_slug: str
    path: Path
    found: bool
    valid: bool
    providers: dict[str, dict[str, Any]]
    error: str = ""

    @property
    def path_label(self) -> str:
        return safe_path_label(self.path)

    def provider(self, name: str) -> dict[str, Any]:
        return self.providers.get(name, {})

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "profile_slug": self.profile_slug,
            "path_label": self.path_label,
            "found": self.found,
            "valid": self.valid,
            "error": self.error,
            "providers": _safe_providers(self.providers),
        }


def profile_local_config_path(
    profile_slug: str,
    *,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> Path:
    _validate_profile_slug(profile_slug)
    return config_dir / f"{profile_slug}.local.json"


def load_profile_local_config(
    profile_slug: str,
    *,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
    env: Mapping[str, str] | None = None,
) -> ProfileLocalConfig:
    source_env = {} if env is None else env
    path = profile_local_config_path(profile_slug, config_dir=config_dir)
    if not path.exists():
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=False,
            valid=True,
            providers=_empty_provider_states(profile_slug, path),
        )
    if not path.is_file():
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=True,
            valid=False,
            providers=_empty_provider_states(profile_slug, path),
            error="local profile config path is not a file",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=True,
            valid=False,
            providers=_empty_provider_states(profile_slug, path),
            error="local profile config is not valid JSON",
        )
    except OSError:
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=True,
            valid=False,
            providers=_empty_provider_states(profile_slug, path),
            error="local profile config could not be read",
        )

    if not isinstance(payload, dict):
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=True,
            valid=False,
            providers=_empty_provider_states(profile_slug, path),
            error="local profile config must contain a JSON object",
        )
    configured_profile = str(payload.get("profile") or "").strip()
    if configured_profile and configured_profile != profile_slug:
        return ProfileLocalConfig(
            profile_slug=profile_slug,
            path=path,
            found=True,
            valid=False,
            providers=_empty_provider_states(profile_slug, path),
            error="local profile config profile does not match requested slug",
        )

    providers = {
        "ga4": _ga4_state(_provider_payload(payload, "ga4"), source_env),
        "gsc": _gsc_state(_provider_payload(payload, "gsc"), source_env),
        "local_falcon": _local_falcon_state(_provider_payload(payload, "local_falcon"), source_env),
        "google_ads_search": _google_ads_state(_provider_payload(payload, "google_ads_search"), source_env),
        "callrail": _callrail_state(_provider_payload(payload, "callrail"), source_env),
        "form_fills": _form_fills_state(_provider_payload(payload, "form_fills")),
    }
    metadata = _metadata(profile_slug, path, found=True, valid=True, error="")
    for provider_state in providers.values():
        provider_state["_local_profile_config"] = metadata
    return ProfileLocalConfig(
        profile_slug=profile_slug,
        path=path,
        found=True,
        valid=True,
        providers=providers,
    )


def load_profile_provider_config_map(
    profile_slug: str,
    *,
    config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return load_profile_local_config(profile_slug, config_dir=config_dir, env=env).providers


def safe_path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _safe_providers(providers: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    safe = {}
    for provider, state in providers.items():
        safe_state = dict(state)
        if safe_state.get("manifest_path"):
            safe_state["manifest_path"] = safe_state.get("manifest_path_label") or safe_path_label(Path(str(safe_state["manifest_path"])))
        safe[provider] = safe_state
    return safe


def _validate_profile_slug(profile_slug: str) -> None:
    if not PROFILE_SLUG_RE.match(profile_slug):
        raise ProfileLocalConfigError("profile slug must contain only lowercase letters, numbers, and hyphens")


def _provider_payload(payload: dict[str, Any], provider: str) -> dict[str, Any]:
    value = payload.get(provider)
    return value if isinstance(value, dict) else {}


def _empty_provider_states(profile_slug: str, path: Path) -> dict[str, dict[str, Any]]:
    metadata = _metadata(
        profile_slug,
        path,
        found=path.exists(),
        valid=not path.exists(),
        error="" if not path.exists() else "local profile config could not be loaded",
    )
    return {
        provider: {"_local_profile_config": metadata}
        for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills")
    }


def _metadata(profile_slug: str, path: Path, *, found: bool, valid: bool, error: str) -> dict[str, Any]:
    return {
        "profile_slug": profile_slug,
        "present": found,
        "valid": valid,
        "path_label": safe_path_label(path),
        "error": error,
    }


def _ga4_state(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    property_env = _text(config.get("property_id_env"))
    client_env = _text(config.get("oauth_client_secrets_env"))
    token_env = _text(config.get("oauth_token_file_env"))
    property_present = _env_present(env, property_env)
    client_present = _env_present(env, client_env)
    token_present = _env_present(env, token_env)
    client_file_exists = _env_path_exists(env, client_env)
    token_file_exists = _env_path_exists(env, token_env)
    missing = []
    if not property_env:
        missing.append("GA4 property id env var name")
    elif not property_present:
        missing.append(f"{property_env} value")
    if not client_env:
        missing.append("GA4 OAuth client secrets env var name")
    elif not client_present:
        missing.append(f"{client_env} value")
    elif not client_file_exists:
        missing.append(f"{client_env} referenced file")
    if not token_env:
        missing.append("GA4 OAuth token file env var name")
    elif not token_present:
        missing.append(f"{token_env} value")
    elif not token_file_exists:
        missing.append(f"{token_env} referenced file")
    return {
        "property_id_env": property_env,
        "property_id_env_present": property_present,
        "oauth_client_secrets_env": client_env,
        "oauth_client_secrets_env_present": client_present,
        "oauth_client_secrets_file_exists": client_file_exists,
        "oauth_token_file_env": token_env,
        "oauth_token_file_env_present": token_present,
        "oauth_token_file_exists": token_file_exists,
        "property_id": property_present,
        "credentials_configured": client_present and token_present and client_file_exists and token_file_exists,
        "_missing_config_items": missing,
    }


def _gsc_state(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    site_url = _text(config.get("site_url"))
    client_env = _text(config.get("oauth_client_secrets_env"))
    token_env = _text(config.get("oauth_token_file_env"))
    client_present = _env_present(env, client_env)
    token_present = _env_present(env, token_env)
    client_file_exists = _env_path_exists(env, client_env)
    token_file_exists = _env_path_exists(env, token_env)
    missing = []
    if not site_url:
        missing.append("GSC site URL")
    if not client_env:
        missing.append("GSC OAuth client secrets env var name")
    elif not client_present:
        missing.append(f"{client_env} value")
    elif not client_file_exists:
        missing.append(f"{client_env} referenced file")
    if not token_env:
        missing.append("GSC OAuth token file env var name")
    elif not token_present:
        missing.append(f"{token_env} value")
    elif not token_file_exists:
        missing.append(f"{token_env} referenced file")
    return {
        "site_url": bool(site_url),
        "site_url_configured": bool(site_url),
        "gsc_site_url": bool(site_url),
        "oauth_client_secrets_env": client_env,
        "oauth_client_secrets_env_present": client_present,
        "oauth_client_secrets_file_exists": client_file_exists,
        "oauth_token_file_env": token_env,
        "oauth_token_file_env_present": token_present,
        "oauth_token_file_exists": token_file_exists,
        "credentials_configured": client_present and token_present and client_file_exists and token_file_exists,
        "_safe_site_url": site_url,
        "_missing_config_items": missing,
    }


def _local_falcon_state(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    manifest_path = _text(config.get("manifest_path"))
    api_key_env = _text(config.get("api_key_env")) or "LOCAL_FALCON_API_KEY"
    manifest_exists = bool(manifest_path) and Path(manifest_path).exists()
    api_key_present = _env_present(env, api_key_env)
    missing = []
    if not manifest_path:
        missing.append("Local Falcon manifest path")
    elif not manifest_exists:
        missing.append("Local Falcon manifest file")
    if not api_key_env:
        missing.append("Local Falcon API key env var name")
    elif not api_key_present:
        missing.append(f"{api_key_env} value")
    return {
        "manifest": bool(manifest_path),
        "manifest_path": manifest_path,
        "manifest_path_label": safe_path_label(Path(manifest_path)) if manifest_path else "",
        "manifest_exists": manifest_exists,
        "local_falcon_manifest_configured": manifest_exists,
        "api_key_env": api_key_env,
        "api_key_env_present": api_key_present,
        "api_key_present": api_key_present,
        "api_key_configured": api_key_present,
        "_missing_config_items": missing,
    }


def _planned_state(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _text(config.get("status")) or "planned",
        "importer_implemented": False,
        "_missing_config_items": ["future read-only Google Ads Search importer implementation"],
    }


def _google_ads_state(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    customer_env = _text(config.get("customer_id_env"))
    developer_token_env = _text(config.get("developer_token_env"))
    client_env = _text(config.get("oauth_client_secrets_env"))
    token_env = _text(config.get("oauth_token_file_env"))
    login_customer_env = _text(config.get("login_customer_id_env"))
    customer_present = _env_present(env, customer_env)
    developer_token_present = _env_present(env, developer_token_env)
    client_present = _env_present(env, client_env)
    token_present = _env_present(env, token_env)
    client_file_exists = _env_path_exists(env, client_env)
    token_file_exists = _env_path_exists(env, token_env)
    missing = []
    if not customer_env:
        missing.append("Google Ads customer ID env var name")
    elif not customer_present:
        missing.append(f"{customer_env} value")
    if not developer_token_env:
        missing.append("Google Ads developer token env var name")
    elif not developer_token_present:
        missing.append(f"{developer_token_env} value")
    if not client_env:
        missing.append("Google Ads OAuth client secrets env var name")
    elif not client_present:
        missing.append(f"{client_env} value")
    elif not client_file_exists:
        missing.append(f"{client_env} referenced file")
    if not token_env:
        missing.append("Google Ads OAuth token file env var name")
    elif not token_present:
        missing.append(f"{token_env} value")
    elif not token_file_exists:
        missing.append(f"{token_env} referenced file")
    return {
        "status": _text(config.get("status")) or "planned",
        "customer_id_env": customer_env,
        "customer_id_env_present": customer_present,
        "customer_id_configured": customer_present,
        "developer_token_env": developer_token_env,
        "developer_token_env_present": developer_token_present,
        "oauth_client_secrets_env": client_env,
        "oauth_client_secrets_env_present": client_present,
        "oauth_client_secrets_file_exists": client_file_exists,
        "oauth_token_file_env": token_env,
        "oauth_token_file_env_present": token_present,
        "oauth_token_file_exists": token_file_exists,
        "login_customer_id_env": login_customer_env,
        "login_customer_id_env_present": _env_present(env, login_customer_env),
        "credentials_configured": developer_token_present and client_present and token_present and client_file_exists and token_file_exists,
        "importer_implemented": True,
        "_missing_config_items": missing,
    }


def _callrail_state(config: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    filename = _text(config.get("local_input_filename"))
    account_env = _text(config.get("account_id_env"))
    company_env = _text(config.get("company_id_env"))
    missing = []
    if not filename:
        missing.append("CallRail local input filename")
    return {
        "local_input_filename": filename,
        "input_path": bool(filename),
        "input_csv": bool(filename and filename.lower().endswith(".csv")),
        "account_id_env": account_env,
        "account_id_env_present": _env_present(env, account_env),
        "company_id_env": company_env,
        "company_id_env_present": _env_present(env, company_env),
        "_missing_config_items": missing,
    }


def _form_fills_state(config: dict[str, Any]) -> dict[str, Any]:
    filename = _text(config.get("local_input_filename"))
    missing = []
    if not filename:
        missing.append("Form Fills local input filename")
    return {
        "local_input_filename": filename,
        "input_path": bool(filename),
        "input_csv": bool(filename and filename.lower().endswith(".csv")),
        "input_json": bool(filename and filename.lower().endswith(".json")),
        "date_only_policy": "date-only local input; no names, emails, phone numbers, messages, IPs, or payloads",
        "_missing_config_items": missing,
    }


def _env_present(env: Mapping[str, str], name: str) -> bool:
    return bool(name and str(env.get(name) or "").strip())


def _env_path_exists(env: Mapping[str, str], name: str) -> bool:
    if not _env_present(env, name):
        return False
    return Path(str(env.get(name))).exists()


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
