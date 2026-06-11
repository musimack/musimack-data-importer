from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FORBIDDEN_SECRET_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "client_secret",
    "oauth",
    "password",
    "secret",
    "credential",
    "credentials",
    "token_file",
    "private_key",
}

FORBIDDEN_CALLRAIL_KEYS = {
    "caller_name",
    "caller",
    "caller_phone",
    "caller_phone_number",
    "phone_number",
    "customer_name",
    "customer_phone",
    "contact_name",
    "contact_phone",
    "recording",
    "recording_url",
    "recording_link",
    "transcript",
    "call_log",
    "call_logs",
    "raw_call",
    "raw_calls",
    "individual_calls",
    "call_recording",
    "call_recordings",
}

PHONE_PATTERN = re.compile(
    r"(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})\b"
)


class DashboardLabFixtureValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    provider: str
    profile: str
    client_label: str
    warnings: list[str]


def load_json_object(path: Path | str) -> dict[str, Any]:
    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DashboardLabFixtureValidationError(f"{input_path.name} is not valid JSON") from exc
    except OSError as exc:
        raise DashboardLabFixtureValidationError(f"{input_path} could not be read") from exc
    if not isinstance(payload, dict):
        raise DashboardLabFixtureValidationError(f"{input_path.name} must contain a JSON object")
    return payload


def validate_google_ads_summary(payload: dict[str, Any]) -> ValidationResult:
    filename = "google-ads-summary.json"
    _require_object(payload, filename)
    _reject_forbidden_keys(payload, filename, FORBIDDEN_SECRET_KEYS)
    warnings = _validate_shared_contract(
        payload,
        filename=filename,
        schema_version="google_ads_summary.v1",
        provider="google_ads",
    )
    _validate_object_if_present(payload, "paid_search_call_signal", filename)
    _validate_object_if_present(payload, "budget_pacing", filename)
    _validate_array_if_present(payload, "keyword_rows", filename)
    _validate_array_if_present(payload, "search_term_rows", filename)
    _validate_array_if_present(payload, "campaign_rows", filename)
    _validate_array_if_present(payload, "landing_page_rows", filename)
    _validate_array_if_present(payload, "time_series", filename)

    _validate_number_fields(payload["summary"], filename, "summary", {
        "spend",
        "clicks",
        "impressions",
        "ctr",
        "avg_cpc",
        "conversions",
        "cost_per_conversion",
        "calls",
        "cost_per_call",
    }, integer_fields={"clicks", "impressions"})
    _validate_rows(
        payload.get("keyword_rows", []),
        filename,
        "keyword_rows",
        string_fields={"keyword", "campaign", "match_type", "landing_page"},
        numeric_fields={"impressions", "clicks", "ctr", "avg_cpc", "cost", "conversions", "calls", "cost_per_call"},
        integer_fields={"impressions", "clicks", "calls"},
    )
    _validate_rows(
        payload.get("search_term_rows", []),
        filename,
        "search_term_rows",
        string_fields={"search_term", "matched_keyword", "campaign"},
        numeric_fields={"impressions", "clicks", "ctr", "cost", "conversions", "calls"},
        integer_fields={"impressions", "clicks", "calls"},
    )
    _validate_rows(
        payload.get("campaign_rows", []),
        filename,
        "campaign_rows",
        string_fields={"campaign"},
        numeric_fields={"spend", "impressions", "clicks", "ctr", "avg_cpc", "conversions", "calls", "cost_per_call"},
        integer_fields={"impressions", "clicks", "calls"},
    )
    _validate_rows(
        payload.get("landing_page_rows", []),
        filename,
        "landing_page_rows",
        string_fields={"landing_page", "campaign"},
        numeric_fields={"impressions", "clicks", "ctr", "cost", "conversions", "calls", "cost_per_call"},
        integer_fields={"impressions", "clicks", "calls"},
    )
    _validate_number_fields(
        payload.get("paid_search_call_signal", {}),
        filename,
        "paid_search_call_signal",
        {"google_ads_calls", "calls_with_keyword_attribution", "missed_paid_search_calls", "cost_per_call"},
        integer_fields={"google_ads_calls", "calls_with_keyword_attribution", "missed_paid_search_calls"},
    )
    _validate_number_fields(
        payload.get("budget_pacing", {}),
        filename,
        "budget_pacing",
        {"spend", "budget", "percent_used", "days_elapsed", "days_remaining"},
        integer_fields={"days_elapsed", "days_remaining"},
    )
    _validate_rows(
        payload.get("time_series", []),
        filename,
        "time_series",
        string_fields={"date"},
        numeric_fields={"spend", "cost", "impressions", "clicks", "ctr", "conversions", "calls"},
        integer_fields={"impressions", "clicks", "calls"},
    )
    return _result(payload, "google_ads", warnings)


def validate_callrail_summary(payload: dict[str, Any]) -> ValidationResult:
    filename = "callrail-summary.json"
    _require_object(payload, filename)
    _reject_forbidden_keys(payload, filename, FORBIDDEN_SECRET_KEYS)
    _reject_forbidden_keys(payload, filename, FORBIDDEN_CALLRAIL_KEYS, message="forbidden CallRail call-detail key")
    _reject_phone_values(payload, filename)
    warnings = _validate_shared_contract(
        payload,
        filename=filename,
        schema_version="callrail_summary.v1",
        provider="callrail",
    )
    for field in (
        "keyword_rows",
        "campaign_rows",
        "landing_page_rows",
        "source_rows",
        "tracking_number_rows",
        "missed_call_opportunities",
        "time_series",
    ):
        _validate_array_if_present(payload, field, filename)
    _validate_object_if_present(payload, "paid_search_attribution", filename)

    _validate_number_fields(
        payload["summary"],
        filename,
        "summary",
        {
            "total_calls",
            "google_ads_calls",
            "first_time_callers",
            "answered_calls",
            "missed_calls",
            "avg_duration_seconds",
            "qualified_calls",
            "calls_with_keyword_attribution",
            "calls_without_keyword_attribution",
        },
        integer_fields={
            "total_calls",
            "google_ads_calls",
            "first_time_callers",
            "answered_calls",
            "missed_calls",
            "qualified_calls",
            "calls_with_keyword_attribution",
            "calls_without_keyword_attribution",
        },
    )
    _validate_number_fields(
        payload.get("paid_search_attribution", {}),
        filename,
        "paid_search_attribution",
        {
            "google_ads_calls",
            "calls_with_keyword_attribution",
            "missed_keyword_calls",
            "attribution_unavailable_calls",
        },
        integer_fields={
            "google_ads_calls",
            "calls_with_keyword_attribution",
            "missed_keyword_calls",
            "attribution_unavailable_calls",
        },
    )
    _validate_text_fields(
        payload.get("paid_search_attribution", {}),
        filename,
        "paid_search_attribution",
        {"top_keyword", "top_campaign"},
    )
    notes = payload.get("paid_search_attribution", {}).get("notes")
    if notes is not None and not isinstance(notes, (str, list)):
        raise DashboardLabFixtureValidationError("callrail-summary.json paid_search_attribution.notes must be a string or array")

    common_call_fields = {"calls", "first_time_callers", "answered_calls", "missed_calls", "avg_duration_seconds", "qualified_calls"}
    common_integer_fields = {"calls", "first_time_callers", "answered_calls", "missed_calls", "qualified_calls"}
    _validate_rows(
        payload.get("keyword_rows", []),
        filename,
        "keyword_rows",
        string_fields={"keyword", "campaign", "landing_page", "source"},
        numeric_fields=common_call_fields | {"cost", "cost_per_call"},
        integer_fields=common_integer_fields,
    )
    _validate_rows(
        payload.get("campaign_rows", []),
        filename,
        "campaign_rows",
        string_fields={"campaign"},
        numeric_fields=common_call_fields | {"cost", "cost_per_call"},
        integer_fields=common_integer_fields,
    )
    _validate_rows(
        payload.get("landing_page_rows", []),
        filename,
        "landing_page_rows",
        string_fields={"landing_page", "keyword", "campaign"},
        numeric_fields={"calls", "answered_calls", "missed_calls", "first_time_callers", "avg_duration_seconds"},
        integer_fields={"calls", "answered_calls", "missed_calls", "first_time_callers"},
    )
    _validate_rows(
        payload.get("source_rows", []),
        filename,
        "source_rows",
        string_fields={"source"},
        numeric_fields={"calls", "answered_calls", "missed_calls", "first_time_callers", "avg_duration_seconds"},
        integer_fields={"calls", "answered_calls", "missed_calls", "first_time_callers"},
    )
    _validate_tracking_number_rows(payload.get("tracking_number_rows", []), filename)
    _validate_rows(
        payload.get("missed_call_opportunities", []),
        filename,
        "missed_call_opportunities",
        string_fields={"keyword", "campaign", "why_it_matters", "recommended_action", "priority"},
        numeric_fields={"missed_calls", "total_calls"},
        integer_fields={"missed_calls", "total_calls"},
    )
    _validate_rows(
        payload.get("time_series", []),
        filename,
        "time_series",
        string_fields={"date"},
        numeric_fields={"total_calls", "answered_calls", "missed_calls", "first_time_callers", "google_ads_calls"},
        integer_fields={"total_calls", "answered_calls", "missed_calls", "first_time_callers", "google_ads_calls"},
    )
    return _result(payload, "callrail", warnings)


def _validate_shared_contract(
    payload: dict[str, Any],
    *,
    filename: str,
    schema_version: str,
    provider: str,
) -> list[str]:
    warnings = []
    _require_fields(
        payload,
        filename,
        ["schema_version", "provider", "profile", "client_label", "is_real_data", "date_range", "summary"],
    )
    if payload.get("schema_version") != schema_version:
        raise DashboardLabFixtureValidationError(f"{filename} schema_version must be {schema_version}")
    if payload.get("provider") != provider:
        raise DashboardLabFixtureValidationError(f"{filename} provider must be {provider}")
    _require_string(payload, "profile", filename)
    _require_string(payload, "client_label", filename)
    if not isinstance(payload.get("is_real_data"), bool):
        raise DashboardLabFixtureValidationError(f"{filename} is_real_data must be a boolean")
    if "generated_at" not in payload:
        warnings.append(f"{filename} generated_at is missing.")
    elif payload.get("generated_at") is not None and not isinstance(payload.get("generated_at"), str):
        raise DashboardLabFixtureValidationError(f"{filename} generated_at must be a string when present")
    date_range = payload.get("date_range")
    if not isinstance(date_range, dict):
        raise DashboardLabFixtureValidationError(f"{filename} date_range must be an object")
    for field in ("start_date", "end_date"):
        if field not in date_range:
            raise DashboardLabFixtureValidationError(f"{filename} date_range.{field} is required")
        if date_range.get(field) is not None and not isinstance(date_range.get(field), str):
            raise DashboardLabFixtureValidationError(f"{filename} date_range.{field} must be a string or null")
    if not isinstance(payload.get("summary"), dict):
        raise DashboardLabFixtureValidationError(f"{filename} summary must be an object")
    if "data_quality_notes" in payload and not isinstance(payload.get("data_quality_notes"), list):
        raise DashboardLabFixtureValidationError(f"{filename} data_quality_notes must be an array")
    return warnings


def _validate_rows(
    rows: Any,
    filename: str,
    collection_name: str,
    *,
    string_fields: set[str],
    numeric_fields: set[str],
    integer_fields: set[str] | None = None,
) -> None:
    integer_fields = integer_fields or set()
    if rows is None:
        return
    if not isinstance(rows, list):
        raise DashboardLabFixtureValidationError(f"{filename} {collection_name} must be an array")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise DashboardLabFixtureValidationError(f"{filename} {collection_name}[{index}] must be an object")
        _validate_text_fields(row, filename, f"{collection_name}[{index}]", string_fields)
        _validate_number_fields(row, filename, f"{collection_name}[{index}]", numeric_fields, integer_fields=integer_fields)


def _validate_tracking_number_rows(rows: Any, filename: str) -> None:
    _validate_rows(
        rows,
        filename,
        "tracking_number_rows",
        string_fields={"label", "tracking_number_label", "source"},
        numeric_fields={"calls", "answered_calls", "missed_calls", "first_time_callers"},
        integer_fields={"calls", "answered_calls", "missed_calls", "first_time_callers"},
    )
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        if not isinstance(row.get("label") or row.get("tracking_number_label"), str):
            raise DashboardLabFixtureValidationError(
                f"{filename} tracking_number_rows[{index}] requires label or tracking_number_label"
            )


def _validate_text_fields(row: dict[str, Any], filename: str, location: str, fields: set[str]) -> None:
    for field in fields:
        if field in row and row[field] is not None and not isinstance(row[field], str):
            raise DashboardLabFixtureValidationError(f"{filename} {location}.{field} must be a string")


def _validate_number_fields(
    row: dict[str, Any],
    filename: str,
    location: str,
    fields: set[str],
    *,
    integer_fields: set[str] | None = None,
) -> None:
    integer_fields = integer_fields or set()
    for field in fields:
        if field not in row or row[field] is None:
            continue
        value = row[field]
        if not _is_number(value):
            raise DashboardLabFixtureValidationError(f"{filename} {location}.{field} must be numeric, not display-formatted")
        if field in integer_fields and isinstance(value, float) and not value.is_integer():
            raise DashboardLabFixtureValidationError(f"{filename} {location}.{field} must be an integer-compatible number")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_array_if_present(payload: dict[str, Any], field: str, filename: str) -> None:
    if field in payload and not isinstance(payload[field], list):
        raise DashboardLabFixtureValidationError(f"{filename} {field} must be an array")


def _validate_object_if_present(payload: dict[str, Any], field: str, filename: str) -> None:
    if field in payload and not isinstance(payload[field], dict):
        raise DashboardLabFixtureValidationError(f"{filename} {field} must be an object")


def _require_fields(payload: dict[str, Any], filename: str, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise DashboardLabFixtureValidationError(f"{filename} missing required fields: {', '.join(missing)}")


def _require_object(payload: Any, filename: str) -> None:
    if not isinstance(payload, dict):
        raise DashboardLabFixtureValidationError(f"{filename} must contain a JSON object")


def _require_string(payload: dict[str, Any], field: str, filename: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DashboardLabFixtureValidationError(f"{filename} {field} must be a non-empty string")


def _reject_forbidden_keys(
    value: Any,
    filename: str,
    forbidden: set[str],
    *,
    message: str = "forbidden secret-like key",
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = _normalize_key(key)
            if normalized_key in forbidden:
                raise DashboardLabFixtureValidationError(f"{filename} contains {message}: {key}")
            _reject_forbidden_keys(nested, filename, forbidden, message=message)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_keys(item, filename, forbidden, message=message)


def _reject_phone_values(value: Any, filename: str) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _reject_phone_values(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _reject_phone_values(item, filename)
    elif isinstance(value, str) and _looks_like_phone_number(value):
        raise DashboardLabFixtureValidationError(
            f"{filename} contains a phone-number-looking value; use aggregate labels instead"
        )


def _looks_like_phone_number(value: str) -> bool:
    text = value.strip()
    match = PHONE_PATTERN.search(text)
    if not match:
        return False
    digits = re.sub(r"\D", "", match.group(0))
    return 10 <= len(digits) <= 11


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _result(payload: dict[str, Any], provider: str, warnings: list[str]) -> ValidationResult:
    return ValidationResult(
        provider=provider,
        profile=str(payload.get("profile") or ""),
        client_label=str(payload.get("client_label") or ""),
        warnings=warnings,
    )
