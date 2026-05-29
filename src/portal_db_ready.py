from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row

from .config import ConfigError, env_value
from .local_config import load_local_operator_config


REQUIRED_TABLES = (
    "clients",
    "projects",
    "integration_accounts",
    "project_integration_accounts",
    "integration_sync_runs",
    "project_integration_snapshots",
)


@dataclass(frozen=True)
class DbReadyCheck:
    level: str
    check: str
    message: str

    @property
    def failed(self) -> bool:
        return self.level == "FAIL"

    def line(self) -> str:
        return f"{self.level}: {self.check} - {self.message}"


def build_portal_db_ready_report() -> list[DbReadyCheck]:
    load_local_operator_config()
    checks: list[DbReadyCheck] = []
    try:
        database_url = env_value("MUSIMACK_PORTAL_DATABASE_URL")
    except ConfigError:
        return [
            DbReadyCheck(
                "FAIL",
                "database env",
                "MUSIMACK_PORTAL_DATABASE_URL is missing; value not printed",
            )
        ]

    checks.append(
        DbReadyCheck(
            "PASS",
            "database env",
            "MUSIMACK_PORTAL_DATABASE_URL is present; value not printed",
        )
    )

    try:
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("select 1 as ok").fetchone()
            checks.append(DbReadyCheck("PASS", "database connection", "SELECT 1 succeeded"))
            checks.extend(_table_checks(conn, REQUIRED_TABLES))
    except OperationalError as exc:
        checks.append(
            DbReadyCheck(
                "FAIL",
                "database connection",
                f"connection failed safely: {_categorize_operational_error(exc)}",
            )
        )
    except Exception as exc:
        checks.append(
            DbReadyCheck(
                "FAIL",
                "database check",
                f"read-only check failed safely: {type(exc).__name__}",
            )
        )
    return checks


def db_report_has_failures(checks: Iterable[DbReadyCheck]) -> bool:
    return any(check.failed for check in checks)


def _table_checks(conn, required_tables: Iterable[str]) -> list[DbReadyCheck]:
    rows = conn.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = 'public'
          and table_name = any(%s)
        """,
        (list(required_tables),),
    ).fetchall()
    present = {row["table_name"] for row in rows}
    checks = []
    for table in required_tables:
        if table in present:
            checks.append(DbReadyCheck("PASS", "schema table", f"{table} exists"))
        else:
            checks.append(DbReadyCheck("FAIL", "schema table", f"{table} is missing"))
    return checks


def _categorize_operational_error(exc: OperationalError) -> str:
    text = str(exc).lower()
    if "connection refused" in text or "could not connect" in text:
        return "port closed or database service not accepting connections"
    if "timeout" in text or "timed out" in text:
        return "host unreachable or connection timeout"
    if "password authentication failed" in text or "authentication failed" in text:
        return "authentication failed"
    if "does not exist" in text and "database" in text:
        return "database missing"
    if "no address associated" in text or "could not translate host" in text:
        return "host unreachable or unknown"
    return "unknown OperationalError"
