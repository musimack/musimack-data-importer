from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError, parse_date_range
from src.local_config import load_local_operator_config
from src.providers.gsc.client import (
    DEFAULT_GSC_TOKEN_FILE,
    GscClientError,
    GscFetchConfig,
    GscOAuthError,
    GscSearchConsoleClient,
)
from src.providers.gsc.summary import (
    GscSummaryError,
    build_gsc_summary,
    real_output_dir,
    validate_gsc_output_dir,
    write_gsc_dashboard_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch local-only Google Search Console data for dashboard-lab summaries."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab fixture profile slug.")
    parser.add_argument("--site-url", help="Exact Search Console property URL, such as https://example.com/.")
    parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--out", help="Output directory for dashboard-lab JSON files.")
    parser.add_argument(
        "--real-output",
        action="store_true",
        help="Use the ignored exports/local-real/dashboard-lab/{profile} output folder.",
    )
    parser.add_argument("--credentials", help="OAuth client secrets JSON path. Value is never printed.")
    parser.add_argument("--token", help="Separate GSC OAuth token cache path. Value is never printed.")
    parser.add_argument("--row-limit", type=int, default=25000, help="Search Analytics row limit.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing GSC output files without OAuth or API calls.",
    )
    args = parser.parse_args()

    try:
        output_dir = resolve_output_dir(args.profile, args.out, args.real_output)
        if args.validate_only:
            files = validate_gsc_output_dir(output_dir, args.profile)
            print(f"Validated GSC dashboard-lab output directory: {output_dir}")
            for path in files:
                print(f"- {path}")
            return 0

        if not args.site_url:
            raise ConfigError("--site-url is required unless --validate-only is used")
        date_range = parse_date_range(args.start_date, args.end_date)
        if args.row_limit < 1 or args.row_limit > 25000:
            raise ConfigError("--row-limit must be between 1 and 25000")

        load_local_operator_config()
        credentials_path = args.credentials or os.environ.get("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS")
        if not credentials_path:
            raise ConfigError("MUSIMACK_GSC_OAUTH_CLIENT_SECRETS is required unless --credentials is provided")
        token_path = args.token or os.environ.get("MUSIMACK_GSC_OAUTH_TOKEN_FILE") or str(DEFAULT_GSC_TOKEN_FILE)

        client = GscSearchConsoleClient(
            GscFetchConfig(
                client_secrets_file=credentials_path,
                token_file=token_path,
                site_url=args.site_url,
                row_limit=args.row_limit,
            )
        )
        response = client.query_search_analytics(
            date_range.start.isoformat(),
            date_range.end.isoformat(),
        )
        summary = build_gsc_summary(
            args.profile,
            args.site_url,
            date_range.start.isoformat(),
            date_range.end.isoformat(),
            response,
        )
        files = write_gsc_dashboard_outputs(output_dir, summary)
    except (ConfigError, GscClientError, GscOAuthError, GscSummaryError, OSError) as exc:
        print(f"GSC fetch failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"Fetched GSC dashboard-lab summary for profile '{args.profile}' into: {output_dir}")
    for path in files:
        print(f"- {path}")
    print("GSC OAuth values, token contents, client secrets, and credential paths were not written to output JSON.")
    return 0


def resolve_output_dir(profile: str, out: str | None, real_output: bool) -> Path:
    if out:
        return Path(out)
    if real_output:
        return real_output_dir(profile)
    raise ConfigError("--out is required unless --real-output is used")


if __name__ == "__main__":
    raise SystemExit(main())
