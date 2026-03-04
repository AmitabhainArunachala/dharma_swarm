"""Swarm Manager — integrates agent pool, task board, message bus, and orchestrator.

Layer 4: The swarm lifecycle manager. Spawns agents, assigns tasks,
monitors health, and provides the unified API for the CLI and MCP server.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    MemoryLayer,
    ProviderType,
    SwarmState,
    Task,
    TaskPriority,
    TaskStatus,
    TopologyType,
)


class SwarmManager:
    """Top-level swarm coordinator."""

    def __init__(self, state_dir: Path | str = ".dharma"):
        self.state_dir = Path(state_dir)
        self._start_time = time.monotonic()
        self._running = False

        # Lazily initialized components
        self._task_board: Any = None
        self._agent_pool: Any = None
        self._message_bus: Any = None
        self._memory: Any = None
        self._orchestrator: Any = None
        self._gatekeeper: Any = None

    async def init(self) -> None:
        """Initialize all subsystems."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        from dharma_swarm.agent_runner import AgentPool
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.message_bus import MessageBus
        from dharma_swarm.orchestrator import Orchestrator
        from dharma_swarm.task_board import TaskBoard
        from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER

        db_dir = self.state_dir / "db"
        db_dir.mkdir(exist_ok=True)

        self._task_board = TaskBoard(db_dir / "tasks.db")
        await self._task_board.init_db()

        self._message_bus = MessageBus(db_dir / "messages.db")
        await self._message_bus.init_db()

        self._memory = StrangeLoopMemory(db_dir / "memory.db")
        await self._memory.init_db()

        self._agent_pool = AgentPool()
        self._gatekeeper = DEFAULT_GATEKEEPER

        self._orchestrator = Orchestrator(
            task_board=self._task_board,
            agent_pool=self._agent_pool,
            message_bus=self._message_bus,
        )

        self._running = True
        await self._memory.remember(
            "Swarm initialized", layer=MemoryLayer.SESSION, source="swarm"
        )

    # --- Agent Operations ---

    async def spawn_agent(
        self,
        name: str,
        role: AgentRole = AgentRole.GENERAL,
        model: str = "claude-sonnet-4-20250514",
        provider_type: ProviderType = ProviderType.ANTHROPIC,
    ) -> AgentState:
        """Spawn a new agent into the pool."""
        config = AgentConfig(
            name=name,
            role=role,
            model=model,
            provider=provider_type,
        )
        runner = await self._agent_pool.spawn(config)
        await self._memory.remember(
            f"Agent spawned: {name} ({role.value})",
            layer=MemoryLayer.SESSION,
            source="swarm",
        )
        return runner.state

    async def list_agents(self) -> list[AgentState]:
        """List all agents in the pool."""
        return await self._agent_pool.list_agents()

    async def stop_agent(self, agent_id: str) -> None:
        """Stop a specific agent."""
        runner = await self._agent_pool.get(agent_id)
        if runner:
            await runner.stop()

    # --- Task Operations ---

    async def create_task(
        self,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> Task:
        """Create a new task on the board."""
        gate_result = self._gatekeeper.check(action=title, content=description)
        if gate_result.decision.value == "block":
            raise ValueError(f"Telos gate blocked: {gate_result.reason}")
        return await self._task_board.create(
            title=title, description=description, priority=priority
        )

    async def list_tasks(
        self, status: TaskStatus | None = None
    ) -> list[Task]:
        """List tasks with optional status filter."""
        return await self._task_board.list_tasks(status=status)

    async def get_task(self, task_id: str) -> Task | None:
        """Get a specific task."""
        return await self._task_board.get(task_id)

    # --- Orchestration ---

    async def dispatch_next(self) -> int:
        """Run one orchestration tick. Returns number of tasks dispatched."""
        dispatches = await self._orchestrator.route_next()
        return len(dispatches)

    async def run(self, interval: float = 2.0) -> None:
        """Run the orchestration loop."""
        while self._running:
            try:
                await self._orchestrator.tick()
            except Exception:
                pass
            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Stop the swarm."""
        self._running = False
        if self._orchestrator:
            self._orchestrator.stop()

    # --- Status ---

    async def status(self) -> SwarmState:
        """Get current swarm state snapshot."""
        agents = await self._agent_pool.list_agents() if self._agent_pool else []
        task_stats = await self._task_board.stats() if self._task_board else {}
        return SwarmState(
            agents=agents,
            tasks_pending=task_stats.get("pending", 0),
            tasks_running=task_stats.get("running", 0),
            tasks_completed=task_stats.get("completed", 0),
            tasks_failed=task_stats.get("failed", 0),
            uptime_seconds=time.monotonic() - self._start_time,
        )

    # --- Memory ---

    async def remember(self, content: str) -> None:
        """Store a memory in the swarm's strange loop."""
        await self._memory.remember(
            content, layer=MemoryLayer.SESSION, source="user"
        )

    async def recall(self, limit: int = 10) -> list:
        """Recall recent memories."""
        return await self._memory.recall(limit=limit)

    async def shutdown(self) -> None:
        """Graceful shutdown of entire swarm."""
        self._running = False
        if self._orchestrator:
            self._orchestrator.stop()
        if self._agent_pool:
            await self._agent_pool.shutdown_all()
        await self._memory.remember(
            "Swarm shutdown", layer=MemoryLayer.SESSION, source="swarm"
        )
