"""Local MCP access to the same guarded data tools used by the web agent."""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.database import run_query
from app.metrics import DATA_DICTIONARY
from app.sql_guard import UnsafeQuery


mcp = MCPServer(
    "olist-analysis",
    instructions="Historical Olist data only. Call get_schema before run_sql. SQL is read-only and row-limited.",
)


@mcp.tool()
def get_schema() -> str:
    """Return approved Olist tables, fields, metric definitions, and limitations."""
    return DATA_DICTIONARY


@mcp.tool()
def run_sql(sql: str) -> dict:
    """Run one guarded SELECT on approved Olist tables; returns columns and rows."""
    try:
        return run_query(sql)
    except (UnsafeQuery, FileNotFoundError) as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
