from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg
from psycopg.rows import dict_row

from src.local_config import load_local_operator_config

PORTAL_ROOT = ROOT.parent / "client-dashboard"
AUTHORIZED_PROFILE = "aluma-seo-geo"
PROVIDER_PROFILE_ARGUMENT = "aluma"
AUTHORIZED_TIMEZONE = "America/Los_Angeles"
OPERATOR_IDENTITY = "local-importer:r3-h4"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process one durable portal Custom exact-range request through the governed local importer."
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--database-url", default=os.environ.get("MUSIMACK_PORTAL_DATABASE_URL") or os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        print("Custom request processing failed safely: portal database configuration is missing.", file=sys.stderr)
        return 1

    try:
        load_local_operator_config()
        request = _load_request(args.database_url, args.request_id)
        _validate_request(request)
        _portal_command(args.database_url, "claim", args.request_id)
        source_dir = ROOT / "exports" / "local-real" / "dashboard-lab" / AUTHORIZED_PROFILE
        request_dir = ROOT / "exports" / "local-real" / "custom-exact-range-requests" / args.request_id
        handoff_dir = request_dir / "handoff"
        range_arg = f"custom_request_{args.request_id.replace('-', '')[:12]},{request['requested_start']},{request['requested_end']}"
        common = [
            "--profile", PROVIDER_PROFILE_ARGUMENT,
            "--report-start-date", str(request["period_start"]),
            "--report-end-date", str(request["period_end"]),
            "--custom-range", range_arg,
        ]
        ga4_summary = _run_provider(
            [sys.executable, str(ROOT / "scripts" / "pull_ga4_exact_range_summary.py"), *common, "--timezone", AUTHORIZED_TIMEZONE, "--real-output"],
            "ga4_summary_provider_failure",
        )
        ga4_ranked = _run_provider(
            [sys.executable, str(ROOT / "scripts" / "pull_ga4_ranked_exact_ranges.py"), *common, "--timezone", AUTHORIZED_TIMEZONE, "--real-output"],
            "ga4_ranked_provider_failure",
        )
        gsc = _run_provider(
            [sys.executable, str(ROOT / "scripts" / "pull_gsc_exact_ranges.py"), *common, "--real-output"],
            "gsc_provider_failure",
        )
        _run_checked(
            [
                sys.executable,
                str(ROOT / "scripts" / "write_client_report_publisher_handoff.py"),
                "--profile", AUTHORIZED_PROFILE,
                "--client-name", str(request["client_name"]),
                "--source-dir", str(source_dir),
                "--out", str(handoff_dir),
                "--custom-range", range_arg,
            ],
            "handoff_generation_failure",
        )
        _run_checked(
            [sys.executable, str(ROOT / "scripts" / "validate_client_report_publisher_handoff.py"), str(handoff_dir)],
            "handoff_validation_failure",
        )
        _portal_command(
            args.database_url,
            "import",
            args.request_id,
            package=handoff_dir / "client_report_presentation_ranges.v2.json",
        )
    except SafeWorkerError as exc:
        _mark_failed(args.database_url, args.request_id, exc.code, exc.message)
        print(f"Custom request processing failed safely: {exc.message}", file=sys.stderr)
        return 1
    except (OSError, psycopg.Error, ValueError) as exc:
        _mark_failed(args.database_url, args.request_id, "operator_internal_failure", "The local operator could not complete the request.")
        print("Custom request processing failed safely: local operator failure.", file=sys.stderr)
        return 1

    print("Custom exact-range request completed through the governed local importer.")
    print(f"Request: {args.request_id}; profile: {AUTHORIZED_PROFILE}; range: {request['requested_start']} through {request['requested_end']}.")
    print(
        "Provider work: "
        f"GA4 summary calls={ga4_summary['provider_calls']}, GA4 ranked calls={ga4_ranked['provider_calls']}, "
        f"GSC calls={gsc['provider_calls']}; reused={ga4_summary['reused'] + ga4_ranked['reused'] + gsc['reused']}."
    )
    print("Sanitized handoff validation and transactional portal result import passed; no credentials or raw provider payloads were printed.")
    return 0


class SafeWorkerError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _load_request(database_url: str, request_id: str) -> dict[str, Any]:
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as conn:
        row = conn.execute(
            """
            select q.id, q.client_id, q.project_id, q.report_id, q.requested_start, q.requested_end,
                   q.timezone, q.profile_key, q.contract_id, q.contract_version, q.dataset_version,
                   q.source_fingerprint, q.request_state, r.period_start, r.period_end, r.status,
                   r.published_at, c.name as client_name
            from custom_exact_range_requests q
            join project_reports r on r.id = q.report_id and r.project_id = q.project_id
            join projects p on p.id = q.project_id and p.client_id = q.client_id
            join clients c on c.id = q.client_id
            where q.id = %s
            """,
            (request_id,),
        ).fetchone()
    if row is None:
        raise SafeWorkerError("request_not_found", "The authorized Custom request was not found.")
    return dict(row)


def _validate_request(request: dict[str, Any]) -> None:
    if request["request_state"] != "queued":
        raise SafeWorkerError("request_not_queued", "The Custom request is not queued.")
    if request["profile_key"] != AUTHORIZED_PROFILE or request["timezone"] != AUTHORIZED_TIMEZONE:
        raise SafeWorkerError("request_identity_rejected", "The Custom request profile or timezone is not authorized.")
    if (
        request["contract_id"] != "client_report_presentation_ranges"
        or request["contract_version"] != "v2"
        or request["dataset_version"] != "custom_exact_range.v1"
        or request["source_fingerprint"] != "aluma-seo-geo:ga4-gsc:v1"
    ):
        raise SafeWorkerError("request_contract_rejected", "The Custom request contract identity is unsupported.")
    if request["status"] != "draft" or request["published_at"] is not None:
        raise SafeWorkerError("report_state_rejected", "The target report is not an internal draft.")
    if request["requested_start"] < request["period_start"] or request["requested_end"] > request["period_end"]:
        raise SafeWorkerError("request_bounds_rejected", "The Custom request is outside the report period.")


def _run_provider(command: list[str], failure_code: str) -> dict[str, int]:
    completed = _run_checked(command, failure_code)
    calls = _extract_count(completed.stdout, "provider calls")
    if calls is None:
        calls = _extract_count(completed.stdout, "API calls")
    reused = _extract_count(completed.stdout, "reused ranges") or 0
    return {"provider_calls": calls or 0, "reused": reused}


def _extract_count(output: str, label: str) -> int | None:
    normalized_label = label.lower()
    for segment in output.replace("\n", ";").split(";"):
        if normalized_label not in segment.lower() or ":" not in segment:
            continue
        tail = segment.lower().split(normalized_label, 1)[1].lstrip(" :")
        digits = "".join(char for char in tail.split()[0] if char.isdigit()) if tail.split() else ""
        if digits:
            return int(digits)
    return None


def _run_checked(command: list[str], failure_code: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SafeWorkerError(failure_code, "A governed importer step failed without importing partial output.")
    return completed


def _portal_command(
    database_url: str,
    action: str,
    request_id: str,
    *,
    package: Path | None = None,
) -> None:
    command = [
        "cargo", "run", "--quiet", "--bin", "manage_custom_exact_range_request", "--",
        "--action", action,
        "--request-id", request_id,
        "--operator", OPERATOR_IDENTITY,
    ]
    if package is not None:
        command.extend(["--package", str(package)])
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    completed = subprocess.run(command, cwd=PORTAL_ROOT, env=env, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SafeWorkerError(f"portal_{action}_failure", f"The portal could not {action} the sanitized Custom result.")


def _mark_failed(database_url: str, request_id: str, code: str, message: str) -> None:
    command = [
        "cargo", "run", "--quiet", "--bin", "manage_custom_exact_range_request", "--",
        "--action", "fail",
        "--request-id", request_id,
        "--operator", OPERATOR_IDENTITY,
        "--error-code", code[:80],
        "--error-message", message[:300],
    ]
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    subprocess.run(command, cwd=PORTAL_ROOT, env=env, text=True, capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
