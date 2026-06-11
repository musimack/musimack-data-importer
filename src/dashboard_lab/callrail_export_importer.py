from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .callrail_export_diagnostic import (
    EMAIL_RE,
    is_likely_google_ads_row,
    redact_sensitive_value,
    sanitize_landing_page,
)
from .paid_callrail_fixture_builder import DEFAULT_CLIENT_LABEL, DEFAULT_PROFILE
from .paid_callrail_validators import DashboardLabFixtureValidationError, validate_callrail_summary


DEFAULT_OUTPUT_ROOT = Path("exports") / "local-real" / "dashboard-lab"
CALLRAIL_SUMMARY_FILENAME = "callrail-summary.json"
MAX_KEYWORD_ROWS = 50
MAX_OPPORTUNITY_ROWS = 25

ANSWERED_HINTS = ("answered", "completed", "complete", "connected", "accepted")
MISSED_HINTS = ("missed", "unanswered", "no answer", "not answered", "voicemail", "abandoned")
TRUTHY_VALUES = {"yes", "true", "1", "y", "qualified", "first-time", "first time"}
FALSEY_VALUES = {"", "no", "false", "0", "n"}
QUALIFIED_TRUTHY_VALUES = TRUTHY_VALUES | {"call qualified", "good lead", "converted"}
QUALIFIED_FALSEY_VALUES = FALSEY_VALUES | {"not qualified"}
UNATTRIBUTED_SOURCE_LABEL = "Unattributed source"

FORBIDDEN_OUTPUT_KEYS = {
    "caller_name",
    "caller",
    "caller_phone",
    "caller_phone_number",
    "phone_number",
    "customer_name",
    "customer_phone",
    "contact_name",
    "contact_phone",
    "tracking_number",
    "destination_number",
    "recording",
    "recording_url",
    "recording_link",
    "transcript",
    "note",
    "call_highlights",
    "keywords_spotted",
    "call_log",
    "call_logs",
    "raw_call",
    "raw_calls",
    "individual_calls",
}
PHONE_VALUE_RE = re.compile(r"(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})\b")


class CallRailExportImportError(ValueError):
    pass


@dataclass
class CallRow:
    date_value: date | None
    keyword: str
    campaign: str
    landing_page: str
    source: str
    medium: str
    number_label: str
    duration_seconds: float | None
    is_first_time: bool
    is_qualified: bool
    is_answered: bool
    is_missed: bool
    is_google_ads: bool
    qualified_value_label: str
    keyword_wrappers_removed: bool


@dataclass
class GroupStats:
    calls: int = 0
    first_time_callers: int = 0
    answered_calls: int = 0
    missed_calls: int = 0
    qualified_calls: int = 0
    google_ads_calls: int = 0
    duration_total: float = 0.0
    duration_count: int = 0
    keywords: Counter[str] = field(default_factory=Counter)
    campaigns: Counter[str] = field(default_factory=Counter)
    landing_pages: Counter[str] = field(default_factory=Counter)
    sources: Counter[str] = field(default_factory=Counter)

    def add(self, row: CallRow) -> None:
        self.calls += 1
        self.first_time_callers += int(row.is_first_time)
        self.answered_calls += int(row.is_answered)
        self.missed_calls += int(row.is_missed)
        self.qualified_calls += int(row.is_qualified)
        self.google_ads_calls += int(row.is_google_ads)
        if row.duration_seconds is not None:
            self.duration_total += row.duration_seconds
            self.duration_count += 1
        if row.keyword:
            self.keywords[row.keyword] += 1
        if row.campaign:
            self.campaigns[row.campaign] += 1
        if row.landing_page:
            self.landing_pages[row.landing_page] += 1
        if row.source:
            self.sources[row.source] += 1

    @property
    def avg_duration_seconds(self) -> float:
        if self.duration_count == 0:
            return 0.0
        return round(self.duration_total / self.duration_count, 2)


@dataclass(frozen=True)
class CallRailImportResult:
    profile: str
    output_path: Path
    payload: dict[str, Any]


def import_callrail_export(
    *,
    profile: str,
    input_path: Path | str,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    start_date: str | None = None,
    end_date: str | None = None,
    granularity: str = "monthly",
    real_output: bool = False,
    dry_run: bool = False,
    validate_only: bool = False,
) -> CallRailImportResult:
    if not profile:
        raise CallRailExportImportError("profile is required")
    if granularity not in {"daily", "weekly", "monthly"}:
        raise CallRailExportImportError("granularity must be daily, weekly, or monthly")

    output_root_path = Path(output_root)
    output_path = output_root_path / profile / CALLRAIL_SUMMARY_FILENAME
    _ensure_safe_output(output_root_path, real_output=real_output, dry_run=dry_run or validate_only)

    rows, raw_count = _read_rows(Path(input_path))
    parsed_start = _parse_date_arg(start_date, "start-date")
    parsed_end = _parse_date_arg(end_date, "end-date")
    included, skipped_invalid_dates, skipped_by_date = _included_call_rows(
        rows,
        start_date=parsed_start,
        end_date=parsed_end,
    )
    payload = build_callrail_summary_payload(
        profile=profile,
        rows=included,
        raw_rows_read=raw_count,
        rows_skipped_invalid_date=skipped_invalid_dates,
        rows_skipped_by_date=skipped_by_date,
        requested_start_date=parsed_start,
        requested_end_date=parsed_end,
        granularity=granularity,
    )
    assert_callrail_payload_is_aggregate_safe(payload)
    validate_callrail_summary(payload)

    if not dry_run and not validate_only:
        _write_json(output_path, payload)
        validate_callrail_summary(json.loads(output_path.read_text(encoding="utf-8")))

    return CallRailImportResult(profile=profile, output_path=output_path, payload=payload)


def build_callrail_summary_payload(
    *,
    profile: str,
    rows: list[CallRow],
    raw_rows_read: int,
    rows_skipped_invalid_date: int,
    rows_skipped_by_date: int,
    requested_start_date: date | None,
    requested_end_date: date | None,
    granularity: str,
) -> dict[str, Any]:
    total = GroupStats()
    keyword_groups: dict[tuple[str, str, str], GroupStats] = defaultdict(GroupStats)
    campaign_groups: dict[str, GroupStats] = defaultdict(GroupStats)
    landing_page_groups: dict[str, GroupStats] = defaultdict(GroupStats)
    source_groups: dict[str, GroupStats] = defaultdict(GroupStats)
    tracking_label_groups: dict[str, GroupStats] = defaultdict(GroupStats)
    time_groups: dict[str, GroupStats] = defaultdict(GroupStats)

    calls_with_keyword = 0
    calls_without_keyword = 0
    calls_without_campaign = 0
    calls_without_landing_page = 0
    ambiguous_status_calls = 0
    qualified_value_counts: Counter[str] = Counter()
    keyword_wrappers_removed = 0
    unattributed_source_calls = 0

    for row in rows:
        total.add(row)
        qualified_value_counts[row.qualified_value_label] += 1
        if row.keyword and row.keyword_wrappers_removed:
            keyword_wrappers_removed += 1
        if row.keyword:
            calls_with_keyword += 1
            keyword_groups[(row.keyword, row.campaign, row.landing_page)].add(row)
        else:
            calls_without_keyword += 1
        if not row.campaign:
            calls_without_campaign += 1
        else:
            campaign_groups[row.campaign].add(row)
        if not row.landing_page:
            calls_without_landing_page += 1
        else:
            landing_page_groups[row.landing_page].add(row)
        source_label = row.source or UNATTRIBUTED_SOURCE_LABEL
        if source_label == UNATTRIBUTED_SOURCE_LABEL:
            unattributed_source_calls += 1
        source_groups[source_label].add(row)
        if row.number_label:
            tracking_label_groups[row.number_label].add(row)
        if row.date_value:
            time_groups[_period_key(row.date_value, granularity)].add(row)
        if not row.is_answered and not row.is_missed:
            ambiguous_status_calls += 1

    start_date, end_date = _date_range(rows, requested_start_date, requested_end_date)
    keyword_rows = _keyword_rows(keyword_groups)
    campaign_rows = _campaign_rows(campaign_groups)
    landing_page_rows = _landing_page_rows(landing_page_groups)
    source_rows = _source_rows(source_groups)
    tracking_number_rows = _tracking_number_rows(tracking_label_groups)
    missed_opportunities = _missed_call_opportunities(keyword_groups)
    time_series = _time_series(time_groups)

    top_keyword = _top_counter_value(total.keywords)
    top_campaign = _top_counter_value(total.campaigns)
    data_quality_notes = [
        f"Raw rows read: {raw_rows_read}.",
        f"Rows included after date filtering: {len(rows)}.",
        f"Rows skipped for invalid date: {rows_skipped_invalid_date}.",
        f"Rows skipped by date filter: {rows_skipped_by_date}.",
        f"Rows without keyword attribution: {calls_without_keyword}.",
        f"Rows without campaign attribution: {calls_without_campaign}.",
        f"Rows without landing page: {calls_without_landing_page}.",
        f"Rows likely Google Ads attributed: {total.google_ads_calls}.",
        f"Qualified field values observed: {_format_counter(qualified_value_counts)}.",
        "Tracking number values were not output; tracking rows use safe labels only when available.",
        "Output is aggregate-only and contains no caller-level details.",
    ]
    if ambiguous_status_calls:
        data_quality_notes.append(f"Rows with ambiguous call status: {ambiguous_status_calls}.")
    if keyword_wrappers_removed:
        data_quality_notes.append("Keyword display values were normalized by removing simple match-type wrappers.")
    if unattributed_source_calls:
        plural = "call did" if unattributed_source_calls == 1 else "calls did"
        data_quality_notes.append(f"{unattributed_source_calls} {plural} not include source attribution.")

    return {
        "schema_version": "callrail_summary.v1",
        "provider": "callrail",
        "profile": profile,
        "client_label": _client_label_for_profile(profile),
        "source": "local_export",
        "is_real_data": True,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "date_range": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "summary": {
            "total_calls": total.calls,
            "google_ads_calls": total.google_ads_calls,
            "first_time_callers": total.first_time_callers,
            "answered_calls": total.answered_calls,
            "missed_calls": total.missed_calls,
            "avg_duration_seconds": total.avg_duration_seconds,
            "qualified_calls": total.qualified_calls,
            "calls_with_keyword_attribution": calls_with_keyword,
            "calls_without_keyword_attribution": calls_without_keyword,
        },
        "paid_search_attribution": {
            "google_ads_calls": total.google_ads_calls,
            "calls_with_keyword_attribution": calls_with_keyword,
            "top_keyword": top_keyword,
            "top_campaign": top_campaign,
            "missed_keyword_calls": sum(row["missed_calls"] for row in keyword_rows),
            "attribution_unavailable_calls": calls_without_keyword,
            "notes": [
                "Local CallRail export import for dashboard-lab aggregate reporting.",
                "Keyword attribution is primary when present; missing keyword rows are counted separately.",
            ],
        },
        "keyword_rows": keyword_rows,
        "campaign_rows": campaign_rows,
        "landing_page_rows": landing_page_rows,
        "source_rows": source_rows,
        "tracking_number_rows": tracking_number_rows,
        "missed_call_opportunities": missed_opportunities,
        "time_series": time_series,
        "data_quality_notes": data_quality_notes,
    }


def assert_callrail_payload_is_aggregate_safe(payload: dict[str, Any]) -> None:
    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized_key = _normalize_key(key)
                if normalized_key in FORBIDDEN_OUTPUT_KEYS:
                    raise CallRailExportImportError(f"unsafe CallRail output key blocked: {path}.{key}")
                walk(nested, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            if _looks_like_phone_number(value) or EMAIL_RE.search(value):
                raise CallRailExportImportError(f"unsafe CallRail output value blocked at {path}")
            lowered = value.lower()
            if "recording url" in lowered or "recording_url" in lowered or "transcript" in lowered:
                raise CallRailExportImportError(f"unsafe CallRail output text blocked at {path}")

    walk(payload, "")


def _read_rows(input_path: Path) -> tuple[list[dict[str, str | None]], int]:
    try:
        with input_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except OSError as exc:
        raise CallRailExportImportError(f"CallRail CSV could not be read: {exc}") from exc
    return rows, len(rows)


def _included_call_rows(
    raw_rows: list[dict[str, str | None]],
    *,
    start_date: date | None,
    end_date: date | None,
) -> tuple[list[CallRow], int, int]:
    included = []
    skipped_invalid_dates = 0
    skipped_by_date = 0
    for row in raw_rows:
        parsed_date = _parse_call_date(_value(row, "Start Time"))
        if _value(row, "Start Time") and parsed_date is None:
            skipped_invalid_dates += 1
            continue
        if parsed_date and start_date and parsed_date < start_date:
            skipped_by_date += 1
            continue
        if parsed_date and end_date and parsed_date > end_date:
            skipped_by_date += 1
            continue
        included.append(_to_call_row(row, parsed_date))
    return included, skipped_invalid_dates, skipped_by_date


def _to_call_row(row: dict[str, str | None], parsed_date: date | None) -> CallRow:
    status = _value(row, "Call Status")
    raw_keyword = _safe_aggregate_text(_value(row, "Keywords"))
    keyword, keyword_wrappers_removed = _normalize_keyword(raw_keyword)
    campaign = _safe_aggregate_text(_value(row, "Campaign"))
    landing_page = sanitize_landing_page(_value(row, "Landing Page")) if _value(row, "Landing Page") else ""
    source = _safe_aggregate_text(_value(row, "Source")) or UNATTRIBUTED_SOURCE_LABEL
    medium = _safe_aggregate_text(_value(row, "Medium"))
    number_label = _safe_aggregate_text(_value(row, "Number Name"))
    if number_label == "[redacted]":
        number_label = "Tracking label unavailable"
    return CallRow(
        date_value=parsed_date,
        keyword="" if keyword == "[redacted]" else keyword,
        campaign="" if campaign == "[redacted]" else campaign,
        landing_page="" if landing_page == "[redacted]" else landing_page,
        source=source,
        medium=medium,
        number_label=number_label,
        duration_seconds=_parse_duration(_value(row, "Duration (seconds)")),
        is_first_time=_parse_bool(_value(row, "First-Time Caller")),
        is_qualified=_parse_qualified(_value(row, "Qualified")),
        is_answered=_is_answered_status(status),
        is_missed=_is_missed_status(status),
        is_google_ads=is_likely_google_ads_row(row),
        qualified_value_label=_qualified_value_label(_value(row, "Qualified")),
        keyword_wrappers_removed=keyword_wrappers_removed,
    )


def _keyword_rows(groups: dict[tuple[str, str, str], GroupStats]) -> list[dict[str, Any]]:
    rows = []
    for (keyword, campaign, landing_page), stats in groups.items():
        rows.append(
            {
                "keyword": keyword,
                "campaign": campaign,
                "calls": stats.calls,
                "first_time_callers": stats.first_time_callers,
                "answered_calls": stats.answered_calls,
                "missed_calls": stats.missed_calls,
                "avg_duration_seconds": stats.avg_duration_seconds,
                "qualified_calls": stats.qualified_calls,
                "landing_page": landing_page,
                "source": "google_ads" if stats.google_ads_calls else "callrail",
                "cost": None,
                "cost_per_call": None,
            }
        )
    rows.sort(key=lambda item: (-item["calls"], item["keyword"], item["campaign"], item["landing_page"]))
    return rows[:MAX_KEYWORD_ROWS]


def _campaign_rows(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    rows = [
        {
            "campaign": campaign,
            "calls": stats.calls,
            "first_time_callers": stats.first_time_callers,
            "answered_calls": stats.answered_calls,
            "missed_calls": stats.missed_calls,
            "avg_duration_seconds": stats.avg_duration_seconds,
            "qualified_calls": stats.qualified_calls,
            "cost": None,
            "cost_per_call": None,
        }
        for campaign, stats in groups.items()
    ]
    rows.sort(key=lambda item: (-item["calls"], item["campaign"]))
    return rows


def _landing_page_rows(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    rows = []
    for landing_page, stats in groups.items():
        row = {
            "landing_page": landing_page,
            "calls": stats.calls,
            "answered_calls": stats.answered_calls,
            "missed_calls": stats.missed_calls,
            "first_time_callers": stats.first_time_callers,
            "avg_duration_seconds": stats.avg_duration_seconds,
        }
        keyword = _top_counter_value(stats.keywords)
        campaign = _top_counter_value(stats.campaigns)
        if keyword:
            row["keyword"] = keyword
        if campaign:
            row["campaign"] = campaign
        rows.append(row)
    rows.sort(key=lambda item: (-item["calls"], item["landing_page"]))
    return rows


def _source_rows(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    rows = [
        {
            "source": source,
            "calls": stats.calls,
            "answered_calls": stats.answered_calls,
            "missed_calls": stats.missed_calls,
            "first_time_callers": stats.first_time_callers,
            "avg_duration_seconds": stats.avg_duration_seconds,
        }
        for source, stats in groups.items()
    ]
    rows.sort(key=lambda item: (-item["calls"], item["source"]))
    return rows


def _tracking_number_rows(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    rows = []
    for label, stats in groups.items():
        if not label:
            continue
        source = _tracking_source_label(stats.sources)
        rows.append(
            {
                "tracking_number_label": label,
                "source": source,
                "calls": stats.calls,
                "answered_calls": stats.answered_calls,
                "missed_calls": stats.missed_calls,
                "first_time_callers": stats.first_time_callers,
            }
        )
    rows.sort(key=lambda item: (-item["calls"], item["tracking_number_label"]))
    return rows


def _missed_call_opportunities(groups: dict[tuple[str, str, str], GroupStats]) -> list[dict[str, Any]]:
    rows = []
    for (keyword, campaign, _landing_page), stats in groups.items():
        if stats.missed_calls <= 0:
            continue
        rows.append(
            {
                "keyword": keyword,
                "campaign": campaign,
                "missed_calls": stats.missed_calls,
                "total_calls": stats.calls,
                "why_it_matters": "Missed calls from attributed paid search traffic can represent booking intent that did not reach the team.",
                "recommended_action": "Review follow-up process for missed calls from paid search traffic.",
                "priority": _priority(stats.missed_calls),
            }
        )
    rows.sort(key=lambda item: (-item["missed_calls"], -item["total_calls"], item["keyword"]))
    return rows[:MAX_OPPORTUNITY_ROWS]


def _time_series(groups: dict[str, GroupStats]) -> list[dict[str, Any]]:
    rows = [
        {
            "date": period,
            "total_calls": stats.calls,
            "answered_calls": stats.answered_calls,
            "missed_calls": stats.missed_calls,
            "first_time_callers": stats.first_time_callers,
            "google_ads_calls": stats.google_ads_calls,
        }
        for period, stats in groups.items()
    ]
    rows.sort(key=lambda item: item["date"])
    return rows


def _priority(missed_calls: int) -> str:
    if missed_calls >= 5:
        return "High"
    if missed_calls >= 2:
        return "Medium"
    return "Low"


def _period_key(value: date, granularity: str) -> str:
    if granularity == "daily":
        return value.isoformat()
    if granularity == "weekly":
        monday = value.fromordinal(value.toordinal() - value.weekday())
        return monday.isoformat()
    return value.replace(day=1).isoformat()


def _date_range(
    rows: list[CallRow],
    requested_start_date: date | None,
    requested_end_date: date | None,
) -> tuple[date | None, date | None]:
    dates = [row.date_value for row in rows if row.date_value is not None]
    start = requested_start_date or (min(dates) if dates else None)
    end = requested_end_date or (max(dates) if dates else None)
    return start, end


def _parse_date_arg(value: str | None, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CallRailExportImportError(f"{label} must use YYYY-MM-DD") from exc


def _parse_call_date(value: str) -> date | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_duration(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUTHY_VALUES:
        return True
    if normalized in FALSEY_VALUES:
        return False
    return any(token in normalized for token in ("first-time", "first time"))


def _parse_qualified(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in QUALIFIED_FALSEY_VALUES:
        return False
    if normalized in QUALIFIED_TRUTHY_VALUES:
        return True
    try:
        return float(normalized) > 0
    except ValueError:
        return False


def _qualified_value_label(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "blank"
    safe = redact_sensitive_value(stripped)
    return safe if safe else "blank"


def _is_answered_status(value: str) -> bool:
    normalized = value.strip().lower()
    return any(hint in normalized for hint in ANSWERED_HINTS)


def _is_missed_status(value: str) -> bool:
    normalized = value.strip().lower()
    return any(hint in normalized for hint in MISSED_HINTS)


def _safe_aggregate_text(value: str) -> str:
    return redact_sensitive_value(value).strip()


def _normalize_keyword(value: str) -> tuple[str, bool]:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip(), True
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1].strip(), True
    return stripped, False


def _top_counter_value(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _tracking_source_label(counter: Counter[str]) -> str:
    if not counter:
        return UNATTRIBUTED_SOURCE_LABEL
    if len(counter) == 1:
        return counter.most_common(1)[0][0]
    return "Mixed sources"


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))


def _value(row: dict[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def _client_label_for_profile(profile: str) -> str:
    if profile == DEFAULT_PROFILE:
        return DEFAULT_CLIENT_LABEL
    return profile.replace("-", " ").title()


def _ensure_safe_output(output_root: Path, *, real_output: bool, dry_run: bool) -> None:
    normalized = output_root.as_posix().strip("/")
    if not real_output and not dry_run:
        raise CallRailExportImportError("--real-output is required before writing real CallRail-derived output")
    if normalized == "exports/dashboard-lab" or normalized.startswith("exports/dashboard-lab/"):
        raise CallRailExportImportError("refusing to write real CallRail-derived output into exports/dashboard-lab")
    if not dry_run and not (
        normalized == "exports/local-real/dashboard-lab" or normalized.startswith("exports/local-real/dashboard-lab/")
    ):
        raise CallRailExportImportError("real CallRail-derived output must stay under exports/local-real/dashboard-lab")


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _looks_like_phone_number(value: str) -> bool:
    match = PHONE_VALUE_RE.search(value.strip())
    if not match:
        return False
    digits = re.sub(r"\D", "", match.group(0))
    return 10 <= len(digits) <= 11


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
