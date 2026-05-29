from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .oauth_readiness import ReadinessCheck, build_oauth_readiness_report


ROOT = Path(__file__).resolve().parents[1]
CLIENT_CONFIG_PATH = ROOT / "examples" / "ga4_clients.local.example.json"
DEFAULT_UNRELATED_EMAIL = "unrelated.client@musimack.local"
ALUMA_SMOKE_START = date(2026, 5, 1)
ALUMA_SMOKE_END = date(2026, 5, 2)

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(access_token[\"'\s:=]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(refresh_token[\"'\s:=]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(id_token[\"'\s:=]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(client_secret[\"'\s:=]+)[^\"'\s,;}]+"),
    re.compile(r"(?i)(private_key[\"'\s:=]+)[^,;}]+"),
    re.compile(r"(?i)(api_key[\"'\s:=]+)[^\"'\s,;}]+"),
]


@dataclass(frozen=True)
class ConsoleClient:
    key: str
    client_label: str
    domain: str
    portal_project_id: str
    ga4_property_id: str
    suggested_export_slug: str
    suggested_ytd_start_date: str
    suggested_ytd_end_date: str
    portal_report_id: str | None = None
    assigned_client_email: str | None = None
    unrelated_client_email: str | None = None


@dataclass(frozen=True)
class CommandResult:
    command_label: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def load_clients(path: Path = CLIENT_CONFIG_PATH) -> list[ConsoleClient]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("client config must be a JSON object")
    clients = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        clients.append(
            ConsoleClient(
                key=str(key),
                client_label=str(value.get("client_label") or key),
                domain=str(value.get("domain") or ""),
                portal_project_id=str(value.get("portal_project_id") or ""),
                ga4_property_id=str(value.get("ga4_property_id") or ""),
                suggested_export_slug=str(value.get("suggested_export_slug") or key),
                suggested_ytd_start_date=str(value.get("suggested_ytd_start_date") or "2026-01-01"),
                suggested_ytd_end_date=str(value.get("suggested_ytd_end_date") or "2026-05-19"),
                portal_report_id=value.get("portal_report_id"),
                assigned_client_email=value.get("assigned_client_email"),
                unrelated_client_email=value.get("unrelated_client_email"),
            )
        )
    return clients


def output_path_for(client: ConsoleClient, start: date, end: date) -> Path:
    if client.key == "aluma" and start == ALUMA_SMOKE_START and end == ALUMA_SMOKE_END:
        return smoke_output_path_for(client, start, end)
    filename = (
        f"{client.suggested_export_slug}_ga4_ytd_2026_"
        f"{start.isoformat()}_to_{end.isoformat()}.json"
    )
    return Path("exports") / "ytd_2026" / filename


def smoke_output_path_for(client: ConsoleClient, start: date, end: date) -> Path:
    filename = f"{client.suggested_export_slug}_ga4_smoke_{start.isoformat()}_to_{end.isoformat()}.json"
    return Path("exports") / "smoke" / filename


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]", redacted)
    forbidden_markers = [
        "raw_provider",
        "google_response",
        "authorization",
        "refresh_token",
        "access_token",
        "client_secret",
        "private_key",
    ]
    for marker in forbidden_markers:
        redacted = re.sub(
            rf"(?i){re.escape(marker)}",
            f"{marker.split('_')[0]}_[redacted]",
            redacted,
        )
    return redacted


def build_console_readiness_report(
    env: Mapping[str, str] | None = None,
    exports_dir: Path = ROOT / "exports",
) -> list[ReadinessCheck]:
    checks = list(build_oauth_readiness_report(env))
    checks.append(_exports_dir_check(exports_dir))
    return checks


def command_to_display(args: list[str]) -> str:
    return " ".join(args)


def run_export(client: ConsoleClient, start: date, end: date, out_path: Path) -> CommandResult:
    env = os.environ.copy()
    env["MUSIMACK_GA4_PROPERTY_ID"] = client.ga4_property_id
    args = [
        sys.executable,
        "scripts/pull_ga4_traffic_overview.py",
        "--start-date",
        start.isoformat(),
        "--end-date",
        end.isoformat(),
        "--out",
        str(out_path),
    ]
    return _run_command("export", args, env=env)


def run_validation(out_path: Path) -> CommandResult:
    return _run_command(
        "validation",
        [sys.executable, "scripts/validate_ga4_snapshot.py", "--file", str(out_path)],
    )


def run_import(out_path: Path, project_id: str) -> CommandResult:
    return _run_command(
        "import",
        [
            sys.executable,
            "scripts/import_ga4_snapshot.py",
            "--file",
            str(out_path),
            "--project-id",
            project_id,
        ],
    )


def run_workflow_helper(client: ConsoleClient) -> CommandResult:
    args = [
        sys.executable,
        "scripts/check_portal_ga4_workflow.py",
        "--project-id",
        client.portal_project_id,
    ]
    if client.assigned_client_email:
        args.extend(["--assigned-email", client.assigned_client_email])
    args.extend(["--unrelated-email", client.unrelated_client_email or DEFAULT_UNRELATED_EMAIL])
    return _run_command("workflow helper", args)


def _run_command(
    command_label: str,
    args: list[str],
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        env=dict(env) if env else None,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    return CommandResult(
        command_label=command_label,
        returncode=completed.returncode,
        stdout=redact_sensitive_text(completed.stdout),
        stderr=redact_sensitive_text(completed.stderr),
    )


def _exports_dir_check(exports_dir: Path) -> ReadinessCheck:
    try:
        exports_dir.mkdir(parents=True, exist_ok=True)
        probe = exports_dir / ".console-write-check.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return ReadinessCheck(
            "FAIL",
            "exports directory",
            "exports directory is not writable; exports cannot be saved",
        )
    return ReadinessCheck(
        "PASS",
        "exports directory",
        "exports directory exists and is writable",
    )
