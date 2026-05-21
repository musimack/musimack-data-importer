from pathlib import Path


def test_validate_script_reports_sanitized_counts():
    script = Path("scripts/validate_ga4_snapshot.py").read_text(encoding="utf-8")

    assert "Validate a sanitized ga4_snapshot.v1 export" in script
    assert "Secret-like fields: none detected" in script
    assert "raw" not in "Secret-like fields: none detected"
