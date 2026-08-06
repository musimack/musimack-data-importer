"""Dependency-inversion ports for configuration, credentials, providers, identity, and sinks."""

from __future__ import annotations

from typing import Protocol

from .budget import ProviderRequestBudget
from .domain import (
    BeginReceipt,
    CredentialMaterial,
    IngestionConfiguration,
    ProviderOutput,
    RunRequest,
)


class ConfigurationProvider(Protocol):
    def load(self, request: RunRequest) -> IngestionConfiguration: ...


class CredentialProvider(Protocol):
    def resolve(self, configuration: IngestionConfiguration) -> CredentialMaterial: ...


class WeeklyProvider(Protocol):
    provider: str

    def planned_requests(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
    ) -> int: ...

    def retrieve(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
        credential: CredentialMaterial,
        budget: ProviderRequestBudget,
    ) -> ProviderOutput: ...


class IngestionSink(Protocol):
    def begin(self, request: RunRequest, configuration: IngestionConfiguration) -> BeginReceipt: ...

    def complete(self, receipt: BeginReceipt, payload: dict) -> None: ...

    def fail(self, receipt: BeginReceipt, payload: dict) -> None: ...


class IdentityTokenProvider(Protocol):
    """Future Portal sinks obtain a short-lived exact-audience token through this port."""

    def token_for_audience(self, audience: str) -> str: ...
