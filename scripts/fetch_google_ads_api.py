from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_lab.paid_callrail_validators import DashboardLabFixtureValidationError
from src.providers.google_ads.client import GoogleAdsClientDependencyError, GoogleAdsReadOnlyClient, GoogleAdsReadOnlyQueryError
from src.providers.google_ads.config import GoogleAdsConfigError, check_google_ads_readiness, load_google_ads_local_config
from src.providers.google_ads.export_plan import build_google_ads_export_plan
from src.providers.google_ads.normalize import (
    normalize_campaign_rows,
    normalize_keyword_rows,
    normalize_landing_page_rows,
    normalize_search_term_rows,
    normalize_time_series,
)
from src.providers.google_ads.queries import (
    build_campaign_performance_query,
    build_keyword_performance_query,
    build_landing_page_performance_query,
    build_search_term_performance_query,
    build_time_series_query,
)
from src.providers.google_ads.summary import build_google_ads_summary_payload, write_google_ads_summary


DEFAULT_OUTPUT_ROOT = Path("exports") / "local-real" / "dashboard-lab"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a safe local Google Ads API export plan without making live API calls."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab technical profile slug.")
    parser.add_argument(
        "--customer-id",
        nargs="?",
        const="",
        help="Google Ads customer id. Presence is tracked, value is never printed.",
    )
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--login-customer-id", help="Optional manager account id. Value is never printed.")
    parser.add_argument("--developer-token-env", default="GOOGLE_ADS_DEVELOPER_TOKEN")
    parser.add_argument("--oauth-client-secrets-env", default="GOOGLE_ADS_OAUTH_CLIENT_SECRETS")
    parser.add_argument("--oauth-token-file-env", default="GOOGLE_ADS_OAUTH_TOKEN_FILE")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--callrail-summary", help="Optional aggregate CallRail summary path for a future join.")
    parser.add_argument("--granularity", choices=["daily", "weekly", "monthly"], default="monthly")
    parser.add_argument("--real-output", action="store_true", help="Required before any future local-real write.")
    parser.add_argument("--dry-run", action="store_true", help="Print a sanitized plan and make no API calls.")
    parser.add_argument("--validate-only", action="store_true", help="Reserved for a future implementation.")
    args = parser.parse_args()

    readiness = check_google_ads_readiness(
        profile=args.profile,
        customer_id=args.customer_id,
        login_customer_id=args.login_customer_id,
        developer_token_env=args.developer_token_env,
        oauth_client_secrets_env=args.oauth_client_secrets_env,
        oauth_token_file_env=args.oauth_token_file_env,
    )
    plan = build_google_ads_export_plan(
        profile=args.profile,
        start_date=args.start_date,
        end_date=args.end_date,
        granularity=args.granularity,
        output_root=Path(args.output_root),
        real_output=args.real_output,
        readiness=readiness,
    )

    if args.dry_run:
        for line in plan.safe_lines():
            print(line)
        if args.callrail_summary:
            print(f"Future CallRail aggregate join input: {args.callrail_summary}")
        return 0

    if not args.real_output:
        print("Google Ads API export failed safely: --real-output is required before any future local-real write.", file=sys.stderr)
        return 1
    if not readiness.ready:
        missing = ", ".join(readiness.missing)
        print(f"Google Ads API export failed safely: missing required local configuration: {missing}", file=sys.stderr)
        return 1
    if not _is_local_real_output(Path(args.output_root)):
        print(
            "Google Ads API export failed safely: real output must stay under exports/local-real/dashboard-lab.",
            file=sys.stderr,
        )
        return 1

    try:
        local_config = load_google_ads_local_config(
            profile=args.profile,
            customer_id=args.customer_id,
            login_customer_id=args.login_customer_id,
            developer_token_env=args.developer_token_env,
            oauth_client_secrets_env=args.oauth_client_secrets_env,
            oauth_token_file_env=args.oauth_token_file_env,
        )
        client = GoogleAdsReadOnlyClient(local_config)
        campaign_rows = normalize_campaign_rows(
            _run_query_area(
                client,
                local_config.customer_id,
                "campaign performance",
                build_campaign_performance_query(args.start_date, args.end_date),
            )
        )
        keyword_rows = normalize_keyword_rows(
            _run_query_area(
                client,
                local_config.customer_id,
                "keyword performance",
                build_keyword_performance_query(args.start_date, args.end_date),
            )
        )
        search_term_rows = normalize_search_term_rows(
            _run_query_area(
                client,
                local_config.customer_id,
                "search term performance",
                build_search_term_performance_query(args.start_date, args.end_date),
            )
        )
        landing_page_rows = normalize_landing_page_rows(
            _run_query_area(
                client,
                local_config.customer_id,
                "landing page performance",
                build_landing_page_performance_query(args.start_date, args.end_date),
            )
        )
        time_series = normalize_time_series(
            _run_query_area(
                client,
                local_config.customer_id,
                "time series",
                build_time_series_query(args.start_date, args.end_date),
            )
        )
        payload = build_google_ads_summary_payload(
            profile=args.profile,
            start_date=args.start_date,
            end_date=args.end_date,
            campaign_rows=campaign_rows,
            keyword_rows=keyword_rows,
            search_term_rows=search_term_rows,
            landing_page_rows=landing_page_rows,
            time_series=time_series,
            data_quality_notes=[
                "Read-only Google Ads API reporting pull.",
                "No Google Ads mutate, upload, bid, budget, campaign, keyword, ad, asset, conversion, billing, or account setting operations are performed.",
                "Dashboard-lab copy remains a separate guarded operator step.",
            ],
        )
        if args.validate_only:
            print("Validated Google Ads API aggregate payload")
            print(f"Future output: {plan.output_path}")
            return 0
        write_google_ads_summary(plan.output_path, payload)
    except (
        GoogleAdsConfigError,
        GoogleAdsClientDependencyError,
        GoogleAdsReadOnlyQueryError,
        DashboardLabFixtureValidationError,
        OSError,
    ) as exc:
        print(f"Google Ads API export failed safely: {exc}", file=sys.stderr)
        return 1

    print("Google Ads API aggregate export written")
    print(f"Profile: {args.profile}")
    print(f"Output: {plan.output_path}")
    print(f"Validation: python scripts/validate_google_ads_summary.py --input {plan.output_path}")
    print("No Google Ads mutations or uploads were performed.")
    return 0


def _is_local_real_output(path: Path) -> bool:
    normalized = path.as_posix().strip("/")
    return normalized == "exports/local-real/dashboard-lab" or normalized.startswith("exports/local-real/dashboard-lab/")


def _run_query_area(
    client: GoogleAdsReadOnlyClient,
    customer_id: str,
    query_area: str,
    query: str,
) -> list[dict]:
    try:
        return client.run_gaql_query(customer_id, query)
    except GoogleAdsReadOnlyQueryError as exc:
        raise GoogleAdsReadOnlyQueryError(f"{query_area}: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
