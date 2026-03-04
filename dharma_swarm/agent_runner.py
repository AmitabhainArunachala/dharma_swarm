"""Async agent lifecycle manager.

Spawns agents, runs their work loop, handles heartbeats and shutdown.
Each AgentRunner manages a single agent; AgentPool manages the fleet.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from dharma_swarm.models import (
    AgentConfig,
    AgentState,
    AgentStatus,
    LLMRequest,
    LLMResponse,
    Task,
)

logger = logging.getLogger(__name__)

_HEARTBEAT_THRESHOLD = timedelta(seconds=60)
_ERROR_PREFIXES = (
    "error",
    "api error:",
    "timeout: exceeded limit",
    "not logged in · please run /login",
    "openrouter error:",
    "no openrouter_api_key set",
)


# ---------------------------------------------------------------------------
# Duck-typed protocols for provider and sandbox (no direct imports)
# ---------------------------------------------------------------------------

@runtime_checkable
class CompletionProvider(Protocol):
    """Anything with an async ``complete`` method returning an LLMResponse."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class CodeSandbox(Protocol):
    """Anything with an async ``execute`` method."""

    async def execute(self, command: str, timeout: float = 30.0) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _state_from_config(config: AgentConfig) -> AgentState:
    """Derive initial runtime state from a static config."""
    return AgentState(
        id=config.id,
        name=config.name,
        role=config.role,
        status=AgentStatus.STARTING,
    )


def _build_system_prompt(config: AgentConfig) -> str:
    """Build the system prompt from config, v7 rules, role briefings, and live context."""
    from dharma_swarm.models import ProviderType

    # For non-CLAUDE_CODE providers, explicit system_prompt is final
    if config.system_prompt and config.provider != ProviderType.CLAUDE_CODE:
        return config.system_prompt

    from dharma_swarm.daemon_config import V7_BASE_RULES, ROLE_BRIEFINGS

    if config.system_prompt:
        # CLAUDE_CODE with explicit prompt: use it as base, append context
        parts = [config.system_prompt]
    else:
        parts = [V7_BASE_RULES]
        role_briefing = ROLE_BRIEFINGS.get(config.role.value)
        if role_briefing:
            parts.append(role_briefing)
        else:
            parts.append(f"You are a {config.role.value} agent in the DHARMA SWARM.")

    # Inject multi-layer context for real Claude Code agents
    if config.provider == ProviderType.CLAUDE_CODE:
        from dharma_swarm.context import build_agent_context
        ctx = build_agent_context(
            role=config.role.value,
            thread=config.thread,
        )
        if ctx:
            parts.append(ctx)

    return "\n\n".join(parts)


def _build_prompt(task: Task, config: AgentConfig) -> LLMRequest:
    """Build an LLMRequest from a task and agent config."""
    system = _build_system_prompt(config)
    user_content = f"## Task: {task.title}\n\n{task.description}"
    return LLMRequest(
        model=config.model,
        messages=[{"role": "user", "content": user_content}],
        system=system,
    )


def _looks_like_provider_failure(content: str) -> bool:
    """Heuristic guard against error strings being marked as completed work."""
    normalized = (content or "").strip().lower()
    if not normalized:
        return True
    return any(normalized.startswith(prefix) for prefix in _ERROR_PREFIXES)


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Manages the full lifecycle of a single agent.

    Args:
        config: Static configuration for the agent.
        provider: Optional LLM provider (duck-typed with ``complete``).
        sandbox: Optional code sandbox (duck-typed with ``execute``).
    """

    def __init__(
        self,
        config: AgentConfig,
        provider: CompletionProvider | None = None,
        sandbox: CodeSandbox | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._sandbox = sandbox
        self._state = _state_from_config(config)
        self._lock = asyncio.Lock()

    # -- properties ---------------------------------------------------------

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def agent_id(self) -> str:
        return self._config.id

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Initialize the agent and mark it IDLE."""
        async with self._lock:
            self._state.status = AgentStatus.IDLE
            self._state.started_at = _utc_now()
            self._state.last_heartbeat = _utc_now()
            logger.info("Agent %s (%s) started", self._config.name, self.agent_id)

    async def run_task(self, task: Task) -> str:
        """Execute a task and return the result string.

        Sets status to BUSY during execution, then back to IDLE.
        If no provider is attached, returns a mock result.

        Args:
            task: The task to execute.

        Returns:
            The LLM completion content, or a mock placeholder.
        """
        async with self._lock:
            self._state.status = AgentStatus.BUSY
            self._state.current_task = task.id

        try:
            request = _build_prompt(task, self._config)

            if self._provider is not None:
                response = await self._provider.complete(request)
                result = response.content
                if _looks_like_provider_failure(result):
                    raise RuntimeError(result or "Provider returned empty response")
            else:
                result = (
                    f"[mock] Agent {self._config.name} completed: {task.title}"
                )

            async with self._lock:
                self._state.turns_used += 1
                self._state.tasks_completed += 1
                self._state.current_task = None
                self._state.status = AgentStatus.IDLE
                self._state.last_heartbeat = _utc_now()

            logger.info(
                "Agent %s finished task %s", self._config.name, task.id
            )
            return result

        except Exception as exc:
            async with self._lock:
                self._state.status = AgentStatus.IDLE
                self._state.current_task = None
                self._state.error = str(exc)
            logger.exception(
                "Agent %s failed task %s", self._config.name, task.id
            )
            raise

    async def heartbeat(self) -> None:
        """Update the last_heartbeat timestamp."""
        async with self._lock:
            self._state.last_heartbeat = _utc_now()

    async def stop(self) -> None:
        """Gracefully shut down the agent."""
        async with self._lock:
            self._state.status = AgentStatus.STOPPING
        logger.info("Agent %s stopping", self._config.name)
        async with self._lock:
            self._state.status = AgentStatus.DEAD
        logger.info("Agent %s stopped", self._config.name)

    async def health_check(self) -> bool:
        """Return True if the agent is alive and its heartbeat is fresh."""
        async with self._lock:
            if self._state.status == AgentStatus.DEAD:
                return False
            if self._state.last_heartbeat is None:
                return False
            return (_utc_now() - self._state.last_heartbeat) < _HEARTBEAT_THRESHOLD


# ---------------------------------------------------------------------------
# AgentPool
# ---------------------------------------------------------------------------

class AgentPool:
    """Manages a fleet of AgentRunner instances.

    Thread-safe via an asyncio lock. All mutating operations are serialised.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentRunner] = {}
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        config: AgentConfig,
        provider: CompletionProvider | None = None,
        sandbox: CodeSandbox | None = None,
    ) -> AgentRunner:
        """Create, start, and register an agent.

        Args:
            config: Agent configuration.
            provider: Optional LLM provider.
            sandbox: Optional code sandbox.

        Returns:
            The started AgentRunner.
        """
        runner = AgentRunner(config, provider=provider, sandbox=sandbox)
        await runner.start()
        async with self._lock:
            self._agents[config.id] = runner
        logger.info("Pool spawned agent %s (%s)", config.name, config.id)
        return runner

    async def get(self, agent_id: str) -> AgentRunner | None:
        """Look up an agent by ID, or None if not found."""
        async with self._lock:
            return self._agents.get(agent_id)

    async def list_agents(self) -> list[AgentState]:
        """Return a snapshot of every agent's current state."""
        async with self._lock:
            return [runner.state for runner in self._agents.values()]

    async def get_idle(self) -> list[AgentRunner]:
        """Return all agents whose status is IDLE."""
        async with self._lock:
            return [
                runner
                for runner in self._agents.values()
                if runner.state.status == AgentStatus.IDLE
            ]

    async def get_idle_agents(self) -> list[AgentState]:
        """Return AgentState for all idle agents (orchestrator interface)."""
        runners = await self.get_idle()
        return [r.state for r in runners]

    async def assign(self, agent_id: str, task_id: str) -> None:
        """Mark an agent as assigned to a task (orchestrator interface)."""
        runner = await self.get(agent_id)
        if runner:
            async with runner._lock:
                runner._state.current_task = task_id

    async def release(self, agent_id: str) -> None:
        """Release an agent back to idle (orchestrator interface)."""
        runner = await self.get(agent_id)
        if runner:
            async with runner._lock:
                runner._state.current_task = None
                runner._state.status = AgentStatus.IDLE

    async def get_result(self, agent_id: str) -> str | None:
        """Get the last result from an agent (orchestrator interface).

        Returns None — actual results are collected via _execute_task
        in the orchestrator. This satisfies the duck-type contract.
        """
        return None

    async def shutdown_all(self) -> None:
        """Stop every agent in the pool."""
        async with self._lock:
            runners = list(self._agents.values())
        await asyncio.gather(*(r.stop() for r in runners))
        logger.info("Pool shut down %d agents", len(runners))

    async def remove_dead(self) -> None:
        """Remove all DEAD agents from the pool."""
        async with self._lock:
            dead_ids = [
                aid
                for aid, runner in self._agents.items()
                if runner.state.status == AgentStatus.DEAD
            ]
            for aid in dead_ids:
                del self._agents[aid]
        if dead_ids:
            logger.info("Pool removed %d dead agents", len(dead_ids))
