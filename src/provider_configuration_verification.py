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
) -> StructuralResult:
    """Structural validation of non-secret configuration.

    Checks that required fields exist and that credential *references* are
    present and safely located. **No credential is opened and no secret
    environment value is resolved.** A reference is validated by shape and
    location only.
    """
    findings: list[str] = []

    property_id = str(ga4_config.get("property_id") or "").strip()
    if not property_id:
        findings.append("GA4 property_id is missing or blank")
    elif not GA4_PROPERTY_ID_RE.match(property_id):
        findings.append(f"GA4 property_id {property_id!r} is not a numeric property identifier")

    site_url = str(gsc_config.get("site_url") or "").strip()
    if not site_url:
        findings.append("GSC site_url is missing or blank")
    elif not (site_url.startswith("http://") or site_url.startswith("https://") or site_url.startswith("sc-domain:")):
        findings.append(f"GSC site_url {site_url!r} is not a supported site identifier")

    ga4_reference = _credential_reference(ga4_config, ("oauth_client_secrets_env", "service_account_file", "oauth_client_secrets_file"))
    if not ga4_reference:
        findings.append("GA4 credential reference field is missing")
    else:
        findings.extend(_reference_location_findings(ga4_reference, "GA4", repository_root))

    gsc_reference = _credential_reference(gsc_config, ("oauth_client_secrets_env", "oauth_client_secrets_file"))
    if not gsc_reference:
        findings.append("GSC credential reference field is missing")
    else:
        findings.extend(_reference_location_findings(gsc_reference, "GSC", repository_root))

    return StructuralResult(
        ga4_property_id=property_id,
        gsc_site_url=site_url,
        ga4_credential_reference=_reference_kind(ga4_reference),
        gsc_credential_reference=_reference_kind(gsc_reference),
        findings=findings,
    )


def build_call_plan(profile: str, structural: StructuralResult) -> ProviderCallPlan:
    """The exact, deterministic provider-call plan for one profile.

    Two operations, one request each, no pagination, no retries. Producible
    with no credentials.
    """
    return ProviderCallPlan(
        profile=profile,
        operations=[
            PlannedOperation("ga4", GA4_METADATA_OPERATION, f"properties/{structural.ga4_property_id}"),
            PlannedOperation("gsc", GSC_SITE_OPERATION, structural.gsc_site_url),
        ],
    )


def offline_validate(
    *,
    authorization: ProfileAuthorization,
    ga4_config: Mapping[str, Any],
    gsc_config: Mapping[str, Any],
    repository_root: Path,
) -> dict[str, object]:
    """Run the full offline path and return deterministic evidence.

    Contains no timestamp and no random value, so identical inputs produce
    byte-identical evidence.
    """
    profile = authorization.requested_profile
    structural = validate_profile_configuration(
        profile, ga4_config, gsc_config, repository_root=repository_root
    )
    plan = build_call_plan(profile, structural)
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
    structural = validate_profile_configuration(
        profile, ga4_config, gsc_config, repository_root=repository_root
    )
    if not structural.ready:
        raise ProviderVerificationError(
            f"profile {profile} is not structurally ready: {'; '.join(structural.findings)}. "
            "No credential was read and no provider client was constructed."
        )

    plan = build_call_plan(profile, structural)
    requests_budget = RequestBudget(max_requests=max_requests)
    cost_budget = CostBudget(max_cost=max_cost)
    cost_budget.check_operations(plan.operation_names)
    requests_budget.check_plan(plan.max_requests)
    cost_budget.check_plan(expected_direct_cost(plan.operation_names))

    # Only now may a credential be touched.
    credentials = resolve_credentials()

    ga4_client = build_ga4_client(credentials)
    _reject_reporting_capable_use(ga4_client)
    requests_budget.consume(GA4_METADATA_OPERATION)
    ga4_metadata = ga4_client.get_property_metadata(structural.ga4_property_id)
    _assert_ga4_identity(ga4_metadata, structural.ga4_property_id)

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
