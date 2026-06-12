from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .paid_callrail_validators import DashboardLabFixtureValidationError


DEFAULT_INPUT_ROOT = Path("inputs") / "local-real" / "form-fills"
DEFAULT_OUTPUT_ROOT = Path("exports") / "local-real" / "dashboard-lab"
FORM_FILLS_SUMMARY_FILENAME = "form-fills-summary.json"
ALLOWED_DATE_HEADERS = {"date", "form_fill_date", "submission_date"}
FORBIDDEN_FORM_FILL_KEYS = {
    "name",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "email_address",
    "phone",
    "phone_number",
    "message",
    "comments",
    "comment",
    "notes",
    "note",
    "ip",
    "ip_address",
    "user_agent",
    "address",
    "street",
    "city",
    "state",
    "zip",
    "postal_code",
    "payload",
    "raw_submission",
    "form_payload",
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})\b")


class FormFillsImportError(ValueError):
    pass


@dataclass(frozen=True)
class FormFillsImportResult:
    output_path: Path
    total_form_fills: int
    date_count: int


def import_form_fills_dates(
    *,
    profile: str,
    input_path: Path,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    real_output: bool = False,
) -> FormFillsImportResult:
    dates = read_form_fill_dates(input_path)
    if not dates:
        raise FormFillsImportError("form fill input contains no dates")
    output_path = output_root / profile / FORM_FILLS_SUMMARY_FILENAME
    if real_output:
        _validate_local_real_output(output_root)
    payload = build_form_fills_summary_payload(profile=profile, dates=dates)
    validate_form_fills_summary(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return FormFillsImportResult(output_path=output_path, total_form_fills=len(dates), date_count=len(set(dates)))


def read_form_fill_dates(input_path: Path) -> list[date]:
    if not input_path.exists() or not input_path.is_file():
        raise FormFillsImportError(f"input file does not exist: {input_path}")
    if input_path.suffix.lower() == ".json":
        return _read_json_dates(input_path)
    return _read_csv_dates(input_path)


def build_form_fills_summary_payload(
    *,
    profile: str,
    dates: list[date],
    generated_at: str | None = None,
) -> dict[str, Any]:
    sorted_dates = sorted(dates)
    daily_counts = Counter(sorted_dates)
    monthly_counts = Counter(value.strftime("%Y-%m") for value in sorted_dates)
    generated_at = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "form_fills_summary.v1",
        "provider": "form_fills",
        "source_type": "date_only_local_real",
        "profile": profile,
        "client_label": _client_label(profile),
        "is_real_data": True,
        "generated_at": generated_at,
        "date_range": {
            "start_date": sorted_dates[0].isoformat(),
            "end_date": sorted_dates[-1].isoformat(),
        },
        "summary": {
            "total_form_fills": len(sorted_dates),
            "unique_form_fill_dates": len(daily_counts),
        },
        "time_series": [
            {"date": value.isoformat(), "form_fills": count}
            for value, count in sorted(daily_counts.items())
        ],
        "monthly_totals": [
            {"month": month, "form_fills": count}
            for month, count in sorted(monthly_counts.items())
        ],
        "data_quality_notes": [
            "Date-only local form-fill import.",
            "No names, emails, phone numbers, messages, IP addresses, or raw form payloads are stored.",
        ],
    }


def validate_form_fills_summary(payload: dict[str, Any]) -> None:
    filename = FORM_FILLS_SUMMARY_FILENAME
    if not isinstance(payload, dict):
        raise DashboardLabFixtureValidationError(f"{filename} must contain a JSON object")
    _reject_forbidden_form_fill_content(payload, filename)
    _require_fields(
        payload,
        filename,
        ["schema_version", "provider", "source_type", "profile", "client_label", "is_real_data", "date_range", "summary"],
    )
    if payload.get("schema_version") != "form_fills_summary.v1":
        raise DashboardLabFixtureValidationError(f"{filename} schema_version must be form_fills_summary.v1")
    if payload.get("provider") not in {"form_fills", "forms"}:
        raise DashboardLabFixtureValidationError(f"{filename} provider must be form_fills")
    if payload.get("source_type") not in {"date_only_local_real", "local_real"}:
        raise DashboardLabFixtureValidationError(f"{filename} source_type must be date_only_local_real or local_real")
    if not isinstance(payload.get("is_real_data"), bool):
        raise DashboardLabFixtureValidationError(f"{filename} is_real_data must be a boolean")
    _require_string(payload, "profile", filename)
    _require_string(payload, "client_label", filename)
    date_range = payload.get("date_range")
    if not isinstance(date_range, dict):
        raise DashboardLabFixtureValidationError(f"{filename} date_range must be an object")
    for field in ("start_date", "end_date"):
        _require_iso_date(date_range.get(field), f"{filename} date_range.{field}")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise DashboardLabFixtureValidationError(f"{filename} summary must be an object")
    total = _require_int(summary.get("total_form_fills"), f"{filename} summary.total_form_fills")
    time_series = payload.get("time_series")
    if not isinstance(time_series, list):
        raise DashboardLabFixtureValidationError(f"{filename} time_series must be an array")
    time_series_total = 0
    for index, row in enumerate(time_series, start=1):
        if not isinstance(row, dict):
            raise DashboardLabFixtureValidationError(f"{filename} time_series[{index}] must be an object")
        _require_iso_date(row.get("date"), f"{filename} time_series[{index}].date")
        time_series_total += _require_int(row.get("form_fills"), f"{filename} time_series[{index}].form_fills")
    if time_series_total != total:
        raise DashboardLabFixtureValidationError(f"{filename} time_series total must match summary.total_form_fills")
    monthly_totals = payload.get("monthly_totals", [])
    if monthly_totals is not None and not isinstance(monthly_totals, list):
        raise DashboardLabFixtureValidationError(f"{filename} monthly_totals must be an array")
    for index, row in enumerate(monthly_totals or [], start=1):
        if not isinstance(row, dict):
            raise DashboardLabFixtureValidationError(f"{filename} monthly_totals[{index}] must be an object")
        month = row.get("month")
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-\d{2}", month):
            raise DashboardLabFixtureValidationError(f"{filename} monthly_totals[{index}].month must be YYYY-MM")
        _require_int(row.get("form_fills"), f"{filename} monthly_totals[{index}].form_fills")


def _read_csv_dates(input_path: Path) -> list[date]:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise FormFillsImportError("form fill CSV must have a date header")
        headers = [_normalize_key(header) for header in reader.fieldnames]
        forbidden_headers = sorted(set(headers) & FORBIDDEN_FORM_FILL_KEYS)
        if forbidden_headers:
            raise FormFillsImportError(f"form fill CSV contains forbidden PII columns: {', '.join(forbidden_headers)}")
        date_headers = [header for header in headers if header in ALLOWED_DATE_HEADERS]
        if len(date_headers) != 1 or len(headers) != 1:
            raise FormFillsImportError("form fill CSV must contain exactly one date-only column")
        source_header = reader.fieldnames[headers.index(date_headers[0])]
        dates = []
        for row_number, row in enumerate(reader, start=2):
            value = (row.get(source_header) or "").strip()
            if not value:
                continue
            dates.append(_parse_iso_date(value, f"row {row_number}"))
        return dates


def _read_json_dates(input_path: Path) -> list[date]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FormFillsImportError("form fill JSON is not valid JSON") from exc
    _reject_forbidden_form_fill_content(payload, input_path.name)
    if isinstance(payload, dict):
        values = payload.get("dates")
    else:
        values = payload
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise FormFillsImportError("form fill JSON must be an array of ISO date strings or an object with dates")
    return [_parse_iso_date(value, f"dates[{index}]") for index, value in enumerate(values, start=1)]


def _parse_iso_date(value: str, location: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FormFillsImportError(f"invalid ISO date in {location}: {value}") from exc


def _require_iso_date(value: Any, location: str) -> None:
    if not isinstance(value, str):
        raise DashboardLabFixtureValidationError(f"{location} must be an ISO date string")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise DashboardLabFixtureValidationError(f"{location} must be an ISO date string") from exc


def _require_int(value: Any, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DashboardLabFixtureValidationError(f"{location} must be an integer")
    if value < 0:
        raise DashboardLabFixtureValidationError(f"{location} must be non-negative")
    return value


def _require_fields(payload: dict[str, Any], filename: str, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise DashboardLabFixtureValidationError(f"{filename} missing required fields: {', '.join(missing)}")


def _require_string(payload: dict[str, Any], field: str, filename: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DashboardLabFixtureValidationError(f"{filename} {field} must be a non-empty string")


def _reject_forbidden_form_fill_content(value: Any, filename: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = _normalize_key(key)
            if normalized_key in FORBIDDEN_FORM_FILL_KEYS:
                raise DashboardLabFixtureValidationError(f"{filename} contains forbidden form-fill detail key: {key}")
            _reject_forbidden_form_fill_content(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_form_fill_content(item, filename)
    elif isinstance(value, str):
        if EMAIL_PATTERN.search(value):
            raise DashboardLabFixtureValidationError(f"{filename} contains an email-looking value")
        if _looks_like_phone_number(value):
            raise DashboardLabFixtureValidationError(f"{filename} contains a phone-number-looking value")


def _looks_like_phone_number(value: str) -> bool:
    match = PHONE_PATTERN.search(value.strip())
    if not match:
        return False
    digits = re.sub(r"\D", "", match.group(0))
    return 10 <= len(digits) <= 11


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _validate_local_real_output(path: Path) -> None:
    normalized = path.as_posix().strip("/")
    if not (normalized == "exports/local-real/dashboard-lab" or normalized.startswith("exports/local-real/dashboard-lab/")):
        raise FormFillsImportError("real form-fill output must stay under exports/local-real/dashboard-lab")


def _client_label(profile: str) -> str:
    if profile == "wc-land-renewal":
        return "WC Land Renewal"
    return " ".join(part.capitalize() for part in profile.replace("_", "-").split("-") if part)
