from __future__ import annotations

import psycopg

from src.portal_db_ready import _categorize_operational_error


def test_operational_error_category_authentication_failed():
    exc = psycopg.OperationalError("password authentication failed for user example")

    assert _categorize_operational_error(exc) == "authentication failed"


def test_operational_error_category_port_closed():
    exc = psycopg.OperationalError("connection refused")

    assert _categorize_operational_error(exc) == "port closed or database service not accepting connections"


def test_operational_error_category_database_missing():
    exc = psycopg.OperationalError('database "example" does not exist')

    assert _categorize_operational_error(exc) == "database missing"


def test_operational_error_category_unknown_does_not_echo_message():
    exc = psycopg.OperationalError("sensitive detail that should not be printed")

    assert _categorize_operational_error(exc) == "unknown OperationalError"
