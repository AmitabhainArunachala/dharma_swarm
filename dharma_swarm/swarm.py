"""Swarm Manager — integrates agent pool, task board, message bus, and orchestrator.

Layer 4: The swarm lifecycle manager. Spawns agents, assigns tasks,
monitors health, and provides the unified API for the CLI and MCP server.

Now wired with Garden Daemon config (heartbeat, thread rotation, circuit
breakers, quality gates, human overrides) and v7 induction prompts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dharma_swarm.daemon_config import DaemonConfig, THREAD_PROMPTS
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
from dharma_swarm.providers import create_default_router

logger = logging.getLogger(__name__)


class SwarmManager:
    """Top-level swarm coordinator.

    Integrates: agent pool, task board, message bus, memory, orchestrator,
    telos gates, ecosystem bridge, daemon config, and thread manager.
    """

    def __init__(
        self,
        state_dir: Path | str = ".dharma",
        daemon_config: DaemonConfig | None = None,
    ):
        self.state_dir = Path(state_dir)
        self._start_time = time.monotonic()
        self._running = False
        self._daemon = daemon_config or DaemonConfig()

        # Lazily initialized components
        self._task_board: Any = None
        self._agent_pool: Any = None
        self._message_bus: Any = None
        self._memory: Any = None
        self._orchestrator: Any = None
        self._gatekeeper: Any = None
        self._thread_mgr: Any = None
        self._router = create_default_router()

        # Daemon state
        self._last_contribution: datetime | None = None
        self._daily_contributions: int = 0
        self._daily_reset: datetime | None = None

    async def init(self) -> None:
        """Initialize all subsystems."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        from dharma_swarm.agent_runner import AgentPool
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.message_bus import MessageBus
        from dharma_swarm.orchestrator import Orchestrator
        from dharma_swarm.task_board import TaskBoard
        from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER
        from dharma_swarm.thread_manager import ThreadManager

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
        self._thread_mgr = ThreadManager(self._daemon, self.state_dir)

        self._orchestrator = Orchestrator(
            task_board=self._task_board,
            agent_pool=self._agent_pool,
            message_bus=self._message_bus,
        )

        self._running = True

        # Load ecosystem awareness on every init
        from dharma_swarm.ecosystem_bridge import update_manifest
        self._manifest = update_manifest()

        # Spawn default crew and seed tasks if this is a fresh start
        from dharma_swarm.startup_crew import spawn_default_crew, create_seed_tasks
        crew = await spawn_default_crew(self)
        seeds = await create_seed_tasks(self)
        if crew:
            logger.info("Spawned %d agents from default crew", len(crew))
        if seeds:
            logger.info("Created %d seed tasks", len(seeds))

        await self._memory.remember(
            f"Swarm initialized — {len(crew)} agents, {len(seeds)} seed tasks",
            layer=MemoryLayer.SESSION,
            source="swarm",
        )

    # --- Agent Operations ---

    async def spawn_agent(
        self,
        name: str,
        role: AgentRole = AgentRole.GENERAL,
        model: str = "anthropic/claude-sonnet-4",
        provider_type: ProviderType = ProviderType.OPENROUTER,
        system_prompt: str = "",
        thread: str | None = None,
    ) -> AgentState:
        """Spawn a new agent into the pool.

        If no system_prompt is given, v7 induction rules + role briefing are used.
        If a thread is specified, the thread focus prompt is appended.
        """
        # Build system prompt with thread context if applicable
        extra_prompt = ""
        if thread and thread in THREAD_PROMPTS:
            extra_prompt = f"\n\nCurrent research thread: {thread}\n{THREAD_PROMPTS[thread]}"

        config = AgentConfig(
            name=name,
            role=role,
            model=model,
            provider=provider_type,
            system_prompt=system_prompt + extra_prompt if system_prompt else extra_prompt,
        )
        provider = self._router.get_provider(provider_type)
        runner = await self._agent_pool.spawn(config, provider=provider)
        await self._memory.remember(
            f"Agent spawned: {name} ({role.value})"
            + (f" [thread: {thread}]" if thread else ""),
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

    def _check_human_overrides(self) -> dict[str, Any]:
        """Check .PAUSE, .FOCUS, .INJECT files. Returns override status."""
        result: dict[str, Any] = {"paused": False, "focus": None, "inject": None}

        pause_path = self.state_dir / self._daemon.pause_file
        if pause_path.exists():
            result["paused"] = True
            return result

        if self._thread_mgr:
            result["focus"] = self._thread_mgr.check_focus_override(self.state_dir)
            result["inject"] = self._thread_mgr.check_inject_override(self.state_dir)

        return result

    def _in_quiet_hours(self) -> bool:
        """Check if current hour is in quiet hours."""
        return datetime.now().hour in self._daemon.quiet_hours

    def _contribution_allowed(self) -> bool:
        """Check rate limits: daily max, min interval between contributions."""
        now = datetime.now()

        # Reset daily counter at midnight
        if self._daily_reset is None or now.date() != self._daily_reset.date():
            self._daily_contributions = 0
            self._daily_reset = now

        if self._daily_contributions >= self._daemon.max_daily_contributions:
            return False

        if self._last_contribution:
            elapsed = (now - self._last_contribution).total_seconds()
            if elapsed < self._daemon.min_between_contributions:
                return False

        return True

    async def run(self, interval: float | None = None) -> None:
        """Run the orchestration loop with Garden Daemon parameters.

        In daemon mode (interval=None), uses heartbeat_interval from config.
        In interactive mode, uses the provided interval.
        """
        tick_interval = interval if interval is not None else self._daemon.heartbeat_interval

        while self._running:
            try:
                # Check human overrides
                overrides = self._check_human_overrides()
                if overrides["paused"]:
                    logger.info("Swarm paused by .PAUSE file")
                    await asyncio.sleep(60)  # check again in a minute
                    continue

                # Apply focus override to thread manager
                if overrides["focus"] and self._thread_mgr:
                    self._thread_mgr._current_thread = overrides["focus"]

                # Check quiet hours
                if self._in_quiet_hours():
                    logger.debug("In quiet hours, skipping tick")
                    await asyncio.sleep(min(tick_interval, 300))
                    continue

                # Check circuit breaker
                if self._daemon.circuit_breaker.is_broken:
                    logger.warning("Circuit breaker tripped, paused")
                    await asyncio.sleep(min(tick_interval, 300))
                    continue

                # Check contribution rate limits
                if not self._contribution_allowed():
                    logger.debug("Rate limit: contribution not allowed yet")
                    await asyncio.sleep(min(tick_interval, 300))
                    continue

                # Run orchestration tick
                await self._orchestrator.tick()

                # Record contribution
                self._last_contribution = datetime.now()
                self._daily_contributions += 1
                self._daemon.circuit_breaker.record_success()

                if self._thread_mgr:
                    self._thread_mgr.record_contribution()

            except Exception as exc:
                logger.exception("Tick failed: %s", exc)
                tripped = self._daemon.circuit_breaker.record_failure()
                if tripped:
                    logger.error(
                        "Circuit breaker tripped after %d consecutive failures",
                        self._daemon.circuit_breaker.consecutive_failures,
                    )
                    # Switch thread on downtrend
                    if self._thread_mgr:
                        self._thread_mgr.rotate()

            await asyncio.sleep(tick_interval)

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

    # --- Thread ---

    @property
    def current_thread(self) -> str | None:
        return self._thread_mgr.current_thread if self._thread_mgr else None

    def rotate_thread(self) -> str | None:
        if self._thread_mgr:
            return self._thread_mgr.rotate()
        return None

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
