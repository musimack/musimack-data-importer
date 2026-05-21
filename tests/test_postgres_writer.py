from datetime import date

import pytest

from src.config import DateRange
from src.normalize import normalize_traffic_overview
from src.postgres_writer import import_snapshot
from src.snapshot_builder import build_traffic_overview_snapshot
from tests.test_normalize import mocked_ga4_response


def valid_payload():
    return build_traffic_overview_snapshot(
        normalize_traffic_overview(mocked_ga4_response()),
        "properties/123456789",
        DateRange(date(2026, 4, 1), date(2026, 4, 30)),
    )


def test_import_validates_before_db_write(monkeypatch):
    def fail_connect(*_args, **_kwargs):
        raise AssertionError("database should not be reached")

    monkeypatch.setattr("psycopg.connect", fail_connect)
    payload = valid_payload()
    payload["access_token"] = "not-real"

    with pytest.raises(ValueError):
        import_snapshot("postgresql://example", "00000000-0000-0000-0000-000000000000", payload)


def test_postgres_insert_sql_uses_internal_draft_conventions():
    source = __import__("src.postgres_writer", fromlist=["unused"])
    text = "\n".join(
        value
        for value in source.__dict__.values()
        if isinstance(value, str)
    )
    module_file = open(source.__file__, encoding="utf-8").read()

    assert "'internal', 'draft'" in module_file
    assert "project_report_snapshots" not in module_file
    assert "report_sections" not in module_file
    assert "project_integration_snapshots" in module_file
    assert "integration_sync_runs" in module_file
    assert "google_analytics" in text


def test_import_script_prints_portal_followup_reminder():
    script = open("scripts/import_ga4_snapshot.py", encoding="utf-8").read()

    assert "Initial visibility/status: internal/draft" in script
    assert "Portal follow-up required: link/preview/promote/set-active in the portal." in script
