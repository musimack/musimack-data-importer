from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_config import load_local_operator_config
from src.operator_console import (
    DashboardLabProfile,
    OperatorConsoleError,
    guarded_import_sequence,
    load_dashboard_lab_profiles,
    local_falcon_manifest_path,
    profile_by_slug,
    provider_setup_checklist,
    readiness_matrix,
    validate_profile_output,
)
from src.profile_local_config import DEFAULT_LOCAL_PROFILE_CONFIG_DIR, load_profile_provider_config_map


APP_NAME = "musimack-data-importer-local-api"
DEFAULT_LOCAL_PROFILE_CONFIG = ROOT / "config" / "dashboard_lab_profiles.local.json"
DEFAULT_AUDIT_LOG = ROOT / "logs" / "local-action-runs.jsonl"
PROVIDER_OUTPUT_FILES = {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "local_falcon": "local-falcon-summary.json",
}
BASE_REQUIRED_DASHBOARD_FILES = [
    "client-profile.json",
    "combined-dashboard-summary.json",
]
ACTION_ALLOWLIST = {"validate-output", "copy-to-dashboard-lab"}


class ActionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_slug: str
    action_id: str
    confirmed: bool = False


class ConfirmedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False
PROVIDER_LABELS = {
    "ga4": "GA4",
    "gsc": "GSC",
    "local_falcon": "Local Falcon",
}


def create_app(
    *,
    registry_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    local_profile_config_path: Path | None = None,
    audit_log_path: Path | None = None,
) -> FastAPI:
    if env is None:
        load_local_operator_config()

    app = FastAPI(title="Musimack Data Importer Local API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def current_profiles() -> list[DashboardLabProfile]:
        try:
            return load_dashboard_lab_profiles(registry_path)
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def current_local_config() -> dict[str, dict[str, Any]]:
        return load_local_profile_config(local_profile_config_path or DEFAULT_LOCAL_PROFILE_CONFIG)

    def current_profile_config(profile: DashboardLabProfile) -> dict[str, Any]:
        aggregate = current_local_config().get(profile.slug)
        if aggregate:
            return aggregate
        return load_profile_provider_config_map(profile.slug, config_dir=DEFAULT_LOCAL_PROFILE_CONFIG_DIR, env=current_env())

    def current_env() -> Mapping[str, str]:
        return os.environ if env is None else env

    def current_audit_log_path() -> Path:
        return audit_log_path or DEFAULT_AUDIT_LOG

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "app": APP_NAME}

    @app.get("/api/action-runs")
    def action_runs(
        profile_slug: str | None = None,
        action_id: str | None = None,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        if profile_slug is not None:
            try:
                profile_by_slug(profile_slug, current_profiles())
            except OperatorConsoleError as exc:
                raise HTTPException(status_code=404, detail="profile not found") from exc
        return read_action_runs(
            current_audit_log_path(),
            profile_slug=profile_slug,
            action_id=action_id,
            limit=limit,
        )

    @app.get("/api/profiles")
    def profiles() -> dict[str, Any]:
        local_config = current_local_config()
        safe_env = current_env()
        return {
            "profiles": [
                serialize_profile_summary(
                    profile,
                    safe_env=safe_env,
                    local_config=local_config.get(profile.slug)
                    or load_profile_provider_config_map(profile.slug, config_dir=DEFAULT_LOCAL_PROFILE_CONFIG_DIR, env=safe_env),
                )
                for profile in current_profiles()
            ]
        }

    @app.get("/api/profiles/{profile_slug}")
    def profile_detail(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return serialize_profile_detail(
            profile,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
            audit_log_path=current_audit_log_path(),
        )

    @app.get("/api/profiles/{profile_slug}/action-plan")
    def profile_action_plan(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return build_action_plan(
            profile,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
        )

    @app.get("/api/profiles/{profile_slug}/action-runs")
    def profile_action_runs(
        profile_slug: str,
        action_id: str | None = None,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return read_action_runs(
            current_audit_log_path(),
            profile_slug=profile.slug,
            action_id=action_id,
            limit=limit,
        )

    @app.get("/api/profiles/{profile_slug}/outputs")
    def profile_outputs(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        report = validate_profile_output(profile)
        return serialize_output_report(profile, report)

    @app.post("/api/profiles/{profile_slug}/actions/validate-output")
    def validate_profile_output_action(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return run_validate_output_action(profile, audit_log_path=current_audit_log_path())

    @app.get("/api/profiles/{profile_slug}/actions/copy-to-dashboard-lab/preview")
    def copy_to_dashboard_lab_preview(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return build_copy_preview(profile)

    @app.post("/api/profiles/{profile_slug}/actions/copy-to-dashboard-lab")
    def copy_to_dashboard_lab_action(profile_slug: str, request: ConfirmedActionRequest) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return run_copy_to_dashboard_lab_action(
            profile,
            confirmed=request.confirmed,
            audit_log_path=current_audit_log_path(),
        )

    @app.post("/api/actions/run")
    def run_action(request: ActionRunRequest) -> dict[str, Any]:
        if request.action_id not in ACTION_ALLOWLIST:
            raise HTTPException(status_code=400, detail="action is not allowed")
        try:
            profile = profile_by_slug(request.profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        if request.action_id == "validate-output":
            return run_validate_output_action(profile, audit_log_path=current_audit_log_path())
        if request.action_id == "copy-to-dashboard-lab":
            return run_copy_to_dashboard_lab_action(
                profile,
                confirmed=request.confirmed,
                audit_log_path=current_audit_log_path(),
            )
        raise HTTPException(status_code=400, detail="action is not implemented")

    return app


def serialize_profile_summary(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "slug": profile.slug,
        "display_name": profile.display_name,
        "domain": profile.domain,
        "vertical": profile.vertical,
        "service_model": profile.service_model,
        "dashboard_lab_route": profile.dashboard_lab_route,
        "enabled_providers": profile.data_sources,
        "capabilities": [
            {
                "key": item.key,
                "label": item.label,
                "status": item.status,
                "kind": item.kind,
                "provider": item.provider,
                "expected_output_file": item.expected_output_file,
                "notes": item.notes,
            }
            for item in profile.capabilities
        ],
        "provider_readiness": serialize_provider_readiness(
            profile,
            safe_env=safe_env,
            local_config=local_config,
        ),
        "readiness_matrix": readiness_matrix(
            profile,
            env=dict(safe_env),
            local_config=dict(local_config),
        ),
        "provider_setup_checklist": provider_setup_checklist(
            profile,
            env=dict(safe_env),
            local_config=dict(local_config),
        ),
    }


def serialize_profile_detail(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    audit_log_path: Path = DEFAULT_AUDIT_LOG,
) -> dict[str, Any]:
    report = validate_profile_output(profile)
    return {
        **serialize_profile_summary(profile, safe_env=safe_env, local_config=local_config),
        "paths": {
            "local_real_output_folder": str(profile.importer_output_folder),
            "dashboard_lab_local_fixture_folder": str(profile.dashboard_lab_local_fixture_folder),
        },
        "output_status": serialize_output_report(profile, report),
        "action_plan": build_action_plan(profile, safe_env=safe_env, local_config=local_config),
        "guarded_import_sequence": guarded_import_sequence(profile),
        "last_actions": build_last_action_summary(profile, audit_log_path),
        "safety": {
            "read_only": True,
            "local_only": True,
            "real_output_ignored_path": "exports/local-real/",
            "dashboard_lab_local_fixtures_only": True,
        },
    }


def build_action_plan(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    provider_config = {
        provider: _provider_config(local_config, provider)
        for provider in ("ga4", "gsc", "local_falcon")
    }
    return {
        "profile_slug": profile.slug,
        "guarded_import_sequence": guarded_import_sequence(profile),
        "actions": [
            _ga4_action(profile, safe_env=safe_env, local_config=provider_config["ga4"]),
            _gsc_action(profile, safe_env=safe_env, local_config=provider_config["gsc"]),
            _local_falcon_action(profile, safe_env=safe_env, local_config=provider_config["local_falcon"]),
            _validate_output_action(profile),
            _copy_to_dashboard_lab_action(profile),
        ],
    }


def _ga4_action(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "ga4" in profile.data_sources
    property_present = _present(safe_env.get("MUSIMACK_GA4_PROPERTY_ID")) or _any_present(
        local_config,
        ("property_id", "ga4_property_id", "property_id_env_present"),
    )
    auth_present = (
        _present(safe_env.get("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"))
        and _present(safe_env.get("MUSIMACK_GA4_OAUTH_TOKEN_FILE"))
    ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
    missing = []
    if not enabled:
        missing.append("GA4 is not enabled for this profile")
    if enabled and not property_present:
        missing.append("MUSIMACK_GA4_PROPERTY_ID or ignored local GA4 property_id")
    if enabled and not auth_present:
        missing.append("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS and MUSIMACK_GA4_OAUTH_TOKEN_FILE")
    status = "manual_only" if enabled and property_present and auth_present else "blocked_missing_config"
    blocked_reason = None if status == "manual_only" else "GA4 needs local property/auth configuration before snapshot export."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "GA4 is not enabled for this profile."
    return _action(
        action_id="ga4-snapshot",
        label="Preview GA4 sanitized snapshot export",
        provider="ga4",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            "\n".join(
                [
                    f'python scripts/pull_ga4_traffic_overview.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --out "{profile.importer_output_folder / "ga4-snapshot.json"}"',
                    f'python scripts/pull_ga4_traffic_overview.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                    f'python scripts/write_ga4_dashboard_lab_summary.py --profile {profile.slug} --snapshot "{profile.importer_output_folder / "ga4-snapshot.json"}" --real-output',
                ]
            )
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "ga4-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "GA4 dashboard-lab ga4-summary.json writer is available as a local snapshot-to-summary step.",
            "The first command writes a sanitized ga4_snapshot.v1 file; the second writes dashboard-lab ga4-summary.json.",
            "Set MUSIMACK_GA4_PROPERTY_ID in the shell or ignored local config; do not expose the value in the browser.",
        ],
        manual_step="Run the local GA4 snapshot export, then convert that snapshot into dashboard-lab ga4-summary.json.",
        readiness={
            "enabled": enabled,
            "property_id_configured": property_present,
            "local_auth_configured": auth_present,
            "dashboard_lab_writer_available": True,
        },
    )


def _gsc_action(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "gsc" in profile.data_sources
    site_url_hint = _gsc_site_url_hint(profile)
    site_present = _present(safe_env.get("MUSIMACK_GSC_SITE_URL")) or _any_present(
        local_config,
        ("site_url", "gsc_site_url", "site_url_configured"),
    )
    auth_present = (
        _present(safe_env.get("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS"))
        and _present(safe_env.get("MUSIMACK_GSC_OAUTH_TOKEN_FILE"))
    ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
    missing = []
    if not enabled:
        missing.append("GSC is not enabled for this profile")
    if enabled and not site_present:
        missing.append("GSC site URL in ignored local config or command argument")
    if enabled and not auth_present:
        missing.append("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS and MUSIMACK_GSC_OAUTH_TOKEN_FILE")
    status = "ready" if enabled and site_present and auth_present else "blocked_missing_config"
    blocked_reason = None if status == "ready" else "GSC needs a site URL and local OAuth config before fetching."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "GSC is not enabled for this profile."
    return _action(
        action_id="gsc-fetch",
        label="Fetch GSC local-real output",
        provider="gsc",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            f"python scripts/fetch_gsc_api.py --profile {profile.slug} --site-url {site_url_hint} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output"
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "gsc-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "Writes only to ignored exports/local-real/ when --real-output is used.",
            "Uses GSC read-only OAuth scope.",
            "Does not touch dashboard-lab committed fixtures.",
        ],
        manual_step=f"Use the verified Search Console property {site_url_hint} in ignored local config or supply it as --site-url.",
        readiness={
            "enabled": enabled,
            "site_url_configured": site_present,
            "local_auth_configured": auth_present,
            "site_url_hint": site_url_hint,
        },
    )


def _gsc_site_url_hint(profile: DashboardLabProfile) -> str:
    if profile.slug == "inn-at-spanish-head":
        return "sc-domain:spanishhead.com"

    return f"https://{profile.domain}/"


def _local_falcon_action(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "local_falcon" in profile.data_sources
    manifest = local_falcon_manifest_path(profile)
    manifest_configured = _local_falcon_manifest_configured(profile, local_config)
    api_key_present = _present(safe_env.get("LOCAL_FALCON_API_KEY")) or _any_present(
        local_config,
        ("api_key_env_present", "api_key_present", "api_key_configured"),
    )
    missing = []
    if not enabled:
        missing.append("Local Falcon is not enabled for this profile")
    if enabled and not manifest_configured:
        missing.append("ignored Local Falcon manifest with existing read-only report IDs")
    if enabled and not api_key_present:
        missing.append("LOCAL_FALCON_API_KEY")
    status = "ready" if enabled and manifest_configured and api_key_present else "blocked_missing_config"
    blocked_reason = None if status == "ready" else "Local Falcon needs an ignored manifest and API key presence before live read-only retrieval."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "Local Falcon is not enabled for this profile."
    return _action(
        action_id="local-falcon-read-only-fetch",
        label="Fetch Local Falcon read-only local-real output",
        provider="local_falcon",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            f'python scripts/fetch_local_falcon_api.py --profile {profile.slug} --transport live --execute --write'
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "local-falcon-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "Read-only report retrieval only.",
            "On-Demand scans are disabled.",
            "Provider mutation endpoints are disabled.",
            "LOCAL_FALCON_API_KEY is referenced by environment variable name only; the value is never returned.",
        ],
        manual_step="Create an ignored manifest under local-falcon-manifests/ using existing report IDs only.",
        readiness={
            "enabled": enabled,
            "manifest_configured": manifest_configured,
            "manifest_path_exists": manifest.exists(),
            "api_key_present": api_key_present,
        },
    )


def _validate_output_action(profile: DashboardLabProfile) -> dict[str, Any]:
    return _action(
        action_id="validate-local-real-output",
        label="Validate local-real dashboard output",
        provider="profile",
        status="ready",
        blocked_reason=None,
        command=f'python scripts/build_dashboard_lab_fixture.py --profile {profile.slug} --validate-only --export-folder --out "{profile.importer_output_folder}"',
        expected_output=str(profile.importer_output_folder),
        missing_inputs=[],
        safety_notes=[
            "Reads only the selected ignored local-real profile folder.",
            "Reports missing or malformed JSON without returning file contents.",
            "Does not write dashboard-lab fixtures.",
        ],
        manual_step="Run after provider summaries are generated.",
        readiness={"enabled": True, "executable": True, "requires_confirmation": True},
    )


def _copy_to_dashboard_lab_action(profile: DashboardLabProfile) -> dict[str, Any]:
    source = profile.importer_output_folder
    destination = profile.dashboard_lab_local_fixture_folder
    command = "\n".join(
        [
            f'New-Item -ItemType Directory -Force "{destination}" | Out-Null',
            f'Copy-Item "{source / "client-profile.json"}" "{destination / "client-profile.json"}" -Force',
            f'Copy-Item "{source / "ga4-summary.json"}" "{destination / "ga4-summary.json"}" -Force',
            f'Copy-Item "{source / "gsc-summary.json"}" "{destination / "gsc-summary.json"}" -Force',
            f'Copy-Item "{source / "combined-dashboard-summary.json"}" "{destination / "combined-dashboard-summary.json"}" -Force',
            f'Copy-Item "{source / "local-falcon-summary.json"}" "{destination / "local-falcon-summary.json"}" -Force',
        ]
    )
    return _action(
        action_id="copy-to-dashboard-lab-local-fixtures",
        label="Copy dashboard-lab local fixtures",
        provider="dashboard_lab",
        status="ready",
        blocked_reason=None,
        command=command,
        expected_output=str(destination),
        missing_inputs=[],
        safety_notes=[
            "Guarded browser copy is available only after explicit confirmation.",
            "Copy only into dashboard-lab public/local-fixtures.",
            "Never copy real local data into dashboard-lab public/fixtures.",
            "Do not commit copied real local fixture data.",
        ],
        manual_step="Review the copy preview, confirm the safety checkbox, then copy only expected JSON fixture files.",
        readiness={
            "source_folder": str(source),
            "destination_is_public_local_fixtures": "/public/local-fixtures/" in destination.as_posix(),
            "destination_is_public_fixtures": "/public/fixtures/" in destination.as_posix(),
            "executable": True,
            "requires_confirmation": True,
        },
    )


def _action(
    *,
    action_id: str,
    label: str,
    provider: str,
    status: str,
    blocked_reason: str | None,
    command: str,
    expected_output: str,
    missing_inputs: list[str],
    safety_notes: list[str],
    manual_step: str,
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "provider": provider,
        "status": status,
        "blocked_reason": blocked_reason,
        "command": command,
        "expected_output": expected_output,
        "missing_inputs": missing_inputs,
        "safety_notes": safety_notes,
        "manual_step": manual_step,
        "readiness": dict(readiness),
    }


def run_validate_output_action(profile: DashboardLabProfile, *, audit_log_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    _validate_profile_output_guard(profile)
    report = validate_profile_output(profile)
    result = serialize_validation_result(profile, report)
    duration_ms = int((time.perf_counter() - started) * 1000)
    audit = _write_audit_log(
        audit_log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action_id": "validate-output",
            "profile_slug": profile.slug,
            "status": result["overall_status"],
            "result_summary": {
                "folder_exists": result["folder_exists"],
                "expected_file_count": len(result["expected_files"]),
                "required_file_count": len(result["required_files"]),
                "missing_required_file_count": len(result["missing_required_files"]),
                "malformed_json_file_count": len(result["malformed_json_files"]),
            },
            "warnings": result["warnings"],
            "duration_ms": duration_ms,
        },
    )
    return {
        "action_id": "validate-output",
        "profile_slug": profile.slug,
        "status": result["overall_status"],
        "duration_ms": duration_ms,
        "result": result,
        "audit": audit,
        "guardrails": [
            "profile slug resolved from committed registry",
            "source folder derived from profile registry only",
            "no arbitrary path input accepted",
            "no shell command or subprocess execution",
            "no provider API calls",
            "no file copying",
        ],
    }


def build_copy_preview(profile: DashboardLabProfile) -> dict[str, Any]:
    _validate_copy_guard(profile)
    items = [_copy_plan_item(profile, filename) for filename in _expected_dashboard_files_for_profile(profile)]
    return {
        "action_id": "copy-to-dashboard-lab",
        "profile_slug": profile.slug,
        "source_folder": str(profile.importer_output_folder),
        "destination_folder": str(profile.dashboard_lab_local_fixture_folder),
        "expected_files": _expected_dashboard_files_for_profile(profile),
        "items": items,
        "guardrails": [
            "source folder derived from profile registry only",
            "destination folder derived from profile registry only",
            "destination must be dashboard-lab public/local-fixtures",
            "destination must not be dashboard-lab public/fixtures",
            "only expected dashboard-lab JSON fixture files are eligible",
            "no shell command or subprocess execution",
            "no provider API calls",
        ],
    }


def run_copy_to_dashboard_lab_action(
    profile: DashboardLabProfile,
    *,
    confirmed: bool,
    audit_log_path: Path,
) -> dict[str, Any]:
    if not confirmed:
        raise HTTPException(status_code=400, detail="copy action requires explicit confirmation")
    started = time.perf_counter()
    preview = build_copy_preview(profile)
    destination_folder = profile.dashboard_lab_local_fixture_folder
    results = []
    destination_folder.mkdir(parents=True, exist_ok=True)
    for item in preview["items"]:
        source = Path(item["source"])
        destination = Path(item["destination"])
        if not item["source_exists"]:
            results.append({**item, "status": "skipped_missing_source", "error": ""})
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            status = "overwritten" if item["destination_exists"] else "copied"
            results.append(
                {
                    **item,
                    "status": status,
                    "destination_exists": destination.exists(),
                    "size": _safe_file_size(destination),
                    "last_modified": _safe_modified_time(destination),
                    "error": "",
                }
            )
        except OSError as exc:
            results.append({**item, "status": "failed", "error": type(exc).__name__})
    counts = _copy_result_counts(results)
    duration_ms = int((time.perf_counter() - started) * 1000)
    warnings = []
    if counts["skipped_missing_source"]:
        warnings.append(f"skipped missing source file(s): {counts['skipped_missing_source']}")
    if counts["failed"]:
        warnings.append(f"failed file(s): {counts['failed']}")
    status = "ok" if counts["failed"] == 0 else "failed"
    audit = _write_audit_log(
        audit_log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action_id": "copy-to-dashboard-lab",
            "profile_slug": profile.slug,
            "status": status,
            "file_counts": {
                "expected": len(results),
                "copied": counts["copied"],
                "overwritten": counts["overwritten"],
                "skipped": counts["skipped_missing_source"],
                "failed": counts["failed"],
            },
            "warnings": warnings,
            "duration_ms": duration_ms,
        },
    )
    return {
        "action_id": "copy-to-dashboard-lab",
        "profile_slug": profile.slug,
        "status": status,
        "duration_ms": duration_ms,
        "source_folder": preview["source_folder"],
        "destination_folder": preview["destination_folder"],
        "items": results,
        "counts": counts,
        "warnings": warnings,
        "audit": audit,
        "guardrails": preview["guardrails"],
    }


def serialize_validation_result(profile: DashboardLabProfile, report: Any) -> dict[str, Any]:
    expected_files = _expected_dashboard_files_for_profile(profile)
    required_files = _required_dashboard_files_for_profile(profile)
    missing_required = [item.file for item in report.files if item.file in required_files and not item.exists]
    disabled_missing = [item.file for item in report.files if item.file not in required_files and not item.exists]
    malformed = [item.file for item in report.files if item.exists and item.json_valid is False]
    warnings = list(report.warnings)
    if disabled_missing:
        warnings.append(f"missing disabled provider file(s): {', '.join(disabled_missing)}")
    overall_status = _validation_overall_status(
        folder_exists=report.folder_exists,
        missing_required=missing_required,
        malformed=malformed,
        warnings=warnings,
    )
    return {
        "folder": str(report.folder),
        "folder_exists": report.folder_exists,
        "expected_files": expected_files,
        "required_files": required_files,
        "files": [
            {
                "file": item.file,
                "exists": item.exists,
                "last_modified": item.last_modified,
                "size": item.size,
                "schema_version": item.schema_version,
                "json_valid": item.json_valid,
                "warning": item.warning,
                "required": item.file in required_files,
            }
            for item in report.files
        ],
        "missing_files": [item.file for item in report.files if not item.exists],
        "missing_required_files": missing_required,
        "missing_disabled_provider_files": disabled_missing,
        "malformed_json_files": malformed,
        "warnings": warnings,
        "overall_status": overall_status,
    }


def _validation_overall_status(
    *,
    folder_exists: bool,
    missing_required: list[str],
    malformed: list[str],
    warnings: list[str],
) -> str:
    if not folder_exists:
        return "folder_missing"
    if malformed:
        return "invalid_json"
    if missing_required:
        return "missing_outputs"
    if warnings:
        return "warning"
    return "ok"


def _expected_dashboard_files_for_profile(profile: DashboardLabProfile) -> list[str]:
    return [
        "client-profile.json",
        "ga4-summary.json",
        "gsc-summary.json",
        "combined-dashboard-summary.json",
        "local-falcon-summary.json",
    ]


def _required_dashboard_files_for_profile(profile: DashboardLabProfile) -> list[str]:
    files = list(BASE_REQUIRED_DASHBOARD_FILES)
    for provider in profile.data_sources:
        output_file = PROVIDER_OUTPUT_FILES.get(provider)
        if output_file:
            files.append(output_file)
    return [file for file in _expected_dashboard_files_for_profile(profile) if file in set(files)]


def _validate_profile_output_guard(profile: DashboardLabProfile) -> None:
    source = profile.importer_output_folder.resolve()
    source_posix = source.as_posix()
    if f"exports/local-real/dashboard-lab/{profile.slug}" not in source_posix:
        raise HTTPException(status_code=400, detail="validation source must be under exports/local-real/dashboard-lab/{profile}")
    if source_posix.endswith(f"public/fixtures/{profile.slug}") or "/public/fixtures/" in source_posix:
        raise HTTPException(status_code=400, detail="validation source must not point to committed fixtures")


def _validate_copy_guard(profile: DashboardLabProfile) -> None:
    source = profile.importer_output_folder.resolve()
    destination = profile.dashboard_lab_local_fixture_folder.resolve()
    source_posix = source.as_posix()
    destination_posix = destination.as_posix()
    if not source_posix.endswith(f"exports/local-real/dashboard-lab/{profile.slug}"):
        raise HTTPException(status_code=400, detail="copy source must be under exports/local-real/dashboard-lab/{profile}")
    if not destination_posix.endswith(f"public/local-fixtures/{profile.slug}"):
        raise HTTPException(status_code=400, detail="copy destination must be under dashboard-lab public/local-fixtures/{profile}")
    if "/public/fixtures/" in destination_posix:
        raise HTTPException(status_code=400, detail="copy destination must not point to committed public/fixtures")


def _copy_plan_item(profile: DashboardLabProfile, filename: str) -> dict[str, Any]:
    source = profile.importer_output_folder / filename
    destination = profile.dashboard_lab_local_fixture_folder / filename
    source_exists = source.exists() and source.is_file()
    destination_exists = destination.exists()
    action = "skip_missing_source"
    if source_exists and destination_exists:
        action = "overwrite"
    elif source_exists:
        action = "copy"
    return {
        "file": filename,
        "source": str(source),
        "source_exists": source_exists,
        "destination": str(destination),
        "destination_exists": destination_exists,
        "action": action,
        "size": _safe_file_size(source),
        "last_modified": _safe_modified_time(source),
    }


def _copy_result_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "copied": sum(1 for item in results if item["status"] == "copied"),
        "overwritten": sum(1 for item in results if item["status"] == "overwritten"),
        "skipped_missing_source": sum(1 for item in results if item["status"] == "skipped_missing_source"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
    }


def _safe_file_size(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return str(path.stat().st_size)


def _safe_modified_time(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def _write_audit_log(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        return {
            "logged": False,
            "path": str(path),
            "error": type(exc).__name__,
        }
    return {
        "logged": True,
        "path": str(path),
    }


def read_action_runs(
    path: Path,
    *,
    profile_slug: str | None = None,
    action_id: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"entries": [], "count": 0, "skipped_malformed": 0}
    entries = []
    skipped_malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"entries": [], "count": 0, "skipped_malformed": 0, "warnings": ["audit log could not be read"]}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            skipped_malformed += 1
            continue
        entry = _safe_audit_entry(payload, line_number)
        if not entry:
            skipped_malformed += 1
            continue
        if profile_slug and entry["profile_slug"] != profile_slug:
            continue
        if action_id and entry["action_id"] != action_id:
            continue
        entries.append(entry)
    recent = list(reversed(entries))[:limit]
    return {
        "entries": recent,
        "count": len(recent),
        "skipped_malformed": skipped_malformed,
    }


def build_last_action_summary(profile: DashboardLabProfile, audit_log_path: Path) -> dict[str, Any]:
    history = read_action_runs(audit_log_path, profile_slug=profile.slug, limit=100)
    entries = history["entries"]
    last_validation = _first_action(entries, "validate-output")
    last_copy = _first_action(entries, "copy-to-dashboard-lab")
    return {
        "last_action": entries[0] if entries else None,
        "last_validation": last_validation,
        "last_copy": last_copy,
        "skipped_malformed": history["skipped_malformed"],
    }


def _safe_audit_entry(payload: Any, line_number: int) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    action_id = payload.get("action_id")
    profile_slug = payload.get("profile_slug")
    if not isinstance(action_id, str) or not isinstance(profile_slug, str):
        return None
    warnings = payload.get("warnings")
    safe_warnings = [str(item) for item in warnings if isinstance(item, str)] if isinstance(warnings, list) else []
    return {
        "audit_entry_id": f"line-{line_number}",
        "timestamp": str(payload.get("timestamp") or ""),
        "action_id": action_id,
        "profile_slug": profile_slug,
        "status": str(payload.get("status") or ""),
        "result_summary": _safe_mapping(
            payload.get("result_summary"),
            {
                "folder_exists",
                "expected_file_count",
                "required_file_count",
                "missing_required_file_count",
                "malformed_json_file_count",
            },
        ),
        "file_counts": _safe_mapping(
            payload.get("file_counts"),
            {"expected", "copied", "overwritten", "skipped", "failed"},
        ),
        "warnings": safe_warnings,
        "warnings_count": len(safe_warnings),
        "duration_ms": _safe_int(payload.get("duration_ms")),
    }


def _safe_mapping(value: Any, allowed_keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe = {}
    for key, item in value.items():
        if (
            isinstance(key, str)
            and key in allowed_keys
            and (isinstance(item, (str, int, float, bool)) or item is None)
        ):
            safe[str(key)] = item
    return safe


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _first_action(entries: list[dict[str, Any]], action_id: str) -> dict[str, Any] | None:
    for entry in entries:
        if entry["action_id"] == action_id:
            return entry
    return None


def serialize_output_report(profile: DashboardLabProfile, report: Any) -> dict[str, Any]:
    return {
        "profile_slug": profile.slug,
        "folder": str(report.folder),
        "folder_exists": report.folder_exists,
        "ok": report.ok,
        "warnings": report.warnings,
        "files": [
            {
                "file": item.file,
                "exists": item.exists,
                "last_modified": item.last_modified,
                "size": item.size,
                "schema_version": item.schema_version,
                "json_valid": item.json_valid,
                "warning": item.warning,
            }
            for item in report.files
        ],
    }


def serialize_provider_readiness(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    output_files = {item.file: item for item in validate_profile_output(profile).files}
    return [
        _provider_status(
            profile,
            provider,
            safe_env=safe_env,
            local_config=_provider_config(local_config, provider),
            output_files=output_files,
        )
        for provider in profile.data_sources
    ]


def _provider_status(
    profile: DashboardLabProfile,
    provider: str,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    output_files: Mapping[str, Any],
) -> dict[str, Any]:
    output_file = PROVIDER_OUTPUT_FILES.get(provider, "")
    output_status = output_files.get(output_file)
    readiness = _provider_readiness_flags(profile, provider, safe_env=safe_env, local_config=local_config)
    return {
        "provider": provider,
        "label": PROVIDER_LABELS.get(provider, provider),
        "enabled": provider in profile.data_sources,
        "config_ready": readiness["config_ready"],
        "credentials_ready": readiness["credentials_ready"],
        "readiness": readiness["readiness"],
        "expected_output_file": output_file,
        "output_file_exists": bool(output_status.exists) if output_status else False,
    }


def _provider_readiness_flags(
    profile: DashboardLabProfile,
    provider: str,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    if provider == "ga4":
        property_present = _present(safe_env.get("MUSIMACK_GA4_PROPERTY_ID")) or _any_present(
            local_config,
            ("property_id", "ga4_property_id", "property_id_env_present"),
        )
        credential_present = (
            _present(safe_env.get("MUSIMACK_GA4_OAUTH_CLIENT_SECRETS"))
            and _present(safe_env.get("MUSIMACK_GA4_OAUTH_TOKEN_FILE"))
        ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
        return _readiness(property_present, credential_present)
    if provider == "gsc":
        site_present = _present(safe_env.get("MUSIMACK_GSC_SITE_URL")) or _any_present(
            local_config,
            ("site_url", "gsc_site_url", "site_url_configured"),
        )
        credential_present = (
            _present(safe_env.get("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS"))
            and _present(safe_env.get("MUSIMACK_GSC_OAUTH_TOKEN_FILE"))
        ) or _any_present(local_config, ("oauth_client_secrets", "oauth_token_file", "credentials_configured"))
        return _readiness(site_present, credential_present)
    if provider == "local_falcon":
        manifest_present = _local_falcon_manifest_configured(profile, local_config)
        credential_present = _present(safe_env.get("LOCAL_FALCON_API_KEY")) or _any_present(
            local_config,
            ("api_key_env_present", "api_key_present", "api_key_configured"),
        )
        return _readiness(manifest_present, credential_present)
    return _readiness(False, False)


def load_local_profile_config(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if isinstance(profiles, dict):
        return {str(slug): value for slug, value in profiles.items() if isinstance(value, dict)}
    if isinstance(profiles, list):
        return {
            str(item["slug"]): item
            for item in profiles
            if isinstance(item, dict) and isinstance(item.get("slug"), str)
        }
    return {}


def _provider_config(local_config: Mapping[str, Any], provider: str) -> Mapping[str, Any]:
    providers = local_config.get("providers")
    if isinstance(providers, Mapping) and isinstance(providers.get(provider), Mapping):
        return providers[provider]
    value = local_config.get(provider)
    return value if isinstance(value, Mapping) else local_config


def _readiness(config_present: bool, credential_present: bool) -> dict[str, Any]:
    return {
        "config_ready": config_present and credential_present,
        "credentials_ready": credential_present,
        "readiness": {
            "config_present": config_present,
            "credentials_present": credential_present,
        },
    }


def _local_falcon_manifest_configured(profile: DashboardLabProfile, local_config: Mapping[str, Any]) -> bool:
    if "manifest_exists" in local_config:
        return bool(local_config.get("manifest_exists"))
    return local_falcon_manifest_path(profile).exists() or _any_present(
        local_config,
        ("manifest", "manifest_path", "report_id", "local_falcon_manifest_configured"),
    )


def _any_present(config: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_present(config.get(key)) for key in keys)


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value).strip()) if value is not None else False


app = create_app()
