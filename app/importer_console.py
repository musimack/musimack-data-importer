from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.console_ops import (
    CommandResult,
    build_console_readiness_report,
    load_clients,
    output_path_for,
    run_export,
    run_import,
    run_validation,
    run_workflow_helper,
)
from src.local_config import load_local_operator_config
from src.oauth_readiness import report_has_failures


st.set_page_config(
    page_title="Musimack GA4 Importer Console",
    page_icon="M",
    layout="wide",
)


def main() -> None:
    local_config_status = load_local_operator_config()
    st.title("Musimack GA4 Importer Console")
    st.caption("Local GA4 export, validation, internal/draft import, and portal workflow checks.")

    if "run_log" not in st.session_state:
        st.session_state.run_log = []
    if "validated_files" not in st.session_state:
        st.session_state.validated_files = set()

    clients = load_clients()
    client = _client_picker(clients)
    start_date, end_date = _date_controls(client)
    default_out_path = output_path_for(client, start_date, end_date)
    out_path = _output_path_control(default_out_path)

    _readiness_panel(local_config_status)
    _client_details(client, out_path)

    left, right = st.columns(2)
    with left:
        _export_panel(client, start_date, end_date, out_path)
        _validation_panel(out_path)
    with right:
        _import_panel(client, out_path)
        _workflow_panel(client)

    _portal_follow_up()
    _run_log()


def _client_picker(clients):
    st.subheader("Client")
    labels = [client.client_label for client in clients]
    selected = st.selectbox("Client roster", labels, index=0)
    return next(client for client in clients if client.client_label == selected)


def _date_controls(client):
    st.subheader("Date Range")
    default_start = date.fromisoformat(client.suggested_ytd_start_date)
    default_end = date.fromisoformat(client.suggested_ytd_end_date)
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=default_start)
    with col2:
        end_date = st.date_input("End date", value=default_end)
    if end_date < start_date:
        st.error("End date must be on or after start date.")
    return start_date, end_date


def _output_path_control(default_out_path: Path) -> Path:
    st.subheader("Output")
    text = st.text_input(
        "Export file",
        value=str(default_out_path),
        help="Use the smoke path for Aluma smoke tests, or the YTD path for batch-prep single-client exports.",
    )
    if not text.strip():
        st.error("Output file is required before export or validation.")
        return default_out_path
    return Path(text.strip())


def _readiness_panel(local_config_status) -> None:
    st.subheader("Environment Readiness")
    for line in local_config_status.safe_summary_lines():
        if line.startswith("PASS"):
            st.success(line)
        elif line.startswith("FAIL"):
            st.error(line)
        elif line.startswith("INFO"):
            st.info(line)
        else:
            st.warning(line)
    checks = build_console_readiness_report()
    for check in checks:
        if check.level == "PASS":
            st.success(check.line())
        elif check.level == "WARN":
            st.warning(check.line())
        else:
            st.error(check.line())
    if report_has_failures(checks):
        st.code(
            '\n'.join(
                [
                    'Copy-Item .env.local.example .env.local',
                    'notepad .env.local',
                    'python -m streamlit run app/importer_console.py',
                ]
            ),
            language="powershell",
        )
        st.info("Fill .env.local with local paths/DB URL, keep OAuth files outside the repo, then restart Streamlit. Values are never displayed.")


def _client_details(client, out_path: Path) -> None:
    st.subheader("Selected Client")
    rows = {
        "Client label": client.client_label,
        "Domain": client.domain or "not set",
        "GA4 property ID": client.ga4_property_id,
        "Portal project ID": client.portal_project_id,
        "Known report ID": client.portal_report_id or "not set",
        "Assigned verification email": client.assigned_client_email or "not set",
        "Export slug": client.suggested_export_slug,
        "Output file": str(out_path),
    }
    st.table([{"Field": key, "Value": value} for key, value in rows.items()])


def _export_panel(client, start_date: date, end_date: date, out_path: Path) -> None:
    st.subheader("Export")
    st.write("Runs one selected-client GA4 export. No batch export is triggered.")
    disabled = end_date < start_date
    if st.button("Run Export", disabled=disabled, type="primary"):
        _append_log(f"Export started for {client.client_label}: {out_path}")
        result = run_export(client, start_date, end_date, out_path)
        _show_result(result)
        _append_log(_result_log_line(result, str(out_path)))


def _validation_panel(out_path: Path) -> None:
    st.subheader("Validation")
    st.write("Validates sanitized `ga4_snapshot.v1` JSON without showing raw payloads.")
    if st.button("Validate Export"):
        _append_log(f"Validation started: {out_path}")
        result = run_validation(out_path)
        _show_result(result)
        if result.ok:
            st.session_state.validated_files.add(str(out_path))
        _append_log(_result_log_line(result, str(out_path)))


def _import_panel(client, out_path: Path) -> None:
    st.subheader("Import")
    st.warning("Imports are internal/draft only. The portal owns link, set active, preview, promote, and visibility.")
    validated = str(out_path) in st.session_state.validated_files
    if not validated:
        st.caption("Validate this export in the console before importing.")
    if st.button("Import Internal/Draft Snapshot", disabled=not validated):
        _append_log(f"Import started for {client.client_label}: {out_path}")
        result = run_import(out_path, client.portal_project_id)
        _show_result(result)
        _append_log(_result_log_line(result, client.portal_project_id))


def _workflow_panel(client) -> None:
    st.subheader("Read-Only Portal Workflow Helper")
    st.write("Checks local portal state for the selected project. It performs no writes.")
    if st.button("Run Workflow Helper"):
        _append_log(f"Workflow helper started for {client.client_label}")
        result = run_workflow_helper(client)
        _show_result(result)
        _append_log(_result_log_line(result, client.portal_project_id))


def _portal_follow_up() -> None:
    st.subheader("Portal Follow-Up Checklist")
    st.caption("Monthly replacement remains manual: imports start internal/draft, and the portal owns link, active-source selection, promotion, and access QA.")
    st.checkbox("Confirm the new import is internal/draft before portal review", value=False)
    st.checkbox("Link the imported snapshot to the intended report in the portal", value=False)
    st.checkbox("Set the new GA4 snapshot as the active report source in the portal", value=False)
    st.checkbox("Confirm older linked snapshots are historical/inactive, not deleted", value=False)
    st.checkbox("Preview the Website Performance Summary as admin/internal user", value=False)
    st.checkbox("Promote/publish only after review", value=False)
    st.checkbox("Verify assigned-client access and unrelated-client denial", value=False)


def _run_log() -> None:
    st.subheader("Run Log")
    if not st.session_state.run_log:
        st.caption("No actions have run yet.")
        return
    for line in reversed(st.session_state.run_log[-30:]):
        st.write(line)


def _show_result(result: CommandResult) -> None:
    if result.ok:
        st.success(f"{result.command_label.title()} succeeded.")
    else:
        st.error(f"{result.command_label.title()} failed with exit code {result.returncode}.")
    if result.stdout.strip():
        st.text_area(f"{result.command_label.title()} stdout", result.stdout, height=180)
    if result.stderr.strip():
        st.text_area(f"{result.command_label.title()} stderr", result.stderr, height=180)


def _append_log(line: str) -> None:
    st.session_state.run_log.append(line)


def _result_log_line(result: CommandResult, detail: str) -> str:
    state = "succeeded" if result.ok else f"failed ({result.returncode})"
    return f"{result.command_label.title()} {state}: {detail}"


if __name__ == "__main__":
    main()
