from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.paid_callrail_fixture_builder import (
    DEFAULT_END_DATE,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PROFILE,
    DEFAULT_START_DATE,
    PaidSearchCallRailFixtureBuildError,
    build_paid_search_callrail_fixtures,
)
from src.dashboard_lab.paid_callrail_validators import DashboardLabFixtureValidationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build synthetic dashboard-lab Google Ads and CallRail fixture contracts."
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help="Profile slug. Currently supports inn-at-spanish-head.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Base output root. Defaults to exports/dashboard-lab.",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Fixture date_range.start_date.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Fixture date_range.end_date.")
    args = parser.parse_args()

    try:
        result = build_paid_search_callrail_fixtures(
            profile=args.profile,
            output_root=Path(args.output_root),
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except (PaidSearchCallRailFixtureBuildError, DashboardLabFixtureValidationError, OSError, ValueError) as exc:
        print(f"Paid search and CallRail fixture build failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"Generated synthetic paid search and CallRail fixtures for profile: {result.profile}")
    print(f"Output directory: {result.output_dir}")
    for path in result.files:
        print(f"- {path}")
    print("Validation: passed")
    print("Fixture data is synthetic/demo only and contains no real provider data, credentials, caller details, phone numbers, recordings, transcripts, or raw call logs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
