from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .operator_console import (
    DEFAULT_PROFILE_REGISTRY,
    PROVIDER_LABELS,
    PROVIDER_OUTPUT_FILES,
    SUPPORTED_IMPORTER_PROVIDERS,
    DashboardLabProfile,
    ProfileCapability,
    expected_dashboard_files,
    load_dashboard_lab_profiles,
)
from .profile_local_config import safe_path_label


PROFILE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+$")
SAFE_TEXT_MAX = 140
SECRET_MARKERS = (
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "developer_token",
    "private_key",
    "bearer",
    "password",
    "oauth",
    "token",
)
RAW_MARKERS = ("name,email", "phone", "message", "form payload", "recording", "transcript", "gclid")

PROVIDER_DEFINITIONS = {
    "ga4": {
        "key": "ga4",
        "label": "GA4",
        "status": "enabled",
        "kind": "importer_provider",
        "provider": "ga4",
    },
    "gsc": {
        "key": "gsc",
        "label": "GSC",
        "status": "enabled",
        "kind": "importer_provider",
        "provider": "gsc",
    },
    "local_falcon": {
        "key": "local_falcon",
        "label": "Local Falcon",
        "status": "enabled",
        "kind": "importer_provider",
        "provider": "local_falcon",
    },
    "google_ads_search": {
        "key": "google_ads_search",
        "label": "Google Ads Search",
        "status": "enabled",
        "kind": "paid_provider",
        "provider": "google_ads_search",
        "expected_output_file": "google-ads-summary.json",
        "notes": "Local read-only paid search dashboard output only; no account mutations or portal integration.",
    },
    "callrail": {
        "key": "callrail",
        "label": "CallRail",
        "status": "enabled",
        "kind": "lead_provider",
        "provider": "callrail",
        "expected_output_file": "callrail-summary.json",
        "notes": "Aggregate call tracking dashboard output only; no caller details, recordings, transcripts, or phone numbers.",
    },
    "form_fills": {
        "key": "form_fills",
        "label": "Form Fills",
        "status": "enabled",
        "kind": "lead_provider",
        "provider": "form_fills",
        "expected_output_file": "form-fills-summary.json",
        "notes": "Date-only form-fill dashboard output only; no raw submissions.",
    },
}

CAPABILITY_DEFINITIONS = {
    "local_falcon_ai": {
        "key": "local_falcon_ai",
        "label": "Local Falcon AI Visibility",
        "status": "planned",
        "kind": "dashboard_room",
        "notes": "Planned once source-aware AI visibility output is configured.",
    },
    "google_lsa": {
        "key": "google_lsa",
        "label": "Google LSA",
        "status": "planned",
        "kind": "paid_provider",
    },
    "leads": {
        "key": "leads",
        "label": "Leads",
        "status": "planned",
        "kind": "dashboard_room",
    },
    "content": {
        "key": "content",
        "label": "Content",
        "status": "enabled",
        "kind": "dashboard_room",
    },
    "strategy": {
        "key": "strategy",
        "label": "Strategy",
        "status": "enabled",
        "kind": "dashboard_room",
    },
    "reports": {
        "key": "reports",
        "label": "Reports",
        "status": "enabled",
        "kind": "dashboard_room",
    },
    "support": {
        "key": "support",
        "label": "Support",
        "status": "enabled",
        "kind": "dashboard_room",
    },
    "operator_profile": {
        "key": "operator_profile",
        "label": "Operator Profile",
        "status": "enabled",
        "kind": "operator",
    },
}

DEFAULT_PROVIDERS = ["ga4", "gsc", "local_falcon"]
DEFAULT_CAPABILITIES = ["content", "strategy", "reports", "support", "operator_profile"]


class ProfileRegistryWriteError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileRegistryPreview:
    registry_path: Path
    profile: dict[str, Any]
    expected_files: list[str]
    changes: list[dict[str, str]]
    errors: list[str]
    warnings: list[str]

    @property
    def blocked(self) -> bool:
        return bool(self.errors)

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "registry_path_label": safe_path_label(self.registry_path),
            "profile": self.profile,
            "expected_files": self.expected_files,
            "changes": self.changes,
            "blocked": self.blocked,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def build_profile_registry_draft() -> dict[str, Any]:
    return {
        "draft": {
            "slug": "",
            "display_name": "",
            "domain": "",
            "vertical": "",
            "service_model": "",
            "data_sources": list(DEFAULT_PROVIDERS),
            "capabilities": [
                {"key": key, "status": CAPABILITY_DEFINITIONS[key]["status"]}
                for key in DEFAULT_CAPABILITIES
            ],
        },
        "provider_options": [
            _option_from_definition(PROVIDER_DEFINITIONS[key])
            for key in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills")
        ],
        "capability_options": [
            _option_from_definition(CAPABILITY_DEFINITIONS[key])
            for key in ("content", "strategy", "reports", "support", "operator_profile", "local_falcon_ai", "google_lsa", "leads")
        ],
        "warnings": [
            "This writes tracked safe profile metadata only. Do not enter secrets, OAuth JSON, API keys, customer IDs, raw provider rows, or fixture payloads."
        ],
    }


def preview_profile_registry_update(
    draft: Mapping[str, Any],
    *,
    registry_path: Path = DEFAULT_PROFILE_REGISTRY,
) -> ProfileRegistryPreview:
    registry = _load_registry(registry_path)
    profile, errors = _build_profile(draft, registry)
    expected_files = _expected_files_for_payload(profile) if not errors else []
    changes = [] if errors else [{"action": "create_profile", "profile_slug": profile["slug"]}]
    return ProfileRegistryPreview(
        registry_path=registry_path,
        profile=_safe_profile(profile),
        expected_files=expected_files,
        changes=changes,
        errors=errors,
        warnings=[
            "Preview only. Saving appends one tracked profile shell and does not create local config, fixtures, routes, or provider output."
        ],
    )


def write_profile_registry_update(
    draft: Mapping[str, Any],
    *,
    confirmed: bool,
    registry_path: Path = DEFAULT_PROFILE_REGISTRY,
) -> dict[str, Any]:
    preview = preview_profile_registry_update(draft, registry_path=registry_path)
    if not confirmed:
        raise ProfileRegistryWriteError("saving tracked profile registry requires confirmation")
    if preview.blocked:
        raise ProfileRegistryWriteError("profile registry draft has validation errors")
    registry = _load_registry(registry_path)
    profiles = registry.get("profiles")
    if not isinstance(profiles, list):
        raise ProfileRegistryWriteError("profile registry must contain profiles array")
    profiles.append(preview.profile)
    _write_json_atomic(registry_path, registry)
    load_dashboard_lab_profiles(registry_path)
    response = preview.as_safe_dict()
    response["saved"] = True
    return response


def _load_registry(registry_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileRegistryWriteError("profile registry could not be read safely") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), list):
        raise ProfileRegistryWriteError("profile registry must contain profiles array")
    return payload


def _build_profile(draft: Mapping[str, Any], registry: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(draft, Mapping):
        return {}, ["draft must be a JSON object"]

    unknown_keys = set(draft.keys()) - {"slug", "display_name", "domain", "vertical", "service_model", "data_sources", "capabilities"}
    if unknown_keys:
        errors.append("draft contains fields that are not editable in v1")

    slug = _clean_text(draft.get("slug"))
    display_name = _clean_text(draft.get("display_name"))
    domain = _clean_text(draft.get("domain")).lower().removeprefix("https://").removeprefix("http://").strip("/")
    vertical = _clean_text(draft.get("vertical"))
    service_model = _clean_text(draft.get("service_model"))

    if not PROFILE_SLUG_RE.match(slug):
        errors.append("slug must contain only lowercase letters, numbers, and hyphens")
    existing_slugs = {str(item.get("slug")) for item in registry.get("profiles", []) if isinstance(item, Mapping)}
    if slug in existing_slugs:
        errors.append("slug already exists")
    errors.extend(_validate_safe_metadata("display_name", display_name, required=True))
    errors.extend(_validate_domain(domain))
    errors.extend(_validate_safe_metadata("vertical", vertical, required=True))
    errors.extend(_validate_safe_metadata("service_model", service_model, required=True))

    data_sources = _data_sources(draft.get("data_sources"), errors)
    capabilities = _capabilities(draft.get("capabilities"), data_sources, errors)
    profile = {
        "slug": slug,
        "display_name": display_name,
        "domain": domain,
        "vertical": vertical,
        "service_model": service_model,
        "dashboard_lab_route": f"/lab/{slug}",
        "importer_output_folder": f"exports/local-real/dashboard-lab/{slug}",
        "dashboard_lab_local_fixture_folder": f"../musimack-dashboard-lab/public/local-fixtures/{slug}",
        "dashboard_lab_synthetic_fixture_folder": f"../musimack-dashboard-lab/public/fixtures/{slug}",
        "data_sources": data_sources,
        "capabilities": capabilities,
    }
    return profile, errors


def _data_sources(value: Any, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append("data_sources must be a list")
        return []
    sources: list[str] = []
    for item in value:
        key = str(item).strip()
        if key not in SUPPORTED_IMPORTER_PROVIDERS:
            errors.append("data_sources contains a provider that is not allowed in v1")
            continue
        if key not in sources:
            sources.append(key)
    return sources


def _capabilities(value: Any, data_sources: list[str], errors: list[str]) -> list[dict[str, str]]:
    if value is None:
        value = [{"key": key, "status": CAPABILITY_DEFINITIONS[key]["status"]} for key in DEFAULT_CAPABILITIES]
    if not isinstance(value, list):
        errors.append("capabilities must be a list")
        return []
    capabilities: list[dict[str, str]] = []
    seen = set()
    for provider in data_sources:
        capabilities.append(_copy_definition(PROVIDER_DEFINITIONS[provider], status="enabled"))
        seen.add(provider)
    for item in value:
        if not isinstance(item, Mapping):
            errors.append("capabilities must contain objects")
            continue
        unknown_keys = set(item.keys()) - {"key", "status"}
        if unknown_keys:
            errors.append("capability contains fields that are not editable in v1")
        key = str(item.get("key") or "").strip()
        status = str(item.get("status") or CAPABILITY_DEFINITIONS.get(key, {}).get("status") or "enabled").strip()
        if key in seen:
            continue
        definition = CAPABILITY_DEFINITIONS.get(key)
        if definition is None:
            errors.append("capabilities contains a key that is not allowed in v1")
            continue
        if status not in {"enabled", "planned"}:
            errors.append("capability status must be enabled or planned")
            continue
        capabilities.append(_copy_definition(definition, status=status))
        seen.add(key)
    return capabilities


def _copy_definition(definition: Mapping[str, str], *, status: str) -> dict[str, str]:
    payload = {key: str(value) for key, value in definition.items() if str(value).strip()}
    payload["status"] = status
    return payload


def _expected_files_for_payload(profile: Mapping[str, Any]) -> list[str]:
    capabilities = [
        ProfileCapability(
            key=str(item.get("key") or ""),
            label=str(item.get("label") or PROVIDER_LABELS.get(str(item.get("key") or ""), str(item.get("key") or ""))),
            status=str(item.get("status") or "enabled"),
            kind=str(item.get("kind") or "dashboard_room"),
            provider=str(item.get("provider") or ""),
            expected_output_file=str(item.get("expected_output_file") or PROVIDER_OUTPUT_FILES.get(str(item.get("provider") or ""), "")),
            notes=str(item.get("notes") or ""),
        )
        for item in profile.get("capabilities", [])
        if isinstance(item, Mapping)
    ]
    dashboard_profile = DashboardLabProfile(
        slug=str(profile.get("slug") or ""),
        display_name=str(profile.get("display_name") or ""),
        domain=str(profile.get("domain") or ""),
        vertical=str(profile.get("vertical") or ""),
        service_model=str(profile.get("service_model") or ""),
        dashboard_lab_route=str(profile.get("dashboard_lab_route") or ""),
        importer_output_folder=Path(str(profile.get("importer_output_folder") or "")),
        dashboard_lab_local_fixture_folder=Path(str(profile.get("dashboard_lab_local_fixture_folder") or "")),
        dashboard_lab_synthetic_fixture_folder=Path(str(profile.get("dashboard_lab_synthetic_fixture_folder") or "")),
        data_sources=[str(item) for item in profile.get("data_sources", [])],
        capabilities=capabilities,
    )
    return [item for item in expected_dashboard_files(dashboard_profile) if item != "ga4-snapshot.json"]


def _safe_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    allowed = [
        "slug",
        "display_name",
        "domain",
        "vertical",
        "service_model",
        "dashboard_lab_route",
        "importer_output_folder",
        "dashboard_lab_local_fixture_folder",
        "dashboard_lab_synthetic_fixture_folder",
        "data_sources",
        "capabilities",
    ]
    return {key: profile[key] for key in allowed if key in profile}


def _validate_safe_metadata(field: str, value: str, *, required: bool) -> list[str]:
    errors: list[str] = []
    if required and not value:
        errors.append(f"{field} is required")
        return errors
    if len(value) > SAFE_TEXT_MAX:
        errors.append(f"{field} is too long")
    errors.extend(_reject_secret_like(field, value))
    if any(token in value for token in ("{", "}", "\n", "\r")):
        errors.append(f"{field} must not contain JSON or multiline content")
    return errors


def _validate_domain(value: str) -> list[str]:
    errors = _validate_safe_metadata("domain", value, required=True)
    if value and (not DOMAIN_RE.match(value) or "." not in value):
        errors.append("domain must be a bare domain such as example.com")
    return errors


def _reject_secret_like(field: str, value: str) -> list[str]:
    lowered = value.lower()
    errors: list[str] = []
    if any(marker in lowered for marker in SECRET_MARKERS):
        errors.append(f"{field} looks like secret or credential material")
    if any(marker in lowered for marker in RAW_MARKERS):
        errors.append(f"{field} looks like raw provider/customer data")
    return errors


def _option_from_definition(definition: Mapping[str, str]) -> dict[str, str]:
    return {
        "key": str(definition.get("key") or ""),
        "label": str(definition.get("label") or ""),
        "status": str(definition.get("status") or "enabled"),
        "kind": str(definition.get("kind") or ""),
        "provider": str(definition.get("provider") or ""),
        "expected_output_file": str(definition.get("expected_output_file") or PROVIDER_OUTPUT_FILES.get(str(definition.get("provider") or ""), "")),
    }


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)
