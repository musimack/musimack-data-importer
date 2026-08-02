"""Governed provider configuration and metadata verification.

Establishes whether a configured importer profile can truthfully proceed to
later R8-C5 reporting generation. It answers one question per profile: is the
configuration structurally complete, and can the configured GA4 property and
Google Search Console site actually be reached?

It deliberately answers nothing about reporting data. No metric, dimension,
date range, ranked row, trend, or comparison is ever requested, and the two
supported operations are incapable of returning any.

Two modes, with a hard boundary between them:

``offline-validate``
    Structural only. Reads non-secret profile configuration, checks that
    credential *references* are present and safely located, and builds the
    exact provider-call plan. **Never opens a credential file, never resolves a
    secret environment value, never constructs a provider client, and never
    makes a network call.**

``provider-verify``
    Implemented here but not executed under the current authorization. Requires
    an approved request ceiling and cost ceiling, validates the plan against
    both *before* touching credentials, then performs exactly the planned
    metadata calls through an injected client.

Provider clients are always injected. This module imports no provider
transport, so importing it cannot trigger authentication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from src.profile_authorization import ProfileAuthorization
from src.provider_verification_budget import (
    CostBudget,
    ProviderBudgetError,
    RequestBudget,
    expected_direct_cost,
)

EVIDENCE_CONTRACT = "musimack_provider_configuration_verification.v1"
EVIDENCE_CONTRACT_VERSION = 1

OFFLINE_MODE = "offline-validate"
PROVIDER_MODE = "provider-verify"
EXECUTION_MODES = (OFFLINE_MODE, PROVIDER_MODE)

# The exact supported operations. Each is a single GET that returns
# configuration metadata and cannot return reporting data.
#
#   ga4.properties.getMetadata
#       GET analyticsdata.googleapis.com/v1beta/properties/{id}/metadata
#       Returns the property's dimension and metric catalogue plus its resource
#       name. No date range is accepted, so no reporting data is reachable.
#
#   gsc.sites.get
#       GET searchconsole.googleapis.com/webmasters/v3/sites/{siteUrl}
#       Returns the site URL and permission level for one exact site. This is
#       an exact lookup rather than sites.list, so there is no pagination.
GA4_METADATA_OPERATION = "ga4.properties.getMetadata"
GSC_SITE_OPERATION = "gsc.sites.get"
SUPPORTED_OPERATIONS = (GA4_METADATA_OPERATION, GSC_SITE_OPERATION)

# Neither operation paginates and neither is retried. Retries are zero by
# default because no existing provider policy in this repository requires them
# for a single idempotent metadata GET. Any retry would count against the
# request ceiling.
PLANNED_REQUESTS_PER_OPERATION = 1
MAX_RETRIES_PER_OPERATION = 0

GA4_PROPERTY_ID_RE = re.compile(r"^[0-9]+$")

# Scaffold placeholders. A local configuration file may be created carrying
# these so an operator sees exactly which values are still required, but a
# placeholder must never satisfy structural validation. Rejecting them
# explicitly is what stops a scaffold being mistaken for a configured profile.
PLACEHOLDER_PREFIX = "REQUIRES_DAVID"

# The approved Group 1 envelope, held here so code and governance cannot drift.
# Approved by David Wallace on 2026-08-02.
APPROVED_REQUESTS_PER_PROFILE = 2
APPROVED_COST_PER_PROFILE = 1.0
GROUP_1_PROFILES = ("avs", "lucy-escobar", "western-wood-structures")
APPROVED_GROUP_REQUESTS = 6
APPROVED_GROUP_COST = 3.0
NUMERICAL_APPROVAL_SOURCE = (
    "David Wallace, 2026-08-02, recorded in "
    "docs/r8_c5_group_1_bounded_dry_run_authorization.md"
)

# Reporting-data method names that must never be reachable from this workflow.
PROHIBITED_REPORTING_METHODS = (
    "run_traffic_overview",
    "run_exact_range_summary",
    "run_exact_range_traffic_series",
    "run_exact_range_channel_performance",
    "run_exact_range_top_sources",
    "run_exact_range_top_landing_pages",
    "run_exact_range_most_viewed_pages",
    "query_search_analytics",
    "query_exact_range_summary",
    "query_exact_range_queries",
    "query_exact_range_pages",
)


class ProviderVerificationError(RuntimeError):
    """Verification refused. Raised before any avoidable provider access."""


@dataclass(frozen=True)
class PlannedOperation:
    provider: str
    operation: str
    target: str
    planned_requests: int = PLANNED_REQUESTS_PER_OPERATION
    max_retries: int = MAX_RETRIES_PER_OPERATION

    @property
    def max_requests(self) -> int:
        return self.planned_requests + self.max_retries


@dataclass
class ProviderCallPlan:
    profile: str
    operations: list[PlannedOperation] = field(default_factory=list)

    @property
    def planned_requests(self) -> int:
        return sum(item.planned_requests for item in self.operations)

    @property
    def max_requests(self) -> int:
        return sum(item.max_requests for item in self.operations)

    @property
    def operation_names(self) -> list[str]:
        return [item.operation for item in self.operations]

    def by_provider(self, provider: str) -> int:
        return sum(item.max_requests for item in self.operations if item.provider == provider)

    def evidence(self) -> dict[str, object]:
        return {
            "planned_operations": [
                {
                    "provider": item.provider,
                    "operation": item.operation,
                    "target": item.target,
                    "planned_requests": item.planned_requests,
                    "max_retries": item.max_retries,
                }
                for item in self.operations
            ],
            "planned_requests_ga4": self.by_provider("ga4"),
            "planned_requests_gsc": self.by_provider("gsc"),
            "planned_requests_total": self.planned_requests,
            "max_requests_total": self.max_requests,
            "max_retries_per_operation": MAX_RETRIES_PER_OPERATION,
        }


@dataclass
class StructuralResult:
    ga4_property_id: str
    gsc_site_url: str
    ga4_credential_reference: str
    gsc_credential_reference: str
    findings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.findings


def validate_profile_configuration(
    profile: str,
    ga4_config: Mapping[str, Any],
    gsc_config: Mapping[str, Any],
    *,
    repository_root: Path,
    ga4_applicable: bool = True,
    gsc_applicable: bool = True,
) -> StructuralResult:
    """Structural validation of non-secret configuration.

    Consumes the loader's **safe dictionary vocabulary**: the non-secret
    resource identifiers ``_safe_property_id`` and ``_safe_site_url``, plus the
    credential-reference state flags. It never reads a raw config value, never
    opens a credential, and never resolves a secret environment value.

    A provider that is not applicable to this profile is not validated and
    contributes no findings, because demanding configuration for a provider the
    client does not use would be a fabricated requirement.
    """
    findings: list[str] = []

    property_id = _safe_identifier(ga4_config, "_safe_property_id")
    site_url = _safe_identifier(gsc_config, "_safe_site_url")

    if ga4_applicable:
        findings.extend(_identifier_findings(property_id, "GA4 property_id", GA4_PROPERTY_ID_RE, _ga4_shape_note))
        findings.extend(_credential_findings(ga4_config, "GA4"))
    if gsc_applicable:
        findings.extend(_identifier_findings(site_url, "GSC site_url", None, _gsc_shape_note))
        findings.extend(_credential_findings(gsc_config, "GSC"))

    if not ga4_applicable and not gsc_applicable:
        findings.append(
            "no provider is applicable for this profile, so there is nothing to verify"
        )

    return StructuralResult(
        ga4_property_id=property_id if ga4_applicable else "",
        gsc_site_url=site_url if gsc_applicable else "",
        ga4_credential_reference=_reference_kind_from_state(ga4_config) if ga4_applicable else "not_applicable",
        gsc_credential_reference=_reference_kind_from_state(gsc_config) if gsc_applicable else "not_applicable",
        findings=findings,
    )


def _safe_identifier(config: Mapping[str, Any], field: str) -> str:
    """Read a non-secret provider resource identifier from the safe dictionary.

    Returns an empty string for a missing value **and for a boolean**. The
    loader also exposes presence flags such as ``property_id: True``; treating
    one of those as an identifier is exactly the defect this guards against.
    """
    value = config.get(field)
    if isinstance(value, bool) or not isinstance(value, str):
        return ""
    return value.strip()


def _is_placeholder(value: str) -> bool:
    """Scaffold and template placeholders only.

    Deliberately narrow. An earlier revision also rejected any
    ``.example.invalid`` value, which wrongly refused legitimate synthetic test
    identifiers. Unresolved provider applicability, which is the real reason a
    registry placeholder domain matters, is handled by
    :func:`resolve_provider_applicability` rather than by identifier shape.
    """
    normalized = value.strip().upper()
    return (
        normalized.startswith(PLACEHOLDER_PREFIX)
        or normalized.startswith("REDACTED_OR_PLACEHOLDER")
        or "EXAMPLE-ALIAS-OR-CANONICAL-SLUG" in normalized
        or normalized in {"CHANGEME", "TODO", "TBD"}
    )


def _ga4_shape_note(value: str) -> str:
    return f"GA4 property_id {value!r} is not a numeric property identifier"


def _gsc_shape_note(value: str) -> str:
    return f"GSC site_url {value!r} is not a supported site identifier"


def _identifier_findings(value: str, label: str, pattern, shape_note) -> list[str]:
    if not value:
        return [f"{label} is missing, blank, or exposed only as a presence flag"]
    if _is_placeholder(value):
        return [f"{label} is still a placeholder and requires David"]
    if pattern is not None:
        if not pattern.match(value):
            return [shape_note(value)]
    elif not (
        value.startswith("http://") or value.startswith("https://") or value.startswith("sc-domain:")
    ):
        return [shape_note(value)]
    return []


def _credential_findings(config: Mapping[str, Any], label: str) -> list[str]:
    """Validate the credential *reference*, never its value.

    Uses the loader's own non-secret vocabulary: whether a reference is
    configured, and whether it resolves inside a prohibited repository path.
    """
    findings: list[str] = []
    if not config.get("oauth_client_secrets_configured"):
        findings.append(f"{label} credential reference is not configured")
    elif str(config.get("oauth_client_secrets_repo_location") or "").strip().lower() == "inside repo":
        findings.append(f"{label} credential reference must stay outside the repository")
    return findings


def _reference_kind_from_state(config: Mapping[str, Any]) -> str:
    env_name = str(config.get("oauth_client_secrets_env") or "").strip()
    if env_name:
        return "environment_variable_name"
    if config.get("oauth_client_secrets_configured"):
        return "file_path"
    return "missing"


def build_call_plan(
    profile: str,
    structural: StructuralResult,
    *,
    ga4_applicable: bool = True,
    gsc_applicable: bool = True,
) -> ProviderCallPlan:
    """The exact, deterministic provider-call plan for one profile.

    One request per **applicable** provider, no pagination, no retries.
    Producible with no credentials.

    A profile with only one applicable provider plans exactly one request, and
    a profile with none plans zero. The approved per-client maximum of two is a
    ceiling, never a quota to fill, so an inapplicable provider is never given
    an invented call.
    """
    operations: list[PlannedOperation] = []
    if ga4_applicable:
        operations.append(
            PlannedOperation("ga4", GA4_METADATA_OPERATION, f"properties/{structural.ga4_property_id}")
        )
    if gsc_applicable:
        operations.append(PlannedOperation("gsc", GSC_SITE_OPERATION, structural.gsc_site_url))
    return ProviderCallPlan(profile=profile, operations=operations)


def offline_validate(
    *,
    authorization: ProfileAuthorization,
    ga4_config: Mapping[str, Any],
    gsc_config: Mapping[str, Any],
    repository_root: Path,
    applicability: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    """Run the full offline path and return deterministic evidence.

    Contains no timestamp and no random value, so identical inputs produce
    byte-identical evidence.

    Structural readiness and provider readiness are reported separately, and
    neither is described as the other.
    """
    profile = authorization.requested_profile
    if applicability is None:
        applicability = resolve_provider_applicability(profile)
    ga4_applicable = bool(applicability.get("ga4_applicable"))
    gsc_applicable = bool(applicability.get("gsc_applicable"))

    structural = validate_profile_configuration(
        profile,
        ga4_config,
        gsc_config,
        repository_root=repository_root,
        ga4_applicable=ga4_applicable,
        gsc_applicable=gsc_applicable,
    )
    plan = build_call_plan(
        profile, structural, ga4_applicable=ga4_applicable, gsc_applicable=gsc_applicable
    )
    cost = expected_direct_cost(plan.operation_names)

    evidence: dict[str, object] = {
        "evidence_contract": EVIDENCE_CONTRACT,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "execution_mode": OFFLINE_MODE,
        "profile": profile,
        "authorized_profiles": list(authorization.authorized_profiles),
        "authorization_result": "authorized",
        "ga4_configured_property": structural.ga4_property_id,
        "gsc_configured_property": structural.gsc_site_url,
        "structural_configuration_result": "ready" if structural.ready else "not_ready",
        "structural_findings": list(structural.findings),
        "ga4_credential_reference_type": structural.ga4_credential_reference,
        "gsc_credential_reference_type": structural.gsc_credential_reference,
        "credential_reference_checked_structurally": True,
        "credential_contents_accessed": False,
        "provider_client_constructed": False,
        "provider_requests_executed": 0,
        "expected_known_direct_cost": cost,
        "unknown_indirect_effects": (
            "Quota consumption, rate limiting, and any downstream billing interaction "
            "are not bounded by repository evidence and are recorded as Unknown."
        ),
        "provider_applicability_status": applicability.get("status"),
        "provider_applicability_reason": applicability.get("reason"),
        "ga4_applicable": ga4_applicable,
        "gsc_applicable": gsc_applicable,
        "planned_requests_for_this_profile": plan.max_requests,
        "required_request_ceiling": plan.max_requests,
        "approved_request_ceiling_per_client": APPROVED_REQUESTS_PER_PROFILE,
        "approved_cost_ceiling_per_client": APPROVED_COST_PER_PROFILE,
        "numerical_approval_source": NUMERICAL_APPROVAL_SOURCE,
        # Structural readiness is not provider readiness and is never reported
        # as though a provider had been contacted.
        "provider_verified": False,
        "provider_execution_authorized": False,
        "execution_eligible": bool(structural.ready and plan.operations),
        "final_state": "structurally_ready" if structural.ready else "structurally_not_ready",
        "stop_reason": None if structural.ready else "structural configuration incomplete",
        "errors": list(structural.findings),
    }
    evidence.update(plan.evidence())
    return evidence


def provider_verify(
    *,
    authorization: ProfileAuthorization,
    ga4_config: Mapping[str, Any],
    gsc_config: Mapping[str, Any],
    repository_root: Path,
    max_requests: int | None,
    max_cost: float | None,
    resolve_credentials: Callable[[], Mapping[str, Any]],
    build_ga4_client: Callable[[Mapping[str, Any]], Any],
    build_gsc_client: Callable[[Mapping[str, Any]], Any],
) -> dict[str, object]:
    """Verify provider access, using exactly the planned metadata calls.

    Implemented but not authorized to execute. The ordering below is the point
    of this function and is asserted by tests:

    authorization, then structural validation, then budget validation, then
    credential resolution, then provider construction, then the calls.

    A refusal at any of the first three steps happens **before** the
    ``resolve_credentials`` callable is ever invoked.
    """
    if max_requests is None:
        raise ProviderBudgetError(
            "provider verification requires an approved request ceiling. "
            "No credential was read and no provider client was constructed."
        )
    if max_cost is None:
        raise ProviderBudgetError(
            "provider verification requires an approved cost ceiling. "
            "No credential was read and no provider client was constructed."
        )

    profile = authorization.requested_profile
    applicability = resolve_provider_applicability(profile)
    if applicability.get("status") != APPLICABILITY_DECLARED:
        raise ProviderVerificationError(
            f"provider applicability for {profile} is {applicability.get('status')}: "
            f"{applicability.get('reason')}. Provider verification cannot run. "
            "No credential was read and no provider client was constructed."
        )
    ga4_applicable = bool(applicability.get("ga4_applicable"))
    gsc_applicable = bool(applicability.get("gsc_applicable"))

    structural = validate_profile_configuration(
        profile,
        ga4_config,
        gsc_config,
        repository_root=repository_root,
        ga4_applicable=ga4_applicable,
        gsc_applicable=gsc_applicable,
    )
    if not structural.ready:
        raise ProviderVerificationError(
            f"profile {profile} is not structurally ready: {'; '.join(structural.findings)}. "
            "No credential was read and no provider client was constructed."
        )

    plan = build_call_plan(
        profile, structural, ga4_applicable=ga4_applicable, gsc_applicable=gsc_applicable
    )
    assert_approved_plan(plan)
    assert_approved_ceilings(max_requests, max_cost, plan.max_requests)

    requests_budget = RequestBudget(max_requests=max_requests)
    cost_budget = CostBudget(max_cost=max_cost)
    cost_budget.check_operations(plan.operation_names)
    requests_budget.check_plan(plan.max_requests)
    cost_budget.check_plan(expected_direct_cost(plan.operation_names))

    # Only now may a credential be touched.
    credentials = resolve_credentials()

    if ga4_applicable:
        ga4_client = build_ga4_client(credentials)
        _reject_reporting_capable_use(ga4_client)
        requests_budget.consume(GA4_METADATA_OPERATION)
        ga4_metadata = ga4_client.get_property_metadata(structural.ga4_property_id)
        _assert_ga4_identity(ga4_metadata, structural.ga4_property_id)

    if gsc_applicable:
        gsc_client = build_gsc_client(credentials)
        _reject_reporting_capable_use(gsc_client)
        requests_budget.consume(GSC_SITE_OPERATION)
        gsc_site = gsc_client.get_site(structural.gsc_site_url)
        _assert_gsc_identity(gsc_site, structural.gsc_site_url)

    evidence: dict[str, object] = {
        "evidence_contract": EVIDENCE_CONTRACT,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "execution_mode": PROVIDER_MODE,
        "profile": profile,
        "authorized_profiles": list(authorization.authorized_profiles),
        "authorization_result": "authorized",
        "ga4_configured_property": structural.ga4_property_id,
        "gsc_configured_property": structural.gsc_site_url,
        "structural_configuration_result": "ready",
        "structural_findings": [],
        "provider_applicability_status": applicability.get("status"),
        "ga4_applicable": ga4_applicable,
        "gsc_applicable": gsc_applicable,
        "provider_verified": True,
        "ga4_credential_reference_type": structural.ga4_credential_reference,
        "gsc_credential_reference_type": structural.gsc_credential_reference,
        "credential_reference_checked_structurally": True,
        "credential_contents_accessed": True,
        "provider_client_constructed": True,
        "final_state": "verified",
        "stop_reason": None,
        "errors": [],
    }
    evidence.update(plan.evidence())
    evidence.update(requests_budget.evidence())
    evidence.update(cost_budget.evidence())
    return evidence


APPLICABILITY_DECLARED = "applicable_providers_declared"
APPLICABILITY_UNRESOLVED = "provider_applicability_unresolved"
APPLICABILITY_NONE = "no_applicable_providers"


def resolve_provider_applicability(
    profile: str, registry_path: Path | None = None
) -> dict[str, object]:
    """Which providers a profile actually uses, from governed registry evidence.

    A profile that declares no data sources is **unresolved**, not "no
    providers". The difference matters: unresolved means David has not yet said
    which providers apply, and guessing either way would fabricate product
    direction. AVS is currently in exactly that state.
    """
    import json

    path = registry_path or (Path(__file__).resolve().parents[1] / "config" / "dashboard_lab_profiles.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = next(
        (item for item in payload.get("profiles", []) if str(item.get("slug") or "") == profile),
        None,
    )
    if entry is None:
        return {
            "profile": profile,
            "status": APPLICABILITY_UNRESOLVED,
            "ga4_applicable": False,
            "gsc_applicable": False,
            "reason": "profile is absent from the governed registry",
        }

    sources = [str(item).strip().lower() for item in (entry.get("data_sources") or [])]
    enabled = {
        str(cap.get("key") or "").strip().lower()
        for cap in (entry.get("capabilities") or [])
        if str(cap.get("status") or "").strip().lower() == "enabled"
        and str(cap.get("kind") or "").strip().lower() == "importer_provider"
    }
    ga4 = "ga4" in sources and "ga4" in enabled
    gsc = "gsc" in sources and "gsc" in enabled

    if not sources:
        return {
            "profile": profile,
            "status": APPLICABILITY_UNRESOLVED,
            "ga4_applicable": False,
            "gsc_applicable": False,
            "reason": (
                "the governed registry declares no data sources and no enabled importer "
                "provider capability, so provider applicability requires David's explicit "
                "classification"
            ),
        }
    if not ga4 and not gsc:
        return {
            "profile": profile,
            "status": APPLICABILITY_NONE,
            "ga4_applicable": False,
            "gsc_applicable": False,
            "reason": "no GA4 or GSC importer provider capability is enabled",
        }
    return {
        "profile": profile,
        "status": APPLICABILITY_DECLARED,
        "ga4_applicable": ga4,
        "gsc_applicable": gsc,
        "reason": "governed registry declares the providers above",
    }


def plan_group_1(profiles: list[str]) -> dict[str, object]:
    """Deterministic Group 1 aggregate plan, enforcing the approved total.

    Guards the aggregate envelope that three separately valid single-profile
    commands could otherwise exceed. A fourth profile is rejected, and an
    incomplete set can never be described as Group 1.
    """
    supplied = [str(item or "").strip() for item in profiles]
    unexpected = sorted(set(supplied) - set(GROUP_1_PROFILES))
    if unexpected:
        raise ProviderVerificationError(
            f"{', '.join(unexpected)} is not a Group 1 profile. Group 1 is exactly "
            f"{', '.join(GROUP_1_PROFILES)} and cannot be extended here."
        )
    missing = [item for item in GROUP_1_PROFILES if item not in supplied]

    entries: list[dict[str, object]] = []
    ready_requests = 0
    potential_max = 0
    for slug in GROUP_1_PROFILES:
        applicability = resolve_provider_applicability(slug)
        planned = int(bool(applicability.get("ga4_applicable"))) + int(
            bool(applicability.get("gsc_applicable"))
        )
        structurally_ready = _structurally_ready(slug, applicability)
        if structurally_ready:
            ready_requests += planned
        entries.append(
            {
                "profile": slug,
                "applicability_status": applicability.get("status"),
                "ga4_applicable": applicability.get("ga4_applicable"),
                "gsc_applicable": applicability.get("gsc_applicable"),
                "planned_requests_when_configured": planned,
                "structurally_ready": structurally_ready,
                # Structural readiness is not execution authorization. This stays
                # false until David authorizes the credentialed run.
                "can_enter_provider_verification": False,
                "reason": applicability.get("reason"),
            }
        )
        potential_max += (
            planned
            if applicability.get("status") == APPLICABILITY_DECLARED
            else APPROVED_REQUESTS_PER_PROFILE
            if applicability.get("status") == APPLICABILITY_UNRESOLVED
            else 0
        )

    unresolved = [
        item["profile"] for item in entries if item["applicability_status"] == APPLICABILITY_UNRESOLVED
    ]

    if potential_max > APPROVED_GROUP_REQUESTS:
        raise ProviderVerificationError(
            f"potential group maximum {potential_max} exceeds the approved "
            f"{APPROVED_GROUP_REQUESTS}"
        )

    return {
        "group": "R8-C5 Group 1",
        # Deterministic order, independent of how the caller supplied them.
        "execution_order": list(GROUP_1_PROFILES),
        "profiles_supplied": sorted(set(supplied)),
        "missing_profiles": missing,
        "group_complete": False,
        "group_completion_blocked_by": (
            (["missing from this invocation: " + ", ".join(missing)] if missing else [])
            + (["provider applicability unresolved: " + ", ".join(unresolved)] if unresolved else [])
            + ["no profile is structurally ready, so no profile can enter provider verification"]
        ),
        "profiles": entries,
        # Requests covered by structurally ready profiles. This is readiness,
        # not authorization: nothing executes until David authorizes the run.
        "structurally_ready_requests": ready_requests,
        "executable_requests_now": 0,
        "potential_maximum_requests": potential_max,
        "cost_ceiling_per_profile": APPROVED_COST_PER_PROFILE,
        "group_request_ceiling": APPROVED_GROUP_REQUESTS,
        "group_cost_ceiling": APPROVED_GROUP_COST,
        "max_retries_per_operation": MAX_RETRIES_PER_OPERATION,
        "approved_operations": list(SUPPORTED_OPERATIONS),
        "numerical_approval_source": NUMERICAL_APPROVAL_SOURCE,
        "stop_on_first_failure": True,
        "provider_execution_authorized": False,
    }


def _structurally_ready(slug: str, applicability: Mapping[str, Any]) -> bool:
    """Whether one profile's local configuration is structurally complete.

    Reads only the loader's safe dictionary. Never opens a credential and never
    resolves a secret environment value.
    """
    if applicability.get("status") != APPLICABILITY_DECLARED:
        return False
    try:
        from src.profile_local_config import load_profile_local_config

        providers = load_profile_local_config(slug).as_safe_dict().get("providers") or {}
    except Exception:
        return False
    result = validate_profile_configuration(
        slug,
        dict(providers.get("ga4") or {}),
        dict(providers.get("gsc") or {}),
        repository_root=Path(__file__).resolve().parents[1],
        ga4_applicable=bool(applicability.get("ga4_applicable")),
        gsc_applicable=bool(applicability.get("gsc_applicable")),
    )
    return result.ready


def assert_approved_plan(plan: ProviderCallPlan) -> None:
    """The plan must be exactly the two approved operations, nothing else.

    Guards against an operation being added, substituted, retried, or
    paginated into the plan after David approved a specific envelope.
    """
    unapproved = [name for name in plan.operation_names if name not in SUPPORTED_OPERATIONS]
    if unapproved:
        raise ProviderVerificationError(
            f"planned operations {unapproved} are not in the approved set "
            f"{list(SUPPORTED_OPERATIONS)}. Verification refused."
        )
    if len(set(plan.operation_names)) != len(plan.operation_names):
        raise ProviderVerificationError(
            "an approved operation is planned more than once. Verification refused."
        )
    for operation in plan.operations:
        if operation.planned_requests != 1 or operation.max_retries != 0:
            raise ProviderVerificationError(
                f"operation {operation.operation} plans {operation.planned_requests} requests "
                f"and {operation.max_retries} retries; the approved envelope is exactly one "
                "request and zero retries. Verification refused."
            )
    if not plan.operations:
        raise ProviderVerificationError(
            "no provider operation is applicable for this profile, so provider verification "
            "cannot run and cannot be reported complete."
        )
    if plan.max_requests > APPROVED_REQUESTS_PER_PROFILE:
        raise ProviderVerificationError(
            f"planned maximum {plan.max_requests} exceeds the approved "
            f"{APPROVED_REQUESTS_PER_PROFILE} requests per profile. Verification refused."
        )


def assert_approved_ceilings(max_requests: int, max_cost: float, planned_requests: int) -> None:
    """Ceilings must match this profile's actual plan exactly.

    **Plan exact, not client maximum.** A profile with one applicable provider
    must be given a ceiling of one, not two. Forcing the global per-client
    maximum onto a one-provider profile would authorize a call that has no
    corresponding planned operation.

    Exact equality is deliberate: a larger ceiling would let an operator widen
    authorization by passing a bigger number, which the approval does not
    permit. The plan itself is separately bounded above by the approved
    per-client maximum.
    """
    if planned_requests > APPROVED_REQUESTS_PER_PROFILE:
        raise ProviderBudgetError(
            f"planned {planned_requests} requests exceed the approved "
            f"{APPROVED_REQUESTS_PER_PROFILE} per client."
        )
    if max_requests != planned_requests:
        raise ProviderBudgetError(
            f"request ceiling must equal the planned {planned_requests} requests for this "
            f"profile; {max_requests} was supplied. The approved per-client maximum of "
            f"{APPROVED_REQUESTS_PER_PROFILE} is a ceiling, not a quota to fill. "
            "No credential was read and no provider client was constructed."
        )
    if max_cost > APPROVED_COST_PER_PROFILE:
        raise ProviderBudgetError(
            f"cost ceiling must not exceed the approved {APPROVED_COST_PER_PROFILE} per "
            f"profile; {max_cost} was supplied. "
            "No credential was read and no provider client was constructed."
        )
    if max_cost < expected_direct_cost([GA4_METADATA_OPERATION, GSC_SITE_OPERATION]):
        raise ProviderBudgetError(
            "cost ceiling is below the expected known direct cost. "
            "No credential was read and no provider client was constructed."
        )


def _assert_ga4_identity(metadata: Mapping[str, Any], property_id: str) -> None:
    name = str(metadata.get("name") or "")
    if f"properties/{property_id}" not in name:
        raise ProviderVerificationError(
            f"GA4 returned identity {name!r}, which does not match configured "
            f"property {property_id}. Verification stopped."
        )


def _assert_gsc_identity(site: Mapping[str, Any], site_url: str) -> None:
    returned = str(site.get("siteUrl") or "")
    if returned != site_url:
        raise ProviderVerificationError(
            f"Google Search Console returned site {returned!r}, which does not match "
            f"configured site {site_url!r}. Verification stopped."
        )


def _reject_reporting_capable_use(client: Any) -> None:
    """Refuse a client that exposes a reporting-data method to this workflow.

    Defensive: the workflow calls only metadata methods, and this makes an
    accidental future wiring of a reporting-capable client fail loudly rather
    than silently retrieving data.
    """
    for method in PROHIBITED_REPORTING_METHODS:
        if hasattr(client, method):
            raise ProviderVerificationError(
                f"the verification client exposes reporting method {method}, which this "
                "workflow must never reach. Verification refused."
            )


def _credential_reference(config: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    for name in fields:
        value = str(config.get(name) or "").strip()
        if value:
            return value
    return ""


def _reference_kind(reference: str) -> str:
    if not reference:
        return "missing"
    if reference.isupper() and "/" not in reference and "\\" not in reference:
        return "environment_variable_name"
    return "file_path"


def _reference_location_findings(reference: str, label: str, repository_root: Path) -> list[str]:
    """A file reference must live outside the repository. Env names are shapes only.

    An environment-variable *name* is validated as a name. Its value is never
    resolved, so a secret cannot leak through offline validation.
    """
    if _reference_kind(reference) == "environment_variable_name":
        return []
    try:
        Path(reference).expanduser().resolve(strict=False).relative_to(
            repository_root.resolve(strict=False)
        )
    except ValueError:
        return []
    return [f"{label} credential reference must stay outside the repository"]
