import json
import subprocess
import sys
from pathlib import Path

from scripts.import_local_falcon_raw_api import import_raw_api_directory
from src.local_falcon_importer import validate_local_falcon_summary


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_local_falcon_raw_api.py"


def test_raw_api_importer_normalizes_maps_and_ai_visibility(tmp_path):
    raw_dir = tmp_path / ".test-tmp-local-falcon-raw"
    raw_dir.mkdir()
    _write_raw_file(raw_dir / "report-001.json", _maps_raw_payload())
    _write_raw_file(raw_dir / "report-002.json", _ai_raw_payload())
    output = tmp_path / ".test-tmp-local-falcon-output" / "local-falcon-summary.json"

    result = import_raw_api_directory(
        profile="inn-at-spanish-head",
        raw_dir=raw_dir,
        output_path=output,
        overwrite=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    scans = payload["keyword_scans"]

    assert result.raw_file_count == 2
    assert result.google_maps_keyword_scan_count == 1
    assert result.ai_visibility_record_count == 1
    assert result.google_maps_grid_present is True
    assert result.chatgpt_ai_visibility_present is True
    assert payload["source_type"] == "api_local_real"
    assert payload["real_data"] is True
    assert payload["fixture_profile"] == "inn-at-spanish-head"
    assert [scan["source_id"] for scan in scans] == ["google_maps", "chatgpt"]

    maps_scan = scans[0]
    assert maps_scan["query_type"] == "map_keyword"
    assert maps_scan["keyword"] == "synthetic oceanfront hotel"
    assert maps_scan["data_points"] == {
        "total": 4,
        "found": 3,
        "top_3": 1,
        "top_10": 2,
        "top_20": 3,
        "not_found_or_20_plus": 1,
    }
    assert maps_scan["rendered_grid"] == {"rows": 2, "columns": 2}
    assert maps_scan["local_falcon_metrics"] == {"arp": 7.5, "atrp": 9.0, "solv": 24.5}
    assert any(item["relationship"] == "client" for item in maps_scan["competitors"])

    ai_scan = scans[1]
    assert ai_scan["query_type"] == "ai_visibility_prompt"
    assert ai_scan["prompt"] == "synthetic private ai prompt"
    assert ai_scan["competitors"] == []
    assert ai_scan["ai_visibility_points"][0]["observation_sequence"] == 1
    assert ai_scan["brand_observations"][0]["relationship"] == "client"
    assert ai_scan["brand_phrases"][0]["phrase"] == "trusted oceanfront lodging"
    assert ai_scan["ai_visibility_sources"] == [
        {
            "source": "synthetic source",
            "title": "Synthetic citation",
            "link": "https://example.invalid/synthetic",
            "count": 2,
        }
    ]

    validation = validate_local_falcon_summary(payload, output)
    assert validation.keyword_scan_count == 2
    assert not any("data point counts" in warning for warning in validation.warnings)
    assert not any("brand observations" in warning for warning in validation.warnings)


def test_raw_api_importer_cli_prints_only_safe_aggregate_metadata(tmp_path):
    raw_dir = tmp_path / ".test-tmp-local-falcon-raw"
    raw_dir.mkdir()
    _write_raw_file(raw_dir / "report-001.json", _maps_raw_payload())
    _write_raw_file(raw_dir / "report-002.json", _ai_raw_payload())
    output = tmp_path / ".test-tmp-local-falcon-output" / "local-falcon-summary.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            "inn-at-spanish-head",
            "--raw-dir",
            str(raw_dir),
            "--output",
            str(output),
            "--overwrite",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Raw file count: 2" in completed.stdout
    assert "- Google Maps: 1" in completed.stdout
    assert "- ChatGPT: 1" in completed.stdout
    assert "- map_keyword: 1" in completed.stdout
    assert "- ai_visibility_prompt: 1" in completed.stdout
    assert "Generated Google Maps keyword scans: 1" in completed.stdout
    assert "Generated AI visibility source count: 1" in completed.stdout
    assert "Report IDs, prompts, API keys, raw payloads, and competitor names were not printed." in completed.stdout
    assert "full-private-report-id" not in completed.stdout
    assert "synthetic private ai prompt" not in completed.stdout
    assert "SECRET_API_KEY" not in completed.stdout
    assert "Synthetic Competitor" not in completed.stdout
    assert "trusted oceanfront lodging" not in completed.stdout


def test_local_falcon_summary_validator_redacts_ai_prompts(tmp_path):
    raw_dir = tmp_path / ".test-tmp-local-falcon-raw"
    raw_dir.mkdir()
    _write_raw_file(raw_dir / "report-001.json", _ai_raw_payload())
    output = tmp_path / ".test-tmp-local-falcon-output" / "local-falcon-summary.json"
    import_raw_api_directory(
        profile="inn-at-spanish-head",
        raw_dir=raw_dir,
        output_path=output,
        overwrite=True,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_local_falcon_summary.py"),
            "--file",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "synthetic private ai prompt" not in completed.stdout
    assert "[redacted AI prompt]" in completed.stdout
    assert "[redacted AI visibility scan]" in completed.stdout


def _write_raw_file(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _maps_raw_payload() -> dict:
    report = {
        "success": True,
        "data": {
            "keyword": "synthetic oceanfront hotel",
            "date": "2026-06-01",
            "grid_size": 2,
            "radius": 3,
            "lat": 44.95,
            "lng": -124.02,
            "location": {
                "name": "Spanish Head",
                "address": "Synthetic address",
                "rating": 4.6,
                "reviews": 1200,
            },
            "arp": 7.5,
            "atrp": 9.0,
            "solv": 24.5,
        },
    }
    grid = {
        "success": True,
        "data": {
            **report["data"],
            "data_points": [
                {"row": 0, "col": 0, "lat": 44.95, "lng": -124.02, "rank": 2},
                {"row": 0, "col": 1, "lat": 44.95, "lng": -124.01, "rank": 8},
                {"row": 1, "col": 0, "lat": 44.94, "lng": -124.02, "rank": 15},
                {"row": 1, "col": 1, "lat": 44.94, "lng": -124.01, "rank": None},
            ],
        },
    }
    competitors = {
        "success": True,
        "data": {
            "businesses": [
                {
                    "name": "Spanish Head",
                    "rank": 2,
                    "found_points": 3,
                    "top_3_points": 1,
                    "top_10_points": 2,
                    "solv": 24.5,
                },
                {
                    "name": "Synthetic Competitor",
                    "rank": 1,
                    "found_points": 4,
                    "top_3_points": 3,
                    "top_10_points": 4,
                    "solv": 39.2,
                },
            ]
        },
    }
    return {
        "profile": "inn-at-spanish-head",
        "source_id": "google_maps",
        "source_label": "Google Maps",
        "query_type": "map_keyword",
        "scan_kind": "map_visibility",
        "report_id_redacted": "full****t-id",
        "responses": {
            "report_summary": report,
            "grid_points": grid,
            "competitors": competitors,
            "ai_analysis": {
                "success": True,
                "data": {"ai_analysis": {"summary": "Synthetic local visibility summary."}},
            },
        },
    }


def _ai_raw_payload() -> dict:
    report = {
        "success": True,
        "data": {
            "keyword": "synthetic private ai prompt",
            "date": "2026-06-01",
            "grid_size": 2,
            "radius": 3,
            "lat": 44.95,
            "lng": -124.02,
            "location": {"name": "Spanish Head"},
            "ai_place_id": "place-client",
            "places": {"place-client": {"name": "Spanish Head", "saiv": 18.5}},
            "data_points": [
                {
                    "row": 0,
                    "col": 0,
                    "lat": 44.95,
                    "lng": -124.02,
                    "rank": True,
                    "found": True,
                    "results": [{"name": "Spanish Head", "place_id": "place-client", "rank": 1}],
                },
                {"row": 0, "col": 1, "lat": 44.95, "lng": -124.01, "rank": False, "found": False, "results": []},
                {"row": 1, "col": 0, "lat": 44.94, "lng": -124.02, "rank": False, "found": False, "results": []},
                {
                    "row": 1,
                    "col": 1,
                    "lat": 44.94,
                    "lng": -124.01,
                    "rank": True,
                    "found": True,
                    "results": [{"name": "Spanish Head", "place_id": "place-client", "rank": 2}],
                },
            ],
            "brand_phrases": [
                {
                    "phrase": "trusted oceanfront lodging",
                    "count": 2,
                    "sentiment": "positive",
                    "brand_name": "Spanish Head",
                }
            ],
            "sources": [
                {
                    "source": "synthetic source",
                    "title": "Synthetic citation",
                    "link": "https://example.invalid/synthetic",
                    "count": 2,
                }
            ],
            "ai_analysis": {"summary": "Synthetic AI visibility summary."},
        },
    }
    return {
        "profile": "inn-at-spanish-head",
        "source_id": "chatgpt",
        "source_label": "ChatGPT",
        "query_type": "ai_visibility_prompt",
        "scan_kind": "ai_visibility_map",
        "report_id_redacted": "full****t-id",
        "responses": {
            "report_summary": report,
            "grid_points": report,
            "competitors": {"success": True, "data": {"businesses": []}},
            "ai_analysis": report,
        },
    }
