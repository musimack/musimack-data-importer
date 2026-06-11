import json

from src.dashboard_lab.paid_callrail_fixture_builder import (
    build_paid_search_callrail_fixtures,
)
from src.dashboard_lab.paid_callrail_validators import (
    FORBIDDEN_CALLRAIL_KEYS,
    PHONE_PATTERN,
    validate_callrail_summary,
    validate_google_ads_summary,
)


def test_paid_search_callrail_builder_writes_both_files(tmp_path):
    result = build_paid_search_callrail_fixtures(
        profile="inn-at-spanish-head",
        output_root=tmp_path,
        start_date="2026-01-01",
        end_date="2026-05-31",
    )

    assert result.google_ads_path == tmp_path / "inn-at-spanish-head" / "google-ads-summary.json"
    assert result.callrail_path == tmp_path / "inn-at-spanish-head" / "callrail-summary.json"
    assert result.google_ads_path.exists()
    assert result.callrail_path.exists()


def test_generated_google_ads_summary_passes_validator(tmp_path):
    result = build_paid_search_callrail_fixtures(output_root=tmp_path)
    payload = json.loads(result.google_ads_path.read_text(encoding="utf-8"))

    validate_google_ads_summary(payload)

    assert payload["source"] == "synthetic_fixture"
    assert payload["is_real_data"] is False
    assert len(payload["keyword_rows"]) == 10
    assert len(payload["search_term_rows"]) == 10
    assert len(payload["campaign_rows"]) == 5
    assert len(payload["landing_page_rows"]) == 7
    assert payload["summary"]["spend"] > 0
    assert isinstance(payload["summary"]["ctr"], float)


def test_generated_callrail_summary_passes_validator_and_is_aggregate_only(tmp_path):
    result = build_paid_search_callrail_fixtures(output_root=tmp_path)
    payload = json.loads(result.callrail_path.read_text(encoding="utf-8"))

    validate_callrail_summary(payload)

    serialized = json.dumps(payload, sort_keys=True)
    assert payload["source"] == "synthetic_fixture"
    assert payload["is_real_data"] is False
    assert len(payload["keyword_rows"]) == 10
    assert len(payload["campaign_rows"]) == 5
    assert len(payload["landing_page_rows"]) == 7
    assert len(payload["missed_call_opportunities"]) == 4
    assert not _contains_forbidden_key(payload, FORBIDDEN_CALLRAIL_KEYS)
    assert not PHONE_PATTERN.search(serialized)


def test_paid_search_callrail_builder_is_deterministic(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = build_paid_search_callrail_fixtures(output_root=first_root)
    second = build_paid_search_callrail_fixtures(output_root=second_root)

    assert first.google_ads_path.read_text(encoding="utf-8") == second.google_ads_path.read_text(encoding="utf-8")
    assert first.callrail_path.read_text(encoding="utf-8") == second.callrail_path.read_text(encoding="utf-8")


def _contains_forbidden_key(value, forbidden):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden or _contains_forbidden_key(nested, forbidden):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False
