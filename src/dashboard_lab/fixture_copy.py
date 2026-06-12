from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .paid_callrail_validators import (
    DashboardLabFixtureValidationError,
    load_json_object,
    validate_callrail_summary,
    validate_google_ads_summary,
)
from .form_fills import validate_form_fills_summary


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DASHBOARD_LAB_ROOT = ROOT.parent / "musimack-dashboard-lab"
ALLOWED_FIXTURE_FILES = [
    "client-profile.json",
    "combined-dashboard-summary.json",
    "ga4-summary.json",
    "gsc-summary.json",
    "local-falcon-summary.json",
    "google-ads-summary.json",
    "callrail-summary.json",
    "form-fills-summary.json",
]


class DashboardLabFixtureCopyError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureCopyItem:
    file: str
    source: Path
    destination: Path
    status: str


@dataclass(frozen=True)
class FixtureCopyResult:
    profile: str
    mode: str
    source_dir: Path
    destination_dir: Path
    dry_run: bool
    copied: list[FixtureCopyItem]
    ignored_files: list[Path]


def copy_dashboard_lab_fixtures(
    *,
    profile: str,
    mode: str,
    dashboard_lab_root: Path | str = DEFAULT_DASHBOARD_LAB_ROOT,
    importer_root: Path | str = ROOT,
    dry_run: bool = False,
) -> FixtureCopyResult:
    source_dir = _source_dir(Path(importer_root), profile, mode)
    dashboard_root = Path(dashboard_lab_root)
    destination_dir = _destination_dir(dashboard_root, profile, mode)
    _validate_copy_request(profile, mode, source_dir, dashboard_root, destination_dir)

    copied: list[FixtureCopyItem] = []
    for filename in ALLOWED_FIXTURE_FILES:
        source = source_dir / filename
        if not source.exists():
            continue
        if not source.is_file():
            raise DashboardLabFixtureCopyError(f"allowlisted source is not a file: {source}")
        _validate_before_copy(source)
        destination = destination_dir / filename
        status = "would copy" if dry_run and not destination.exists() else "would overwrite" if dry_run else "copied" if not destination.exists() else "overwritten"
        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        copied.append(FixtureCopyItem(filename, source, destination, status))

    if not copied:
        raise DashboardLabFixtureCopyError("source directory contains no allowlisted dashboard JSON files")

    ignored = [
        path
        for path in sorted(source_dir.iterdir())
        if path.is_file() and path.name not in ALLOWED_FIXTURE_FILES
    ]
    return FixtureCopyResult(
        profile=profile,
        mode=mode,
        source_dir=source_dir,
        destination_dir=destination_dir,
        dry_run=dry_run,
        copied=copied,
        ignored_files=ignored,
    )


def _source_dir(importer_root: Path, profile: str, mode: str) -> Path:
    _validate_profile(profile)
    if mode == "synthetic":
        return importer_root / "exports" / "dashboard-lab" / profile
    if mode == "local-real":
        return importer_root / "exports" / "local-real" / "dashboard-lab" / profile
    raise DashboardLabFixtureCopyError("--mode must be synthetic or local-real")


def _destination_dir(dashboard_root: Path, profile: str, mode: str) -> Path:
    if mode == "synthetic":
        return dashboard_root / "public" / "fixtures" / profile
    if mode == "local-real":
        return dashboard_root / "public" / "local-fixtures" / profile
    raise DashboardLabFixtureCopyError("--mode must be synthetic or local-real")


def _validate_copy_request(
    profile: str,
    mode: str,
    source_dir: Path,
    dashboard_root: Path,
    destination_dir: Path,
) -> None:
    _validate_profile(profile)
    if mode not in {"synthetic", "local-real"}:
        raise DashboardLabFixtureCopyError("--mode must be synthetic or local-real")
    if not source_dir.exists() or not source_dir.is_dir():
        raise DashboardLabFixtureCopyError(f"source directory does not exist: {source_dir}")
    if dashboard_root.name != "musimack-dashboard-lab":
        raise DashboardLabFixtureCopyError("dashboard-lab root must look like musimack-dashboard-lab")
    if not dashboard_root.exists() or not dashboard_root.is_dir():
        raise DashboardLabFixtureCopyError(f"dashboard-lab root does not exist: {dashboard_root}")
    destination_posix = destination_dir.resolve().as_posix()
    if mode == "local-real":
        if "/public/local-fixtures/" not in destination_posix:
            raise DashboardLabFixtureCopyError("local-real destination must be public/local-fixtures/{profile}")
        if "/public/fixtures/" in destination_posix:
            raise DashboardLabFixtureCopyError("local-real mode must never copy into public/fixtures")
    if mode == "synthetic":
        if "/public/fixtures/" not in destination_posix:
            raise DashboardLabFixtureCopyError("synthetic destination must be public/fixtures/{profile}")
        if "/public/local-fixtures/" in destination_posix:
            raise DashboardLabFixtureCopyError("synthetic mode must not copy into public/local-fixtures")


def _validate_before_copy(source: Path) -> None:
    try:
        if source.name == "google-ads-summary.json":
            validate_google_ads_summary(load_json_object(source))
        if source.name == "callrail-summary.json":
            validate_callrail_summary(load_json_object(source))
        if source.name == "form-fills-summary.json":
            validate_form_fills_summary(load_json_object(source))
    except DashboardLabFixtureValidationError as exc:
        raise DashboardLabFixtureCopyError(f"{source.name} failed validation before copy: {exc}") from exc


def _validate_profile(profile: str) -> None:
    if not profile or "/" in profile or "\\" in profile or profile in {".", ".."}:
        raise DashboardLabFixtureCopyError("--profile must be a safe profile slug")
