"""Read-only access to the prepared analytical database."""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from app.sql_guard import validate_sql


DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "olist.duckdb"


def run_query(sql: str, *, database_path: Path = DATABASE_PATH, timeout_s: float = 8.0) -> dict:
    safe_sql = validate_sql(sql)
    if not database_path.exists():
        raise FileNotFoundError("Analysis database missing. Run scripts/prepare_data.py first.")
    connection = duckdb.connect(
        str(database_path),
        read_only=True,
        config={"enable_external_access": "false", "threads": "2", "memory_limit": "512MB"},
    )
    timer = threading.Timer(timeout_s, connection.interrupt)
    try:
        timer.start()
        cursor = connection.execute(safe_sql)
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchall()
        return {
            "sql": safe_sql,
            "columns": columns,
            "rows": [[_json_value(value) for value in row] for row in rows],
            "row_count": len(rows),
        }
    finally:
        timer.cancel()
        connection.close()


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
