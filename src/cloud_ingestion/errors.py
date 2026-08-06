"""Closed, safe error taxonomy shared by the application and CLI."""

from __future__ import annotations

from .exit_codes import ExitCode


class IngestionError(RuntimeError):
    code = "internal_failure"
    phase = "internal"
    exit_code = ExitCode.INTERNAL_FAILED
    safe_message = "The ingestion task failed safely."


class InputError(IngestionError):
    code = "invalid_input"
    phase = "input"
    exit_code = ExitCode.INVALID_INPUT
    safe_message = "The ingestion task input was invalid."


class ConfigurationError(IngestionError):
    code = "configuration_refused"
    phase = "configuration"
    exit_code = ExitCode.CONFIGURATION_REFUSED
    safe_message = "The ingestion configuration was refused."


class BudgetError(IngestionError):
    code = "request_budget_refused"
    phase = "request_budget"
    exit_code = ExitCode.REQUEST_BUDGET_REFUSED
    safe_message = "The approved provider request budget refused the operation."


class CredentialError(IngestionError):
    code = "credential_resolution_failed"
    phase = "credential_resolution"
    exit_code = ExitCode.CREDENTIAL_RESOLUTION_FAILED
    safe_message = "Credential resolution failed safely."


class ProviderError(IngestionError):
    code = "provider_failed"
    phase = "provider_retrieval"
    exit_code = ExitCode.PROVIDER_FAILED
    safe_message = "The provider operation failed safely."


class ContractError(IngestionError):
    code = "contract_failed"
    phase = "normalization"
    exit_code = ExitCode.CONTRACT_FAILED
    safe_message = "The normalized ingestion contract was invalid."


class SinkError(IngestionError):
    code = "sink_failed"
    phase = "delivery"
    exit_code = ExitCode.SINK_FAILED
    safe_message = "The ingestion sink failed safely."


class TerminationError(IngestionError):
    code = "task_terminated"
    phase = "execution"
    exit_code = ExitCode.INTERNAL_FAILED
    safe_message = "The ingestion task received a termination signal."
