from datetime import date

import pytest

from scripts.process_portal_custom_exact_range_request import SafeWorkerError, _extract_count, _validate_request


def request(**overrides):
    value = {
        "request_state": "queued",
        "profile_key": "aluma-seo-geo",
        "timezone": "America/Los_Angeles",
        "contract_id": "client_report_presentation_ranges",
        "contract_version": "v2",
        "dataset_version": "custom_exact_range.v1",
        "source_fingerprint": "aluma-seo-geo:ga4-gsc:v1",
        "status": "draft",
        "published_at": None,
        "period_start": date(2025, 1, 1),
        "period_end": date(2026, 7, 8),
        "requested_start": date(2026, 6, 9),
        "requested_end": date(2026, 6, 30),
    }
    value.update(overrides)
    return value


def test_request_validation_accepts_only_authorized_draft_identity():
    _validate_request(request())
    with pytest.raises(SafeWorkerError):
        _validate_request(request(profile_key="another-profile"))
    with pytest.raises(SafeWorkerError):
        _validate_request(request(status="published"))
    with pytest.raises(SafeWorkerError):
        _validate_request(request(requested_start=date(2024, 12, 31)))


def test_safe_provider_counts_are_extracted_without_echoing_output():
    assert _extract_count("GA4 Data API calls: 4; reused ranges: 1.", "API calls") == 4
    assert _extract_count("provider calls: 3; reused ranges: 0", "provider calls") == 3
    assert _extract_count("no count", "provider calls") is None
