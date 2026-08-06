"""Validated domain values for one project/provider/week ingestion task."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ConfigurationError, InputError

SUPPORTED_PROVIDERS = frozenset({"ga4", "gsc"})
SUPPORTED_ENVIRONMENTS = frozenset({"development", "production"})
MAX_NORMALIZED_PAYLOAD_BYTES = 2 * 1024 * 1024


def _uuid_text(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InputError(f"{label} must be a UUID") from exc


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ConfigurationError("reporting timezone must be a valid IANA name") from exc
    return value


@dataclass(frozen=True)
class RunRequest:
    project_id: str
    provider: str
    week_start: date
    idempotency_key: str
    environment: str
    trigger_type: str = "manual_operator"
    operator_audit_identity: str = "fixture-operator"
    pinned_configuration_version: int | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _uuid_text(self.project_id, "project_id"))
        object.__setattr__(self, "idempotency_key", _uuid_text(self.idempotency_key, "idempotency_key"))
        if self.provider not in SUPPORTED_PROVIDERS:
            raise InputError("provider must be ga4 or gsc")
        if self.environment not in SUPPORTED_ENVIRONMENTS:
            raise InputError("environment must be development or production")
        if self.week_start.weekday() != 0:
            raise InputError("week_start must be a Monday")
        if self.trigger_type != "manual_operator":
            raise InputError("P2-3B permits manual_operator trigger only")
        if self.requested_at.tzinfo is None:
            raise InputError("requested_at must include a timezone")

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=6)


@dataclass(frozen=True)
class IngestionConfiguration:
    identity: str
    version: int
    client_id: str
    project_id: str
    project_slug: str
    provider: str
    environment: str
    reporting_timezone: str
    external_resource_type: str
    external_resource_id: str
    credential_binding_key: str
    request_ceiling: int
    enabled: bool
    authorized_retry_count: int = 0
    max_payload_bytes: int = MAX_NORMALIZED_PAYLOAD_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(self, "client_id", _uuid_text(self.client_id, "client_id"))
        object.__setattr__(self, "project_id", _uuid_text(self.project_id, "project_id"))
        object.__setattr__(self, "reporting_timezone", _timezone(self.reporting_timezone))
        if not self.identity or self.version < 1:
            raise ConfigurationError("configuration identity and positive version are required")
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ConfigurationError("configuration provider is unsupported")
        if self.environment not in SUPPORTED_ENVIRONMENTS:
            raise ConfigurationError("configuration environment is unsupported")
        if not self.project_slug or not self.external_resource_type or not self.external_resource_id:
            raise ConfigurationError("project and provider resource mapping are required")
        if not self.credential_binding_key:
            raise ConfigurationError("opaque credential binding key is required")
        if not isinstance(self.request_ceiling, int) or isinstance(self.request_ceiling, bool):
            raise ConfigurationError("request ceiling must be an integer")
        if self.request_ceiling < 0:
            raise ConfigurationError("request ceiling cannot be negative")
        if not isinstance(self.authorized_retry_count, int) or isinstance(self.authorized_retry_count, bool):
            raise ConfigurationError("authorized retry count must be an integer")
        if self.authorized_retry_count < 0:
            raise ConfigurationError("authorized retry count cannot be negative")
        if self.max_payload_bytes < 1 or self.max_payload_bytes > MAX_NORMALIZED_PAYLOAD_BYTES:
            raise ConfigurationError("maximum payload exceeds the approved 2 MiB limit")

    def authorize(self, request: RunRequest) -> None:
        if not self.enabled:
            raise ConfigurationError("configuration is disabled")
        if self.project_id != request.project_id or self.provider != request.provider:
            raise ConfigurationError("configuration does not match the requested project/provider")
        if self.environment != request.environment:
            raise ConfigurationError("configuration environment does not match the task")
        if request.pinned_configuration_version not in (None, self.version):
            raise ConfigurationError("pinned configuration version does not match")


@dataclass(frozen=True)
class CredentialMaterial:
    binding_key: str
    version_label: str
    value: Any = field(repr=False, compare=False)


@dataclass(frozen=True)
class ProviderOutput:
    freshness: dict[str, Any]
    source: dict[str, Any]
    metrics: list[dict[str, Any]]
    daily: list[dict[str, Any]]
    ranked: list[dict[str, Any]]
    direct_cost_usd: float = 0.0


@dataclass(frozen=True)
class BeginReceipt:
    run_id: str
    cycle_id: str
    week_end: date
    accepted_configuration_version: int
    max_payload_bytes: int
