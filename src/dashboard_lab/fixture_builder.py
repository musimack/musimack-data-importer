from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


EXPECTED_FILES = [
    "client-profile.json",
    "ga4-summary.json",
    "gsc-summary.json",
    "google-ads-search-summary.json",
    "google-ads-lsa-summary.json",
    "local-falcon-summary.json",
    "callrail-summary.json",
    "combined-dashboard-summary.json",
]

PROVIDER_FILES = {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "google_ads_search": "google-ads-search-summary.json",
    "google_ads_lsa": "google-ads-lsa-summary.json",
    "local_falcon": "local-falcon-summary.json",
    "callrail": "callrail-summary.json",
}

FORBIDDEN_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "client_secret",
    "password",
    "authorization",
    "private_key",
}

FORBIDDEN_CALLRAIL_KEYS = {
    "recording",
    "recordings",
    "recording_url",
    "recording_urls",
    "transcript",
    "transcripts",
    "transcript_text",
    "raw_transcript",
}

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)


class FixtureValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureWriteResult:
    output_dir: Path
    files: list[Path]


def build_all_services_fixture(output_dir: Path) -> FixtureWriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = all_services_payloads()
    written = []
    for filename, payload in payloads.items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    validate_dashboard_lab_fixture(output_dir)
    return FixtureWriteResult(output_dir=output_dir, files=written)


def all_services_payloads() -> dict[str, dict[str, Any]]:
    period = {"start": "2026-04-01", "end": "2026-04-30"}
    services = [
        "SEO/GEO",
        "Google Ads Search",
        "Google Ads LSA",
        "Local SEO / Maps",
        "Call Tracking",
        "Website Maintenance",
        "Hosting",
    ]
    return {
        "client-profile.json": _client_profile(period, services),
        "ga4-summary.json": _ga4_summary(period),
        "gsc-summary.json": _gsc_summary(period),
        "google-ads-search-summary.json": _google_ads_search_summary(period),
        "google-ads-lsa-summary.json": _google_ads_lsa_summary(period),
        "local-falcon-summary.json": _local_falcon_summary(),
        "callrail-summary.json": _callrail_summary(period),
        "combined-dashboard-summary.json": _combined_dashboard_summary(period, services),
    }


def validate_dashboard_lab_fixture(output_dir: Path) -> list[Path]:
    missing = [name for name in EXPECTED_FILES if not (output_dir / name).exists()]
    if missing:
        raise FixtureValidationError(f"missing expected fixture files: {', '.join(missing)}")

    payloads = {}
    for filename in EXPECTED_FILES:
        path = output_dir / filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FixtureValidationError(f"{filename} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise FixtureValidationError(f"{filename} must contain a JSON object")
        _reject_secret_like_keys(payload, filename)
        payloads[filename] = payload

    _validate_client_profile(payloads["client-profile.json"])
    for provider, filename in PROVIDER_FILES.items():
        _validate_provider_summary(payloads[filename], provider, filename)
    _validate_callrail_privacy(payloads["callrail-summary.json"])
    _validate_combined_summary(payloads["combined-dashboard-summary.json"])
    return [output_dir / name for name in EXPECTED_FILES]


def _client_profile(period: dict[str, str], services: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "dashboard_lab_client_profile.v1",
        "client_key": "all_services_client",
        "client_name": "Riverside Home Services Demo",
        "domain": "riversidehomeservices.example",
        "primary_market": "Portland Metro",
        "source_mode": "synthetic_mock",
        "local_only": True,
        "mock_data": True,
        "active_services": services,
        "reporting_period": period,
        "fixture_notes": [
            "Synthetic local fixture for dashboard prototyping.",
            "No live provider connections, credentials, or portal database writes.",
        ],
    }


def _provider_base(provider: str, period: dict[str, str] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": provider,
        "source_mode": "synthetic_mock",
        "local_only": True,
        "mock_data": True,
    }
    if period:
        payload["reporting_period"] = period
    return payload


def _ga4_summary(period: dict[str, str]) -> dict[str, Any]:
    payload = _provider_base("ga4", period)
    payload.update(
        {
            "summary_metrics": {
                "users": 8420,
                "sessions": 11385,
                "views": 28640,
                "engagement_rate": 0.684,
                "average_session_duration_seconds": 138,
                "event_count": 74520,
                "conversions": 312,
            },
            "time_series": _daily_series(
                period,
                {"users": 250, "sessions": 330, "views": 840, "conversions": 8},
                {"users": 64, "sessions": 83, "views": 210, "conversions": 6},
            ),
            "traffic_channels": [
                {"channel": "Organic Search", "sessions": 4210, "users": 3290, "views": 11320, "conversions": 142},
                {"channel": "Paid Search", "sessions": 2985, "users": 2310, "views": 7610, "conversions": 96},
                {"channel": "Direct", "sessions": 1640, "users": 1304, "views": 3840, "conversions": 28},
                {"channel": "Referral", "sessions": 1015, "users": 870, "views": 2510, "conversions": 22},
                {"channel": "Organic Social", "sessions": 760, "users": 646, "views": 1785, "conversions": 14},
            ],
            "top_pages": [
                {"path": "/", "title": "Home", "views": 6920, "users": 2840, "conversions": 62},
                {"path": "/services/hvac-repair", "title": "HVAC Repair", "views": 4310, "users": 1610, "conversions": 74},
                {"path": "/services/plumbing", "title": "Plumbing Services", "views": 3860, "users": 1475, "conversions": 68},
                {"path": "/service-area/portland", "title": "Portland Service Area", "views": 2510, "users": 980, "conversions": 31},
                {"path": "/contact", "title": "Request Service", "views": 2280, "users": 1160, "conversions": 77},
            ],
            "insights": [
                "Organic Search generated the largest session volume and the strongest assisted service-request activity.",
                "HVAC and plumbing landing pages are carrying most high-intent website engagement.",
            ],
            "warnings": [],
        }
    )
    return payload


def _gsc_summary(period: dict[str, str]) -> dict[str, Any]:
    payload = _provider_base("gsc", period)
    payload.update(
        {
            "summary_metrics": {
                "clicks": 4980,
                "impressions": 148500,
                "ctr": 0.0335,
                "average_position": 9.8,
            },
            "time_series": _daily_series(
                period,
                {"clicks": 142, "impressions": 4300},
                {"clicks": 48, "impressions": 1180},
            ),
            "top_queries": [
                {"query": "hvac repair portland", "clicks": 620, "impressions": 11800, "position": 4.8},
                {"query": "emergency plumber near me", "clicks": 545, "impressions": 13640, "position": 6.1},
                {"query": "furnace repair portland", "clicks": 488, "impressions": 9200, "position": 5.3},
                {"query": "water heater replacement", "clicks": 315, "impressions": 8700, "position": 8.9},
            ],
            "top_pages": [
                {"path": "/services/hvac-repair", "clicks": 1120, "impressions": 26800, "ctr": 0.0418},
                {"path": "/services/plumbing", "clicks": 980, "impressions": 30100, "ctr": 0.0326},
                {"path": "/service-area/portland", "clicks": 625, "impressions": 18400, "ctr": 0.034},
            ],
            "query_movement": [
                {"query": "hvac repair portland", "previous_position": 6.7, "current_position": 4.8, "change": -1.9},
                {"query": "water heater replacement", "previous_position": 11.4, "current_position": 8.9, "change": -2.5},
                {"query": "drain cleaning portland", "previous_position": 9.2, "current_position": 10.1, "change": 0.9},
            ],
            "insights": [
                "High-intent HVAC terms improved into the top five average positions.",
                "Plumbing pages have large impression volume and should be tested for stronger calls to action.",
            ],
            "warnings": [],
        }
    )
    return payload


def _google_ads_search_summary(period: dict[str, str]) -> dict[str, Any]:
    payload = _provider_base("google_ads_search", period)
    spend = 18420.75
    conversions = 286
    clicks = 3925
    impressions = 82600
    payload.update(
        {
            "summary_metrics": {
                "spend": spend,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": round(clicks / impressions, 4),
                "conversions": conversions,
                "conversion_rate": round(conversions / clicks, 4),
                "cost_per_conversion": round(spend / conversions, 2),
            },
            "time_series": _daily_series(
                period,
                {"spend": 520, "clicks": 112, "impressions": 2420, "conversions": 7},
                {"spend": 180, "clicks": 42, "impressions": 780, "conversions": 5},
            ),
            "campaigns": [
                {"name": "Search | HVAC Emergency", "spend": 6820.4, "clicks": 1290, "conversions": 104},
                {"name": "Search | Plumbing Core", "spend": 5940.2, "clicks": 1185, "conversions": 88},
                {"name": "Search | Water Heater", "spend": 3160.9, "clicks": 715, "conversions": 54},
                {"name": "Search | Brand", "spend": 910.25, "clicks": 420, "conversions": 28},
            ],
            "ad_groups": [
                {"name": "Emergency HVAC Repair", "campaign": "Search | HVAC Emergency", "spend": 3910.8, "conversions": 66},
                {"name": "Furnace Repair", "campaign": "Search | HVAC Emergency", "spend": 2075.4, "conversions": 28},
                {"name": "Emergency Plumbing", "campaign": "Search | Plumbing Core", "spend": 2860.1, "conversions": 43},
                {"name": "Drain Cleaning", "campaign": "Search | Plumbing Core", "spend": 1885.3, "conversions": 31},
            ],
            "safe_keyword_preview": [
                {"term": "emergency hvac repair", "clicks": 245, "conversions": 28},
                {"term": "plumber near me", "clicks": 218, "conversions": 22},
                {"term": "furnace repair portland", "clicks": 176, "conversions": 17},
                {"term": "water heater install", "clicks": 149, "conversions": 13},
            ],
            "insights": [
                "Emergency HVAC search is the strongest paid conversion driver.",
                "Brand spend is efficient but low volume; keep it protected while expanding core service campaigns.",
            ],
            "warnings": [],
        }
    )
    return payload


def _google_ads_lsa_summary(period: dict[str, str]) -> dict[str, Any]:
    payload = _provider_base("google_ads_lsa", period)
    spend = 7825.5
    leads = 132
    payload.update(
        {
            "summary_metrics": {
                "spend": spend,
                "leads": leads,
                "booked_leads": 74,
                "cost_per_lead": round(spend / leads, 2),
                "calls": 108,
                "messages": 24,
                "disputed_leads": 7,
                "charged_leads": 125,
            },
            "time_series": _daily_series(
                period,
                {"spend": 220, "leads": 3, "calls": 3, "messages": 1},
                {"spend": 90, "leads": 3, "calls": 2, "messages": 1},
            ),
            "lead_categories": [
                {"category": "HVAC Repair", "leads": 52, "booked_leads": 31, "cost_per_lead": 55.4},
                {"category": "Plumbing", "leads": 44, "booked_leads": 24, "cost_per_lead": 61.2},
                {"category": "Water Heater", "leads": 21, "booked_leads": 12, "cost_per_lead": 58.9},
                {"category": "Other Home Services", "leads": 15, "booked_leads": 7, "cost_per_lead": 66.8},
            ],
            "insights": [
                "Booked lead rate is strongest for HVAC repair.",
                "Dispute review should focus on out-of-area and wrong-service leads.",
            ],
            "warnings": [],
        }
    )
    return payload


def _local_falcon_summary() -> dict[str, Any]:
    payload = _provider_base("local_falcon")
    payload.update(
        {
            "scan_date": "2026-04-28",
            "location_metadata": {
                "business_name": "Riverside Home Services Demo",
                "primary_market": "Portland Metro",
                "center_point_label": "Portland, OR",
            },
            "grid_metadata": {
                "grid_size": "7x7",
                "radius_miles": 8,
                "keywords_tracked": ["hvac repair", "plumber", "water heater repair"],
            },
            "summary_metrics": {
                "average_rank": 5.7,
                "visibility_score": 71,
                "top_3_grid_share": 0.38,
                "top_10_grid_share": 0.86,
            },
            "top_ranking_areas": [
                {"area": "North Portland", "average_rank": 2.4},
                {"area": "Pearl District", "average_rank": 3.1},
                {"area": "Sellwood", "average_rank": 3.6},
            ],
            "weak_ranking_areas": [
                {"area": "Beaverton", "average_rank": 11.2},
                {"area": "Gresham", "average_rank": 10.7},
                {"area": "Lake Oswego", "average_rank": 9.8},
            ],
            "keyword_location_scans": [
                {"keyword": "hvac repair", "average_rank": 4.6, "visibility_score": 78},
                {"keyword": "plumber", "average_rank": 6.1, "visibility_score": 69},
                {"keyword": "water heater repair", "average_rank": 6.5, "visibility_score": 66},
            ],
            "scan_history": [
                {"scan_date": "2026-02-28", "average_rank": 7.8, "visibility_score": 62},
                {"scan_date": "2026-03-28", "average_rank": 6.4, "visibility_score": 68},
                {"scan_date": "2026-04-28", "average_rank": 5.7, "visibility_score": 71},
            ],
            "insights": [
                "Map visibility improved for HVAC and plumbing keywords month over month.",
                "Outer west-side ranking gaps should guide location page and review-generation priorities.",
            ],
            "warnings": [],
        }
    )
    return payload


def _callrail_summary(period: dict[str, str]) -> dict[str, Any]:
    payload = _provider_base("callrail", period)
    payload.update(
        {
            "summary_metrics": {
                "calls": 486,
                "first_time_callers": 312,
                "answered_calls": 421,
                "missed_calls": 65,
                "average_call_duration_seconds": 214,
                "qualified_leads": 148,
            },
            "time_series": _daily_series(
                period,
                {"calls": 13, "answered_calls": 11, "missed_calls": 2, "qualified_leads": 4},
                {"calls": 6, "answered_calls": 5, "missed_calls": 2, "qualified_leads": 3},
            ),
            "source_breakdown": [
                {"source": "Google Ads Search", "calls": 168, "qualified_leads": 62},
                {"source": "Organic Search", "calls": 142, "qualified_leads": 44},
                {"source": "Google Ads LSA", "calls": 108, "qualified_leads": 31},
                {"source": "Direct", "calls": 46, "qualified_leads": 8},
                {"source": "Referral", "calls": 22, "qualified_leads": 3},
            ],
            "safe_call_examples": [
                {"caller_label": "Caller 001", "source": "Google Ads Search", "duration_seconds": 332, "status": "answered", "qualified": True},
                {"caller_label": "Caller 002", "source": "Organic Search", "duration_seconds": 184, "status": "answered", "qualified": True},
                {"caller_label": "Caller 003", "source": "Google Ads LSA", "duration_seconds": 48, "status": "missed", "qualified": False},
                {"caller_label": "Caller 004", "source": "Direct", "duration_seconds": 276, "status": "answered", "qualified": True},
            ],
            "insights": [
                "Paid Search produced the most qualified tracked calls.",
                "Missed call follow-up is the clearest near-term conversion recovery opportunity.",
            ],
            "warnings": [
                "Caller labels are synthetic and do not represent real people or phone numbers."
            ],
        }
    )
    return payload


def _combined_dashboard_summary(period: dict[str, str], services: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "dashboard_lab_combined_summary.v1",
        "client_name": "Riverside Home Services Demo",
        "domain": "riversidehomeservices.example",
        "primary_market": "Portland Metro",
        "active_services": services,
        "primary_service_priority": "SEO/GEO",
        "latest_report_date": period["end"],
        "top_strategy_focus": [
            "Grow high-intent HVAC and plumbing organic visibility.",
            "Improve paid lead quality and missed-call recovery.",
            "Close Local Falcon ranking gaps in west-side service areas.",
        ],
        "current_tasks": [
            {"title": "Refresh HVAC repair landing page calls to action", "service": "SEO/GEO", "status": "in_progress"},
            {"title": "Review LSA disputed lead categories", "service": "Google Ads LSA", "status": "planned"},
            {"title": "Add Beaverton and Gresham local proof sections", "service": "Local SEO / Maps", "status": "planned"},
            {"title": "Audit missed-call follow-up workflow", "service": "Call Tracking", "status": "in_progress"},
        ],
        "recent_insights": [
            "Organic Search and Paid Search are both producing strong service-request intent.",
            "HVAC repair has the best cross-channel momentum.",
            "Missed calls represent a measurable conversion recovery opportunity.",
        ],
        "modules_enabled": [
            "executive_summary",
            "website_performance",
            "search_console",
            "paid_search",
            "lsa_performance",
            "local_map_rankings",
            "call_tracking",
            "tasks",
            "insights",
        ],
        "above_fold_module_order": [
            "executive_summary",
            "website_performance",
            "paid_search",
            "call_tracking",
        ],
        "below_fold_module_order": [
            "search_console",
            "lsa_performance",
            "local_map_rankings",
            "tasks",
            "insights",
        ],
        "provider_summaries": PROVIDER_FILES,
        "source_mode": "synthetic_mock",
        "local_only": True,
        "mock_data": True,
    }


def _daily_series(
    period: dict[str, str],
    base: dict[str, int | float],
    variance: dict[str, int | float],
) -> list[dict[str, Any]]:
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    rows = []
    current = start
    index = 0
    while current <= end:
        row: dict[str, Any] = {"date": current.isoformat()}
        for key, value in base.items():
            spread = variance.get(key, 0)
            modifier = ((index * 7) % 11) - 5
            computed = float(value) + (float(spread) * modifier / 10)
            row[key] = round(computed, 2) if isinstance(value, float) else max(0, int(round(computed)))
        rows.append(row)
        current += timedelta(days=1)
        index += 1
    return rows


def _validate_client_profile(payload: dict[str, Any]) -> None:
    _require_fields(
        payload,
        "client-profile.json",
        ["schema_version", "client_name", "domain", "active_services", "reporting_period", "local_only"],
    )
    if payload.get("schema_version") != "dashboard_lab_client_profile.v1":
        raise FixtureValidationError("client-profile.json has unexpected schema_version")
    if payload.get("local_only") is not True or payload.get("mock_data") is not True:
        raise FixtureValidationError("client-profile.json must be marked local_only and mock_data")


def _validate_provider_summary(payload: dict[str, Any], provider: str, filename: str) -> None:
    _require_fields(
        payload,
        filename,
        ["schema_version", "provider", "summary_metrics", "source_mode", "local_only", "mock_data"],
    )
    if payload.get("schema_version") != "dashboard_lab_provider_summary.v1":
        raise FixtureValidationError(f"{filename} has unexpected schema_version")
    if payload.get("provider") != provider:
        raise FixtureValidationError(f"{filename} provider must be {provider}")
    if payload.get("local_only") is not True or payload.get("mock_data") is not True:
        raise FixtureValidationError(f"{filename} must be marked local_only and mock_data")


def _validate_combined_summary(payload: dict[str, Any]) -> None:
    _require_fields(
        payload,
        "combined-dashboard-summary.json",
        [
            "schema_version",
            "client_name",
            "domain",
            "active_services",
            "modules_enabled",
            "above_fold_module_order",
            "below_fold_module_order",
            "provider_summaries",
        ],
    )
    summaries = payload.get("provider_summaries")
    if summaries != PROVIDER_FILES:
        raise FixtureValidationError("combined-dashboard-summary.json must reference all provider summary files")


def _validate_callrail_privacy(payload: dict[str, Any]) -> None:
    _reject_callrail_keys(payload)
    serialized = json.dumps(payload, sort_keys=True)
    if PHONE_PATTERN.search(serialized):
        raise FixtureValidationError("callrail-summary.json contains a real-looking phone number")


def _require_fields(payload: dict[str, Any], filename: str, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise FixtureValidationError(f"{filename} missing required fields: {', '.join(missing)}")


def _reject_secret_like_keys(value: Any, filename: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
            if normalized_key in FORBIDDEN_SECRET_KEYS:
                raise FixtureValidationError(f"{filename} contains forbidden secret-like key: {key}")
            _reject_secret_like_keys(nested, filename)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_like_keys(item, filename)


def _reject_callrail_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).lower().replace("-", "_").replace(" ", "_")
            if normalized_key in FORBIDDEN_CALLRAIL_KEYS:
                raise FixtureValidationError(f"callrail-summary.json contains forbidden call data key: {key}")
            _reject_callrail_keys(nested)
    elif isinstance(value, list):
        for item in value:
            _reject_callrail_keys(item)
