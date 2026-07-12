from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_ga4_ranked_exact_range_provider import (
    build_all_ga4_ranked_exact_ranges_from_provider,
)
from src.config import ConfigError, load_ga4_config
from src.ga4_client import Ga4ClientError, Ga4DataClient
from src.profile_aliases import ProfileAliasError, resolve_profile_slug


DEFAULT_REPORT_START = date(2026, 1, 1)
DEFAULT_REPORT_END = date(2026, 7, 8)
AUTHORIZED_PROFILE = "aluma-seo-geo"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull real GA4 ranked exact-range data for Client Report Publisher range QA."
    )
    parser.add_argument("--profile", required=True, help="Authorized dashboard-lab profile slug or alias.")
    parser.add_argument("--report-start-date", default=DEFAULT_REPORT_START.isoformat())
    parser.add_argument("--report-end-date", default=DEFAULT_REPORT_END.isoformat())
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument(
        "--real-output",
        action="store_true",
        help="Write ranked exact-range files under ignored exports/local-real/dashboard-lab/{profile}/.",
    )
    parser.add_argument("--out-dir", help="Output folder for ranked exact-range JSON files.")
    args = parser.parse_args()

    try:
        canonical_profile = resolve_profile_slug(args.profile)
        if canonical_profile != AUTHORIZED_PROFILE:
            raise ConfigError("this controlled milestone is authorized only for aluma-seo-geo")
        if args.real_output and args.out_dir:
            raise ConfigError("--real-output and --out-dir cannot be combined")
        report_start = _parse_date(args.report_start_date, "--report-start-date")
        report_end = _parse_date(args.report_end_date, "--report-end-date")
        config = load_ga4_config(args.profile)
        payloads = build_all_ga4_ranked_exact_ranges_from_provider(
            client=Ga4DataClient(config),
            profile=canonical_profile,
            report_period_start=report_start,
            report_period_end=report_end,
            timezone=args.timezone,
        )
        output_dir = _resolve_output_dir(canonical_profile, args.out_dir, args.real_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        for schema_version, payload in payloads.items():
            (output_dir / f"{schema_version}.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (ConfigError, Ga4ClientError, ProfileAliasError, OSError, ValueError) as exc:
        print(f"GA4 ranked exact-range export failed safely: {exc}", file=sys.stderr)
        return 1

    available = sum(
        1
        for payload in payloads.values()
        for item in payload["ranges"]
        if item.get("data_state") == "available"
    )
    empty = sum(
        1
        for payload in payloads.values()
        for item in payload["ranges"]
        if item.get("data_state") == "empty"
    )
    print(f"Saved sanitized GA4 ranked exact-range datasets to {output_dir}.")
    print(f"Contracts: {len(payloads)}; ranges: {len(payloads) * 4}; available: {available}; empty: {empty}.")
    print("GA4 Data API call count: 16 expected ranked calls; no GSC, BigQuery, or portal provider calls were made by this script.")
    print("Output contains sanitized ranked rows only; credentials, tokens, raw provider payloads, and property ids were not written.")
    return 0


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{label} must use YYYY-MM-DD format") from exc


def _resolve_output_dir(profile: str, out_dir: str | None, real_output: bool) -> Path:
    if out_dir:
        return Path(out_dir)
    if real_output:
        return Path("exports") / "local-real" / "dashboard-lab" / profile
    return Path("exports") / f"{profile}_ga4_ranked_exact_ranges"


if __name__ == "__main__":
    raise SystemExit(main())
