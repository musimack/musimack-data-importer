from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportingDatasetContract:
    schema_version: str
    provider: str
    report_type: str
    data_scope: str
    ranked_row_fields: tuple[str, ...] = ()


CANONICAL_DATASET_CONTRACTS = {
    "ga4_metric_display.v1": ReportingDatasetContract(
        "ga4_metric_display.v1", "ga4", "metric_display", "ga4_report_summary"
    ),
    "ga4_top_sources_display.v1": ReportingDatasetContract(
        "ga4_top_sources_display.v1", "ga4", "top_sources_display", "source_medium", ("rows",)
    ),
    "ga4_top_landing_pages_display.v1": ReportingDatasetContract(
        "ga4_top_landing_pages_display.v1",
        "ga4",
        "top_landing_pages_display",
        "landing_page",
        ("rows",),
    ),
    "ga4_most_viewed_pages_display.v1": ReportingDatasetContract(
        "ga4_most_viewed_pages_display.v1",
        "ga4",
        "most_viewed_pages_display",
        "page_popularity",
        ("rows",),
    ),
    "gsc_summary_display.v1": ReportingDatasetContract(
        "gsc_summary_display.v1", "gsc", "summary_display", "search_summary"
    ),
    "gsc_queries_display.v1": ReportingDatasetContract(
        "gsc_queries_display.v1",
        "gsc",
        "queries_display",
        "search_query_and_page",
        ("query_rows", "page_rows"),
    ),
}

CANONICAL_SECTION_SOURCE_MATRIX = {
    "ga4_top_metrics": ("ga4_metric_display.v1", "metric_cards"),
    "ga4_website_traffic_trends": ("ga4_metric_display.v1", "trend_charts"),
    "ga4_channel_performance": ("ga4_metric_display.v1", "breakdowns.top_traffic_channels"),
    "ga4_user_engagement": ("ga4_metric_display.v1", "metric_cards.engagement"),
    "ga4_top_sources": ("ga4_top_sources_display.v1", "rows.source_medium"),
    "ga4_top_landing_pages": ("ga4_top_landing_pages_display.v1", "rows.landing_page"),
    "ga4_most_viewed_pages": ("ga4_most_viewed_pages_display.v1", "rows.page_popularity"),
    "gsc_summary": ("gsc_summary_display.v1", "summary_metrics"),
    "gsc_top_queries": ("gsc_queries_display.v1", "query_rows"),
    "gsc_top_pages": ("gsc_queries_display.v1", "page_rows"),
}

SAFE_LEGACY_SECTION_ALIASES = {
    "ga4_traffic_trends": "ga4_website_traffic_trends",
    "ga4_traffic_channels": "ga4_channel_performance",
    "ga4_top_pages": "ga4_most_viewed_pages",
}

AMBIGUOUS_SECTION_IDENTIFIERS = {
    "traffic_trends",
    "traffic_channels",
    "top_pages",
    "landing_pages",
    "search_rows",
}


def canonical_dataset_contract(schema_version: str) -> ReportingDatasetContract | None:
    return CANONICAL_DATASET_CONTRACTS.get(schema_version)


def canonical_section_key(value: str) -> str | None:
    """Resolve one stored section key to its canonical identity.

    This is the single authoritative resolver for the importer. It mirrors the
    portal's ``canonical_reporting_section_key`` exactly, using the same alias
    map and the same ambiguous-key refusal, so both repositories agree on what
    a section *is*.

    Returns ``None`` for ambiguous keys, unknown keys, and helper sections that
    carry no canonical identity. Those are not canonical sections and therefore
    cannot collide with one.
    """
    normalized = str(value or "").strip()
    if normalized in CANONICAL_SECTION_SOURCE_MATRIX:
        return normalized
    if normalized in SAFE_LEGACY_SECTION_ALIASES:
        return SAFE_LEGACY_SECTION_ALIASES[normalized]
    return None


def detect_canonical_section_collisions(section_keys: list[str]) -> list[dict[str, object]]:
    """Find canonical identities claimed by more than one stored key.

    Deterministic in both identity order and claiming-key order, so the same
    input always produces the same refusal message. Mirrors the portal's
    accepted R8-C2 detector.
    """
    collisions: list[dict[str, object]] = []
    for canonical in CANONICAL_SECTION_SOURCE_MATRIX:
        claiming = sorted(key for key in section_keys if canonical_section_key(key) == canonical)
        if len(claiming) > 1:
            collisions.append({"canonical_section_key": canonical, "claiming_keys": claiming})
    return collisions
