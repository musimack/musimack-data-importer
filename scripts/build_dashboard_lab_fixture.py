from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.fixture_builder import (
    FixtureValidationError,
    build_all_profiles,
    build_profile_fixture,
    default_output_dir,
    list_profile_slugs,
    validate_dashboard_lab_fixture,
)


DEFAULT_PROFILE = "all-services-client"
DEFAULT_BASE_OUTPUT_DIR = Path("exports") / "dashboard-lab"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build local-only synthetic dashboard-lab fixture data."
    )
    parser.add_argument(
        "--out",
        help=(
            "Output directory. For one profile, defaults to exports/dashboard-lab/{profile}. "
            "With --all, this is treated as the base output directory."
        ),
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        choices=list_profile_slugs(),
        help="Fixture profile to generate.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all dashboard-lab fixture profiles.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing fixture directory without regenerating files.",
    )
    args = parser.parse_args()

    try:
        if args.validate_only:
            output_dir = Path(args.out) if args.out else default_output_dir(args.profile)
            files = validate_dashboard_lab_fixture(output_dir)
            print(f"Validated dashboard-lab fixture directory: {output_dir}")
        elif args.all:
            base_dir = Path(args.out) if args.out else DEFAULT_BASE_OUTPUT_DIR
            results = build_all_profiles(base_dir)
            files = [path for result in results for path in result.files]
            print(f"Generated all dashboard-lab fixture profiles under: {base_dir}")
        else:
            output_dir = Path(args.out) if args.out else default_output_dir(args.profile)
            result = build_profile_fixture(args.profile, output_dir)
            files = result.files
            print(
                f"Generated dashboard-lab fixture profile '{result.profile.slug}' "
                f"at: {result.output_dir}"
            )
    except (FixtureValidationError, OSError, ValueError) as exc:
        print(f"Dashboard-lab fixture operation failed safely: {exc}", file=sys.stderr)
        return 1

    for path in files:
        print(f"- {path}")
    print("Fixture data is synthetic/mock, local-only, and contains no live provider credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
