from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_ga4_exact_range_provider import build_ga4_exact_range_summary_from_provider
from src.config import ConfigError, load_ga4_config
from src.ga4_client import Ga4ClientError, Ga4DataClient
from src.profile_aliases import ProfileAliasError, resolve_profile_slug


DEFAULT_REPORT_START = date(2026, 1, 1)
DEFAULT_REPORT_END = date(2026, 7, 8)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull real GA4 exact-range summary data for Client Report Publisher range QA."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug or alias.")
    parser.add_argument("--report-start-date", default=DEFAULT_REPORT_START.isoformat())
    parser.add_argument("--report-end-date", default=DEFAULT_REPORT_END.isoformat())
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument(
        "--real-output",
        action="store_true",
        help="Write ga4_metric_display_exact_ranges.v1.json under ignored exports/local-real/dashboard-lab/{profile}/.",
    )
    parser.add_argument("--out", help="Output JSON path.")
    args = parser.parse_args()

    try:
        if args.real_output and args.out:
            raise ConfigError("--real-output and --out cannot be combined")
        canonical_profile = resolve_profile_slug(args.profile)
        report_start = _parse_date(args.report_start_date, "--report-start-date")
        report_end = _parse_date(args.report_end_date, "--report-end-date")
        config = load_ga4_config(args.profile)
        payload = build_ga4_exact_range_summary_from_provider(
            client=Ga4DataClient(config),
            profile=canonical_profile,
            report_period_start=report_start,
            report_period_end=report_end,
            timezone=args.timezone,
        )
        out_path = _resolve_output_path(canonical_profile, args.out, args.real_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ConfigError, Ga4ClientError, ProfileAliasError, OSError, ValueError) as exc:
        print(f"GA4 exact-range summary export failed safely: {exc}", file=sys.stderr)
        return 1

    available = sum(1 for item in payload["ranges"] if item.get("data_state") == "available")
    empty = sum(1 for item in payload["ranges"] if item.get("data_state") == "empty")
    print(f"Saved sanitized GA4 exact-range summary to {out_path}.")
    print(f"Ranges: {len(payload['ranges'])}; available: {available}; empty: {empty}.")
    print("Output contains sanitized metric summaries only; credentials, tokens, raw provider payloads, and property ids were not written.")
    return 0


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{label} must use YYYY-MM-DD format") from exc


def _resolve_output_path(profile: str, out: str | None, real_output: bool) -> Path:
    if out:
        return Path(out)
    if real_output:
        return Path("exports") / "local-real" / "dashboard-lab" / profile / "ga4_metric_display_exact_ranges.v1.json"
    return Path("exports") / f"{profile}_ga4_metric_display_exact_ranges.v1.json"


if __name__ == "__main__":
    raise SystemExit(main())
