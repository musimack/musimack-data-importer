from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_publisher_handoff_validator import validate_handoff_directory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a local sanitized Client Report Publisher handoff folder."
    )
    parser.add_argument("folder", help="Path to a handoff folder containing manifest.json.")
    parser.add_argument(
        "--max-list-items",
        type=int,
        default=100,
        help="Maximum allowed items in any JSON list. Defaults to 100.",
    )
    args = parser.parse_args()

    result = validate_handoff_directory(args.folder, max_list_items=args.max_list_items)
    if result.valid:
        print("Client Report Publisher handoff validation: valid")
    else:
        print("Client Report Publisher handoff validation: invalid", file=sys.stderr)

    print(f"Files checked: {len(result.files_checked)}")
    for file_name in result.files_checked:
        print(f"FILE: {file_name}")

    print(f"Contracts seen: {len(result.contracts_seen)}")
    for contract in result.contracts_seen:
        print(f"CONTRACT: {contract}")

    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
