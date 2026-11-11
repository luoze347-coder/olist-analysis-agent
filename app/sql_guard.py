"""Validate model-written SQL before it reaches DuckDB."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from app.metrics import ALLOWED_TABLES


class UnsafeQuery(ValueError):
    """Raised when SQL is outside the supported read-only analytical subset."""


FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Copy, exp.Attach, exp.Pragma, exp.Set, exp.Merge,
)


def validate_sql(sql: str, max_rows: int = 200) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeQuery("SQL is empty")
    if len(sql) > 8000:
        raise UnsafeQuery("SQL exceeds the 8,000 character limit")
    try:
        parsed = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQuery(f"SQL syntax error: {exc}") from exc
    if len(parsed) != 1 or parsed[0] is None:
        raise UnsafeQuery("Exactly one query is allowed")
    tree = parsed[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise UnsafeQuery("Only SELECT queries are allowed")
    if any(isinstance(node, FORBIDDEN_NODES) for node in tree.walk()):
        raise UnsafeQuery("Data modification or database commands are forbidden")

    # CTE names are query-local, while physical table names must be allowlisted.
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = {table.name.lower() for table in tree.find_all(exp.Table)}
    physical_tables = tables - cte_names
    if not physical_tables or not physical_tables.issubset(ALLOWED_TABLES):
        raise UnsafeQuery("Query must use only the approved analytical tables")
    if any(isinstance(node, (exp.TableFromRows, exp.Anonymous)) and
           getattr(node, "name", "").lower().startswith(("read_", "http", "sqlite_", "postgres_", "glob", "query"))
           for node in tree.walk()):
        raise UnsafeQuery("External data access is forbidden")
    if any(isinstance(node, exp.Into) for node in tree.walk()):
        raise UnsafeQuery("SELECT INTO is forbidden")
    existing_limit = tree.args.get("limit")
    if existing_limit is not None:
        value = existing_limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 1:
            raise UnsafeQuery("LIMIT must be a positive integer literal")
        if int(value.this) <= max_rows:
            return tree.sql(dialect="duckdb")
    return tree.limit(max_rows).sql(dialect="duckdb")
