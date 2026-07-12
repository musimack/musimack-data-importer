from __future__ import annotations

from copy import deepcopy

import pytest

from src.client_report_gsc_exact_range_provider import build_all_gsc_exact_ranges_from_provider


class FakeClient:
    def __init__(self): self.calls = []
    def query_exact_range_summary(self, start, end):
        self.calls.append(("summary", start, end)); return {"rows": [{"clicks": 20, "impressions": 200, "ctr": .1, "position": 4.5}]}
    def query_exact_range_queries(self, start, end):
        self.calls.append(("query", start, end)); return {"rows": [_row("query b", 5), _row("query a", 5), _row("query c", 2)]}
    def query_exact_range_pages(self, start, end):
        self.calls.append(("page", start, end)); return {"rows": [_row("https://example.test/b", 6), _row("https://example.test/a", 6)]}


def _row(label, clicks):
    return {"keys": [label], "clicks": clicks, "impressions": clicks * 10, "ctr": .1, "position": 3.2}


def test_provider_builds_three_contracts_and_twelve_complete_ranges():
    client = FakeClient()
    datasets = build_all_gsc_exact_ranges_from_provider(client, client_slug="aluma-seo-geo", report_start="2026-01-01", report_end="2026-07-08", available_through_date="2026-07-08")
    assert len(datasets) == 3
    assert len(client.calls) == 12
    assert all(len(payload["ranges"]) == 4 for payload in datasets.values())
    assert all(item["data_state"] == "available" for payload in datasets.values() for item in payload["ranges"])
    assert all(payload["calculation_version"] == "gsc_exact_ranges.provider.v1" for payload in datasets.values())
    assert all(payload["generation_metadata"]["provider_calls"] == 4 for payload in datasets.values())
    assert "synthetic" not in str(datasets).lower()


def test_provider_uses_dimensionless_query_and_distinct_ranked_scopes():
    client = FakeClient()
    datasets = build_all_gsc_exact_ranges_from_provider(client, client_slug="aluma-seo-geo", report_start="2026-01-01", report_end="2026-07-08", available_through_date="2026-07-08")
    summary = datasets["gsc_summary_exact_ranges.v1"]["ranges"][0]
    assert summary["summary_source"] == "provider_total_row_equivalent"
    assert summary["summary_metrics"] == {"clicks": 20, "impressions": 200, "ctr": .1, "average_position": 4.5}
    assert [row["query"] for row in datasets["gsc_top_queries_exact_ranges.v1"]["ranges"][0]["query_rows"]] == ["query a", "query b", "query c"]
    assert all("page" not in row for row in datasets["gsc_top_queries_exact_ranges.v1"]["ranges"][0]["query_rows"])
    assert all("query" not in row for row in datasets["gsc_top_pages_exact_ranges.v1"]["ranges"][0]["page_rows"])


def test_freshness_partial_is_truthful_and_uses_effective_end():
    client = FakeClient()
    datasets = build_all_gsc_exact_ranges_from_provider(client, client_slug="aluma-seo-geo", report_start="2026-01-01", report_end="2026-07-08", available_through_date="2026-07-06")
    assert all(payload["ranges"][0]["data_state"] == "partial" for payload in datasets.values())
    assert all(payload["ranges"][0]["actual_coverage_end_date"] == "2026-07-06" for payload in datasets.values())
    assert client.calls[0] == ("summary", "2026-07-02", "2026-07-06")


@pytest.mark.parametrize("method", ["summary", "query", "page"])
def test_provider_errors_propagate_and_are_not_empty(method):
    class Broken(FakeClient):
        def _fail(self, start, end): raise RuntimeError("sanitized provider failure")
    client = Broken()
    setattr(client, f"query_exact_range_{'queries' if method == 'query' else 'pages' if method == 'page' else 'summary'}", client._fail)
    with pytest.raises(RuntimeError, match="provider failure"):
        build_all_gsc_exact_ranges_from_provider(client, client_slug="aluma-seo-geo", report_start="2026-01-01", report_end="2026-07-08", available_through_date="2026-07-08")


def test_malformed_provider_rows_fail_closed():
    client = FakeClient()
    client.query_exact_range_summary = lambda start, end: {"rows": [{"clicks": "bad"}]}
    with pytest.raises(ValueError, match="malformed"):
        build_all_gsc_exact_ranges_from_provider(client, client_slug="aluma-seo-geo", report_start="2026-01-01", report_end="2026-07-08", available_through_date="2026-07-08")
