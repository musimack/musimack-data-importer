"""Build, hash, and validate the normalized weekly ingestion contract."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from .budget import ProviderRequestBudget
from .domain import BeginReceipt, IngestionConfiguration, ProviderOutput, RunRequest, SUPPORTED_PROVIDERS
from .errors import ContractError

RESULT_SCHEMA = "weekly_provider_ingestion.v1"
RUN_SCHEMA = "weekly_ingestion_run.v1"
FAILURE_SCHEMA = "weekly_ingestion_failure.v1"
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "authorization",
        "token",
        "secret",
        "raw_payload",
        "raw_response",
        "credential",
        "credential_binding_key",
        "external_resource_id",
        "property_id",
        "site_url",
    }
)


def build_begin_payload(request: RunRequest, configuration: IngestionConfiguration) -> dict[str, Any]:
    return {
        "contract_version": RUN_SCHEMA,
        "project_id": request.project_id,
        "provider": request.provider,
        "week_start": request.week_start.isoformat(),
        "reporting_timezone": configuration.reporting_timezone,
        "trigger_type": request.trigger_type,
        "operator_audit_identity": request.operator_audit_identity,
        "idempotency_key": request.idempotency_key,
        "configuration_identity": configuration.identity,
        "configuration_version": configuration.version,
        "requested_at": _timestamp(request.requested_at),
    }


def build_result_payload(
    request: RunRequest,
    configuration: IngestionConfiguration,
    output: ProviderOutput,
    budget: ProviderRequestBudget,
    *,
    sent_at: datetime,
) -> dict[str, Any]:
    payload = {
        "schema_version": RESULT_SCHEMA,
        "project_id": request.project_id,
        "provider": request.provider,
        "week": {
            "start": request.week_start.isoformat(),
            "end": request.week_end.isoformat(),
            "timezone": configuration.reporting_timezone,
            "inclusive_dates": True,
        },
        "configuration": {"identity": configuration.identity, "version": configuration.version},
        "freshness": copy.deepcopy(output.freshness),
        "source": copy.deepcopy(output.source),
        "metrics": copy.deepcopy(output.metrics),
        "daily": copy.deepcopy(output.daily),
        "ranked": copy.deepcopy(output.ranked),
        "evidence": {
            "requests_consumed": budget.requests_consumed,
            "retry_count": budget.retry_count,
            "direct_cost_usd": output.direct_cost_usd,
            "bigquery_bytes_processed": None,
        },
        "sent_at": _timestamp(sent_at),
    }
    payload["normalized_payload_hash"] = canonical_payload_hash(payload)
    validate_result_payload(payload, maximum_bytes=configuration.max_payload_bytes)
    return payload


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    semantic = copy.deepcopy(payload)
    semantic.pop("normalized_payload_hash", None)
    semantic.pop("sent_at", None)
    try:
        encoded = json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("contract content is not canonically serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def serialized_size(payload: dict[str, Any]) -> int:
    try:
        return len(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("contract content is not serializable") from exc


def validate_result_payload(payload: dict[str, Any], *, maximum_bytes: int) -> None:
    required = {
        "schema_version",
        "project_id",
        "provider",
        "week",
        "configuration",
        "freshness",
        "source",
        "metrics",
        "daily",
        "ranked",
        "evidence",
        "normalized_payload_hash",
        "sent_at",
    }
    if set(payload) != required:
        raise ContractError("normalized contract fields do not match the v1 schema")
    if payload["schema_version"] != RESULT_SCHEMA:
        raise ContractError("normalized contract schema version is unsupported")
    try:
        UUID(str(payload["project_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError("normalized contract project_id must be a UUID") from exc
    if payload["provider"] not in SUPPORTED_PROVIDERS:
        raise ContractError("normalized contract provider is unsupported")
    if serialized_size(payload) > maximum_bytes:
        raise ContractError("normalized contract exceeds the approved payload limit")
    _scan_forbidden(payload)
    week = payload.get("week")
    if not isinstance(week, dict) or week.get("inclusive_dates") is not True:
        raise ContractError("weekly contract must use inclusive dates")
    start = _parse_date(week.get("start"), "week start")
    end = _parse_date(week.get("end"), "week end")
    if (end - start).days != 6 or start.weekday() != 0:
        raise ContractError("weekly contract must contain one Monday-through-Sunday week")
    configuration = payload.get("configuration")
    if (
        not isinstance(configuration, dict)
        or not isinstance(configuration.get("identity"), str)
        or not configuration["identity"]
        or not isinstance(configuration.get("version"), int)
        or configuration["version"] < 1
    ):
        raise ContractError("normalized contract configuration identity/version is invalid")
    _validate_freshness(payload.get("freshness"), start, end)
    source = payload.get("source")
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("identity"), str)
        or not source["identity"]
        or not isinstance(source.get("contract_version"), int)
        or source["contract_version"] < 1
    ):
        raise ContractError("normalized contract source identity/version is invalid")
    for collection in ("metrics", "daily", "ranked"):
        if not isinstance(payload.get(collection), list):
            raise ContractError(f"{collection} observations must be a list")
    for item in payload["metrics"]:
        _validate_metric(item)
    for item in payload["daily"]:
        _validate_metric(item, require_date=True)
        item_date = _parse_date(item.get("date"), "daily observation date")
        if not start <= item_date <= end:
            raise ContractError("daily observation is outside the requested week")
    for item in payload["ranked"]:
        if not isinstance(item, dict) or not isinstance(item.get("rank"), int) or item["rank"] < 1:
            raise ContractError("ranked observation requires a positive rank")
        if not all(isinstance(item.get(key), str) and item[key] for key in ("dimension", "identity", "label")):
            raise ContractError("ranked observation identity fields are required")
        _validate_metric(item.get("metric"))
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise ContractError("request evidence is required")
    if not isinstance(evidence.get("requests_consumed"), int) or evidence["requests_consumed"] < 0:
        raise ContractError("request evidence is invalid")
    if not isinstance(evidence.get("retry_count"), int) or evidence["retry_count"] < 0:
        raise ContractError("retry evidence is invalid")
    if evidence["retry_count"] > evidence["requests_consumed"]:
        raise ContractError("retry evidence exceeds total provider requests")
    if evidence["requests_consumed"] > 12:
        raise ContractError("request evidence exceeds the approved task maximum")
    direct_cost = evidence.get("direct_cost_usd")
    if isinstance(direct_cost, bool) or not isinstance(direct_cost, (int, float)) or direct_cost < 0:
        raise ContractError("direct cost evidence is invalid")
    if evidence.get("bigquery_bytes_processed") is not None:
        raise ContractError("BigQuery evidence is prohibited in P2-3B")
    expected_hash = canonical_payload_hash(payload)
    actual_hash = payload.get("normalized_payload_hash")
    if not isinstance(actual_hash, str) or not HASH_PATTERN.fullmatch(actual_hash) or actual_hash != expected_hash:
        raise ContractError("normalized payload hash does not match canonical content")


def build_failure_payload(
    request: RunRequest,
    configuration: IngestionConfiguration,
    receipt: BeginReceipt,
    budget: ProviderRequestBudget,
    error,
    *,
    failed_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": FAILURE_SCHEMA,
        "run_id": receipt.run_id,
        "project_id": request.project_id,
        "provider": request.provider,
        "week_start": request.week_start.isoformat(),
        "configuration": {"identity": configuration.identity, "version": configuration.version},
        "error": {"code": error.code, "message": error.safe_message, "phase": error.phase},
        "evidence": {
            "requests_consumed": budget.requests_consumed,
            "retry_count": budget.retry_count,
        },
        "failed_at": _timestamp(failed_at),
    }


def _validate_metric(item: Any, *, require_date: bool = False) -> None:
    if not isinstance(item, dict):
        raise ContractError("metric observation must be an object")
    required = {"metric_key", "value", "unit", "aggregation", "provenance"}
    if require_date:
        required.add("date")
    if not required.issubset(item):
        raise ContractError("metric observation is missing required fields")
    if not isinstance(item["metric_key"], str) or not item["metric_key"]:
        raise ContractError("metric key is required")
    value = item["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ContractError("metric value must be a finite number")
    if not all(isinstance(item[key], str) and item[key] for key in ("unit", "aggregation", "provenance")):
        raise ContractError("metric unit, aggregation, and provenance are required")


def _validate_freshness(value: Any, start: date, end: date) -> None:
    if not isinstance(value, dict):
        raise ContractError("freshness evidence is required")
    required = {
        "state",
        "available_through",
        "first_available_date",
        "last_available_date",
        "expected_observation_count",
        "actual_observation_count",
        "missing_observation_count",
        "generated_at",
        "checked_at",
    }
    if set(value) != required:
        raise ContractError("freshness fields do not match the v1 schema")
    if value["state"] not in {"available", "partial", "unavailable"}:
        raise ContractError("freshness state is invalid")
    counts = [
        value["expected_observation_count"],
        value["actual_observation_count"],
        value["missing_observation_count"],
    ]
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in counts):
        raise ContractError("freshness observation counts are invalid")
    if counts[1] + counts[2] != counts[0]:
        raise ContractError("freshness observation counts contradict each other")
    date_values = [value["available_through"], value["first_available_date"], value["last_available_date"]]
    if value["state"] == "unavailable":
        if any(item is not None for item in date_values):
            raise ContractError("unavailable freshness must not claim available dates")
    else:
        if any(item is None for item in date_values):
            raise ContractError("available or partial freshness requires available dates")
        parsed = [_parse_date(item, "freshness date") for item in date_values]
        if not all(start <= item <= end for item in parsed):
            raise ContractError("freshness date falls outside the requested week")
        if parsed[1] > parsed[2] or parsed[0] != parsed[2]:
            raise ContractError("freshness date bounds contradict each other")
    for key in ("generated_at", "checked_at"):
        try:
            parsed = datetime.fromisoformat(str(value[key]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError("freshness timestamps must be ISO datetimes") from exc
        if parsed.tzinfo is None:
            raise ContractError("freshness timestamps must include a timezone")


def _scan_forbidden(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ContractError("normalized contract contains a forbidden raw or credential field")
            _scan_forbidden(child)
    elif isinstance(value, list):
        for child in value:
            _scan_forbidden(child)


def _parse_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ContractError(f"{label} must be an ISO date") from exc


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
