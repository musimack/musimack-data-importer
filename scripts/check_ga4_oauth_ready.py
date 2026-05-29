from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.console_ops import build_console_readiness_report
from src.local_config import load_local_operator_config
from src.oauth_readiness import report_has_failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local GA4 OAuth/operator readiness without printing secrets."
    )
    parser.parse_args()

    local_config_status = load_local_operator_config()
    checks = build_console_readiness_report()
    print("GA4 OAuth/operator readiness check")
    for line in local_config_status.safe_summary_lines():
        print(line)
    for check in checks:
        print(check.line())
    if report_has_failures(checks):
        print("Result: FAIL - fix failed checks before live GA4 export or batch import.")
        return 1
    print("Result: PASS - OAuth/operator readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
