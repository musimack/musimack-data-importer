from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_importer import (
    DEFAULT_COMPETITOR_CAP,
    LocalFalconImportError,
    import_local_falcon_csv,
    validate_local_falcon_summary,
)


DEFAULT_PROFILE = "aluma-seo-geo"
DEFAULT_KEYWORD = "sculptra treatment"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a real local Local Falcon CSV/TXT export without committing real data."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Dashboard-lab profile slug.")
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD, help="Keyword represented by this scan.")
    parser.add_argument("--business-name", default="Aluma Aesthetic Medicine", help="Business name for matching client rows.")
    parser.add_argument("--scan-report", required=True, help="Real local scan/report CSV path.")
    parser.add_argument("--data-points", required=True, help="Real local data points CSV path.")
    parser.add_argument("--ai-analysis", help="Optional real local AI analysis TXT path.")
    parser.add_argument(
        "--output",
        help=(
            "Output JSON path. Defaults to "
            "exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json."
        ),
    )
    parser.add_argument("--featured-keyword-id", help="Optional featured keyword id.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output instead of merging scans.")
    parser.add_argument("--competitor-cap", type=int, default=DEFAULT_COMPETITOR_CAP)
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
        payload = json.loads(output.read_text(encoding="utf-8"))
        scan = _find_scan(payload, args.keyword)
        validation = validate_local_falcon_summary(payload, output)
    except (LocalFalconImportError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Local Falcon real export validation failed safely: {exc}", file=sys.stderr)
        return 1

    counts = scan["data_points"]
    metrics = scan.get("local_falcon_metrics", {})
    print("Validated real local Local Falcon export")
    print(f"Profile: {args.profile}")
    print(f"Keyword scans: {validation.keyword_scan_count}")
    print(f"Featured: {validation.featured_keyword_id or 'none'}")
    print(f"Strongest: {validation.strongest_keyword_id or 'none'}")
    print(f"Weakest: {validation.weakest_keyword_id or 'none'}")
    print(f"Keyword: {scan['keyword']}")
    print(f"Output: {summary.output_path}")
    print(
        "Data points: "
        f"total={counts['total']}, found={counts['found']}, "
        f"top_3={counts['top_3']}, top_10={counts['top_10']}, "
        f"weak_or_not_found={counts['not_found_or_20_plus']}"
    )
    print(
        "Rendered grid: "
        f"{scan['rendered_grid']['rows']} rows x {scan['rendered_grid']['columns']} columns"
    )
    print(f"Grid size label: {scan.get('grid_size_label') or 'not available'}")
    print(
        "Local Falcon metrics: "
        f"ARP={metrics.get('arp', 'n/a')}, ATRP={metrics.get('atrp', 'n/a')}, "
        f"SoLV={metrics.get('solv', 'n/a')}"
    )
    print(f"Competitors: {len(scan.get('competitors', []))}")
    print(f"AI analysis available: {'yes' if scan.get('ai_analysis', {}).get('available') else 'no'}")
    print(f"Action bridge: {len(scan.get('action_bridge', []))}")
    for warning in summary.warnings + validation.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


def _find_scan(payload: dict[str, Any], keyword: str) -> dict[str, Any]:
    for scan in payload.get("keyword_scans", []):
        if scan.get("keyword") == keyword:
            return scan
    raise ValueError(f"output does not contain keyword scan: {keyword}")

if __name__ == "__main__":
    raise SystemExit(main())
