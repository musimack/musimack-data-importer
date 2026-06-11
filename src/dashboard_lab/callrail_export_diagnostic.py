from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


EXPECTED_HEADERS = [
    "Call Status",
    "Company Name",
    "Company ID",
    "Number Name",
    "Tracking Number",
    "Name",
    "Phone Number",
    "Email",
    "First-Time Caller",
    "City",
    "State",
    "Country",
    "Agent Name",
    "Agent Number",
    "Source",
    "Duration (seconds)",
    "Start Time",
    "Device Type",
    "Keywords",
    "Referrer",
    "Medium",
    "Landing Page",
    "Campaign",
    "Value",
    "Tags",
    "Qualified",
    "Destination Number",
    "Browser",
    "Google Ads gclid",
    "Facebook fbclid",
    "Keywords Spotted",
    "Call Highlights",
    "Match Type",
    "Ad Group",
    "Ad Position",
    "utm_medium",
    "utm_source",
    "Customer Talk Time Percent",
    "Agent Talk Time Percent",
    "Active Page",
    "Recording Url",
    "Note",
]

SENSITIVE_HEADERS = {
    "Tracking Number",
    "Name",
    "Phone Number",
    "Email",
    "Agent Name",
    "Agent Number",
    "Destination Number",
    "Recording Url",
    "Note",
    "Call Highlights",
    "Keywords Spotted",
    "Referrer",
    "Active Page",
    "City",
    "State",
    "Country",
    "Browser",
}

PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){7,}")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PERSONAL_PATH_RE = re.compile(r"/(?:users?|customers?|clients?|contacts?|callers?)/[^/?#]+", re.IGNORECASE)
PAID_HINT_RE = re.compile(r"google\s*ads|paid\s*search|ppc|\bcpc\b", re.IGNORECASE)


@dataclass(frozen=True)
class CallRailExportDiagnostic:
    input_path: str
    profile: str | None
    parsed_successfully: bool
    row_count: int
    detected_headers: list[str]
    missing_expected_headers: list[str]
    sensitive_headers_detected: list[str]
    mapping_readiness: dict[str, bool]
    aggregate_counts: dict[str, int]
    value_diversity_counts: dict[str, int]
    top_examples: dict[str, list[tuple[str, int]]]
    qualified_value_counts: list[tuple[str, int]]


def diagnose_callrail_export_shape(
    input_path: Path,
    profile: str | None = None,
    max_sample_values: int = 5,
) -> CallRailExportDiagnostic:
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [header for header in (reader.fieldnames or []) if header is not None]
        rows = list(reader)

    header_set = set(headers)
    missing_expected = [header for header in EXPECTED_HEADERS if header not in header_set]
    sensitive_detected = [header for header in EXPECTED_HEADERS if header in header_set and header in SENSITIVE_HEADERS]

    keyword_counter: Counter[str] = Counter()
    campaign_counter: Counter[str] = Counter()
    landing_page_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    medium_counter: Counter[str] = Counter()
    qualified_counter: Counter[str] = Counter()

    counts = {
        "total_rows": len(rows),
        "rows_with_keyword_present": 0,
        "rows_without_keyword": 0,
        "rows_with_campaign_present": 0,
        "rows_with_landing_page_present": 0,
        "rows_with_gclid_present": 0,
        "rows_likely_google_ads_attributed": 0,
        "rows_with_qualified_value_present": 0,
        "rows_with_duration_present": 0,
        "rows_with_call_status_present": 0,
    }

    for row in rows:
        keyword = _value(row, "Keywords")
        campaign = _value(row, "Campaign")
        landing_page = _value(row, "Landing Page")
        source = _value(row, "Source")
        medium = _value(row, "Medium")
        utm_medium = _value(row, "utm_medium")
        utm_source = _value(row, "utm_source")
        gclid = _value(row, "Google Ads gclid")

        _count_presence(counts, "rows_with_keyword_present", keyword)
        _count_presence(counts, "rows_with_campaign_present", campaign)
        _count_presence(counts, "rows_with_landing_page_present", landing_page)
        _count_presence(counts, "rows_with_gclid_present", gclid)
        _count_presence(counts, "rows_with_qualified_value_present", _value(row, "Qualified"))
        _count_presence(counts, "rows_with_duration_present", _value(row, "Duration (seconds)"))
        _count_presence(counts, "rows_with_call_status_present", _value(row, "Call Status"))

        if not keyword:
            counts["rows_without_keyword"] += 1
        if is_likely_google_ads_row(row):
            counts["rows_likely_google_ads_attributed"] += 1

        _add_safe_value(keyword_counter, keyword)
        _add_safe_value(campaign_counter, campaign)
        _add_safe_landing_page(landing_page_counter, landing_page)
        _add_safe_value(source_counter, source)
        _add_safe_value(medium_counter, medium)
        _add_safe_value(medium_counter, utm_medium)
        _add_safe_value(source_counter, utm_source)
        _add_safe_value(qualified_counter, _value(row, "Qualified") or "blank")

    mapping_readiness = {
        "keyword_field_present": "Keywords" in header_set,
        "campaign_field_present": "Campaign" in header_set,
        "landing_page_field_present": "Landing Page" in header_set,
        "source_field_present": "Source" in header_set,
        "medium_or_utm_or_gclid_fields_present": any(
            header in header_set for header in ["Medium", "utm_medium", "utm_source", "Google Ads gclid"]
        ),
        "duration_field_present": "Duration (seconds)" in header_set,
        "status_field_present": "Call Status" in header_set,
        "first_time_caller_field_present": "First-Time Caller" in header_set,
        "qualified_field_present": "Qualified" in header_set,
    }

    top_examples = {
        "keywords": _top_items(keyword_counter, max_sample_values),
        "campaigns": _top_items(campaign_counter, max_sample_values),
        "landing_pages": _top_items(landing_page_counter, max_sample_values),
        "sources": _top_items(source_counter, max_sample_values),
        "mediums": _top_items(medium_counter, max_sample_values),
    }

    return CallRailExportDiagnostic(
        input_path=str(input_path),
        profile=profile,
        parsed_successfully=True,
        row_count=len(rows),
        detected_headers=headers,
        missing_expected_headers=missing_expected,
        sensitive_headers_detected=sensitive_detected,
        mapping_readiness=mapping_readiness,
        aggregate_counts=counts,
        value_diversity_counts={
            "unique_keywords": len(keyword_counter),
            "unique_campaigns": len(campaign_counter),
            "unique_landing_pages": len(landing_page_counter),
            "unique_sources": len(source_counter),
            "unique_mediums": len(medium_counter),
        },
        top_examples=top_examples,
        qualified_value_counts=_top_items(qualified_counter, max_sample_values),
    )


def is_likely_google_ads_row(row: dict[str, str | None]) -> bool:
    keyword = _value(row, "Keywords")
    source = _value(row, "Source")
    medium = _value(row, "Medium")
    utm_source = _value(row, "utm_source")
    utm_medium = _value(row, "utm_medium")
    gclid = _value(row, "Google Ads gclid")

    if gclid:
        return True
    if utm_source.lower() == "google" and utm_medium.lower() in {"cpc", "paid_search"}:
        return True
    if PAID_HINT_RE.search(source) or PAID_HINT_RE.search(medium):
        return True
    return bool(keyword and (PAID_HINT_RE.search(source) or PAID_HINT_RE.search(medium)))


def diagnostic_to_lines(diagnostic: CallRailExportDiagnostic) -> list[str]:
    lines = [
        "CallRail CSV export shape diagnostic",
        "Output is aggregate-only. Raw rows and sensitive field values are not printed.",
        f"CSV parsed successfully: {'yes' if diagnostic.parsed_successfully else 'no'}",
        f"Input: {diagnostic.input_path}",
    ]
    if diagnostic.profile:
        lines.append(f"Profile: {diagnostic.profile}")
    lines.extend(
        [
            f"Row count: {diagnostic.row_count}",
            "",
            "Detected headers:",
        ]
    )
    lines.extend(_bullet_lines(diagnostic.detected_headers))
    lines.append("")
    lines.append("Missing expected headers:")
    lines.extend(_bullet_lines(diagnostic.missing_expected_headers, empty="[none]"))
    lines.append("")
    lines.append("Sensitive headers detected:")
    lines.extend(_bullet_lines(diagnostic.sensitive_headers_detected, empty="[none]"))
    lines.append("")
    lines.append("Mapping readiness:")
    for key, value in diagnostic.mapping_readiness.items():
        lines.append(f"- {key}: {'yes' if value else 'no'}")
    lines.append("")
    lines.append("Safe aggregate counts:")
    for key, value in diagnostic.aggregate_counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Value diversity counts:")
    for key, value in diagnostic.value_diversity_counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("Qualified value counts:")
    if not diagnostic.qualified_value_counts:
        lines.append("- [none]")
    else:
        for value, count in diagnostic.qualified_value_counts:
            lines.append(f"- {value}: {count}")
    lines.append("")
    lines.append("Safe top examples:")
    for label, items in diagnostic.top_examples.items():
        lines.append(f"- {label}:")
        if not items:
            lines.append("  - [none]")
            continue
        for value, count in items:
            lines.append(f"  - {value}: {count}")
    return lines


def _value(row: dict[str, str | None], key: str) -> str:
    return (row.get(key) or "").strip()


def _count_presence(counts: dict[str, int], key: str, value: str) -> None:
    if value:
        counts[key] += 1


def _add_safe_value(counter: Counter[str], value: str) -> None:
    if not value:
        return
    counter[redact_sensitive_value(value)] += 1


def _add_safe_landing_page(counter: Counter[str], value: str) -> None:
    if not value:
        return
    counter[sanitize_landing_page(value)] += 1


def _top_items(counter: Counter[str], max_items: int) -> list[tuple[str, int]]:
    return counter.most_common(max(0, max_items))


def _bullet_lines(values: list[str], empty: str = "[none]") -> list[str]:
    if not values:
        return [f"- {empty}"]
    return [f"- {value}" for value in values]


def redact_sensitive_value(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    if EMAIL_RE.search(stripped) or PHONE_RE.search(stripped):
        return "[redacted]"
    return stripped


def sanitize_landing_page(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    if PERSONAL_PATH_RE.search(stripped):
        return "[redacted]"
    parsed = urlsplit(stripped)
    if parsed.scheme and parsed.netloc:
        safe_path = parsed.path or "/"
        if PERSONAL_PATH_RE.search(safe_path) or redact_sensitive_value(urlunsplit((parsed.scheme, parsed.netloc, safe_path, "", ""))) == "[redacted]":
            return "[redacted]"
        return safe_path
    path = stripped.split("?", 1)[0].split("#", 1)[0] or "/"
    if PERSONAL_PATH_RE.search(path) or redact_sensitive_value(path) == "[redacted]":
        return "[redacted]"
    return path
