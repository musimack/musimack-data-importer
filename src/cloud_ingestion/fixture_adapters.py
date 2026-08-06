"""Synthetic adapters for contract conformance and local/cloud parity tests only."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from .budget import ProviderRequestBudget
from .contract import build_begin_payload
from .domain import (
    BeginReceipt,
    CredentialMaterial,
    IngestionConfiguration,
    ProviderOutput,
    RunRequest,
)
from .errors import ConfigurationError, CredentialError, ProviderError, SinkError

CONFIGURATION_SCHEMA = "project_ingestion_configuration.v1"
FIXTURE_PROVIDER_SCHEMA = "weekly_provider_fixture.v1"


def _read_object(path: Path, label: str, error_type=ConfigurationError) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_type(f"{label} could not be read as JSON") from exc
    if not isinstance(payload, dict):
        raise error_type(f"{label} must contain a JSON object")
    return payload


@dataclass(frozen=True)
class FixtureConfigurationProvider:
    path: Path

    def load(self, request: RunRequest) -> IngestionConfiguration:
        payload = _read_object(self.path, "fixture configuration")
        if payload.get("schema_version") != CONFIGURATION_SCHEMA:
            raise ConfigurationError("fixture configuration schema is unsupported")
        try:
            return IngestionConfiguration(
                identity=payload["identity"],
                version=payload["version"],
                client_id=payload["client_id"],
                project_id=payload["project_id"],
                project_slug=payload["project_slug"],
                provider=payload["provider"],
                environment=payload["environment"],
                reporting_timezone=payload["reporting_timezone"],
                external_resource_type=payload["external_resource_type"],
                external_resource_id=payload["external_resource_id"],
                credential_binding_key=payload["credential_binding_key"],
                request_ceiling=payload["request_ceiling"],
                authorized_retry_count=payload.get("authorized_retry_count", 0),
                max_payload_bytes=payload.get("max_payload_bytes", 2 * 1024 * 1024),
                enabled=payload["enabled"],
            )
        except KeyError as exc:
            raise ConfigurationError("fixture configuration is missing a required field") from exc


@dataclass
class FixtureCredentialProvider:
    resolutions: int = 0

    def resolve(self, configuration: IngestionConfiguration) -> CredentialMaterial:
        self.resolutions += 1
        if not configuration.credential_binding_key.startswith("fixture/"):
            raise CredentialError()
        # The marker is deliberately not a token and never leaves memory.
        return CredentialMaterial(configuration.credential_binding_key, "fixture-v1", object())


@dataclass
class FixtureIdentityTokenProvider:
    expected_audience: str
    requests: list[str] = field(default_factory=list)

    def token_for_audience(self, audience: str) -> str:
        self.requests.append(audience)
        if audience != self.expected_audience or not audience.startswith("https://"):
            raise CredentialError("fixture identity audience mismatch")
        return "fixture-identity-token"


@dataclass(frozen=True)
class FixtureWeeklyProvider:
    path: Path
    provider: str

    def planned_requests(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
    ) -> int:
        payload = self._load(request)
        operations = payload.get("request_operations")
        if not isinstance(operations, list):
            raise ProviderError("provider fixture request plan is invalid")
        return len(operations)

    def retrieve(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
        credential: CredentialMaterial,
        budget: ProviderRequestBudget,
    ) -> ProviderOutput:
        payload = self._load(request)
        operations = payload.get("request_operations")
        if not isinstance(operations, list) or not all(isinstance(value, str) and value for value in operations):
            raise ProviderError("provider fixture request plan is invalid")
        for operation in operations:
            budget.consume(operation)
        normalized = payload.get("normalized")
        if not isinstance(normalized, dict):
            raise ProviderError("provider fixture normalized output is missing")
        try:
            return ProviderOutput(
                freshness=normalized["freshness"],
                source=normalized["source"],
                metrics=normalized["metrics"],
                daily=normalized["daily"],
                ranked=normalized["ranked"],
                direct_cost_usd=float(normalized.get("direct_cost_usd", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("provider fixture normalized output is invalid") from exc

    def _load(self, request: RunRequest) -> dict[str, Any]:
        payload = _read_object(self.path, "provider fixture", ProviderError)
        if payload.get("schema_version") != FIXTURE_PROVIDER_SCHEMA:
            raise ProviderError("provider fixture schema is unsupported")
        if payload.get("provider") != request.provider or request.provider != self.provider:
            raise ProviderError("provider fixture does not match the task")
        if payload.get("week_start") != request.week_start.isoformat():
            raise ProviderError("provider fixture week does not match the task")
        return payload


@dataclass
class MemoryIngestionSink:
    begin_calls: list[dict[str, Any]] = field(default_factory=list)
    completed: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)

    def begin(self, request: RunRequest, configuration: IngestionConfiguration) -> BeginReceipt:
        self.begin_calls.append(build_begin_payload(request, configuration))
        return BeginReceipt(
            run_id=request.idempotency_key,
            cycle_id=str(UUID(int=0)),
            week_end=request.week_end,
            accepted_configuration_version=configuration.version,
            max_payload_bytes=configuration.max_payload_bytes,
        )

    def complete(self, receipt: BeginReceipt, payload: dict) -> None:
        self.completed.append(payload)

    def fail(self, receipt: BeginReceipt, payload: dict) -> None:
        self.failed.append(payload)


@dataclass
class FixtureFileIngestionSink(MemoryIngestionSink):
    output_path: Path | None = None

    def complete(self, receipt: BeginReceipt, payload: dict) -> None:
        super().complete(receipt, payload)
        if self.output_path is not None:
            _atomic_write_json(self.output_path, payload)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SinkError() from exc
