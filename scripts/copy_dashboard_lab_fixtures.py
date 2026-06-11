from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.fixture_copy import (
    DEFAULT_DASHBOARD_LAB_ROOT,
    DashboardLabFixtureCopyError,
    copy_dashboard_lab_fixtures,
)
from src.dashboard_lab.paid_callrail_validators import DashboardLabFixtureValidationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy allowlisted importer dashboard-lab JSON fixtures into the dashboard-lab repo."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug.")
    parser.add_argument("--mode", required=True, choices=["synthetic", "local-real"], help="Copy synthetic or ignored local-real fixtures.")
    parser.add_argument(
        "--dashboard-lab-root",
        default=str(DEFAULT_DASHBOARD_LAB_ROOT),
        help="Path to musimack-dashboard-lab. Defaults to ../musimack-dashboard-lab.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned copies without writing files.")
    args = parser.parse_args()

    try:
        result = copy_dashboard_lab_fixtures(
            profile=args.profile,
            mode=args.mode,
            dashboard_lab_root=Path(args.dashboard_lab_root),
            dry_run=args.dry_run,
        )
    except (DashboardLabFixtureCopyError, DashboardLabFixtureValidationError, OSError) as exc:
        print(f"Dashboard-lab fixture copy failed safely: {exc}", file=sys.stderr)
        return 1

    print("Dashboard-lab fixture copy plan" if args.dry_run else "Copied dashboard-lab fixtures")
    print(f"Profile: {result.profile}")
    print(f"Mode: {result.mode}")
    print(f"Source: {result.source_dir}")
    print(f"Destination: {result.destination_dir}")
    print(f"Dry run: {'yes' if result.dry_run else 'no'}")
    for item in result.copied:
        print(f"- {item.status}: {item.source} -> {item.destination}")
    for path in result.ignored_files:
        print(f"- ignored non-allowlisted source file: {path}")
    if result.mode == "local-real":
        print("WARNING: local-real dashboard fixtures are for ignored local-fixtures only and must not be committed.")
    print("Only allowlisted dashboard JSON files were considered. Raw exports, credentials, logs, CSVs, PDFs, TXT files, API responses, and directories were not copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
