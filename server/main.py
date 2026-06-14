from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_config import load_local_operator_config
from src.local_secret_vault import (
    DEFAULT_VAULT_PATH,
    CorruptVaultError,
    InvalidPassphraseError,
    LocalSecretVault,
    LocalSecretVaultError,
    MissingSecretError,
    SecretStatus,
    VaultLockedError,
)
from src.operator_console import (
    DEFAULT_PROFILE_REGISTRY,
    DashboardLabProfile,
    OperatorConsoleError,
    expected_dashboard_files,
    guarded_import_sequence,
    load_dashboard_lab_profiles,
    local_falcon_manifest_path,
    profile_by_slug,
    provider_setup_checklist,
    readiness_matrix,
    validate_profile_output,
)
from src.profile_local_config import (
    DEFAULT_LOCAL_PROFILE_CONFIG_DIR,
    ProfileLocalConfigError,
    load_profile_provider_config_map,
)
from src.profile_local_config_writer import (
    ProfileLocalConfigWriteError,
    build_local_config_draft,
    preview_local_config_update,
    write_local_config_update,
)
from src.profile_registry_writer import (
    ProfileRegistryWriteError,
    build_profile_registry_draft,
    preview_profile_registry_update,
    write_profile_registry_update,
)
from scripts.validate_local_falcon_manifest import validate_manifest as validate_local_falcon_manifest


APP_NAME = "musimack-data-importer-local-api"
DEFAULT_LOCAL_PROFILE_CONFIG = ROOT / "config" / "dashboard_lab_profiles.local.json"
DEFAULT_AUDIT_LOG = ROOT / "logs" / "local-action-runs.jsonl"
IMPORTER_VAULT_PATH_ENV = "MUSIMACK_IMPORTER_VAULT_PATH"
LOCAL_CONFIG_DIR_ENV = "MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR"
PROFILE_REGISTRY_PATH_ENV = "MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH"
FORM_FILLS_INPUT_DIR_ENV = "MUSIMACK_IMPORTER_FORM_FILLS_INPUT_DIR"
CALLRAIL_INPUT_DIR_ENV = "MUSIMACK_IMPORTER_CALLRAIL_INPUT_DIR"
LOCAL_FALCON_MANIFEST_DIR_ENV = "MUSIMACK_IMPORTER_LOCAL_FALCON_MANIFEST_DIR"
DASHBOARD_LAB_FIXTURE_TARGET_DIR_ENV = "MUSIMACK_IMPORTER_DASHBOARD_LAB_FIXTURE_TARGET_DIR"
PROVIDER_OUTPUT_FILES = {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "local_falcon": "local-falcon-summary.json",
    "google_ads_search": "google-ads-summary.json",
    "callrail": "callrail-summary.json",
    "form_fills": "form-fills-summary.json",
}
PROVIDER_VALIDATION_TARGETS = {
    "ga4": {
        "script": ROOT / "scripts" / "validate_ga4_snapshot.py",
        "argument": "--file",
        "file": "ga4-snapshot.json",
    },
    "local_falcon": {
        "script": ROOT / "scripts" / "validate_local_falcon_summary.py",
        "argument": "--file",
        "file": "local-falcon-summary.json",
    },
    "google_ads_search": {
        "script": ROOT / "scripts" / "validate_google_ads_summary.py",
        "argument": "--input",
        "file": "google-ads-summary.json",
    },
    "callrail": {
        "script": ROOT / "scripts" / "validate_callrail_summary.py",
        "argument": "--input",
        "file": "callrail-summary.json",
    },
    "form_fills": {
        "script": ROOT / "scripts" / "validate_form_fills_summary.py",
        "argument": "--input",
        "file": "form-fills-summary.json",
    },
}
LOCAL_VALIDATION_TIMEOUT_SECONDS = 20
LOCAL_IMPORT_TIMEOUT_SECONDS = 30
BASE_REQUIRED_DASHBOARD_FILES = [
    "client-profile.json",
    "combined-dashboard-summary.json",
]
ACTION_ALLOWLIST = {"validate-output", "copy-to-dashboard-lab"}
LOCAL_FILE_UPLOAD_PROVIDERS = {"local_falcon", "form_fills", "callrail"}
LOCAL_FILE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024


class ActionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_slug: str
    action_id: str
    confirmed: bool = False


class ConfirmedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False
    input_file: str | None = None


class SecretVaultUnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passphrase: str
    create_if_missing: bool = False


class SecretValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class LocalConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: dict[str, Any]
    confirmed: bool = False


class ProfileRegistryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: dict[str, Any]
    confirmed: bool = False


PROVIDER_LABELS = {
    "ga4": "GA4",
    "gsc": "GSC",
    "local_falcon": "Local Falcon",
    "google_ads_search": "Google Ads Search",
    "callrail": "CallRail",
    "form_fills": "Form Fills",
    "profile": "Profile Output",
    "dashboard_lab": "Dashboard-lab Fixtures",
}
ALLOWED_VAULT_SECRET_KEYS = {("local_falcon", "api_key")}


def create_app(
    *,
    registry_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    local_profile_config_path: Path | None = None,
    local_profile_config_dir: Path | None = None,
    audit_log_path: Path | None = None,
    secret_vault_path: Path | None = None,
    form_fills_input_dir: Path | None = None,
    callrail_input_dir: Path | None = None,
    dashboard_lab_fixture_target_dir: Path | None = None,
) -> FastAPI:
    if env is None:
        load_local_operator_config()

    secret_vault_state = SecretVaultApiState(
        resolve_secret_vault_path(env=os.environ if env is None else env, explicit_path=secret_vault_path)
    )
    app = FastAPI(title="Musimack Data Importer Local API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5274", "http://127.0.0.1:5274"],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "POST"],
        allow_headers=["*"],
    )

    def current_registry_path() -> Path:
        return resolve_profile_registry_path(
            env=current_env(),
            explicit_path=registry_path,
        )

    def current_profiles() -> list[DashboardLabProfile]:
        try:
            profiles = load_dashboard_lab_profiles(current_registry_path())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        target_dir = resolve_dashboard_lab_fixture_target_dir(
            env=current_env(),
            explicit_dir=dashboard_lab_fixture_target_dir,
        )
        if target_dir is None:
            return profiles
        return [
            replace(profile, dashboard_lab_local_fixture_folder=target_dir / profile.slug)
            for profile in profiles
        ]

    def current_local_config() -> dict[str, dict[str, Any]]:
        return load_local_profile_config(local_profile_config_path or DEFAULT_LOCAL_PROFILE_CONFIG)

    def current_profile_config(profile: DashboardLabProfile) -> dict[str, Any]:
        aggregate = current_local_config().get(profile.slug)
        config = (
            aggregate
            if aggregate
            else load_profile_provider_config_map(profile.slug, config_dir=current_local_profile_config_dir(), env=current_env())
        )
        return _with_secret_vault_readiness(profile, config, current_env(), secret_vault_state)

    def current_env() -> Mapping[str, str]:
        return os.environ if env is None else env

    def current_local_profile_config_dir() -> Path:
        return resolve_local_profile_config_dir(
            env=current_env(),
            explicit_dir=local_profile_config_dir,
        )

    def current_audit_log_path() -> Path:
        if audit_log_path is not None:
            return audit_log_path
        if registry_path is not None and registry_path.resolve() != DEFAULT_PROFILE_REGISTRY.resolve():
            return registry_path.parent / "logs" / "local-action-runs.jsonl"
        return DEFAULT_AUDIT_LOG

    def current_form_fills_input_dir() -> Path:
        return resolve_form_fills_input_dir(
            env=current_env(),
            explicit_dir=form_fills_input_dir,
        )

    def current_callrail_input_dir() -> Path:
        return resolve_callrail_input_dir(
            env=current_env(),
            explicit_dir=callrail_input_dir,
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "app": APP_NAME}

    @app.get("/api/secrets/status")
    def secret_vault_status() -> dict[str, Any]:
        return secret_vault_state.status()

    @app.post("/api/secrets/unlock")
    def secret_vault_unlock(request: SecretVaultUnlockRequest) -> dict[str, Any]:
        try:
            return secret_vault_state.unlock(
                passphrase=request.passphrase,
                create_if_missing=request.create_if_missing,
            )
        except InvalidPassphraseError as exc:
            raise HTTPException(status_code=401, detail="vault passphrase is invalid") from exc
        except CorruptVaultError as exc:
            raise HTTPException(status_code=400, detail="vault could not be read") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vault file is missing") from exc

    @app.post("/api/secrets/lock")
    def secret_vault_lock() -> dict[str, Any]:
        return secret_vault_state.lock()

    @app.get("/api/profiles/{profile_slug}/secrets")
    def profile_secret_status(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            return {
                "profile": profile.slug,
                "secrets": secret_vault_state.profile_secret_status(profile.slug),
            }
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except CorruptVaultError as exc:
            raise HTTPException(status_code=400, detail="vault could not be read") from exc

    @app.post("/api/profiles/{profile_slug}/secrets/{provider}/{key}")
    def set_profile_secret(profile_slug: str, provider: str, key: str, request: SecretValueRequest) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            _require_allowed_vault_secret(provider=provider, key=key)
            secret_value = request.value.strip()
            if not secret_value:
                raise HTTPException(status_code=400, detail="secret value is required")
            return {
                "profile": profile.slug,
                "secret": secret_vault_state.set_secret(
                    profile=profile.slug,
                    provider=provider,
                    key=key,
                    value=secret_value,
                ),
            }
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except VaultLockedError as exc:
            raise HTTPException(status_code=423, detail="vault is locked") from exc
        except CorruptVaultError as exc:
            raise HTTPException(status_code=400, detail="vault could not be read") from exc

    @app.delete("/api/profiles/{profile_slug}/secrets/{provider}/{key}")
    def delete_profile_secret(profile_slug: str, provider: str, key: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            _require_allowed_vault_secret(provider=provider, key=key)
            return {
                "profile": profile.slug,
                "secret": secret_vault_state.delete_secret(
                    profile=profile.slug,
                    provider=provider,
                    key=key,
                ),
            }
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except VaultLockedError as exc:
            raise HTTPException(status_code=423, detail="vault is locked") from exc
        except CorruptVaultError as exc:
            raise HTTPException(status_code=400, detail="vault could not be read") from exc

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
        safe_env = current_env()
        return {
            "profiles": [
                serialize_profile_summary(
                    profile,
                    safe_env=safe_env,
                    local_config=current_profile_config(profile),
                )
                for profile in current_profiles()
            ]
        }

    @app.get("/api/runtime-safety-status")
    def runtime_safety_status() -> dict[str, Any]:
        return build_runtime_safety_status(current_env())

    @app.get("/api/profile-registry/new-draft")
    def profile_registry_new_draft() -> dict[str, Any]:
        return build_profile_registry_draft()

    @app.post("/api/profile-registry/preview")
    def profile_registry_preview(request: ProfileRegistryUpdateRequest) -> dict[str, Any]:
        try:
            return preview_profile_registry_update(
                request.draft,
                registry_path=current_registry_path(),
            ).as_safe_dict()
        except ProfileRegistryWriteError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/profile-registry")
    def profile_registry_save(request: ProfileRegistryUpdateRequest) -> dict[str, Any]:
        try:
            return write_profile_registry_update(
                request.draft,
                confirmed=request.confirmed,
                registry_path=current_registry_path(),
            )
        except ProfileRegistryWriteError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    @app.get("/api/profiles/{profile_slug}/onboarding-status")
    def profile_onboarding_status(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return build_onboarding_status(
            profile,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
            audit_log_path=current_audit_log_path(),
        )

    @app.post("/api/profiles/{profile_slug}/local-files/{provider}/upload")
    async def profile_local_file_upload(
        profile_slug: str,
        provider: str,
        file: UploadFile = File(...),
        confirmed: bool = Form(False),
    ) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        try:
            return await store_local_file_upload(
                profile,
                provider,
                file=file,
                confirmed=confirmed,
                safe_env=current_env(),
                local_config=current_profile_config(profile),
                form_fills_input_dir=current_form_fills_input_dir(),
                callrail_input_dir=current_callrail_input_dir(),
            )
        except OSError as exc:
            raise HTTPException(status_code=400, detail="local file could not be saved safely") from exc

    @app.get("/api/profiles/{profile_slug}/onboarding-completion-summary")
    def profile_onboarding_completion_summary(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return build_onboarding_completion_summary(
            profile,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
            audit_log_path=current_audit_log_path(),
        )

    @app.get("/api/profiles/{profile_slug}/onboarding-actions")
    def profile_onboarding_actions(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return build_onboarding_actions(
            profile,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
        )

    @app.post("/api/profiles/{profile_slug}/onboarding-actions/{action_id}/preview")
    def profile_onboarding_action_preview(profile_slug: str, action_id: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return preview_onboarding_action(
            profile,
            action_id,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
        )

    @app.post("/api/profiles/{profile_slug}/onboarding-actions/{action_id}/run")
    def profile_onboarding_action_run(profile_slug: str, action_id: str, request: ConfirmedActionRequest) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        return run_onboarding_action(
            profile,
            action_id,
            confirmed=request.confirmed,
            input_file=request.input_file,
            safe_env=current_env(),
            local_config=current_profile_config(profile),
            form_fills_input_dir=current_form_fills_input_dir(),
            callrail_input_dir=current_callrail_input_dir(),
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

    @app.get("/api/profiles/{profile_slug}/local-config/draft")
    def local_config_draft(profile_slug: str) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            return build_local_config_draft(profile.slug, config_dir=current_local_profile_config_dir())
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except (ProfileLocalConfigError, ProfileLocalConfigWriteError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/profiles/{profile_slug}/local-config/preview")
    def local_config_preview(profile_slug: str, request: LocalConfigUpdateRequest) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            return preview_local_config_update(
                profile.slug,
                request.draft,
                config_dir=current_local_profile_config_dir(),
            ).as_safe_dict()
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except (ProfileLocalConfigError, ProfileLocalConfigWriteError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/profiles/{profile_slug}/local-config")
    def local_config_save(profile_slug: str, request: LocalConfigUpdateRequest) -> dict[str, Any]:
        try:
            profile = profile_by_slug(profile_slug, current_profiles())
            return write_local_config_update(
                profile.slug,
                request.draft,
                confirmed=request.confirmed,
                config_dir=current_local_profile_config_dir(),
            )
        except OperatorConsoleError as exc:
            raise HTTPException(status_code=404, detail="profile not found") from exc
        except (ProfileLocalConfigError, ProfileLocalConfigWriteError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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


class SecretVaultApiState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._vault: LocalSecretVault | None = None

    def status(self) -> dict[str, Any]:
        if not self.path.exists() or not self.path.is_file():
            self._vault = None
            return _secret_vault_status(
                exists=False,
                unlocked=False,
                entries=[],
            )
        try:
            vault = self._vault if self._vault is not None else LocalSecretVault.load(self.path)
            return _secret_vault_status(
                exists=True,
                unlocked=not vault.locked,
                entries=[item.as_safe_dict() for item in vault.list_status()],
            )
        except LocalSecretVaultError:
            self._vault = None
            return _secret_vault_status(
                exists=True,
                unlocked=False,
                entries=[],
                status="error",
                error="vault could not be read",
            )

    def unlock(self, *, passphrase: str, create_if_missing: bool = False) -> dict[str, Any]:
        if not self.path.exists() or not self.path.is_file():
            if not create_if_missing:
                self._vault = None
                raise FileNotFoundError("vault file is missing")
            self._vault = LocalSecretVault.create(self.path, passphrase=passphrase)
            return self.status()
        vault = LocalSecretVault.load(self.path)
        vault.unlock(passphrase)
        self._vault = vault
        return self.status()

    def lock(self) -> dict[str, Any]:
        if self._vault is not None:
            self._vault.lock()
        self._vault = None
        return self.status()

    def profile_secret_status(self, profile: str) -> list[dict[str, Any]]:
        return [
            self.secret_status(profile=profile, provider=provider, key=key)
            for provider, key in sorted(ALLOWED_VAULT_SECRET_KEYS)
        ]

    def secret_status(self, *, profile: str, provider: str, key: str) -> dict[str, Any]:
        if not self.path.exists() or not self.path.is_file():
            return SecretStatus(
                configured=False,
                profile=profile,
                provider=provider,
                key=key,
            ).as_safe_dict()
        vault = self._vault if self._vault is not None else LocalSecretVault.load(self.path)
        return vault.status(profile=profile, provider=provider, key=key).as_safe_dict()

    def set_secret(self, *, profile: str, provider: str, key: str, value: str) -> dict[str, Any]:
        vault = self._require_unlocked_vault()
        return vault.set_secret(
            profile=profile,
            provider=provider,
            key=key,
            value=value,
            classification="secret",
        ).as_safe_dict()

    def delete_secret(self, *, profile: str, provider: str, key: str) -> dict[str, Any]:
        vault = self._require_unlocked_vault()
        try:
            return vault.delete_secret(profile=profile, provider=provider, key=key).as_safe_dict()
        except MissingSecretError:
            return SecretStatus(
                configured=False,
                profile=profile,
                provider=provider,
                key=key,
            ).as_safe_dict()

    def local_falcon_api_key_readiness(self, profile: str) -> dict[str, Any]:
        if not self.path.exists() or not self.path.is_file():
            return {"configured": False, "source": "missing", "locked": False}
        if self._vault is None or self._vault.locked:
            return {"configured": False, "source": "locked", "locked": True}
        status = self._vault.status(profile=profile, provider="local_falcon", key="api_key")
        return {
            "configured": status.configured,
            "source": "vault" if status.configured else "missing",
            "locked": False,
        }

    def _require_unlocked_vault(self) -> LocalSecretVault:
        if self._vault is None or self._vault.locked:
            raise VaultLockedError("vault is locked")
        return self._vault


def resolve_secret_vault_path(
    *,
    env: Mapping[str, str],
    explicit_path: Path | None = None,
) -> Path:
    if explicit_path is not None:
        return explicit_path
    override = str(env.get(IMPORTER_VAULT_PATH_ENV, "")).strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_VAULT_PATH


def resolve_local_profile_config_dir(
    *,
    env: Mapping[str, str] | None = None,
    explicit_dir: Path | None = None,
) -> Path:
    if explicit_dir is not None:
        return explicit_dir
    source_env = os.environ if env is None else env
    override = str(source_env.get(LOCAL_CONFIG_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    return DEFAULT_LOCAL_PROFILE_CONFIG_DIR


def resolve_profile_registry_path(
    *,
    env: Mapping[str, str] | None = None,
    explicit_path: Path | None = None,
) -> Path:
    if explicit_path is not None:
        return explicit_path
    source_env = os.environ if env is None else env
    override = str(source_env.get(PROFILE_REGISTRY_PATH_ENV) or "").strip()
    if override:
        return Path(override)
    return DEFAULT_PROFILE_REGISTRY


def resolve_form_fills_input_dir(
    *,
    env: Mapping[str, str] | None = None,
    explicit_dir: Path | None = None,
) -> Path:
    if explicit_dir is not None:
        return explicit_dir
    source_env = os.environ if env is None else env
    override = str(source_env.get(FORM_FILLS_INPUT_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    return ROOT / "inputs" / "local-real" / "form-fills"


def resolve_callrail_input_dir(
    *,
    env: Mapping[str, str] | None = None,
    explicit_dir: Path | None = None,
) -> Path:
    if explicit_dir is not None:
        return explicit_dir
    source_env = os.environ if env is None else env
    override = str(source_env.get(CALLRAIL_INPUT_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    return ROOT / "inputs" / "local-real" / "callrail"


def resolve_local_falcon_manifest_dir(
    *,
    env: Mapping[str, str] | None = None,
    explicit_dir: Path | None = None,
) -> Path:
    if explicit_dir is not None:
        return explicit_dir
    source_env = os.environ if env is None else env
    override = str(source_env.get(LOCAL_FALCON_MANIFEST_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    return ROOT / "local-falcon-manifests"


def resolve_dashboard_lab_fixture_target_dir(
    *,
    env: Mapping[str, str] | None = None,
    explicit_dir: Path | None = None,
) -> Path | None:
    if explicit_dir is not None:
        return explicit_dir
    source_env = os.environ if env is None else env
    override = str(source_env.get(DASHBOARD_LAB_FIXTURE_TARGET_DIR_ENV) or "").strip()
    if override:
        return Path(override)
    return None


def build_runtime_safety_status(env: Mapping[str, str]) -> dict[str, Any]:
    flags = {
        "profile_registry_override_active": _env_override_active(env, PROFILE_REGISTRY_PATH_ENV),
        "local_config_override_active": _env_override_active(env, LOCAL_CONFIG_DIR_ENV),
        "vault_override_active": _env_override_active(env, IMPORTER_VAULT_PATH_ENV),
        "form_fills_input_override_active": _env_override_active(env, FORM_FILLS_INPUT_DIR_ENV),
        "callrail_input_override_active": _env_override_active(env, CALLRAIL_INPUT_DIR_ENV),
        "local_falcon_manifest_dir_override_active": _env_override_active(env, LOCAL_FALCON_MANIFEST_DIR_ENV),
        "dashboard_lab_fixture_target_override_active": _env_override_active(env, DASHBOARD_LAB_FIXTURE_TARGET_DIR_ENV),
    }
    return {
        "mode": "qa_override" if any(flags.values()) else "default_local",
        "overrides": flags,
        "active_labels": [
            label
            for key, label in {
                "profile_registry_override_active": "Profile registry override active",
                "local_config_override_active": "Local config override active",
                "vault_override_active": "Vault override active",
                "form_fills_input_override_active": "Form Fills input override active",
                "callrail_input_override_active": "CallRail input override active",
                "dashboard_lab_fixture_target_override_active": "Fixture target override active",
            }.items()
            if flags[key]
        ],
        "guardrails": [
            "no raw paths returned",
            "no provider pulls or OAuth flows",
            "no portal publishing",
            "no dashboard-lab source edits",
        ],
    }


def _env_override_active(env: Mapping[str, str], name: str) -> bool:
    return bool(str(env.get(name) or "").strip())


def _require_allowed_vault_secret(*, provider: str, key: str) -> None:
    if (provider, key) not in ALLOWED_VAULT_SECRET_KEYS:
        raise HTTPException(status_code=400, detail="secret key is not allowed")


def _with_secret_vault_readiness(
    profile: DashboardLabProfile,
    local_config: Mapping[str, Any],
    safe_env: Mapping[str, str],
    secret_vault_state: SecretVaultApiState,
) -> dict[str, Any]:
    if "local_falcon" not in profile.data_sources:
        return dict(local_config)

    enriched = dict(local_config)
    providers = enriched.get("providers")
    if isinstance(providers, Mapping):
        providers = dict(providers)
        local_falcon_config = dict(providers.get("local_falcon") if isinstance(providers.get("local_falcon"), Mapping) else {})
        providers["local_falcon"] = local_falcon_config
        enriched["providers"] = providers
    else:
        local_falcon_config = dict(enriched.get("local_falcon") if isinstance(enriched.get("local_falcon"), Mapping) else {})
        enriched["local_falcon"] = local_falcon_config

    api_key_env = str(local_falcon_config.get("api_key_env") or "LOCAL_FALCON_API_KEY")
    env_configured = bool(str(safe_env.get(api_key_env, "")).strip())
    vault_readiness = secret_vault_state.local_falcon_api_key_readiness(profile.slug)
    vault_configured = bool(vault_readiness["configured"]) and not env_configured
    source = "env" if env_configured else str(vault_readiness["source"])
    configured = env_configured or vault_configured

    local_falcon_config["api_key_env_present"] = env_configured
    local_falcon_config["api_key_vault_configured"] = vault_configured
    local_falcon_config["api_key_vault_locked"] = source == "locked"
    local_falcon_config["api_key_present"] = configured
    local_falcon_config["api_key_configured"] = configured
    local_falcon_config["api_key_readiness_source"] = source

    missing = [
        item
        for item in _safe_string_list(local_falcon_config.get("_missing_config_items"))
        if "api key" not in item.lower() and "local_falcon_api_key" not in item.lower()
    ]
    if not configured:
        if source == "locked":
            missing.append("LOCAL_FALCON_API_KEY or unlock vault to check saved key")
        else:
            missing.append("LOCAL_FALCON_API_KEY or saved Local Falcon API key")
    local_falcon_config["_missing_config_items"] = missing
    return enriched


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _secret_vault_status(
    *,
    exists: bool,
    unlocked: bool,
    entries: list[dict[str, Any]],
    status: str = "ok",
    error: str = "",
) -> dict[str, Any]:
    return {
        "exists": exists,
        "unlocked": unlocked,
        "status": status,
        "error": error,
        "entries": entries,
        "entry_count": len(entries),
    }


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
    onboarding_status = build_onboarding_status(
        profile,
        safe_env=safe_env,
        local_config=local_config,
        audit_log_path=audit_log_path,
        output_report=report,
    )
    return {
        **serialize_profile_summary(profile, safe_env=safe_env, local_config=local_config),
        "paths": {
            "local_real_output_folder": str(profile.importer_output_folder),
            "dashboard_lab_local_fixture_folder": str(profile.dashboard_lab_local_fixture_folder),
        },
        "output_status": serialize_output_report(profile, report),
        "action_plan": build_action_plan(profile, safe_env=safe_env, local_config=local_config),
        "onboarding_status": onboarding_status,
        "guarded_import_sequence": guarded_import_sequence(profile),
        "last_actions": build_last_action_summary(profile, audit_log_path),
        "safety": {
            "read_only": True,
            "local_only": True,
            "real_output_ignored_path": "exports/local-real/",
            "dashboard_lab_local_fixtures_only": True,
        },
    }


async def store_local_file_upload(
    profile: DashboardLabProfile,
    provider: str,
    *,
    file: UploadFile,
    confirmed: bool,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    form_fills_input_dir: Path,
    callrail_input_dir: Path,
) -> dict[str, Any]:
    if provider not in LOCAL_FILE_UPLOAD_PROVIDERS:
        raise HTTPException(status_code=404, detail="local file provider not supported")
    if provider not in profile.data_sources:
        raise HTTPException(status_code=400, detail="provider is not enabled for this profile")
    if not confirmed:
        raise HTTPException(status_code=400, detail="local file upload requires confirmation")
    upload_name = _safe_upload_filename(file.filename)
    if Path(upload_name).suffix.lower() not in _local_file_upload_suffixes(provider):
        raise HTTPException(status_code=400, detail="local file type is not supported for this provider")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="local file is empty")
    if len(content) > LOCAL_FILE_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="local file is too large")

    provider_config = _provider_config(local_config, provider)
    target = _local_file_upload_target(
        profile,
        provider,
        provider_config,
        upload_name=upload_name,
        safe_env=safe_env,
        form_fills_input_dir=form_fills_input_dir,
        callrail_input_dir=callrail_input_dir,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    readiness = _provider_local_file_readiness(
        profile=profile,
        provider=provider,
        safe_env=safe_env,
        local_config=provider_config,
    )
    return {
        "profile": profile.slug,
        "provider": provider,
        "provider_label": PROVIDER_LABELS.get(provider, provider),
        "saved": True,
        "size_bucket": _upload_size_bucket(len(content)),
        "readiness": {
            "state": readiness["state"],
            "detected": readiness["detected"],
            "action_label": readiness["action_label"],
            "step_label": readiness["step_label"],
        },
    }


def _safe_upload_filename(filename: str | None) -> str:
    raw = str(filename or "").strip()
    if not raw or raw in {".", ".."}:
        raise HTTPException(status_code=400, detail="local file name is required")
    if "/" in raw or "\\" in raw or Path(raw).name != raw:
        raise HTTPException(status_code=400, detail="local file name must not contain a path")
    if raw.startswith("."):
        raise HTTPException(status_code=400, detail="local file name is not allowed")
    return raw


def _local_file_upload_suffixes(provider: str) -> set[str]:
    if provider == "local_falcon":
        return {".json"}
    if provider == "callrail":
        return {".csv"}
    return {".csv", ".json"}


def _local_file_upload_target(
    profile: DashboardLabProfile,
    provider: str,
    local_config: Mapping[str, Any],
    *,
    upload_name: str,
    safe_env: Mapping[str, str],
    form_fills_input_dir: Path,
    callrail_input_dir: Path,
) -> Path:
    if provider == "local_falcon":
        target = _resolve_local_falcon_manifest_path(profile, local_config, safe_env=safe_env)
        if target is None:
            target = resolve_local_falcon_manifest_dir(env=safe_env) / _default_local_upload_filename(profile, provider, upload_name)
        return target
    configured = _safe_local_input_filename(local_config)
    if provider == "form_fills":
        return _resolve_form_fills_input_file(
            input_root=form_fills_input_dir,
            input_file=configured or _default_local_upload_filename(profile, provider, upload_name),
        )["path"]
    return _resolve_callrail_input_file(
        input_root=callrail_input_dir,
        input_file=configured or _default_local_upload_filename(profile, provider, upload_name),
    )["path"]


def _default_local_upload_filename(profile: DashboardLabProfile, provider: str, upload_name: str) -> str:
    suffix = Path(upload_name).suffix.lower()
    if provider == "local_falcon":
        return f"{profile.slug}-local-falcon-manifest.json"
    if provider == "callrail":
        return f"{profile.slug}-callrail.csv"
    return f"{profile.slug}-form-fills{suffix if suffix in {'.csv', '.json'} else '.csv'}"


def _upload_size_bucket(size: int) -> str:
    if size <= 16 * 1024:
        return "small"
    if size <= 1024 * 1024:
        return "medium"
    return "large"


def build_onboarding_status(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    audit_log_path: Path = DEFAULT_AUDIT_LOG,
    output_report: Any | None = None,
) -> dict[str, Any]:
    report = output_report or validate_profile_output(profile)
    output_status = serialize_output_report(profile, report)
    provider_readiness = serialize_provider_readiness(profile, safe_env=safe_env, local_config=local_config)
    provider_readiness_map = {item["provider"]: item for item in provider_readiness}
    checklist = provider_setup_checklist(profile, env=dict(safe_env), local_config=dict(local_config))
    checklist_map = {item["provider_key"]: item for item in checklist}
    expected_files = {item["file"]: item for item in output_status["files"]}
    last_actions = build_last_action_summary(profile, audit_log_path)

    providers = [
        _onboarding_provider_status(
            profile,
            provider,
            provider_readiness=provider_readiness_map.get(provider),
            checklist_item=checklist_map.get(provider),
            output_files=expected_files,
        )
        for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills")
    ]
    enabled_provider_count = sum(1 for item in providers if item["enabled"])
    configured_provider_count = sum(1 for item in providers if item["enabled"] and item["config_state"] in {"Configured", "Configured via vault"})
    output_ready_count = sum(1 for item in providers if item["enabled"] and item["output_state"] == "Output exists")
    ready_for_copy_count = sum(1 for item in providers if item["enabled"] and item["copy_state"] == "Ready for dashboard-lab copy")
    local_config_state = _onboarding_local_config_state(checklist)
    vault_state = _onboarding_vault_state(local_config)
    try:
        safe_preview = build_safe_dashboard_lab_copy_preview(profile)["result"]
    except HTTPException:
        safe_preview = {"status": "not_ready", "eligible_count": 0, "items": []}
    history = read_action_runs(audit_log_path, profile_slug=profile.slug, limit=30)
    local_file_readiness = _build_local_file_readiness(
        profile=profile,
        safe_env=safe_env,
        local_config=local_config,
    )
    preflight = _build_onboarding_preflight(
        profile=profile,
        providers=providers,
        checklist=checklist_map,
        local_config=local_config,
        safe_env=safe_env,
        local_file_readiness=local_file_readiness,
    )
    execution = _build_execution_tracking(
        profile=profile,
        providers=providers,
        local_file_readiness=local_file_readiness,
        preflight=preflight,
        safe_preview=safe_preview,
        last_actions=last_actions,
        history_entries=history["entries"],
    )
    acceleration = _build_onboarding_acceleration(
        profile=profile,
        providers=providers,
        preflight=preflight,
        local_file_readiness=local_file_readiness,
        safe_preview=safe_preview,
        last_actions=last_actions,
        local_config_state=local_config_state["state"],
        vault_state=vault_state["state"],
        execution=execution,
    )
    next_action_stack = _onboarding_next_action_stack(acceleration=acceleration)
    next_safe_action = _build_next_safe_action(acceleration=acceleration, execution=execution)
    validation_state = _validation_status_state(
        folder_exists=output_status["folder_exists"],
        last_validation=last_actions.get("last_validation"),
    )
    dashboard_copy_state = _dashboard_copy_state(
        enabled_provider_count=enabled_provider_count,
        execution=execution,
        last_actions=last_actions,
    )
    command_center = _build_operator_command_center(
        profile=profile,
        providers=providers,
        local_config_state=local_config_state["state"],
        vault_state=vault_state["state"],
        local_file_readiness=local_file_readiness,
        validation_state=validation_state,
        dashboard_copy_state=dashboard_copy_state,
        execution=execution,
        acceleration=acceleration,
        next_safe_action=next_safe_action,
    )

    return {
        "profile": {
            "slug": profile.slug,
            "display_name": profile.display_name,
            "route": profile.dashboard_lab_route,
            "shell_state": "Profile shell created",
            "enabled_provider_count": enabled_provider_count,
            "configured_provider_count": configured_provider_count,
            "output_ready_count": output_ready_count,
            "ready_for_copy_count": ready_for_copy_count,
        },
        "local_config": local_config_state,
        "vault": vault_state,
        "validation": {
            "state": validation_state,
            "folder_exists": output_status["folder_exists"],
            "overall_ok": output_status["ok"],
            "last_validation": "Available" if last_actions["last_validation"] else "Not run",
            "warning_count": len(output_status["warnings"]),
        },
        "dashboard_copy": {
            "state": dashboard_copy_state,
            "ready_provider_count": ready_for_copy_count,
            "last_copy": "Available" if last_actions["last_copy"] else "Not run",
        },
        "providers": providers,
        "local_file_readiness": local_file_readiness,
        "preflight": preflight,
        "execution": execution,
        "acceleration": acceleration,
        "next_action_stack": next_action_stack,
        "next_safe_action": next_safe_action,
        "command_center": command_center,
        "operator_guidance": _real_operator_guidance(),
        "safety": {
            "read_only": True,
            "no_provider_execution": True,
            "no_fixture_copy": True,
            "no_secret_values": True,
            "no_file_contents": True,
        },
    }


def build_onboarding_completion_summary(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    audit_log_path: Path = DEFAULT_AUDIT_LOG,
) -> dict[str, Any]:
    report = validate_profile_output(profile)
    onboarding_status = build_onboarding_status(
        profile,
        safe_env=safe_env,
        local_config=local_config,
        audit_log_path=audit_log_path,
        output_report=report,
    )
    checklist = provider_setup_checklist(profile, env=dict(safe_env), local_config=dict(local_config))
    checklist_map = {item["provider_key"]: item for item in checklist}
    enabled_provider_labels = [
        PROVIDER_LABELS.get(provider, provider)
        for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills")
        if provider in profile.data_sources
    ]
    actions = _onboarding_action_catalog(profile, safe_env=safe_env, local_config=local_config)
    try:
        safe_preview = build_safe_dashboard_lab_copy_preview(profile)["result"]
    except HTTPException:
        safe_preview = {
            "status": "not_ready",
            "eligible_count": 0,
            "items": [],
            "guardrails": _safe_copy_guardrails(),
        }
    last_actions = build_last_action_summary(profile, audit_log_path)
    validation_last = _completion_action_label(last_actions.get("last_validation"))
    copy_last = _completion_action_label(last_actions.get("last_copy"))
    readiness_state = _completion_readiness_state(
        onboarding_status=onboarding_status,
        safe_preview=safe_preview,
        last_actions=last_actions,
    )
    completed_steps, incomplete_steps = _completion_steps(
        onboarding_status=onboarding_status,
        readiness_state=readiness_state,
        validation_last=validation_last,
        copy_last=copy_last,
    )
    blockers = _completion_blockers(
        profile=profile,
        onboarding_status=onboarding_status,
        checklist=checklist_map,
        safe_preview=safe_preview,
        last_actions=last_actions,
    )
    recommended_next_actions = _completion_recommended_actions(
        readiness_state=readiness_state,
        blockers=blockers,
        onboarding_status=onboarding_status,
        safe_preview=safe_preview,
    )
    final_checklist = _completion_final_checklist(
        profile=profile,
        onboarding_status=onboarding_status,
        last_actions=last_actions,
    )
    planned_live_actions = [
        action["label"]
        for action in actions
        if bool(action.get("external_api")) or str(action.get("label") or "").startswith("Future:")
    ]
    provider_outputs = [
        {
            "provider": provider["provider"],
            "label": provider["label"],
            "status": provider["output_state"],
        }
        for provider in onboarding_status["providers"]
        if provider["enabled"]
    ]
    execution = onboarding_status.get("execution", {})
    fixture_copy = {
        "state": onboarding_status["dashboard_copy"]["state"],
        "preview_state": safe_preview["status"],
        "eligible_file_count": int(safe_preview["eligible_count"]),
        "copied_file_count": int(
            (last_actions["last_copy"] or {}).get("file_counts", {}).get("copied", 0)
            + (last_actions["last_copy"] or {}).get("file_counts", {}).get("overwritten", 0)
        ),
        "last_copy": copy_last,
    }
    validation = {
        "state": onboarding_status["validation"]["state"],
        "last_validation": validation_last,
        "warning_count": onboarding_status["validation"]["warning_count"],
    }
    handoff_text = _build_operator_handoff_text(
        profile=profile,
        enabled_provider_labels=enabled_provider_labels,
        readiness_state=readiness_state,
        completed_steps=completed_steps,
        incomplete_steps=incomplete_steps,
        blockers=blockers,
        planned_live_actions=planned_live_actions,
        validation=validation,
        fixture_copy=fixture_copy,
        local_config=onboarding_status["local_config"],
        vault=onboarding_status["vault"],
        local_file_readiness=onboarding_status["local_file_readiness"],
        recommended_next_actions=recommended_next_actions,
    )
    return {
        "profile": {
            "slug": profile.slug,
            "display_name": profile.display_name,
            "route": profile.dashboard_lab_route,
            "readiness_state": readiness_state,
        },
        "enabled_provider_labels": enabled_provider_labels,
        "completed_steps": completed_steps,
        "incomplete_steps": incomplete_steps,
        "blockers": blockers,
        "local_config": onboarding_status["local_config"],
        "vault": onboarding_status["vault"],
        "provider_outputs": provider_outputs,
        "local_execution": execution,
        "validation": validation,
        "fixture_copy": fixture_copy,
        "dashboard_lab_readiness": {
            "state": readiness_state,
            "portal_publishing": "Separate manual workflow",
        },
        "planned_live_actions": planned_live_actions,
        "recommended_next_actions": recommended_next_actions,
        "final_checklist": final_checklist,
        "safety_notes": [
            "Local onboarding summary only. No provider execution, OAuth, portal publishing, or database mutation.",
            "Secrets stay in env or the encrypted vault and are never returned here.",
            "File contents, raw rows, phone numbers, caller names, transcripts, recordings, customer IDs, and OAuth material are excluded.",
            "Dashboard-lab readiness here means local fixture readiness only. Portal publishing is separate.",
        ],
        "operator_handoff_text": handoff_text,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _onboarding_provider_status(
    profile: DashboardLabProfile,
    provider: str,
    *,
    provider_readiness: Mapping[str, Any] | None,
    checklist_item: Mapping[str, Any] | None,
    output_files: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = provider in profile.data_sources
    expected_file = PROVIDER_OUTPUT_FILES.get(provider, "")
    output = output_files.get(expected_file)
    output_exists = bool(output.get("exists")) if isinstance(output, Mapping) else False
    readiness = provider_readiness or {}
    checklist = checklist_item or {}
    config_ready = bool(readiness.get("config_ready")) or str(checklist.get("status")) in {"ready", "output_available"}
    credential_source = str(checklist.get("credential_source") or "")
    vault_locked = provider == "local_falcon" and credential_source == "vault locked"
    vault_configured = provider == "local_falcon" and credential_source == "vault"

    if not enabled:
        config_state = "Not enabled"
        output_state = "Not applicable"
        validation_state = "Not applicable"
        copy_state = "Not applicable"
        next_step = "Enable this provider in the tracked profile registry before onboarding it."
    else:
        if vault_locked:
            config_state = "Vault locked"
        elif config_ready and vault_configured:
            config_state = "Configured via vault"
        elif config_ready:
            config_state = "Configured"
        else:
            config_state = "Needs config"
        output_state = "Output exists" if output_exists else "Output missing"
        validation_state = "Ready for validation" if output_exists else "Validation unknown"
        copy_state = "Ready for dashboard-lab copy" if str(checklist.get("dashboard_copy_readiness")) == "Ready" else "Output missing"
        next_step = str(checklist.get("safe_next_action") or checklist.get("blocked_reason") or "Review provider setup.")

    return {
        "provider": provider,
        "label": PROVIDER_LABELS.get(provider, provider),
        "enabled": enabled,
        "expected_output_file": expected_file,
        "config_state": config_state,
        "output_state": output_state,
        "validation_state": validation_state,
        "copy_state": copy_state,
        "next_step": next_step,
    }


def _build_onboarding_preflight(
    *,
    profile: DashboardLabProfile,
    providers: list[dict[str, Any]],
    checklist: Mapping[str, Mapping[str, Any]],
    local_config: Mapping[str, Any],
    safe_env: Mapping[str, str],
    local_file_readiness: list[dict[str, Any]],
) -> dict[str, Any]:
    file_readiness_map = {item["provider"]: item for item in local_file_readiness}
    rows = [
        _provider_preflight_row(
            profile=profile,
            provider_status=provider_status,
            checklist_item=checklist.get(str(provider_status["provider"]), {}),
            local_config=_provider_config(local_config, str(provider_status["provider"])),
            safe_env=safe_env,
            local_file_state=file_readiness_map.get(str(provider_status["provider"])),
        )
        for provider_status in providers
        if provider_status["enabled"]
    ]
    return {
        "state": "Complete" if rows and all(item["overall_state"] == "Complete" for item in rows) else "In progress",
        "providers": rows,
    }


def _provider_preflight_row(
    *,
    profile: DashboardLabProfile,
    provider_status: Mapping[str, Any],
    checklist_item: Mapping[str, Any],
    local_config: Mapping[str, Any],
    safe_env: Mapping[str, str],
    local_file_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    provider = str(provider_status["provider"])
    output_exists = str(provider_status["output_state"]) == "Output exists"
    config_state = str(provider_status["config_state"])
    validation_state = str(provider_status["validation_state"])
    credential_source = str(checklist_item.get("credential_source") or "")
    file_state = local_file_state or {}

    if provider == "ga4":
        checks = [
            {"label": "Config metadata", "status": "Complete" if config_state == "Configured" else "Needs local config"},
            {"label": "OAuth and env references", "status": "Complete" if config_state == "Configured" else "Needs local config"},
            {"label": "Live pull", "status": "Complete" if output_exists else "Planned live step"},
        ]
    elif provider == "gsc":
        site_present = bool(local_config.get("site_url")) or bool(local_config.get("site_url_configured"))
        checks = [
            {"label": "Config metadata", "status": "Complete" if config_state == "Configured" else "Needs local config"},
            {"label": "Site URL", "status": "Complete" if site_present else "Missing setup"},
            {"label": "Live pull", "status": "Complete" if output_exists else "Planned live step"},
        ]
    elif provider == "local_falcon":
        manifest_status = str(file_state.get("state") or "File not configured")
        secret_status = "Blocked" if credential_source == "Vault locked" else "Complete" if config_state in {"Configured", "Configured via vault"} else "Needs secret"
        checks = [
            {"label": "Manifest", "status": manifest_status},
            {"label": "Vault or env key", "status": secret_status},
            {
                "label": "Manifest validation",
                "status": "Complete" if output_exists else "Ready to validate manifest" if str(file_state.get("action_state")) == "ready" else "Missing setup",
            },
            {
                "label": "Fetch",
                "status": "Complete"
                if output_exists
                else "Planned live step"
                if str(file_state.get("action_state")) == "ready" and secret_status == "Complete"
                else "Missing setup",
            },
        ]
    elif provider == "google_ads_search":
        checks = [
            {"label": "Config metadata and env refs", "status": "Complete" if config_state == "Configured" else "Needs local config"},
            {"label": "Read-only reporting", "status": "Complete" if output_exists else "Planned live step"},
            {"label": "Mutation guardrail", "status": "Complete"},
        ]
    elif provider == "callrail":
        file_status = str(file_state.get("state") or "File not configured")
        checks = [
            {"label": "Local input file", "status": file_status},
            {
                "label": "Local import",
                "status": "Complete" if output_exists else "Ready to import" if str(file_state.get("action_state")) == "ready" else "Missing setup",
            },
        ]
    elif provider == "form_fills":
        file_status = str(file_state.get("state") or "File not configured")
        checks = [
            {"label": "Local input file", "status": file_status},
            {
                "label": "Local import",
                "status": "Complete" if output_exists else "Ready to import" if str(file_state.get("action_state")) == "ready" else "Missing setup",
            },
        ]
    else:
        checks = [{"label": "Setup", "status": "Missing setup"}]

    overall_state = (
        "Blocked" if any(item["status"] == "Blocked" for item in checks)
        else "Complete" if output_exists
        else "Ready for local step" if any(item["status"] in {"Ready for local step", "Ready to import", "Ready to validate manifest"} for item in checks)
        else "Planned live step" if any(item["status"] == "Planned live step" for item in checks)
        else "Missing setup"
    )
    next_step = "Validate existing output." if validation_state == "Ready for validation" and overall_state == "Complete" else str(provider_status["next_step"])
    return {
        "provider": provider,
        "label": str(provider_status["label"]),
        "overall_state": overall_state,
        "checks": checks,
        "next_step": next_step,
    }


def _build_local_file_readiness(
    *,
    profile: DashboardLabProfile,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider in ("local_falcon", "form_fills", "callrail"):
        if provider not in profile.data_sources:
            continue
        rows.append(
            _provider_local_file_readiness(
                profile=profile,
                provider=provider,
                safe_env=safe_env,
                local_config=_provider_config(local_config, provider),
            )
        )
    return rows


def _provider_local_file_readiness(
    *,
    profile: DashboardLabProfile,
    provider: str,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    if provider == "local_falcon":
        configured = _present(local_config.get("manifest_path")) or local_falcon_manifest_path(profile).exists()
        manifest_path = _resolve_local_falcon_manifest_path(profile, local_config, safe_env=safe_env)
        detected = bool(manifest_path and manifest_path.is_file())
        state = "File detected" if detected else "Configured local file not found" if configured else "File not configured"
        detail = "Ready to validate manifest." if detected else "Configured local manifest is not available in the approved location." if configured else "Add the local-only manifest filename or place the default manifest file."
        return {
            "provider": provider,
            "label": PROVIDER_LABELS.get(provider, provider),
            "state": state,
            "detail": detail,
            "configured": configured,
            "detected": detected,
            "action_state": "ready" if detected else "blocked",
            "action_label": "Ready to validate manifest" if detected else "Needs file",
            "step_label": "Validate Local Falcon manifest",
        }

    filename = _safe_local_input_filename(local_config)
    if provider == "form_fills":
        detected = _local_input_file_detected(
            provider=provider,
            safe_env=safe_env,
            input_file=filename,
        )
        detail = "Ready to import Form Fills." if detected else "Configured local file is not available in the approved input location." if filename else "Add the approved Form Fills local filename."
        return {
            "provider": provider,
            "label": PROVIDER_LABELS.get(provider, provider),
            "state": "File detected" if detected else "Configured local file not found" if filename else "File not configured",
            "detail": detail,
            "configured": bool(filename),
            "detected": detected,
            "action_state": "ready" if detected else "blocked",
            "action_label": "Ready to import" if detected else "Needs file",
            "step_label": "Import Form Fills",
        }

    detected = _local_input_file_detected(
        provider=provider,
        safe_env=safe_env,
        input_file=filename,
    )
    detail = "Ready to import CallRail." if detected else "Configured local file is not available in the approved input location." if filename else "Add the approved CallRail local filename."
    return {
        "provider": provider,
        "label": PROVIDER_LABELS.get(provider, provider),
        "state": "File detected" if detected else "Configured local file not found" if filename else "File not configured",
        "detail": detail,
        "configured": bool(filename),
        "detected": detected,
        "action_state": "ready" if detected else "blocked",
        "action_label": "Ready to import" if detected else "Needs file",
        "step_label": "Import CallRail",
    }


def _build_execution_tracking(
    *,
    profile: DashboardLabProfile,
    providers: list[dict[str, Any]],
    local_file_readiness: list[dict[str, Any]],
    preflight: Mapping[str, Any],
    safe_preview: Mapping[str, Any],
    last_actions: Mapping[str, Any],
    history_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    recent_results = [_recent_execution_result(entry) for entry in history_entries if _recent_execution_result(entry) is not None][:8]
    file_map = {item["provider"]: item for item in local_file_readiness}
    provider_map = {item["provider"]: item for item in providers}
    local_falcon_checks = {
        item["label"]: item["status"]
        for item in next((row for row in preflight.get("providers", []) if isinstance(row, Mapping) and row.get("provider") == "local_falcon"), {}).get("checks", [])
        if isinstance(item, Mapping)
    }
    manifest_action = _first_action(history_entries, "local_falcon.validate-manifest")
    form_fills_action = _first_action(history_entries, "form_fills.import-local")
    callrail_action = _first_action(history_entries, "callrail.import-local")
    preview_action = _first_action(history_entries, "dashboard_lab.preview-fixture-copy")
    validation_action = last_actions.get("last_validation")
    copy_action = last_actions.get("last_copy")
    any_output_exists = any(item["output_state"] == "Output exists" for item in providers if item["enabled"])
    validation_ok = _action_succeeded(validation_action)
    validation_failed = bool(validation_action) and str(validation_action.get("status") or "") != "ok"
    preview_ok = _action_succeeded(preview_action)
    copy_ok = _action_succeeded(copy_action)
    manifest_failed = bool(manifest_action) and not _action_succeeded(manifest_action)
    form_fills_failed = bool(form_fills_action) and not _action_succeeded(form_fills_action)
    callrail_failed = bool(callrail_action) and not _action_succeeded(callrail_action)

    steps = [
        _execution_step(
            step_id="local_falcon.validate-manifest",
            provider="local_falcon",
            label="Validate Local Falcon manifest",
            status="Failed" if manifest_failed else "Complete" if _action_succeeded(manifest_action) else "Ready now" if file_map.get("local_falcon", {}).get("detected") else "Needs file",
            detail="Latest manifest validation needs attention." if manifest_failed else "Latest manifest validation passed." if _action_succeeded(manifest_action) else "Run the local-only manifest validator before any live Local Falcon planning." if file_map.get("local_falcon", {}).get("detected") else "Place the local-only manifest in an approved manifest location or disposable QA override.",
            phase=_execution_phase(
                step_id="local_falcon.validate-manifest",
                status="Failed" if manifest_failed else "Complete" if _action_succeeded(manifest_action) else "Ready now" if file_map.get("local_falcon", {}).get("detected") else "Needs file",
            ),
            action=manifest_action,
        ),
        _execution_step(
            step_id="form_fills.import-local",
            provider="form_fills",
            label="Import Form Fills",
            status="Failed" if form_fills_failed else "Complete" if provider_map.get("form_fills", {}).get("output_state") == "Output exists" else "Ready now" if file_map.get("form_fills", {}).get("detected") else "Needs file",
            detail="The latest Form Fills import needs attention." if form_fills_failed else "Date-only Form Fills summary output is available." if provider_map.get("form_fills", {}).get("output_state") == "Output exists" else "Run the local-only Form Fills import from the approved input location." if file_map.get("form_fills", {}).get("detected") else "Add the approved Form Fills local file before import.",
            phase=_execution_phase(
                step_id="form_fills.import-local",
                status="Failed" if form_fills_failed else "Complete" if provider_map.get("form_fills", {}).get("output_state") == "Output exists" else "Ready now" if file_map.get("form_fills", {}).get("detected") else "Needs file",
            ),
            action=form_fills_action,
        ),
        _execution_step(
            step_id="callrail.import-local",
            provider="callrail",
            label="Import CallRail",
            status="Failed" if callrail_failed else "Complete" if provider_map.get("callrail", {}).get("output_state") == "Output exists" else "Ready now" if file_map.get("callrail", {}).get("detected") else "Needs file",
            detail="The latest CallRail import needs attention." if callrail_failed else "CallRail summary output is available." if provider_map.get("callrail", {}).get("output_state") == "Output exists" else "Run the local-only CallRail import from the approved input location." if file_map.get("callrail", {}).get("detected") else "Add the approved CallRail local file before import.",
            phase=_execution_phase(
                step_id="callrail.import-local",
                status="Failed" if callrail_failed else "Complete" if provider_map.get("callrail", {}).get("output_state") == "Output exists" else "Ready now" if file_map.get("callrail", {}).get("detected") else "Needs file",
            ),
            action=callrail_action,
        ),
        _execution_step(
            step_id="validate-output",
            provider="profile",
            label="Validate existing summaries",
            status="Blocked" if validation_failed else "Complete" if validation_ok else "Needs validation" if any_output_exists else "Output missing",
            detail="Latest validation failed and blocks dashboard-lab readiness." if validation_failed else "Local summary validation passed." if validation_ok else "Run the allowlisted local validator on the current dashboard summary output." if any_output_exists else "Create or update local summary output before validation.",
            phase=_execution_phase(
                step_id="validate-output",
                status="Blocked" if validation_failed else "Complete" if validation_ok else "Needs validation" if any_output_exists else "Output missing",
            ),
            action=validation_action,
        ),
        _execution_step(
            step_id="dashboard_lab.preview-fixture-copy",
            provider="dashboard_lab",
            label="Preview dashboard-lab fixture copy",
            status="Complete" if preview_ok or copy_ok else "Needs confirmation" if validation_ok and safe_preview.get("status") == "ready" else "Validation required",
            detail="Fixture preview is ready." if preview_ok or copy_ok else "Preview the guarded dashboard-lab copy set before copying." if validation_ok and safe_preview.get("status") == "ready" else "Validation must pass before previewing fixture copy.",
            phase=_execution_phase(
                step_id="dashboard_lab.preview-fixture-copy",
                status="Complete" if preview_ok or copy_ok else "Needs confirmation" if validation_ok and safe_preview.get("status") == "ready" else "Validation required",
            ),
            action=preview_action,
        ),
        _execution_step(
            step_id="dashboard_lab.copy-validated-fixtures",
            provider="dashboard_lab",
            label="Copy validated fixtures",
            status="Complete" if copy_ok else "Needs confirmation" if (preview_ok or (validation_ok and safe_preview.get("status") == "ready")) else "Validation required",
            detail="Validated summaries were copied to the guarded local fixture target." if copy_ok else "Copy only eligible validated summaries into guarded local fixtures." if (preview_ok or (validation_ok and safe_preview.get("status") == "ready")) else "Validation and preview must be ready before copying fixtures.",
            phase=_execution_phase(
                step_id="dashboard_lab.copy-validated-fixtures",
                status="Complete" if copy_ok else "Needs confirmation" if (preview_ok or (validation_ok and safe_preview.get("status") == "ready")) else "Validation required",
            ),
            action=copy_action,
        ),
        _execution_step(
            step_id="dashboard_lab_ready",
            provider="dashboard_lab",
            label="Dashboard-lab ready",
            status="Blocked" if validation_failed else "Complete" if copy_ok else "Needs confirmation" if (preview_ok or (validation_ok and safe_preview.get("status") == "ready")) else "In progress",
            detail="Local fixture copy is complete. Ready to open dashboard-lab manually." if copy_ok else "Validation failure must be resolved before dashboard-lab readiness." if validation_failed else "Complete validation, preview, and guarded copy to reach dashboard-lab ready state.",
            phase=_execution_phase(
                step_id="dashboard_lab_ready",
                status="Blocked" if validation_failed else "Complete" if copy_ok else "Needs confirmation" if (preview_ok or (validation_ok and safe_preview.get("status") == "ready")) else "In progress",
            ),
            action=copy_action,
        ),
    ]
    if local_falcon_checks.get("Vault or env key") == "Needs secret":
        steps.insert(
            1,
            _execution_step(
                step_id="local_falcon_key",
                provider="local_falcon",
                label="Add Local Falcon key",
                status="Needs secret",
                detail="Save the key through the local vault or make the env reference available.",
                phase="blocked",
                action=None,
            ),
        )
    return {
        "steps": steps,
        "recent_results": recent_results,
    }


def _execution_step(
    *,
    step_id: str,
    provider: str,
    label: str,
    status: str,
    detail: str,
    phase: str,
    action: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "provider": provider,
        "label": label,
        "status": status,
        "detail": detail,
        "phase": phase,
        "timestamp": str((action or {}).get("timestamp") or ""),
        "latest_result": _recent_execution_summary(action) if action else "",
    }


def _execution_phase(*, step_id: str, status: str) -> str:
    if status in {"Needs file", "Needs secret", "Blocked", "Output missing"}:
        return "blocked"
    if status == "Failed":
        return "failed"
    if status == "Ready now":
        return "ready_to_run"
    if status == "Needs validation":
        return "validation_required"
    if status == "Needs confirmation":
        return "copy_eligible" if step_id in {"dashboard_lab.preview-fixture-copy", "dashboard_lab.copy-validated-fixtures", "dashboard_lab_ready"} else "ready_to_run"
    if status == "Complete":
        if step_id == "local_falcon.validate-manifest":
            return "validated"
        if step_id in {"form_fills.import-local", "callrail.import-local"}:
            return "ran_successfully"
        if step_id == "validate-output":
            return "validated"
        if step_id == "dashboard_lab.preview-fixture-copy":
            return "copy_eligible"
        if step_id in {"dashboard_lab.copy-validated-fixtures", "dashboard_lab_ready"}:
            return "copied"
        return "validated"
    return "configured"


def _recent_execution_result(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    action_id = str(entry.get("action_id") or "")
    labels = {
        "local_falcon.validate-manifest": ("local_falcon", "Validate Local Falcon manifest"),
        "form_fills.import-local": ("form_fills", "Import Form Fills"),
        "callrail.import-local": ("callrail", "Import CallRail"),
        "validate-output": ("profile", "Validate existing summaries"),
        "dashboard_lab.preview-fixture-copy": ("dashboard_lab", "Preview dashboard-lab fixture copy"),
        "dashboard_lab.copy-validated-fixtures": ("dashboard_lab", "Copy validated fixtures"),
    }
    if action_id not in labels:
        return None
    provider, label = labels[action_id]
    return {
        "action_id": action_id,
        "provider": provider,
        "label": label,
        "status": str(entry.get("status") or ""),
        "timestamp": str(entry.get("timestamp") or ""),
        "summary": _recent_execution_summary(entry),
    }


def _recent_execution_summary(entry: Mapping[str, Any] | None) -> str:
    if not entry:
        return ""
    action_id = str(entry.get("action_id") or "")
    status = str(entry.get("status") or "")
    result_summary = entry.get("result_summary") if isinstance(entry.get("result_summary"), Mapping) else {}
    file_counts = entry.get("file_counts") if isinstance(entry.get("file_counts"), Mapping) else {}
    if action_id == "local_falcon.validate-manifest":
        return "Manifest validation passed." if status == "ok" else "Manifest validation needs attention."
    if action_id == "form_fills.import-local":
        return "Form Fills import completed." if status == "ok" else "Form Fills import needs attention."
    if action_id == "callrail.import-local":
        return "CallRail import completed." if status == "ok" else "CallRail import needs attention."
    if action_id == "validate-output":
        return "Local output validation passed." if status == "ok" else "Local output validation needs attention."
    if action_id == "dashboard_lab.preview-fixture-copy":
        eligible_count = result_summary.get("eligible_count")
        return f"Fixture preview ready for {eligible_count} file(s)." if status == "ok" and isinstance(eligible_count, int) else "Fixture preview updated."
    if action_id == "dashboard_lab.copy-validated-fixtures":
        copied = int(file_counts.get("copied", 0)) + int(file_counts.get("overwritten", 0))
        return f"Copied {copied} validated fixture file(s)." if status == "ok" else "Fixture copy needs attention."
    return ""


def _build_onboarding_acceleration(
    *,
    profile: DashboardLabProfile,
    providers: list[dict[str, Any]],
    preflight: Mapping[str, Any],
    local_file_readiness: list[dict[str, Any]],
    safe_preview: Mapping[str, Any],
    last_actions: Mapping[str, Any],
    local_config_state: str,
    vault_state: str,
    execution: Mapping[str, Any],
) -> dict[str, Any]:
    ready_statuses = {"Ready now", "Needs validation", "Needs confirmation"}
    blocked_statuses = {"Needs file", "Needs secret", "Blocked", "Validation required", "Output missing", "Failed"}
    ready_now = [
        _execution_action_item(item)
        for item in execution.get("steps", [])
        if isinstance(item, Mapping) and str(item.get("status")) in ready_statuses
    ]
    blocked = [
        _execution_action_item(item)
        for item in execution.get("steps", [])
        if isinstance(item, Mapping) and str(item.get("status")) in blocked_statuses
    ]
    ready_now.sort(key=_action_priority)
    blocked.sort(key=_action_priority)
    planned_live: list[dict[str, str]] = []
    preflight_rows = {item["provider"]: item for item in preflight.get("providers", []) if isinstance(item, Mapping)}

    if vault_state == "Vault locked":
        blocked.append(_next_action_item("vault_unlock", "Unlock local vault", "Blocked", "Unlock the local encrypted vault to confirm saved Local Falcon key metadata."))

    for provider, label in (("ga4", "GA4"), ("gsc", "GSC"), ("local_falcon", "Local Falcon"), ("google_ads_search", "Google Ads Search")):
        row = preflight_rows.get(provider)
        if not row or row.get("overall_state") == "Complete":
            continue
        if any(item.get("status") == "Planned live step" for item in row.get("checks", []) if isinstance(item, Mapping)):
            planned_live.append(_next_action_item(f"{provider}_planned", f"{label} live step planned or unavailable", "Planned live step", "Provider execution stays separately approved and is not run automatically here."))

    return {
        "ready_now": _dedupe_action_items(ready_now),
        "blocked": _dedupe_action_items(blocked),
        "planned_live": _dedupe_action_items(planned_live),
        "guidance": [
            _guidance_item("Ready now", ready_now),
            _guidance_item("Needs file", [item for item in blocked if item["status"] == "Needs file"]),
            _guidance_item("Needs validation", [item for item in ready_now if item["status"] == "Needs validation"]),
            _guidance_item("Needs confirmation", [item for item in ready_now if item["status"] == "Needs confirmation"]),
            _guidance_item("Failed", [item for item in blocked if item["status"] == "Failed"]),
            _guidance_item("Planned live step", planned_live),
        ],
    }


def _onboarding_next_action_stack(
    *,
    acceleration: Mapping[str, Any],
) -> dict[str, Any]:
    blocked = [item for item in acceleration.get("blocked", []) if isinstance(item, Mapping)]
    hard_blocked = [
        item
        for item in blocked
        if str(item.get("status") or "") in {"Needs file", "Needs secret", "Blocked"}
    ]
    deferred_blocked = [
        item
        for item in blocked
        if str(item.get("status") or "") in {"Output missing", "Validation required"}
    ]
    queue = _dedupe_action_items(
        hard_blocked
        + list(acceleration.get("ready_now", []))
        + deferred_blocked
        + list(acceleration.get("planned_live", []))
    )
    primary = queue[0] if queue else _next_action_item("review", "Review local readiness", "Complete", "All visible local onboarding gates are currently satisfied.")
    return {
        "primary": primary,
        "queue": queue[1:5],
    }


def _next_action_item(action_id: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {
        "id": action_id,
        "label": label,
        "status": status,
        "detail": detail,
    }


def _execution_action_item(step: Mapping[str, Any]) -> dict[str, str]:
    step_id = str(step.get("id") or "")
    status = str(step.get("status") or "")
    label = str(step.get("label") or "")
    detail = str(step.get("detail") or "")
    if step_id == "local_falcon.validate-manifest" and status == "Needs file":
        return _next_action_item(step_id, "Add Local Falcon manifest file", status, detail)
    if step_id == "local_falcon_key" and status == "Needs secret":
        return _next_action_item(step_id, "Add Local Falcon key", status, detail)
    if step_id == "callrail.import-local" and status == "Needs file":
        return _next_action_item(step_id, "Add CallRail local file", status, detail)
    if step_id == "form_fills.import-local" and status == "Needs file":
        return _next_action_item(step_id, "Add Form Fills local file", status, detail)
    if step_id == "validate-output" and status == "Failed":
        return _next_action_item(step_id, "Resolve validation failure", status, detail)
    return _next_action_item(step_id, label, status, detail)


def _action_priority(item: Mapping[str, Any]) -> tuple[int, str]:
    priorities = {
        "local_falcon.validate-manifest": 10,
        "local_falcon_key": 20,
        "callrail.import-local": 30 if str(item.get("status") or "") == "Needs file" else 50,
        "form_fills.import-local": 40 if str(item.get("status") or "") == "Needs file" else 40,
        "validate-output": 60,
        "dashboard_lab.preview-fixture-copy": 70,
        "dashboard_lab.copy-validated-fixtures": 80,
        "dashboard_lab_ready": 90,
        "vault_unlock": 95,
    }
    action_id = str(item.get("id") or "")
    return priorities.get(action_id, 999), action_id


def _dedupe_action_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    return deduped


def _guidance_item(label: str, items: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "label": label,
        "count": len(items),
        "active": bool(items),
    }


def _real_operator_guidance() -> list[str]:
    return [
        "Tracked profile is real.",
        "Local config writes ignored local config only.",
        "Secrets stay local.",
        "Imports and validation are local-only.",
        "Fixture copy remains confirmation-gated.",
        "Dashboard-lab source repo is not modified by this frontend.",
        "Portal publishing is separate.",
    ]


def _completion_readiness_state(
    *,
    onboarding_status: Mapping[str, Any],
    safe_preview: Mapping[str, Any],
    last_actions: Mapping[str, Any],
) -> str:
    local_config_state = str(onboarding_status["local_config"]["state"])
    validation_state = str(onboarding_status["validation"]["state"])
    copy_succeeded = _action_succeeded(last_actions.get("last_copy"))
    providers = onboarding_status["providers"]
    enabled_providers = [item for item in providers if item["enabled"]]
    file_readiness = {item["provider"]: item for item in onboarding_status.get("local_file_readiness", []) if isinstance(item, Mapping)}
    if not enabled_providers and local_config_state != "Configured":
        return "Not started"
    last_validation = last_actions.get("last_validation") or {}
    if str(last_validation.get("status") or "") == "failed":
        return "Blocked"
    if copy_succeeded:
        return "Dashboard-lab ready"
    if any(item.get("state") == "Configured local file not found" for item in file_readiness.values()):
        return "Blocked"
    if any(item["config_state"] in {"Needs config", "Vault locked"} for item in enabled_providers):
        return "Setup in progress"
    if (
        safe_preview.get("status") == "ready"
        and _action_succeeded(last_actions.get("last_validation"))
    ):
        return "Fixture copy ready"
    if (
        enabled_providers
        and all(item["output_state"] == "Output exists" for item in enabled_providers)
        and validation_state in {"Ready for validation", "Validation passed"}
    ):
        return "Local data ready"
    return "Setup in progress"


def _completion_steps(
    *,
    onboarding_status: Mapping[str, Any],
    readiness_state: str,
    validation_last: str,
    copy_last: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    local_config_state = str(onboarding_status["local_config"]["state"])
    vault_state = str(onboarding_status["vault"]["state"])
    providers = [item for item in onboarding_status["providers"] if item["enabled"]]
    output_ready = bool(providers) and all(item["output_state"] == "Output exists" for item in providers)
    fixture_preview_ready = readiness_state in {"Fixture copy ready", "Dashboard-lab ready"}
    checklist = [
        {"id": "profile_shell", "label": "Profile shell created", "status": "complete", "detail": "Tracked profile shell is saved."},
        {
            "id": "local_config",
            "label": "Local config saved",
            "status": "complete" if local_config_state == "Configured" else "pending",
            "detail": local_config_state,
        },
        {
            "id": "secrets",
            "label": "Secrets configured if needed",
            "status": "complete" if vault_state in {"Configured via vault", "Not configured"} else "pending",
            "detail": vault_state,
        },
        {
            "id": "local_imports",
            "label": "Local imports completed if enabled",
            "status": "complete" if output_ready else "pending",
            "detail": "Enabled local providers have summary output." if output_ready else "One or more enabled providers still need output.",
        },
        {
            "id": "validation",
            "label": "Validation completed",
            "status": "complete" if validation_last == "Available" else "pending",
            "detail": validation_last,
        },
        {
            "id": "fixture_preview",
            "label": "Fixture copy preview completed",
            "status": "complete" if fixture_preview_ready else "pending",
            "detail": readiness_state,
        },
        {
            "id": "fixture_copy",
            "label": "Fixture copy completed",
            "status": "complete" if copy_last == "Available" else "pending",
            "detail": copy_last,
        },
        {
            "id": "portal",
            "label": "Portal publishing separate",
            "status": "separate",
            "detail": "Handled outside the importer after local QA.",
        },
    ]
    completed = [item for item in checklist if item["status"] == "complete"]
    incomplete = [item for item in checklist if item["status"] != "complete"]
    return completed, incomplete


def _completion_blockers(
    *,
    profile: DashboardLabProfile,
    onboarding_status: Mapping[str, Any],
    checklist: Mapping[str, Any],
    safe_preview: Mapping[str, Any],
    last_actions: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    providers = [item for item in onboarding_status["providers"] if item["enabled"]]
    file_readiness = {item["provider"]: item for item in onboarding_status.get("local_file_readiness", []) if isinstance(item, Mapping)}
    execution_steps = {item["id"]: item for item in onboarding_status.get("execution", {}).get("steps", []) if isinstance(item, Mapping)}
    if onboarding_status["local_config"]["state"] != "Configured":
        blockers.append("Missing local config")
    if any(item["config_state"] == "Vault locked" for item in providers):
        blockers.append("Missing required secret")
    if file_readiness.get("local_falcon", {}).get("state") == "Configured local file not found":
        blockers.append("Configured Local Falcon manifest file not found")
    if file_readiness.get("form_fills", {}).get("state") == "Configured local file not found":
        blockers.append("Configured Form Fills local file not found")
    if file_readiness.get("callrail", {}).get("state") == "Configured local file not found":
        blockers.append("Configured CallRail local file not found")
    if any(item["output_state"] != "Output exists" for item in providers):
        blockers.append("Output missing")
    last_validation = last_actions.get("last_validation") or {}
    if not last_validation:
        blockers.append("Validation not run")
    elif str(last_validation.get("status") or "") == "failed":
        blockers.append("Validation failed")
    if str(execution_steps.get("dashboard_lab.preview-fixture-copy", {}).get("status") or "") == "Validation required":
        blockers.append("Fixture preview requires validation")
    elif safe_preview.get("status") != "ready":
        blockers.append("Fixture preview required")
    if not _action_succeeded(last_actions.get("last_copy")):
        blockers.append("Fixture copy not completed")
    if any(
        str(checklist.get(provider, {}).get("status") or "") == "planned"
        for provider in ("ga4", "gsc", "local_falcon", "google_ads_search")
        if provider in profile.data_sources
    ):
        blockers.append("Live provider action planned/unavailable")
    return _dedupe_strings(blockers)


def _completion_recommended_actions(
    *,
    readiness_state: str,
    blockers: list[str],
    onboarding_status: Mapping[str, Any],
    safe_preview: Mapping[str, Any],
) -> list[str]:
    if blockers:
        return blockers[:3]
    if readiness_state == "Dashboard-lab ready":
        return [
            "Review the copied local dashboard-lab fixtures.",
            "Hand off the operator summary.",
            "Handle portal publishing separately.",
        ]
    if readiness_state == "Fixture copy ready":
        return [
            "Confirm the guarded fixture copy step.",
            "Refresh the completion summary after copy.",
            "Prepare the operator handoff.",
        ]
    if safe_preview.get("status") == "ready":
        return [
            "Run the guarded fixture copy.",
            "Refresh the completion summary.",
            "Prepare the operator handoff.",
        ]
    if onboarding_status["validation"]["last_validation"] != "Available":
        return [
            "Run validation on the current local output.",
            "Refresh the completion summary.",
        ]
    return ["Continue local setup and refresh the completion summary."]


def _validation_status_state(
    *,
    folder_exists: bool,
    last_validation: Mapping[str, Any] | None,
) -> str:
    if last_validation and str(last_validation.get("status") or "") == "failed":
        return "Validation failed"
    if _action_succeeded(last_validation):
        return "Validation passed"
    return "Ready for validation" if folder_exists else "Validation unknown"


def _dashboard_copy_state(
    *,
    enabled_provider_count: int,
    execution: Mapping[str, Any],
    last_actions: Mapping[str, Any],
) -> str:
    if not enabled_provider_count:
        return "Not applicable"
    if _action_succeeded(last_actions.get("last_validation")) and _action_succeeded(last_actions.get("last_copy")):
        return "Dashboard-lab ready"
    steps = {item["id"]: item for item in execution.get("steps", []) if isinstance(item, Mapping)}
    copy_status = str(steps.get("dashboard_lab.copy-validated-fixtures", {}).get("status") or "")
    preview_status = str(steps.get("dashboard_lab.preview-fixture-copy", {}).get("status") or "")
    validation_status = str(steps.get("validate-output", {}).get("status") or "")
    if copy_status == "Needs confirmation":
        return "Ready to copy validated fixtures"
    if preview_status == "Needs confirmation":
        return "Ready to preview dashboard-lab fixture copy"
    if validation_status == "Blocked":
        return "Blocked by validation"
    if validation_status == "Needs validation":
        return "Validation required"
    return "Output missing"


def _build_next_safe_action(
    *,
    acceleration: Mapping[str, Any],
    execution: Mapping[str, Any],
) -> dict[str, Any] | None:
    ready_now = [item for item in acceleration.get("ready_now", []) if isinstance(item, Mapping)]
    if not ready_now:
        return None
    primary = ready_now[0]
    action_id = str(primary.get("id") or "")
    if action_id not in {
        "local_falcon.validate-manifest",
        "form_fills.import-local",
        "callrail.import-local",
        "validate-output",
        "dashboard_lab.preview-fixture-copy",
        "dashboard_lab.copy-validated-fixtures",
    }:
        return None
    steps = {item["id"]: item for item in execution.get("steps", []) if isinstance(item, Mapping)}
    step = steps.get(action_id, {})
    return {
        "action_id": action_id,
        "label": str(primary.get("label") or ""),
        "status": str(primary.get("status") or ""),
        "detail": str(primary.get("detail") or ""),
        "provider": str(step.get("provider") or ""),
        "phase": str(step.get("phase") or ""),
        "requires_confirmation": action_id in {"form_fills.import-local", "callrail.import-local", "dashboard_lab.copy-validated-fixtures"},
        "auto_chain": False,
    }


def _build_operator_command_center(
    *,
    profile: DashboardLabProfile,
    providers: list[dict[str, Any]],
    local_config_state: str,
    vault_state: str,
    local_file_readiness: list[dict[str, Any]],
    validation_state: str,
    dashboard_copy_state: str,
    execution: Mapping[str, Any],
    acceleration: Mapping[str, Any],
    next_safe_action: Mapping[str, Any] | None,
) -> dict[str, Any]:
    enabled_providers = [item for item in providers if item["enabled"]]
    execution_steps = {item["id"]: item for item in execution.get("steps", []) if isinstance(item, Mapping)}
    file_items = [item for item in local_file_readiness if isinstance(item, Mapping)]
    detected_file_count = sum(1 for item in file_items if bool(item.get("detected")))
    file_blocker_count = sum(1 for item in file_items if not bool(item.get("detected")))
    output_ready_count = sum(1 for item in enabled_providers if item["output_state"] == "Output exists")
    local_falcon_enabled = any(item["provider"] == "local_falcon" for item in enabled_providers)
    local_falcon_key_step = execution_steps.get("local_falcon_key")

    if local_falcon_key_step:
        secret_state = "Needs secret"
        secret_detail = "Local Falcon key status needs attention."
    elif local_falcon_enabled:
        secret_state = "Known"
        secret_detail = "Local Falcon key status is known for this local session."
    else:
        secret_state = "Not required"
        secret_detail = "Local Falcon is not enabled for this profile."

    if not file_items:
        local_file_state = "Not required"
        local_file_detail = "No local-only input files are required for enabled providers."
    elif file_blocker_count:
        local_file_state = "Blocked"
        local_file_detail = f"{file_blocker_count} approved local input check(s) still need attention."
    else:
        local_file_state = "Detected"
        local_file_detail = f"{detected_file_count} approved local input check(s) are ready."

    ready_now = [item for item in acceleration.get("ready_now", []) if isinstance(item, Mapping)]
    blocked = [item for item in acceleration.get("blocked", []) if isinstance(item, Mapping)]
    planned_live = [item for item in acceleration.get("planned_live", []) if isinstance(item, Mapping)]
    dashboard_ready = dashboard_copy_state == "Dashboard-lab ready"
    next_step_label = str((next_safe_action or {}).get("label") or (blocked[0].get("label") if blocked else "Review local readiness"))
    next_step_detail = str(
        (next_safe_action or {}).get("detail")
        or (blocked[0].get("detail") if blocked else "All visible local onboarding gates are currently satisfied.")
    )

    return {
        "headline": f"{profile.display_name} local onboarding command center",
        "readiness_state": "Dashboard-lab ready" if dashboard_ready else "Blocked" if blocked else "Ready for local action" if ready_now else "In progress",
        "next_step_label": next_step_label,
        "next_step_detail": next_step_detail,
        "metrics": [
            {"label": "Enabled providers", "value": str(len(enabled_providers)), "tone": "neutral"},
            {"label": "Outputs ready", "value": f"{output_ready_count}/{len(enabled_providers)}", "tone": "ok" if enabled_providers and output_ready_count == len(enabled_providers) else "warn"},
            {"label": "Ready now", "value": str(len(ready_now)), "tone": "ok" if ready_now else "neutral"},
            {"label": "Blocked", "value": str(len(blocked)), "tone": "warn" if blocked else "ok"},
            {"label": "Planned live", "value": str(len(planned_live)), "tone": "neutral"},
        ],
        "ladder": [
            {"label": "Profile verified", "status": "Complete", "detail": "Tracked profile shell is saved.", "tone": "ok"},
            {"label": "Local config saved", "status": local_config_state, "detail": "Ignored local config only.", "tone": _command_center_tone(local_config_state)},
            {"label": "Local Falcon key status", "status": secret_state, "detail": secret_detail, "tone": _command_center_tone(secret_state)},
            {"label": "Local file readiness", "status": local_file_state, "detail": local_file_detail, "tone": _command_center_tone(local_file_state)},
            {"label": "Ready local actions", "status": "Ready now" if ready_now else "None ready", "detail": f"{len(ready_now)} safe local step(s) currently runnable.", "tone": "ok" if ready_now else "neutral"},
            {"label": "Local imports", "status": "Complete" if enabled_providers and output_ready_count == len(enabled_providers) else "Waiting on output", "detail": "Enabled provider summary outputs are present." if enabled_providers and output_ready_count == len(enabled_providers) else "One or more enabled providers still need local output.", "tone": "ok" if enabled_providers and output_ready_count == len(enabled_providers) else "warn"},
            {"label": "Validation", "status": validation_state, "detail": str(execution_steps.get("validate-output", {}).get("detail") or "Validation state is tracked without file contents."), "tone": _command_center_tone(validation_state)},
            {"label": "Fixture preview", "status": str(execution_steps.get("dashboard_lab.preview-fixture-copy", {}).get("status") or "Not ready"), "detail": str(execution_steps.get("dashboard_lab.preview-fixture-copy", {}).get("detail") or "Preview is required before guarded copy."), "tone": _command_center_tone(str(execution_steps.get("dashboard_lab.preview-fixture-copy", {}).get("status") or ""))},
            {"label": "Fixture copy", "status": str(execution_steps.get("dashboard_lab.copy-validated-fixtures", {}).get("status") or "Not ready"), "detail": str(execution_steps.get("dashboard_lab.copy-validated-fixtures", {}).get("detail") or "Guarded fixture copy remains confirmation-gated."), "tone": _command_center_tone(str(execution_steps.get("dashboard_lab.copy-validated-fixtures", {}).get("status") or ""))},
            {"label": "Dashboard-lab ready", "status": dashboard_copy_state, "detail": "Ready to open dashboard-lab manually." if dashboard_ready else "Portal publishing remains separate.", "tone": _command_center_tone(dashboard_copy_state)},
        ],
        "lanes": {
            "ready_now": ready_now[:4],
            "blocked": blocked[:4],
            "planned_live": planned_live[:4],
        },
    }


def _command_center_tone(status: str) -> str:
    normalized = status.lower()
    if "unknown" in normalized:
        return "neutral"
    if any(token in normalized for token in ("complete", "configured", "detected", "known", "ready", "passed", "copied")):
        return "ok"
    if any(token in normalized for token in ("missing", "needs", "blocked", "failed", "waiting", "required", "not found", "output missing")):
        return "warn"
    return "neutral"


def _completion_final_checklist(
    *,
    profile: DashboardLabProfile,
    onboarding_status: Mapping[str, Any],
    last_actions: Mapping[str, Any],
) -> list[dict[str, str]]:
    providers = [item for item in onboarding_status["providers"] if item["enabled"]]
    output_ready = bool(providers) and all(item["output_state"] == "Output exists" for item in providers)
    validation_last = _completion_action_label(last_actions.get("last_validation"))
    copy_last = _completion_action_label(last_actions.get("last_copy"))
    return [
        {"label": "Profile shell created", "status": "complete", "detail": profile.dashboard_lab_route},
        {
            "label": "Local config saved",
            "status": "complete" if onboarding_status["local_config"]["state"] == "Configured" else "pending",
            "detail": str(onboarding_status["local_config"]["state"]),
        },
        {
            "label": "Secrets configured if needed",
            "status": "complete" if onboarding_status["vault"]["state"] != "Vault locked" else "pending",
            "detail": str(onboarding_status["vault"]["state"]),
        },
        {
            "label": "Local imports completed if enabled",
            "status": "complete" if output_ready else "pending",
            "detail": "Ready" if output_ready else "Waiting on output",
        },
        {
            "label": "Validation completed",
            "status": "complete" if _action_succeeded(last_actions.get("last_validation")) else "pending",
            "detail": validation_last,
        },
        {
            "label": "Fixture copy completed",
            "status": "complete" if _action_succeeded(last_actions.get("last_copy")) else "pending",
            "detail": copy_last,
        },
        {
            "label": "Dashboard-lab ready",
            "status": "complete" if _action_succeeded(last_actions.get("last_copy")) else "pending",
            "detail": str(onboarding_status["dashboard_copy"]["state"]),
        },
        {
            "label": "Portal publishing separate",
            "status": "separate",
            "detail": "Manual follow-up outside this tool.",
        },
    ]


def _build_operator_handoff_text(
    *,
    profile: DashboardLabProfile,
    enabled_provider_labels: list[str],
    readiness_state: str,
    completed_steps: list[dict[str, str]],
    incomplete_steps: list[dict[str, str]],
    blockers: list[str],
    planned_live_actions: list[str],
    validation: Mapping[str, Any],
    fixture_copy: Mapping[str, Any],
    local_config: Mapping[str, Any],
    vault: Mapping[str, Any],
    local_file_readiness: list[dict[str, Any]],
    recommended_next_actions: list[str],
) -> str:
    execution_completed = [
        item["label"]
        for item in completed_steps
        if item["id"] in {"local_imports", "validation", "fixture_preview", "fixture_copy"}
    ]
    lines = [
        f"Operator handoff: {profile.display_name} ({profile.slug})",
        f"Dashboard-lab route: {profile.dashboard_lab_route}",
        f"Current readiness: {readiness_state}",
        f"Enabled providers: {', '.join(enabled_provider_labels) if enabled_provider_labels else 'none'}",
        "",
        "Completed local steps:",
    ]
    lines.extend(f"- {item['label']}: {item['detail']}" for item in completed_steps)
    if execution_completed:
        lines.append("")
        lines.append("Completed local execution:")
        lines.extend(f"- {item}" for item in execution_completed)
    detected_files = sum(1 for item in local_file_readiness if bool(item.get("detected")))
    blocked_files = sum(1 for item in local_file_readiness if not bool(item.get("detected")))
    lines.append("")
    lines.append("Local setup status:")
    lines.append(f"- Local config: {local_config['state']}")
    lines.append(f"- Local Falcon key status: {vault['local_falcon_api_key_metadata']}")
    lines.append(f"- Approved local files: {detected_files} detected, {blocked_files} needing attention")
    lines.append("")
    lines.append("Still pending:")
    lines.extend(f"- {item['label']}: {item['detail']}" for item in incomplete_steps)
    lines.append("")
    lines.append(f"Validation status: {validation['state']} ({validation['last_validation']})")
    lines.append(f"Fixture copy status: {fixture_copy['state']} ({fixture_copy['last_copy']})")
    if fixture_copy["state"] == "Dashboard-lab ready":
        lines.append("Dashboard-lab local review: Ready to open dashboard-lab manually.")
    if blockers:
        lines.append("")
        lines.append("Current blockers:")
        lines.extend(f"- {item}" for item in blockers)
    if planned_live_actions:
        lines.append("")
        lines.append("Planned or unavailable live actions:")
        lines.extend(f"- {item}" for item in planned_live_actions)
    lines.append("")
    lines.append("Recommended next actions:")
    lines.extend(f"- {item}" for item in recommended_next_actions)
    lines.append("")
    lines.append("Portal publishing is separate from this local importer workflow.")
    lines.append("Live provider pulls, OAuth, fixture copies beyond the guarded local target, and portal publishing are not run automatically by this completed local workflow.")
    return "\n".join(lines)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _action_succeeded(action: Mapping[str, Any] | None) -> bool:
    return bool(action) and str(action.get("status") or "") == "ok"


def _completion_action_label(action: Mapping[str, Any] | None) -> str:
    if not action:
        return "Not run"
    return "Available" if _action_succeeded(action) else "Failed"


def _onboarding_local_config_state(checklist: list[dict[str, Any]]) -> dict[str, Any]:
    visible_items = [item for item in checklist if item.get("status") != "not_enabled"]
    present_count = sum(1 for item in visible_items if item.get("local_config_file_present"))
    valid = all(bool(item.get("local_config_valid", True)) for item in visible_items)
    if present_count:
        state = "Configured" if valid else "Needs config"
    else:
        state = "Needs config"
    labels = sorted({str(item.get("local_config_path_label") or "") for item in visible_items if item.get("local_config_path_label")})
    return {
        "state": state,
        "configured_provider_count": present_count,
        "path_labels": labels[:3],
    }


def _onboarding_vault_state(local_config: Mapping[str, Any]) -> dict[str, Any]:
    local_falcon_config = _provider_config(local_config, "local_falcon")
    source = str(local_falcon_config.get("api_key_readiness_source") or "")
    configured = bool(local_falcon_config.get("api_key_vault_configured"))
    locked = bool(local_falcon_config.get("api_key_vault_locked")) or source == "locked"
    if locked:
        state = "Vault locked"
    elif configured:
        state = "Configured via vault"
    else:
        state = "Not configured"
    return {
        "state": state,
        "local_falcon_api_key_metadata": "configured" if configured else "not configured",
        "locked": locked,
    }


def build_onboarding_actions(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    actions = _onboarding_action_catalog(profile, safe_env=safe_env, local_config=local_config)
    return {
        "profile": profile.slug,
        "actions": actions,
        "groups": [
            {
                "provider": provider,
                "label": PROVIDER_LABELS.get(provider, provider),
                "actions": [action for action in actions if action["provider"] == provider],
            }
            for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills", "profile", "dashboard_lab")
        ],
        "safety": _onboarding_action_safety(),
    }


def preview_onboarding_action(
    profile: DashboardLabProfile,
    action_id: str,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    action = _find_onboarding_action(
        profile,
        action_id,
        safe_env=safe_env,
        local_config=local_config,
    )
    return {
        "profile": profile.slug,
        "action": action,
        "preview": {
            "status": "available" if action["available"] else "unavailable",
            "would_run": bool(action["available"] and not action["writes_files"]),
            "message": "Ready to run read-only local check." if action["available"] else action["unavailable_reason"],
        },
        "safety": _onboarding_action_safety(),
    }


def run_onboarding_action(
    profile: DashboardLabProfile,
    action_id: str,
    *,
    confirmed: bool,
    input_file: str | None = None,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
    form_fills_input_dir: Path | None = None,
    callrail_input_dir: Path | None = None,
    audit_log_path: Path | None = None,
) -> dict[str, Any]:
    action = _find_onboarding_action(
        profile,
        action_id,
        safe_env=safe_env,
        local_config=local_config,
    )
    if action["writes_files"] and not confirmed:
        raise HTTPException(status_code=400, detail="onboarding action requires explicit confirmation")
    if not action["available"]:
        if action["kind"] == "validate_existing_output":
            result = _run_onboarding_output_check(profile, action["provider"])
        elif action["kind"] == "local_falcon_validate_manifest":
            result = _run_local_falcon_manifest_validation(
                profile,
                local_config=_provider_config(local_config, "local_falcon"),
                safe_env=safe_env,
            )
        else:
            result = {
                "status": "unavailable",
                "message": action["unavailable_reason"] or "This onboarding action is not available yet.",
            }
        return {
            "profile": profile.slug,
            "action": action,
            "result": result,
            "safety": _onboarding_action_safety(),
        }
    if action["kind"] == "readiness_check":
        result = _run_onboarding_readiness_check(profile, action["provider"], safe_env=safe_env, local_config=local_config)
    elif action["kind"] == "validate_existing_output":
        result = _run_onboarding_output_check(profile, action["provider"])
    elif action["kind"] == "local_falcon_validate_manifest":
        result = _run_local_falcon_manifest_validation(
            profile,
            local_config=_provider_config(local_config, "local_falcon"),
            safe_env=safe_env,
        )
    elif action["kind"] == "dashboard_lab_copy_preview":
        result = build_safe_dashboard_lab_copy_preview(profile)["result"]
    elif action["kind"] == "dashboard_lab_copy_validated":
        result = run_safe_dashboard_lab_copy_action(profile, audit_log_path=audit_log_path or DEFAULT_AUDIT_LOG)["result"]
    elif action["kind"] == "profile_validate_output":
        validation = run_validate_output_action(profile, audit_log_path=audit_log_path or DEFAULT_AUDIT_LOG)
        result = {
            "status": "passed" if validation["status"] == "ok" else "failed",
            "message": "Local output validation passed." if validation["status"] == "ok" else "Local output validation failed.",
            "warning_count": len(validation["result"]["warnings"]),
            "missing_required_file_count": len(validation["result"]["missing_required_files"]),
            "malformed_json_file_count": len(validation["result"]["malformed_json_files"]),
        }
    elif action["kind"] == "form_fills_import_local":
        result = _run_form_fills_import_action(
            profile,
            input_file=input_file,
            input_root=form_fills_input_dir or resolve_form_fills_input_dir(env=safe_env),
            local_config=_provider_config(local_config, "form_fills"),
        )
    elif action["kind"] == "callrail_import_local":
        result = _run_callrail_import_action(
            profile,
            input_file=input_file,
            input_root=callrail_input_dir or resolve_callrail_input_dir(env=safe_env),
            local_config=_provider_config(local_config, "callrail"),
        )
    else:
        return {
            "profile": profile.slug,
            "action": action,
            "result": {
                "status": "unavailable",
                "message": "This onboarding action is planned but not runnable in this milestone.",
            },
            "safety": _onboarding_action_safety(),
        }
    audit = _write_onboarding_action_audit(
        profile=profile,
        action=action,
        result=result,
        audit_log_path=audit_log_path or DEFAULT_AUDIT_LOG,
    )
    return {
        "profile": profile.slug,
        "action": action,
        "result": result,
        "audit": audit,
        "safety": _onboarding_action_safety(),
    }


def _onboarding_action_catalog(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    status = build_onboarding_status(profile, safe_env=safe_env, local_config=local_config)
    provider_status = {item["provider"]: item for item in status["providers"]}
    actions: list[dict[str, Any]] = []
    for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills"):
        current = provider_status[provider]
        enabled = bool(current["enabled"])
        validation_target = _onboarding_validation_target(profile, provider)
        validation_unavailable_reason = _onboarding_validation_unavailable_reason(
            enabled=enabled,
            validation_target=validation_target,
        )
        actions.append(
            _onboarding_action(
                action_id=f"{provider}-check-readiness",
                provider=provider,
                kind="readiness_check",
                label="Refresh local readiness",
                description=_onboarding_readiness_description(provider),
                available=enabled,
                unavailable_reason="" if enabled else "Provider is not enabled for this profile.",
                read_only=True,
                writes_files=False,
                external_api=False,
                fixture_copy=False,
                requires_confirmation=False,
            )
        )
        actions.append(
            _onboarding_action(
                action_id=f"{provider}-validate-existing-output",
                provider=provider,
                kind="validate_existing_output",
                label="Validate existing output",
                description="Run the allowlisted local validator for existing output without returning file contents.",
                available=enabled and validation_unavailable_reason == "",
                unavailable_reason=validation_unavailable_reason,
                read_only=True,
                writes_files=False,
                external_api=False,
                fixture_copy=False,
                requires_confirmation=False,
            )
        )
        if provider == "local_falcon":
            manifest_validation_reason = _local_falcon_manifest_validation_unavailable_reason(
                profile,
                local_config=_provider_config(local_config, "local_falcon"),
                enabled=enabled,
                safe_env=safe_env,
            )
            actions.append(
                _onboarding_action(
                    action_id="local_falcon.validate-manifest",
                    provider=provider,
                    kind="local_falcon_validate_manifest",
                    label="Validate Local Falcon manifest",
                    description="Validate the local-only Local Falcon manifest structure without fetching provider data or returning manifest contents.",
                    available=enabled and manifest_validation_reason == "",
                    unavailable_reason=manifest_validation_reason,
                    read_only=True,
                    writes_files=False,
                    external_api=False,
                    fixture_copy=False,
                    requires_confirmation=False,
                )
            )
        if provider == "form_fills":
            actions.append(
                _onboarding_action(
                    action_id="form_fills.import-local",
                    provider=provider,
                    kind="form_fills_import_local",
                    label="Import local date-only form fills",
                    description="Import an existing date-only CSV or JSON from the allowed local Form Fills input folder.",
                    available=enabled,
                    unavailable_reason="" if enabled else "Provider is not enabled for this profile.",
                    read_only=False,
                    writes_files=True,
                    external_api=False,
                    fixture_copy=False,
                    requires_confirmation=True,
                )
            )
        if provider == "callrail":
            actions.append(
                _onboarding_action(
                    action_id="callrail.import-local",
                    provider=provider,
                    kind="callrail_import_local",
                    label="Import local aggregate CallRail export",
                    description="Import an existing local CallRail CSV export into aggregate dashboard output.",
                    available=enabled,
                    unavailable_reason="" if enabled else "Provider is not enabled for this profile.",
                    read_only=False,
                    writes_files=True,
                    external_api=False,
                    fixture_copy=False,
                    requires_confirmation=True,
                )
            )
        actions.append(_future_onboarding_action(provider))
    actions.append(
        _onboarding_action(
            action_id="validate-output",
            provider="profile",
            kind="profile_validate_output",
            label="Validate existing summaries",
            description="Run the allowlisted local validator across the current dashboard summary output without returning file contents.",
            available=True,
            unavailable_reason="",
            read_only=True,
            writes_files=False,
            external_api=False,
            fixture_copy=False,
            requires_confirmation=False,
        )
    )
    actions.append(
        _onboarding_action(
            action_id="dashboard_lab.preview-fixture-copy",
            provider="dashboard_lab",
            kind="dashboard_lab_copy_preview",
            label="Preview dashboard-lab fixture copy",
            description="Preview allowlisted validated summaries that are eligible for dashboard-lab local fixtures.",
            available=True,
            unavailable_reason="",
            read_only=True,
            writes_files=False,
            external_api=False,
            fixture_copy=True,
            requires_confirmation=False,
        )
    )
    safe_preview = build_safe_dashboard_lab_copy_preview(profile)
    copy_available = any(item["eligible"] for item in safe_preview["result"]["items"])
    actions.append(
        _onboarding_action(
            action_id="dashboard_lab.copy-validated-fixtures",
            provider="dashboard_lab",
            kind="dashboard_lab_copy_validated",
            label="Copy validated fixtures",
            description="Copy only eligible validated summary JSON files to the guarded dashboard-lab local fixture target.",
            available=copy_available,
            unavailable_reason="" if copy_available else "No validated dashboard-lab summary files are ready to copy.",
            read_only=False,
            writes_files=True,
            external_api=False,
            fixture_copy=True,
            requires_confirmation=True,
        )
    )
    return actions


def _onboarding_action(
    *,
    action_id: str,
    provider: str,
    kind: str,
    label: str,
    description: str,
    available: bool,
    unavailable_reason: str,
    read_only: bool,
    writes_files: bool,
    external_api: bool,
    fixture_copy: bool,
    requires_confirmation: bool,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "provider": provider,
        "provider_label": PROVIDER_LABELS.get(provider, provider),
        "kind": kind,
        "label": label,
        "description": description,
        "status": "available" if available else "unavailable",
        "available": available,
        "unavailable_reason": unavailable_reason,
        "requires_confirmation": requires_confirmation,
        "read_only": read_only,
        "local_only": not external_api,
        "writes_files": writes_files,
        "external_api": external_api,
        "fixture_copy": fixture_copy,
    }


def _onboarding_readiness_description(provider: str) -> str:
    if provider == "google_ads_search":
        return (
            "Refresh read-only Google Ads Search reporting readiness. "
            "No campaign, budget, bid, keyword, ad, asset, conversion, or account-setting mutations."
        )
    return "Refresh safe setup, local file readiness, output readiness, and next-step metadata."


def _future_onboarding_action(provider: str) -> dict[str, Any]:
    labels = {
        "ga4": "Future: Pull GA4 data",
        "gsc": "Future: Pull GSC data",
        "local_falcon": "Future: Fetch Local Falcon scans",
        "google_ads_search": "Future: Fetch read-only reporting",
        "callrail": "Future: Import aggregate export",
        "form_fills": "Future: Import date-only form fills",
    }
    return _onboarding_action(
        action_id=f"{provider}-future-run",
        provider=provider,
        kind="future_provider_run",
        label=labels.get(provider, "Future provider action"),
        description="Planned provider execution is visible for sequencing but disabled in this milestone.",
        available=False,
        unavailable_reason="Not available yet. Future provider execution remains disabled.",
        read_only=False,
        writes_files=True,
        external_api=provider in {"ga4", "gsc", "local_falcon", "google_ads_search"},
        fixture_copy=False,
        requires_confirmation=True,
    )


def _find_onboarding_action(
    profile: DashboardLabProfile,
    action_id: str,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    actions = _onboarding_action_catalog(profile, safe_env=safe_env, local_config=local_config)
    for action in actions:
        if action["id"] == action_id:
            return action
    raise HTTPException(status_code=404, detail="onboarding action not found")


def _run_onboarding_readiness_check(
    profile: DashboardLabProfile,
    provider: str,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    status = build_onboarding_status(profile, safe_env=safe_env, local_config=local_config)
    provider_status = next(item for item in status["providers"] if item["provider"] == provider)
    file_state = next((item for item in status.get("local_file_readiness", []) if item["provider"] == provider), None)
    return {
        "status": "ok",
        "message": "Readiness checked.",
        "provider": provider,
        "config_state": provider_status["config_state"],
        "output_state": provider_status["output_state"],
        "validation_state": provider_status["validation_state"],
        "copy_state": provider_status["copy_state"],
        "next_step": provider_status["next_step"],
        "local_file_state": file_state["state"] if file_state else "",
        "local_file_action": file_state["action_label"] if file_state else "",
    }


def _run_onboarding_output_check(profile: DashboardLabProfile, provider: str) -> dict[str, Any]:
    target = _onboarding_validation_target(profile, provider)
    if target is None:
        return {
            "status": "unavailable",
            "message": "Validation is not available yet for this provider.",
            "provider": provider,
            "file": PROVIDER_OUTPUT_FILES.get(provider, ""),
            "error": "validator_unavailable",
        }
    if not target["script_path"].is_file():
        return {
            "status": "unavailable",
            "message": "Validation is not available yet for this provider.",
            "provider": provider,
            "file": target["file"],
            "error": "validator_unavailable",
        }
    if not target["input_path"].is_file():
        return {
            "status": "unavailable",
            "message": "Expected local validation input is missing.",
            "provider": provider,
            "file": target["file"],
            "exists": False,
            "error": "missing_output",
        }

    metadata = _safe_local_file_metadata(target["input_path"], target["file"])
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(target["script_path"]),
                target["argument"],
                str(target["input_path"]),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=LOCAL_VALIDATION_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "message": "Validation timed out.",
            "provider": provider,
            "file": target["file"],
            "error": "validator_timeout",
            **metadata,
        }
    status = "passed" if completed.returncode == 0 else "failed"
    message = "Validation passed." if completed.returncode == 0 else "Validation failed."
    return {
        "status": status,
        "message": message,
        "provider": provider,
        "file": target["file"],
        "validator": "allowlisted_local_validator",
        "return_code": completed.returncode,
        **metadata,
    }


def _onboarding_validation_target(profile: DashboardLabProfile, provider: str) -> dict[str, Any] | None:
    target = PROVIDER_VALIDATION_TARGETS.get(provider)
    if target is None:
        return None
    file_label = str(target["file"])
    return {
        "script_path": target["script"],
        "argument": str(target["argument"]),
        "input_path": profile.importer_output_folder / file_label,
        "file": file_label,
    }


def _onboarding_validation_unavailable_reason(*, enabled: bool, validation_target: dict[str, Any] | None) -> str:
    if not enabled:
        return "Provider is not enabled for this profile."
    if validation_target is None or not validation_target["script_path"].is_file():
        return "Validation is not available yet for this provider."
    if not validation_target["input_path"].is_file():
        return "Expected local validation input is missing."
    return ""


def _local_falcon_manifest_validation_unavailable_reason(
    profile: DashboardLabProfile,
    *,
    local_config: Mapping[str, Any],
    enabled: bool,
    safe_env: Mapping[str, str],
) -> str:
    if not enabled:
        return "Provider is not enabled for this profile."
    manifest_path = _resolve_local_falcon_manifest_path(profile, local_config, safe_env=safe_env)
    if manifest_path is None:
        return "Local Falcon manifest is missing or outside the allowed local manifest locations."
    if not manifest_path.is_file():
        return "Expected local Local Falcon manifest is missing."
    return ""


def _run_local_falcon_manifest_validation(
    profile: DashboardLabProfile,
    *,
    local_config: Mapping[str, Any],
    safe_env: Mapping[str, str],
) -> dict[str, Any]:
    manifest_path = _resolve_local_falcon_manifest_path(profile, local_config, safe_env=safe_env)
    if manifest_path is None:
        return {
            "status": "unavailable",
            "message": "Local Falcon manifest is missing or outside the allowed local manifest locations.",
            "provider": "local_falcon",
        }
    if not manifest_path.is_file():
        return {
            "status": "unavailable",
            "message": "Expected local Local Falcon manifest is missing.",
            "provider": "local_falcon",
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "message": "Manifest JSON is invalid.",
            "provider": "local_falcon",
        }
    except OSError:
        return {
            "status": "failed",
            "message": "Manifest could not be read safely.",
            "provider": "local_falcon",
        }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "message": "Manifest must contain a JSON object.",
            "provider": "local_falcon",
        }
    validation = validate_local_falcon_manifest(payload, profile=profile.slug, manifest_path=manifest_path)
    return {
        "status": "passed" if validation.safe_to_process else "failed",
        "message": "Manifest validation passed." if validation.safe_to_process else "Manifest validation failed.",
        "provider": "local_falcon",
        "report_count": validation.report_count,
        "report_source_counts": dict(validation.report_source_counts),
        "planned_source_counts": dict(validation.planned_source_counts),
        "missing_report_ids": validation.missing_report_ids,
        "duplicate_report_ids": validation.duplicate_report_ids,
        "duplicate_source_query_pairs": validation.duplicate_source_query_pairs,
        "planned_missing_report_ids": validation.planned_missing_report_ids,
        "google_ai_overview_pending_prompts": validation.google_ai_overview_pending_prompts,
        "warning_count": len(validation.warnings),
        "error_count": len(validation.errors),
        "safe_to_process": validation.safe_to_process,
    }


def _safe_local_file_metadata(path: Path, file_label: str) -> dict[str, Any]:
    metadata = {
        "exists": path.is_file(),
        "json_valid": None,
        "schema_version": None,
        "size": None,
        "last_modified": None,
    }
    if not metadata["exists"]:
        return metadata
    try:
        stat = path.stat()
        metadata["size"] = stat.st_size
        metadata["last_modified"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        metadata["json_valid"] = False
        return metadata
    except OSError:
        metadata["json_valid"] = False
        return metadata
    metadata["json_valid"] = isinstance(payload, dict)
    if isinstance(payload, dict) and isinstance(payload.get("schema_version"), str):
        metadata["schema_version"] = payload["schema_version"]
    return metadata


def _run_form_fills_import_action(
    profile: DashboardLabProfile,
    *,
    input_file: str | None,
    input_root: Path,
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_input = _resolve_form_fills_input_file(
        input_root=input_root,
        input_file=input_file or _safe_local_input_filename(local_config),
    )
    if not resolved_input["path"].is_file():
        return {
            "status": "input_missing",
            "message": "Input missing.",
            "provider": "form_fills",
            "input_file": resolved_input["label"],
            "output_file": "form-fills-summary.json",
            "error": "input_missing",
        }

    output_target = _form_fills_output_target(profile)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_form_fills.py"),
        "--profile",
        profile.slug,
        "--input",
        str(resolved_input["path"]),
        "--output-root",
        output_target["argument"],
    ]
    if output_target["real_output"]:
        command.append("--real-output")
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=LOCAL_IMPORT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "message": "Import timed out.",
            "provider": "form_fills",
            "input_file": resolved_input["label"],
            "output_file": "form-fills-summary.json",
            "error": "import_timeout",
        }
    if completed.returncode != 0:
        return {
            "status": "rejected",
            "message": "Unsafe input rejected." if resolved_input["path"].is_file() else "Input missing.",
            "provider": "form_fills",
            "input_file": resolved_input["label"],
            "output_file": "form-fills-summary.json",
            "error": "import_failed",
            "return_code": completed.returncode,
        }

    validation = _run_onboarding_output_check(profile, "form_fills")
    summary = _safe_form_fills_summary(output_target["output_path"])
    validation_passed = validation.get("status") == "passed"
    return {
        "status": "ok" if validation_passed else "failed",
        "message": "Form Fills import completed. Validation passed." if validation_passed else "Form Fills import completed. Validation failed.",
        "provider": "form_fills",
        "input_file": resolved_input["label"],
        "output_file": "form-fills-summary.json",
        "validation_status": validation.get("status"),
        "validation_message": validation.get("message"),
        **summary,
    }


def _resolve_form_fills_input_file(*, input_root: Path, input_file: str | None) -> dict[str, Any]:
    raw = str(input_file or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="form fills input file is required")
    candidate = Path(raw)
    root = _absolute_path(input_root)
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve(strict=False)
    try:
        label = resolved.relative_to(root.resolve(strict=False)).as_posix()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="form fills input must stay under the allowed local input folder") from exc
    if not label or label.startswith("../") or "/../" in label:
        raise HTTPException(status_code=400, detail="form fills input must stay under the allowed local input folder")
    if resolved.suffix.lower() not in {".csv", ".json"}:
        raise HTTPException(status_code=400, detail="form fills input must be a CSV or JSON file")
    return {"path": resolved, "label": label}


def _form_fills_output_target(profile: DashboardLabProfile) -> dict[str, Any]:
    output_folder = _absolute_path(profile.importer_output_folder)
    if output_folder.name != profile.slug:
        raise HTTPException(status_code=400, detail="form fills output folder must match the selected profile")
    output_root = output_folder.parent.resolve(strict=False)
    output_posix = output_root.as_posix()
    if "/public/fixtures/" in output_posix or output_posix.endswith("/public/fixtures"):
        raise HTTPException(status_code=400, detail="form fills output must not target committed dashboard-lab fixtures")
    if "/public/local-fixtures/" in output_posix or output_posix.endswith("/public/local-fixtures"):
        raise HTTPException(status_code=400, detail="form fills import does not write dashboard-lab local fixtures")

    real_root = (ROOT / "exports" / "local-real" / "dashboard-lab").resolve(strict=False)
    real_output = _is_relative_to(output_root, real_root)
    argument = output_root
    if real_output:
        argument = Path(os.path.relpath(output_root, ROOT))
    return {
        "argument": str(argument),
        "real_output": real_output,
        "output_path": output_folder / "form-fills-summary.json",
    }


def _safe_form_fills_summary(path: Path) -> dict[str, Any]:
    metadata = _safe_local_file_metadata(path, "form-fills-summary.json")
    summary: dict[str, Any] = {
        "total_form_fills": None,
        "date_count": None,
        "date_range_start": None,
        "date_range_end": None,
        **metadata,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return summary
    if not isinstance(payload, dict):
        return summary
    payload_summary = payload.get("summary")
    if isinstance(payload_summary, dict):
        summary["total_form_fills"] = payload_summary.get("total_form_fills")
    time_series = payload.get("time_series")
    if isinstance(time_series, list):
        summary["date_count"] = len(time_series)
    date_range = payload.get("date_range")
    if isinstance(date_range, dict):
        summary["date_range_start"] = date_range.get("start_date")
        summary["date_range_end"] = date_range.get("end_date")
    return summary


def _run_callrail_import_action(
    profile: DashboardLabProfile,
    *,
    input_file: str | None,
    input_root: Path,
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_input = _resolve_callrail_input_file(
        input_root=input_root,
        input_file=input_file or _safe_local_input_filename(local_config),
    )
    if not resolved_input["path"].is_file():
        return {
            "status": "input_missing",
            "message": "Input missing.",
            "provider": "callrail",
            "input_file": resolved_input["label"],
            "output_file": "callrail-summary.json",
            "error": "input_missing",
        }

    output_target = _callrail_output_target(profile)
    output_target["cwd"].mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "import_callrail_export.py"),
                "--profile",
                profile.slug,
                "--input",
                str(resolved_input["path"]),
                "--output-root",
                output_target["argument"],
                "--real-output",
            ],
            cwd=output_target["cwd"],
            env=env,
            capture_output=True,
            text=True,
            timeout=LOCAL_IMPORT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "message": "Import timed out.",
            "provider": "callrail",
            "input_file": resolved_input["label"],
            "output_file": "callrail-summary.json",
            "error": "import_timeout",
        }
    if completed.returncode != 0:
        return {
            "status": "rejected",
            "message": "Unsafe input rejected." if resolved_input["path"].is_file() else "Input missing.",
            "provider": "callrail",
            "input_file": resolved_input["label"],
            "output_file": "callrail-summary.json",
            "error": "import_failed",
            "return_code": completed.returncode,
        }

    validation = _run_onboarding_output_check(profile, "callrail")
    summary = _safe_callrail_summary(output_target["output_path"])
    validation_passed = validation.get("status") == "passed"
    return {
        "status": "ok" if validation_passed else "failed",
        "message": "CallRail import completed. Validation passed." if validation_passed else "CallRail import completed. Validation failed.",
        "provider": "callrail",
        "input_file": resolved_input["label"],
        "output_file": "callrail-summary.json",
        "validation_status": validation.get("status"),
        "validation_message": validation.get("message"),
        **summary,
    }


def _resolve_callrail_input_file(*, input_root: Path, input_file: str | None) -> dict[str, Any]:
    raw = str(input_file or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="CallRail input file is required")
    candidate = Path(raw)
    root = _absolute_path(input_root)
    resolved = candidate if candidate.is_absolute() else root / candidate
    resolved = resolved.resolve(strict=False)
    try:
        label = resolved.relative_to(root.resolve(strict=False)).as_posix()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="CallRail input must stay under the allowed local input folder") from exc
    if not label or label.startswith("../") or "/../" in label:
        raise HTTPException(status_code=400, detail="CallRail input must stay under the allowed local input folder")
    if resolved.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="CallRail input must be a CSV file")
    return {"path": resolved, "label": label}


def _callrail_output_target(profile: DashboardLabProfile) -> dict[str, Any]:
    output_folder = _absolute_path(profile.importer_output_folder)
    if output_folder.name != profile.slug:
        raise HTTPException(status_code=400, detail="CallRail output folder must match the selected profile")
    output_root = output_folder.parent.resolve(strict=False)
    output_posix = output_root.as_posix()
    if "/public/fixtures/" in output_posix or output_posix.endswith("/public/fixtures"):
        raise HTTPException(status_code=400, detail="CallRail output must not target committed dashboard-lab fixtures")
    if "/public/local-fixtures/" in output_posix or output_posix.endswith("/public/local-fixtures"):
        raise HTTPException(status_code=400, detail="CallRail import does not write dashboard-lab local fixtures")

    marker = Path("exports") / "local-real" / "dashboard-lab"
    marker_parts = marker.parts
    parts = output_root.parts
    for index in range(0, len(parts) - len(marker_parts) + 1):
        if parts[index : index + len(marker_parts)] == marker_parts:
            cwd = Path(*parts[:index]) if index else Path.cwd()
            return {
                "argument": marker.as_posix(),
                "cwd": cwd,
                "output_path": output_folder / "callrail-summary.json",
            }
    raise HTTPException(status_code=400, detail="CallRail output must stay under exports/local-real/dashboard-lab")


def _safe_callrail_summary(path: Path) -> dict[str, Any]:
    metadata = _safe_local_file_metadata(path, "callrail-summary.json")
    summary: dict[str, Any] = {
        "total_calls": None,
        "google_ads_calls": None,
        "answered_calls": None,
        "missed_calls": None,
        "qualified_calls": None,
        "date_range_start": None,
        "date_range_end": None,
        **metadata,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return summary
    if not isinstance(payload, dict):
        return summary
    payload_summary = payload.get("summary")
    if isinstance(payload_summary, dict):
        for key in ("total_calls", "google_ads_calls", "answered_calls", "missed_calls", "qualified_calls"):
            summary[key] = payload_summary.get(key)
    date_range = payload.get("date_range")
    if isinstance(date_range, dict):
        summary["date_range_start"] = date_range.get("start_date")
        summary["date_range_end"] = date_range.get("end_date")
    return summary


def _absolute_path(path: Path) -> Path:
    return path.resolve(strict=False) if path.is_absolute() else (ROOT / path).resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _onboarding_action_safety() -> dict[str, bool]:
    return {
        "no_live_api_calls": True,
        "no_provider_execution": True,
        "no_fixture_copy": True,
        "no_secret_values": True,
        "no_file_contents": True,
    }


def build_action_plan(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    provider_config = {
        provider: _provider_config(local_config, provider)
        for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills")
    }
    provider_actions = [
        _ga4_action(profile, safe_env=safe_env, local_config=provider_config["ga4"]),
        _gsc_action(profile, safe_env=safe_env, local_config=provider_config["gsc"]),
        _local_falcon_action(profile, safe_env=safe_env, local_config=provider_config["local_falcon"]),
        _google_ads_action(profile, safe_env=safe_env, local_config=provider_config["google_ads_search"]),
        _callrail_action(profile, local_config=provider_config["callrail"]),
        _form_fills_action(profile, local_config=provider_config["form_fills"]),
    ]
    return {
        "profile_slug": profile.slug,
        "guarded_import_sequence": guarded_import_sequence(profile),
        "actions": [
            action
            for action in provider_actions
            if action["readiness"].get("enabled")
        ] + [
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


def _google_ads_action(
    profile: DashboardLabProfile,
    *,
    safe_env: Mapping[str, str],
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "google_ads_search" in profile.data_sources
    customer_present = _present(safe_env.get("MUSIMACK_GOOGLE_ADS_CUSTOMER_ID")) or _any_present(
        local_config,
        ("customer_id", "google_ads_customer_id", "customer_id_env_present", "customer_id_configured"),
    )
    auth_present = _any_present(
        local_config,
        (
            "oauth_client_secrets",
            "oauth_token_file",
            "credentials_configured",
            "developer_token_env_present",
            "oauth_client_secrets_env_present",
            "oauth_token_file_env_present",
        ),
    ) or (
        _present(safe_env.get("GOOGLE_ADS_DEVELOPER_TOKEN"))
        and _present(safe_env.get("GOOGLE_ADS_OAUTH_CLIENT_SECRETS"))
        and _present(safe_env.get("GOOGLE_ADS_OAUTH_TOKEN_FILE"))
    )
    missing = []
    if not enabled:
        missing.append("Google Ads Search is not enabled for this profile")
    if enabled and not customer_present:
        missing.append("Google Ads customer id in ignored local config or shell")
    if enabled and not auth_present:
        missing.append("Google Ads developer token and local OAuth/client credentials")
    status = "ready" if enabled and customer_present and auth_present else "blocked_missing_config"
    blocked_reason = None if status == "ready" else "Google Ads Search needs local read-only API configuration before export."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "Google Ads Search is not enabled for this profile."
    return _action(
        action_id="google-ads-search-read-only-export",
        label="Export Google Ads Search local-real output",
        provider="google_ads_search",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            "\n".join(
                [
                    f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output --dry-run",
                    f"python scripts/fetch_google_ads_api.py --profile {profile.slug} --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output",
                    f'python scripts/validate_google_ads_summary.py --input "{profile.importer_output_folder / "google-ads-summary.json"}"',
                ]
            )
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "google-ads-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "Read-only GoogleAdsService/search reporting only.",
            "No campaign, budget, bid, keyword, ad, asset, conversion, or account-setting mutations.",
            "Credential values and customer IDs must stay in ignored local config or environment only.",
        ],
        manual_step="Run dry-run first, then run the read-only export only after operator approval.",
        readiness={
            "enabled": enabled,
            "customer_id_configured": customer_present,
            "local_auth_configured": auth_present,
            "read_only_exporter_available": True,
        },
    )


def _callrail_action(
    profile: DashboardLabProfile,
    *,
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "callrail" in profile.data_sources
    input_present = _any_present(
        local_config,
        ("input_csv", "calls_csv", "source_csv", "callrail_export_csv", "input_path", "local_input_filename"),
    )
    missing = []
    if not enabled:
        missing.append("CallRail is not enabled for this profile")
    if enabled and not input_present:
        missing.append("ignored CallRail calls CSV")
    status = "ready" if enabled and input_present else "blocked_missing_config"
    blocked_reason = None if status == "ready" else "CallRail needs an ignored local CSV before aggregate import."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "CallRail is not enabled for this profile."
    input_path = f"inputs/local-real/callrail/{profile.slug}/calls.csv"
    return _action(
        action_id="callrail-csv-import",
        label="Import CallRail aggregate local-real output",
        provider="callrail",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            "\n".join(
                [
                    f'python scripts/diagnose_callrail_export_shape.py --profile {profile.slug} --input "{input_path}"',
                    f'python scripts/import_callrail_export.py --profile {profile.slug} --input "{input_path}" --start-date YYYY-MM-DD --end-date YYYY-MM-DD --real-output',
                    f'python scripts/validate_callrail_summary.py --input "{profile.importer_output_folder / "callrail-summary.json"}"',
                ]
            )
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "callrail-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "Reads an ignored local CSV only.",
            "Writes aggregate callrail-summary.json without caller names, phone numbers, recordings, transcripts, or raw rows.",
            "No CallRail API call is made by this CSV import path.",
        ],
        manual_step="Place the CSV under inputs/local-real/callrail/{profile}/, diagnose shape, then import aggregate output.",
        readiness={
            "enabled": enabled,
            "ignored_csv_configured": input_present,
            "aggregate_importer_available": True,
        },
    )


def _form_fills_action(
    profile: DashboardLabProfile,
    *,
    local_config: Mapping[str, Any],
) -> dict[str, Any]:
    enabled = "form_fills" in profile.data_sources
    input_present = _any_present(
        local_config,
        ("input_csv", "input_json", "forms_csv", "form_fills_csv", "source_csv", "input_path", "local_input_filename"),
    )
    missing = []
    if not enabled:
        missing.append("Form Fills are not enabled for this profile")
    if enabled and not input_present:
        missing.append("ignored date-only form fills CSV or JSON")
    status = "ready" if enabled and input_present else "blocked_missing_config"
    blocked_reason = None if status == "ready" else "Form Fills need an ignored date-only local input before import."
    if not enabled:
        status = "blocked_not_enabled"
        blocked_reason = "Form Fills are not enabled for this profile."
    input_path = f"inputs/local-real/form-fills/{profile.slug}/form-fills.csv"
    return _action(
        action_id="form-fills-date-only-import",
        label="Import date-only Form Fills local-real output",
        provider="form_fills",
        status=status,
        blocked_reason=blocked_reason,
        command=(
            "\n".join(
                [
                    f'python scripts/import_form_fills.py --profile {profile.slug} --input "{input_path}" --real-output',
                    f'python scripts/validate_form_fills_summary.py --input "{profile.importer_output_folder / "form-fills-summary.json"}"',
                ]
            )
            if enabled
            else ""
        ),
        expected_output=str(profile.importer_output_folder / "form-fills-summary.json"),
        missing_inputs=missing,
        safety_notes=[
            "Input must be date-only.",
            "Names, emails, phone numbers, messages, IP addresses, and raw form payloads are rejected.",
            "No live API call is made by this local importer.",
        ],
        manual_step="Create an ignored date-only form-fill input, import it locally, then validate the summary.",
        readiness={
            "enabled": enabled,
            "date_only_input_configured": input_present,
            "date_only_importer_available": True,
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
        [f'New-Item -ItemType Directory -Force "{destination}" | Out-Null']
        + [
            f'Copy-Item "{source / filename}" "{destination / filename}" -Force'
            for filename in _expected_dashboard_files_for_profile(profile)
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


def build_safe_dashboard_lab_copy_preview(profile: DashboardLabProfile) -> dict[str, Any]:
    _validate_copy_guard(profile)
    report_files = {item.file: item for item in validate_profile_output(profile).files}
    items = [_safe_copy_plan_item(profile, filename, report_files) for filename in _expected_dashboard_files_for_profile(profile)]
    snapshot = profile.importer_output_folder / "ga4-snapshot.json"
    if snapshot.exists():
        items.append(
            {
                "file": "ga4-snapshot.json",
                "provider": "ga4",
                "source_exists": True,
                "destination_exists": False,
                "validation_status": "excluded",
                "eligible": False,
                "action": "excluded_by_policy",
                "reason": "Excluded by policy. GA4 snapshots are not copied to dashboard-lab fixtures.",
                "size": _safe_file_size(snapshot),
                "last_modified": _safe_modified_time(snapshot),
            }
        )
    eligible_count = sum(1 for item in items if item["eligible"])
    return {
        "profile": profile.slug,
        "action_id": "dashboard_lab.preview-fixture-copy",
        "result": {
            "status": "ready" if eligible_count else "not_ready",
            "message": "Fixture copy preview ready." if eligible_count else "No validated summaries are ready to copy.",
            "items": items,
            "eligible_count": eligible_count,
            "excluded_files": [item["file"] for item in items if item["action"] == "excluded_by_policy"],
            "guardrails": _safe_copy_guardrails(),
        },
    }


def run_safe_dashboard_lab_copy_action(profile: DashboardLabProfile, *, audit_log_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    preview = build_safe_dashboard_lab_copy_preview(profile)["result"]
    destination_folder = profile.dashboard_lab_local_fixture_folder
    destination_folder.mkdir(parents=True, exist_ok=True)
    results = []
    for item in preview["items"]:
        if not item["eligible"]:
            results.append({**item, "status": item["action"], "error": ""})
            continue
        source = profile.importer_output_folder / item["file"]
        destination = destination_folder / item["file"]
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            existed = destination.exists()
            shutil.copy2(source, destination)
            results.append(
                {
                    **item,
                    "destination_exists": True,
                    "status": "overwritten" if existed else "copied",
                    "size": _safe_file_size(destination),
                    "last_modified": _safe_modified_time(destination),
                    "error": "",
                }
            )
        except OSError as exc:
            results.append({**item, "status": "failed", "error": type(exc).__name__})
    counts = _safe_copy_result_counts(results)
    duration_ms = int((time.perf_counter() - started) * 1000)
    warnings = []
    if counts["skipped"]:
        warnings.append(f"skipped file(s): {counts['skipped']}")
    if counts["failed"]:
        warnings.append(f"failed file(s): {counts['failed']}")
    status = "ok" if counts["failed"] == 0 else "failed"
    audit = _write_audit_log(
        audit_log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action_id": "dashboard_lab.copy-validated-fixtures",
            "profile_slug": profile.slug,
            "status": status,
            "file_counts": counts,
            "warnings": warnings,
            "duration_ms": duration_ms,
        },
    )
    return {
        "profile": profile.slug,
        "action_id": "dashboard_lab.copy-validated-fixtures",
        "result": {
            "status": status,
            "message": "Dashboard-lab fixture copy complete." if status == "ok" else "Dashboard-lab fixture copy completed with warnings.",
            "duration_ms": duration_ms,
            "items": results,
            "counts": counts,
            "warnings": warnings,
            "audit_logged": bool(audit.get("logged")),
            "guardrails": _safe_copy_guardrails(),
        },
    }


def _safe_copy_plan_item(
    profile: DashboardLabProfile,
    filename: str,
    report_files: Mapping[str, Any],
) -> dict[str, Any]:
    source = profile.importer_output_folder / filename
    destination = profile.dashboard_lab_local_fixture_folder / filename
    source_exists = source.exists() and source.is_file()
    destination_exists = destination.exists()
    status = report_files.get(filename)
    json_valid = None if status is None else status.json_valid
    validation_status = "valid" if json_valid is True else "invalid" if json_valid is False else "unknown"
    eligible = source_exists and json_valid is not False
    reason = "Ready to copy"
    action = "copy" if not destination_exists else "overwrite"
    if not source_exists:
        eligible = False
        action = "skip_missing_output"
        reason = "Missing output"
    elif json_valid is False:
        eligible = False
        action = "skip_invalid_output"
        reason = "Validation failed"
    return {
        "file": filename,
        "provider": _provider_for_dashboard_file(filename),
        "source_exists": source_exists,
        "destination_exists": destination_exists,
        "validation_status": validation_status,
        "eligible": eligible,
        "action": action,
        "reason": reason,
        "size": _safe_file_size(source),
        "last_modified": _safe_modified_time(source),
    }


def _safe_copy_result_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    copied = sum(1 for item in results if item["status"] == "copied")
    overwritten = sum(1 for item in results if item["status"] == "overwritten")
    failed = sum(1 for item in results if item["status"] == "failed")
    skipped = len(results) - copied - overwritten - failed
    return {
        "copied": copied,
        "overwritten": overwritten,
        "skipped": skipped,
        "failed": failed,
        "eligible": sum(1 for item in results if item.get("eligible")),
        "total": len(results),
    }


def _provider_for_dashboard_file(filename: str) -> str:
    mapping = {
        "client-profile.json": "profile",
        "combined-dashboard-summary.json": "profile",
        "ga4-summary.json": "ga4",
        "gsc-summary.json": "gsc",
        "local-falcon-summary.json": "local_falcon",
        "google-ads-summary.json": "google_ads_search",
        "callrail-summary.json": "callrail",
        "form-fills-summary.json": "form_fills",
        "ga4-snapshot.json": "ga4",
    }
    return mapping.get(filename, "dashboard_lab")


def _safe_copy_guardrails() -> list[str]:
    return [
        "copies allowlisted dashboard summary JSON files only",
        "ga4-snapshot.json is excluded",
        "no raw provider rows, local config, secrets, OAuth files, or vault files",
        "copy requires explicit confirmation",
        "no provider API calls or portal publishing",
    ]


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
    return expected_dashboard_files(profile)


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
    if "/public/fixtures/" in destination_posix:
        raise HTTPException(status_code=400, detail="copy destination must not point to committed public/fixtures")
    if not (
        destination_posix.endswith(f"public/local-fixtures/{profile.slug}")
        or ".tmp" in destination.parts
    ):
        raise HTTPException(status_code=400, detail="copy destination must be under dashboard-lab public/local-fixtures/{profile} or repo .tmp")


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
    last_copy = _first_action(entries, "dashboard_lab.copy-validated-fixtures") or _first_action(entries, "copy-to-dashboard-lab")
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
                "report_count",
                "warning_count",
                "error_count",
                "safe_to_process",
                "total_form_fills",
                "date_count",
                "total_calls",
                "answered_calls",
                "missed_calls",
                "eligible_count",
                "validation_passed",
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


def _write_onboarding_action_audit(
    *,
    profile: DashboardLabProfile,
    action: Mapping[str, Any],
    result: Mapping[str, Any],
    audit_log_path: Path,
) -> dict[str, Any]:
    action_id = str(action.get("id") or "")
    allowed = {
        "local_falcon.validate-manifest",
        "form_fills.import-local",
        "callrail.import-local",
        "dashboard_lab.preview-fixture-copy",
    }
    if action_id not in allowed:
        return {"logged": False}
    status = str(result.get("status") or "")
    audit_status = "ok" if status in {"ok", "passed", "ready"} else status
    result_summary: dict[str, Any] = {}
    if action_id == "local_falcon.validate-manifest":
        result_summary = {
            "report_count": _safe_int(result.get("report_count")),
            "warning_count": _safe_int(result.get("warning_count")),
            "error_count": _safe_int(result.get("error_count")),
            "safe_to_process": bool(result.get("safe_to_process")),
        }
    elif action_id == "form_fills.import-local":
        result_summary = {
            "total_form_fills": _safe_int(result.get("total_form_fills")),
            "date_count": _safe_int(result.get("date_count")),
            "validation_passed": str(result.get("validation_status") or "") == "passed",
        }
    elif action_id == "callrail.import-local":
        result_summary = {
            "total_calls": _safe_int(result.get("total_calls")),
            "answered_calls": _safe_int(result.get("answered_calls")),
            "missed_calls": _safe_int(result.get("missed_calls")),
            "validation_passed": str(result.get("validation_status") or "") == "passed",
        }
    elif action_id == "dashboard_lab.preview-fixture-copy":
        result_summary = {
            "eligible_count": _safe_int(result.get("eligible_count")),
        }
    return _write_audit_log(
        audit_log_path,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action_id": action_id,
            "profile_slug": profile.slug,
            "status": audit_status,
            "result_summary": result_summary,
            "warnings": [],
        },
    )


def serialize_output_report(profile: DashboardLabProfile, report: Any) -> dict[str, Any]:
    return {
        "profile_slug": profile.slug,
        "folder": str(report.folder),
        "folder_exists": report.folder_exists,
        "ok": report.ok,
        "warnings": report.warnings,
        "expected_files": _expected_dashboard_files_for_profile(profile),
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
        manifest_path = _resolve_local_falcon_manifest_path(profile, local_config, safe_env=safe_env)
        env_present = _present(safe_env.get("LOCAL_FALCON_API_KEY")) or bool(local_config.get("api_key_env_present"))
        vault_configured = bool(local_config.get("api_key_vault_configured"))
        vault_locked = bool(local_config.get("api_key_vault_locked"))
        credential_present = env_present or vault_configured or _any_present(
            local_config,
            ("api_key_present", "api_key_configured"),
        )
        readiness = _readiness(manifest_present, credential_present)
        readiness["readiness"].update(
            {
                "manifest_detected": bool(manifest_path and manifest_path.is_file()),
                "api_key_env_present": env_present,
                "api_key_vault_configured": vault_configured,
                "api_key_vault_locked": vault_locked,
            }
        )
        return readiness
    if provider == "google_ads_search":
        customer_present = _present(safe_env.get("MUSIMACK_GOOGLE_ADS_CUSTOMER_ID")) or _any_present(
            local_config,
            ("customer_id", "google_ads_customer_id", "customer_id_env_present", "customer_id_configured"),
        )
        credential_present = (
            _present(safe_env.get("GOOGLE_ADS_DEVELOPER_TOKEN"))
            and _present(safe_env.get("GOOGLE_ADS_OAUTH_CLIENT_SECRETS"))
            and _present(safe_env.get("GOOGLE_ADS_OAUTH_TOKEN_FILE"))
        ) or _any_present(
            local_config,
            (
                "oauth_client_secrets",
                "oauth_token_file",
                "credentials_configured",
                "developer_token_env_present",
                "oauth_client_secrets_env_present",
                "oauth_token_file_env_present",
            ),
        )
        readiness = _readiness(customer_present, credential_present)
        readiness["readiness"].update(
            {
                "developer_token_configured": bool(local_config.get("developer_token_env_present")),
                "read_only_exporter_available": True,
            }
        )
        return readiness
    if provider == "callrail":
        filename = _safe_local_input_filename(local_config)
        input_present = bool(filename)
        readiness = _readiness(input_present, True)
        readiness["readiness"].update(
            {
                "aggregate_importer_available": True,
                "file_detected": _local_input_file_detected(provider=provider, safe_env=safe_env, input_file=filename),
            }
        )
        return readiness
    if provider == "form_fills":
        filename = _safe_local_input_filename(local_config)
        input_present = bool(filename)
        readiness = _readiness(input_present, True)
        readiness["readiness"].update(
            {
                "date_only_importer_available": True,
                "file_detected": _local_input_file_detected(provider=provider, safe_env=safe_env, input_file=filename),
            }
        )
        return readiness
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


def _safe_local_input_filename(local_config: Mapping[str, Any]) -> str:
    return str(local_config.get("local_input_filename") or "").strip()


def _local_input_file_detected(
    *,
    provider: str,
    safe_env: Mapping[str, str],
    input_file: str,
) -> bool:
    if not input_file:
        return False
    try:
        if provider == "form_fills":
            root = resolve_form_fills_input_dir(env=safe_env)
            return _resolve_form_fills_input_file(input_root=root, input_file=input_file)["path"].is_file()
        root = resolve_callrail_input_dir(env=safe_env)
        return _resolve_callrail_input_file(input_root=root, input_file=input_file)["path"].is_file()
    except HTTPException:
        return False


def _resolve_local_falcon_manifest_path(
    profile: DashboardLabProfile,
    local_config: Mapping[str, Any],
    *,
    safe_env: Mapping[str, str] | None = None,
) -> Path | None:
    raw_value = str(local_config.get("manifest_path") or "").strip()
    candidate = local_falcon_manifest_path(profile) if not raw_value else Path(raw_value)
    manifest_root = resolve_local_falcon_manifest_dir(env=safe_env)
    if raw_value and not candidate.is_absolute():
        first_part = candidate.parts[0] if candidate.parts else ""
        if first_part in {".tmp", "local-falcon-manifests"}:
            candidate = ROOT / candidate
        else:
            candidate = manifest_root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    allowed_roots = [
        manifest_root.resolve(),
        (ROOT / "local-falcon-manifests").resolve(),
        (ROOT / ".tmp").resolve(),
    ]
    if any(resolved == root or root in resolved.parents for root in allowed_roots):
        return resolved
    return None


def _any_present(config: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_present(config.get(key)) for key in keys)


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value).strip()) if value is not None else False


app = create_app()
