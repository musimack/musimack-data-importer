from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.portal_db_ready import build_portal_db_ready_report, db_report_has_failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only portal database readiness check without printing credentials."
    )
    parser.parse_args()

    checks = build_portal_db_ready_report()
    print("Portal database readiness check")
    for check in checks:
        print(check.line())
    if db_report_has_failures(checks):
        print("Result: FAIL - fix portal database connectivity/schema before imports.")
        return 1
    print("Result: PASS - portal database is reachable and required tables exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
