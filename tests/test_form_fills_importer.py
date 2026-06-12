from __future__ import annotations

import json
from datetime import date

import pytest

from src.dashboard_lab.form_fills import (
    FormFillsImportError,
    build_form_fills_summary_payload,
    import_form_fills_dates,
    read_form_fill_dates,
    validate_form_fills_summary,
)
from src.dashboard_lab.paid_callrail_validators import DashboardLabFixtureValidationError


def test_date_only_csv_import_writes_aggregate_summary(tmp_path):
    input_path = tmp_path / "inputs" / "form-fills.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        "\n".join(
            [
                "date",
                "2026-04-11",
                "2026-05-12",
                "2026-05-16",
                "2026-05-26",
                "2026-06-11",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output_root = tmp_path / "exports" / "local-real" / "dashboard-lab"
    result = import_form_fills_dates(
        profile="wc-land-renewal",
        input_path=input_path,
        output_root=output_root,
        real_output=False,
    )

    assert result.total_form_fills == 5
    assert result.date_count == 5
    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    validate_form_fills_summary(payload)
    assert payload["schema_version"] == "form_fills_summary.v1"
    assert payload["provider"] == "form_fills"
    assert payload["source_type"] == "date_only_local_real"
    assert payload["is_real_data"] is True
    assert payload["date_range"] == {"start_date": "2026-04-11", "end_date": "2026-06-11"}
    assert payload["summary"]["total_form_fills"] == 5
    assert payload["time_series"] == [
        {"date": "2026-04-11", "form_fills": 1},
        {"date": "2026-05-12", "form_fills": 1},
        {"date": "2026-05-16", "form_fills": 1},
        {"date": "2026-05-26", "form_fills": 1},
        {"date": "2026-06-11", "form_fills": 1},
    ]
    assert payload["monthly_totals"] == [
        {"month": "2026-04", "form_fills": 1},
        {"month": "2026-05", "form_fills": 3},
        {"month": "2026-06", "form_fills": 1},
    ]
    serialized = json.dumps(payload).lower()
    assert "@" not in serialized
    assert "503-555" not in serialized


def test_rejects_csv_with_pii_columns(tmp_path):
    input_path = tmp_path / "form-fills.csv"
    input_path.write_text("date,email\n2026-04-11,test@example.com\n", encoding="utf-8")

    with pytest.raises(FormFillsImportError, match="forbidden PII columns"):
        read_form_fill_dates(input_path)


def test_rejects_json_with_pii_values(tmp_path):
    input_path = tmp_path / "form-fills.json"
    input_path.write_text(json.dumps({"dates": ["2026-04-11"], "email": "test@example.com"}), encoding="utf-8")

    with pytest.raises(DashboardLabFixtureValidationError, match="forbidden form-fill detail key"):
        read_form_fill_dates(input_path)


def test_validator_rejects_pii_values_in_summary():
    payload = build_form_fills_summary_payload(
        profile="wc-land-renewal",
        dates=[date(2026, 4, 11)],
        generated_at="2026-06-12T00:00:00Z",
    )
    payload["label"] = "Call 503-555-0199"

    with pytest.raises(DashboardLabFixtureValidationError, match="phone-number-looking value"):
        validate_form_fills_summary(payload)


def test_validator_requires_time_series_total_to_match_summary():
    payload = build_form_fills_summary_payload(
        profile="wc-land-renewal",
        dates=[date(2026, 4, 11), date(2026, 4, 11)],
        generated_at="2026-06-12T00:00:00Z",
    )
    payload["summary"]["total_form_fills"] = 3

    with pytest.raises(DashboardLabFixtureValidationError, match="time_series total"):
        validate_form_fills_summary(payload)
