"""Governed manual completed-week GA4/GSC Cloud Run entrypoint.

One execution is exactly one client, one project, one provider and one completed
Monday-through-Sunday week. Provider resource identities and credential binding
keys come only from the Portal configuration response. The operator cannot
supply or override either value.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping
from uuid import UUID
from zoneinfo import ZoneInfo

from .application import IngestionApplication
from .cloud_adapters import MountedGrant, MountedOAuthCredentialProvider, PortalConfigurationProvider
from .contract import serialized_size
from .domain import IngestionConfiguration, RunRequest
from .errors import ConfigurationError, CredentialError, InputError
from .google_identity import MetadataIdentityTokenProvider
from .google_providers import GoogleGa4WeeklyProvider, GoogleGscWeeklyProvider
from .portal_sink import PortalIngestionSink
from .structured_logging import SafeJsonLogger

ENVIRONMENT = "production"
EXPECTED_CEILINGS = {"ga4": 6, "gsc": 4}
EXPECTED_REQUESTS = {"ga4": 5, "gsc": 1}
RESOURCE_KINDS = {
    "ga4": frozenset({"ga4_property"}),
    "gsc": frozenset({"gsc_site", "gsc_domain_property", "gsc_url_prefix"}),
}


@dataclass(frozen=True)
class ManualRunInputs:
    client_id: str
    project_id: str
    provider: str
    week_start: date
    idempotency_key: str
    mode: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _uuid(self.client_id, "client_id"))
        object.__setattr__(self, "project_id", _uuid(self.project_id, "project_id"))
        object.__setattr__(self, "idempotency_key", _uuid(self.idempotency_key, "idempotency_key"))
        if self.provider not in EXPECTED_CEILINGS:
            raise InputError("provider must be ga4 or gsc")
        if self.week_start.weekday() != 0:
            raise InputError("week_start must be a Monday")
        if self.mode not in {"preflight", "execute"}:
            raise InputError("mode must be preflight or execute")

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=6)


class _StaticConfigurationProvider:
    def __init__(self, configuration: IngestionConfiguration) -> None:
        self._configuration = configuration

    def load(self, request: RunRequest) -> IngestionConfiguration:
        return self._configuration


def _uuid(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InputError(f"{label} must be a UUID") from exc


def _required(name: str, environment: Mapping[str, str] | None = None) -> str:
    source = os.environ if environment is None else environment
    value = source.get(name, "").strip()
    if not value:
        raise InputError(f"{name} is required")
    return value


def parse_inputs(environment: Mapping[str, str] | None = None) -> ManualRunInputs:
    source = os.environ if environment is None else environment
    try:
        week_start = date.fromisoformat(_required("INTERNAL_REPORTING_WEEK_START", source))
    except ValueError as exc:
        raise InputError("week_start must be an ISO date") from exc
    if _required("INTERNAL_REPORTING_ENVIRONMENT", source) != ENVIRONMENT:
        raise InputError("internal reporting environment must be production")
    return ManualRunInputs(
        client_id=_required("INTERNAL_REPORTING_CLIENT_ID", source),
        project_id=_required("INTERNAL_REPORTING_PROJECT_ID", source),
        provider=_required("INTERNAL_REPORTING_PROVIDER", source),
        week_start=week_start,
        idempotency_key=_required("INTERNAL_REPORTING_IDEMPOTENCY_KEY", source),
        mode=_required("INTERNAL_REPORTING_MODE", source),
    )


def parse_grants(encoded: str) -> dict[str, MountedGrant]:
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(raw)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialError("credential grant manifest is malformed") from exc
    if not isinstance(payload, dict) or not payload:
        raise CredentialError("credential grant manifest is malformed")
    grants: dict[str, MountedGrant] = {}
    for binding, value in payload.items():
        if not isinstance(binding, str) or not binding or not isinstance(value, dict):
            raise CredentialError("credential grant manifest is malformed")
        if set(value) != {"provider", "path", "version"}:
            raise CredentialError("credential grant manifest is malformed")
        provider = value.get("provider")
        path = value.get("path")
        version = value.get("version")
        if provider not in EXPECTED_CEILINGS or not isinstance(path, str) or not Path(path).is_absolute():
            raise CredentialError("credential grant manifest is malformed")
        if not isinstance(version, str) or not version.isdigit():
            raise CredentialError("credential grant manifest is malformed")
        grants[binding] = MountedGrant(binding, provider, Path(path), version)
    return grants


def validate_manual_configuration(
    inputs: ManualRunInputs,
    request: RunRequest,
    configuration: IngestionConfiguration,
    *,
    now: datetime | None = None,
) -> None:
    configuration.authorize(request)
    if configuration.client_id != inputs.client_id:
        raise ConfigurationError("configuration client does not match the requested client")
    if configuration.request_ceiling != EXPECTED_CEILINGS[inputs.provider]:
        raise ConfigurationError("configuration request ceiling is not governed")
    if configuration.authorized_retry_count != 0:
        raise ConfigurationError("automatic provider retries are not authorized")
    if configuration.external_resource_type not in RESOURCE_KINDS[inputs.provider]:
        raise ConfigurationError("provider resource identity kind is not governed")
    instant = now or datetime.now(timezone.utc)
    local_today = instant.astimezone(ZoneInfo(configuration.reporting_timezone)).date()
    if inputs.week_end >= local_today:
        raise InputError("the selected reporting week is not complete")


def validate_grant_readiness(
    configuration: IngestionConfiguration,
    grants: Mapping[str, MountedGrant],
) -> MountedGrant:
    grant = grants.get(configuration.credential_binding_key)
    if grant is None or grant.provider != configuration.provider:
        raise CredentialError("the governed credential binding is unavailable")
    if not grant.path.is_file():
        raise CredentialError("the governed credential mount is unavailable")
    return grant


def _safe_failure() -> int:
    print(
        json.dumps(
            {
                "event": "internal_reporting_manual_run_result",
                "proof_ok": False,
                "status": "failed",
                "error_code": "manual_run_refused",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
        flush=True,
    )
    return 64


def main() -> int:
    try:
        inputs = parse_inputs()
        portal_url = _required("INTERNAL_REPORTING_PORTAL_URL")
        grants = parse_grants(_required("INTERNAL_REPORTING_GRANTS_B64"))
        identity = MetadataIdentityTokenProvider()
        request = RunRequest(
            project_id=inputs.project_id,
            provider=inputs.provider,
            week_start=inputs.week_start,
            idempotency_key=inputs.idempotency_key,
            environment=ENVIRONMENT,
            operator_audit_identity="internal-reporting-manual-cloud-run-job",
        )
        configuration = PortalConfigurationProvider(portal_url, identity).load(request)
        validate_manual_configuration(inputs, request, configuration)
        validate_grant_readiness(configuration, grants)

        if inputs.mode == "preflight":
            print(
                json.dumps(
                    {
                        "event": "internal_reporting_manual_run_result",
                        "proof_ok": True,
                        "status": "preflight_ready",
                        "client_id": inputs.client_id,
                        "project_id": inputs.project_id,
                        "provider": inputs.provider,
                        "week_start": inputs.week_start.isoformat(),
                        "week_end": inputs.week_end.isoformat(),
                        "configuration_version": configuration.version,
                        "resource_kind": configuration.external_resource_type,
                        "credential_binding_ready": True,
                        "request_ceiling": configuration.request_ceiling,
                        "retry_count": 0,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                flush=True,
            )
            return 0

        sink = PortalIngestionSink(portal_url, identity)
        application = IngestionApplication(
            _StaticConfigurationProvider(configuration),
            MountedOAuthCredentialProvider(grants),
            {"ga4": GoogleGa4WeeklyProvider(), "gsc": GoogleGscWeeklyProvider()},
            sink,
            logger=SafeJsonLogger(stream=sys.stdout),
        )
        outcome = application.run(request)
        if outcome.exit_code != 0 or outcome.payload is None:
            return int(outcome.exit_code or 1)

        accepted = dict(sink.last_response or {})
        replay = sink.replay_last_delivery()
        invalid = sink.prove_invalid_contract()
        mismatch = sink.prove_resource_mismatch()
        if (
            replay.get("outcome") != "replayed"
            or invalid.get("accepted") is not False
            or mismatch.get("error_code") != "resource_mismatch"
        ):
            raise RuntimeError("Portal replay or negative proof failed")

        payload = outcome.payload
        if payload["evidence"]["requests_consumed"] != EXPECTED_REQUESTS[inputs.provider]:
            raise RuntimeError("provider request count did not match the governed plan")
        print(
            json.dumps(
                {
                    "event": "internal_reporting_manual_run_result",
                    "proof_ok": True,
                    "status": "completed",
                    "client_id": inputs.client_id,
                    "project_id": inputs.project_id,
                    "provider": inputs.provider,
                    "week_start": inputs.week_start.isoformat(),
                    "week_end": inputs.week_end.isoformat(),
                    "configuration_version": configuration.version,
                    "resource_kind": configuration.external_resource_type,
                    "credential_binding_ready": True,
                    "request_ceiling": configuration.request_ceiling,
                    "requests_consumed": payload["evidence"]["requests_consumed"],
                    "retry_count": payload["evidence"]["retry_count"],
                    "direct_cost_usd": payload["evidence"]["direct_cost_usd"],
                    "payload_hash": payload["normalized_payload_hash"],
                    "payload_bytes": serialized_size(payload),
                    "metric_count": len(payload["metrics"]),
                    "daily_observation_count": len(payload["daily"]),
                    "ranked_observation_count": len(payload["ranked"]),
                    "freshness_state": payload["freshness"]["state"],
                    "accepted": accepted,
                    "replay": replay,
                    "invalid_contract": invalid,
                    "resource_mismatch": mismatch,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return 0
    except Exception:
        return _safe_failure()


if __name__ == "__main__":
    raise SystemExit(main())
