from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_importer import (
    DEFAULT_COMPETITOR_CAP,
    LocalFalconImportError,
    import_local_falcon_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import local Local Falcon CSV exports into dashboard-lab local_falcon_summary.v2 JSON."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug.")
    parser.add_argument("--keyword", required=True, help="Keyword represented by this scan.")
    parser.add_argument("--business-name", help="Client/business name, if not reliable in the CSV.")
    parser.add_argument("--scan-report", required=True, help="Scan/report-level CSV path.")
    parser.add_argument("--data-points", required=True, help="Grid points and competitor/result rows CSV path.")
    parser.add_argument("--ai-analysis", help="Optional local AI analysis .txt path.")
    parser.add_argument(
        "--output",
        help="Output JSON path. Defaults to exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json.",
    )
    parser.add_argument("--featured-keyword-id", help="Optional featured keyword id to preserve/show first.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output file instead of preserving scans.")
    parser.add_argument(
        "--competitor-cap",
        type=int,
        default=DEFAULT_COMPETITOR_CAP,
        help="Maximum focused competitors to write.",
    )
    args = parser.parse_args()

    output = (
        Path(args.output)
        if args.output
        else Path("exports") / "local-real" / "dashboard-lab" / args.profile / "local-falcon-summary.json"
    )

    try:
        summary = import_local_falcon_csv(
            profile=args.profile,
            keyword=args.keyword,
            business_name=args.business_name,
            scan_report_path=args.scan_report,
            data_points_path=args.data_points,
            ai_analysis_path=args.ai_analysis,
            output_path=output,
            featured_keyword_id=args.featured_keyword_id,
            overwrite=args.overwrite,
            competitor_cap=args.competitor_cap,
        )
    except (LocalFalconImportError, OSError, ValueError) as exc:
        print(f"Local Falcon CSV import failed safely: {exc}", file=sys.stderr)
        return 1

    counts = summary.data_points
    print(f"Imported Local Falcon scan for profile: {summary.profile}")
    print(f"Keyword: {summary.keyword}")
    print(
        "Data points: "
        f"total={counts['total']}, found={counts['found']}, "
        f"top_3={counts['top_3']}, top_10={counts['top_10']}, "
        f"weak_or_not_found={counts['not_found_or_20_plus']}"
    )
    print(f"Competitors: {summary.competitor_count}")
    print(
        "Rendered grid: "
        f"{summary.rendered_grid['rows']} rows x {summary.rendered_grid['columns']} columns"
    )
    print(f"AI analysis available: {'yes' if summary.ai_analysis_available else 'no'}")
    print(f"Output: {summary.output_path}")
    for warning in summary.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
