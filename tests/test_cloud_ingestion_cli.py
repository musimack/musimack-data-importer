from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from src.cloud_ingestion.application import IngestionApplication
from src.cloud_ingestion.cli import build_parser, main
from src.cloud_ingestion.domain import RunRequest
from src.cloud_ingestion.exit_codes import ExitCode
from src.cloud_ingestion.fixture_adapters import (
    FixtureConfigurationProvider,
    FixtureCredentialProvider,
    FixtureWeeklyProvider,
    MemoryIngestionSink,
)
from src.cloud_ingestion.structured_logging import SafeJsonLogger

FIXTURES = Path(__file__).parent / "fixtures" / "cloud_ingestion"


def _args(provider: str, output: Path | None = None) -> list[str]:
    suffix = "1" if provider == "ga4" else "2"
    values = [
        "--configuration-fixture",
        str(FIXTURES / f"{provider}_configuration.json"),
        "--provider-fixture",
        str(FIXTURES / f"{provider}_provider.json"),
        "--project-id",
        f"20000000-0000-0000-0000-00000000000{suffix}",
        "--provider",
        provider,
        "--week-start",
        "2026-07-27",
        "--idempotency-key",
        f"30000000-0000-0000-0000-00000000000{suffix}",
        "--environment",
        "development",
    ]
    if output is not None:
        values.extend(["--result-out", str(output)])
    return values


def test_cli_fixture_mode_is_one_shot_and_writes_only_explicit_result(tmp_path, capsys):
    output = tmp_path / "normalized.json"
    exit_code = main(_args("ga4", output))

    assert exit_code == ExitCode.SUCCESS
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provider"] == "ga4"
    assert payload["evidence"]["requests_consumed"] == 5
    lines = capsys.readouterr().out.splitlines()
    records = [json.loads(line) for line in lines]
    assert records[-1]["event"] == "ingestion_process_exit"
    assert records[-1]["exit_code"] == 0
    assert "sessions" not in json.dumps(records)


def test_cli_without_result_path_is_stateless(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(_args("gsc")) == ExitCode.SUCCESS
    assert list(tmp_path.iterdir()) == []


def test_ga4_and_gsc_fixture_paths_produce_same_contract_shape(tmp_path):
    outputs = []
    for provider in ("ga4", "gsc"):
        path = tmp_path / f"{provider}.json"
        assert main(_args(provider, path)) == ExitCode.SUCCESS
        outputs.append(json.loads(path.read_text(encoding="utf-8")))
    required = set(outputs[0])
    assert set(outputs[1]) == required
    assert required == {
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


def test_direct_local_and_one_shot_entrypoint_have_identical_semantic_hash(tmp_path):
    cli_output = tmp_path / "cli.json"
    assert main(_args("ga4", cli_output)) == ExitCode.SUCCESS
    cli_payload = json.loads(cli_output.read_text(encoding="utf-8"))

    sink = MemoryIngestionSink()
    app = IngestionApplication(
        FixtureConfigurationProvider(FIXTURES / "ga4_configuration.json"),
        FixtureCredentialProvider(),
        {"ga4": FixtureWeeklyProvider(FIXTURES / "ga4_provider.json", "ga4")},
        sink,
        logger=SafeJsonLogger(writer=lambda _: None),
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    outcome = app.run(
        RunRequest(
            project_id="20000000-0000-0000-0000-000000000001",
            provider="ga4",
            week_start=date(2026, 7, 27),
            idempotency_key="30000000-0000-0000-0000-000000000001",
            environment="development",
        )
    )
    assert outcome.exit_code == ExitCode.SUCCESS
    assert cli_payload["normalized_payload_hash"] == outcome.payload["normalized_payload_hash"]


def test_cli_rejects_non_monday_with_deterministic_exit(capsys):
    args = _args("ga4")
    args[args.index("2026-07-27")] = "2026-07-28"
    assert main(args) == ExitCode.INVALID_INPUT
    assert json.loads(capsys.readouterr().err)["error_code"] == "invalid_input"


def test_container_is_non_root_and_fixture_entrypoint_only():
    root = Path(__file__).parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")
    assert "USER musimack" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "src.cloud_ingestion.cli"]' in dockerfile
    assert "COPY src ./src" not in dockerfile
    assert "postgres_writer" not in dockerfile
    cli_source = (root / "src" / "cloud_ingestion" / "cli.py").read_text(encoding="utf-8")
    assert "FixtureWeeklyProvider" in cli_source
    assert "GoogleGa4WeeklyProvider" not in cli_source
    assert "GoogleGscWeeklyProvider" not in cli_source
    assert "secrets" in dockerignore
    assert ".env*" in dockerignore
    assert "local-profile-configs" in dockerignore


def test_cli_does_not_allow_operator_to_widen_retry_policy():
    help_text = build_parser().format_help()
    assert "authorized-retries" not in help_text
