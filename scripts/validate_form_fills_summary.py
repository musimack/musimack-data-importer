from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.form_fills import validate_form_fills_summary
from src.dashboard_lab.paid_callrail_validators import (
    DashboardLabFixtureValidationError,
    load_json_object,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a dashboard-lab form-fills-summary.json aggregate fixture contract."
    )
    parser.add_argument("--input", required=True, help="Path to form-fills-summary.json.")
    args = parser.parse_args()

    path = Path(args.input)
    try:
        payload = load_json_object(path)
        validate_form_fills_summary(payload)
    except DashboardLabFixtureValidationError as exc:
        print(f"Form fills summary validation failed safely: {exc}", file=sys.stderr)
        return 1

    print("Validated form fills summary fixture")
    print(f"Profile: {payload.get('profile')}")
    print(f"Client: {payload.get('client_label')}")
    print(f"Input: {path}")
    print("Provider: form_fills")
    print(f"Total form fills: {payload.get('summary', {}).get('total_form_fills')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
