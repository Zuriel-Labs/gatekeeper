"""MCP v1 subprocess used by the optional cross-version SSE integration test."""

import asyncio
import json
import sys
from datetime import timedelta

from mcp import ClientSession
from mcp.client.sse import sse_client


async def main():
    config = json.loads(sys.stdin.read())
    headers = {"X-Gatekeeper-API-Key": config["key"]}
    async with sse_client(config["url"] + "/mcp/sse", headers=headers) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=5)) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert any(tool.name == "drive__files_list" for tool in tools.tools)
            result = await session.call_tool("drive__files_list", {"q": "v1"})
            assert json.loads(result.content[0].text) == {"ok": True}


asyncio.run(main())
