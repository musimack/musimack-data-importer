"""Noninteractive, one-shot P2-3B entrypoint. Only synthetic fixture adapters exist."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import date
from pathlib import Path

from .application import IngestionApplication
from .domain import RunRequest
from .errors import IngestionError, TerminationError
from .exit_codes import ExitCode
from .fixture_adapters import (
    FixtureConfigurationProvider,
    FixtureCredentialProvider,
    FixtureFileIngestionSink,
    FixtureWeeklyProvider,
)
from .structured_logging import SafeJsonLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded synthetic weekly ingestion task without provider or Portal calls."
    )
    parser.add_argument("--configuration-fixture", required=True, type=Path)
    parser.add_argument("--provider-fixture", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--provider", required=True, choices=("ga4", "gsc"))
    parser.add_argument("--week-start", required=True, help="Monday in YYYY-MM-DD format")
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--environment", required=True, choices=("development", "production"))
    parser.add_argument("--configuration-version", type=int)
    parser.add_argument(
        "--result-out",
        type=Path,
        help="Optional fixture-only normalized contract output. Omit for stateless execution.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        request = RunRequest(
            project_id=args.project_id,
            provider=args.provider,
            week_start=date.fromisoformat(args.week_start),
            idempotency_key=args.idempotency_key,
            environment=args.environment,
            pinned_configuration_version=args.configuration_version,
        )
    except ValueError:
        _safe_cli_error("invalid_input")
        return int(ExitCode.INVALID_INPUT)
    except IngestionError as exc:
        _safe_cli_error(exc.code)
        return int(exc.exit_code)

    logger = SafeJsonLogger(stream=sys.stdout)
    sink = FixtureFileIngestionSink(output_path=args.result_out)
    app = IngestionApplication(
        FixtureConfigurationProvider(args.configuration_fixture),
        FixtureCredentialProvider(),
        {args.provider: FixtureWeeklyProvider(args.provider_fixture, args.provider)},
        sink,
        logger=logger,
    )
    previous_handlers = _install_signal_handlers()
    try:
        outcome = app.run(request)
    finally:
        _restore_signal_handlers(previous_handlers)
    print(
        json.dumps(
            {
                "event": "ingestion_process_exit",
                "status": outcome.status,
                "error_code": outcome.error_code,
                "exit_code": int(outcome.exit_code),
                "run_id": outcome.run_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
    return int(outcome.exit_code)


def _safe_cli_error(code: str) -> None:
    print(
        json.dumps(
            {"event": "ingestion_process_exit", "status": "failed", "error_code": code},
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


def _install_signal_handlers() -> dict[int, object]:
    previous = {}

    def terminate(_signum, _frame):
        raise TerminationError()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, terminate)
    return previous


def _restore_signal_handlers(previous: dict[int, object]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
