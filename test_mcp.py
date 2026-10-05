# test_mcp.py
import asyncio
from mcp import Client

async def main():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        tools = await client.list_tools()
        print(tools)
        result = await client.call_tool(
            "query_database", {"sql": "SELECT count(*) FROM books"}
        )
        print(result)

asyncio.run(main())