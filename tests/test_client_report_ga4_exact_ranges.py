import copy

import pytest

from src.client_report_ga4_exact_ranges import (
    GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
    display_data_for_section,
    validate_ga4_exact_range_summary_contract,
)


def test_valid_ga4_exact_range_summary_contract_passes():
    payload = _exact_payload()

    validate_ga4_exact_range_summary_contract(payload)

    last_7 = payload["ranges"][0]
    top_metrics = display_data_for_section(last_7, "ga4_top_metrics")
    engagement = display_data_for_section(last_7, "ga4_user_engagement")
    assert top_metrics["metrics"][0] == {"key": "users", "label": "Users", "value": "707"}
    assert any(metric["key"] == "average_engagement_time" for metric in engagement["metrics"])


def test_zero_values_and_missing_optional_values_survive():
    payload = _exact_payload()
    range_item = payload["ranges"][0]
    range_item["metrics"]["key_events"] = 0
    range_item["metrics"].pop("new_users")

    validate_ga4_exact_range_summary_contract(payload)
    top_metrics = display_data_for_section(range_item, "ga4_top_metrics")

    assert any(metric == {"key": "key_events", "label": "Key Events", "value": "0"} for metric in top_metrics["metrics"])
    assert not any(metric["key"] == "new_users" for metric in top_metrics["metrics"])


@pytest.mark.parametrize(
    "mutate,error",
    [
        (lambda p: p["ranges"][0]["metrics"].pop("users"), "missing required metric users"),
        (lambda p: p["ranges"][0]["metrics"].update({"sessions": "many"}), "metric value is invalid"),
        (lambda p: p["ranges"][0]["metrics"].update({"engagement_rate": 1.25}), "ratio metric is out of range"),
        (lambda p: p["ranges"][0]["metrics"].update({"average_engagement_time_seconds": 10.5}), "must be an integer"),
        (lambda p: p["ranges"][0].update({"data_state": "unavailable"}), "unavailable state contradicts coverage"),
        (lambda p: p["ranges"][0].update({"coverage_state": "partial"}), "available state requires complete passed coverage"),
        (lambda p: p["ranges"][0].update({"requested_start_date": "2026-07-03"}), "expected_date_count is inconsistent"),
        (lambda p: p.update({"dataset_version": "wrong.v1"}), "dataset_version is invalid"),
        (lambda p: p.update({"schema_version": "wrong.v1"}), "schema_version is unsupported"),
    ],
)
def test_invalid_ga4_exact_range_summary_contract_fails(mutate, error):
    payload = _exact_payload()
    mutate(payload)

    with pytest.raises(ValueError, match=error):
        validate_ga4_exact_range_summary_contract(payload)


def test_duplicate_range_identity_fails():
    payload = _exact_payload()
    payload["ranges"].append(copy.deepcopy(payload["ranges"][0]))

    with pytest.raises(ValueError, match="duplicate exact-range GA4 summary identity"):
        validate_ga4_exact_range_summary_contract(payload)


def test_partial_empty_and_unavailable_states_are_explicit():
    payload = _exact_payload()
    payload["ranges"] = [
        _range("last_7_days", "2026-07-02", "2026-07-08", users=0, sessions=0, views=0, engagement_rate=0.0),
        {
            **_range("last_30_days", "2026-06-09", "2026-07-08"),
            "data_state": "partial",
            "coverage_state": "partial",
            "quality_state": "partial",
            "actual_date_count": 20,
            "quality_notes": ["Synthetic partial coverage fixture."],
        },
        {
            "range_key": "this_month",
            "requested_start_date": "2026-07-01",
            "requested_end_date": "2026-07-08",
            "inclusive_dates": True,
            "data_state": "unavailable",
            "coverage_state": "unavailable",
            "quality_state": "unavailable",
            "expected_date_count": 8,
            "actual_date_count": 0,
            "metrics": {},
            "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
            "source_identity": "sample-client:this_month:2026-07-01:2026-07-08",
            "quality_notes": ["Synthetic unavailable fixture."],
        },
    ]
    payload["ranges"][0]["metrics"] = {
        key: 0 for key in payload["ranges"][0]["metrics"]
    }
    payload["ranges"][0]["data_state"] = "empty"
    payload["ranges"][0]["coverage_state"] = "empty"
    payload["ranges"][0]["quality_state"] = "empty"

    validate_ga4_exact_range_summary_contract(payload)


def _exact_payload():
    return {
        "schema_version": GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
        "provider": "ga4",
        "report_type": "metric_display_exact_ranges",
        "data_scope": "ga4_exact_range_summary",
        "dataset_version": GA4_EXACT_RANGE_SUMMARY_SCHEMA_VERSION,
        "client_slug": "synthetic-client",
        "report_period": {"start_date": "2026-01-01", "end_date": "2026-07-08"},
        "timezone": "America/Los_Angeles",
        "inclusive_dates": True,
        "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
        "generated_at": "2026-07-09T12:00:00Z",
        "source_identity": {
            "source_kind": "synthetic_fixture",
            "source_label": "Synthetic GA4 exact-range summary fixture",
        },
        "query_identity": {
            "shape_id": "ga4_summary_exact_range.synthetic.v1",
            "fingerprint": "synthetic-ga4-summary-v1",
        },
        "metric_definitions": [
            {"key": "users"},
            {"key": "new_users"},
            {"key": "sessions"},
            {"key": "views"},
            {"key": "engaged_sessions"},
            {"key": "engagement_rate"},
            {"key": "average_session_duration_seconds"},
            {"key": "average_engagement_time_seconds"},
            {"key": "event_count"},
            {"key": "key_events"},
            {"key": "conversions"},
        ],
        "ranges": [
            _range("last_7_days", "2026-07-02", "2026-07-08"),
            _range("last_30_days", "2026-06-09", "2026-07-08", users=3000, sessions=3500, views=7000),
        ],
    }


def _range(
    range_key,
    start,
    end,
    *,
    users=707,
    sessions=814,
    views=1401,
    engagement_rate=0.625,
):
    expected = {
        ("last_7_days", "2026-07-02", "2026-07-08"): 7,
        ("last_30_days", "2026-06-09", "2026-07-08"): 30,
        ("this_month", "2026-07-01", "2026-07-08"): 8,
        ("last_month", "2026-06-01", "2026-06-30"): 30,
    }.get((range_key, start, end), 7)
    return {
        "range_key": range_key,
        "requested_start_date": start,
        "requested_end_date": end,
        "inclusive_dates": True,
        "data_state": "available",
        "coverage_state": "complete",
        "quality_state": "passed",
        "expected_date_count": expected,
        "actual_date_count": expected,
        "metrics": {
            "users": users,
            "new_users": users - 100,
            "sessions": sessions,
            "views": views,
            "engaged_sessions": int(sessions * engagement_rate),
            "engagement_rate": engagement_rate,
            "average_engagement_time_seconds": 74,
            "average_session_duration_seconds": 118,
            "event_count": 2100,
            "key_events": 42,
            "conversions": 9,
        },
        "calculation_version": "ga4_summary_exact_ranges.synthetic.v1",
        "source_identity": f"synthetic-client:{range_key}:{start}:{end}",
        "quality_notes": ["Synthetic exact-range summary fixture."],
    }
