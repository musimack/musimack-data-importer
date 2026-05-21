from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError, load_database_config
from src.postgres_writer import import_snapshot, load_snapshot_file
from src.validate import inspect_snapshot_payload, safe_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Import sanitized GA4 snapshot JSON locally.")
    parser.add_argument("--file", required=True, help="Sanitized ga4_snapshot.v1 JSON file")
    parser.add_argument("--project-id", help="Local portal project UUID")
    parser.add_argument("--skip-sync-run", action="store_true", help="Do not create integration_sync_runs row")
    args = parser.parse_args()

    try:
        payload = load_snapshot_file(args.file)
        inspection = inspect_snapshot_payload(payload)
        config = load_database_config(args.project_id)
        outcome = import_snapshot(
            database_url=config.database_url,
            project_id=config.project_id,
            payload=payload,
            create_sync_run=not args.skip_sync_run,
        )
    except (ConfigError, OSError, ValueError) as exc:
        print(f"GA4 import failed safely: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"GA4 import failed safely during database write: {type(exc).__name__}", file=sys.stderr)
        return 1

    summary = safe_summary(payload)
    print(
        "Imported internal/draft GA4 snapshot "
        f"{outcome.snapshot_id} for {summary['period_start']} through {summary['period_end']} "
        f"with {summary['metric_count']} metrics."
    )
    if outcome.sync_run_id:
        print(f"Recorded local import sync run {outcome.sync_run_id}.")
    print(f"Project ID: {config.project_id}")
    print("Initial visibility/status: internal/draft")
    print(
        "Sanitized counts: "
        f"{inspection.metric_count} metrics, "
        f"{inspection.trend_point_count} daily trend points, "
        f"{inspection.channel_row_count} traffic channel rows, "
        f"{inspection.top_page_row_count} top page rows, "
        f"{inspection.warning_count} warnings."
    )
    print("Portal follow-up required: link/preview/promote/set-active in the portal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
