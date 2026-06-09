from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


BASE_FILES = ["client-profile.json", "combined-dashboard-summary.json"]

PROVIDER_FILES = {
    "ga4": "ga4-summary.json",
    "gsc": "gsc-summary.json",
    "google_ads_search": "google-ads-search-summary.json",
    "google_ads_lsa": "google-ads-lsa-summary.json",
    "local_falcon": "local-falcon-summary.json",
    "callrail": "callrail-summary.json",
    "website_maintenance": "website-maintenance-summary.json",
    "hosting": "hosting-summary.json",
}

ALL_KNOWN_FILES = [*BASE_FILES, *PROVIDER_FILES.values()]
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
class FixtureProfile:
    slug: str
    client_name: str
    domain: str
    primary_market: str
    active_services: list[str]
    providers: list[str]
    primary_service_priority: str
    modules_enabled: list[str]
    above_fold_module_order: list[str]
    below_fold_module_order: list[str]
    top_strategy_focus: list[str]
    current_tasks: list[dict[str, str]]
    recent_insights: list[str]
    latest_report_date: str = "2026-04-30"
    period_start: str = "2026-04-01"

    @property
    def period(self) -> dict[str, str]:
        return {"start": self.period_start, "end": self.latest_report_date}

    @property
    def expected_files(self) -> list[str]:
        return [
            "client-profile.json",
            *[PROVIDER_FILES[provider] for provider in self.providers],
            "combined-dashboard-summary.json",
        ]


@dataclass(frozen=True)
class FixtureWriteResult:
    output_dir: Path
    files: list[Path]
    profile: FixtureProfile


PROFILES = {
    "all-services-client": FixtureProfile(
        slug="all-services-client",
        client_name="Riverside Home Services Demo",
        domain="riversidehomeservices.example",
        primary_market="Portland Metro",
        active_services=[
            "SEO/GEO",
            "Google Ads Search",
            "Google Ads LSA",
            "Local SEO / Maps",
            "Call Tracking",
            "Website Maintenance",
            "Hosting",
        ],
        providers=[
            "ga4",
            "gsc",
            "google_ads_search",
            "google_ads_lsa",
            "local_falcon",
            "callrail",
        ],
        primary_service_priority="SEO/GEO",
        modules_enabled=[
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
        above_fold_module_order=[
            "executive_summary",
            "website_performance",
            "paid_search",
            "call_tracking",
        ],
        below_fold_module_order=[
            "search_console",
            "lsa_performance",
            "local_map_rankings",
            "tasks",
            "insights",
        ],
        top_strategy_focus=[
            "Grow high-intent HVAC and plumbing organic visibility.",
            "Improve paid lead quality and missed-call recovery.",
            "Close Local Falcon ranking gaps in west-side service areas.",
        ],
        current_tasks=[
            {"title": "Refresh HVAC repair landing page calls to action", "service": "SEO/GEO", "status": "in_progress"},
            {"title": "Review LSA disputed lead categories", "service": "Google Ads LSA", "status": "planned"},
            {"title": "Add Beaverton and Gresham local proof sections", "service": "Local SEO / Maps", "status": "planned"},
            {"title": "Audit missed-call follow-up workflow", "service": "Call Tracking", "status": "in_progress"},
        ],
        recent_insights=[
            "Organic Search and Paid Search are both producing strong service-request intent.",
            "HVAC repair has the best cross-channel momentum.",
            "Missed calls represent a measurable conversion recovery opportunity.",
        ],
    ),
    "aluma-seo-geo": FixtureProfile(
        slug="aluma-seo-geo",
        client_name="Aluma Aesthetic Medicine",
        domain="alumapdx.example",
        primary_market="Portland Metro",
        active_services=["SEO/GEO", "GA4 reporting", "GSC reporting", "content performance"],
        providers=["ga4", "gsc"],
        primary_service_priority="SEO/GEO",
        modules_enabled=[
            "executive_summary",
            "website_performance",
            "search_console",
            "content_performance",
            "tasks",
            "insights",
        ],
        above_fold_module_order=["executive_summary", "website_performance", "search_console"],
        below_fold_module_order=["content_performance", "tasks", "insights"],
        top_strategy_focus=[
            "Improve organic visibility for treatment and service pages.",
            "Track search demand across Botox, Dysport, fillers, and aesthetic medicine topics.",
            "Use content performance to prioritize page refreshes and internal linking.",
        ],
        current_tasks=[
            {"title": "Refresh Botox and Dysport page comparison copy", "service": "SEO/GEO", "status": "in_progress"},
            {"title": "Add internal links from filler education content to treatment pages", "service": "content performance", "status": "planned"},
            {"title": "Review GSC query movement for Sculptra and Kybella topics", "service": "GSC reporting", "status": "planned"},
        ],
        recent_insights=[
            "Treatment pages are the primary organic performance surface.",
            "Search demand is strongest around Botox, lip filler, cheek filler, and dermal fillers.",
            "No Ads Search, LSA, or CallRail modules are enabled for this fixture.",
        ],
    ),
    "inn-at-spanish-head": FixtureProfile(
        slug="inn-at-spanish-head",
        client_name="Spanish Head",
        domain="spanishhead.com",
        primary_market="Lincoln City, Oregon",
        active_services=[
            "SEO/GEO",
            "GA4 reporting",
            "GSC reporting",
            "Local SEO / Maps",
            "content performance",
        ],
        providers=["ga4", "gsc", "local_falcon"],
        primary_service_priority="SEO/GEO + Local Visibility",
        modules_enabled=[
            "executive_summary",
            "website_performance",
            "search_console",
            "local_map_rankings",
            "content_performance",
            "tasks",
            "insights",
        ],
        above_fold_module_order=["executive_summary", "website_performance", "search_console"],
        below_fold_module_order=["local_map_rankings", "content_performance", "tasks", "insights"],
        top_strategy_focus=[
            "Grow organic visibility for Lincoln City oceanfront hotel searches.",
            "Use local visibility data to understand lodging and ocean-view search demand.",
            "Prioritize content around oceanfront stays, romantic getaways, and Oregon Coast lodging.",
        ],
        current_tasks=[
            {"title": "Review oceanfront hotel query visibility", "service": "GSC reporting", "status": "planned"},
            {"title": "Prepare Lincoln City lodging content refresh plan", "service": "SEO/GEO", "status": "planned"},
            {"title": "Validate Local Falcon query set for hospitality searches", "service": "Local SEO / Maps", "status": "planned"},
        ],
        recent_insights=[
            "Hospitality reporting is modeled as organic/local SEO and content performance.",
            "Local visibility should focus on Lincoln City and Oregon Coast lodging intent.",
            "No Ads Search, LSA, CallRail, or contractor lead-gen modules are enabled for this fixture.",
        ],
    ),
    "priority-tree-lead-gen": FixtureProfile(
        slug="priority-tree-lead-gen",
        client_name="Priority Tree Service Demo",
        domain="prioritytreeservice.example",
        primary_market="Portland Metro",
        active_services=[
            "SEO/GEO",
            "GA4 reporting",
            "GSC reporting",
            "Google Ads Search",
            "Local SEO / Maps",
            "Call Tracking",
        ],
        providers=["ga4", "gsc", "google_ads_search", "local_falcon", "callrail"],
        primary_service_priority="lead generation",
        modules_enabled=[
            "executive_summary",
            "website_performance",
            "search_console",
            "paid_search",
            "local_map_rankings",
            "call_tracking",
            "tasks",
            "insights",
        ],
        above_fold_module_order=["executive_summary", "paid_search", "call_tracking", "local_map_rankings"],
        below_fold_module_order=["website_performance", "search_console", "tasks", "insights"],
        top_strategy_focus=[
            "Increase qualified tree removal and pruning leads.",
            "Improve local visibility for emergency tree service searches.",
            "Use call quality signals to tune paid search and landing pages.",
        ],
        current_tasks=[
            {"title": "Split emergency tree service ad group by urgent intent", "service": "Google Ads Search", "status": "planned"},
            {"title": "Add pruning and tree removal proof sections to landing pages", "service": "SEO/GEO", "status": "in_progress"},
            {"title": "Review missed-call patterns during storm-related demand spikes", "service": "Call Tracking", "status": "planned"},
        ],
        recent_insights=[
            "Emergency tree service demand produces high-value but volatile call volume.",
            "Local ranking strength is best near the core Portland service area.",
            "Paid and organic channels both support tree removal lead flow.",
        ],
    ),
    "ads-client": FixtureProfile(
        slug="ads-client",
        client_name="Cascade Paid Search Demo",
        domain="cascadepaidsearch.example",
        primary_market="Pacific Northwest",
        active_services=["Google Ads Search", "GA4 reporting", "conversion tracking summary"],
        providers=["ga4", "google_ads_search"],
        primary_service_priority="paid search efficiency",
        modules_enabled=["executive_summary", "website_performance", "paid_search", "tasks", "insights"],
        above_fold_module_order=["executive_summary", "paid_search", "website_performance"],
        below_fold_module_order=["tasks", "insights"],
        top_strategy_focus=[
            "Improve conversion rate from paid landing pages.",
            "Reduce cost per conversion in non-brand search campaigns.",
            "Use GA4 conversion tracking to validate paid search quality.",
        ],
        current_tasks=[
            {"title": "Pause low-intent broad match terms", "service": "Google Ads Search", "status": "in_progress"},
            {"title": "Review conversion tracking event consistency", "service": "GA4 reporting", "status": "planned"},
        ],
        recent_insights=[
            "Non-brand search drives most spend and most conversion variance.",
            "Landing page engagement is a good early warning signal for paid efficiency.",
        ],
    ),
    "seo-geo-ads-client": FixtureProfile(
        slug="seo-geo-ads-client",
        client_name="Willamette Growth Demo",
        domain="willamettegrowth.example",
        primary_market="Portland Metro",
        active_services=[
            "SEO/GEO",
            "GA4 reporting",
            "GSC reporting",
            "Google Ads Search",
            "Local SEO / Maps",
        ],
        providers=["ga4", "gsc", "google_ads_search", "local_falcon"],
        primary_service_priority="blended search growth",
        modules_enabled=[
            "executive_summary",
            "website_performance",
            "search_console",
            "paid_search",
            "local_map_rankings",
            "tasks",
            "insights",
        ],
        above_fold_module_order=["executive_summary", "website_performance", "paid_search"],
        below_fold_module_order=["search_console", "local_map_rankings", "tasks", "insights"],
        top_strategy_focus=[
            "Balance paid and organic coverage on high-intent service searches.",
            "Improve local map visibility in priority service areas.",
            "Use GSC query movement to guide paid search expansion.",
        ],
        current_tasks=[
            {"title": "Compare paid search terms against rising GSC queries", "service": "SEO/GEO", "status": "planned"},
            {"title": "Refresh local landing page proof blocks", "service": "Local SEO / Maps", "status": "in_progress"},
        ],
        recent_insights=[
            "Paid search fills gaps where organic ranking is still maturing.",
            "Local visibility improvements are opening opportunities for lower paid dependence.",
        ],
    ),
    "maintenance-hosting-client": FixtureProfile(
        slug="maintenance-hosting-client",
        client_name="Evergreen Care Plan Demo",
        domain="evergreencareplan.example",
        primary_market="Local/Internal",
        active_services=["Website Maintenance", "Hosting"],
        providers=["website_maintenance", "hosting"],
        primary_service_priority="website operations",
        modules_enabled=["executive_summary", "maintenance", "hosting", "tasks", "insights"],
        above_fold_module_order=["executive_summary", "maintenance", "hosting"],
        below_fold_module_order=["tasks", "insights"],
        top_strategy_focus=[
            "Keep website maintenance, uptime, and hosting health visible without marketing modules.",
            "Track care-plan tasks, updates, backups, and performance checks.",
        ],
        current_tasks=[
            {"title": "Apply monthly plugin and CMS updates", "service": "Website Maintenance", "status": "planned"},
            {"title": "Review backup restore-point status", "service": "Hosting", "status": "in_progress"},
        ],
        recent_insights=[
            "No paid, organic, call tracking, or local rank modules are enabled for this fixture.",
            "Operational health modules can stand alone for maintenance-only clients.",
        ],
    ),
}


def default_output_dir(profile_slug: str) -> Path:
    return Path("exports") / "dashboard-lab" / profile_slug


def list_profile_slugs() -> list[str]:
    return list(PROFILES)


def build_all_services_fixture(output_dir: Path) -> FixtureWriteResult:
    return build_profile_fixture("all-services-client", output_dir)


def build_profile_fixture(profile_slug: str, output_dir: Path | None = None) -> FixtureWriteResult:
    profile = _profile(profile_slug)
    output_dir = output_dir or default_output_dir(profile.slug)
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_stale_known_files(output_dir, profile.expected_files)

    payloads = profile_payloads(profile.slug)
    written = []
    for filename, payload in payloads.items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    validate_dashboard_lab_fixture(output_dir)
    return FixtureWriteResult(output_dir=output_dir, files=written, profile=profile)


def build_all_profiles(base_output_dir: Path | None = None) -> list[FixtureWriteResult]:
    base_output_dir = base_output_dir or (Path("exports") / "dashboard-lab")
    return [
        build_profile_fixture(slug, base_output_dir / slug)
        for slug in list_profile_slugs()
    ]


def profile_payloads(profile_slug: str) -> dict[str, dict[str, Any]]:
    profile = _profile(profile_slug)
    payloads = {
        "client-profile.json": _client_profile(profile),
        "combined-dashboard-summary.json": _combined_dashboard_summary(profile),
    }
    for provider in profile.providers:
        payloads[PROVIDER_FILES[provider]] = _provider_payload(provider, profile)
    return {filename: payloads[filename] for filename in profile.expected_files}


def all_services_payloads() -> dict[str, dict[str, Any]]:
    return profile_payloads("all-services-client")


def validate_dashboard_lab_fixture(output_dir: Path) -> list[Path]:
    for filename in BASE_FILES:
        if not (output_dir / filename).exists():
            raise FixtureValidationError(f"missing expected fixture files: {filename}")

    profile_payload = _load_json(output_dir / "client-profile.json")
    _reject_secret_like_keys(profile_payload, "client-profile.json")
    _validate_client_profile(profile_payload)
    profile_slug = profile_payload.get("fixture_profile")
    profile = PROFILES.get(str(profile_slug))
    if not profile:
        raise FixtureValidationError("client-profile.json has unknown fixture_profile")

    expected_files = profile.expected_files
    missing = [name for name in expected_files if not (output_dir / name).exists()]
    if missing:
        raise FixtureValidationError(f"missing expected fixture files: {', '.join(missing)}")

    stale = [
        name for name in ALL_KNOWN_FILES
        if name not in expected_files and (output_dir / name).exists()
    ]
    if stale:
        raise FixtureValidationError(f"fixture has stale disabled provider files: {', '.join(stale)}")

    payloads = {"client-profile.json": profile_payload}
    for filename in expected_files:
        if filename == "client-profile.json":
            continue
        payload = _load_json(output_dir / filename)
        _reject_secret_like_keys(payload, filename)
        payloads[filename] = payload

    for provider in profile.providers:
        filename = PROVIDER_FILES[provider]
        _validate_provider_summary(payloads[filename], provider, filename)
        if provider == "callrail":
            _validate_callrail_privacy(payloads[filename])

    _validate_combined_summary(payloads["combined-dashboard-summary.json"], profile)
    return [output_dir / name for name in expected_files]


def validate_dashboard_lab_export_folder(output_dir: Path, profile_slug: str) -> list[Path]:
    """Lightweight validation for synthetic or ignored local-real dashboard-lab export folders."""
    profile = _profile(profile_slug)
    missing = [filename for filename in profile.expected_files if not (output_dir / filename).exists()]
    if missing:
        raise FixtureValidationError(f"missing expected export files: {', '.join(missing)}")

    payloads = {}
    for filename in profile.expected_files:
        payload = _load_json(output_dir / filename)
        _reject_secret_like_keys(payload, filename)
        payloads[filename] = payload

    client_profile = payloads["client-profile.json"]
    if client_profile.get("fixture_profile") != profile.slug:
        raise FixtureValidationError("client-profile.json fixture_profile mismatch")

    combined = payloads["combined-dashboard-summary.json"]
    if combined.get("fixture_profile") != profile.slug:
        raise FixtureValidationError("combined-dashboard-summary.json fixture_profile mismatch")
    expected_summaries = {provider: PROVIDER_FILES[provider] for provider in profile.providers}
    if combined.get("provider_summaries") != expected_summaries:
        raise FixtureValidationError("combined-dashboard-summary.json must reference enabled profile providers only")

    return [output_dir / filename for filename in profile.expected_files]


def _profile(profile_slug: str) -> FixtureProfile:
    try:
        return PROFILES[profile_slug]
    except KeyError as exc:
        valid = ", ".join(list_profile_slugs())
        raise FixtureValidationError(f"unknown fixture profile '{profile_slug}'. Valid profiles: {valid}") from exc


def _remove_stale_known_files(output_dir: Path, expected_files: list[str]) -> None:
    for filename in ALL_KNOWN_FILES:
        path = output_dir / filename
        if filename not in expected_files and path.exists():
            path.unlink()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureValidationError(f"{path.name} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise FixtureValidationError(f"{path.name} must contain a JSON object")
    return payload


def _client_profile(profile: FixtureProfile) -> dict[str, Any]:
    return {
        "schema_version": "dashboard_lab_client_profile.v1",
        "fixture_profile": profile.slug,
        "client_key": profile.slug.replace("-", "_"),
        "client_name": profile.client_name,
        "domain": profile.domain,
        "primary_market": profile.primary_market,
        "source_mode": "synthetic_mock",
        "local_only": True,
        "mock_data": True,
        "active_services": profile.active_services,
        "enabled_providers": profile.providers,
        "reporting_period": profile.period,
        "fixture_notes": [
            "Synthetic local fixture for dashboard prototyping.",
            "No live provider connections, credentials, or portal database writes.",
        ],
    }


def _provider_base(provider: str, profile: FixtureProfile, period: dict[str, str] | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": "dashboard_lab_provider_summary.v1",
        "provider": provider,
        "fixture_profile": profile.slug,
        "source_mode": "synthetic_mock",
        "local_only": True,
        "mock_data": True,
    }
    if period:
        payload["reporting_period"] = period
    return payload


def _provider_payload(provider: str, profile: FixtureProfile) -> dict[str, Any]:
    if provider == "ga4":
        return _ga4_summary(profile)
    if provider == "gsc":
        return _gsc_summary(profile)
    if provider == "google_ads_search":
        return _google_ads_search_summary(profile)
    if provider == "google_ads_lsa":
        return _google_ads_lsa_summary(profile)
    if provider == "local_falcon":
        return _local_falcon_summary(profile)
    if provider == "callrail":
        return _callrail_summary(profile)
    if provider == "website_maintenance":
        return _website_maintenance_summary(profile)
    if provider == "hosting":
        return _hosting_summary(profile)
    raise FixtureValidationError(f"unsupported provider: {provider}")


def _ga4_summary(profile: FixtureProfile) -> dict[str, Any]:
    if profile.slug == "aluma-seo-geo":
        top_pages = [
            {"path": "/botox-portland", "title": "Botox Portland", "views": 3920, "users": 1680, "conversions": 44},
            {"path": "/dysport-portland", "title": "Dysport Portland", "views": 2410, "users": 1015, "conversions": 28},
            {"path": "/dermal-fillers", "title": "Dermal Fillers", "views": 3580, "users": 1490, "conversions": 39},
            {"path": "/sculptra", "title": "Sculptra", "views": 1725, "users": 740, "conversions": 17},
            {"path": "/lip-filler", "title": "Lip Filler", "views": 2140, "users": 930, "conversions": 24},
        ]
        channels = [
            {"channel": "Organic Search", "sessions": 3720, "users": 2890, "views": 10640, "conversions": 118},
            {"channel": "Direct", "sessions": 1260, "users": 1010, "views": 3140, "conversions": 31},
            {"channel": "Referral", "sessions": 540, "users": 465, "views": 1410, "conversions": 13},
            {"channel": "Organic Social", "sessions": 420, "users": 350, "views": 980, "conversions": 8},
        ]
        metrics = {
            "users": 6120,
            "sessions": 7940,
            "views": 22680,
            "engagement_rate": 0.712,
            "average_session_duration_seconds": 152,
            "event_count": 51240,
            "conversions": 186,
        }
        insights = [
            "Organic traffic is concentrated around treatment and service education pages.",
            "Botox, dermal filler, and lip filler pages are the strongest organic engagement surfaces.",
        ]
    elif profile.slug == "inn-at-spanish-head":
        top_pages = [
            {"path": "/", "title": "Oceanfront Hotel in Lincoln City", "views": 5840, "users": 2520, "conversions": 96},
            {"path": "/rooms", "title": "Oceanfront Rooms", "views": 4120, "users": 1840, "conversions": 74},
            {"path": "/specials", "title": "Oregon Coast Hotel Specials", "views": 2380, "users": 1120, "conversions": 38},
            {"path": "/dining", "title": "Ocean View Dining", "views": 1920, "users": 870, "conversions": 22},
            {"path": "/lincoln-city", "title": "Lincoln City Getaway Guide", "views": 1680, "users": 760, "conversions": 18},
        ]
        channels = [
            {"channel": "Organic Search", "sessions": 4620, "users": 3510, "views": 12880, "conversions": 154},
            {"channel": "Direct", "sessions": 2180, "users": 1660, "views": 5720, "conversions": 66},
            {"channel": "Referral", "sessions": 940, "users": 790, "views": 2460, "conversions": 24},
            {"channel": "Organic Social", "sessions": 520, "users": 440, "views": 1260, "conversions": 10},
        ]
        metrics = {
            "users": 7380,
            "sessions": 9820,
            "views": 26340,
            "engagement_rate": 0.694,
            "average_session_duration_seconds": 164,
            "event_count": 60420,
            "conversions": 254,
        }
        insights = [
            "Organic Search is the strongest synthetic acquisition surface for lodging intent.",
            "Rooms, specials, and Lincoln City destination content are the primary engagement paths.",
        ]
    else:
        top_pages = [
            {"path": "/", "title": "Home", "views": 6920, "users": 2840, "conversions": 62},
            {"path": "/services/hvac-repair", "title": "HVAC Repair", "views": 4310, "users": 1610, "conversions": 74},
            {"path": "/services/plumbing", "title": "Plumbing Services", "views": 3860, "users": 1475, "conversions": 68},
            {"path": "/service-area/portland", "title": "Portland Service Area", "views": 2510, "users": 980, "conversions": 31},
            {"path": "/contact", "title": "Request Service", "views": 2280, "users": 1160, "conversions": 77},
        ]
        if profile.slug == "priority-tree-lead-gen":
            top_pages = [
                {"path": "/tree-removal", "title": "Tree Removal", "views": 4680, "users": 1740, "conversions": 86},
                {"path": "/emergency-tree-service", "title": "Emergency Tree Service", "views": 3210, "users": 1380, "conversions": 72},
                {"path": "/tree-pruning", "title": "Tree Pruning", "views": 2860, "users": 1150, "conversions": 41},
                {"path": "/service-area/portland", "title": "Portland Tree Service", "views": 2420, "users": 940, "conversions": 33},
                {"path": "/contact", "title": "Request Estimate", "views": 2180, "users": 1050, "conversions": 64},
            ]
        channels = [
            {"channel": "Organic Search", "sessions": 4210, "users": 3290, "views": 11320, "conversions": 142},
            {"channel": "Paid Search", "sessions": 2985, "users": 2310, "views": 7610, "conversions": 96},
            {"channel": "Direct", "sessions": 1640, "users": 1304, "views": 3840, "conversions": 28},
            {"channel": "Referral", "sessions": 1015, "users": 870, "views": 2510, "conversions": 22},
            {"channel": "Organic Social", "sessions": 760, "users": 646, "views": 1785, "conversions": 14},
        ]
        metrics = {
            "users": 8420,
            "sessions": 11385,
            "views": 28640,
            "engagement_rate": 0.684,
            "average_session_duration_seconds": 138,
            "event_count": 74520,
            "conversions": 312,
        }
        insights = [
            "Organic Search generated the largest session volume and the strongest assisted service-request activity.",
            "High-intent landing pages are carrying most website engagement.",
        ]

    payload = _provider_base("ga4", profile, profile.period)
    payload.update(
        {
            "summary_metrics": metrics,
            "time_series": _daily_series(
                profile.period,
                {"users": 250, "sessions": 330, "views": 840, "conversions": 8},
                {"users": 64, "sessions": 83, "views": 210, "conversions": 6},
            ),
            "traffic_channels": channels,
            "top_pages": top_pages,
            "insights": insights,
            "warnings": [],
        }
    )
    return payload


def _gsc_summary(profile: FixtureProfile) -> dict[str, Any]:
    if profile.slug == "aluma-seo-geo":
        top_queries = [
            {"query": "botox portland", "clicks": 540, "impressions": 9800, "position": 5.2},
            {"query": "dysport portland", "clicks": 318, "impressions": 6200, "position": 6.4},
            {"query": "dermal fillers portland", "clicks": 452, "impressions": 11100, "position": 7.1},
            {"query": "sculptra portland", "clicks": 210, "impressions": 4200, "position": 8.5},
            {"query": "kybella portland", "clicks": 168, "impressions": 3600, "position": 9.2},
        ]
        top_pages = [
            {"path": "/botox-portland", "clicks": 880, "impressions": 17600, "ctr": 0.05},
            {"path": "/dermal-fillers", "clicks": 720, "impressions": 18900, "ctr": 0.0381},
            {"path": "/lip-filler", "clicks": 410, "impressions": 9300, "ctr": 0.0441},
        ]
        movement = [
            {"query": "botox portland", "previous_position": 6.8, "current_position": 5.2, "change": -1.6},
            {"query": "cheek filler portland", "previous_position": 12.4, "current_position": 9.7, "change": -2.7},
            {"query": "kybella portland", "previous_position": 8.8, "current_position": 9.2, "change": 0.4},
        ]
        metrics = {"clicks": 3860, "impressions": 112400, "ctr": 0.0343, "average_position": 8.7}
        insights = [
            "Treatment page demand is strongest for Botox, dermal fillers, and lip filler searches.",
            "Sculptra and Kybella queries are useful expansion areas for content updates.",
        ]
    elif profile.slug == "inn-at-spanish-head":
        top_queries = [
            {"query": "lincoln city oceanfront hotel", "clicks": 620, "impressions": 11800, "position": 4.7},
            {"query": "lincoln city hotel", "clicks": 540, "impressions": 15200, "position": 6.2},
            {"query": "oregon coast oceanfront lodging", "clicks": 318, "impressions": 8700, "position": 7.8},
            {"query": "hotel with ocean views lincoln city", "clicks": 286, "impressions": 6400, "position": 5.9},
            {"query": "lincoln city romantic getaway", "clicks": 174, "impressions": 3900, "position": 8.4},
        ]
        top_pages = [
            {"path": "/", "clicks": 980, "impressions": 22600, "ctr": 0.0434},
            {"path": "/rooms", "clicks": 710, "impressions": 17100, "ctr": 0.0415},
            {"path": "/specials", "clicks": 390, "impressions": 9200, "ctr": 0.0424},
            {"path": "/lincoln-city", "clicks": 245, "impressions": 7600, "ctr": 0.0322},
        ]
        movement = [
            {"query": "lincoln city oceanfront hotel", "previous_position": 5.8, "current_position": 4.7, "change": -1.1},
            {"query": "hotel with ocean views lincoln city", "previous_position": 7.4, "current_position": 5.9, "change": -1.5},
            {"query": "oregon coast oceanfront lodging", "previous_position": 8.1, "current_position": 7.8, "change": -0.3},
        ]
        metrics = {"clicks": 4120, "impressions": 126800, "ctr": 0.0325, "average_position": 8.3}
        insights = [
            "Oceanfront hotel and Lincoln City lodging terms are the strongest organic demand surfaces.",
            "Destination and room content can support both discovery and booking-intent queries.",
        ]
    elif profile.slug == "priority-tree-lead-gen":
        top_queries = [
            {"query": "tree removal portland", "clicks": 710, "impressions": 12800, "position": 4.9},
            {"query": "emergency tree service", "clicks": 620, "impressions": 10400, "position": 5.7},
            {"query": "tree pruning near me", "clicks": 388, "impressions": 8200, "position": 7.2},
        ]
        top_pages = [
            {"path": "/tree-removal", "clicks": 1160, "impressions": 21800, "ctr": 0.0532},
            {"path": "/emergency-tree-service", "clicks": 840, "impressions": 16400, "ctr": 0.0512},
            {"path": "/tree-pruning", "clicks": 530, "impressions": 11900, "ctr": 0.0445},
        ]
        movement = [
            {"query": "emergency tree service", "previous_position": 7.4, "current_position": 5.7, "change": -1.7},
            {"query": "tree pruning near me", "previous_position": 8.9, "current_position": 7.2, "change": -1.7},
        ]
        metrics = {"clicks": 5240, "impressions": 133200, "ctr": 0.0393, "average_position": 8.9}
        insights = [
            "Emergency and removal terms are strongest for lead generation.",
            "Pruning visibility is improving and can support seasonal demand.",
        ]
    else:
        top_queries = [
            {"query": "hvac repair portland", "clicks": 620, "impressions": 11800, "position": 4.8},
            {"query": "emergency plumber near me", "clicks": 545, "impressions": 13640, "position": 6.1},
            {"query": "furnace repair portland", "clicks": 488, "impressions": 9200, "position": 5.3},
            {"query": "water heater replacement", "clicks": 315, "impressions": 8700, "position": 8.9},
        ]
        top_pages = [
            {"path": "/services/hvac-repair", "clicks": 1120, "impressions": 26800, "ctr": 0.0418},
            {"path": "/services/plumbing", "clicks": 980, "impressions": 30100, "ctr": 0.0326},
            {"path": "/service-area/portland", "clicks": 625, "impressions": 18400, "ctr": 0.034},
        ]
        movement = [
            {"query": "hvac repair portland", "previous_position": 6.7, "current_position": 4.8, "change": -1.9},
            {"query": "water heater replacement", "previous_position": 11.4, "current_position": 8.9, "change": -2.5},
            {"query": "drain cleaning portland", "previous_position": 9.2, "current_position": 10.1, "change": 0.9},
        ]
        metrics = {"clicks": 4980, "impressions": 148500, "ctr": 0.0335, "average_position": 9.8}
        insights = [
            "High-intent service terms improved into stronger average positions.",
            "Service pages have large impression volume and should be tested for stronger calls to action.",
        ]

    payload = _provider_base("gsc", profile, profile.period)
    payload.update(
        {
            "summary_metrics": metrics,
            "time_series": _daily_series(
                profile.period,
                {"clicks": 142, "impressions": 4300},
                {"clicks": 48, "impressions": 1180},
            ),
            "top_queries": top_queries,
            "top_pages": top_pages,
            "query_movement": movement,
            "insights": insights,
            "warnings": [],
        }
    )
    return payload


def _google_ads_search_summary(profile: FixtureProfile) -> dict[str, Any]:
    spend = 18420.75
    conversions = 286
    clicks = 3925
    impressions = 82600
    if profile.slug == "priority-tree-lead-gen":
        campaigns = [
            {"name": "Search | Emergency Tree Service", "spend": 6420.3, "clicks": 1080, "conversions": 92},
            {"name": "Search | Tree Removal", "spend": 5280.8, "clicks": 960, "conversions": 74},
            {"name": "Search | Tree Pruning", "spend": 2760.1, "clicks": 540, "conversions": 36},
        ]
        keywords = [
            {"term": "emergency tree service", "clicks": 210, "conversions": 26},
            {"term": "tree removal near me", "clicks": 198, "conversions": 22},
            {"term": "tree pruning service", "clicks": 132, "conversions": 11},
        ]
    else:
        campaigns = [
            {"name": "Search | HVAC Emergency", "spend": 6820.4, "clicks": 1290, "conversions": 104},
            {"name": "Search | Plumbing Core", "spend": 5940.2, "clicks": 1185, "conversions": 88},
            {"name": "Search | Water Heater", "spend": 3160.9, "clicks": 715, "conversions": 54},
            {"name": "Search | Brand", "spend": 910.25, "clicks": 420, "conversions": 28},
        ]
        keywords = [
            {"term": "emergency hvac repair", "clicks": 245, "conversions": 28},
            {"term": "plumber near me", "clicks": 218, "conversions": 22},
            {"term": "furnace repair portland", "clicks": 176, "conversions": 17},
            {"term": "water heater install", "clicks": 149, "conversions": 13},
        ]

    payload = _provider_base("google_ads_search", profile, profile.period)
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
                profile.period,
                {"spend": 520, "clicks": 112, "impressions": 2420, "conversions": 7},
                {"spend": 180, "clicks": 42, "impressions": 780, "conversions": 5},
            ),
            "campaigns": campaigns,
            "ad_groups": [
                {"name": "High Intent Core", "campaign": campaigns[0]["name"], "spend": 3910.8, "conversions": 66},
                {"name": "Near Me Searches", "campaign": campaigns[1]["name"], "spend": 2075.4, "conversions": 28},
                {"name": "Service Variants", "campaign": campaigns[-1]["name"], "spend": 1885.3, "conversions": 31},
            ],
            "safe_keyword_preview": keywords,
            "insights": [
                "High-intent search campaigns are the strongest paid conversion driver.",
                "Safe keyword previews are synthetic and contain no account exports.",
            ],
            "warnings": [],
        }
    )
    return payload


def _google_ads_lsa_summary(profile: FixtureProfile) -> dict[str, Any]:
    spend = 7825.5
    leads = 132
    payload = _provider_base("google_ads_lsa", profile, profile.period)
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
                profile.period,
                {"spend": 220, "leads": 3, "calls": 3, "messages": 1},
                {"spend": 90, "leads": 3, "calls": 2, "messages": 1},
            ),
            "lead_categories": [
                {"category": "HVAC Repair", "leads": 52, "booked_leads": 31, "cost_per_lead": 55.4},
                {"category": "Plumbing", "leads": 44, "booked_leads": 24, "cost_per_lead": 61.2},
                {"category": "Water Heater", "leads": 21, "booked_leads": 12, "cost_per_lead": 58.9},
            ],
            "insights": [
                "Booked lead rate is strongest for urgent service categories.",
                "Dispute review should focus on out-of-area and wrong-service leads.",
            ],
            "warnings": [],
        }
    )
    return payload


def _local_falcon_summary(profile: FixtureProfile) -> dict[str, Any]:
    keywords = ["hvac repair", "plumber", "water heater repair"]
    center_point_label = "Portland, OR"
    top_areas = [
        {"area": "North Portland", "average_rank": 2.4},
        {"area": "Pearl District", "average_rank": 3.1},
        {"area": "Sellwood", "average_rank": 3.6},
    ]
    weak_areas = [
        {"area": "Beaverton", "average_rank": 11.2},
        {"area": "Gresham", "average_rank": 10.7},
        {"area": "Lake Oswego", "average_rank": 9.8},
    ]
    insights = [
        "Map visibility improved for tracked service keywords month over month.",
        "Outer west-side ranking gaps should guide location page priorities.",
    ]
    if profile.slug == "priority-tree-lead-gen":
        keywords = ["tree removal", "emergency tree service", "tree pruning"]
    elif profile.slug == "inn-at-spanish-head":
        keywords = [
            "lincoln city oceanfront hotel",
            "lincoln city hotel",
            "oregon coast oceanfront lodging",
            "hotel with ocean views lincoln city",
            "lincoln city romantic getaway",
            "can you recommend an oceanfront hotel in lincoln city oregon?",
        ]
        center_point_label = "Lincoln City, OR"
        top_areas = [
            {"area": "Oceanlake", "average_rank": 2.8},
            {"area": "Nelscott", "average_rank": 3.4},
            {"area": "Roads End", "average_rank": 4.1},
        ]
        weak_areas = [
            {"area": "South Beach", "average_rank": 10.6},
            {"area": "Depoe Bay", "average_rank": 11.4},
            {"area": "Newport", "average_rank": 12.1},
        ]
        insights = [
            "Local visibility is strongest for Lincoln City oceanfront lodging intent.",
            "Regional Oregon Coast terms should be monitored without overextending local relevance.",
        ]
    payload = _provider_base("local_falcon", profile)
    payload.update(
        {
            "scan_date": "2026-04-28",
            "location_metadata": {
                "business_name": profile.client_name,
                "primary_market": profile.primary_market,
                "center_point_label": center_point_label,
            },
            "grid_metadata": {
                "grid_size": "7x7",
                "radius_miles": 8,
                "keywords_tracked": keywords,
            },
            "summary_metrics": {
                "average_rank": 5.7,
                "visibility_score": 71,
                "top_3_grid_share": 0.38,
                "top_10_grid_share": 0.86,
            },
            "top_ranking_areas": top_areas,
            "weak_ranking_areas": weak_areas,
            "keyword_location_scans": [
                {"keyword": keywords[0], "average_rank": 4.6, "visibility_score": 78},
                {"keyword": keywords[1], "average_rank": 6.1, "visibility_score": 69},
                {"keyword": keywords[2], "average_rank": 6.5, "visibility_score": 66},
            ],
            "scan_history": [
                {"scan_date": "2026-02-28", "average_rank": 7.8, "visibility_score": 62},
                {"scan_date": "2026-03-28", "average_rank": 6.4, "visibility_score": 68},
                {"scan_date": "2026-04-28", "average_rank": 5.7, "visibility_score": 71},
            ],
            "insights": insights,
            "warnings": [],
        }
    )
    return payload


def _callrail_summary(profile: FixtureProfile) -> dict[str, Any]:
    payload = _provider_base("callrail", profile, profile.period)
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
                profile.period,
                {"calls": 13, "answered_calls": 11, "missed_calls": 2, "qualified_leads": 4},
                {"calls": 6, "answered_calls": 5, "missed_calls": 2, "qualified_leads": 3},
            ),
            "source_breakdown": [
                {"source": "Google Ads Search", "calls": 168, "qualified_leads": 62},
                {"source": "Organic Search", "calls": 142, "qualified_leads": 44},
                {"source": "Local Search", "calls": 108, "qualified_leads": 31},
                {"source": "Direct", "calls": 46, "qualified_leads": 8},
                {"source": "Referral", "calls": 22, "qualified_leads": 3},
            ],
            "safe_call_examples": [
                {"caller_label": "Caller 001", "source": "Google Ads Search", "duration_seconds": 332, "status": "answered", "qualified": True},
                {"caller_label": "Caller 002", "source": "Organic Search", "duration_seconds": 184, "status": "answered", "qualified": True},
                {"caller_label": "Caller 003", "source": "Local Search", "duration_seconds": 48, "status": "missed", "qualified": False},
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


def _website_maintenance_summary(profile: FixtureProfile) -> dict[str, Any]:
    payload = _provider_base("website_maintenance", profile, profile.period)
    payload.update(
        {
            "summary_metrics": {
                "updates_completed": 18,
                "open_maintenance_tasks": 3,
                "security_checks_passed": 12,
                "content_edits_completed": 7,
            },
            "recent_activity": [
                {"date": "2026-04-05", "type": "CMS update", "status": "completed"},
                {"date": "2026-04-12", "type": "Plugin update batch", "status": "completed"},
                {"date": "2026-04-22", "type": "Accessibility copy cleanup", "status": "completed"},
            ],
            "insights": [
                "Maintenance work is current and no marketing reporting modules are enabled.",
                "Care-plan visibility can focus on tasks, updates, and operational status.",
            ],
            "warnings": [],
        }
    )
    return payload


def _hosting_summary(profile: FixtureProfile) -> dict[str, Any]:
    payload = _provider_base("hosting", profile, profile.period)
    payload.update(
        {
            "summary_metrics": {
                "uptime_percent": 99.98,
                "backups_completed": 30,
                "average_response_time_ms": 184,
                "incidents": 0,
            },
            "health_checks": [
                {"name": "Daily backups", "status": "healthy"},
                {"name": "SSL certificate", "status": "healthy"},
                {"name": "Core web vitals watch", "status": "monitoring"},
            ],
            "insights": [
                "Hosting is stable with successful daily backups.",
                "No incidents were recorded in the synthetic reporting period.",
            ],
            "warnings": [],
        }
    )
    return payload


def _combined_dashboard_summary(profile: FixtureProfile) -> dict[str, Any]:
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
        [
            "schema_version",
            "fixture_profile",
            "client_name",
            "domain",
            "active_services",
            "enabled_providers",
            "reporting_period",
            "local_only",
        ],
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


def _validate_combined_summary(payload: dict[str, Any], profile: FixtureProfile) -> None:
    _require_fields(
        payload,
        "combined-dashboard-summary.json",
        [
            "schema_version",
            "fixture_profile",
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
    expected = {provider: PROVIDER_FILES[provider] for provider in profile.providers}
    if summaries != expected:
        raise FixtureValidationError(
            "combined-dashboard-summary.json must reference only enabled provider summary files"
        )


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
