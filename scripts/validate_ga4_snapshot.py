from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.validate import ValidationError, inspect_snapshot_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a sanitized ga4_snapshot.v1 export.")
    parser.add_argument("--file", required=True, help="Sanitized GA4 snapshot JSON file")
    args = parser.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        inspection = inspect_snapshot_payload(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"GA4 snapshot validation failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"Validated sanitized GA4 snapshot: {args.file}")
    for line in inspection.lines():
        print(f"- {line}")
    print("Secret-like fields: none detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
