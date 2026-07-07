import json
import shutil
import subprocess
import sys
from pathlib import Path

from src.client_report_publisher_handoff_validator import validate_handoff_directory


FIXTURE_DIR = Path("dev/fixtures/client_report_publisher_handoff")


def test_fake_fixture_directory_validates_successfully():
    result = validate_handoff_directory(FIXTURE_DIR)

    assert result.valid is True
    assert result.errors == []
    assert "manifest.json" in result.files_checked
    assert "ga4_metric_display.v1" in result.contracts_seen
    assert "local_falcon_display.v1" in result.contracts_seen


def test_manifest_missing_required_field_fails_safely(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    del manifest["client_slug"]
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.client_slug is required" in result.errors
    assert _safe_error_text(result.errors)


def test_manifest_path_traversal_is_rejected(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["files"][0]["path"] = "../outside.json"
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("must stay inside" in error for error in result.errors)


def test_missing_referenced_file_fails_safely(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    (handoff_dir / "ga4_metric_display.v1.json").unlink()

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "referenced file is missing: ga4_metric_display.v1.json" in result.errors


def test_forbidden_keys_are_rejected_deeply(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "gsc_summary_display.v1.json"
    payload = _load_json(payload_path)
    payload["nested"] = {"safe": [{"api_token_label": "redacted-in-test"}]}
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("forbidden key" in error and "api_token_label" in error for error in result.errors)
    assert _safe_error_text(result.errors)


def test_secret_like_values_are_rejected_without_echoing_value(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    payload["notes"] = ["Bearer abcdefghijklmnopqrstuvwxyz123456"]
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("secret-like value" in error for error in result.errors)
    assert all("abcdefghijklmnopqrstuvwxyz" not in error for error in result.errors)


def test_invalid_date_range_fails(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["period_start"] = "2026-05-01"
    manifest["period_end"] = "2026-04-01"
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.period_start must be on or before period_end" in result.errors


def test_invalid_json_fails_safely_without_dumping_content(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "local_falcon_display.v1.json"
    payload_path.write_text('{"schema_version": "local_falcon_display.v1", bad', encoding="utf-8")

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "local_falcon_display.v1.json is not valid JSON" in result.errors
    assert all("schema_version" not in error for error in result.errors)


def test_auto_publish_is_rejected(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_top_sources_display.v1.json"
    payload = _load_json(payload_path)
    payload["auto_publish"] = False
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("auto_publish" in error for error in result.errors)


def test_unrecognized_contract_fails(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_metric_display.v1.json"
    payload = _load_json(payload_path)
    payload["schema_version"] = "ga4_raw_payload.v1"
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert any("schema_version is not recognized" in error for error in result.errors)


def test_manifest_contracts_must_match_referenced_files(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["display_contract_versions"].remove("gsc_summary_display.v1")
    _write_json(manifest_path, manifest)

    result = validate_handoff_directory(handoff_dir)

    assert result.valid is False
    assert "manifest.display_contract_versions is missing referenced contract gsc_summary_display.v1" in result.errors


def test_list_count_limit_is_enforced(tmp_path):
    handoff_dir = _copy_fixture(tmp_path)
    payload_path = handoff_dir / "ga4_top_sources_display.v1.json"
    payload = _load_json(payload_path)
    payload["rows"] = [{"rank": index + 1, "label": f"Sample Source {index}"} for index in range(101)]
    _write_json(payload_path, payload)

    result = validate_handoff_directory(handoff_dir, max_list_items=100)

    assert result.valid is False
    assert any("list exceeds maximum item count" in error for error in result.errors)


def test_cli_returns_success_on_fake_fixture():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/validate_client_report_publisher_handoff.py",
            str(FIXTURE_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "validation: valid" in completed.stdout
    assert "ga4_metric_display.v1" in completed.stdout
    assert completed.stderr == ""


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "handoff"
    shutil.copytree(FIXTURE_DIR, target)
    return target


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _safe_error_text(errors: list[str]) -> bool:
    joined = "\n".join(errors).lower()
    return all(term not in joined for term in ("bearer ", "ya29.", "private_key_value"))
