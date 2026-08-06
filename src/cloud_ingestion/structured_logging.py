"""Allowlisted JSON events that never serialize provider values or credentials."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, TextIO

ALLOWED_FIELDS = frozenset(
    {
        "event",
        "phase",
        "provider",
        "run_id",
        "status",
        "error_code",
        "requests_consumed",
        "retry_count",
        "configuration_version",
        "payload_bytes",
        "payload_hash",
    }
)


@dataclass
class SafeJsonLogger:
    stream: TextIO = sys.stdout
    captured: list[dict[str, Any]] = field(default_factory=list)
    writer: Callable[[str], None] | None = None

    def emit(self, event: str, **fields: Any) -> None:
        record = {"event": event}
        for key, value in fields.items():
            if key not in ALLOWED_FIELDS:
                raise ValueError(f"structured log field is not allowlisted: {key}")
            if value is not None:
                record[key] = value
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.captured.append(record)
        if self.writer is not None:
            self.writer(encoded)
        else:
            print(encoded, file=self.stream, flush=True)
