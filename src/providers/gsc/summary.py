from __future__ import annotations

import json
from collections import defaultdict
import shutil
from pathlib import Path
from typing import Any

from ...dashboard_lab.fixture_builder import PROVIDER_FILES, PROFILES


FORBIDDEN_OUTPUT_TERMS = {
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "credential",
    "credentials",
    "authorization",
    "private_key",
}

SYNTHETIC_DASHBOARD_LAB_ROOT = Path("exports") / "dashboard-lab"


class GscSummaryError(ValueError):
    pass


def build_gsc_summary(
    profile_slug: str,
    site_url: str,
    start_date: str,
    end_date: str,
    response_payload: dict[str, Any],
) -> dict[str, Any]:
    rows = response_payload.get("rows", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise GscSummaryError("GSC response rows must be a list")

    query_totals: dict[str, dict[str, float]] = defaultdict(_metric_bucket)
    page_totals: dict[str, dict[str, float]] = defaultdict(_metric_bucket)
    date_totals: dict[str, dict[str, float]] = defaultdict(_metric_bucket)
    query_page_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(_metric_bucket)
    warnings: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            warnings.append("Skipped a non-object GSC row.")
            continue
        keys = row.get("keys")
        if not isinstance(keys, list) or len(keys) < 3:
            warnings.append("Skipped a GSC row without query/page/date keys.")
            continue
        query = str(keys[0])
        page = str(keys[1])
        day = str(keys[2])
        clicks = _number(row.get("clicks"))
        impressions = _number(row.get("impressions"))
        ctr = _number(row.get("ctr"))
        position = _number(row.get("position"))
        for bucket in (
            query_totals[query],
            page_totals[_page_path(page)],
            date_totals[day],
            query_page_totals[(query, _page_path(page))],
        ):
            _add_metrics(bucket, clicks, impressions, ctr, position)

    summary = _finalize_bucket(_rollup(date_totals.values()))
    payload = {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": "gsc",
        "fixture_profile": profile_slug,
        "source_mode": "local_gsc_api",
        "local_only": True,
        "mock_data": False,
        "site_url": site_url,
        "reporting_period": {"start": start_date, "end": end_date},
        "summary_metrics": summary,
        "time_series": [
            {"date": day, **_finalize_bucket(bucket)}
            for day, bucket in sorted(date_totals.items())
        ],
        "top_queries": _top_items(query_totals, "query", 20),
        "top_pages": _top_items(page_totals, "path", 20),
        "top_query_pages": _top_query_pages(query_page_totals, 50),
        "query_movement": [],
        "insights": _insights(summary, query_totals, page_totals),
        "warnings": warnings,
    }
    validate_gsc_summary(payload)
    return payload


def build_combined_summary(profile_slug: str, source_mode: str = "local_gsc_api") -> dict[str, Any]:
    profile = _profile(profile_slug)
    return {
        "schema_version": "dashboard_lab_combined_summary.v1",
        "fixture_profile": profile.slug,
        "client_name": profile.client_name,
        "domain": profile.domain,
        "primary_market": profile.primary_market,
        "active_services": profile.active_services,
        "primary_service_priority": profile.primary_service_priority,
        "latest_report_date": profile.latest_report_date,
        "top_strategy_focus": profile.top_strategy_focus,
        "current_tasks": profile.current_tasks,
        "recent_insights": profile.recent_insights,
        "modules_enabled": profile.modules_enabled,
        "above_fold_module_order": profile.above_fold_module_order,
        "below_fold_module_order": profile.below_fold_module_order,
        "provider_summaries": {
            provider: PROVIDER_FILES[provider] for provider in profile.providers
        },
        "source_mode": source_mode,
        "local_only": True,
        "mock_data": False,
    }


def write_gsc_dashboard_outputs(output_dir: Path, gsc_summary: dict[str, Any]) -> list[Path]:
    profile_slug = str(gsc_summary.get("fixture_profile"))
    output_dir.mkdir(parents=True, exist_ok=True)
    support_files = ensure_dashboard_profile_files(output_dir, profile_slug)
    gsc_path = output_dir / PROVIDER_FILES["gsc"]
    combined_path = output_dir / "combined-dashboard-summary.json"
    combined_summary = build_combined_summary(profile_slug)
    validate_gsc_summary(gsc_summary)
    validate_aluma_combined_summary(combined_summary, profile_slug)
    _write_json(gsc_path, gsc_summary)
    _write_json(combined_path, combined_summary)
    return [*support_files, gsc_path, combined_path]


def validate_gsc_output_dir(output_dir: Path, profile_slug: str) -> list[Path]:
    support_files = _expected_support_files(profile_slug)
    missing_support = [filename for filename in support_files if not (output_dir / filename).exists()]
    if missing_support:
        raise GscSummaryError(
            f"missing dashboard-lab profile support files: {', '.join(missing_support)}"
        )
    gsc_path = output_dir / PROVIDER_FILES["gsc"]
    combined_path = output_dir / "combined-dashboard-summary.json"
    if not gsc_path.exists():
        raise GscSummaryError(f"missing {gsc_path.name}")
    if not combined_path.exists():
        raise GscSummaryError(f"missing {combined_path.name}")
    gsc_payload = _read_json(gsc_path)
    combined_payload = _read_json(combined_path)
    for filename in support_files:
        _reject_secret_like(_read_json(output_dir / filename), filename)
    validate_gsc_summary(gsc_payload)
    validate_aluma_combined_summary(combined_payload, profile_slug)
    return [*[output_dir / filename for filename in support_files], gsc_path, combined_path]


def ensure_dashboard_profile_files(
    output_dir: Path,
    profile_slug: str,
    synthetic_root: Path = SYNTHETIC_DASHBOARD_LAB_ROOT,
) -> list[Path]:
    _profile(profile_slug)
    copied = []
    source_dir = synthetic_root / profile_slug
    for filename in _expected_support_files(profile_slug):
        target = output_dir / filename
        if target.exists():
            continue
        source = source_dir / filename
        if not source.exists():
            raise GscSummaryError(
                f"missing source support file for real-output profile: {source}"
            )
        shutil.copyfile(source, target)
        copied.append(target)
    return copied


def validate_gsc_summary(payload: dict[str, Any]) -> None:
    _require_fields(
        payload,
        "gsc-summary.json",
        [
            "schema_version",
            "provider",
            "fixture_profile",
            "source_mode",
            "local_only",
            "mock_data",
            "reporting_period",
            "summary_metrics",
            "time_series",
            "top_queries",
            "top_pages",
            "warnings",
        ],
    )
    if payload.get("schema_version") != "dashboard_lab_provider_summary.v1":
        raise GscSummaryError("gsc-summary.json has unexpected schema_version")
    if payload.get("provider") != "gsc":
        raise GscSummaryError("gsc-summary.json provider must be gsc")
    if payload.get("local_only") is not True:
        raise GscSummaryError("gsc-summary.json must be marked local_only")
    metrics = payload.get("summary_metrics")
    if not isinstance(metrics, dict):
        raise GscSummaryError("gsc-summary.json summary_metrics must be an object")
    for field in ["clicks", "impressions", "ctr", "average_position"]:
        if field not in metrics:
            raise GscSummaryError(f"gsc-summary.json summary_metrics missing {field}")
    _reject_secret_like(payload, "gsc-summary.json")


def validate_aluma_combined_summary(payload: dict[str, Any], profile_slug: str) -> None:
    _profile(profile_slug)
    _require_fields(
        payload,
        "combined-dashboard-summary.json",
        ["fixture_profile", "provider_summaries", "modules_enabled", "local_only"],
    )
    if payload.get("fixture_profile") != profile_slug:
        raise GscSummaryError("combined-dashboard-summary.json fixture_profile mismatch")
    summaries = payload.get("provider_summaries")
    if profile_slug == "aluma-seo-geo":
        if summaries != {"ga4": "ga4-summary.json", "gsc": "gsc-summary.json"}:
            raise GscSummaryError("Aluma combined summary must reference only GA4 and GSC")
        modules = payload.get("modules_enabled")
        if not isinstance(modules, list):
            raise GscSummaryError("combined-dashboard-summary.json modules_enabled must be a list")
        forbidden = {"paid_search", "lsa_performance", "call_tracking"}
        if forbidden.intersection(modules):
            raise GscSummaryError("Aluma combined summary must not enable Ads, LSA, or CallRail")
    _reject_secret_like(payload, "combined-dashboard-summary.json")


def real_output_dir(profile_slug: str) -> Path:
    _profile(profile_slug)
    return Path("exports") / "local-real" / "dashboard-lab" / profile_slug


def _expected_support_files(profile_slug: str) -> list[str]:
    profile = _profile(profile_slug)
    return [
        "client-profile.json",
        *[
            PROVIDER_FILES[provider]
            for provider in profile.providers
            if provider != "gsc"
        ],
    ]


def _metric_bucket() -> dict[str, float]:
    return {
        "clicks": 0.0,
        "impressions": 0.0,
        "weighted_ctr": 0.0,
        "weighted_position": 0.0,
    }


def _add_metrics(bucket: dict[str, float], clicks: float, impressions: float, ctr: float, position: float) -> None:
    bucket["clicks"] += clicks
    bucket["impressions"] += impressions
    bucket["weighted_ctr"] += ctr * impressions
    bucket["weighted_position"] += position * impressions


def _rollup(buckets: Any) -> dict[str, float]:
    total = _metric_bucket()
    for bucket in buckets:
        total["clicks"] += bucket.get("clicks", 0.0)
        total["impressions"] += bucket.get("impressions", 0.0)
        total["weighted_ctr"] += bucket.get("weighted_ctr", 0.0)
        total["weighted_position"] += bucket.get("weighted_position", 0.0)
    return total


def _finalize_bucket(bucket: dict[str, float]) -> dict[str, int | float]:
    impressions = bucket.get("impressions", 0.0)
    clicks = bucket.get("clicks", 0.0)
    return {
        "clicks": int(round(clicks)),
        "impressions": int(round(impressions)),
        "ctr": round(bucket.get("weighted_ctr", 0.0) / impressions, 4) if impressions else 0.0,
        "average_position": round(bucket.get("weighted_position", 0.0) / impressions, 2) if impressions else 0.0,
    }


def _top_items(totals: dict[str, dict[str, float]], label: str, limit: int) -> list[dict[str, Any]]:
    rows = []
    for value, bucket in totals.items():
        rows.append({label: value, **_finalize_bucket(bucket)})
    return sorted(rows, key=lambda item: (-int(item["clicks"]), -int(item["impressions"]), str(item[label])))[:limit]


def _top_query_pages(totals: dict[tuple[str, str], dict[str, float]], limit: int) -> list[dict[str, Any]]:
    rows = []
    for (query, path), bucket in totals.items():
        rows.append({"query": query, "path": path, **_finalize_bucket(bucket)})
    return sorted(rows, key=lambda item: (-int(item["clicks"]), -int(item["impressions"]), item["query"], item["path"]))[:limit]


def _insights(
    summary: dict[str, int | float],
    query_totals: dict[str, dict[str, float]],
    page_totals: dict[str, dict[str, float]],
) -> list[str]:
    insights = []
    top_query = _top_items(query_totals, "query", 1)
    top_page = _top_items(page_totals, "path", 1)
    if top_query:
        insights.append(f"Top organic query by clicks: {top_query[0]['query']}.")
    if top_page:
        insights.append(f"Top organic landing page by clicks: {top_page[0]['path']}.")
    insights.append(
        f"Search Console export contains {summary['clicks']} clicks and {summary['impressions']} impressions."
    )
    return insights


def _page_path(page: str) -> str:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(page)
        if parsed.path:
            return parsed.path
    except ValueError:
        pass
    return page


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _profile(profile_slug: str):
    try:
        return PROFILES[profile_slug]
    except KeyError as exc:
        valid = ", ".join(sorted(PROFILES))
        raise GscSummaryError(f"unknown profile '{profile_slug}'. Valid profiles: {valid}") from exc


def _require_fields(payload: dict[str, Any], filename: str, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise GscSummaryError(f"{filename} missing required fields: {', '.join(missing)}")


def _reject_secret_like(value: Any, filename: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
            if any(term in normalized_key for term in FORBIDDEN_OUTPUT_TERMS):
                raise GscSummaryError(f"{filename} contains forbidden secret-like key: {key}")
            _reject_secret_like(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_like(item, filename)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(
            term in lowered
            for term in ["access_token", "refresh_token", "client_secret", "authorization", "token"]
        ):
            raise GscSummaryError(f"{filename} contains forbidden secret-like text")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GscSummaryError(f"{path.name} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise GscSummaryError(f"{path.name} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
