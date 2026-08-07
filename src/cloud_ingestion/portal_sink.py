"""Private Portal delivery sink for the bounded P2-3D pilot."""

from __future__ import annotations

import copy
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from uuid import uuid4

from .domain import BeginReceipt, IngestionConfiguration, RunRequest
from .errors import SinkError
from .ports import IdentityTokenProvider


@dataclass(frozen=True)
class _DeliveryContext:
    request: RunRequest
    configuration: IngestionConfiguration


class PortalIngestionSink:
    """Deliver one contract with the same token at both authorization layers."""

    def __init__(
        self,
        portal_url: str,
        identity_tokens: IdentityTokenProvider,
        *,
        tamper_contract: bool = False,
    ) -> None:
        base = portal_url.rstrip("/")
        if not base.startswith("https://") or "*" in base:
            raise SinkError("the Portal URL must be an exact https URL")
        self.portal_url = base
        self._identity_tokens = identity_tokens
        self._tamper_contract = tamper_contract
        self._contexts: dict[str, _DeliveryContext] = {}
        self.last_response: dict | None = None

    def begin(self, request: RunRequest, configuration: IngestionConfiguration) -> BeginReceipt:
        run_id = str(uuid4())
        self._contexts[run_id] = _DeliveryContext(request, configuration)
        return BeginReceipt(
            run_id=run_id,
            cycle_id=str(uuid4()),
            week_end=request.week_end,
            accepted_configuration_version=configuration.version,
            max_payload_bytes=configuration.max_payload_bytes,
        )

    def complete(self, receipt: BeginReceipt, payload: dict) -> None:
        context = self._contexts.pop(receipt.run_id, None)
        if context is None:
            raise SinkError("delivery context was unavailable")
        delivered = copy.deepcopy(payload)
        if self._tamper_contract:
            delivered["metrics"][0]["value"] = delivered["metrics"][0]["value"] + 1
        envelope = {
            "envelope_version": "portal_provider_ingestion_envelope.v1",
            "workload": {"environment": context.request.environment},
            "resource": {
                "provider": context.request.provider,
                "identity": context.configuration.external_resource_id,
                "identity_kind": context.configuration.external_resource_type,
            },
            "run": {"importer_run_id": receipt.run_id},
            "payload": delivered,
        }
        token = self._identity_tokens.token_for_audience(self.portal_url)
        request = urllib.request.Request(
            f"{self.portal_url}/api/service/v1/provider-ingestions",
            data=json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "X-Serverless-Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(64 * 1024)
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(64 * 1024)
        except Exception as exc:
            raise SinkError("Portal delivery transport failed") from exc
        try:
            parsed = json.loads(body)
        except Exception as exc:
            raise SinkError("Portal returned a malformed response") from exc
        self.last_response = {
            key: parsed.get(key)
            for key in (
                "accepted",
                "outcome",
                "error_code",
                "weekly_cycle_id",
                "refresh_run_id",
                "revision_id",
                "revision_number",
                "verified_payload_hash",
                "current_pointer_outcome",
                "is_current",
                "scalar_observation_count",
                "daily_observation_count",
                "ranked_observation_count",
            )
            if key in parsed
        }
        if status != 200 or parsed.get("accepted") is not True:
            raise SinkError("Portal refused the normalized contract")

    def fail(self, receipt: BeginReceipt, payload: dict) -> None:
        self._contexts.pop(receipt.run_id, None)
