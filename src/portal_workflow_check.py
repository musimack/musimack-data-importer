from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class WorkflowCheck:
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class WorkflowSummary:
    project_id: str
    checks: list[WorkflowCheck]

    @property
    def ready_for_import(self) -> bool:
        required = {"project", "ga4_mapping"}
        return all(check.ok for check in self.checks if check.label in required)

    def lines(self) -> list[str]:
        lines = [f"Portal GA4 workflow check for project {self.project_id}"]
        for check in self.checks:
            state = "ok" if check.ok else "needs attention"
            lines.append(f"- {check.label}: {state} - {check.detail}")
        return lines


def build_workflow_summary(
    database_url: str,
    project_id: str,
    assigned_email: str | None = None,
    unrelated_email: str | None = None,
) -> WorkflowSummary:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        project = _fetch_one(
            conn,
            """
            select p.id, p.name, c.name as client_name
            from projects p
            left join clients c on c.id = p.client_id
            where p.id = %s
            """,
            (project_id,),
        )
        mapping = _fetch_one(
            conn,
            """
            select external_resource_id, external_resource_name, visibility, sync_enabled
            from project_integration_accounts
            where project_id = %s
              and resource_type = 'ga4_property'
            order by updated_at desc
            limit 1
            """,
            (project_id,),
        )
        snapshot_counts = _fetch_one(
            conn,
            """
            select
              count(*)::int as total,
              count(*) filter (where visibility = 'internal' and status = 'draft')::int as internal_draft,
              count(*) filter (where visibility = 'client' and status = 'published')::int as client_published
            from project_integration_snapshots
            where project_id = %s
              and provider = 'google_analytics'
              and snapshot_type = 'ga4_summary'
            """,
            (project_id,),
        )
        report_counts = _fetch_one(
            conn,
            """
            select
              count(*)::int as total,
              count(*) filter (where status = 'published')::int as published
            from project_reports
            where project_id = %s
            """,
            (project_id,),
        )
        link_counts = _fetch_one(
            conn,
            """
            select count(*)::int as total
            from project_report_snapshots prs
            join project_reports r on r.id = prs.project_report_id
            join project_integration_snapshots s on s.id = prs.project_integration_snapshot_id
            where r.project_id = %s
              and s.project_id = %s
              and s.provider = 'google_analytics'
              and s.snapshot_type = 'ga4_summary'
            """,
            (project_id, project_id),
        )
        active_link_counts = (
            _active_link_counts(conn, project_id) if _has_active_link_column(conn) else None
        )
        assigned = _assignment_state(conn, project_id, assigned_email) if assigned_email else None
        unrelated = _assignment_state(conn, project_id, unrelated_email) if unrelated_email else None

    checks = [
        WorkflowCheck(
            "project",
            project is not None,
            _project_detail(project),
        ),
        WorkflowCheck(
            "ga4_mapping",
            mapping is not None,
            _mapping_detail(mapping),
        ),
        WorkflowCheck(
            "snapshots",
            bool(snapshot_counts and snapshot_counts["total"] > 0),
            _snapshot_detail(snapshot_counts),
        ),
        WorkflowCheck(
            "reports",
            bool(report_counts and report_counts["total"] > 0),
            _report_detail(report_counts),
        ),
        WorkflowCheck(
            "report_links",
            bool(link_counts and link_counts["total"] > 0),
            _link_detail(link_counts),
        ),
        WorkflowCheck(
            "active_snapshot_links",
            _active_links_ok(active_link_counts, link_counts),
            _active_link_detail(active_link_counts, link_counts),
        ),
    ]
    if assigned_email:
        checks.append(
            WorkflowCheck(
                "assigned_client",
                bool(assigned and assigned["assigned"]),
                _assignment_detail(assigned_email, assigned),
            )
        )
    if unrelated_email:
        checks.append(
            WorkflowCheck(
                "unrelated_client",
                bool(unrelated and not unrelated["assigned"]),
                _assignment_detail(unrelated_email, unrelated),
            )
        )
    return WorkflowSummary(project_id=project_id, checks=checks)


def _fetch_one(conn, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    return conn.execute(query, params).fetchone()


def _assignment_state(conn, project_id: str, email: str) -> dict[str, Any] | None:
    return _fetch_one(
        conn,
        """
        select
          u.email,
          u.role::text as role,
          exists (
            select 1
            from user_project_assignments upa
            where upa.user_id = u.id
              and upa.project_id = %s
          ) as assigned
        from users u
        where lower(u.email) = lower(%s)
        """,
        (project_id, email),
    )


def _has_active_link_column(conn) -> bool:
    row = _fetch_one(
        conn,
        """
        select exists (
          select 1
          from information_schema.columns
          where table_name = 'project_report_snapshots'
            and column_name = 'is_active'
        ) as present
        """,
        (),
    )
    return bool(row and row["present"])


def _active_link_counts(conn, project_id: str) -> dict[str, Any] | None:
    return _fetch_one(
        conn,
        """
        select
          count(*)::int as total,
          count(*) filter (where prs.is_active = true)::int as active,
          count(*) filter (where prs.is_active = false)::int as inactive,
          max(s.id::text) filter (where prs.is_active = true) as active_snapshot_id,
          count(*) filter (
            where s.visibility = 'internal'
              and s.status = 'draft'
          )::int as internal_draft
        from project_report_snapshots prs
        join project_reports r on r.id = prs.project_report_id
        join project_integration_snapshots s on s.id = prs.project_integration_snapshot_id
        where r.project_id = %s
          and s.project_id = %s
          and s.provider = 'google_analytics'
          and s.snapshot_type = 'ga4_summary'
        """,
        (project_id, project_id),
    )


def _project_detail(row: dict[str, Any] | None) -> str:
    if not row:
        return "project not found"
    client = row.get("client_name") or "no client label"
    return f"{row['name']} ({client})"


def _mapping_detail(row: dict[str, Any] | None) -> str:
    if not row:
        return "no local ga4_property mapping found"
    resource = row["external_resource_id"]
    visibility = row["visibility"]
    enabled = "enabled" if row["sync_enabled"] else "disabled"
    return f"{resource}, {visibility}, sync {enabled}"


def _snapshot_detail(row: dict[str, Any] | None) -> str:
    if not row:
        return "0 GA4 summary snapshots"
    return (
        f"{row['total']} GA4 summary snapshot(s), "
        f"{row['internal_draft']} internal/draft, "
        f"{row['client_published']} client/published"
    )


def _report_detail(row: dict[str, Any] | None) -> str:
    if not row:
        return "0 project reports"
    return f"{row['total']} report(s), {row['published']} published"


def _link_detail(row: dict[str, Any] | None) -> str:
    count = int(row["total"]) if row else 0
    return f"{count} GA4 report snapshot link(s)"


def _active_links_ok(
    row: dict[str, Any] | None, fallback_link_counts: dict[str, Any] | None
) -> bool:
    if row is None:
        return bool(fallback_link_counts and fallback_link_counts["total"] > 0)
    return int(row["active"] or 0) > 0


def _active_link_detail(
    row: dict[str, Any] | None, fallback_link_counts: dict[str, Any] | None
) -> str:
    if row is None:
        count = int(fallback_link_counts["total"]) if fallback_link_counts else 0
        return (
            "active-link columns not detected; "
            f"legacy link count is {count}; active/historical state unavailable"
        )
    active = int(row["active"] or 0)
    inactive = int(row["inactive"] or 0)
    internal_draft = int(row["internal_draft"] or 0)
    active_snapshot = row.get("active_snapshot_id") or "none"
    if active == 0:
        return (
            f"active linked snapshot missing, {inactive} inactive/historical link(s), "
            f"{internal_draft} internal/draft linked snapshot(s) awaiting review"
        )
    return (
        f"active linked snapshot {active_snapshot}, "
        f"{inactive} inactive/historical link(s), "
        f"{internal_draft} internal/draft linked snapshot(s) awaiting review"
    )


def _assignment_detail(email: str, row: dict[str, Any] | None) -> str:
    if not row:
        return f"{email} not found"
    assigned = "assigned" if row["assigned"] else "not assigned"
    return f"{email}, role {row['role']}, {assigned}"
