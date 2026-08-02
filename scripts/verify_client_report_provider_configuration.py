"""Governed provider configuration and metadata verification for R8-C5.

Two modes. ``offline-validate`` is structural only and needs no credential.
``provider-verify`` performs exactly two metadata calls per profile and is
refused unless an explicit request ceiling and cost ceiling are supplied.

Neither mode retrieves reporting data. Provider transport is imported lazily
inside ``provider-verify`` only, so running the offline mode cannot trigger
authentication merely by importing this module.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import ConfigError
from src.profile_aliases import ProfileAliasError
from src.profile_authorization import (
    ProfileAuthorizationError,
    add_authorized_profile_argument,
    authorize_profile,
)
from src.profile_local_config import load_profile_local_config
from src.provider_configuration_verification import (
    EXECUTION_MODES,
    OFFLINE_MODE,
    PROVIDER_MODE,
    ProviderVerificationError,
    offline_validate,
    plan_group_1,
    provider_verify,
)
from src.provider_verification_budget import ProviderBudgetError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.group_plan:
            plan = plan_group_1(list(args.authorized_profiles or []))
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0 if plan["group_complete"] else 1

        # Authorization first, before configuration loading, before any
        # credential reference is examined, and long before provider access.
        authorization = authorize_profile(args.profile, args.authorized_profiles)

        if args.mode == PROVIDER_MODE and (args.max_requests is None or args.max_cost is None):
            raise ProviderBudgetError(
                "provider-verify requires both --max-requests and --max-cost. "
                "No credential was read and no provider client was constructed."
            )

        ga4_config, gsc_config = _load_non_secret_configuration(authorization.requested_profile)

        if args.mode == OFFLINE_MODE:
            evidence = offline_validate(
                authorization=authorization,
                ga4_config=ga4_config,
                gsc_config=gsc_config,
                repository_root=ROOT,
            )
        else:
            evidence = _run_provider_verify(args, authorization, ga4_config, gsc_config)
    except Exception as exc:  # noqa: BLE001
        # Every failure must leave truthful evidence, including a provider
        # failure raised from inside the transport layer. Catching broadly is
        # deliberate: an uncaught exception would otherwise leave no record of
        # a run that really did consume provider requests.
        message = _sanitize_failure(str(exc))
        print(f"provider configuration verification failed safely: {message}", file=sys.stderr)
        _write_failure_evidence(args, message, type(exc).__name__)
        return 1

    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.evidence_out:
        out = Path(args.evidence_out).resolve(strict=False)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(f"Evidence written to {out}")
    else:
        print(rendered, end="")

    if evidence.get("final_state") in {"structurally_not_ready"}:
        return 1
    return 0


def _sanitize_failure(message: str) -> str:
    """Strip anything path-like or token-like from a failure message."""
    cleaned = re.sub(r"[A-Za-z]:[\\/][^\s'\"]+", "[path removed]", message)
    cleaned = re.sub(r"(?i)(bearer|token|secret|refresh_token)\s*[:=]?\s*\S+", r"\1 [redacted]", cleaned)
    return cleaned


def _write_failure_evidence(args, message: str, error_type: str) -> None:
    """Record a truthful, sanitized failure so a run is never silent.

    States plainly that the run did not succeed, so partial progress can never
    be mistaken for verification.
    """
    if not getattr(args, "evidence_out", None):
        return
    evidence = {
        "evidence_contract": "musimack_provider_configuration_verification.v1",
        "evidence_contract_version": 1,
        "execution_mode": getattr(args, "mode", None),
        "profile": getattr(args, "profile", None),
        "authorized_profiles": list(getattr(args, "authorized_profiles", None) or []),
        "request_ceiling": getattr(args, "max_requests", None),
        "cost_ceiling": getattr(args, "max_cost", None),
        "final_state": "failed",
        "provider_verified": False,
        "group_complete": False,
        "error_type": error_type,
        "stop_reason": message,
        "retries_performed": 0,
        "pagination_performed": 0,
        "reporting_data_requested": False,
    }
    try:
        out = Path(args.evidence_out).resolve(strict=False)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Failure evidence written to {out}", file=sys.stderr)
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that a governed reporting profile is structurally configured and, "
            "when separately authorized, that its GA4 property and Google Search Console "
            "site are reachable. Retrieves no reporting data."
        )
    )
    parser.add_argument("--profile", default=None, help="Requested reporting profile slug or alias.")
    add_authorized_profile_argument(parser)
    parser.add_argument(
        "--mode",
        choices=EXECUTION_MODES,
        default=OFFLINE_MODE,
        help=(
            "offline-validate performs structural checks and builds the call plan with no "
            "credential access. provider-verify performs the planned metadata calls and "
            "requires both numerical ceilings."
        ),
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Approved maximum provider requests for this profile. Required by provider-verify.",
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=None,
        help="Approved maximum direct monetary cost for this profile. Required by provider-verify.",
    )
    parser.add_argument(
        "--evidence-out",
        default=None,
        help="Optional path for the run evidence JSON. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--group-plan",
        action="store_true",
        help=(
            "Print the deterministic R8-C5 Group 1 aggregate plan and exit. Enforces the "
            "approved group totals of 6 requests and $3, rejects a fourth profile, and "
            "refuses to report Group 1 complete when a profile is missing."
        ),
    )
    return parser


def _load_non_secret_configuration(profile: str) -> tuple[dict, dict]:
    """Load non-secret provider configuration for one profile.

    Deliberately uses ``as_safe_dict``, which strips every ``_resolved_`` key.
    The loader itself expands some environment variables into resolved paths;
    those resolved values are dropped here so that offline validation sees
    credential *reference names and shapes* only, never a resolved secret path.
    No credential file is opened.
    """
    providers = load_profile_local_config(profile).as_safe_dict().get("providers") or {}
    return dict(providers.get("ga4") or {}), dict(providers.get("gsc") or {})


def _run_provider_verify(args, authorization, ga4_config, gsc_config) -> dict:
    """Provider mode, wired against David's approved envelope.

    The ceilings are approved, so this now reaches ``provider_verify`` rather
    than refusing at the CLI. Every guard still runs before a credential is
    touched: authorization, structural validation, the exact approved plan,
    and both exact ceilings.

    Credential resolution and provider construction are passed as callables and
    are therefore reached only if every preceding guard has already passed:
    authorization, structural validation, the approved-plan guard, and both
    exact ceilings.
    """
    return provider_verify(
        authorization=authorization,
        ga4_config=ga4_config,
        gsc_config=gsc_config,
        repository_root=ROOT,
        max_requests=args.max_requests,
        max_cost=args.max_cost,
        resolve_credentials=_credential_resolver(authorization.requested_profile),
        build_ga4_client=_build_ga4_metadata_client,
        build_gsc_client=_build_gsc_metadata_client,
    )


def _credential_resolver(profile: str):
    """Resolve credential *references* for one profile.

    Returns references, never contents, and opens no file. Reached only after
    every preceding guard has passed.
    """

    def resolve():
        from src.provider_metadata_clients import credential_references

        return {
            "ga4": credential_references(profile, "ga4"),
            "gsc": credential_references(profile, "gsc"),
        }

    return resolve


def _build_ga4_metadata_client(credentials):
    """Construct the metadata-only GA4 client.

    Imported lazily, so the offline path never loads provider transport.
    """
    from src.provider_metadata_clients import Ga4MetadataClient

    secrets, token = credentials["ga4"]
    return Ga4MetadataClient(secrets, token)


def _build_gsc_metadata_client(credentials):
    from src.provider_metadata_clients import GscSiteMetadataClient

    secrets, token = credentials["gsc"]
    return GscSiteMetadataClient(secrets, token)


if __name__ == "__main__":
    raise SystemExit(main())
