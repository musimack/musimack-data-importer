from src.portal_workflow_check import (
    WorkflowCheck,
    WorkflowSummary,
    _active_link_detail,
    _active_links_ok,
)


def test_workflow_summary_lines_are_safe_and_operational():
    summary = WorkflowSummary(
        project_id="project-123",
        checks=[
            WorkflowCheck("project", True, "Aluma Website Reporting"),
            WorkflowCheck("ga4_mapping", True, "properties/341923472, internal, sync disabled"),
            WorkflowCheck("snapshots", False, "0 GA4 summary snapshots"),
        ],
    )

    output = "\n".join(summary.lines())

    assert "Portal GA4 workflow check for project project-123" in output
    assert "ga4_mapping: ok" in output
    assert "snapshots: needs attention" in output
    forbidden_terms = [
        "access_token",
        "refresh_token",
        "token",
        "secret",
        "encrypted_payload",
        "credential_ref",
        "raw_payload",
        "provider_metadata",
    ]
    assert all(term not in output.lower() for term in forbidden_terms)


def test_ready_for_import_requires_project_and_ga4_mapping():
    ready = WorkflowSummary(
        project_id="project-123",
        checks=[
            WorkflowCheck("project", True, "found"),
            WorkflowCheck("ga4_mapping", True, "properties/123"),
            WorkflowCheck("snapshots", False, "0 snapshots"),
        ],
    )
    missing_mapping = WorkflowSummary(
        project_id="project-123",
        checks=[
            WorkflowCheck("project", True, "found"),
            WorkflowCheck("ga4_mapping", False, "missing"),
        ],
    )

    assert ready.ready_for_import
    assert not missing_mapping.ready_for_import


def test_active_link_detail_reports_current_and_historical_state():
    detail = _active_link_detail(
        {
            "total": 2,
            "active": 1,
            "inactive": 1,
            "active_snapshot_id": "snapshot-123",
            "internal_draft": 1,
        },
        None,
    )

    assert _active_links_ok({"active": 1}, None)
    assert "active linked snapshot snapshot-123" in detail
    assert "1 inactive/historical link(s)" in detail
    assert "1 internal/draft linked snapshot(s) awaiting review" in detail


def test_active_link_detail_degrades_without_active_columns():
    detail = _active_link_detail(None, {"total": 1})

    assert _active_links_ok(None, {"total": 1})
    assert "active-link columns not detected" in detail
    assert "legacy link count is 1" in detail
