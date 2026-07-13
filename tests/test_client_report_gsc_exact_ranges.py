from __future__ import annotations

from copy import deepcopy

import pytest

from src.client_report_gsc_exact_ranges import (
    GSC_EXACT_RANGE_CONTRACTS,
    build_fake_gsc_exact_range_dataset,
    display_data_for_section,
    validate_gsc_exact_range_contract,
)


@pytest.mark.parametrize("schema", GSC_EXACT_RANGE_CONTRACTS)
def test_fake_contracts_have_four_exact_ranges(schema):
    payload = build_fake_gsc_exact_range_dataset(schema)
    validate_gsc_exact_range_contract(payload)
    assert [item["range_key"] for item in payload["ranges"]] == [
        "last_7_days", "last_30_days", "this_month", "last_month"
    ]
    assert all(item["data_state"] == "available" for item in payload["ranges"])
    assert payload["generation_metadata"]["provider_calls"] == 0
    assert payload["sanitized_source_metadata"]["contains_real_data"] is False


def test_summary_is_total_level_and_formats_ctr():
    payload = build_fake_gsc_exact_range_dataset("gsc_summary_exact_ranges.v1")
    entry = payload["ranges"][0]
    assert entry["summary_source"] == "provider_total_row_equivalent"
    assert "query_rows" not in entry and "page_rows" not in entry
    display = display_data_for_section(entry, "gsc_summary")
    assert display["metrics"][2]["value"].endswith("%")
    assert display["metrics"][2]["value"].count(".") == 1


@pytest.mark.parametrize("schema,wrong_key", [
    ("gsc_top_queries_exact_ranges.v1", "page"),
    ("gsc_top_pages_exact_ranges.v1", "query"),
])
def test_ranked_scopes_cannot_substitute(schema, wrong_key):
    payload = build_fake_gsc_exact_range_dataset(schema)
    contract = GSC_EXACT_RANGE_CONTRACTS[schema]
    payload["ranges"][0][contract.row_field][0][wrong_key] = "wrong scope"
    with pytest.raises(ValueError, match="wrong scope"):
        validate_gsc_exact_range_contract(payload)


@pytest.mark.parametrize("mutation,error", [
    (lambda p: p["ranges"][0]["summary_metrics"].__setitem__("ctr", .99), "CTR"),
    (lambda p: p["ranges"][0]["summary_metrics"].__setitem__("average_position", -1), "average_position"),
    (lambda p: p["ranges"][0]["summary_metrics"].__setitem__("clicks", 999999), "contradictory"),
    (lambda p: p["ranges"][0].__setitem__("summary_source", "ranked_rows"), "total-level"),
    (lambda p: p["ranges"].append(deepcopy(p["ranges"][0])), "duplicate"),
    (lambda p: p["ranges"][0].__setitem__("requested_end_date", "2026-07-09"), "dates"),
])
def test_invalid_summary_cases_fail(mutation, error):
    payload = build_fake_gsc_exact_range_dataset("gsc_summary_exact_ranges.v1")
    mutation(payload)
    with pytest.raises(ValueError, match=error):
        validate_gsc_exact_range_contract(payload)


def test_partial_empty_and_unavailable_are_distinct():
    partial = build_fake_gsc_exact_range_dataset("gsc_summary_exact_ranges.v1")
    entry = partial["ranges"][0]
    entry.update(data_state="partial", coverage_state="partial", freshness_state="partial",
                 available_through_date="2026-07-06", actual_coverage_end_date="2026-07-06")
    validate_gsc_exact_range_contract(partial)

    empty = build_fake_gsc_exact_range_dataset("gsc_top_queries_exact_ranges.v1")
    entry = empty["ranges"][0]
    entry.update(data_state="empty", coverage_state="empty", freshness_state="complete", query_rows=[])
    validate_gsc_exact_range_contract(empty)

    unavailable = build_fake_gsc_exact_range_dataset("gsc_top_pages_exact_ranges.v1")
    entry = unavailable["ranges"][0]
    entry.update(data_state="unavailable", coverage_state="unavailable", freshness_state="unavailable",
                 page_rows=[], available_through_date=None, actual_coverage_start_date=None,
                 actual_coverage_end_date=None, quality_state="unavailable")
    validate_gsc_exact_range_contract(unavailable)


@pytest.mark.parametrize(
    "schema,section_key,content_key",
    [
        ("gsc_summary_exact_ranges.v1", "gsc_summary", "metrics"),
        ("gsc_top_queries_exact_ranges.v1", "gsc_top_queries", "queries"),
        ("gsc_top_pages_exact_ranges.v1", "gsc_top_pages", "pages"),
    ],
)
def test_partial_exact_ranges_keep_displayable_provider_data(schema, section_key, content_key):
    payload = build_fake_gsc_exact_range_dataset(schema)
    entry = payload["ranges"][0]
    entry.update(
        data_state="partial",
        coverage_state="partial",
        freshness_state="partial",
        available_through_date="2026-07-06",
        actual_coverage_end_date="2026-07-06",
    )

    validate_gsc_exact_range_contract(payload)
    display = display_data_for_section(entry, section_key)

    assert isinstance(display, dict)
    assert display[content_key]


@pytest.mark.parametrize("schema", ["gsc_top_queries_exact_ranges.v1", "gsc_top_pages_exact_ranges.v1"])
def test_ranked_duplicate_unsorted_and_limit_fail(schema):
    contract = GSC_EXACT_RANGE_CONTRACTS[schema]
    payload = build_fake_gsc_exact_range_dataset(schema)
    rows = payload["ranges"][0][contract.row_field]
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_gsc_exact_range_contract(payload)
    payload = build_fake_gsc_exact_range_dataset(schema)
    payload["ranges"][0][contract.row_field].reverse()
    with pytest.raises(ValueError, match="sorted"):
        validate_gsc_exact_range_contract(payload)
    payload = build_fake_gsc_exact_range_dataset(schema)
    payload["ranges"][0][contract.row_field] *= 4
    with pytest.raises(ValueError, match="limit"):
        validate_gsc_exact_range_contract(payload)
