"""One-shot synthetic P2-3D Cloud Run Job entrypoint."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import UUID

from .application import IngestionApplication
from .domain import RunRequest
from .fixture_adapters import FixtureConfigurationProvider, FixtureCredentialProvider, FixtureWeeklyProvider
from .google_identity import MetadataIdentityTokenProvider
from .portal_sink import PortalIngestionSink
from .structured_logging import SafeJsonLogger


PROJECT_ID = "20000000-0000-0000-0000-000000000001"
WEEK_START = date(2026, 7, 27)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def main() -> int:
    try:
        portal_url = _required("P2_3D_PORTAL_URL")
        project_id = _required("P2_3D_PROJECT_ID")
        if project_id != PROJECT_ID or str(UUID(project_id)) != PROJECT_ID:
            raise ValueError("P2_3D_PROJECT_ID does not match the governed pilot project UUID")
        case = os.environ.get("P2_3D_PILOT_CASE", "valid")
        if case not in {"valid", "invalid-contract"}:
            raise ValueError("P2_3D_PILOT_CASE is unsupported")
        fixtures = Path("/app/p2_3d_fixtures")
        sink = PortalIngestionSink(
            portal_url,
            MetadataIdentityTokenProvider(),
            tamper_contract=case == "invalid-contract",
        )
        request = RunRequest(
            project_id=PROJECT_ID,
            provider="ga4",
            week_start=WEEK_START,
            idempotency_key="30000000-0000-0000-0000-000000000001",
            environment="production",
            operator_audit_identity="p2-3d-manual-cloud-run-job",
        )
        app = IngestionApplication(
            FixtureConfigurationProvider(fixtures / "ga4_configuration.json"),
            FixtureCredentialProvider(),
            {"ga4": FixtureWeeklyProvider(fixtures / "ga4_provider.json", "ga4")},
            sink,
            logger=SafeJsonLogger(stream=sys.stdout),
        )
        outcome = app.run(request)
        expected_failure = case == "invalid-contract"
        accepted = outcome.exit_code == 0
        proof_ok = (accepted and not expected_failure) or (not accepted and expected_failure)
        print(
            json.dumps(
                {
                    "event": "p2_3d_pilot_result",
                    "case": case,
                    "proof_ok": proof_ok,
                    "status": outcome.status,
                    "error_code": outcome.error_code,
                    "payload_hash": outcome.payload.get("normalized_payload_hash") if outcome.payload else None,
                    "portal": sink.last_response,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            flush=True,
        )
        return 0 if proof_ok else int(outcome.exit_code or 1)
    except Exception:
        print(
            json.dumps(
                {"event": "p2_3d_pilot_result", "proof_ok": False, "status": "failed", "error_code": "pilot_configuration_refused"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
