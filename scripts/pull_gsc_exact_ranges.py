from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client_report_gsc_exact_range_provider import build_all_gsc_exact_ranges_from_provider
from src.config import ConfigError
from src.local_config import load_local_operator_config
from src.profile_aliases import ProfileAliasError, resolve_profile_slug
from src.profile_local_config import load_profile_local_config
from src.providers.gsc.client import DEFAULT_GSC_TOKEN_FILE, GscClientError, GscFetchConfig, GscOAuthError, GscSearchConsoleClient
from src.providers.gsc.summary import real_output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate sanitized provider-backed GSC exact-range contracts.")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report-start-date", required=True)
    parser.add_argument("--report-end-date", required=True)
    parser.add_argument("--available-through-date")
    parser.add_argument("--out-dir")
    parser.add_argument("--real-output", action="store_true")
    args = parser.parse_args()
    try:
        profile = resolve_profile_slug(args.profile)
        if profile != "aluma-seo-geo":
            raise ConfigError("controlled GSC exact-range generation is limited to aluma-seo-geo")
        output = Path(args.out_dir) if args.out_dir else real_output_dir(profile)
        if not args.out_dir and not args.real_output:
            raise ConfigError("--out-dir or --real-output is required")
        existing_summary = _read_object(output / "gsc-summary.json")
        available_through = args.available_through_date or _latest_observation_date(existing_summary)
        if not available_through:
            raise ConfigError("available-through date is required or must resolve from existing GSC daily observations")
        load_local_operator_config()
        provider = load_profile_local_config(args.profile).provider("gsc")
        site_url = provider.get("_resolved_site_url") or provider.get("_safe_site_url")
        if not site_url:
            raise ConfigError("configured GSC site URL is required")
        credentials_env = str(provider.get("oauth_client_secrets_env") or "MUSIMACK_GSC_OAUTH_CLIENT_SECRETS")
        token_env = str(provider.get("oauth_token_file_env") or "MUSIMACK_GSC_OAUTH_TOKEN_FILE")
        credentials = provider.get("_resolved_oauth_client_secrets_file") or os.environ.get(credentials_env)
        token = provider.get("_resolved_oauth_token_file") or os.environ.get(token_env) or str(DEFAULT_GSC_TOKEN_FILE)
        if not credentials:
            raise ConfigError(f"{credentials_env} is required")
        _reject_repo_path(str(credentials), "GSC OAuth client secrets")
        _reject_repo_path(str(token), "GSC OAuth token")
        client = GscSearchConsoleClient(GscFetchConfig(str(credentials), str(token), str(site_url)))
        datasets = build_all_gsc_exact_ranges_from_provider(
            client,
            client_slug=profile,
            report_start=args.report_start_date,
            report_end=args.report_end_date,
            available_through_date=available_through,
        )
        output.mkdir(parents=True, exist_ok=True)
        for schema, payload in datasets.items():
            (output / f"{schema}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except (ConfigError, ProfileAliasError, GscClientError, GscOAuthError, OSError, ValueError) as exc:
        print(f"GSC exact-range generation failed safely: {exc}", file=sys.stderr)
        return 1
    calls = sum(int(item["generation_metadata"]["provider_calls"]) for item in datasets.values())
    counts = {state: sum(1 for payload in datasets.values() for item in payload["ranges"] if item["data_state"] == state) for state in ("available", "partial", "empty", "unavailable")}
    print(f"Generated GSC exact-range contracts for profile: {profile}")
    print(f"Output category: ignored local real output; contracts: {len(datasets)}; provider calls: {calls}")
    print("Range states: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    print("Credential values, property identifiers, raw provider payloads, and local secret paths were not written or printed.")
    return 0


def _read_object(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _latest_observation_date(payload: dict) -> str | None:
    dates = [row.get("date") for row in payload.get("time_series", []) if isinstance(row, dict) and isinstance(row.get("date"), str)]
    return max(dates) if dates else None


def _reject_repo_path(value: str, label: str) -> None:
    try:
        Path(value).expanduser().resolve(strict=False).relative_to(ROOT.resolve(strict=False))
    except ValueError:
        return
    raise ConfigError(f"{label} path must stay outside the repository")


if __name__ == "__main__":
    raise SystemExit(main())
