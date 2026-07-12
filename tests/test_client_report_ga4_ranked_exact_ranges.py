import copy

import pytest

from src.client_report_ga4_ranked_exact_ranges import (
    RANKED_EXACT_RANGE_SOURCE_BY_SECTION,
    build_fake_ga4_ranked_exact_range_dataset,
    display_data_for_ranked_section,
    exact_ranked_range_entry_for,
    validate_ga4_ranked_exact_range_contract,
)


PERIOD = {"start": "2026-01-01", "end": "2026-07-08"}


@pytest.mark.parametrize(
    ("section_key", "expected_schema"),
    sorted(RANKED_EXACT_RANGE_SOURCE_BY_SECTION.items()),
)
def test_fake_ranked_exact_range_contracts_validate_and_render(section_key, expected_schema):
    payload = build_fake_ga4_ranked_exact_range_dataset(
        section_key=section_key,
        client_slug="sample-client",
        period=PERIOD,
    )

    assert payload["schema_version"] == expected_schema
    assert payload["section_key"] == section_key
    assert [item["range_key"] for item in payload["ranges"]] == [
        "last_7_days",
        "last_30_days",
        "this_month",
        "last_month",
    ]
    validate_ga4_ranked_exact_range_contract(payload)

    entry = exact_ranked_range_entry_for(
        payload,
        range_key="last_7_days",
        start_date="2026-07-02",
        end_date="2026-07-08",
    )
    display = display_data_for_ranked_section(entry, section_key)

    assert display is not None
    assert len(display["rows"]) == 3
    assert display["rows"][0]["rank"] == 1
    assert display["rows"][0]["metrics"]


def test_ranked_exact_range_contracts_reject_cross_section_scope_substitution():
    sources = build_fake_ga4_ranked_exact_range_dataset(
        section_key="ga4_top_sources",
        client_slug="sample-client",
        period=PERIOD,
    )
    landing = build_fake_ga4_ranked_exact_range_dataset(
        section_key="ga4_top_landing_pages",
        client_slug="sample-client",
        period=PERIOD,
    )

    substituted = copy.deepcopy(sources)
    substituted["ranges"][0]["rows"][0] = copy.deepcopy(landing["ranges"][0]["rows"][0])

    with pytest.raises(ValueError, match="missing required dimension field|mismatched section scope"):
        validate_ga4_ranked_exact_range_contract(substituted)

    wrong_section = copy.deepcopy(sources)
    wrong_section["section_key"] = "ga4_top_landing_pages"
    with pytest.raises(ValueError, match="section_key"):
        validate_ga4_ranked_exact_range_contract(wrong_section)
