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

from fastapi import FastAPI, HTTPException, Query
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
from src.profile_local_config import DEFAULT_LOCAL_PROFILE_CONFIG_DIR, ProfileLocalConfigError, load_profile_provider_config_map
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


APP_NAME = "musimack-data-importer-local-api"
DEFAULT_LOCAL_PROFILE_CONFIG = ROOT / "config" / "dashboard_lab_profiles.local.json"
DEFAULT_AUDIT_LOG = ROOT / "logs" / "local-action-runs.jsonl"
IMPORTER_VAULT_PATH_ENV = "MUSIMACK_IMPORTER_VAULT_PATH"
LOCAL_CONFIG_DIR_ENV = "MUSIMACK_IMPORTER_LOCAL_CONFIG_DIR"
PROFILE_REGISTRY_PATH_ENV = "MUSIMACK_IMPORTER_PROFILE_REGISTRY_PATH"
FORM_FILLS_INPUT_DIR_ENV = "MUSIMACK_IMPORTER_FORM_FILLS_INPUT_DIR"
CALLRAIL_INPUT_DIR_ENV = "MUSIMACK_IMPORTER_CALLRAIL_INPUT_DIR"
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
        return audit_log_path or DEFAULT_AUDIT_LOG

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
        "local_config": _onboarding_local_config_state(checklist),
        "vault": _onboarding_vault_state(local_config),
        "validation": {
            "state": "Ready for validation" if output_status["folder_exists"] else "Validation unknown",
            "folder_exists": output_status["folder_exists"],
            "overall_ok": output_status["ok"],
            "last_validation": "Available" if last_actions["last_validation"] else "Not run",
            "warning_count": len(output_status["warnings"]),
        },
        "dashboard_copy": {
            "state": "Ready for dashboard-lab copy" if ready_for_copy_count and ready_for_copy_count == enabled_provider_count else "Not applicable" if not enabled_provider_count else "Output missing",
            "ready_provider_count": ready_for_copy_count,
            "last_copy": "Available" if last_actions["last_copy"] else "Not run",
        },
        "providers": providers,
        "safety": {
            "read_only": True,
            "no_provider_execution": True,
            "no_fixture_copy": True,
            "no_secret_values": True,
            "no_file_contents": True,
        },
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
            for provider in ("ga4", "gsc", "local_falcon", "google_ads_search", "callrail", "form_fills", "dashboard_lab")
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
    elif action["kind"] == "dashboard_lab_copy_preview":
        result = build_safe_dashboard_lab_copy_preview(profile)["result"]
    elif action["kind"] == "dashboard_lab_copy_validated":
        result = run_safe_dashboard_lab_copy_action(profile, audit_log_path=audit_log_path or DEFAULT_AUDIT_LOG)["result"]
    elif action["kind"] == "form_fills_import_local":
        result = _run_form_fills_import_action(
            profile,
            input_file=input_file,
            input_root=form_fills_input_dir or resolve_form_fills_input_dir(env=safe_env),
        )
    elif action["kind"] == "callrail_import_local":
        result = _run_callrail_import_action(
            profile,
            input_file=input_file,
            input_root=callrail_input_dir or resolve_callrail_input_dir(env=safe_env),
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
    return {
        "profile": profile.slug,
        "action": action,
        "result": result,
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
                label="Check readiness",
                description="Refresh safe setup and output readiness metadata.",
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
    return {
        "status": "ok",
        "message": "Readiness checked.",
        "provider": provider,
        "config_state": provider_status["config_state"],
        "output_state": provider_status["output_state"],
        "validation_state": provider_status["validation_state"],
        "copy_state": provider_status["copy_state"],
        "next_step": provider_status["next_step"],
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
) -> dict[str, Any]:
    resolved_input = _resolve_form_fills_input_file(input_root=input_root, input_file=input_file)
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
) -> dict[str, Any]:
    resolved_input = _resolve_callrail_input_file(input_root=input_root, input_file=input_file)
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
        ("customer_id", "google_ads_customer_id", "customer_id_configured"),
    )
    auth_present = _any_present(
        local_config,
        ("oauth_client_secrets", "oauth_token_file", "credentials_configured"),
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
        ("input_csv", "calls_csv", "source_csv", "callrail_export_csv", "input_path"),
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
        ("input_csv", "forms_csv", "form_fills_csv", "source_csv", "input_path"),
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
                "api_key_env_present": env_present,
                "api_key_vault_configured": vault_configured,
                "api_key_vault_locked": vault_locked,
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


def _any_present(config: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_present(config.get(key)) for key in keys)


def _present(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(str(value).strip()) if value is not None else False


app = create_app()
