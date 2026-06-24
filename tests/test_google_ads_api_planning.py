from src.providers.google_ads.normalize import (
    build_summary_from_rows,
    micros_to_currency,
    normalize_campaign_rows,
    normalize_campaign_time_series,
    normalize_ctr,
    normalize_keyword_rows,
    normalize_landing_page_rows,
    normalize_landing_page_url,
    normalize_search_term_rows,
    normalize_time_series,
)
from src.providers.google_ads.queries import (
    build_budget_pacing_query,
    build_campaign_performance_query,
    build_keyword_performance_query,
    build_landing_page_performance_query,
    build_search_term_performance_query,
    build_time_series_query,
)


def test_campaign_query_includes_expected_read_only_fields_and_date_range():
    query = build_campaign_performance_query("2026-01-01", "2026-05-31")

    assert "campaign.id" in query
    assert "campaign.name" in query
    assert "campaign.status" in query
    assert "metrics.impressions" in query
    assert "metrics.clicks" in query
    assert "metrics.cost_micros" in query
    assert "metrics.conversions" in query
    assert "segments.date BETWEEN '2026-01-01' AND '2026-05-31'" in query
    _assert_no_mutation_language(query)


def test_keyword_query_includes_keyword_text_and_match_type():
    query = build_keyword_performance_query("2026-01-01", "2026-05-31")

    assert "FROM keyword_view" in query
    assert "ad_group_criterion.keyword.text" in query
    assert "ad_group_criterion.keyword.match_type" in query
    assert "ad_group_criterion.type = KEYWORD" in query
    _assert_no_mutation_language(query)


def test_search_term_query_includes_search_term_view():
    query = build_search_term_performance_query("2026-01-01", "2026-05-31")

    assert "FROM search_term_view" in query
    assert "search_term_view.search_term" in query
    assert "search_term_view.status" in query
    assert "campaign.name" in query
    assert "ad_group.name" in query
    assert "segments.keyword.info.text" in query
    assert "segments.keyword.info.match_type" in query
    assert "ad_group_criterion" not in query
    _assert_no_mutation_language(query)


def test_landing_page_query_uses_landing_page_reporting_view():
    query = build_landing_page_performance_query("2026-01-01", "2026-05-31")

    assert "FROM expanded_landing_page_view" in query
    assert "expanded_landing_page_view.expanded_final_url" in query
    assert "segments.date BETWEEN '2026-01-01' AND '2026-05-31'" in query
    _assert_no_mutation_language(query)


def test_time_series_and_budget_queries_include_reporting_dimensions():
    time_query = build_time_series_query("2026-01-01", "2026-05-31")
    budget_query = build_budget_pacing_query("2026-01-01", "2026-05-31")

    assert "segments.date" in time_query
    assert "campaign.name" in time_query
    assert "metrics.cost_micros" in time_query
    assert "campaign_budget.amount_micros" in budget_query
    assert "campaign.status" in budget_query
    _assert_no_mutation_language(time_query)
    _assert_no_mutation_language(budget_query)


def test_micros_and_ctr_normalizers_return_numeric_values():
    assert micros_to_currency(1_234_567) == 1.234567
    assert micros_to_currency("2500000") == 2.5
    assert normalize_ctr(0.1234) == 0.1234
    assert normalize_ctr("12.5%") == 0.125


def test_landing_page_normalizer_strips_query_strings_and_fragments():
    assert normalize_landing_page_url("https://spanishhead.com/landing-page/?utm=abc#top") == "/landing-page/"
    assert normalize_landing_page_url("/rooms?gclid=not-output") == "/rooms"


def test_campaign_rows_normalize_to_contract_friendly_aggregate_rows():
    rows = normalize_campaign_rows(
        [
            {
                "campaign": {"name": "Brand"},
                "metrics": {
                    "impressions": 100,
                    "clicks": 10,
                    "cost_micros": 2_500_000,
                    "conversions": 3.5,
                    "average_cpc": 250_000,
                    "ctr": 0.1,
                },
                "gclid": "must-not-leak",
            }
        ]
    )

    assert rows == [
        {
            "campaign": "Brand",
            "spend": 2.5,
            "impressions": 100,
            "clicks": 10,
            "ctr": 0.1,
            "avg_cpc": 0.25,
            "conversions": 3.5,
        }
    ]
    assert "gclid" not in rows[0]


def test_keyword_rows_normalize_keyword_metrics_and_landing_page():
    rows = normalize_keyword_rows(
        [
            {
                "campaign.name": "Rooms",
                "ad_group_criterion.keyword.text": "oceanfront hotel",
                "ad_group_criterion.keyword.match_type": "EXACT",
                "metrics.impressions": 200,
                "metrics.clicks": 20,
                "metrics.cost_micros": 5_000_000,
                "metrics.conversions": 4,
                "landing_page": "https://spanishhead.com/rooms/?utm=abc",
                "calls": 5,
                "click_id": "must-not-leak",
            }
        ]
    )

    assert rows == [
        {
            "keyword": "oceanfront hotel",
            "campaign": "Rooms",
            "match_type": "EXACT",
            "impressions": 200,
            "clicks": 20,
            "ctr": 0.1,
            "avg_cpc": 0.25,
            "cost": 5.0,
            "conversions": 4.0,
            "calls": 5,
            "cost_per_call": 1.0,
            "landing_page": "/rooms/",
        }
    ]
    assert "click_id" not in rows[0]


def test_search_term_landing_page_and_time_series_rows_normalize():
    search_terms = normalize_search_term_rows(
        [
            {
                "search_term_view": {"search_term": "best oceanfront hotel"},
                "campaign": {"name": "Rooms"},
                "segments": {"keyword": {"info": {"text": "oceanfront hotel", "match_type": "EXACT"}}},
                "metrics": {"impressions": 80, "clicks": 8, "cost_micros": 1_600_000, "conversions": 1, "ctr": 0.1},
            }
        ]
    )
    landing_pages = normalize_landing_page_rows(
        [
            {
                "expanded_landing_page_view": {"expanded_final_url": "https://spanishhead.com/offers/?utm=abc"},
                "campaign": {"name": "Deals"},
                "metrics": {"impressions": 50, "clicks": 5, "cost_micros": 1_000_000, "conversions": 2, "ctr": 0.1},
                "calls": 4,
            }
        ]
    )
    time_series = normalize_time_series(
        [
            {
                "segments": {"date": "2026-01-01"},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_000_000, "conversions": 3},
            }
        ]
    )

    assert search_terms[0]["search_term"] == "best oceanfront hotel"
    assert search_terms[0]["matched_keyword"] == "oceanfront hotel"
    assert landing_pages[0]["landing_page"] == "/offers/"
    assert landing_pages[0]["cost_per_call"] == 0.25
    assert time_series == [
        {"date": "2026-01-01", "spend": 2.0, "clicks": 10, "impressions": 100, "conversions": 3.0}
    ]


def test_time_series_rows_aggregate_duplicate_campaign_dates():
    time_series = normalize_time_series(
        [
            {
                "segments": {"date": "2026-01-02"},
                "metrics": {"impressions": 20, "clicks": 2, "cost_micros": 2_000_000, "conversions": 0.5},
                "campaign": {"name": "Second campaign name should not be kept"},
            },
            {
                "segments": {"date": "2026-01-01"},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_500_000, "conversions": 1.25},
                "interactions": 11,
                "calls": 3,
            },
            {
                "segments": {"date": "2026-01-01"},
                "metrics": {"impressions": 50, "clicks": 5, "cost_micros": 1_250_000, "conversions": 2.75},
                "interactions": 6,
                "calls": 2,
                "form_fills": 1,
                "tracked_leads": 3,
                "campaign": {"name": "Brand campaign name should not be kept"},
            },
            {
                "date": "2026-01-01",
                "spend": 0.5,
                "impressions": 25,
                "clicks": 3,
                "conversions": 1,
            },
        ]
    )

    assert time_series == [
        {
            "date": "2026-01-01",
            "spend": 4.25,
            "clicks": 18,
            "impressions": 175,
            "conversions": 5.0,
            "interactions": 17,
            "tracked_calls": 5,
            "form_fills": 1,
            "tracked_leads": 3,
        },
        {"date": "2026-01-02", "spend": 2.0, "clicks": 2, "impressions": 20, "conversions": 0.5},
    ]
    assert all("campaign" not in row for row in time_series)
    assert len({row["date"] for row in time_series}) == len(time_series)


def test_campaign_time_series_rows_aggregate_duplicate_campaign_dates():
    campaign_time_series = normalize_campaign_time_series(
        [
            {
                "segments": {"date": "2026-01-02"},
                "campaign": {"name": "Rooms"},
                "metrics": {"impressions": 20, "clicks": 2, "cost_micros": 2_000_000, "conversions": 0.5},
            },
            {
                "segments": {"date": "2026-01-01"},
                "campaign": {"name": "Brand"},
                "metrics": {"impressions": 100, "clicks": 10, "cost_micros": 2_500_000, "conversions": 1.25},
                "interactions": 11,
                "calls": 3,
                "campaign_id": "must-not-leak",
            },
            {
                "segments": {"date": "2026-01-01"},
                "campaign": {"name": "Brand"},
                "metrics": {"impressions": 50, "clicks": 5, "cost_micros": 1_250_000, "conversions": 2.75},
                "interactions": 6,
                "calls": 2,
                "form_fills": 1,
                "tracked_leads": 3,
            },
            {
                "date": "2026-01-01",
                "campaign": "Rooms",
                "spend": 0.5,
                "impressions": 25,
                "clicks": 3,
                "conversions": 1,
            },
        ]
    )

    assert campaign_time_series == [
        {
            "date": "2026-01-01",
            "campaign": "Brand",
            "spend": 3.75,
            "clicks": 15,
            "impressions": 150,
            "conversions": 4.0,
            "interactions": 17,
            "tracked_calls": 5,
            "form_fills": 1,
            "tracked_leads": 3,
        },
        {
            "date": "2026-01-01",
            "campaign": "Rooms",
            "spend": 0.5,
            "clicks": 3,
            "impressions": 25,
            "conversions": 1.0,
        },
        {"date": "2026-01-02", "campaign": "Rooms", "spend": 2.0, "clicks": 2, "impressions": 20, "conversions": 0.5},
    ]
    assert all("campaign_id" not in row for row in campaign_time_series)
    assert len({(row["campaign"], row["date"]) for row in campaign_time_series}) == len(campaign_time_series)


def test_search_term_rows_tolerate_missing_keyword_segment_fields():
    rows = normalize_search_term_rows(
        [
            {
                "search_term_view": {"search_term": "best oceanfront hotel"},
                "campaign": {"name": "Rooms"},
                "metrics": {"impressions": 80, "clicks": 8, "cost_micros": 1_600_000, "conversions": 1, "ctr": 0.1},
            }
        ]
    )

    assert rows == [
        {
            "search_term": "best oceanfront hotel",
            "campaign": "Rooms",
            "impressions": 80,
            "clicks": 8,
            "ctr": 0.1,
            "cost": 1.6,
            "conversions": 1.0,
        }
    ]


def test_summary_builds_totals_from_normalized_rows():
    summary = build_summary_from_rows(
        [
            {"cost": 5.0, "clicks": 20, "impressions": 200, "conversions": 4, "calls": 5},
            {"cost": 3.0, "clicks": 10, "impressions": 100, "conversions": 1, "calls": 3},
        ]
    )

    assert summary == {
        "spend": 8.0,
        "clicks": 30,
        "impressions": 300,
        "ctr": 0.1,
        "avg_cpc": 0.266667,
        "conversions": 5.0,
        "cost_per_conversion": 1.6,
        "calls": 8,
        "cost_per_call": 1.0,
    }


def _assert_no_mutation_language(query: str) -> None:
    lowered = query.lower()
    for forbidden in (" mutate ", " update ", " remove ", " create ", "operations", " set "):
        assert forbidden not in f" {lowered} "
