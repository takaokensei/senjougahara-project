"""
brain/mcp/server.py

Optional MCP server re-exposing the brain tool layer to external MCP clients.
NEVER used for the avatar<->brain hot path (that uses WebSocket/REST bridge).
Useful for debugging tools via Claude Desktop during development.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def create_mcp_server():
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        logger.warning("mcp package not installed; MCP server disabled.")
        return None

    from brain.tools import registry
    from brain.tools.registry import import_all_tools
    import_all_tools()

    server = Server("senjougahara-tools")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(name=t.name, description=t.description, inputSchema=t.parameters)
            for t in registry.get_all_tools()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            result = await registry.dispatch(name, arguments or {})
            return [TextContent(type="text", text=str(result))]
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]

    return server


if __name__ == "__main__":
    import asyncio, mcp.server.stdio
    server = create_mcp_server()
    if server:
        asyncio.run(mcp.server.stdio.stdio_server(server))