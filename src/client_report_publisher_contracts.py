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
