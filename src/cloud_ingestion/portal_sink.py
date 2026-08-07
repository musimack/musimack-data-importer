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
        self.response_history: list[dict] = []
        self._last_envelope: dict | None = None

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
        self._last_envelope = copy.deepcopy(envelope)
        self._deliver(envelope)

    def replay_last_delivery(self) -> dict:
        """Replay the exact in-memory envelope without another provider call."""
        if self._last_envelope is None:
            raise SinkError("no completed delivery is available for replay")
        self._deliver(copy.deepcopy(self._last_envelope))
        return copy.deepcopy(self.last_response or {})

    def prove_invalid_contract(self) -> dict:
        """Submit a hash-invalid copy with a fresh run id and expect refusal."""
        if self._last_envelope is None:
            raise SinkError("no completed delivery is available for negative proof")
        envelope = copy.deepcopy(self._last_envelope)
        envelope["run"]["importer_run_id"] = str(uuid4())
        metrics = envelope.get("payload", {}).get("metrics", [])
        if not metrics or not isinstance(metrics[0].get("value"), (int, float)):
            raise SinkError("the normalized contract cannot be safely tampered")
        metrics[0]["value"] += 1
        try:
            self._deliver(envelope)
        except SinkError:
            response = copy.deepcopy(self.last_response or {})
            if response.get("accepted") is False:
                return response
            raise
        raise SinkError("the Portal accepted an invalid normalized contract")

    def prove_resource_mismatch(self) -> dict:
        """Submit a wrong governed resource without making a provider call."""
        if self._last_envelope is None:
            raise SinkError("no completed delivery is available for negative proof")
        envelope = copy.deepcopy(self._last_envelope)
        envelope["run"]["importer_run_id"] = str(uuid4())
        kind = envelope.get("resource", {}).get("identity_kind")
        envelope["resource"]["identity"] = (
            "properties/999999999" if kind == "ga4_property" else "https://wrong.invalid/"
        )
        try:
            self._deliver(envelope)
        except SinkError:
            response = copy.deepcopy(self.last_response or {})
            if response.get("error_code") == "resource_mismatch":
                return response
            raise
        raise SinkError("the Portal accepted a mismatched provider resource")

    def _deliver(self, envelope: dict) -> None:
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
        self.response_history.append(copy.deepcopy(self.last_response))
        if status != 200 or parsed.get("accepted") is not True:
            raise SinkError("Portal refused the normalized contract")

    def fail(self, receipt: BeginReceipt, payload: dict) -> None:
        self._contexts.pop(receipt.run_id, None)
