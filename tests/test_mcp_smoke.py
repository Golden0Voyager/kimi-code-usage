"""End-to-end smoke over the real MCP protocol.

Every other MCP test mocks the transport, so a breaking change in `fastmcp` or
in the `mcp` SDK — the two dependencies whose majors move independently — would
keep the suite green while the published `kimi-mcp` entry point stopped working.
This test spawns the actual server as a subprocess and speaks MCP to it.

The child gets a throwaway ``HOME`` and no provider credentials, so it never
reads the developer's real config or calls a provider: the tools must answer
with their "not configured" text, which still proves the request/response path.
"""

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.asyncio


async def test_stdio_server_lists_and_calls_tools(tmp_path):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "PYTHONUNBUFFERED": "1",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "kimi_code_usage.mcp"],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.server_info.name

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"get_usage", "get_kimi_usage"} <= names

            result = await session.call_tool("get_kimi_usage", {})
            assert result.content, "the tool returned no content"
            text = result.content[0].text
            assert isinstance(text, str)
            assert text.strip()
