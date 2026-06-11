from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.paid_callrail_validators import (
    DashboardLabFixtureValidationError,
    load_json_object,
    validate_google_ads_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a dashboard-lab google-ads-summary.json fixture contract."
    )
    parser.add_argument("--input", required=True, help="Path to google-ads-summary.json.")
    args = parser.parse_args()

    path = Path(args.input)
    try:
        result = validate_google_ads_summary(load_json_object(path))
    except DashboardLabFixtureValidationError as exc:
        print(f"Google Ads summary validation failed safely: {exc}", file=sys.stderr)
        return 1

    print("Validated Google Ads summary fixture")
    print(f"Profile: {result.profile}")
    print(f"Client: {result.client_label}")
    print(f"Input: {path}")
    print("Provider: google_ads")
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
