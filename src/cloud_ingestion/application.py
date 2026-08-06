"""One-shot ingestion application service with fail-closed dependency ordering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from .budget import ProviderRequestBudget
from .contract import build_failure_payload, build_result_payload, serialized_size
from .domain import BeginReceipt, IngestionConfiguration, RunRequest
from .errors import (
    ConfigurationError,
    ContractError,
    CredentialError,
    IngestionError,
    ProviderError,
    SinkError,
)
from .exit_codes import ExitCode
from .ports import ConfigurationProvider, CredentialProvider, IngestionSink, WeeklyProvider
from .structured_logging import SafeJsonLogger


@dataclass(frozen=True)
class RunOutcome:
    exit_code: ExitCode
    status: str
    error_code: str | None = None
    run_id: str | None = None
    payload: dict | None = None


class IngestionApplication:
    def __init__(
        self,
        configuration_provider: ConfigurationProvider,
        credential_provider: CredentialProvider,
        providers: Mapping[str, WeeklyProvider],
        sink: IngestionSink,
        *,
        logger: SafeJsonLogger | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration_provider = configuration_provider
        self._credential_provider = credential_provider
        self._providers = dict(providers)
        self._sink = sink
        self._logger = logger or SafeJsonLogger()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, request: RunRequest) -> RunOutcome:
        configuration: IngestionConfiguration | None = None
        receipt: BeginReceipt | None = None
        budget: ProviderRequestBudget | None = None
        try:
            self._logger.emit("ingestion_started", phase="configuration", provider=request.provider)
            configuration = self._load_and_authorize(request)
            budget = ProviderRequestBudget(
                request.provider,
                configuration.request_ceiling,
                configuration.authorized_retry_count,
            )
            provider = self._providers.get(request.provider)
            if provider is None or provider.provider != request.provider:
                raise ConfigurationError("no provider adapter is registered for the request")
            budget.check_plan(provider.planned_requests(request, configuration))

            # The durable attempt begins before any credential is resolved or provider call is possible.
            try:
                receipt = self._sink.begin(request, configuration)
            except Exception as exc:
                raise SinkError() from exc
            self._validate_receipt(request, configuration, receipt)
            self._logger.emit(
                "ingestion_attempt_begun",
                phase="begin",
                provider=request.provider,
                run_id=receipt.run_id,
                configuration_version=configuration.version,
            )

            try:
                credential = self._credential_provider.resolve(configuration)
            except IngestionError:
                raise
            except Exception as exc:
                raise CredentialError() from exc
            if credential.binding_key != configuration.credential_binding_key or not credential.version_label:
                raise CredentialError()

            try:
                output = provider.retrieve(request, configuration, credential, budget)
            except IngestionError:
                raise
            except Exception as exc:
                raise ProviderError() from exc

            payload = build_result_payload(
                request,
                configuration,
                output,
                budget,
                sent_at=self._clock(),
            )
            if serialized_size(payload) > min(configuration.max_payload_bytes, receipt.max_payload_bytes):
                raise ContractError("normalized contract exceeds the sink payload limit")
            try:
                self._sink.complete(receipt, payload)
            except Exception as exc:
                raise SinkError() from exc
            self._logger.emit(
                "ingestion_completed",
                phase="delivery",
                provider=request.provider,
                run_id=receipt.run_id,
                status="completed",
                requests_consumed=budget.requests_consumed,
                retry_count=budget.retry_count,
                payload_bytes=serialized_size(payload),
                payload_hash=payload["normalized_payload_hash"],
            )
            return RunOutcome(ExitCode.SUCCESS, "completed", run_id=receipt.run_id, payload=payload)
        except IngestionError as error:
            return self._fail(request, configuration, receipt, budget, error)
        except Exception:
            return self._fail(request, configuration, receipt, budget, IngestionError())

    def _load_and_authorize(self, request: RunRequest) -> IngestionConfiguration:
        try:
            configuration = self._configuration_provider.load(request)
            configuration.authorize(request)
            return configuration
        except IngestionError:
            raise
        except Exception as exc:
            raise ConfigurationError() from exc

    def _fail(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration | None,
        receipt: BeginReceipt | None,
        budget: ProviderRequestBudget | None,
        error: IngestionError,
    ) -> RunOutcome:
        requests_consumed = budget.requests_consumed if budget else 0
        retry_count = budget.retry_count if budget else 0
        if configuration is not None and receipt is not None and budget is not None:
            failure = build_failure_payload(
                request,
                configuration,
                receipt,
                budget,
                error,
                failed_at=self._clock(),
            )
            try:
                self._sink.fail(receipt, failure)
            except Exception:
                error = SinkError()
        self._logger.emit(
            "ingestion_failed",
            phase=error.phase,
            provider=request.provider,
            run_id=receipt.run_id if receipt else None,
            status="failed",
            error_code=error.code,
            requests_consumed=requests_consumed,
            retry_count=retry_count,
        )
        return RunOutcome(error.exit_code, "failed", error_code=error.code, run_id=receipt.run_id if receipt else None)

    @staticmethod
    def _validate_receipt(
        request: RunRequest,
        configuration: IngestionConfiguration,
        receipt: BeginReceipt,
    ) -> None:
        if receipt.week_end != request.week_end:
            raise SinkError("sink returned a different canonical week")
        if receipt.accepted_configuration_version != configuration.version:
            raise SinkError("sink returned a different configuration version")
        if receipt.max_payload_bytes < 1:
            raise SinkError("sink returned an invalid payload limit")
