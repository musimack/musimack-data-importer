from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.ga4.dashboard_summary import (
    Ga4DashboardSummaryError,
    build_ga4_dashboard_summary,
    real_output_dir,
    validate_ga4_dashboard_summary,
    write_ga4_dashboard_summary,
)
from src.providers.ga4.validate import ValidationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write a dashboard-lab ga4-summary.json from an existing sanitized GA4 snapshot."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug.")
    parser.add_argument("--snapshot", help="Existing sanitized ga4_snapshot.v1 JSON file.")
    parser.add_argument("--out", help="Output directory for ga4-summary.json.")
    parser.add_argument(
        "--real-output",
        action="store_true",
        help="Write to ignored exports/local-real/dashboard-lab/{profile}/.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate an existing ga4-summary.json without reading a snapshot.",
    )
    args = parser.parse_args()

    try:
        output_dir = resolve_output_dir(args.profile, args.out, args.real_output)
        if args.validate_only:
            path = output_dir / "ga4-summary.json"
            payload = _read_json(path)
            validate_ga4_dashboard_summary(payload, expected_profile_slug=args.profile)
            print(f"Validated GA4 dashboard-lab summary: {path}")
            return 0

        if not args.snapshot:
            raise Ga4DashboardSummaryError("--snapshot is required unless --validate-only is used")
        snapshot_path = Path(args.snapshot)
        snapshot_payload = _read_json(snapshot_path)
        summary = build_ga4_dashboard_summary(args.profile, snapshot_payload)
        path = write_ga4_dashboard_summary(output_dir, summary)
    except (OSError, json.JSONDecodeError, ValidationError, Ga4DashboardSummaryError) as exc:
        print(f"GA4 dashboard-lab summary write failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote GA4 dashboard-lab summary for profile '{args.profile}' to: {path}")
    print("Output contains dashboard summary fields only; raw property ids, credentials, tokens, and provider responses were not written.")
    return 0


def resolve_output_dir(profile: str, out: str | None, real_output: bool) -> Path:
    if out:
        return Path(out)
    if real_output:
        return real_output_dir(profile)
    raise Ga4DashboardSummaryError("--out is required unless --real-output is used")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Ga4DashboardSummaryError(f"file does not exist: {path}") from exc
    if not isinstance(payload, dict):
        raise Ga4DashboardSummaryError(f"{path.name} must contain a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
