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
from src.operator_console import (
    command_guidance,
    copy_dry_run,
    copy_guidance,
    copy_local_real_to_dashboard_lab,
    guarded_import_sequence,
    load_dashboard_lab_profiles,
    output_folder_status,
    provider_readiness,
    provider_setup_checklist,
    readiness_matrix,
    validate_profile_output,
)


st.set_page_config(
    page_title="Musimack Data Importer Console",
    page_icon="M",
    layout="wide",
)


def main() -> None:
    local_config_status = load_local_operator_config()
    st.title("Musimack Data Importer Console")
    st.caption("Local-only importer helper for dashboard-lab data sources and legacy GA4 snapshot operations.")

    if "run_log" not in st.session_state:
        st.session_state.run_log = []
    if "validated_files" not in st.session_state:
        st.session_state.validated_files = set()

    dashboard_tab, ga4_tab = st.tabs(["Dashboard-Lab Profiles", "GA4 Snapshot Workflow"])
    with dashboard_tab:
        _dashboard_lab_console(local_config_status)
    with ga4_tab:
        _ga4_snapshot_console(local_config_status)


def _ga4_snapshot_console(local_config_status) -> None:
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


def _dashboard_lab_console(local_config_status) -> None:
    st.subheader("Dashboard-Lab Profile Registry")
    st.warning(
        "Local-only helper. Real data stays in ignored folders. Do not commit exports/local-real/, "
        "public/local-fixtures/, .env.local, API keys, service account files, or raw provider outputs."
    )
    try:
        profiles = load_dashboard_lab_profiles()
    except Exception as exc:
        st.error(f"Profile registry could not be loaded: {exc}")
        return

    selected = st.selectbox(
        "Dashboard-lab profile",
        [profile.slug for profile in profiles],
        format_func=lambda slug: next(profile.display_name for profile in profiles if profile.slug == slug),
    )
    profile = next(item for item in profiles if item.slug == selected)

    st.table(
        [
            {"Field": "Slug", "Value": profile.slug},
            {"Field": "Display name", "Value": profile.display_name},
            {"Field": "Domain", "Value": profile.domain},
            {"Field": "Vertical", "Value": profile.vertical},
            {"Field": "Service model", "Value": profile.service_model},
            {"Field": "Dashboard-lab route", "Value": profile.dashboard_lab_route},
            {"Field": "Importer output folder", "Value": str(profile.importer_output_folder)},
            {"Field": "Dashboard-lab local fixture target", "Value": str(profile.dashboard_lab_local_fixture_folder)},
            {"Field": "Synthetic fallback", "Value": str(profile.dashboard_lab_synthetic_fixture_folder)},
            {"Field": "Supported importer providers", "Value": ", ".join(profile.data_sources)},
            {"Field": "Capabilities", "Value": ", ".join(f"{item.label} ({item.status})" for item in profile.capabilities)},
        ]
    )

    st.subheader("Safe Config Boundary")
    st.write("Committed registry contains slugs, names, domains, verticals, service model, routes, paths, and provider types only.")
    st.write("Ignored local config should hold GA4 property IDs, GSC site URLs if sensitive, Local Falcon report IDs/manifests, API keys, token paths, and service account paths.")
    _readiness_panel(local_config_status)

    st.subheader("Provider Readiness")
    st.table(provider_readiness(profile))

    st.subheader("Readiness Matrix")
    st.caption(
        "Local output, live fetch config, validation, and dashboard-lab copy readiness are separate states. "
        "Missing local output for planning profiles is normal until an operator creates a real local export."
    )
    matrix = readiness_matrix(profile)
    st.dataframe(
        [
            {
                "Capability": row["provider_label"],
                "Status": row["capability_status"],
                "Local output": row["local_output_status"],
                "Live fetch": row["live_fetch_status"],
                "Validation": row["validate_readiness"],
                "Dashboard copy": row["dashboard_copy_readiness"],
                "Expected file": row["expected_output_file"],
                "Schema": row["output_schema"],
                "Size": row["output_size"],
                "Last modified": row["last_modified"],
                "Overall": row["status_label"],
                "Severity": row["status_severity"],
            }
            for row in matrix
        ],
        use_container_width=True,
    )
    future_notes = [row for row in matrix if row["capability_status"] == "planned" or row["notes"]]
    if future_notes:
        st.subheader("Future Provider And Capability Notes")
        for row in future_notes:
            note = row["notes"] or row["status_label"]
            st.write(f"- {row['provider_label']}: {note}")

    st.subheader("Provider Setup Checklist")
    st.caption(
        "Checklist values are safe booleans and labels only. It does not print API keys, OAuth tokens, "
        "credential contents, Local Falcon report IDs, or raw provider payloads."
    )
    checklist = provider_setup_checklist(profile)
    st.dataframe(
        [
            {
                "Provider": row["provider_label"],
                "Output": row["local_output_state"],
                "Config": _config_state_label(row["config_state"]),
                "Next action": row["safe_next_action"],
                "Blocked reason": row["blocked_reason"],
                "Status": row["status"],
                "Severity": row["severity"],
            }
            for row in checklist
        ],
        use_container_width=True,
    )
    for row in checklist:
        if row["suggested_command"]:
            with st.expander(f"{row['provider_label']} safe command shape"):
                st.code(row["suggested_command"], language="powershell")

    st.subheader("Output Folder Status")
    st.table(output_folder_status(profile))

    st.subheader("Validate Local-Real Output")
    if st.button("Validate local-real output"):
        report = validate_profile_output(profile)
        if report.ok:
            st.success(f"Output folder is ready: {report.folder}")
        else:
            st.warning(f"Output folder needs attention: {report.folder}")
        st.write(f"Folder exists: {'yes' if report.folder_exists else 'no'}")
        st.table([item.as_row() for item in report.files])
        if report.warnings:
            st.warning("\n".join(f"- {warning}" for warning in report.warnings))

    st.subheader("Command Guidance")
    for item in command_guidance(profile):
        st.markdown(f"**{item['provider']}**")
        st.code(item["command"], language="powershell")

    st.subheader("Guarded Real Import Sequence")
    sequence = guarded_import_sequence(profile)
    st.caption(sequence["summary"])
    for phase in sequence["phases"]:
        with st.expander(f"{phase['label']}"):
            st.write(f"Network allowed: {'yes' if phase['network_allowed'] else 'no'}")
            st.write(f"Explicit approval required: {'yes' if phase['requires_explicit_approval'] else 'no'}")
            for command in phase.get("commands", []):
                st.code(command, language="powershell")
            for provider_step in phase.get("providers", []):
                st.markdown(f"**{provider_step['label']}**")
                if provider_step["command"]:
                    st.code(provider_step["command"], language="powershell")
                st.write(provider_step["approval_prompt"])
                for guardrail in provider_step["guardrails"]:
                    st.write(f"- {guardrail}")

    st.subheader("Dashboard-Lab Copy Guidance")
    st.write("Copy only into dashboard-lab `public/local-fixtures/{profile}`. Never copy real data into committed `public/fixtures/{profile}`.")
    st.code(copy_guidance(profile), language="powershell")

    st.subheader("Guarded Copy Preview")
    try:
        plan = copy_dry_run(profile)
        st.table([item.as_row() for item in plan])
    except Exception as exc:
        st.error(f"Copy preview failed safety checks: {exc}")
        return

    confirmed = st.checkbox(
        "I understand this copies ignored real local data into dashboard-lab public/local-fixtures only.",
        value=False,
    )
    if st.button("Copy local-real output to dashboard-lab local fixtures", disabled=not confirmed):
        results = copy_local_real_to_dashboard_lab(profile)
        st.table([item.as_row() for item in results])
        failures = [item for item in results if item.status == "failed"]
        copied = [item for item in results if item.status in {"copied", "overwritten"}]
        if failures:
            st.error(f"Copy completed with {len(failures)} failure(s).")
        elif copied:
            st.success(f"Copy completed for {len(copied)} file(s). Missing source files were skipped.")
        else:
            st.warning("No files were copied. Source files may be missing.")


def _client_picker(clients):
    st.subheader("Client")
    labels = [client.client_label for client in clients]
    selected = st.selectbox("Client roster", labels, index=0)
    return next(client for client in clients if client.client_label == selected)


def _config_state_label(config_state: dict[str, bool]) -> str:
    if not config_state:
        return "not required"
    return "; ".join(f"{key}: {'yes' if value else 'no'}" for key, value in config_state.items())


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
