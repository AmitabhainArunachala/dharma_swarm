"""MCP Server — exposes DHARMA SWARM operations as MCP tools.

Requires the `mcp` optional dependency: pip install dharma-swarm[mcp]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from dharma_swarm.models import AgentRole, TaskPriority


def create_mcp_server(state_dir: str = ".dharma"):
    """Create an MCP server with swarm tools.

    Returns the server instance. Call server.run() to start.
    Raises ImportError if mcp package is not installed.
    """
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        raise ImportError(
            "MCP support requires the 'mcp' package. "
            "Install with: pip install dharma-swarm[mcp]"
        )

    server = Server("dharma-swarm")
    _swarm = None

    async def _get_swarm():
        nonlocal _swarm
        if _swarm is None:
            from dharma_swarm.swarm import SwarmManager
            _swarm = SwarmManager(state_dir=state_dir)
            await _swarm.init()
        return _swarm

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="swarm_status",
                description="Get current DHARMA SWARM status",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="spawn_agent",
                description="Spawn a new agent in the swarm",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Agent name"},
                        "role": {
                            "type": "string",
                            "enum": [r.value for r in AgentRole],
                            "default": "general",
                        },
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="create_task",
                description="Create a new task",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string", "default": ""},
                        "priority": {
                            "type": "string",
                            "enum": [p.value for p in TaskPriority],
                            "default": "normal",
                        },
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="list_tasks",
                description="List all tasks",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="store_memory",
                description="Store a memory in the swarm's strange loop",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="recall_memory",
                description="Recall recent memories",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        swarm = await _get_swarm()

        if name == "swarm_status":
            state = await swarm.status()
            return [TextContent(type="text", text=state.model_dump_json(indent=2))]

        elif name == "spawn_agent":
            role = AgentRole(arguments.get("role", "general"))
            agent = await swarm.spawn_agent(
                name=arguments["name"], role=role
            )
            return [TextContent(
                type="text",
                text=json.dumps({"id": agent.id, "name": agent.name, "status": agent.status.value}),
            )]

        elif name == "create_task":
            priority = TaskPriority(arguments.get("priority", "normal"))
            task = await swarm.create_task(
                title=arguments["title"],
                description=arguments.get("description", ""),
                priority=priority,
            )
            return [TextContent(
                type="text",
                text=json.dumps({"id": task.id, "title": task.title, "status": task.status.value}),
            )]

        elif name == "list_tasks":
            tasks = await swarm.list_tasks()
            data = [{"id": t.id, "title": t.title, "status": t.status.value} for t in tasks]
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        elif name == "store_memory":
            await swarm.remember(arguments["content"])
            return [TextContent(type="text", text="Stored.")]

        elif name == "recall_memory":
            entries = await swarm.recall(limit=arguments.get("limit", 10))
            data = [{"layer": e.layer.value, "content": e.content[:200]} for e in entries]
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    return server
