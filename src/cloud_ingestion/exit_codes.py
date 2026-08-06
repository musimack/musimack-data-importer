"""Deterministic one-shot process exits for the P2-3B job entrypoint."""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_INPUT = 2
    CONFIGURATION_REFUSED = 3
    REQUEST_BUDGET_REFUSED = 4
    CREDENTIAL_RESOLUTION_FAILED = 5
    PROVIDER_FAILED = 6
    CONTRACT_FAILED = 7
    SINK_FAILED = 8
    INTERNAL_FAILED = 9
