from src.client_report_publisher_contracts import (
    AMBIGUOUS_SECTION_IDENTIFIERS,
    CANONICAL_DATASET_CONTRACTS,
    CANONICAL_SECTION_SOURCE_MATRIX,
    SAFE_LEGACY_SECTION_ALIASES,
)


def test_canonical_contract_inventory_covers_ten_distinct_sections():
    assert len(CANONICAL_DATASET_CONTRACTS) == 6
    assert len(CANONICAL_SECTION_SOURCE_MATRIX) == 10
    assert len(set(CANONICAL_SECTION_SOURCE_MATRIX)) == 10
    assert all(
        dataset in CANONICAL_DATASET_CONTRACTS
        for dataset, _scope in CANONICAL_SECTION_SOURCE_MATRIX.values()
    )


def test_safe_legacy_section_aliases_are_explicit_and_unambiguous():
    assert SAFE_LEGACY_SECTION_ALIASES == {
        "ga4_traffic_trends": "ga4_website_traffic_trends",
        "ga4_traffic_channels": "ga4_channel_performance",
        "ga4_top_pages": "ga4_most_viewed_pages",
    }
    assert not set(SAFE_LEGACY_SECTION_ALIASES).intersection(AMBIGUOUS_SECTION_IDENTIFIERS)
    assert all(
        canonical in CANONICAL_SECTION_SOURCE_MATRIX
        for canonical in SAFE_LEGACY_SECTION_ALIASES.values()
    )


def test_semantically_distinct_sections_require_distinct_scopes():
    assert CANONICAL_SECTION_SOURCE_MATRIX["ga4_top_sources"] != CANONICAL_SECTION_SOURCE_MATRIX[
        "ga4_top_landing_pages"
    ]
    assert CANONICAL_SECTION_SOURCE_MATRIX[
        "ga4_top_landing_pages"
    ] != CANONICAL_SECTION_SOURCE_MATRIX["ga4_most_viewed_pages"]
    assert CANONICAL_SECTION_SOURCE_MATRIX["gsc_top_queries"][1] == "query_rows"
    assert CANONICAL_SECTION_SOURCE_MATRIX["gsc_top_pages"][1] == "page_rows"
