from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .profile_local_config import (
    DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
    load_profile_local_config,
    load_profile_provider_config_map,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_REGISTRY = ROOT / "config" / "dashboard_lab_profiles.json"
BASE_EXPECTED_DASHBOARD_FILES = [
    "client-profile.json",
    "ga4-summary.json",
    "gsc-summary.json",
    "combined-dashboard-summary.json",
    "local-falcon-summary.json",
]
EXPECTED_DASHBOARD_FILES = BASE_EXPECTED_DASHBOARD_FILES
LOCAL_FALCON_MANIFEST_DIR = ROOT / "local-falcon-manifests"
SUPPORTED_IMPORTER_PROVIDERS = {"ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"}
PROVIDER_OUTPUT_FILES = {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "local_falcon": "local-falcon-summary.json",
    "google_ads_search": "google-ads-summary.json",
    "callrail": "callrail-summary.json",
    "form_fills": "form-fills-summary.json",
}
PLANNED_PROVIDER_OUTPUT_FILES = {
    "google_ads_search": "google-ads-search-summary.json",
}
PROVIDER_LABELS = {
    "ga4": "GA4",
    "gsc": "GSC",
    "local_falcon": "Local Falcon",
    "local_falcon_ai": "Local Falcon AI Visibility",
    "google_ads_search": "Google Ads Search",
    "google_lsa": "Google LSA",
    "callrail": "CallRail",
    "form_fills": "Form Fills",
    "leads": "Leads",
    "content": "Content",
    "strategy": "Strategy",
    "reports": "Reports",
    "support": "Support",
    "operator_profile": "Operator Profile",
}
PROVIDER_DASHBOARD_LAB_WRITERS = {
    "ga4": "Ready",
    "gsc": "Ready",
    "local_falcon": "Ready",
    "google_ads_search": "Ready",
    "callrail": "Ready",
    "form_fills": "Ready",
}


class OperatorConsoleError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileCapability:
    key: str
    label: str
    status: str
    kind: str
    provider: str
    expected_output_file: str
    notes: str = ""


@dataclass(frozen=True)
class DashboardLabProfile:
    slug: str
    display_name: str
    domain: str
    vertical: str
    service_model: str
    dashboard_lab_route: str
    importer_output_folder: Path
    dashboard_lab_local_fixture_folder: Path
    dashboard_lab_synthetic_fixture_folder: Path
    data_sources: list[str]
    capabilities: list[ProfileCapability] = field(default_factory=list)


@dataclass(frozen=True)
class OutputFileStatus:
    file: str
    exists: bool
    last_modified: str
    size: str
    schema_version: str
    json_valid: bool | None
    warning: str

    def as_row(self) -> dict[str, str]:
        return {
            "file": self.file,
            "exists": "yes" if self.exists else "no",
            "last_modified": self.last_modified,
            "size": self.size,
            "schema_version": self.schema_version,
            "json_valid": "" if self.json_valid is None else ("yes" if self.json_valid else "no"),
            "warning": self.warning,
        }


@dataclass(frozen=True)
class OutputValidationReport:
    folder: Path
    folder_exists: bool
    files: list[OutputFileStatus]
    missing_files: list[str]
    malformed_json_files: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return self.folder_exists and not self.missing_files and not self.malformed_json_files


@dataclass(frozen=True)
class CopyPlanItem:
    file: str
    source: Path
    destination: Path
    source_exists: bool
    destination_exists: bool
    action: str
    size: str
    last_modified: str

    def as_row(self) -> dict[str, str]:
        return {
            "file": self.file,
            "source_exists": "yes" if self.source_exists else "no",
            "destination": str(self.destination),
            "destination_exists": "yes" if self.destination_exists else "no",
            "action": self.action,
            "size": self.size,
            "last_modified": self.last_modified,
        }


@dataclass(frozen=True)
class CopyResultItem:
    file: str
    status: str
    destination: Path
    size: str
    last_modified: str
    error: str = ""

    def as_row(self) -> dict[str, str]:
        return {
            "file": self.file,
            "status": self.status,
            "destination": str(self.destination),
            "size": self.size,
            "last_modified": self.last_modified,
            "error": self.error,
        }


def load_dashboard_lab_profiles(path: Path | None = None) -> list[DashboardLabProfile]:
    registry_path = path or DEFAULT_PROFILE_REGISTRY
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise OperatorConsoleError("dashboard-lab profile registry must contain a non-empty profiles array")
    loaded = [_profile_from_payload(item) for item in profiles]
    seen = set()
    for profile in loaded:
        if profile.slug in seen:
            raise OperatorConsoleError(f"duplicate dashboard-lab profile slug: {profile.slug}")
        seen.add(profile.slug)
        _validate_safe_fixture_paths(profile)
    return loaded


def profile_by_slug(slug: str, profiles: list[DashboardLabProfile] | None = None) -> DashboardLabProfile:
    profile_list = profiles or load_dashboard_lab_profiles()
    for profile in profile_list:
        if profile.slug == slug:
            return profile
    raise OperatorConsoleError(f"unknown dashboard-lab profile: {slug}")


def provider_readiness(
    profile: DashboardLabProfile,
    env: dict[str, str] | None = None,
    local_config: dict[str, Any] | None = None,
    local_config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> list[dict[str, str]]:
    source = os.environ if env is None else env
    profile_config = (
        load_profile_local_config(profile.slug, config_dir=local_config_dir, env=source)
        if local_config is None
        else None
    )
    config = local_config or (profile_config.providers if profile_config else {})
    rows = []
    metadata = _local_profile_config_metadata(profile, config, profile_config)
    rows.append(
        {
            "provider": "Local profile config",
            "status": "present" if metadata["present"] else "missing",
            "detail": f"{metadata['path_label']}; valid {'yes' if metadata['valid'] else 'no'}",
        }
    )
    if "ga4" in profile.data_sources:
        provider_config = _provider_config(config, "ga4")
        state = _safe_config_state(profile, "ga4", source, provider_config)
        rows.append(
            {
                "provider": "GA4",
                "status": "configured" if state.get("property_id_configured") and state.get("auth_configured") else "missing config",
                "detail": _ga4_detail(source, provider_config),
            }
        )
    if "gsc" in profile.data_sources:
        provider_config = _provider_config(config, "gsc")
        state = _safe_config_state(profile, "gsc", source, provider_config)
        rows.append(
            {
                "provider": "GSC",
                "status": "configured" if (
                    state.get("site_url_configured") and state.get("oauth_configured")
                ) or (
                    not _local_profile_metadata_present(provider_config) and _gsc_configured(source)
                ) else "missing config",
                "detail": _gsc_detail(source, provider_config),
            }
        )
    if "local_falcon" in profile.data_sources:
        manifest = local_falcon_manifest_path(profile)
        provider_config = _provider_config(config, "local_falcon")
        state = _safe_config_state(profile, "local_falcon", source, provider_config)
        manifest_label = provider_config.get("manifest_path_label") or manifest
        api_key_env = provider_config.get("api_key_env") or "LOCAL_FALCON_API_KEY"
        api_key_source = provider_config.get("api_key_readiness_source") or ("env" if state.get("api_key_visible") else "missing")
        api_key_detail = {
            "env": f"API key env {api_key_env} present",
            "vault": "API key configured via encrypted local vault",
            "locked": f"API key env {api_key_env} missing; unlock vault to check saved key",
            "missing": f"API key env {api_key_env} missing",
        }.get(str(api_key_source), f"API key env {api_key_env} missing")
        rows.append(
            {
                "provider": "Local Falcon",
                "status": "configured" if state.get("manifest_exists") and state.get("api_key_visible") else "missing config",
                "detail": f"{api_key_detail}; manifest {manifest_label}",
            }
        )
    rows.append(
        {
            "provider": "Importer output",
            "status": "exists" if profile.importer_output_folder.exists() else "missing",
            "detail": str(profile.importer_output_folder),
        }
    )
    rows.append(
        {
            "provider": "Dashboard-lab local fixture target",
            "status": "exists" if profile.dashboard_lab_local_fixture_folder.exists() else "missing",
            "detail": str(profile.dashboard_lab_local_fixture_folder),
        }
    )
    return rows


def readiness_matrix(
    profile: DashboardLabProfile,
    env: dict[str, str] | None = None,
    local_config: dict[str, Any] | None = None,
    local_config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> list[dict[str, Any]]:
    source = os.environ if env is None else env
    config = local_config or load_profile_provider_config_map(profile.slug, config_dir=local_config_dir, env=source)
    output_files = {item.file: item for item in validate_profile_output(profile).files}
    for capability in _profile_capabilities(profile):
        if capability.expected_output_file and capability.expected_output_file not in output_files:
            filename = capability.expected_output_file
            output_files[filename] = _file_status(profile.importer_output_folder / filename, filename)
    return [
        _readiness_matrix_row(
            profile,
            capability,
            env=source,
            local_config=_provider_config(config, capability.provider or capability.key),
            output_files=output_files,
        )
        for capability in _profile_capabilities(profile)
    ]


def provider_setup_checklist(
    profile: DashboardLabProfile,
    env: dict[str, str] | None = None,
    local_config: dict[str, Any] | None = None,
    local_config_dir: Path = DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
) -> list[dict[str, Any]]:
    source = os.environ if env is None else env
    config = local_config or load_profile_provider_config_map(profile.slug, config_dir=local_config_dir, env=source)
    matrix = readiness_matrix(profile, env=env, local_config=config, local_config_dir=local_config_dir)
    return [
        _setup_checklist_row(
            profile,
            row,
            env=source,
            local_config=_provider_config(config, row["provider_key"]),
        )
        for row in matrix
    ]


def output_folder_status(profile: DashboardLabProfile) -> list[dict[str, str]]:
    return [item.as_row() for item in validate_profile_output(profile).files]


def expected_dashboard_files(profile: DashboardLabProfile) -> list[str]:
    files = list(BASE_EXPECTED_DASHBOARD_FILES)
    for capability in _profile_capabilities(profile):
        if capability.status != "enabled" or not capability.expected_output_file:
            continue
        if capability.expected_output_file not in files:
            files.append(capability.expected_output_file)
    return files


def validate_profile_output(profile: DashboardLabProfile) -> OutputValidationReport:
    folder = profile.importer_output_folder
    folder_exists = folder.exists() and folder.is_dir()
    files = [_file_status(folder / filename, filename) for filename in expected_dashboard_files(profile)]
    missing = [item.file for item in files if not item.exists]
    malformed = [item.file for item in files if item.exists and item.json_valid is False]
    warnings = []
    if not folder.exists():
        warnings.append("output folder is missing")
    elif not folder.is_dir():
        warnings.append("output path exists but is not a folder")
    if missing:
        warnings.append(f"missing expected file(s): {', '.join(missing)}")
    if malformed:
        warnings.append(f"malformed JSON file(s): {', '.join(malformed)}")
    return OutputValidationReport(
        folder=folder,
        folder_exists=folder_exists,
        files=files,
        missing_files=missing,
        malformed_json_files=malformed,
        warnings=warnings,
    )


def command_guidance(profile: DashboardLabProfile) -> list[dict[str, str]]:
    commands = []
    if "ga4" in profile.data_sources:
        commands.append(
            {
                "provider": "GA4",
                "command": "\n".join(
                    [
                        '$env:MUSIMACK_GA4_PROPERTY_ID="<profile GA4 property id from ignored local config>"',
                        f'python scripts/pull_ga4_traffic_overview.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/validate_ga4_snapshot.py --file "{profile.importer_output_folder / "ga4-snapshot.json"}"',
                        f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --snapshot "{profile.importer_output_folder / "ga4-snapshot.json"}" --real-output',
                        f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --real-output --validate-only',
                    ]
                ),
            }
        )
    if "gsc" in profile.data_sources:
        gsc_site_url = _gsc_site_url_hint(profile)
        commands.append(
            {
                "provider": "GSC",
                "command": "\n".join(
                    [
                        f'python scripts/fetch_gsc_api.py --profile {profile.slug} --site-url {gsc_site_url} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/fetch_gsc_api.py --profile {profile.slug} --real-output --validate-only',
                    ]
                ),
            }
        )
    if "local_falcon" in profile.data_sources:
        manifest = local_falcon_manifest_path(profile)
        commands.append(
            {
                "provider": "Local Falcon",
                "command": "\n".join(
                    [
                        f"# Real manifests stay ignored under local-falcon-manifests/. Expected: {manifest}",
                        f'python scripts/fetch_local_falcon_api.py --profile {profile.slug} --transport live --execute --write',
                        f'python scripts/validate_local_falcon_summary.py --file "{profile.importer_output_folder / "local-falcon-summary.json"}"',
                    ]
                ),
            }
        )
    if "google_ads_search" in profile.data_sources:
        commands.append(
            {
                "provider": "Google Ads Search",
                "command": "\n".join(
                    [
                        f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --dry-run",
                        f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --real-output",
                        f'python scripts/validate_google_ads_summary.py --input "{profile.importer_output_folder / "google-ads-summary.json"}"',
                    ]
                ),
            }
        )
    if "callrail" in profile.data_sources:
        commands.append(
            {
                "provider": "CallRail",
                "command": "\n".join(
                    [
                        f'python scripts/diagnose_callrail_export_shape.py --profile {profile.slug} --input "inputs/local-real/callrail/{profile.slug}/calls.csv"',
                        f'python scripts/import_callrail_export.py --profile {profile.slug} --input "inputs/local-real/callrail/{profile.slug}/calls.csv" --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/validate_callrail_summary.py --input "{profile.importer_output_folder / "callrail-summary.json"}"',
                    ]
                ),
            }
        )
    commands.append(
        {
            "provider": "Profile folder validation",
            "command": f'python scripts/build_dashboard_lab_fixture.py --profile {profile.slug} --validate-only --export-folder --out "{profile.importer_output_folder}"',
        }
    )
    return commands


def _gsc_site_url_hint(profile: DashboardLabProfile) -> str:
    if profile.slug == "inn-at-spanish-head":
        return "sc-domain:spanishhead.com"

    return f"https://{profile.domain}/"


def guarded_import_sequence(profile: DashboardLabProfile) -> dict[str, Any]:
    output = profile.importer_output_folder
    local_fixture = profile.dashboard_lab_local_fixture_folder
    manifest = local_falcon_manifest_path(profile)
    gsc_site_url = _gsc_site_url_hint(profile)
    provider_steps = []
    if "ga4" in profile.data_sources:
        provider_steps.append(
            {
                "provider": "ga4",
                "label": "GA4",
                "phase": "operator_approved_live_fetch",
                "requires_explicit_approval": True,
                "writes_real_output": True,
                "expected_output_file": "ga4-summary.json",
                "output_path": str(output / "ga4-summary.json"),
                "command": "\n".join(
                    [
                        f'python scripts/pull_ga4_traffic_overview.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/validate_ga4_snapshot.py --file "{output / "ga4-snapshot.json"}"',
                        f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --snapshot "{output / "ga4-snapshot.json"}" --real-output',
                        f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --real-output --validate-only',
                    ]
                ),
                "approval_prompt": "Operator confirms the Spanish Head GA4 property id and local OAuth files are configured outside git.",
                "guardrails": [
                    "uses a completed reporting date range",
                    "writes only sanitized ga4_snapshot.v1 plus ga4-summary.json",
                    "keeps property ids, OAuth files, tokens, and credential paths out of output",
                ],
            }
        )
    if "gsc" in profile.data_sources:
        provider_steps.append(
            {
                "provider": "gsc",
                "label": "GSC",
                "phase": "operator_approved_live_fetch",
                "requires_explicit_approval": True,
                "writes_real_output": True,
                "expected_output_file": "gsc-summary.json",
                "output_path": str(output / "gsc-summary.json"),
                "command": "\n".join(
                    [
                        f'python scripts/fetch_gsc_api.py --profile {profile.slug} --site-url {gsc_site_url} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/fetch_gsc_api.py --profile {profile.slug} --real-output --validate-only',
                    ]
                ),
                "approval_prompt": f"Operator confirms exact Search Console property access for {gsc_site_url} and local GSC OAuth files are configured outside git.",
                "guardrails": [
                    "uses Search Console read-only scope",
                    "writes to --real-output under exports/local-real",
                    "does not print OAuth token values, client secrets, or credential paths",
                ],
            }
        )
    if "local_falcon" in profile.data_sources:
        provider_steps.append(
            {
                "provider": "local_falcon",
                "label": "Local Falcon",
                "phase": "operator_approved_live_fetch",
                "requires_explicit_approval": True,
                "writes_real_output": True,
                "expected_output_file": "local-falcon-summary.json",
                "output_path": str(output / "local-falcon-summary.json"),
                "command": "\n".join(
                    [
                        f'# Real report ids stay in ignored manifest: "{manifest}"',
                        f'python scripts/fetch_local_falcon_api.py --profile {profile.slug} --transport live',
                        f'python scripts/fetch_local_falcon_api.py --profile {profile.slug} --transport live --execute --write',
                        f'python scripts/validate_local_falcon_summary.py --file "{output / "local-falcon-summary.json"}"',
                    ]
                ),
                "approval_prompt": "Operator confirms the ignored manifest contains only existing report IDs and LOCAL_FALCON_API_KEY is available without printing it.",
                "guardrails": [
                    "live preflight without --execute makes no network request",
                    "live execution requires --transport live --execute --write",
                    "retrieves existing reports only; On-Demand scans and provider mutation remain disabled",
                    "real report ids stay in ignored local-falcon-manifests",
                ],
            }
        )
    if "google_ads_search" in profile.data_sources:
        provider_steps.append(
            {
                "provider": "google_ads_search",
                "label": "Google Ads Search",
                "phase": "operator_approved_live_fetch",
                "requires_explicit_approval": True,
                "writes_real_output": True,
                "expected_output_file": "google-ads-summary.json",
                "output_path": str(output / "google-ads-summary.json"),
                "command": "\n".join(
                    [
                        f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --dry-run",
                        f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --real-output",
                        f'python scripts/validate_google_ads_summary.py --input "{output / "google-ads-summary.json"}"',
                    ]
                ),
                "approval_prompt": "Operator confirms ignored Google Ads customer/config values are available and the read-only local exporter is approved for this profile.",
                "guardrails": [
                    "dry-run writes no files",
                    "non-dry-run requires --real-output and local read-only credential readiness",
                    "writes only aggregate google-ads-summary.json under exports/local-real",
                    "does not mutate campaigns, budgets, bids, keywords, ads, settings, portal data, or dashboard-lab source",
                ],
            }
        )
    if "callrail" in profile.data_sources:
        provider_steps.append(
            {
                "provider": "callrail",
                "label": "CallRail",
                "phase": "operator_approved_local_import",
                "requires_explicit_approval": True,
                "writes_real_output": True,
                "expected_output_file": "callrail-summary.json",
                "output_path": str(output / "callrail-summary.json"),
                "command": "\n".join(
                    [
                        f'python scripts/diagnose_callrail_export_shape.py --profile {profile.slug} --input "inputs/local-real/callrail/{profile.slug}/calls.csv"',
                        f'python scripts/import_callrail_export.py --profile {profile.slug} --input "inputs/local-real/callrail/{profile.slug}/calls.csv" --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                        f'python scripts/validate_callrail_summary.py --input "{output / "callrail-summary.json"}"',
                    ]
                ),
                "approval_prompt": "Operator confirms the CallRail CSV is local, ignored, and approved for aggregate dashboard-lab import.",
                "guardrails": [
                    "reads ignored local CSV exports only",
                    "writes aggregate callrail-summary.json under exports/local-real",
                    "does not output caller names, phone numbers, recordings, transcripts, notes, or raw call rows",
                    "does not call live CallRail APIs or mutate provider/portal data",
                ],
            }
        )
    planned_steps = [
        {
            "provider": item.provider or item.key,
            "label": item.label,
            "phase": "planned_only",
            "requires_explicit_approval": True,
            "writes_real_output": False,
            "expected_output_file": item.expected_output_file,
            "output_path": str(output / item.expected_output_file) if item.expected_output_file else "",
            "command": "",
            "approval_prompt": "No live importer exists for this planned capability.",
            "guardrails": [
                "do not create fake real output",
                "do not mark this capability active until a future importer milestone exists",
            ],
        }
        for item in _profile_capabilities(profile)
        if item.status == "planned"
    ]
    return {
        "profile_slug": profile.slug,
        "domain": profile.domain,
        "local_real_output_folder": str(output),
        "dashboard_lab_local_fixture_folder": str(local_fixture),
        "summary": "Plan, approve, fetch locally, validate, then copy only to ignored dashboard-lab local fixtures.",
        "phases": [
            {
                "id": "preflight",
                "label": "Read-only preflight",
                "requires_explicit_approval": False,
                "network_allowed": False,
                "writes_real_output": False,
                "commands": [
                    f"python scripts/build_dashboard_lab_fixture.py --profile {profile.slug}",
                    f'python scripts/build_dashboard_lab_fixture.py --profile {profile.slug} --validate-only --export-folder --out "{output}"',
                ],
            },
            {
                "id": "approved_provider_fetches",
                "label": "Operator-approved provider fetches",
                "requires_explicit_approval": True,
                "network_allowed": True,
                "writes_real_output": True,
                "providers": provider_steps,
            },
            {
                "id": "validation_only",
                "label": "Validation-only checks",
                "requires_explicit_approval": False,
                "network_allowed": False,
                "writes_real_output": False,
                "commands": [
                    f'python scripts/build_dashboard_lab_fixture.py --profile {profile.slug} --validate-only --export-folder --out "{output}"'
                ],
            },
            {
                "id": "dashboard_lab_local_copy",
                "label": "Copy for local dashboard-lab QA",
                "requires_explicit_approval": True,
                "network_allowed": False,
                "writes_real_output": False,
                "source_folder": str(output),
                "destination_folder": str(local_fixture),
                "guardrails": [
                    "copy only expected dashboard JSON files",
                    "destination must be public/local-fixtures",
                    "destination must not be committed public/fixtures",
                ],
            },
            {
                "id": "planned_capabilities",
                "label": "Planned capabilities",
                "requires_explicit_approval": True,
                "network_allowed": False,
                "writes_real_output": False,
                "providers": planned_steps,
            },
        ],
        "global_guardrails": [
            "do not connect to staging or production",
            "do not mutate the portal database",
            "do not print credential values, token values, API keys, Authorization headers, client secrets, or raw credential JSON",
            "do not copy real output to committed public/fixtures without explicit approval",
            "do not copy Aluma output into this profile",
        ],
    }


def copy_guidance(profile: DashboardLabProfile) -> str:
    source = profile.importer_output_folder
    destination = profile.dashboard_lab_local_fixture_folder
    lines = [
        f'New-Item -ItemType Directory -Force "{destination}" | Out-Null',
    ]
    for filename in expected_dashboard_files(profile):
        lines.append(f'Copy-Item "{source / filename}" "{destination / filename}" -Force')
    return "\n".join(lines)


def copy_dry_run(profile: DashboardLabProfile) -> list[CopyPlanItem]:
    _validate_copy_paths(profile)
    plan = []
    for filename in expected_dashboard_files(profile):
        source = profile.importer_output_folder / filename
        destination = profile.dashboard_lab_local_fixture_folder / filename
        source_exists = source.exists() and source.is_file()
        destination_exists = destination.exists()
        action = "skip missing"
        if source_exists and destination_exists:
            action = "overwrite"
        elif source_exists:
            action = "copy"
        plan.append(
            CopyPlanItem(
                file=filename,
                source=source,
                destination=destination,
                source_exists=source_exists,
                destination_exists=destination_exists,
                action=action,
                size=_file_size(source),
                last_modified=_modified_time(source),
            )
        )
    return plan


def copy_local_real_to_dashboard_lab(profile: DashboardLabProfile) -> list[CopyResultItem]:
    _validate_copy_paths(profile)
    profile.dashboard_lab_local_fixture_folder.mkdir(parents=True, exist_ok=True)
    results = []
    for item in copy_dry_run(profile):
        if not item.source_exists:
            results.append(
                CopyResultItem(
                    file=item.file,
                    status="skipped missing source",
                    destination=item.destination,
                    size="",
                    last_modified="",
                )
            )
            continue
        try:
            shutil.copy2(item.source, item.destination)
            results.append(
                CopyResultItem(
                    file=item.file,
                    status="copied" if item.action == "copy" else "overwritten",
                    destination=item.destination,
                    size=_file_size(item.destination),
                    last_modified=_modified_time(item.destination),
                )
            )
        except OSError as exc:
            results.append(
                CopyResultItem(
                    file=item.file,
                    status="failed",
                    destination=item.destination,
                    size="",
                    last_modified="",
                    error=type(exc).__name__,
                )
            )
    return results


def local_falcon_manifest_path(profile: DashboardLabProfile) -> Path:
    return LOCAL_FALCON_MANIFEST_DIR / f"{profile.slug}.json"


def _profile_capabilities(profile: DashboardLabProfile) -> list[ProfileCapability]:
    if profile.capabilities:
        return profile.capabilities
    base = [
        ProfileCapability(
            key=provider,
            label=PROVIDER_LABELS.get(provider, provider),
            status="enabled",
            kind="importer_provider",
            provider=provider,
            expected_output_file=PROVIDER_OUTPUT_FILES.get(provider, ""),
        )
        for provider in profile.data_sources
    ]
    base.extend(
        [
            ProfileCapability("content", "Content", "enabled", "dashboard_room", "", "", ""),
            ProfileCapability("strategy", "Strategy", "enabled", "dashboard_room", "", "", ""),
            ProfileCapability("reports", "Reports", "enabled", "dashboard_room", "", "", ""),
            ProfileCapability("support", "Support", "enabled", "dashboard_room", "", "", ""),
            ProfileCapability("operator_profile", "Operator Profile", "enabled", "operator", "", "", ""),
        ]
    )
    return base


def _readiness_matrix_row(
    profile: DashboardLabProfile,
    capability: ProfileCapability,
    *,
    env: os._Environ[str] | dict[str, str],
    local_config: dict[str, Any],
    output_files: dict[str, OutputFileStatus],
) -> dict[str, Any]:
    supported = capability.provider in SUPPORTED_IMPORTER_PROVIDERS
    enabled = capability.status == "enabled"
    output_file = capability.expected_output_file
    output_status = output_files.get(output_file) if output_file else None
    output_exists = bool(output_status and output_status.exists)
    live_fetch = _live_fetch_readiness(profile, capability.provider, env, local_config) if supported and enabled else {
        "status": "Not available yet" if capability.status == "planned" else "Unsupported in console",
        "ready": False,
        "missing": [],
    }
    if capability.status == "planned":
        local_output_status = "Output exists (planned provider)" if output_exists else "Planned provider"
        validate_status = "Not available yet"
        copy_status = "Not available yet"
        status_label = "Planned, not enabled"
        severity = "info"
    elif not supported and capability.kind != "importer_provider":
        local_output_status = "No provider output expected"
        validate_status = "Not available"
        copy_status = "Not available"
        status_label = "Capability enabled"
        severity = "info"
    elif not supported:
        local_output_status = "Unsupported in console"
        validate_status = "Not available yet"
        copy_status = "Not available yet"
        status_label = "Unsupported in console"
        severity = "warning"
    else:
        local_output_status = "Output exists" if output_exists else "No local output yet"
        validate_status = "Ready" if output_exists else "Blocked until output exists"
        copy_status = "Ready" if output_exists else "Blocked until output exists"
        if output_exists:
            status_label = "Ready to copy"
            severity = "ok"
        elif live_fetch["ready"]:
            status_label = "Ready after local export is created"
            severity = "warning"
        else:
            status_label = "Live fetch needs config"
            severity = "warning"
    return {
        "provider_key": capability.provider or capability.key,
        "provider_label": capability.label,
        "capability_key": capability.key,
        "capability_kind": capability.kind,
        "capability_status": capability.status,
        "supported_in_console": supported,
        "enabled": enabled,
        "expected_output_file": output_file,
        "output_exists": output_exists,
        "output_schema": output_status.schema_version if output_status else "",
        "output_size": output_status.size if output_status else "",
        "last_modified": output_status.last_modified if output_status else "",
        "local_output_status": local_output_status,
        "live_fetch_status": live_fetch["status"],
        "dashboard_lab_writer_status": PROVIDER_DASHBOARD_LAB_WRITERS.get(capability.provider, "Not available"),
        "missing_config_details": live_fetch["missing"],
        "validate_readiness": validate_status,
        "dashboard_copy_readiness": copy_status,
        "status_label": status_label,
        "status_severity": severity,
        "notes": capability.notes,
    }


def _live_fetch_readiness(
    profile: DashboardLabProfile,
    provider: str,
    env: os._Environ[str] | dict[str, str],
    local_config: dict[str, Any],
) -> dict[str, Any]:
    missing = []
    ready = False
    if provider == "ga4":
        property_present = _present(env.get("MUSIMACK_GA4_PROPERTY_ID")) or _any_present(
            local_config,
            ("property_id", "ga4_property_id", "property_id_env_present"),
        )
        auth_present = (
            _present(env.get("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"))
            and _present(env.get("MUSIMACK_GA4_OAUTH_TOKEN_FILE"))
        ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
        missing = _missing_config_items(local_config)
        if not missing:
            if not property_present:
                missing.append("GA4 property id")
            if not auth_present:
                missing.append("GA4 local OAuth/client credentials")
        ready = property_present and auth_present
    elif provider == "gsc":
        site_present = _present(env.get("MUSIMACK_GSC_SITE_URL")) or _any_present(
            local_config,
            ("site_url", "gsc_site_url", "site_url_configured"),
        )
        auth_present = (
            _present(env.get("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS"))
            and _present(env.get("MUSIMACK_GSC_OAUTH_TOKEN_FILE"))
        ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
        missing = _missing_config_items(local_config)
        if not missing:
            if not site_present:
                missing.append("GSC site URL")
            if not auth_present:
                missing.append("GSC local OAuth/client credentials")
        ready = site_present and auth_present
    elif provider == "local_falcon":
        manifest_present = _local_falcon_manifest_configured(profile, local_config)
        credential_present = _present(env.get("LOCAL_FALCON_API_KEY")) or _any_present(
            local_config,
            ("api_key_env_present", "api_key_present", "api_key_configured"),
        )
        missing = _missing_config_items(local_config)
        if not missing:
            if not manifest_present:
                missing.append("ignored Local Falcon manifest")
            if not credential_present:
                missing.append("LOCAL_FALCON_API_KEY")
        ready = manifest_present and credential_present
    elif provider == "google_ads_search":
        customer_present = _present(env.get("MUSIMACK_GOOGLE_ADS_CUSTOMER_ID")) or _any_present(
            local_config,
            ("customer_id", "google_ads_customer_id", "customer_id_configured"),
        )
        auth_present = _any_present(
            local_config,
            ("oauth_client_secrets", "oauth_token_file", "credentials_configured"),
        )
        missing = _missing_config_items(local_config)
        if not missing:
            if not customer_present:
                missing.append("Google Ads customer id")
            if not auth_present:
                missing.append("Google Ads local OAuth/client credentials")
        ready = customer_present and auth_present
    elif provider == "callrail":
        input_present = _any_present(
            local_config,
            ("input_csv", "calls_csv", "source_csv", "callrail_export_csv", "input_path"),
        )
        missing = _missing_config_items(local_config)
        if not missing and not input_present:
            missing.append("ignored CallRail calls CSV")
        ready = input_present
    elif provider == "form_fills":
        input_present = _any_present(
            local_config,
            ("input_csv", "forms_csv", "form_fills_csv", "source_csv", "input_path"),
        )
        missing = _missing_config_items(local_config)
        if not missing and not input_present:
            missing.append("ignored date-only form fills CSV or JSON")
        ready = input_present
    return {
        "status": "Ready" if ready else "Local import needs config" if provider in {"callrail", "form_fills"} else "Live fetch needs config",
        "ready": ready,
        "missing": missing,
    }


def _setup_checklist_row(
    profile: DashboardLabProfile,
    matrix_row: dict[str, Any],
    *,
    env: os._Environ[str] | dict[str, str],
    local_config: dict[str, Any],
) -> dict[str, Any]:
    provider = matrix_row["provider_key"]
    config_state = _safe_config_state(profile, provider, env, local_config)
    config_metadata = _local_profile_config_metadata(profile, {provider: local_config}, None, provider_config=local_config)
    required_items = _required_config_items(provider)
    status = _setup_status(matrix_row)
    missing_config_details = matrix_row["missing_config_details"] or [
        item for item in required_items if not matrix_row["output_exists"]
    ]
    return {
        "provider_key": provider,
        "provider_label": matrix_row["provider_label"],
        "profile_slug": profile.slug,
        "domain": profile.domain,
        "expected_output_file": matrix_row["expected_output_file"],
        "output_exists": matrix_row["output_exists"],
        "local_output_state": matrix_row["local_output_status"],
        "dashboard_lab_writer_status": matrix_row["dashboard_lab_writer_status"],
        "credential_source": _credential_source_label(provider, local_config, config_state),
        "required_config_items": required_items,
        "local_config_file_present": config_metadata["present"],
        "local_config_path_label": config_metadata["path_label"],
        "local_config_valid": config_metadata["valid"],
        "local_config_error": config_metadata["error"],
        "config_state": config_state,
        "config_visible": False if matrix_row["capability_status"] == "planned" else any(
            bool(value) for key, value in config_state.items() if key != "ai_visibility_capability_present"
        ),
        "missing_config_details": missing_config_details,
        "safe_next_action": _safe_next_action(matrix_row, config_state),
        "blocked_reason": _blocked_reason(matrix_row, required_items),
        "suggested_command": _suggested_command(profile, provider, matrix_row),
        "status": status,
        "severity": matrix_row["status_severity"],
        "capability_status": matrix_row["capability_status"],
        "supported_in_console": matrix_row["supported_in_console"],
        "validation_ready": matrix_row["validate_readiness"],
        "dashboard_copy_ready": matrix_row["dashboard_copy_readiness"],
        "validate_readiness": matrix_row["validate_readiness"],
        "dashboard_copy_readiness": matrix_row["dashboard_copy_readiness"],
    }


def _safe_config_state(
    profile: DashboardLabProfile,
    provider: str,
    env: os._Environ[str] | dict[str, str],
    local_config: dict[str, Any],
) -> dict[str, bool]:
    if provider == "ga4":
        state = {
            "property_id_configured": _present(env.get("MUSIMACK_GA4_PROPERTY_ID")) or _any_present(
                local_config,
                ("property_id", "ga4_property_id", "property_id_env_present"),
            ),
            "auth_configured": (
                _present(env.get("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"))
                and _present(env.get("MUSIMACK_GA4_OAUTH_TOKEN_FILE"))
            ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured")),
        }
        if _local_profile_metadata_present(local_config):
            state["oauth_client_file_exists"] = bool(local_config.get("oauth_client_secrets_file_exists", False))
            state["oauth_token_file_exists"] = bool(local_config.get("oauth_token_file_exists", False))
        return state
    if provider == "gsc":
        state = {
            "site_url_configured": _present(env.get("MUSIMACK_GSC_SITE_URL")) or _any_present(
                local_config,
                ("site_url", "gsc_site_url", "site_url_configured"),
            ),
            "oauth_configured": (
                _present(env.get("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS"))
                and _present(env.get("MUSIMACK_GSC_OAUTH_TOKEN_FILE"))
            ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured")),
        }
        if _local_profile_metadata_present(local_config):
            state["oauth_client_file_exists"] = bool(local_config.get("oauth_client_secrets_file_exists", False))
            state["oauth_token_file_exists"] = bool(local_config.get("oauth_token_file_exists", False))
        return state
    if provider == "local_falcon":
        state = {
            "manifest_exists": _local_falcon_manifest_configured(profile, local_config),
            "api_key_visible": _present(env.get("LOCAL_FALCON_API_KEY")) or _any_present(
                local_config,
                ("api_key_env_present", "api_key_present", "api_key_configured"),
            ),
            "ai_visibility_capability_present": any(
                item.key == "local_falcon_ai" and item.status in {"enabled", "planned"}
                for item in _profile_capabilities(profile)
            ),
        }
        if "api_key_env_present" in local_config:
            state["api_key_env_present"] = bool(local_config.get("api_key_env_present"))
        if "api_key_vault_configured" in local_config:
            state["api_key_vault_configured"] = bool(local_config.get("api_key_vault_configured"))
        if "api_key_vault_locked" in local_config:
            state["api_key_vault_locked"] = bool(local_config.get("api_key_vault_locked"))
        return state
    if provider == "google_ads_search":
        customer_configured = _present(env.get("MUSIMACK_GOOGLE_ADS_CUSTOMER_ID")) or _any_present(
            local_config,
            ("customer_id", "google_ads_customer_id", "customer_id_env_present", "customer_id_configured"),
        )
        developer_configured = _present(env.get("GOOGLE_ADS_DEVELOPER_TOKEN")) or _any_present(
            local_config,
            ("developer_token_env_present",),
        )
        oauth_configured = (
            _present(env.get("GOOGLE_ADS_OAUTH_CLIENT_SECRETS"))
            and _present(env.get("GOOGLE_ADS_OAUTH_TOKEN_FILE"))
        ) or _any_present(
            local_config,
            (
                "oauth_client_secrets",
                "oauth_token_file",
                "credentials_configured",
                "oauth_client_secrets_env_present",
                "oauth_token_file_env_present",
            ),
        )
        return {
            "customer_id_configured": customer_configured,
            "developer_token_configured": developer_configured,
            "oauth_configured": oauth_configured,
            "importer_implemented": True,
        }
    if provider == "callrail":
        return {
            "ignored_calls_csv_configured": _any_present(
                local_config,
                ("input_csv", "calls_csv", "source_csv", "callrail_export_csv", "input_path", "local_input_filename"),
            ),
            "aggregate_importer_available": True,
        }
    if provider == "form_fills":
        return {
            "date_only_input_configured": _any_present(
                local_config,
                ("input_csv", "input_json", "forms_csv", "form_fills_csv", "source_csv", "input_path", "local_input_filename"),
            ),
            "date_only_importer_available": True,
        }
    return {}


def _required_config_items(provider: str) -> list[str]:
    if provider == "ga4":
        return ["GA4 property id", "GA4 local OAuth/client credentials"]
    if provider == "gsc":
        return ["GSC site URL", "GSC local OAuth/client credentials"]
    if provider == "local_falcon":
        return ["ignored Local Falcon manifest", "LOCAL_FALCON_API_KEY visible to current process"]
    if provider == "google_ads_search":
        return [
            "Google Ads customer id in ignored local config",
            "Google Ads OAuth/client credentials",
            "read-only Google Ads Search exporter available locally",
        ]
    if provider == "callrail":
        return ["ignored local CallRail calls CSV export", "aggregate CallRail importer available locally"]
    if provider == "form_fills":
        return ["ignored local date-only form fills CSV or JSON", "date-only Form Fills importer available locally"]
    return []


def _setup_status(matrix_row: dict[str, Any]) -> str:
    if matrix_row["capability_status"] == "planned":
        return "planned"
    if not matrix_row["supported_in_console"]:
        return "capability"
    if matrix_row["local_output_status"] == "Output exists" and matrix_row["live_fetch_status"] == "Ready":
        return "ready"
    if matrix_row["local_output_status"] == "Output exists":
        return "output_available"
    if matrix_row["live_fetch_status"] == "Ready":
        return "ready_to_fetch"
    return "needs_config"


def _safe_next_action(matrix_row: dict[str, Any], config_state: dict[str, bool]) -> str:
    if matrix_row["capability_status"] == "planned":
        if matrix_row["provider_key"] == "google_ads_search":
            return "Google Ads Search is still planned for this profile; do not create fake output or activate it without approval."
        return "Future provider integration; no active importer action yet."
    if not matrix_row["supported_in_console"]:
        return "Use this capability in planning only; no provider setup is required in the importer console."
    if matrix_row["provider_key"] == "ga4" and matrix_row["local_output_status"] != "Output exists":
        if matrix_row["live_fetch_status"] == "Ready":
            return "GA4 writer ready; run the local snapshot export, then write ga4-summary.json for dashboard lab."
        return "GA4 writer ready; add missing local property/auth config before snapshot export."
    if matrix_row["local_output_status"] == "Output exists" and matrix_row["live_fetch_status"] == "Ready":
        return "Refresh provider output if needed, then validate or copy to dashboard lab."
    if matrix_row["local_output_status"] == "Output exists":
        return "Validate existing local output or copy to dashboard lab; add config before live refresh."
    if matrix_row["live_fetch_status"] == "Ready":
        return "Run the local fetch command to create the missing local output."
    missing = [key for key, present in config_state.items() if not present and key != "ai_visibility_capability_present"]
    if missing:
        return "Add missing local provider config, then refresh this checklist."
    return "Create local output for this provider when operator-approved."


def _credential_source_label(provider: str, local_config: dict[str, Any], config_state: dict[str, bool]) -> str:
    if provider != "local_falcon":
        return ""
    source = str(local_config.get("api_key_readiness_source") or "")
    if source == "env" or config_state.get("api_key_env_present"):
        return "Configured via env var"
    if source == "vault" or config_state.get("api_key_vault_configured"):
        return "Configured via vault"
    if source == "locked" or config_state.get("api_key_vault_locked"):
        return "Vault locked"
    return "Missing"


def _blocked_reason(matrix_row: dict[str, Any], required_items: list[str]) -> str:
    if matrix_row["capability_status"] == "planned":
        if matrix_row["provider_key"] == "google_ads_search":
            return "Google Ads Search is not enabled for this profile; output should remain absent until this capability is approved."
        return "Planned capability; not enabled in importer console yet."
    if not matrix_row["supported_in_console"]:
        return "Capability does not have a provider fetch workflow in the importer console."
    if matrix_row["local_output_status"] != "Output exists" and matrix_row["live_fetch_status"] != "Ready":
        missing = matrix_row["missing_config_details"] or required_items
        return f"Needs config: {', '.join(missing)}"
    if matrix_row["local_output_status"] != "Output exists":
        return "Blocked until local output exists."
    return ""


def _suggested_command(profile: DashboardLabProfile, provider: str, matrix_row: dict[str, Any]) -> str:
    if matrix_row["capability_status"] == "planned" or not matrix_row["supported_in_console"]:
        return ""
    if provider == "ga4":
        return (
            f'python scripts/pull_ga4_traffic_overview.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --out "exports/local-real/dashboard-lab/{profile.slug}/ga4-snapshot.json"\n'
            f'python scripts/pull_ga4_traffic_overview.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output\n'
            f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --snapshot "exports/local-real/dashboard-lab/{profile.slug}/ga4-snapshot.json" --real-output'
        )
    if provider == "gsc":
        return (
            f"python scripts/fetch_gsc_api.py --profile {profile.slug} "
            f"--site-url {_gsc_site_url_hint(profile)} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output"
        )
    if provider == "local_falcon":
        manifest = f"local-falcon-manifests/{profile.slug}.json"
        return "\n".join(
            [
                f"# Expected ignored manifest: {manifest}",
                f"python scripts/fetch_local_falcon_api.py --profile {profile.slug} --transport live --execute --write",
                f"python scripts/validate_local_falcon_summary.py --file exports/local-real/dashboard-lab/{profile.slug}/local-falcon-summary.json",
            ]
        )
    if provider == "google_ads_search":
        return "\n".join(
            [
                f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --dry-run",
                f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --real-output",
                f"python scripts/validate_google_ads_summary.py --input exports/local-real/dashboard-lab/{profile.slug}/google-ads-summary.json",
            ]
        )
    if provider == "callrail":
        return "\n".join(
            [
                f"python scripts/diagnose_callrail_export_shape.py --profile {profile.slug} --input inputs/local-real/callrail/{profile.slug}/calls.csv",
                f"python scripts/import_callrail_export.py --profile {profile.slug} --input inputs/local-real/callrail/{profile.slug}/calls.csv --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output",
                f"python scripts/validate_callrail_summary.py --input exports/local-real/dashboard-lab/{profile.slug}/callrail-summary.json",
            ]
        )
    if provider == "form_fills":
        return "\n".join(
            [
                f"python scripts/import_form_fills.py --profile {profile.slug} --input inputs/local-real/form-fills/{profile.slug}/form-fills.csv --real-output",
                f"python scripts/validate_form_fills_summary.py --input exports/local-real/dashboard-lab/{profile.slug}/form-fills-summary.json",
            ]
        )
    return ""


def _profile_from_payload(payload: Any) -> DashboardLabProfile:
    if not isinstance(payload, dict):
        raise OperatorConsoleError("profile registry entries must be objects")
    required = [
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
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise OperatorConsoleError(f"profile registry entry missing fields: {', '.join(missing)}")
    sources = payload["data_sources"]
    if not isinstance(sources, list) or not all(isinstance(item, str) for item in sources):
        raise OperatorConsoleError("profile data_sources must be a list of strings")
    capabilities = _capabilities_from_payload(payload.get("capabilities"), sources)
    return DashboardLabProfile(
        slug=str(payload["slug"]),
        display_name=str(payload["display_name"]),
        domain=str(payload["domain"]),
        vertical=str(payload["vertical"]),
        service_model=str(payload["service_model"]),
        dashboard_lab_route=str(payload["dashboard_lab_route"]),
        importer_output_folder=_resolve_repo_path(str(payload["importer_output_folder"])),
        dashboard_lab_local_fixture_folder=_resolve_repo_path(str(payload["dashboard_lab_local_fixture_folder"])),
        dashboard_lab_synthetic_fixture_folder=_resolve_repo_path(str(payload["dashboard_lab_synthetic_fixture_folder"])),
        data_sources=sources,
        capabilities=capabilities,
    )


def _capabilities_from_payload(payload: Any, data_sources: list[str]) -> list[ProfileCapability]:
    if payload is None:
        return []
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise OperatorConsoleError("profile capabilities must be a list of objects")
    capabilities = []
    seen = set()
    for item in payload:
        key = str(item.get("key") or "").strip()
        if not key:
            raise OperatorConsoleError("profile capability key is required")
        if key in seen:
            raise OperatorConsoleError(f"duplicate profile capability key: {key}")
        seen.add(key)
        status = str(item.get("status") or "enabled").strip()
        if status not in {"enabled", "planned"}:
            raise OperatorConsoleError("profile capability status must be enabled or planned")
        provider = str(item.get("provider") or (key if key in SUPPORTED_IMPORTER_PROVIDERS else "")).strip()
        expected_output_file = str(
            item.get("expected_output_file")
            or PROVIDER_OUTPUT_FILES.get(provider, "")
            or PLANNED_PROVIDER_OUTPUT_FILES.get(provider, "")
        ).strip()
        capabilities.append(
            ProfileCapability(
                key=key,
                label=str(item.get("label") or PROVIDER_LABELS.get(key) or key),
                status=status,
                kind=str(item.get("kind") or ("importer_provider" if provider else "dashboard_room")),
                provider=provider,
                expected_output_file=expected_output_file,
                notes=str(item.get("notes") or ""),
            )
        )
    enabled_providers = {item.provider for item in capabilities if item.status == "enabled" and item.provider in SUPPORTED_IMPORTER_PROVIDERS}
    missing_sources = [source for source in data_sources if source not in enabled_providers]
    if missing_sources:
        raise OperatorConsoleError(f"profile capabilities missing enabled data source(s): {', '.join(missing_sources)}")
    return capabilities


def _validate_safe_fixture_paths(profile: DashboardLabProfile) -> None:
    if "public\\fixtures" in str(profile.dashboard_lab_local_fixture_folder) or "/public/fixtures/" in profile.dashboard_lab_local_fixture_folder.as_posix():
        raise OperatorConsoleError("dashboard_lab_local_fixture_folder must not point to committed public/fixtures")
    if "public/local-fixtures/" not in profile.dashboard_lab_local_fixture_folder.as_posix():
        raise OperatorConsoleError("dashboard_lab_local_fixture_folder must point under public/local-fixtures")
    if not profile.importer_output_folder.as_posix().endswith(f"exports/local-real/dashboard-lab/{profile.slug}"):
        raise OperatorConsoleError("importer_output_folder must point under exports/local-real/dashboard-lab/{profile}")


def _validate_copy_paths(profile: DashboardLabProfile) -> None:
    source = profile.importer_output_folder.resolve()
    destination = profile.dashboard_lab_local_fixture_folder.resolve()
    source_posix = source.as_posix()
    destination_posix = destination.as_posix()
    if f"exports/local-real/dashboard-lab/{profile.slug}" not in source_posix:
        raise OperatorConsoleError("copy source must be under exports/local-real/dashboard-lab/{profile}")
    if "/public/fixtures/" in destination_posix:
        raise OperatorConsoleError("copy destination must not point to committed public/fixtures")
    if "/public/local-fixtures/" not in destination_posix:
        raise OperatorConsoleError("copy destination must be under dashboard-lab public/local-fixtures")


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (ROOT / path).resolve()


def _provider_config(local_config: dict[str, Any], provider: str) -> dict[str, Any]:
    providers = local_config.get("providers")
    if isinstance(providers, dict) and isinstance(providers.get(provider), dict):
        return providers[provider]
    value = local_config.get(provider)
    return value if isinstance(value, dict) else local_config


def _missing_config_items(local_config: dict[str, Any]) -> list[str]:
    value = local_config.get("_missing_config_items")
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _local_profile_metadata_present(local_config: dict[str, Any]) -> bool:
    metadata = local_config.get("_local_profile_config")
    return isinstance(metadata, dict) and bool(metadata.get("present"))


def _local_falcon_manifest_configured(profile: DashboardLabProfile, local_config: dict[str, Any]) -> bool:
    if "manifest_exists" in local_config:
        return bool(local_config.get("manifest_exists"))
    return local_falcon_manifest_path(profile).exists() or _any_present(
        local_config,
        ("manifest", "manifest_path", "report_id", "local_falcon_manifest_configured"),
    )


def _local_profile_config_metadata(
    profile: DashboardLabProfile,
    config: dict[str, Any],
    loaded_config: Any | None,
    *,
    provider_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if loaded_config is not None:
        return {
            "present": loaded_config.found,
            "valid": loaded_config.valid,
            "path_label": loaded_config.path_label,
            "error": loaded_config.error,
        }
    metadata = None
    if provider_config and isinstance(provider_config.get("_local_profile_config"), dict):
        metadata = provider_config.get("_local_profile_config")
    elif isinstance(config, dict):
        for value in config.values():
            if isinstance(value, dict) and isinstance(value.get("_local_profile_config"), dict):
                metadata = value.get("_local_profile_config")
                break
    if isinstance(metadata, dict):
        return {
            "present": bool(metadata.get("present")),
            "valid": bool(metadata.get("valid", True)),
            "path_label": str(metadata.get("path_label") or f"local-profile-configs/{profile.slug}.local.json"),
            "error": str(metadata.get("error") or ""),
        }
    return {
        "present": False,
        "valid": True,
        "path_label": f"local-profile-configs/{profile.slug}.local.json",
        "error": "",
    }


def _ga4_configured(env: os._Environ[str] | dict[str, str]) -> bool:
    auth_method = (env.get("MUSIMACK_GA4_AUTH_METHOD") or "oauth").lower()
    if auth_method == "oauth":
        return all(env.get(name) for name in ("MUSIMACK_GA4_PROPERTY_ID", "MUSIMACK_GA4_OAUTH_CLIENT_SECRETS", "MUSIMACK_GA4_OAUTH_TOKEN_FILE"))
    if auth_method == "service_account":
        return bool(env.get("MUSIMACK_GA4_PROPERTY_ID") and (env.get("GOOGLE_APPLICATION_CREDENTIALS") or env.get("MUSIMACK_GA4_SERVICE_ACCOUNT_JSON")))
    return False


def _ga4_detail(env: os._Environ[str] | dict[str, str], local_config: dict[str, Any] | None = None) -> str:
    config = local_config or {}
    if config.get("property_id_env"):
        property_env = config.get("property_id_env") or "MUSIMACK_GA4_PROPERTY_ID"
        return (
            f"property env {property_env} {'present' if _any_present(config, ('property_id_env_present', 'property_id')) else 'missing'}; "
            f"OAuth files {'present' if _any_present(config, ('credentials_configured',)) else 'missing'}"
        )
    auth_method = (env.get("MUSIMACK_GA4_AUTH_METHOD") or "oauth").lower()
    return f"auth={auth_method}; property id {'present' if bool(env.get('MUSIMACK_GA4_PROPERTY_ID')) else 'missing'}"


def _gsc_configured(env: os._Environ[str] | dict[str, str]) -> bool:
    return all(env.get(name) for name in ("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS", "MUSIMACK_GSC_OAUTH_TOKEN_FILE"))


def _gsc_detail(env: os._Environ[str] | dict[str, str], local_config: dict[str, Any] | None = None) -> str:
    config = local_config or {}
    if config.get("oauth_client_secrets_env") or config.get("site_url_configured"):
        return (
            f"site URL {'present' if _any_present(config, ('site_url', 'gsc_site_url', 'site_url_configured')) else 'missing'}; "
            f"OAuth files {'present' if _any_present(config, ('credentials_configured',)) else 'missing'}"
        )
    return f"client secrets {'present' if bool(env.get('MUSIMACK_GSC_OAUTH_CLIENT_SECRETS')) else 'missing'}; token file {'present' if bool(env.get('MUSIMACK_GSC_OAUTH_TOKEN_FILE')) else 'missing'}"


def _any_present(config: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_present(config.get(key)) for key in keys)


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value).strip()) if value is not None else False


def _modified_time(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _file_size(path: Path) -> str:
    if not path.exists():
        return ""
    return str(path.stat().st_size)


def _schema_version(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unreadable"
    if isinstance(payload, dict):
        return str(payload.get("schema_version") or "")
    return ""


def _file_status(path: Path, filename: str) -> OutputFileStatus:
    if not path.exists():
        return OutputFileStatus(
            file=filename,
            exists=False,
            last_modified="",
            size="",
            schema_version="",
            json_valid=None,
            warning="missing",
        )
    if not path.is_file():
        return OutputFileStatus(
            file=filename,
            exists=True,
            last_modified=_modified_time(path),
            size=_file_size(path),
            schema_version="",
            json_valid=False,
            warning="not a file",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return OutputFileStatus(
            file=filename,
            exists=True,
            last_modified=_modified_time(path),
            size=_file_size(path),
            schema_version="",
            json_valid=False,
            warning="malformed JSON",
        )
    except OSError:
        return OutputFileStatus(
            file=filename,
            exists=True,
            last_modified=_modified_time(path),
            size=_file_size(path),
            schema_version="",
            json_valid=False,
            warning="unreadable",
        )
    schema = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
    return OutputFileStatus(
        file=filename,
        exists=True,
        last_modified=_modified_time(path),
        size=_file_size(path),
        schema_version=schema,
        json_valid=True,
        warning="",
    )
