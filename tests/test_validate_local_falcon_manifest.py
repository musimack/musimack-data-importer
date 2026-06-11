from pathlib import Path

from scripts.validate_local_falcon_manifest import validate_manifest


def test_manifest_validator_allows_pending_google_ai_overview_prompts():
    payload = {
        "profile": "inn-at-spanish-head",
        "reports": [
            {
                "source": "Google Maps",
                "keyword": "demo local hotel",
                "report_id": "map-report-1",
            },
            {
                "source": "ChatGPT",
                "keyword": "demo AI visibility prompt",
                "report_id": "chatgpt-report-1",
            },
        ],
        "planned_or_in_progress_sources": [
            {
                "source": "Google AI Overview",
                "keyword": "demo pending AI overview prompt",
                "status": "pending",
            }
        ],
    }

    result = validate_manifest(
        payload,
        profile="inn-at-spanish-head",
        manifest_path=Path("local/inn-at-spanish-head/local-falcon/report-manifest.json"),
    )

    assert result.safe_to_process is True
    assert result.report_count == 2
    assert result.report_source_counts["Google Maps"] == 1
    assert result.report_source_counts["ChatGPT"] == 1
    assert result.google_ai_overview_pending_prompts == 1
    assert result.planned_missing_report_ids == 1
    assert result.errors == []


def test_manifest_validator_rejects_duplicate_existing_report_ids():
    payload = {
        "profile": "inn-at-spanish-head",
        "reports": [
            {
                "source": "Google Maps",
                "keyword": "demo local hotel",
                "report_id": "duplicate-report",
            },
            {
                "source": "ChatGPT",
                "keyword": "demo AI visibility prompt",
                "report_id": "duplicate-report",
            },
        ],
    }

    result = validate_manifest(
        payload,
        profile="inn-at-spanish-head",
        manifest_path=Path("local/inn-at-spanish-head/local-falcon/report-manifest.json"),
    )

    assert result.safe_to_process is False
    assert result.duplicate_report_ids == 1
    assert "duplicate report IDs found" in result.errors


def test_manifest_validator_rejects_duplicate_source_query_pairs():
    payload = {
        "profile": "inn-at-spanish-head",
        "reports": [
            {
                "source": "Google Maps",
                "keyword": "demo local hotel",
                "report_id": "report-1",
            },
            {
                "source": "Google Maps",
                "keyword": "demo local hotel",
                "report_id": "report-2",
            },
        ],
    }

    result = validate_manifest(
        payload,
        profile="inn-at-spanish-head",
        manifest_path=Path("local/inn-at-spanish-head/local-falcon/report-manifest.json"),
    )

    assert result.safe_to_process is False
    assert result.duplicate_source_query_pairs == 1
    assert "duplicate source/query pairs found" in result.errors
