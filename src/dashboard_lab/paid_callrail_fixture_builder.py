from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paid_callrail_validators import (
    validate_callrail_summary,
    validate_google_ads_summary,
)


DEFAULT_PROFILE = "inn-at-spanish-head"
DEFAULT_CLIENT_LABEL = "Spanish Head"
DEFAULT_OUTPUT_ROOT = Path("exports") / "dashboard-lab"
DEFAULT_GENERATED_AT = "2026-06-10T00:00:00Z"
DEFAULT_START_DATE = "2026-01-01"
DEFAULT_END_DATE = "2026-05-31"


class PaidSearchCallRailFixtureBuildError(ValueError):
    pass


@dataclass(frozen=True)
class PaidSearchCallRailFixtureBuildResult:
    profile: str
    output_dir: Path
    google_ads_path: Path
    callrail_path: Path

    @property
    def files(self) -> list[Path]:
        return [self.google_ads_path, self.callrail_path]


def build_paid_search_callrail_fixtures(
    *,
    profile: str = DEFAULT_PROFILE,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> PaidSearchCallRailFixtureBuildResult:
    if profile != DEFAULT_PROFILE:
        raise PaidSearchCallRailFixtureBuildError(
            "paid search and CallRail synthetic fixtures currently support inn-at-spanish-head only"
        )
    output_dir = Path(output_root) / profile
    google_ads_payload = build_google_ads_summary(profile=profile, start_date=start_date, end_date=end_date)
    callrail_payload = build_callrail_summary(profile=profile, start_date=start_date, end_date=end_date)
    validate_google_ads_summary(google_ads_payload)
    validate_callrail_summary(callrail_payload)

    google_ads_path = output_dir / "google-ads-summary.json"
    callrail_path = output_dir / "callrail-summary.json"
    _write_json(google_ads_path, google_ads_payload)
    _write_json(callrail_path, callrail_payload)
    validate_google_ads_summary(json.loads(google_ads_path.read_text(encoding="utf-8")))
    validate_callrail_summary(json.loads(callrail_path.read_text(encoding="utf-8")))
    return PaidSearchCallRailFixtureBuildResult(
        profile=profile,
        output_dir=output_dir,
        google_ads_path=google_ads_path,
        callrail_path=callrail_path,
    )


def build_google_ads_summary(
    *,
    profile: str = DEFAULT_PROFILE,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> dict[str, Any]:
    keyword_rows = [
        _ads_keyword("lincoln city hotel", "Spanish Head | Oceanfront Hotel", "phrase", 12500, 540, 3.15, 0.112, 62, "/lp-main/"),
        _ads_keyword("oceanfront hotel lincoln city", "Spanish Head | Oceanfront Hotel", "exact", 9800, 488, 3.42, 0.126, 68, "/lp-oceanfront/"),
        _ads_keyword("lincoln city ocean view rooms", "Spanish Head | Rooms & Suites", "phrase", 6400, 252, 2.95, 0.095, 31, "/lp-accommodations/"),
        _ads_keyword("lincoln city beachfront lodging", "Spanish Head | Oceanfront Hotel", "phrase", 5900, 218, 3.08, 0.087, 25, "/lp-oceanfront/"),
        _ads_keyword("oregon coast hotel", "Spanish Head | Oceanfront Hotel", "broad", 18200, 610, 2.74, 0.071, 44, "/lp-main/"),
        _ads_keyword("hotel with restaurant lincoln city", "Spanish Head | Dining & Fathoms", "phrase", 3200, 128, 2.58, 0.062, 16, "/lp-amenities/"),
        _ads_keyword("lincoln city hotel deals", "Spanish Head | Deals & Packages", "phrase", 7200, 360, 2.88, 0.082, 42, "/lp-deals/"),
        _ads_keyword("romantic hotel lincoln city", "Spanish Head | Deals & Packages", "phrase", 4100, 184, 3.36, 0.071, 19, "/lp-romantic/"),
        _ads_keyword("lincoln city hotel with pool", "Spanish Head | Rooms & Suites", "phrase", 2800, 96, 2.44, 0.044, 11, "/lp-amenities/"),
        _ads_keyword("oceanfront suites lincoln city", "Spanish Head | Rooms & Suites", "exact", 3600, 172, 3.18, 0.093, 23, "/lp-accommodations/"),
    ]
    search_term_rows = [
        _search_term("best lincoln city hotel oceanfront", "oceanfront hotel lincoln city", "Spanish Head | Oceanfront Hotel", 1800, 106, 3.44, 0.132, 17),
        _search_term("lincoln city hotel rooms with ocean view", "lincoln city ocean view rooms", "Spanish Head | Rooms & Suites", 1320, 64, 3.02, 0.094, 8),
        _search_term("oregon coast hotel on beach", "oregon coast hotel", "Spanish Head | Oceanfront Hotel", 2400, 88, 2.82, 0.067, 7),
        _search_term("lincoln city hotel packages", "lincoln city hotel deals", "Spanish Head | Deals & Packages", 1180, 72, 2.76, 0.089, 10),
        _search_term("hotel near fathoms restaurant", "hotel with restaurant lincoln city", "Spanish Head | Dining & Fathoms", 620, 31, 2.48, 0.052, 4),
        _search_term("romantic oceanfront hotel lincoln city", "romantic hotel lincoln city", "Spanish Head | Deals & Packages", 840, 45, 3.58, 0.082, 5),
        _search_term("lincoln city beachfront lodging deals", "lincoln city beachfront lodging", "Spanish Head | Oceanfront Hotel", 980, 42, 3.12, 0.071, 6),
        _search_term("oceanfront suites oregon coast", "oceanfront suites lincoln city", "Spanish Head | Rooms & Suites", 720, 34, 3.24, 0.077, 4),
        _search_term("lincoln city lodging with pool", "lincoln city hotel with pool", "Spanish Head | Rooms & Suites", 560, 18, 2.51, 0.036, 2),
        _search_term("book lincoln city oceanfront hotel", "lincoln city hotel", "Spanish Head | Brand", 1050, 92, 2.66, 0.151, 15),
    ]
    campaign_rows = [
        _ads_campaign("Spanish Head | Brand", 620.0, 6100, 410, 0.0672, 1.51, 59.0, 42),
        _ads_campaign("Spanish Head | Oceanfront Hotel", 4750.25, 46400, 1856, 0.04, 2.56, 220.0, 199),
        _ads_campaign("Spanish Head | Rooms & Suites", 2107.68, 12800, 520, 0.0406, 4.05, 65.0, 65),
        _ads_campaign("Spanish Head | Deals & Packages", 1655.04, 11300, 544, 0.0481, 3.04, 72.0, 61),
        _ads_campaign("Spanish Head | Dining & Fathoms", 330.24, 3200, 128, 0.04, 2.58, 8.0, 16),
    ]
    landing_page_rows = [
        _landing_page("/lp-main/", "Spanish Head | Oceanfront Hotel", 30700, 1150, 0.0375, 2395.0, 106.0, 106),
        _landing_page("/lp-booking/", "Spanish Head | Brand", 6100, 410, 0.0672, 620.0, 59.0, 42),
        _landing_page("/lp-deals/", "Spanish Head | Deals & Packages", 7200, 360, 0.05, 1036.8, 42.0, 42),
        _landing_page("/lp-accommodations/", "Spanish Head | Rooms & Suites", 10000, 424, 0.0424, 1289.4, 54.0, 54),
        _landing_page("/lp-oceanfront/", "Spanish Head | Oceanfront Hotel", 15700, 706, 0.045, 2274.93, 87.0, 86),
        _landing_page("/lp-amenities/", "Spanish Head | Dining & Fathoms", 6000, 224, 0.0373, 564.48, 27.0, 27),
        _landing_page("/lp-romantic/", "Spanish Head | Deals & Packages", 4100, 184, 0.0449, 618.24, 19.0, 19),
    ]
    time_series = [
        {"date": "2026-01-31", "spend": 1432.18, "clicks": 512, "impressions": 12400, "conversions": 58.0, "calls": 49},
        {"date": "2026-02-28", "spend": 1668.75, "clicks": 604, "impressions": 14800, "conversions": 69.0, "calls": 58},
        {"date": "2026-03-31", "spend": 1915.42, "clicks": 698, "impressions": 16900, "conversions": 83.0, "calls": 73},
        {"date": "2026-04-30", "spend": 2228.36, "clicks": 790, "impressions": 18500, "conversions": 98.0, "calls": 87},
        {"date": "2026-05-31", "spend": 2218.5, "clicks": 854, "impressions": 21200, "conversions": 117.0, "calls": 116},
    ]
    summary = _ads_summary(keyword_rows)
    return {
        "schema_version": "google_ads_summary.v1",
        "provider": "google_ads",
        "profile": profile,
        "client_label": DEFAULT_CLIENT_LABEL,
        "source": "synthetic_fixture",
        "is_real_data": False,
        "generated_at": DEFAULT_GENERATED_AT,
        "date_range": {"start_date": start_date, "end_date": end_date},
        "currency": "USD",
        "summary": summary,
        "keyword_rows": keyword_rows,
        "search_term_rows": search_term_rows,
        "campaign_rows": campaign_rows,
        "landing_page_rows": landing_page_rows,
        "paid_search_call_signal": {
            "google_ads_calls": summary["calls"],
            "calls_with_keyword_attribution": 344,
            "top_call_keyword": "oceanfront hotel lincoln city",
            "top_call_campaign": "Spanish Head | Oceanfront Hotel",
            "missed_paid_search_calls": 39,
            "cost_per_call": summary["cost_per_call"],
            "attribution_notes": "Synthetic aggregate call signal for dashboard-lab UI testing only.",
        },
        "budget_pacing": {
            "spend": summary["spend"],
            "budget": 10000.0,
            "percent_used": round(summary["spend"] / 10000.0, 4),
            "days_elapsed": 151,
            "days_remaining": 0,
            "pacing_status": "synthetic_on_track",
            "notes": "Synthetic budget pacing, not actual Spanish Head spend.",
        },
        "time_series": time_series,
        "data_quality_notes": [
            "Synthetic fixture data for dashboard-lab UI testing only.",
            "No real Spanish Head Google Ads data, exports, credentials, or API pulls are included.",
            "Canonical numeric values are stored as numbers; dashboard-lab is responsible for display formatting.",
        ],
    }


def build_callrail_summary(
    *,
    profile: str = DEFAULT_PROFILE,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> dict[str, Any]:
    keyword_rows = [
        _call_keyword("lincoln city hotel", "Spanish Head | Oceanfront Hotel", 62, 44, 55, 7, 214, 42, "/lp-main/", 1701.0),
        _call_keyword("oceanfront hotel lincoln city", "Spanish Head | Oceanfront Hotel", 68, 49, 61, 7, 232, 48, "/lp-oceanfront/", 1668.96),
        _call_keyword("lincoln city ocean view rooms", "Spanish Head | Rooms & Suites", 31, 22, 27, 4, 198, 19, "/lp-accommodations/", 743.4),
        _call_keyword("lincoln city beachfront lodging", "Spanish Head | Oceanfront Hotel", 25, 18, 21, 4, 187, 15, "/lp-oceanfront/", 671.44),
        _call_keyword("oregon coast hotel", "Spanish Head | Oceanfront Hotel", 44, 29, 36, 8, 176, 22, "/lp-main/", 1671.4),
        _call_keyword("hotel with restaurant lincoln city", "Spanish Head | Dining & Fathoms", 16, 11, 13, 3, 163, 8, "/lp-amenities/", 330.24),
        _call_keyword("lincoln city hotel deals", "Spanish Head | Deals & Packages", 42, 30, 35, 7, 205, 24, "/lp-deals/", 1036.8),
        _call_keyword("romantic hotel lincoln city", "Spanish Head | Deals & Packages", 19, 14, 16, 3, 221, 12, "/lp-romantic/", 618.24),
        _call_keyword("lincoln city hotel with pool", "Spanish Head | Rooms & Suites", 11, 8, 9, 2, 151, 5, "/lp-amenities/", 234.24),
        _call_keyword("oceanfront suites lincoln city", "Spanish Head | Rooms & Suites", 23, 16, 20, 3, 209, 14, "/lp-accommodations/", 546.96),
    ]
    campaign_rows = [
        _call_campaign("Spanish Head | Brand", 42, 30, 37, 5, 210, 30, 620.0),
        _call_campaign("Spanish Head | Oceanfront Hotel", 199, 140, 173, 26, 206, 127, 4750.25),
        _call_campaign("Spanish Head | Rooms & Suites", 65, 46, 56, 9, 190, 38, 2107.68),
        _call_campaign("Spanish Head | Deals & Packages", 61, 44, 51, 10, 213, 36, 1655.04),
        _call_campaign("Spanish Head | Dining & Fathoms", 16, 11, 13, 3, 163, 8, 330.24),
    ]
    landing_page_rows = [
        _call_landing_page("/lp-main/", "lincoln city hotel", "Spanish Head | Oceanfront Hotel", 106, 91, 15, 73, 198),
        _call_landing_page("/lp-booking/", None, "Spanish Head | Brand", 42, 37, 5, 30, 210),
        _call_landing_page("/lp-deals/", "lincoln city hotel deals", "Spanish Head | Deals & Packages", 42, 35, 7, 30, 205),
        _call_landing_page("/lp-accommodations/", "oceanfront suites lincoln city", "Spanish Head | Rooms & Suites", 54, 47, 7, 38, 203),
        _call_landing_page("/lp-oceanfront/", "oceanfront hotel lincoln city", "Spanish Head | Oceanfront Hotel", 86, 73, 13, 62, 226),
        _call_landing_page("/lp-amenities/", "hotel with restaurant lincoln city", "Spanish Head | Dining & Fathoms", 27, 22, 5, 19, 158),
        _call_landing_page("/lp-romantic/", "romantic hotel lincoln city", "Spanish Head | Deals & Packages", 19, 16, 3, 14, 221),
    ]
    total_calls = sum(row["calls"] for row in keyword_rows)
    missed_calls = sum(row["missed_calls"] for row in keyword_rows)
    answered_calls = sum(row["answered_calls"] for row in keyword_rows)
    first_time_callers = sum(row["first_time_callers"] for row in keyword_rows)
    qualified_calls = sum(row["qualified_calls"] for row in keyword_rows)
    return {
        "schema_version": "callrail_summary.v1",
        "provider": "callrail",
        "profile": profile,
        "client_label": DEFAULT_CLIENT_LABEL,
        "source": "synthetic_fixture",
        "is_real_data": False,
        "generated_at": DEFAULT_GENERATED_AT,
        "date_range": {"start_date": start_date, "end_date": end_date},
        "summary": {
            "total_calls": total_calls,
            "google_ads_calls": total_calls,
            "first_time_callers": first_time_callers,
            "answered_calls": answered_calls,
            "missed_calls": missed_calls,
            "avg_duration_seconds": 200.4,
            "qualified_calls": qualified_calls,
            "calls_with_keyword_attribution": 344,
            "calls_without_keyword_attribution": total_calls - 344,
        },
        "paid_search_attribution": {
            "google_ads_calls": total_calls,
            "calls_with_keyword_attribution": 344,
            "top_keyword": "oceanfront hotel lincoln city",
            "top_campaign": "Spanish Head | Oceanfront Hotel",
            "missed_keyword_calls": 30,
            "attribution_unavailable_calls": total_calls - 344,
            "notes": [
                "Synthetic paid-search call attribution for dashboard-lab UI testing only.",
                "Keyword attribution is intentionally primary for this Spanish Head demo state.",
            ],
        },
        "keyword_rows": keyword_rows,
        "campaign_rows": campaign_rows,
        "landing_page_rows": landing_page_rows,
        "source_rows": [
            {"source": "google_ads", "calls": total_calls, "answered_calls": answered_calls, "missed_calls": missed_calls, "first_time_callers": first_time_callers, "avg_duration_seconds": 200.4},
            {"source": "organic", "calls": 24, "answered_calls": 21, "missed_calls": 3, "first_time_callers": 17, "avg_duration_seconds": 182.0},
            {"source": "direct", "calls": 18, "answered_calls": 16, "missed_calls": 2, "first_time_callers": 10, "avg_duration_seconds": 174.0},
        ],
        "tracking_number_rows": [
            {"label": "Booking line", "source": "google_ads", "calls": 165, "answered_calls": 143, "missed_calls": 22, "first_time_callers": 118},
            {"label": "Oceanfront campaign line", "source": "google_ads", "calls": 137, "answered_calls": 118, "missed_calls": 19, "first_time_callers": 96},
            {"label": "Deals campaign line", "source": "google_ads", "calls": 81, "answered_calls": 70, "missed_calls": 11, "first_time_callers": 57},
        ],
        "missed_call_opportunities": [
            _missed("oceanfront hotel lincoln city", "Spanish Head | Oceanfront Hotel", 7, 68, "High-intent oceanfront searches are generating call demand.", "Review follow-up process for missed calls from paid search traffic.", "high"),
            _missed("oregon coast hotel", "Spanish Head | Oceanfront Hotel", 8, 44, "Broad Oregon Coast hotel traffic can still include booking-ready callers.", "Compare call volume against spend for this keyword group.", "medium"),
            _missed("lincoln city hotel deals", "Spanish Head | Deals & Packages", 7, 42, "Deal-oriented callers may be close to booking when package copy is clear.", "Check whether the landing page matches booking intent.", "medium"),
            _missed("lincoln city hotel with pool", "Spanish Head | Rooms & Suites", 2, 11, "Amenity-specific searches can reveal page-to-call routing gaps.", "Confirm high-call keywords are routed to the best landing page.", "low"),
        ],
        "time_series": [
            {"date": "2026-01-31", "total_calls": 49, "answered_calls": 43, "missed_calls": 6, "first_time_callers": 34, "google_ads_calls": 49},
            {"date": "2026-02-28", "total_calls": 58, "answered_calls": 50, "missed_calls": 8, "first_time_callers": 41, "google_ads_calls": 58},
            {"date": "2026-03-31", "total_calls": 73, "answered_calls": 63, "missed_calls": 10, "first_time_callers": 52, "google_ads_calls": 73},
            {"date": "2026-04-30", "total_calls": 87, "answered_calls": 75, "missed_calls": 12, "first_time_callers": 61, "google_ads_calls": 87},
            {"date": "2026-05-31", "total_calls": 116, "answered_calls": 101, "missed_calls": 15, "first_time_callers": 83, "google_ads_calls": 116},
        ],
        "data_quality_notes": [
            "Synthetic fixture data for dashboard-lab UI testing only.",
            "No real Spanish Head CallRail export, API data, audio files, text call notes, or call-detail rows are included.",
            "CallRail rows are aggregate-only and contain no caller-level details or tracking phone numbers.",
        ],
    }


def _ads_keyword(keyword: str, campaign: str, match_type: str, impressions: int, clicks: int, avg_cpc: float, conversions: float, calls: int, landing_page: str) -> dict[str, Any]:
    cost = round(clicks * avg_cpc, 2)
    return {
        "keyword": keyword,
        "campaign": campaign,
        "match_type": match_type,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(clicks / impressions, 4),
        "avg_cpc": avg_cpc,
        "cost": cost,
        "conversions": conversions,
        "calls": calls,
        "cost_per_call": round(cost / calls, 2),
        "landing_page": landing_page,
    }


def _search_term(search_term: str, matched_keyword: str, campaign: str, impressions: int, clicks: int, avg_cpc: float, conversions: float, calls: int) -> dict[str, Any]:
    return {
        "search_term": search_term,
        "matched_keyword": matched_keyword,
        "campaign": campaign,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round(clicks / impressions, 4),
        "cost": round(clicks * avg_cpc, 2),
        "conversions": conversions,
        "calls": calls,
    }


def _ads_campaign(campaign: str, spend: float, impressions: int, clicks: int, ctr: float, avg_cpc: float, conversions: float, calls: int) -> dict[str, Any]:
    return {
        "campaign": campaign,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "avg_cpc": avg_cpc,
        "conversions": conversions,
        "calls": calls,
        "cost_per_call": round(spend / calls, 2),
    }


def _landing_page(landing_page: str, campaign: str, impressions: int, clicks: int, ctr: float, cost: float, conversions: float, calls: int) -> dict[str, Any]:
    return {
        "landing_page": landing_page,
        "campaign": campaign,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": ctr,
        "cost": cost,
        "conversions": conversions,
        "calls": calls,
        "cost_per_call": round(cost / calls, 2),
    }


def _ads_summary(keyword_rows: list[dict[str, Any]]) -> dict[str, Any]:
    spend = round(sum(row["cost"] for row in keyword_rows), 2)
    clicks = sum(row["clicks"] for row in keyword_rows)
    impressions = sum(row["impressions"] for row in keyword_rows)
    conversions = round(sum(row["conversions"] for row in keyword_rows), 3)
    calls = sum(row["calls"] for row in keyword_rows)
    return {
        "spend": spend,
        "clicks": clicks,
        "impressions": impressions,
        "ctr": round(clicks / impressions, 4),
        "avg_cpc": round(spend / clicks, 2),
        "conversions": conversions,
        "cost_per_conversion": round(spend / conversions, 2),
        "calls": calls,
        "cost_per_call": round(spend / calls, 2),
    }


def _call_keyword(keyword: str, campaign: str, calls: int, first_time_callers: int, answered_calls: int, missed_calls: int, avg_duration_seconds: int, qualified_calls: int, landing_page: str, cost: float) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "campaign": campaign,
        "calls": calls,
        "first_time_callers": first_time_callers,
        "answered_calls": answered_calls,
        "missed_calls": missed_calls,
        "avg_duration_seconds": avg_duration_seconds,
        "qualified_calls": qualified_calls,
        "landing_page": landing_page,
        "source": "google_ads",
        "cost": cost,
        "cost_per_call": round(cost / calls, 2),
    }


def _call_campaign(campaign: str, calls: int, first_time_callers: int, answered_calls: int, missed_calls: int, avg_duration_seconds: int, qualified_calls: int, cost: float) -> dict[str, Any]:
    return {
        "campaign": campaign,
        "calls": calls,
        "first_time_callers": first_time_callers,
        "answered_calls": answered_calls,
        "missed_calls": missed_calls,
        "avg_duration_seconds": avg_duration_seconds,
        "qualified_calls": qualified_calls,
        "cost": cost,
        "cost_per_call": round(cost / calls, 2),
    }


def _call_landing_page(landing_page: str, keyword: str | None, campaign: str, calls: int, answered_calls: int, missed_calls: int, first_time_callers: int, avg_duration_seconds: int) -> dict[str, Any]:
    payload = {
        "landing_page": landing_page,
        "campaign": campaign,
        "calls": calls,
        "answered_calls": answered_calls,
        "missed_calls": missed_calls,
        "first_time_callers": first_time_callers,
        "avg_duration_seconds": avg_duration_seconds,
    }
    if keyword:
        payload["keyword"] = keyword
    return payload


def _missed(keyword: str, campaign: str, missed_calls: int, total_calls: int, why_it_matters: str, recommended_action: str, priority: str) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "campaign": campaign,
        "missed_calls": missed_calls,
        "total_calls": total_calls,
        "why_it_matters": why_it_matters,
        "recommended_action": recommended_action,
        "priority": priority,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
