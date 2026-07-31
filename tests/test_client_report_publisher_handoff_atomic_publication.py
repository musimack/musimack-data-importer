"""Focused regression tests for atomic client report handoff publication.

The approved presentation-range contract requires that no partially written or
half-replaced handoff can ever become portal-visible. These tests pin that
behavior on the private publication helper so a future refactor cannot silently
reintroduce a direct, non-atomic write.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.client_report_publisher_handoff_writer import _write_json


def _payload(marker: str) -> dict[str, object]:
    return {"schema_version": "client_report_presentation_ranges.v2", "marker": marker}


def test_publication_writes_complete_payload(tmp_path):
    target = tmp_path / "client_report_presentation_ranges.v2.json"

    _write_json(target, _payload("first"))

    assert json.loads(target.read_text(encoding="utf-8"))["marker"] == "first"


def test_publication_replaces_existing_destination_completely(tmp_path):
    target = tmp_path / "client_report_presentation_ranges.v2.json"
    _write_json(target, _payload("first"))

    _write_json(target, _payload("second"))

    assert json.loads(target.read_text(encoding="utf-8"))["marker"] == "second"


def test_publication_uses_atomic_replace(tmp_path, monkeypatch):
    """Publication must go through os.replace, not a direct write to target."""
    target = tmp_path / "handoff.json"
    observed: list[tuple[str, str]] = []

    real_replace = __import__("os").replace

    def recording_replace(src, dst):
        observed.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(
        "src.client_report_publisher_handoff_writer.os.replace", recording_replace
    )

    _write_json(target, _payload("atomic"))

    assert len(observed) == 1, "expected exactly one atomic replacement"
    source_path, destination_path = observed[0]
    assert destination_path == str(target)
    assert source_path != str(target), "must replace from a temporary file"
    assert Path(source_path).parent == target.parent, (
        "temporary file must live in the destination directory so os.replace stays atomic"
    )


def test_failed_write_leaves_existing_destination_byte_identical(tmp_path, monkeypatch):
    target = tmp_path / "client_report_presentation_ranges.v2.json"
    _write_json(target, _payload("published"))
    original_bytes = target.read_bytes()

    def failing_write_text(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if self == target:
            raise AssertionError("the destination must never be written directly")
        raise OSError("simulated disk failure while writing the temporary file")

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError):
        _write_json(target, _payload("should-not-be-published"))

    assert target.read_bytes() == original_bytes


def test_failed_write_does_not_expose_truncated_destination(tmp_path, monkeypatch):
    """A failure before replacement must not create the destination at all."""
    target = tmp_path / "brand_new_handoff.json"

    def failing_write_text(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise OSError("simulated disk failure while writing the temporary file")

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError):
        _write_json(target, _payload("never"))

    assert not target.exists()


def test_no_temporary_file_remains_after_success(tmp_path):
    target = tmp_path / "client_report_presentation_ranges.v2.json"

    _write_json(target, _payload("clean"))

    leftovers = [path.name for path in tmp_path.iterdir() if path.name != target.name]
    assert leftovers == [], f"temporary files were left behind: {leftovers}"


def test_no_temporary_file_remains_after_failure(tmp_path, monkeypatch):
    target = tmp_path / "client_report_presentation_ranges.v2.json"
    _write_json(target, _payload("published"))

    real_replace = __import__("os").replace

    def failing_replace(src, dst):  # noqa: ANN001
        raise OSError("simulated failure during replacement")

    monkeypatch.setattr(
        "src.client_report_publisher_handoff_writer.os.replace", failing_replace
    )

    with pytest.raises(OSError):
        _write_json(target, _payload("interrupted"))

    leftovers = [path.name for path in tmp_path.iterdir() if path.name != target.name]
    assert leftovers == [], f"temporary files were left behind: {leftovers}"
    assert json.loads(target.read_text(encoding="utf-8"))["marker"] == "published"

    monkeypatch.setattr(
        "src.client_report_publisher_handoff_writer.os.replace", real_replace
    )


def test_publication_preserves_formatting_and_encoding(tmp_path):
    """Sorted keys, two-space indent, and the trailing newline must be unchanged."""
    target = tmp_path / "handoff.json"

    _write_json(target, {"b": 2, "a": 1})

    assert target.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_publication_creates_missing_parent_directory(tmp_path):
    target = tmp_path / "nested" / "handoff.json"

    _write_json(target, _payload("nested"))

    assert json.loads(target.read_text(encoding="utf-8"))["marker"] == "nested"
