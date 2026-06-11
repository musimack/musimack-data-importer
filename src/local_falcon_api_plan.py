from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .dashboard_lab.fixture_builder import PROFILES


DEFAULT_BASE_URL = "https://api.localfalcon.com"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2


class LocalFalconApiPlanError(ValueError):
    pass


@dataclass(frozen=True)
class LocalFalconApiReportPlan:
    keyword: str
    report_id: str
    relationship: str | None = None
    source_id: str | None = None
    source_label: str | None = None
    query_type: str | None = None
    query: str | None = None
    scan_kind: str | None = None


@dataclass(frozen=True)
class LocalFalconApiFetchPlan:
    profile: str
    output: Path
    reports: list[LocalFalconApiReportPlan]
    featured_keyword_id: str | None
    merge_mode: str
    dry_run: bool
    no_write: bool
    timeout_seconds: int
    max_retries: int
    api_key_env: str
    api_key_configured: bool
    api_key_redacted: str
    base_url: str


def default_output_path(profile: str) -> Path:
    _validate_profile(profile)
    return Path("exports") / "local-real" / "dashboard-lab" / profile / "local-falcon-summary.json"


def build_direct_plan(
    *,
    profile: str | None,
    keyword: str | None,
    report_id: str | None,
    output: str | None = None,
    featured_keyword_id: str | None = None,
    replace: bool = False,
    append: bool = False,
    dry_run: bool = True,
    no_write: bool = False,
    timeout: int | None = None,
    max_retries: int | None = None,
    api_key_env: str | None = None,
    allow_global_api_key: bool = True,
    env: Mapping[str, str] | None = None,
) -> LocalFalconApiFetchPlan:
    if not profile:
        raise LocalFalconApiPlanError("--profile is required")
    _validate_profile(profile)
    if not keyword or not keyword.strip():
        raise LocalFalconApiPlanError("--keyword is required for direct report dry-run planning")
    if not report_id or not report_id.strip():
        raise LocalFalconApiPlanError("--report-id is required for direct report dry-run planning")
    return _build_plan(
        profile=profile,
        output=Path(output) if output else default_output_path(profile),
        reports=[
            LocalFalconApiReportPlan(
                keyword=keyword.strip(),
                report_id=report_id.strip(),
                query=keyword.strip(),
            )
        ],
        featured_keyword_id=_clean_optional(featured_keyword_id),
        replace=replace,
        append=append,
        dry_run=dry_run,
        no_write=no_write,
        timeout=timeout,
        max_retries=max_retries,
        api_key_env=api_key_env,
        allow_global_api_key=allow_global_api_key,
        env=env,
    )


def build_manifest_plan(
    manifest_path: Path,
    *,
    profile_override: str | None = None,
    output_override: str | None = None,
    featured_keyword_id_override: str | None = None,
    replace: bool = False,
    append: bool = False,
    dry_run: bool = True,
    no_write: bool = False,
    timeout: int | None = None,
    max_retries: int | None = None,
    api_key_env: str | None = None,
    allow_global_api_key: bool = True,
    env: Mapping[str, str] | None = None,
) -> LocalFalconApiFetchPlan:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalFalconApiPlanError("manifest is not valid JSON") from exc
    except OSError as exc:
        raise LocalFalconApiPlanError("manifest could not be read") from exc
    if not isinstance(payload, dict):
        raise LocalFalconApiPlanError("manifest must contain a JSON object")

    profile = profile_override or _required_string(payload, "profile", "manifest profile is required")
    _validate_profile(profile)
    reports_payload = payload.get("reports")
    if not isinstance(reports_payload, list) or not reports_payload:
        raise LocalFalconApiPlanError("manifest reports must be a non-empty array")
    reports = []
    for index, item in enumerate(reports_payload, start=1):
        if not isinstance(item, dict):
            raise LocalFalconApiPlanError(f"manifest report {index} must be an object")
        query = _clean_optional(item.get("query")) or _clean_optional(item.get("keyword"))
        if not query:
            raise LocalFalconApiPlanError(f"manifest report {index} query is required")
        reports.append(
            LocalFalconApiReportPlan(
                keyword=query,
                report_id=_required_string(item, "report_id", f"manifest report {index} report_id is required"),
                relationship=_clean_optional(item.get("relationship")),
                source_id=_clean_optional(item.get("source_id")) or _source_id_from_label(_clean_optional(item.get("source"))),
                source_label=_clean_optional(item.get("source_label")) or _clean_optional(item.get("source")),
                query_type=_clean_optional(item.get("query_type")) or _query_type_from_source(_clean_optional(item.get("source"))),
                query=query,
                scan_kind=_clean_optional(item.get("scan_kind")) or _scan_kind_from_source(_clean_optional(item.get("source"))),
            )
        )

    output_text = output_override or _clean_optional(payload.get("output"))
    featured_keyword_id = (
        featured_keyword_id_override
        or _clean_optional(payload.get("featured_scan_id"))
        or _clean_optional(payload.get("featured_keyword_id"))
    )
    return _build_plan(
        profile=profile,
        output=Path(output_text) if output_text else default_output_path(profile),
        reports=reports,
        featured_keyword_id=featured_keyword_id,
        replace=replace,
        append=append,
        dry_run=dry_run,
        no_write=no_write,
        timeout=timeout,
        max_retries=max_retries,
        api_key_env=api_key_env,
        allow_global_api_key=allow_global_api_key,
        env=env,
    )


def redacted_api_key(value: str | None) -> str:
    if not value:
        return "[not configured]"
    text = str(value)
    if len(text) <= 4:
        return "****"
    prefix = text[:3] if len(text) >= 8 else ""
    return f"{prefix}****{text[-4:]}"


def mask_report_id(report_id: str) -> str:
    text = str(report_id)
    if not text:
        return "[missing]"
    if len(text) <= 4:
        return "****"
    return f"****{text[-4:]}"


def redact_query_text(query: str, *, visible_chars: int = 18) -> str:
    text = " ".join(str(query).split())
    if not text:
        return "[missing]"
    if len(text) <= visible_chars:
        return f"{text[: max(3, visible_chars // 2)]}... [redacted]"
    return f"{text[:visible_chars]}... [redacted]"


def summarize_source_counts(reports: list[LocalFalconApiReportPlan]) -> Counter[str]:
    return Counter(report.source_label or report.source_id or "Local Falcon" for report in reports)


def summarize_query_type_counts(reports: list[LocalFalconApiReportPlan]) -> Counter[str]:
    return Counter(report.query_type or "map_keyword" for report in reports)


def render_plan(plan: LocalFalconApiFetchPlan, *, verbose: bool = False) -> str:
    lines = [
        "Local Falcon API dry run only. No network requests will be made.",
        "",
        f"Profile: {plan.profile}",
        f"Output: {plan.output}",
        f"Mode: {plan.merge_mode}",
        f"Reports planned: {len(plan.reports)}",
    ]
    if plan.featured_keyword_id:
        lines.append(f"Featured keyword id: {plan.featured_keyword_id}")
    lines.append("")
    lines.append("Reports by source:")
    for source, count in sorted(summarize_source_counts(plan.reports).items()):
        lines.append(f"- {source}: {count}")
    lines.append("Reports by query type:")
    for query_type, count in sorted(summarize_query_type_counts(plan.reports).items()):
        lines.append(f"- {query_type}: {count}")
    lines.append("Report IDs and full keyword/prompt text are not printed.")
    if verbose:
        lines.append("")
        lines.append("Verbose report plan:")
        for index, report in enumerate(plan.reports, start=1):
            lines.append(f"{index}. Source: {report.source_label or report.source_id or 'Local Falcon'}")
            lines.append(f"   Query type: {report.query_type or 'map_keyword'}")
            lines.append(f"   Query: {redact_query_text(report.query or report.keyword)}")
            lines.append(f"   Report ID: {mask_report_id(report.report_id)}")
            if report.relationship:
                lines.append(f"   Relationship: {report.relationship}")
    lines.extend(
        [
            "",
            "Config:",
            f"- API key env: {plan.api_key_env or '[not selected]'}",
            f"- API key configured: {'yes' if plan.api_key_configured else 'no'}",
            f"- Base URL: {plan.base_url}",
            f"- Timeout: {plan.timeout_seconds} seconds",
            f"- Max retries: {plan.max_retries}",
            "",
            "Validation:",
            "- Manifest/direct arguments: passed",
            f"- Output path: {'ignored local-real path' if _is_local_real_path(plan.output) else 'custom path'}",
            "- Future validator: scripts/validate_local_falcon_summary.py",
            "",
            "Status:",
            "- Live API fetching is not implemented.",
            "- This command performed dry-run validation only.",
        ]
    )
    return "\n".join(lines)


def _build_plan(
    *,
    profile: str,
    output: Path,
    reports: list[LocalFalconApiReportPlan],
    featured_keyword_id: str | None,
    replace: bool,
    append: bool,
    dry_run: bool,
    no_write: bool,
    timeout: int | None,
    max_retries: int | None,
    api_key_env: str | None,
    allow_global_api_key: bool,
    env: Mapping[str, str] | None,
) -> LocalFalconApiFetchPlan:
    if replace and append:
        raise LocalFalconApiPlanError("--replace and --append cannot be used together")
    timeout_seconds = _positive_int(timeout, DEFAULT_TIMEOUT_SECONDS, "--timeout")
    retry_count = _non_negative_int(max_retries, DEFAULT_MAX_RETRIES, "--max-retries")
    source_env = os.environ if env is None else env
    resolved_api_key_env = _clean_optional(api_key_env)
    if not resolved_api_key_env and allow_global_api_key:
        resolved_api_key_env = "LOCAL_FALCON_API_KEY"
    api_key = source_env.get(resolved_api_key_env or "")
    base_url = source_env.get("LOCAL_FALCON_BASE_URL") or DEFAULT_BASE_URL
    return LocalFalconApiFetchPlan(
        profile=profile,
        output=output,
        reports=reports,
        featured_keyword_id=featured_keyword_id,
        merge_mode=_merge_mode(replace, append),
        dry_run=dry_run,
        no_write=no_write,
        timeout_seconds=timeout_seconds,
        max_retries=retry_count,
        api_key_env=resolved_api_key_env or "",
        api_key_configured=bool(api_key),
        api_key_redacted=redacted_api_key(api_key),
        base_url=base_url,
    )


def _merge_mode(replace: bool, append: bool) -> str:
    if replace:
        return "replace matching keyword scans"
    if append:
        return "append new keyword scans"
    return "append/update keyword scans"


def _validate_profile(profile: str) -> None:
    if profile not in PROFILES:
        valid = ", ".join(sorted(PROFILES))
        raise LocalFalconApiPlanError(f"unknown profile '{profile}'. Valid profiles: {valid}")


def _required_string(payload: Mapping[str, Any], key: str, message: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LocalFalconApiPlanError(message)
    return value.strip()


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _source_id_from_label(value: str | None) -> str | None:
    normalized = _normalize_label(value)
    if normalized in {"google_maps", "maps"}:
        return "google_maps"
    if normalized in {"chatgpt", "openai_chatgpt"}:
        return "chatgpt"
    if normalized in {"google_ai_overview", "google_ai_overviews", "ai_overview", "ai_overviews"}:
        return "google_ai_overviews"
    return None


def _query_type_from_source(value: str | None) -> str | None:
    source_id = _source_id_from_label(value)
    if source_id == "google_maps":
        return "map_keyword"
    if source_id in {"chatgpt", "google_ai_overviews"}:
        return "ai_visibility_prompt"
    return None


def _scan_kind_from_source(value: str | None) -> str | None:
    source_id = _source_id_from_label(value)
    if source_id == "google_maps":
        return "map_visibility"
    if source_id in {"chatgpt", "google_ai_overviews"}:
        return "ai_visibility_map"
    return None


def _normalize_label(value: str | None) -> str:
    if not value:
        return ""
    import re

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _positive_int(value: int | None, default: int, name: str) -> int:
    if value is None:
        return default
    if value < 1:
        raise LocalFalconApiPlanError(f"{name} must be at least 1")
    return value


def _non_negative_int(value: int | None, default: int, name: str) -> int:
    if value is None:
        return default
    if value < 0:
        raise LocalFalconApiPlanError(f"{name} cannot be negative")
    return value


def _is_local_real_path(path: Path) -> bool:
    normalized = path.as_posix()
    return normalized.startswith("exports/local-real/")
