"""Prove that an independent MCP client can call the local stdio server."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import Client, StdioServerParameters


async def main() -> None:
    server = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"])
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert {"get_schema", "run_sql"} <= names, names
        schema = await client.call_tool("get_schema", {})
        assert "orders" in str(schema.structured_content or schema.content)
        result = await client.call_tool("run_sql", {"sql": "SELECT COUNT(*) AS order_count FROM orders"})
        if result.is_error:
            raise RuntimeError(str(result.content))
        payload = result.structured_content or json.loads(result.content[0].text)
        assert payload["row_count"] == 1
        assert payload["rows"][0][0] > 0
        unsafe = await client.call_tool("run_sql", {"sql": "DELETE FROM orders"})
        assert unsafe.is_error, "MCP server accepted unsafe SQL"
        print("MCP stdio connected; tools:", ", ".join(sorted(names)))
        print("Safe SQL order count:", payload["rows"][0][0])
        print("Unsafe SQL: blocked")


if __name__ == "__main__":
    asyncio.run(main())
