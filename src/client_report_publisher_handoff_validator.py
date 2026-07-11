from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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

DAILY_SERIES_COVERAGE_VERSION = "daily_series_coverage.v1"
MAX_DAILY_SERIES_ITEMS = 3660
DAILY_SERIES_CONTRACTS = {"ga4_metric_display.v1", "gsc_summary_display.v1"}
DAILY_SERIES_TIMEZONES = {"UTC", "provider_local_unspecified"}

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
        if schema_version in DAILY_SERIES_CONTRACTS:
            _validate_daily_series_contract(
                payload,
                schema_version,
                safe_rel_path,
                manifest.get("period_start"),
                manifest.get("period_end"),
                errors,
                warnings,
            )

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
        item_limit = MAX_DAILY_SERIES_ITEMS if _is_daily_series_path(path) else max_list_items
        if len(payload) > item_limit:
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


def _is_daily_series_path(path: tuple[str, ...]) -> bool:
    if path == ("trend_points",):
        return True
    return (
        len(path) == 5
        and path[0] == "trend_charts"
        and path[1].isdigit()
        and path[2] == "series"
        and path[3].isdigit()
        and path[4] == "points"
    )


def _validate_daily_series_contract(
    payload: dict[str, Any],
    schema_version: str,
    label: str,
    period_start_raw: Any,
    period_end_raw: Any,
    errors: list[str],
    warnings: list[str],
) -> None:
    period_start = _parse_date(period_start_raw)
    period_end = _parse_date(period_end_raw)
    if period_start is None or period_end is None or period_start > period_end:
        return
    expected_dates = [
        (period_start + timedelta(days=offset)).isoformat()
        for offset in range((period_end - period_start).days + 1)
    ]
    series_dates = _daily_series_dates(payload, schema_version, label, errors)
    if not series_dates:
        return

    expected_date_set = set(expected_dates)
    if any(
        observed not in expected_date_set
        for dates in series_dates
        for observed in dates
    ):
        errors.append(f"{label} daily observations must stay inside the requested period")

    coverage = payload.get("daily_series_coverage")
    if coverage is None:
        if len(expected_dates) > 100 and any(len(dates) == 100 for dates in series_dates):
            errors.append(
                f"{label} legacy daily series has 100 points inside a longer report period; possible silent truncation"
            )
        else:
            warnings.append(f"{label} uses legacy daily-series coverage without explicit metadata")
        return
    if not isinstance(coverage, dict):
        errors.append(f"{label}.daily_series_coverage must be an object")
        return

    required_fields = {
        "schema_version",
        "grain",
        "timezone",
        "requested_period_start",
        "requested_period_end",
        "expected_observation_count",
        "actual_observation_count",
        "first_observation_date",
        "last_observation_date",
        "coverage_state",
        "gap_state",
        "missing_observation_count",
        "quality_notes",
    }
    for field_name in sorted(required_fields - coverage.keys()):
        errors.append(f"{label}.daily_series_coverage.{field_name} is required")
    if required_fields - coverage.keys():
        return

    if coverage.get("schema_version") != DAILY_SERIES_COVERAGE_VERSION:
        errors.append(f"{label}.daily_series_coverage.schema_version is unsupported")
    if coverage.get("grain") != "day":
        errors.append(f"{label}.daily_series_coverage.grain must be day")
    timezone = coverage.get("timezone")
    if not isinstance(timezone, str) or not _valid_daily_timezone(timezone):
        errors.append(f"{label}.daily_series_coverage.timezone is invalid")
    if coverage.get("requested_period_start") != period_start.isoformat():
        errors.append(f"{label}.daily_series_coverage.requested_period_start does not match manifest")
    if coverage.get("requested_period_end") != period_end.isoformat():
        errors.append(f"{label}.daily_series_coverage.requested_period_end does not match manifest")

    expected_count = len(expected_dates)
    actual_count = len(series_dates[0])
    if any(dates != series_dates[0] for dates in series_dates[1:]):
        errors.append(f"{label} daily series must use the same ordered observation dates")
    if coverage.get("expected_observation_count") != expected_count:
        errors.append(f"{label}.daily_series_coverage.expected_observation_count is inconsistent")
    if coverage.get("actual_observation_count") != actual_count:
        errors.append(f"{label}.daily_series_coverage.actual_observation_count is inconsistent")
    if coverage.get("missing_observation_count") != expected_count - actual_count:
        errors.append(f"{label}.daily_series_coverage.missing_observation_count is inconsistent")

    observed_dates = series_dates[0]
    first_date = observed_dates[0] if observed_dates else None
    last_date = observed_dates[-1] if observed_dates else None
    if coverage.get("first_observation_date") != first_date:
        errors.append(f"{label}.daily_series_coverage.first_observation_date is inconsistent")
    if coverage.get("last_observation_date") != last_date:
        errors.append(f"{label}.daily_series_coverage.last_observation_date is inconsistent")

    state = coverage.get("coverage_state")
    gap_state = coverage.get("gap_state")
    if state not in {"complete", "partial", "empty", "unavailable"}:
        errors.append(f"{label}.daily_series_coverage.coverage_state is invalid")
    elif state == "complete" and observed_dates != expected_dates:
        errors.append(f"{label} claims complete daily coverage but observations contain gaps")
    elif state == "partial" and (not observed_dates or observed_dates == expected_dates):
        errors.append(f"{label} partial daily coverage contradicts serialized observations")
    elif state in {"empty", "unavailable"} and observed_dates:
        errors.append(f"{label} {state} daily coverage must not contain observations")

    expected_gap_state = (
        "none" if state == "complete" else "gaps_present" if state == "partial" else "not_applicable"
    )
    if gap_state != expected_gap_state:
        errors.append(f"{label}.daily_series_coverage.gap_state contradicts coverage_state")
    quality_notes = coverage.get("quality_notes")
    if not isinstance(quality_notes, list) or len(quality_notes) > 10 or not all(
        isinstance(note, str) for note in quality_notes
    ):
        errors.append(f"{label}.daily_series_coverage.quality_notes must be a bounded string list")


def _daily_series_dates(
    payload: dict[str, Any],
    schema_version: str,
    label: str,
    errors: list[str],
) -> list[list[str]]:
    if schema_version == "gsc_summary_display.v1":
        point_sets = [payload.get("trend_points")]
    else:
        point_sets = []
        charts = payload.get("trend_charts")
        if isinstance(charts, list):
            for chart in charts:
                if isinstance(chart, dict) and chart.get("grain") == "day":
                    series = chart.get("series")
                    if isinstance(series, list):
                        point_sets.extend(
                            item.get("points") for item in series if isinstance(item, dict)
                        )
    results: list[list[str]] = []
    for series_index, points in enumerate(point_sets):
        if not isinstance(points, list):
            errors.append(f"{label} daily series {series_index} points must be a list")
            continue
        dates: list[str] = []
        for point_index, point in enumerate(points):
            raw_date = point.get("date") if isinstance(point, dict) else None
            parsed = _parse_date(raw_date)
            if parsed is None:
                errors.append(f"{label} daily series {series_index} point {point_index} has an invalid date")
                continue
            dates.append(parsed.isoformat())
        if dates != sorted(dates):
            errors.append(f"{label} daily series {series_index} dates must be in ascending order")
        if len(dates) != len(set(dates)):
            errors.append(f"{label} daily series {series_index} dates must be unique")
        results.append(dates)
    return results


def _valid_daily_timezone(value: str) -> bool:
    if value in DAILY_SERIES_TIMEZONES:
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*/[A-Za-z][A-Za-z0-9_+./-]*", value))


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
