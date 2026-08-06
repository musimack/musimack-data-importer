"""Cloud-ready, provider-neutral weekly ingestion application boundary."""

from .application import IngestionApplication, RunOutcome
from .domain import IngestionConfiguration, RunRequest
from .exit_codes import ExitCode

__all__ = [
    "ExitCode",
    "IngestionApplication",
    "IngestionConfiguration",
    "RunOutcome",
    "RunRequest",
]
