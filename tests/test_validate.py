from datetime import date

import pytest

from src.config import ConfigError, DateRange, default_date_range, parse_date_range
from src.normalize import normalize_traffic_overview
from src.snapshot_builder import build_traffic_overview_snapshot
from src.validate import ValidationError, inspect_snapshot_payload, validate_snapshot_payload
from tests.test_normalize import mocked_ga4_response


def valid_payload():
    return build_traffic_overview_snapshot(
        normalize_traffic_overview(mocked_ga4_response()),
        "properties/123456789",
        DateRange(date(2026, 4, 1), date(2026, 4, 30)),
    )


def test_default_date_range_uses_last_30_full_days():
    result = default_date_range(today=date(2026, 5, 20))

    assert result.start.isoformat() == "2026-04-20"
    assert result.end.isoformat() == "2026-05-19"


def test_parse_date_range_requires_both_dates():
    with pytest.raises(ConfigError):
        parse_date_range("2026-04-01", None)


def test_required_fields_validate():
    validate_snapshot_payload(valid_payload())


def test_invalid_or_raw_payloads_are_refused():
    payload = valid_payload()
    payload["raw_provider"] = {"rows": []}

    with pytest.raises(ValidationError):
        validate_snapshot_payload(payload)


def test_invalid_date_range_is_refused():
    payload = valid_payload()
    payload["date_range"] = {"start": "2026-04-30", "end": "2026-04-01"}

    with pytest.raises(ValidationError):
        validate_snapshot_payload(payload)


def test_inspection_counts_richer_rows_and_warnings():
    payload = valid_payload()
    payload["dimension_rows"] = [
        {"kind": "traffic_channels", "label": "Direct", "metrics": [{"name": "sessions", "value": 1, "unit": "count"}]},
        {"kind": "top_pages", "label": "/", "metrics": [{"name": "views", "value": 2, "unit": "count"}]},
    ]
    payload["warnings"] = ["Sparse data"]

    inspection = inspect_snapshot_payload(payload)

    assert inspection.schema_version == "ga4_snapshot.v1"
    assert inspection.channel_row_count == 1
    assert inspection.top_page_row_count == 1
    assert inspection.warning_count == 1
