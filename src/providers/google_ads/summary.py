from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.dashboard_lab.paid_callrail_fixture_builder import DEFAULT_CLIENT_LABEL, DEFAULT_PROFILE
from src.dashboard_lab.paid_callrail_validators import validate_google_ads_summary

from .normalize import build_summary_from_rows


def build_google_ads_summary_payload(
    *,
    profile: str,
    start_date: str,
    end_date: str,
    campaign_rows: list[dict[str, Any]],
    keyword_rows: list[dict[str, Any]],
    search_term_rows: list[dict[str, Any]],
    landing_page_rows: list[dict[str, Any]],
    time_series: list[dict[str, Any]],
    budget_pacing: dict[str, Any] | None = None,
    paid_search_call_signal: dict[str, Any] | None = None,
    source: str = "google_ads_api",
    is_real_data: bool = True,
    data_quality_notes: list[str] | None = None,
) -> dict[str, Any]:
    notes = list(data_quality_notes or [])
    if not budget_pacing:
        notes.append("Budget pacing deferred in the first read-only API pull.")
    payload = {
        "schema_version": "google_ads_summary.v1",
        "provider": "google_ads",
        "profile": profile,
        "client_label": _client_label_for_profile(profile),
        "source": source,
        "is_real_data": is_real_data,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "date_range": {"start_date": start_date, "end_date": end_date},
        "currency": "USD",
        "summary": build_summary_from_rows(campaign_rows or keyword_rows),
        "keyword_rows": keyword_rows,
        "search_term_rows": search_term_rows,
        "campaign_rows": campaign_rows,
        "landing_page_rows": landing_page_rows,
        "paid_search_call_signal": paid_search_call_signal or {},
        "budget_pacing": budget_pacing or {},
        "time_series": time_series,
        "data_quality_notes": notes,
    }
    validate_google_ads_summary(payload)
    return payload


def write_google_ads_summary(path: Path, payload: dict[str, Any]) -> None:
    validate_google_ads_summary(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    validate_google_ads_summary(json.loads(path.read_text(encoding="utf-8")))


def _client_label_for_profile(profile: str) -> str:
    if profile == DEFAULT_PROFILE:
        return DEFAULT_CLIENT_LABEL
    return profile.replace("-", " ").title()
