from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.fixture_builder import (
    FixtureValidationError,
    build_all_services_fixture,
    validate_dashboard_lab_fixture,
)


DEFAULT_OUTPUT_DIR = Path("exports") / "dashboard-lab" / "all-services-client"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build local-only synthetic dashboard-lab fixture data."
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Output directory for generated dashboard-lab JSON fixtures.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing fixture directory without regenerating files.",
    )
    args = parser.parse_args()

    output_dir = Path(args.out)
    try:
        if args.validate_only:
            files = validate_dashboard_lab_fixture(output_dir)
            print(f"Validated dashboard-lab fixture directory: {output_dir}")
        else:
            result = build_all_services_fixture(output_dir)
            files = result.files
            print(f"Generated dashboard-lab fixture directory: {result.output_dir}")
    except (FixtureValidationError, OSError, ValueError) as exc:
        print(f"Dashboard-lab fixture operation failed safely: {exc}", file=sys.stderr)
        return 1

    for path in files:
        print(f"- {path}")
    print("Fixture data is synthetic/mock, local-only, and contains no live provider credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
