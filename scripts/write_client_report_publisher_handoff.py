from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_publisher_handoff_writer import write_client_report_publisher_handoff


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write local-only sanitized Client Report Publisher handoff JSON from existing summaries."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug.")
    parser.add_argument("--client-name", required=True, help="Client display name for sanitized handoff metadata.")
    parser.add_argument("--source-dir", help="Folder containing sanitized dashboard-lab local-real summaries.")
    parser.add_argument("--out", help="Output folder for handoff JSON.")
    parser.add_argument("--ga4-summary", help="Optional ga4-summary.json path.")
    parser.add_argument("--ga4-snapshot", help="Optional ga4-snapshot.json path.")
    parser.add_argument("--gsc-summary", help="Optional gsc-summary.json path.")
    args = parser.parse_args()

    try:
        result = write_client_report_publisher_handoff(
            profile=args.profile,
            client_name=args.client_name,
            source_dir=Path(args.source_dir) if args.source_dir else None,
            output_dir=Path(args.out) if args.out else None,
            ga4_summary_path=Path(args.ga4_summary) if args.ga4_summary else None,
            ga4_snapshot_path=Path(args.ga4_snapshot) if args.ga4_snapshot else None,
            gsc_summary_path=Path(args.gsc_summary) if args.gsc_summary else None,
        )
    except (OSError, ValueError) as exc:
        print(f"Client Report Publisher handoff write failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote Client Report Publisher handoff to: {result.output_dir}")
    for path in result.files:
        print(f"- {path}")
    for warning in result.skipped:
        print(f"WARN: {warning}", file=sys.stderr)
    print("Handoff output was generated from sanitized local-real summaries only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
