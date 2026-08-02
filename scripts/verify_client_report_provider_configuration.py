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
    except (
        ProfileAuthorizationError,
        ProviderBudgetError,
        ProviderVerificationError,
        ProfileAliasError,
        ConfigError,
        OSError,
        ValueError,
    ) as exc:
        print(f"provider configuration verification failed safely: {exc}", file=sys.stderr)
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
    are therefore reached only if every preceding guard has already passed. The
    two builders below remain unimplemented in this package, because the
    credentialed run is a separately authorized step.
    """
    return provider_verify(
        authorization=authorization,
        ga4_config=ga4_config,
        gsc_config=gsc_config,
        repository_root=ROOT,
        max_requests=args.max_requests,
        max_cost=args.max_cost,
        resolve_credentials=_resolve_credentials,
        build_ga4_client=_build_ga4_metadata_client,
        build_gsc_client=_build_gsc_metadata_client,
    )


def _resolve_credentials():
    """Reached only after authorization, structure, plan, and both ceilings pass.

    Deliberately not implemented here. David approved the numerical ceilings,
    but the credentialed run is a separate authorized step and all three Group 1
    profiles are still structurally not ready.
    """
    raise ProviderVerificationError(
        "credential resolution is not implemented in this configuration-readiness package. "
        "The approved ceilings authorize the limits of a later credentialed run, not the run "
        "itself. No credential was read and no provider client was constructed."
    )


def _build_ga4_metadata_client(_credentials):
    raise ProviderVerificationError(
        "GA4 metadata client construction is not authorized in this package"
    )


def _build_gsc_metadata_client(_credentials):
    raise ProviderVerificationError(
        "GSC metadata client construction is not authorized in this package"
    )


if __name__ == "__main__":
    raise SystemExit(main())
