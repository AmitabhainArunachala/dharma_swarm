#!/usr/bin/env python3
"""Run the dharma_swarm MCP server over stdio."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.stdio import stdio_server

from dharma_swarm.mcp_server import create_mcp_server


async def main() -> None:
    state_dir = str(Path.home() / ".dharma")
    server = create_mcp_server(state_dir=state_dir)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
