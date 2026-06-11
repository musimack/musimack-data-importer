from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.callrail_export_diagnostic import (
    diagnose_callrail_export_shape,
    diagnostic_to_lines,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely inspect a local CallRail CSV export shape without printing raw rows or sensitive values."
    )
    parser.add_argument("--input", required=True, help="Ignored local CallRail CSV export path.")
    parser.add_argument("--profile", help="Dashboard-lab technical profile slug, for example inn-at-spanish-head.")
    parser.add_argument(
        "--max-sample-values",
        type=int,
        default=5,
        help="Maximum safe top values to print for each non-sensitive aggregate field.",
    )
    args = parser.parse_args()

    try:
        diagnostic = diagnose_callrail_export_shape(
            Path(args.input),
            profile=args.profile,
            max_sample_values=args.max_sample_values,
        )
    except OSError as exc:
        print(f"CallRail CSV export diagnostic failed safely: {exc}", file=sys.stderr)
        return 1

    for line in diagnostic_to_lines(diagnostic):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
