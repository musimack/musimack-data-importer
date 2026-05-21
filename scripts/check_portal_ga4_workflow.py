from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError, load_database_config
from src.portal_workflow_check import build_workflow_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only local portal GA4 onboarding/report workflow check."
    )
    parser.add_argument("--project-id", help="Local portal project UUID")
    parser.add_argument("--assigned-email", help="Expected assigned client user email")
    parser.add_argument("--unrelated-email", help="Expected unrelated client user email")
    args = parser.parse_args()

    try:
        config = load_database_config(args.project_id)
        summary = build_workflow_summary(
            database_url=config.database_url,
            project_id=config.project_id,
            assigned_email=args.assigned_email,
            unrelated_email=args.unrelated_email,
        )
    except ConfigError as exc:
        print(f"Workflow check failed safely: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            "Workflow check failed safely during read-only database check: "
            f"{type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    for line in summary.lines():
        print(line)
    print("Database writes: none")
    print("Live Google calls: none")
    return 0 if summary.ready_for_import else 2


if __name__ == "__main__":
    raise SystemExit(main())
