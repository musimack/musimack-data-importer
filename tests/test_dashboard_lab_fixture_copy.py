import json
from pathlib import Path

import pytest

from src.dashboard_lab.fixture_copy import (
    DashboardLabFixtureCopyError,
    copy_dashboard_lab_fixtures,
)
from src.dashboard_lab.paid_callrail_fixture_builder import build_paid_search_callrail_fixtures


PROFILE = "inn-at-spanish-head"


def test_synthetic_mode_maps_to_dashboard_public_fixtures(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    build_paid_search_callrail_fixtures(
        profile=PROFILE,
        output_root=importer_root / "exports" / "dashboard-lab",
    )

    result = copy_dashboard_lab_fixtures(
        profile=PROFILE,
        mode="synthetic",
        dashboard_lab_root=dashboard_root,
        importer_root=importer_root,
    )

    assert result.destination_dir == dashboard_root / "public" / "fixtures" / PROFILE
    assert (result.destination_dir / "google-ads-summary.json").exists()
    assert (result.destination_dir / "callrail-summary.json").exists()
    assert "public/local-fixtures" not in result.destination_dir.as_posix()


def test_local_real_mode_maps_to_dashboard_local_fixtures(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    build_paid_search_callrail_fixtures(
        profile=PROFILE,
        output_root=importer_root / "exports" / "local-real" / "dashboard-lab",
    )

    result = copy_dashboard_lab_fixtures(
        profile=PROFILE,
        mode="local-real",
        dashboard_lab_root=dashboard_root,
        importer_root=importer_root,
    )

    assert result.destination_dir == dashboard_root / "public" / "local-fixtures" / PROFILE
    assert (result.destination_dir / "google-ads-summary.json").exists()
    assert (result.destination_dir / "callrail-summary.json").exists()
    assert "/public/fixtures/" not in result.destination_dir.as_posix()


def test_dry_run_does_not_write_files(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    build_paid_search_callrail_fixtures(
        profile=PROFILE,
        output_root=importer_root / "exports" / "dashboard-lab",
    )

    result = copy_dashboard_lab_fixtures(
        profile=PROFILE,
        mode="synthetic",
        dashboard_lab_root=dashboard_root,
        importer_root=importer_root,
        dry_run=True,
    )

    assert result.dry_run is True
    assert all(item.status == "would copy" for item in result.copied)
    assert not result.destination_dir.exists()


def test_copy_uses_allowlist_only(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    source_root = importer_root / "exports" / "dashboard-lab"
    build_paid_search_callrail_fixtures(profile=PROFILE, output_root=source_root)
    source_dir = source_root / PROFILE
    (source_dir / "raw-api-response.json").write_text("{}", encoding="utf-8")
    (source_dir / "calls.csv").write_text("not copied", encoding="utf-8")

    result = copy_dashboard_lab_fixtures(
        profile=PROFILE,
        mode="synthetic",
        dashboard_lab_root=dashboard_root,
        importer_root=importer_root,
    )

    assert not (result.destination_dir / "raw-api-response.json").exists()
    assert not (result.destination_dir / "calls.csv").exists()
    assert sorted(path.name for path in result.ignored_files) == ["calls.csv", "raw-api-response.json"]


def test_google_ads_fixture_is_validated_before_copy(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    source_root = importer_root / "exports" / "dashboard-lab"
    build_paid_search_callrail_fixtures(profile=PROFILE, output_root=source_root)
    _mutate_json(source_root / PROFILE / "google-ads-summary.json", {"provider": "bad_provider"})

    with pytest.raises(DashboardLabFixtureCopyError) as exc_info:
        copy_dashboard_lab_fixtures(
            profile=PROFILE,
            mode="synthetic",
            dashboard_lab_root=dashboard_root,
            importer_root=importer_root,
        )

    assert "provider must be google_ads" in str(exc_info.value)
    assert not (dashboard_root / "public" / "fixtures" / PROFILE / "google-ads-summary.json").exists()


def test_callrail_fixture_is_validated_before_copy(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    dashboard_root = _dashboard_root(tmp_path)
    source_root = importer_root / "exports" / "dashboard-lab"
    build_paid_search_callrail_fixtures(profile=PROFILE, output_root=source_root)
    _mutate_json(source_root / PROFILE / "callrail-summary.json", {"tracking_number_rows": [{"label": "503-555-0199", "calls": 2}]})

    with pytest.raises(DashboardLabFixtureCopyError) as exc_info:
        copy_dashboard_lab_fixtures(
            profile=PROFILE,
            mode="synthetic",
            dashboard_lab_root=dashboard_root,
            importer_root=importer_root,
        )

    assert "phone-number-looking value" in str(exc_info.value)
    assert not (dashboard_root / "public" / "fixtures" / PROFILE / "callrail-summary.json").exists()


def test_copy_refuses_dashboard_root_that_does_not_look_like_dashboard_lab(tmp_path):
    importer_root = tmp_path / "musimack-data-importer"
    bad_dashboard_root = tmp_path / "client-dashboard"
    bad_dashboard_root.mkdir()
    build_paid_search_callrail_fixtures(
        profile=PROFILE,
        output_root=importer_root / "exports" / "dashboard-lab",
    )

    with pytest.raises(DashboardLabFixtureCopyError, match="musimack-dashboard-lab"):
        copy_dashboard_lab_fixtures(
            profile=PROFILE,
            mode="synthetic",
            dashboard_lab_root=bad_dashboard_root,
            importer_root=importer_root,
        )


def _dashboard_root(tmp_path: Path) -> Path:
    root = tmp_path / "musimack-dashboard-lab"
    root.mkdir()
    return root


def _mutate_json(path: Path, updates: dict) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    path.write_text(json.dumps(payload), encoding="utf-8")
