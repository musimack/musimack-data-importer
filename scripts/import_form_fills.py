from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.form_fills import (
    DEFAULT_OUTPUT_ROOT,
    FormFillsImportError,
    import_form_fills_dates,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import date-only local form fills into an aggregate dashboard-lab form-fills-summary.json."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab technical profile slug.")
    parser.add_argument("--input", required=True, help="Ignored local CSV/JSON input containing dates only.")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Output root. Real output must stay under exports/local-real/dashboard-lab.",
    )
    parser.add_argument("--real-output", action="store_true", help="Required for local-real output safety checks.")
    args = parser.parse_args()

    try:
        result = import_form_fills_dates(
            profile=args.profile,
            input_path=Path(args.input),
            output_root=Path(args.output_root),
            real_output=args.real_output,
        )
    except (FormFillsImportError, OSError) as exc:
        print(f"Form fills import failed safely: {exc}", file=sys.stderr)
        return 1

    print("Form fills summary written")
    print(f"Profile: {args.profile}")
    print(f"Output: {result.output_path}")
    print(f"Total form fills: {result.total_form_fills}")
    print(f"Dates with form fills: {result.date_count}")
    print(f"Validation: python scripts/validate_form_fills_summary.py --input {result.output_path}")
    print("No names, emails, phone numbers, messages, IP addresses, or raw form payloads were stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
