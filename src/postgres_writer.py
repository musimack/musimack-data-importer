from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .validate import validate_snapshot_payload

DB_PROVIDER = "google_analytics"
SNAPSHOT_TYPE = "ga4_summary"


@dataclass(frozen=True)
class ImportOutcome:
    snapshot_id: str
    integration_account_id: str
    sync_run_id: str | None


def import_snapshot(
    database_url: str,
    project_id: str,
    payload: dict[str, Any],
    create_sync_run: bool = True,
) -> ImportOutcome:
    validate_snapshot_payload(payload)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            account_id = _ensure_integration_account(conn, project_id, payload)
            sync_run_id = _insert_sync_run(conn, project_id, account_id, payload) if create_sync_run else None
            snapshot_id = _insert_snapshot(conn, project_id, account_id, sync_run_id, payload)
            return ImportOutcome(
                snapshot_id=str(snapshot_id),
                integration_account_id=str(account_id),
                sync_run_id=str(sync_run_id) if sync_run_id else None,
            )


def _ensure_integration_account(conn, project_id: str, payload: dict[str, Any]):
    property_resource = payload["property_resource"]
    account_name = f"Musimack GA4 {property_resource}"
    metadata = {
        "source": "ga4_local_importer",
        "property_resource": property_resource,
        "local_only": True,
    }
    row = conn.execute(
        """
        insert into integration_accounts
            (provider, account_name, external_account_id, connection_status, metadata)
        values (%s, %s, %s, 'planned', %s)
        on conflict (provider, external_account_id)
        do update set
            account_name = excluded.account_name,
            metadata = integration_accounts.metadata || excluded.metadata,
            updated_at = now()
        returning id
        """,
        (DB_PROVIDER, account_name, property_resource, Jsonb(metadata)),
    ).fetchone()
    account_id = row["id"]
    conn.execute(
        """
        insert into project_integration_accounts
            (project_id, integration_account_id, resource_type, external_resource_id,
             external_resource_name, sync_enabled, visibility, metadata)
        values (%s, %s, 'ga4_property', %s, %s, false, 'internal', %s)
        on conflict (project_id, integration_account_id, resource_type, external_resource_id)
        do update set
            visibility = 'internal',
            sync_enabled = false,
            metadata = project_integration_accounts.metadata || excluded.metadata,
            updated_at = now()
        """,
        (project_id, account_id, property_resource, property_resource, Jsonb(metadata)),
    )
    return account_id


def _insert_sync_run(conn, project_id: str, account_id, payload: dict[str, Any]):
    summary_counts = payload.get("summary_counts", {})
    row = conn.execute(
        """
        insert into integration_sync_runs
            (integration_account_id, project_id, provider, sync_type, status,
             started_at, finished_at, source_started_at, source_finished_at,
             records_seen, records_imported, metadata)
        values (%s, %s, %s, 'ga4_local_import', 'succeeded',
             now(), now(), now(), now(), %s, 1, %s)
        returning id
        """,
        (
            account_id,
            project_id,
            DB_PROVIDER,
            int(summary_counts.get("metric_count", 0)) + int(summary_counts.get("dimension_row_count", 0)),
            Jsonb(
                {
                    "source": "ga4_local_importer",
                    "schema_version": payload["schema_version"],
                    "report_type": payload["report_type"],
                    "local_only": True,
                }
            ),
        ),
    ).fetchone()
    return row["id"]


def _insert_snapshot(conn, project_id: str, account_id, sync_run_id, payload: dict[str, Any]):
    dimensions = {
        "date_range": payload.get("date_range"),
        "comparison_date_range": payload.get("comparison_date_range"),
        "dimension_rows": payload.get("dimension_rows", []),
        "time_series": payload.get("time_series", []),
    }
    source_metadata = {
        "schema_version": payload["schema_version"],
        "provider_key": payload["provider_key"],
        "source": payload.get("source"),
        "report_type": payload["report_type"],
        "property_resource": payload["property_resource"],
        "summary_counts": payload.get("summary_counts", {}),
        "warnings": payload.get("warnings", []),
        "snapshot_writer": "ga4_local_importer",
        "live_sync": False,
        "local_only": True,
    }
    row = conn.execute(
        """
        insert into project_integration_snapshots
            (project_id, integration_account_id, sync_run_id, provider, snapshot_type,
             period_start, period_end, visibility, status, summary, metrics,
             dimensions, source_metadata)
        values (%s, %s, %s, %s, %s, %s, %s, 'internal', 'draft',
             %s, %s, %s, %s)
        returning id
        """,
        (
            project_id,
            account_id,
            sync_run_id,
            DB_PROVIDER,
            SNAPSHOT_TYPE,
            payload["date_range"]["start"],
            payload["date_range"]["end"],
            payload["summary"],
            Jsonb(payload["metrics"]),
            Jsonb(dimensions),
            Jsonb(source_metadata),
        ),
    ).fetchone()
    return row["id"]


def load_snapshot_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    validate_snapshot_payload(payload)
    return payload
