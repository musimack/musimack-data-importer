from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .local_falcon_api_fetcher import (
    LocalFalconApiFetcher,
    LocalFalconApiFetcherError,
    LocalFalconApiFetchRequest,
    LocalFalconApiFetchResult,
    LocalFalconApiTransport,
)
from .local_falcon_api_responses import load_synthetic_api_fixture
from .local_falcon_importer import OutputValidation


class LocalFalconApiWriteError(RuntimeError):
    pass


class DisabledLiveLocalFalconTransport:
    def _raise(self) -> None:
        raise NotImplementedError(
            "Live Local Falcon API transport is not implemented and requires explicit approval."
        )

    def get_report_summary(self, report_id: str) -> dict[str, Any]:
        self._raise()

    def get_grid_points(self, report_id: str) -> dict[str, Any]:
        self._raise()

    def get_competitors(self, report_id: str) -> dict[str, Any] | None:
        self._raise()

    def get_ai_analysis(self, report_id: str) -> dict[str, Any] | None:
        self._raise()


class SyntheticFixtureLocalFalconTransport:
    """Deterministic fake transport backed by committed synthetic API fixtures."""

    def __init__(self, fixture_dir: Path | str | None = None):
        base_dir = Path(fixture_dir) if fixture_dir else _default_fixture_dir()
        self._summary = load_synthetic_api_fixture(base_dir / "report_summary_response.json")
        self._grid = load_synthetic_api_fixture(base_dir / "report_grid_points_response.json")
        self._competitors = load_synthetic_api_fixture(base_dir / "competitor_report_response.json")
        self._ai = load_synthetic_api_fixture(base_dir / "ai_analysis_response.json")

    def get_report_summary(self, report_id: str) -> dict[str, Any]:
        payload = copy.deepcopy(self._summary)
        report = payload["data"]["report"]
        report["report_key"] = report_id
        if report_id == "demo-report-b":
            report["keyword"] = "demo weak service"
            report["arp"] = 18.4
            report["atrp"] = 21.9
            report["solv"] = 3.2
        return payload

    def get_grid_points(self, report_id: str) -> dict[str, Any]:
        payload = copy.deepcopy(self._grid)
        if report_id == "demo-report-b":
            for point in payload["data"]["grid_points"]:
                point["rank"] = None
        return payload

    def get_competitors(self, report_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self._competitors)

    def get_ai_analysis(self, report_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self._ai)


@dataclass(frozen=True)
class LocalFalconApiWriteResult:
    output_path: Path
    created: bool
    updated: bool
    keyword_count: int
    validation: OutputValidation
    warnings: list[str]
    source_type: str
    no_network: bool


def fetch_validate_and_write_summary(
    request: LocalFalconApiFetchRequest,
    transport: LocalFalconApiTransport,
    *,
    preserve_existing: bool = True,
) -> LocalFalconApiWriteResult:
    output_path = request.output_path
    existing_on_disk = _load_existing_summary(output_path)
    existing = existing_on_disk if preserve_existing else None
    fetch_request = LocalFalconApiFetchRequest(
        profile=request.profile,
        reports=request.reports,
        output=output_path,
        featured_keyword_id=request.featured_keyword_id,
        existing_summary=existing,
        source_type=request.source_type,
        real_data=request.real_data,
        dry_run=False,
        no_write=False,
    )
    try:
        result = LocalFalconApiFetcher(transport).fetch(fetch_request)
    except LocalFalconApiFetcherError:
        raise
    except Exception as exc:
        raise LocalFalconApiWriteError(f"Local Falcon fake write failed before output write: {exc}") from exc
    _atomic_write_json(output_path, result.summary)
    return _write_result(output_path, existing_on_disk is None, result)


def is_safe_local_falcon_api_write_path(path: Path | str, *, cwd: Path | str | None = None) -> bool:
    target = Path(path)
    base = Path(cwd) if cwd else Path.cwd()
    try:
        relative = target.resolve().relative_to(base.resolve())
        normalized = relative.as_posix()
    except ValueError:
        normalized = target.as_posix()
    return (
        normalized.startswith("exports/local-real/")
        or normalized.startswith(".test-tmp-")
        or "/.test-tmp-" in normalized
    )


def _load_existing_summary(output_path: Path) -> dict[str, Any] | None:
    if not output_path.exists():
        return None
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalFalconApiWriteError("existing Local Falcon output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LocalFalconApiWriteError("existing Local Falcon output must contain a JSON object")
    return payload


def _atomic_write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_result(output_path: Path, created: bool, result: LocalFalconApiFetchResult) -> LocalFalconApiWriteResult:
    return LocalFalconApiWriteResult(
        output_path=output_path,
        created=created,
        updated=not created,
        keyword_count=result.summary.get("summary", {}).get("keyword_count", 0),
        validation=result.validation,
        warnings=result.warnings,
        source_type=str(result.summary.get("source_type") or ""),
        no_network=result.summary.get("real_data") is not True,
    )


def _default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "local_falcon_api"
