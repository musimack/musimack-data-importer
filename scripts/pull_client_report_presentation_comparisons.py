from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_presentation_comparison_provider import build_real_presentation_comparisons
from src.config import ConfigError, load_ga4_config
from src.ga4_client import Ga4ClientError, Ga4DataClient
from src.local_config import load_local_operator_config
from src.profile_aliases import ProfileAliasError, resolve_profile_slug
from src.profile_authorization import (
    ProfileAuthorizationError,
    add_authorized_profile_argument,
    authorize_profile,
)
from src.profile_local_config import load_profile_local_config
from src.providers.gsc.client import DEFAULT_GSC_TOKEN_FILE, GscClientError, GscFetchConfig, GscOAuthError, GscSearchConsoleClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull bounded provider-backed R4 presentation comparisons for the retained local report.")
    parser.add_argument("--profile", required=True)
    add_authorized_profile_argument(parser)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--report-start-date", required=True)
    parser.add_argument("--report-end-date", required=True)
    parser.add_argument("--gsc-available-through-date", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    # Held outside the try so a failed run can still state what it spent. A
    # partial run consumes real provider requests, and a defect report that
    # cannot say how many is not an accounting record.
    provider_calls: dict[str, int] = {"ga4": 0, "gsc": 0}
    try:
        # Authorization first, before any output check, credential lookup, or
        # provider-client construction. A refused run never reads a secret.
        authorization = authorize_profile(args.profile, args.authorized_profiles)
        profile = authorization.requested_profile
        output = Path(args.out).resolve(strict=False)
        if not _is_ignored_real_output(output):
            raise ConfigError("R4 real comparison output must stay under ignored exports/local-real")
        load_local_operator_config()
        ga4_client = Ga4DataClient(load_ga4_config(args.profile))
        provider = load_profile_local_config(args.profile).provider("gsc")
        site_url = provider.get("_resolved_site_url") or provider.get("_safe_site_url")
        credentials_env = str(provider.get("oauth_client_secrets_env") or "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS")
        token_env = str(provider.get("oauth_token_file_env") or "MUSIMACK_GSC_OAUTH_TOKEN_FILE")
        credentials = provider.get("_resolved_oauth_client_secrets_file") or os.environ.get(credentials_env)
        token = provider.get("_resolved_oauth_token_file") or os.environ.get(token_env) or str(DEFAULT_GSC_TOKEN_FILE)
        if not site_url or not credentials:
            raise ConfigError("configured GSC site and OAuth client secrets are required")
        _reject_repo_secret_path(str(credentials), "GSC OAuth client secrets")
        _reject_repo_secret_path(str(token), "GSC OAuth token")
        gsc_client = GscSearchConsoleClient(GscFetchConfig(str(credentials), str(token), str(site_url)))
        package = build_real_presentation_comparisons(
            ga4_client=ga4_client,
            gsc_client=gsc_client,
            profile=profile,
            report_id=args.report_id,
            client_id=args.client_id,
            project_id=args.project_id,
            report_start=date.fromisoformat(args.report_start_date),
            report_end=date.fromisoformat(args.report_end_date),
            gsc_available_through=date.fromisoformat(args.gsc_available_through_date),
            authorization=authorization,
            provider_calls=provider_calls,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ConfigError, ProfileAuthorizationError, ProfileAliasError, Ga4ClientError, GscClientError, GscOAuthError, OSError, ValueError) as exc:
        print(f"R4 comparison retrieval failed safely: {exc}", file=sys.stderr)
        consumed = provider_calls.get("ga4", 0) + provider_calls.get("gsc", 0)
        print(
            f"Provider requests consumed before the failure: {consumed} "
            f"(GA4 {provider_calls.get('ga4', 0)}, GSC {provider_calls.get('gsc', 0)}). "
            "No output file was written.",
            file=sys.stderr,
        )
        return 1
    entries = package["comparisons"]
    eligible = sum(1 for entry in entries if entry["delta_eligible"])
    print(f"Saved sanitized R4 comparisons for {profile} to ignored local real output.")
    print(f"Authorization contract: {authorization.contract}; authorized profiles: {', '.join(authorization.authorized_profiles)}.")
    print(f"Comparison entries: {len(entries)}; delta-eligible: {eligible}; withheld: {len(entries) - eligible}.")
    print(f"GA4 calls: {package['source_identity']['ga4_provider_calls']}; GSC calls: {package['source_identity']['gsc_provider_calls']}.")
    print("No credentials, provider identifiers, raw payloads, or secret paths were written or printed.")
    return 0


def _is_ignored_real_output(path: Path) -> bool:
    try:
        path.relative_to((ROOT / "exports" / "local-real").resolve(strict=False))
        return True
    except ValueError:
        return False


def _reject_repo_secret_path(value: str, label: str) -> None:
    try:
        Path(value).expanduser().resolve(strict=False).relative_to(ROOT.resolve(strict=False))
    except ValueError:
        return
    raise ConfigError(f"{label} path must stay outside the repository")


if __name__ == "__main__":
    raise SystemExit(main())
