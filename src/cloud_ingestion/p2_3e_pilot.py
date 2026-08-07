"""One-shot real-provider P2-3E Cloud Run Job entrypoint."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

from .application import IngestionApplication
from .cloud_adapters import MountedGrant, MountedOAuthCredentialProvider, PortalConfigurationProvider
from .contract import serialized_size
from .domain import RunRequest
from .google_identity import MetadataIdentityTokenProvider
from .google_providers import GoogleGa4WeeklyProvider, GoogleGscWeeklyProvider
from .portal_sink import PortalIngestionSink
from .structured_logging import SafeJsonLogger


PROJECT_ID = "cd39f3ec-58b7-4ecc-8691-8415e29e9545"
WEEK_START = date(2026, 7, 27)
BINDINGS = {
    "ga4": "google-oauth/inn-spanish-head/ga4",
    "gsc": "google-oauth/inn-spanish-head/gsc",
}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def main() -> int:
    try:
        portal_url = _required("P2_3E_PORTAL_URL")
        project_id = _required("P2_3E_PROJECT_ID")
        provider = _required("P2_3E_PROVIDER")
        week_start = date.fromisoformat(_required("P2_3E_WEEK_START"))
        idempotency_key = str(UUID(_required("P2_3E_IDEMPOTENCY_KEY")))
        if project_id != PROJECT_ID or str(UUID(project_id)) != PROJECT_ID:
            raise ValueError("P2_3E_PROJECT_ID does not match the governed pilot project UUID")
        if provider not in BINDINGS:
            raise ValueError("P2_3E_PROVIDER is unsupported")
        if week_start != WEEK_START:
            raise ValueError("P2_3E_WEEK_START is not the governed completed pilot week")
        binding = _required("P2_3E_CREDENTIAL_BINDING")
        if binding != BINDINGS[provider]:
            raise ValueError("P2_3E_CREDENTIAL_BINDING is not the governed provider binding")
        secret_path = Path(_required("P2_3E_CREDENTIAL_PATH"))
        version = _required("P2_3E_CREDENTIAL_VERSION")

        identity = MetadataIdentityTokenProvider()
        sink = PortalIngestionSink(portal_url, identity)
        request = RunRequest(
            project_id=PROJECT_ID,
            provider=provider,
            week_start=WEEK_START,
            idempotency_key=idempotency_key,
            environment="production",
            operator_audit_identity="p2-3e-manual-cloud-run-job",
        )
        app = IngestionApplication(
            PortalConfigurationProvider(portal_url, identity),
            MountedOAuthCredentialProvider(
                {binding: MountedGrant(binding, provider, secret_path, version)}
            ),
            {"ga4": GoogleGa4WeeklyProvider(), "gsc": GoogleGscWeeklyProvider()},
            sink,
            logger=SafeJsonLogger(stream=sys.stdout),
        )
        outcome = app.run(request)
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
        print(
            json.dumps(
                {
                    "event": "p2_3e_pilot_result",
                    "proof_ok": True,
                    "client": "Inn At Spanish Head",
                    "project_id": PROJECT_ID,
                    "provider": provider,
                    "week_start": WEEK_START.isoformat(),
                    "week_end": request.week_end.isoformat(),
                    "requests_consumed": payload["evidence"]["requests_consumed"],
                    "retry_count": payload["evidence"]["retry_count"],
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
        print(
            json.dumps(
                {
                    "event": "p2_3e_pilot_result",
                    "proof_ok": False,
                    "status": "failed",
                    "error_code": "pilot_configuration_refused",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
