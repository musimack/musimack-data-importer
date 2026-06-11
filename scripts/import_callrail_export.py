from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.callrail_export_importer import (
    DEFAULT_OUTPUT_ROOT,
    CallRailExportImportError,
    import_callrail_export,
)
from src.dashboard_lab.paid_callrail_validators import DashboardLabFixtureValidationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a local CallRail CSV export into an aggregate-only dashboard-lab callrail-summary.json."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab technical profile slug.")
    parser.add_argument("--input", required=True, help="Ignored local CallRail CSV export path.")
    parser.add_argument("--start-date", help="Optional inclusive start date filter, YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Optional inclusive end date filter, YYYY-MM-DD.")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Output root. Real output must stay under exports/local-real/dashboard-lab.",
    )
    parser.add_argument(
        "--granularity",
        choices=["daily", "weekly", "monthly"],
        default="monthly",
        help="Time series granularity.",
    )
    parser.add_argument("--real-output", action="store_true", help="Required to write real local CallRail-derived output.")
    parser.add_argument("--dry-run", action="store_true", help="Build and validate aggregate output without writing it.")
    parser.add_argument("--validate-only", action="store_true", help="Build and validate aggregate output without writing it.")
    args = parser.parse_args()

    try:
        result = import_callrail_export(
            profile=args.profile,
            input_path=Path(args.input),
            output_root=Path(args.output_root),
            start_date=args.start_date,
            end_date=args.end_date,
            granularity=args.granularity,
            real_output=args.real_output,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
        )
    except (CallRailExportImportError, DashboardLabFixtureValidationError) as exc:
        print(f"CallRail export import failed safely: {exc}", file=sys.stderr)
        return 1

    summary = result.payload["summary"]
    print("Imported CallRail export aggregate summary")
    print(f"Profile: {result.profile}")
    print(f"Output path: {result.output_path}")
    print(f"Output written: {'no' if args.dry_run or args.validate_only else 'yes'}")
    print(f"Total calls: {summary['total_calls']}")
    print(f"Google Ads calls: {summary['google_ads_calls']}")
    print(f"Calls with keyword attribution: {summary['calls_with_keyword_attribution']}")
    print(f"Calls without keyword attribution: {summary['calls_without_keyword_attribution']}")
    print(f"Answered calls: {summary['answered_calls']}")
    print(f"Missed calls: {summary['missed_calls']}")
    print(f"Qualified calls: {summary['qualified_calls']}")
    print("Validation: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
