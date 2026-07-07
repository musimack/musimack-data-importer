from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError, add_date_args, load_ga4_config, parse_date_range, resolve_output_path
from src.ga4_client import Ga4DataClient, Ga4ClientError
from src.normalize import normalize_traffic_overview
from src.snapshot_builder import build_traffic_overview_snapshot
from src.validate import safe_summary, validate_snapshot_payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Musimack GA4 traffic overview JSON.")
    add_date_args(parser)
    parser.add_argument("--profile", help="Dashboard-lab profile slug for per-profile local config.")
    parser.add_argument("--out", help="Output JSON path, defaults under exports/")
    parser.add_argument(
        "--real-output",
        action="store_true",
        help="With --profile, write ga4-snapshot.json under ignored exports/local-real/dashboard-lab/{profile}/.",
    )
    args = parser.parse_args()

    try:
        if args.real_output and not args.profile:
            raise ConfigError("--profile is required with --real-output")
        date_range = parse_date_range(args.start_date, args.end_date)
        config = load_ga4_config(args.profile)
        raw = Ga4DataClient(config).run_traffic_overview(date_range)
        normalized = normalize_traffic_overview(raw)
        snapshot = build_traffic_overview_snapshot(
            normalized=normalized,
            property_resource=config.property_resource,
            date_range=date_range,
        )
        validate_snapshot_payload(snapshot)
        out_path = _resolve_ga4_output_path(args.profile, args.out, args.real_output, date_range)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ConfigError, Ga4ClientError, OSError, ValueError) as exc:
        print(f"GA4 export failed safely: {exc}", file=sys.stderr)
        return 1

    summary = safe_summary(snapshot)
    print(
        "Saved sanitized GA4 snapshot "
        f"to {out_path} with {summary['metric_count']} metrics, "
        f"{summary['dimension_row_count']} dimension rows, "
        f"{summary['time_series_count']} trend points."
    )
    return 0


def _resolve_ga4_output_path(profile: str | None, out: str | None, real_output: bool, date_range) -> Path:
    if out:
        return Path(out)
    if real_output and profile:
        return Path("exports") / "local-real" / "dashboard-lab" / profile / "ga4-snapshot.json"
    return resolve_output_path(out, date_range)


if __name__ == "__main__":
    raise SystemExit(main())
