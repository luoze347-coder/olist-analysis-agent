import asyncio

from mcp import Client

from app.mcp_server import mcp


def test_mcp_tools_use_guarded_database():
    async def check():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert {"get_schema", "run_sql"} <= {item.name for item in tools.tools}
            schema = await client.call_tool("get_schema", {})
            assert "delivered" in str(schema.structured_content or schema.content)

            safe = await client.call_tool("run_sql", {"sql": "SELECT COUNT(*) AS orders FROM orders"})
            assert not safe.is_error
            assert "row_count" in str(safe.structured_content or safe.content)

            unsafe = await client.call_tool("run_sql", {"sql": "DELETE FROM orders"})
            assert unsafe.is_error

    asyncio.run(check())
