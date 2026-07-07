from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


RECOGNIZED_CONTRACTS = {
    "client_report_publisher_handoff_manifest.v1",
    "ga4_metric_display.v1",
    "ga4_most_viewed_pages_display.v1",
    "ga4_top_landing_pages_display.v1",
    "ga4_top_sources_display.v1",
    "gsc_queries_display.v1",
    "gsc_summary_display.v1",
    "local_falcon_display.v1",
}

REQUIRED_MANIFEST_FIELDS = {
    "client_slug",
    "period_start",
    "period_end",
    "generated_at",
    "files",
    "display_contract_versions",
    "validation_status",
}

FORBIDDEN_KEYS = {
    "token",
    "secret",
    "credential",
    "authorization",
    "refresh_token",
    "access_token",
    "client_secret",
    "private_key",
    "service_account",
    "raw_payload",
    "request_body",
    "response_body",
    "config_json",
    "bigquery_project",
    "dataset_id",
    "oauth",
    "auto_publish",
}

RAW_PAYLOAD_KEYS = {
    "raw",
    "payload",
    "request",
    "response",
    "headers",
}

SECRET_LIKE_VALUE_PATTERNS = [
    re.compile(r"ya29\.", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bbearer\s+[a-z0-9._-]{16,}", re.IGNORECASE),
    re.compile(r"\bsk-[a-z0-9]{16,}", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
]

SECRET_LIKE_SUBSTRINGS = (
    ".env",
    "client-dashboard db",
    "bigquery",
    "private key",
    "refresh token",
    "access token",
)


@dataclass(frozen=True)
class HandoffValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_checked: list[str] = field(default_factory=list)
    contracts_seen: list[str] = field(default_factory=list)


def validate_handoff_directory(
    handoff_dir: str | Path,
    *,
    max_list_items: int = 100,
) -> HandoffValidationResult:
    """Validate a local sanitized Client Report Publisher handoff folder."""
    root = Path(handoff_dir)
    errors: list[str] = []
    warnings: list[str] = []
    files_checked: list[str] = []
    contracts_seen: set[str] = set()

    if max_list_items < 1:
        raise ValueError("max_list_items must be positive")

    try:
        root_resolved = root.resolve(strict=True)
    except OSError:
        return _result(errors=[f"handoff directory is not readable: {_safe_path_label(root)}"])

    if not root_resolved.is_dir():
        return _result(errors=[f"handoff path is not a directory: {_safe_path_label(root)}"])

    manifest_path = root_resolved / "manifest.json"
    manifest = _load_json_object(manifest_path, "manifest.json", errors)
    if manifest is None:
        return _result(errors=errors)

    files_checked.append("manifest.json")
    _validate_schema_version(manifest, "manifest.json", errors, contracts_seen)
    _validate_manifest_shape(manifest, errors)
    _validate_period(manifest, errors)
    _scan_payload(manifest, "manifest.json", errors, max_list_items=max_list_items)

    file_entries = manifest.get("files")
    if not isinstance(file_entries, list):
        return _result(
            errors=errors,
            warnings=warnings,
            files_checked=files_checked,
            contracts_seen=contracts_seen,
        )

    manifest_contracts = manifest.get("display_contract_versions")
    if isinstance(manifest_contracts, list):
        for index, contract in enumerate(manifest_contracts):
            if not isinstance(contract, str):
                errors.append(f"display_contract_versions[{index}] must be a string")
            elif contract not in RECOGNIZED_CONTRACTS:
                errors.append(f"display_contract_versions[{index}] is not recognized")

    seen_paths: set[str] = set()
    referenced_contracts: set[str] = set()
    for index, entry in enumerate(file_entries):
        if not isinstance(entry, dict):
            errors.append(f"files[{index}] must be an object")
            continue

        rel_path = entry.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            errors.append(f"files[{index}].path is required")
            continue

        safe_rel_path = rel_path.replace("\\", "/")
        if safe_rel_path in seen_paths:
            errors.append(f"duplicate manifest file reference: {safe_rel_path}")
            continue
        seen_paths.add(safe_rel_path)

        referenced_path = _resolve_inside_root(root_resolved, rel_path)
        if referenced_path is None:
            errors.append(f"files[{index}].path must stay inside the handoff directory")
            continue
        if not referenced_path.exists():
            errors.append(f"referenced file is missing: {safe_rel_path}")
            continue
        if not referenced_path.is_file():
            errors.append(f"referenced path is not a file: {safe_rel_path}")
            continue

        payload = _load_json_object(referenced_path, safe_rel_path, errors)
        if payload is None:
            continue

        files_checked.append(safe_rel_path)
        schema_version = _validate_schema_version(payload, safe_rel_path, errors, contracts_seen)
        if schema_version:
            referenced_contracts.add(schema_version)
        _scan_payload(payload, safe_rel_path, errors, max_list_items=max_list_items)

        for key in ("provider", "report_type"):
            if not isinstance(payload.get(key), str) or not payload.get(key):
                errors.append(f"{safe_rel_path}.{key} is required")
            elif entry.get(key) != payload.get(key):
                errors.append(f"{safe_rel_path}.{key} does not match manifest")

        if entry.get("schema_version") != schema_version:
            errors.append(f"{safe_rel_path}.schema_version does not match manifest")

    if isinstance(manifest_contracts, list):
        manifest_contract_set = {contract for contract in manifest_contracts if isinstance(contract, str)}
        missing_from_manifest = sorted(referenced_contracts - manifest_contract_set)
        missing_files = sorted(manifest_contract_set - referenced_contracts)
        for contract in missing_from_manifest:
            errors.append(f"manifest.display_contract_versions is missing referenced contract {contract}")
        for contract in missing_files:
            errors.append(f"manifest references contract without a file: {contract}")

    if not files_checked or files_checked == ["manifest.json"]:
        warnings.append("no display files were checked")

    return _result(
        errors=errors,
        warnings=warnings,
        files_checked=files_checked,
        contracts_seen=contracts_seen,
    )


def _validate_manifest_shape(manifest: dict[str, Any], errors: list[str]) -> None:
    missing = sorted(field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest)
    for field_name in missing:
        errors.append(f"manifest.{field_name} is required")

    if "client_slug" in manifest and not _is_non_empty_string(manifest["client_slug"]):
        errors.append("manifest.client_slug must be a non-empty string")
    if "generated_at" in manifest and not _is_valid_datetime(str(manifest["generated_at"])):
        errors.append("manifest.generated_at must be an ISO datetime string")
    if "files" in manifest and not isinstance(manifest["files"], list):
        errors.append("manifest.files must be a list")
    if "display_contract_versions" in manifest and not isinstance(manifest["display_contract_versions"], list):
        errors.append("manifest.display_contract_versions must be a list")
    if "validation_status" in manifest and not _is_non_empty_string(manifest["validation_status"]):
        errors.append("manifest.validation_status must be a non-empty string")


def _validate_period(manifest: dict[str, Any], errors: list[str]) -> None:
    start_raw = manifest.get("period_start")
    end_raw = manifest.get("period_end")
    start = _parse_date(start_raw)
    end = _parse_date(end_raw)

    if start_raw is not None and start is None:
        errors.append("manifest.period_start must be an ISO date")
    if end_raw is not None and end is None:
        errors.append("manifest.period_end must be an ISO date")
    if start is not None and end is not None and start > end:
        errors.append("manifest.period_start must be on or before period_end")


def _validate_schema_version(
    payload: dict[str, Any],
    label: str,
    errors: list[str],
    contracts_seen: set[str],
) -> str | None:
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        errors.append(f"{label}.schema_version is required")
        return None
    if schema_version not in RECOGNIZED_CONTRACTS:
        errors.append(f"{label}.schema_version is not recognized")
        return schema_version
    contracts_seen.add(schema_version)
    return schema_version


def _scan_payload(
    payload: Any,
    label: str,
    errors: list[str],
    *,
    max_list_items: int,
    path: tuple[str, ...] = (),
) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            path_label = _path_label(label, (*path, str(key)))
            if (
                any(forbidden in key_lower for forbidden in FORBIDDEN_KEYS)
                or key_lower in RAW_PAYLOAD_KEYS
            ):
                errors.append(f"forbidden key found at {path_label}")
            _scan_payload(value, label, errors, max_list_items=max_list_items, path=(*path, str(key)))
    elif isinstance(payload, list):
        path_label = _path_label(label, path)
        if len(payload) > max_list_items:
            errors.append(f"list exceeds maximum item count at {path_label}")
        for index, value in enumerate(payload):
            _scan_payload(value, label, errors, max_list_items=max_list_items, path=(*path, str(index)))
    elif isinstance(payload, str):
        lowered = payload.lower()
        path_label = _path_label(label, path)
        if any(item in lowered for item in SECRET_LIKE_SUBSTRINGS):
            errors.append(f"secret-like value found at {path_label}")
        elif any(pattern.search(payload) for pattern in SECRET_LIKE_VALUE_PATTERNS):
            errors.append(f"secret-like value found at {path_label}")
    elif isinstance(payload, float) and not math.isfinite(payload):
        errors.append(f"non-finite number found at {_path_label(label, path)}")


def _load_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        errors.append(f"{label} is not readable")
        return None
    except json.JSONDecodeError:
        errors.append(f"{label} is not valid JSON")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object")
        return None
    return payload


def _resolve_inside_root(root: Path, rel_path: str) -> Path | None:
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return None
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_valid_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_path_label(path: Path) -> str:
    return path.name or str(path)


def _path_label(label: str, path: tuple[str, ...]) -> str:
    if not path:
        return label
    return f"{label}.{'.'.join(path)}"


def _result(
    *,
    errors: list[str],
    warnings: list[str] | None = None,
    files_checked: list[str] | None = None,
    contracts_seen: set[str] | list[str] | None = None,
) -> HandoffValidationResult:
    return HandoffValidationResult(
        valid=not errors,
        errors=errors,
        warnings=warnings or [],
        files_checked=files_checked or [],
        contracts_seen=sorted(contracts_seen or []),
    )
