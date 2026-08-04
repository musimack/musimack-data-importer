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
from src.client_report_presentation_comparison_resume import (
    ComparisonCheckpointStore,
    ComparisonResumeError,
    ComparisonRunIdentity,
    assert_no_secret_material,
    provider_configuration_fingerprint,
)
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
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help=(
            "Directory holding durable per-preset state. When supplied, presets "
            "already completed under this exact run identity are reused instead "
            "of being requested again. Restarting the command is an explicit "
            "operator action; nothing is ever re-issued automatically."
        ),
    )
    args = parser.parse_args()
    # Held outside the try so a failed run can still state what it spent. A
    # partial run consumes real provider requests, and a defect report that
    # cannot say how many is not an accounting record. `provider_calls` counts
    # only what this run newly issued; `restored_calls` counts what a prior run
    # already paid for. They are never conflated.
    provider_calls: dict[str, int] = {"ga4": 0, "gsc": 0}
    restored_calls: dict[str, int] = {"ga4": 0, "gsc": 0}
    try:
        # Authorization first, before any output check, credential lookup, or
        # provider-client construction. A refused run never reads a secret.
        authorization = authorize_profile(args.profile, args.authorized_profiles)
        profile = authorization.requested_profile
        output = Path(args.out).resolve(strict=False)
        if not _is_ignored_real_output(output):
            raise ConfigError("R4 real comparison output must stay under ignored exports/local-real")
        load_local_operator_config()
        ga4_config = load_ga4_config(args.profile)
        ga4_client = Ga4DataClient(ga4_config)
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
        report_start = date.fromisoformat(args.report_start_date)
        report_end = date.fromisoformat(args.report_end_date)
        gsc_available_through = date.fromisoformat(args.gsc_available_through_date)
        checkpoint = ComparisonCheckpointStore(
            _checkpoint_directory(args.checkpoint_dir),
            ComparisonRunIdentity(
                profile=profile,
                report_id=args.report_id,
                client_id=args.client_id,
                project_id=args.project_id,
                report_start=report_start,
                report_end=report_end,
                gsc_available_through=gsc_available_through,
                # Hashed, never written in the clear: partial state must bind to
                # the provider configuration without disclosing it.
                provider_configuration_fingerprint=provider_configuration_fingerprint(
                    ga4_property_id=ga4_config.property_id,
                    gsc_site_url=str(site_url),
                ),
            ),
        )
        package = build_real_presentation_comparisons(
            ga4_client=ga4_client,
            gsc_client=gsc_client,
            profile=profile,
            report_id=args.report_id,
            client_id=args.client_id,
            project_id=args.project_id,
            report_start=report_start,
            report_end=report_end,
            gsc_available_through=gsc_available_through,
            authorization=authorization,
            provider_calls=provider_calls,
            checkpoint=checkpoint,
            restored_calls=restored_calls,
        )
        # Final artifacts are secret-scanned exactly as partial ones are.
        assert_no_secret_material(package, label="comparison contract")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (ConfigError, ProfileAuthorizationError, ProfileAliasError, Ga4ClientError, GscClientError, GscOAuthError, ComparisonResumeError, OSError, ValueError) as exc:
        print(f"R4 comparison retrieval failed safely: {exc}", file=sys.stderr)
        consumed = provider_calls.get("ga4", 0) + provider_calls.get("gsc", 0)
        prior = restored_calls.get("ga4", 0) + restored_calls.get("gsc", 0)
        print(
            f"Provider requests newly consumed by this run before the failure: {consumed} "
            f"(GA4 {provider_calls.get('ga4', 0)}, GSC {provider_calls.get('gsc', 0)}). "
            f"Requests reused from prior runs, not re-issued: {prior}. "
            "No output file was written.",
            file=sys.stderr,
        )
        print(
            "Completed presets remain durably recorded. Restarting this command "
            "is an explicit operator action and resumes at the next incomplete "
            "preset; nothing is retried automatically.",
            file=sys.stderr,
        )
        return 1
    entries = package["comparisons"]
    eligible = sum(1 for entry in entries if entry["delta_eligible"])
    print(f"Saved sanitized R4 comparisons for {profile} to ignored local real output.")
    print(f"Authorization contract: {authorization.contract}; authorized profiles: {', '.join(authorization.authorized_profiles)}.")
    print(f"Comparison entries: {len(entries)}; delta-eligible: {eligible}; withheld: {len(entries) - eligible}.")
    print(f"GA4 calls: {package['source_identity']['ga4_provider_calls']}; GSC calls: {package['source_identity']['gsc_provider_calls']}.")
    new_total = provider_calls["ga4"] + provider_calls["gsc"]
    prior_total = restored_calls["ga4"] + restored_calls["gsc"]
    print(
        f"Request accounting: newly consumed by this run {new_total} "
        f"(GA4 {provider_calls['ga4']}, GSC {provider_calls['gsc']}); "
        f"reused from prior runs and not re-issued {prior_total} "
        f"(GA4 {restored_calls['ga4']}, GSC {restored_calls['gsc']}); "
        f"cumulative {new_total + prior_total}."
    )
    print("No credentials, provider identifiers, raw payloads, or secret paths were written or printed.")
    return 0


def _checkpoint_directory(value: str | None) -> Path | None:
    """Resolve the durable state directory, or None to run without resume.

    Partial state holds the same sanitized comparison entries as the final
    artifact, so it is held to the same containment rule: it must stay under
    the ignored real-output tree and can never be committed.
    """
    if value is None:
        return None
    directory = Path(value).resolve(strict=False)
    if not _is_ignored_real_output(directory):
        raise ConfigError("comparison checkpoint state must stay under ignored exports/local-real")
    return directory


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
