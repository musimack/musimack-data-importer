from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (
    ConfigError,
    add_date_args,
    load_database_config,
    load_ga4_config,
    parse_date_range,
    resolve_output_path,
)
from src.ga4_client import Ga4ClientError, Ga4DataClient
from src.normalize import normalize_traffic_overview
from src.postgres_writer import import_snapshot
from src.snapshot_builder import build_traffic_overview_snapshot
from src.validate import safe_summary, validate_snapshot_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local GA4 export and optional import.")
    add_date_args(parser)
    parser.add_argument("--out", help="Output JSON path, defaults under exports/")
    parser.add_argument("--project-id", help="Local portal project UUID")
    parser.add_argument("--write", action="store_true", help="Import into local portal Postgres")
    parser.add_argument("--skip-sync-run", action="store_true", help="Do not create integration_sync_runs row")
    args = parser.parse_args()

    try:
        date_range = parse_date_range(args.start_date, args.end_date)
        ga4_config = load_ga4_config()
        raw = Ga4DataClient(ga4_config).run_traffic_overview(date_range)
        normalized = normalize_traffic_overview(raw)
        snapshot = build_traffic_overview_snapshot(normalized, ga4_config.property_resource, date_range)
        validate_snapshot_payload(snapshot)
        out_path = resolve_output_path(args.out, date_range)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outcome = None
        if args.write:
            db_config = load_database_config(args.project_id)
            outcome = import_snapshot(
                db_config.database_url,
                db_config.project_id,
                snapshot,
                create_sync_run=not args.skip_sync_run,
            )
    except (ConfigError, Ga4ClientError, OSError, ValueError) as exc:
        print(f"GA4 pipeline failed safely: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"GA4 pipeline failed safely during local operation: {type(exc).__name__}", file=sys.stderr)
        return 1

    summary = safe_summary(snapshot)
    print(
        "Saved sanitized GA4 snapshot "
        f"to {out_path} with {summary['metric_count']} metrics, "
        f"{summary['dimension_row_count']} channel rows, "
        f"{summary['time_series_count']} trend points."
    )
    if outcome:
        print(f"Imported internal/draft snapshot {outcome.snapshot_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
