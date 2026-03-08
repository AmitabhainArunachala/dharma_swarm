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
    GateDecision,
    LLMRequest,
    LLMResponse,
    Task,
    TaskPriority,
)
from dharma_swarm.agent_memory import AgentMemoryBank
from dharma_swarm.telos_gates import check_with_reflective_reroute

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
_PRIORITY_SALIENCE = {
    TaskPriority.LOW: 0.30,
    TaskPriority.NORMAL: 0.50,
    TaskPriority.HIGH: 0.70,
    TaskPriority.URGENT: 0.90,
}


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
        from dharma_swarm.shakti import SHAKTI_HOOK
        ctx = build_agent_context(
            role=config.role.value,
            thread=config.thread,
        )
        if ctx:
            parts.append(ctx)
        parts.append(SHAKTI_HOOK)

    return "\n\n".join(parts)


def _build_prompt(
    task: Task,
    config: AgentConfig,
    plan_context: str = "",
) -> LLMRequest:
    """Build an LLMRequest from a task and agent config.

    Args:
        task: The task to execute.
        config: Agent configuration.
        plan_context: Optional formatted plan to inject (Manus pattern).
    """
    system = _build_system_prompt(config)
    user_parts = [f"## Task: {task.title}\n\n{task.description}"]
    if plan_context:
        user_parts.append(f"\n\n{plan_context}")
    return LLMRequest(
        model=config.model,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
        system=system,
    )


def _looks_like_provider_failure(content: str) -> bool:
    """Heuristic guard against error strings being marked as completed work."""
    normalized = (content or "").strip().lower()
    if not normalized:
        return True
    return any(normalized.startswith(prefix) for prefix in _ERROR_PREFIXES)


def _task_file_path(task: Task) -> str:
    """Infer file path context for a task mark."""
    meta = task.metadata or {}
    for key in ("file_path", "target_file", "path"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"task:{task.id}"


def _task_action(task: Task) -> str:
    """Infer stigmergy action from task metadata."""
    meta = task.metadata or {}
    if meta.get("modified") or meta.get("writes_files"):
        return "write"
    return "scan"


async def _leave_task_mark(
    *,
    agent_name: str,
    task: Task,
    result_text: str,
    success: bool,
) -> None:
    """Leave a stigmergic mark after task execution.

    Best-effort only: never fail task execution because marking failed.
    """
    try:
        from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

        salience = _PRIORITY_SALIENCE.get(task.priority, 0.5)
        if not success:
            salience = max(salience, 0.8)

        observation = (result_text or "").strip().replace("\n", " ")
        if not observation:
            observation = f"{task.title} ({'success' if success else 'failure'})"
        observation = f"{task.title}: {observation}"[:200]

        mark = StigmergicMark(
            agent=agent_name,
            file_path=_task_file_path(task),
            action=_task_action(task),  # type: ignore[arg-type]
            observation=observation,
            salience=salience,
            connections=[task.id, task.priority.value, "success" if success else "failure"],
        )
        store = StigmergyStore()
        await store.leave_mark(mark)
    except Exception as exc:
        logger.debug("Failed to leave task mark for %s: %s", agent_name, exc)


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Manages the full lifecycle of a single agent.

    Args:
        config: Static configuration for the agent.
        provider: Optional LLM provider (duck-typed with ``complete``).
        sandbox: Optional code sandbox (duck-typed with ``execute``).
        memory: Optional self-editing memory bank for the agent.
    """

    def __init__(
        self,
        config: AgentConfig,
        provider: CompletionProvider | None = None,
        sandbox: CodeSandbox | None = None,
        memory: AgentMemoryBank | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._sandbox = sandbox
        self._memory = memory
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
            meta = task.metadata if isinstance(task.metadata, dict) else {}
            spec_ref = str(meta.get("spec_ref", "")).strip() or None
            req_refs_raw = meta.get("requirement_refs", [])
            if isinstance(req_refs_raw, str):
                req_refs = [req_refs_raw]
            elif isinstance(req_refs_raw, list):
                req_refs = [str(r) for r in req_refs_raw if str(r).strip()]
            else:
                req_refs = []
            seed_reflection = str(meta.get("think_notes", "")).strip()
            if not seed_reflection:
                seed_reflection = (
                    f"Task={task.title}. Goal: execute safely with bounded changes."
                )

            gate = check_with_reflective_reroute(
                action=task.title,
                content=task.description,
                tool_name="agent_runner",
                think_phase="before_complete",
                reflection=seed_reflection,
                max_reroutes=2,
                spec_ref=spec_ref,
                requirement_refs=req_refs,
            )
            if gate.result.decision == GateDecision.BLOCK:
                raise RuntimeError(f"Telos block: {gate.result.reason}")

            plan_context = ""
            if gate.attempts:
                plan_context = (
                    "## Reflective Reroute Context\n"
                    f"- Reroute attempts: {gate.attempts}\n"
                    f"- Gate reason: {gate.result.reason}\n"
                    "- Apply these lenses before execution:\n"
                    + "\n".join(f"  - {s}" for s in gate.suggestions)
                )
            request = _build_prompt(task, self._config, plan_context=plan_context)

            # Inject agent self-editing memory into system prompt
            if self._memory is not None:
                memory_ctx = await self._memory.get_working_context()
                if memory_ctx.strip():
                    request.system = request.system + "\n\n" + memory_ctx

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

            await _leave_task_mark(
                agent_name=self._config.name,
                task=task,
                result_text=result,
                success=True,
            )

            # Record task result in agent memory
            await self._record_task_memory(task, result)

            logger.info(
                "Agent %s finished task %s", self._config.name, task.id
            )
            return result

        except Exception as exc:
            await _leave_task_mark(
                agent_name=self._config.name,
                task=task,
                result_text=str(exc),
                success=False,
            )

            # Record failure as a learned lesson
            await self._record_failure_memory(task, exc)

            async with self._lock:
                self._state.status = AgentStatus.IDLE
                self._state.current_task = None
                self._state.error = str(exc)
            logger.exception(
                "Agent %s failed task %s", self._config.name, task.id
            )
            raise

    # -- memory helpers ---------------------------------------------------

    async def _record_task_memory(self, task: Task, result: str) -> None:
        """Store a successful task result in agent memory.

        Records the result as a working memory entry with salience
        derived from task priority. Consolidates every 5 completed tasks.
        Best-effort: never fails the task if memory operations error.
        """
        if self._memory is None:
            return
        try:
            salience = _PRIORITY_SALIENCE.get(task.priority, 0.5)
            await self._memory.remember(
                key=f"task:{task.id}",
                value=result[:200],
                category="working",
                importance=salience,
                source=self._config.name,
            )
            # Consolidate periodically
            if self._state.tasks_completed % 5 == 0:
                await self._memory.consolidate()
            await self._memory.save()
        except Exception as exc:
            logger.debug(
                "Memory record failed for %s: %s", self._config.name, exc
            )

    async def _record_failure_memory(self, task: Task, exc: Exception) -> None:
        """Store a task failure as a learned lesson in archival memory.

        Best-effort: never masks the original exception.
        """
        if self._memory is None:
            return
        try:
            await self._memory.learn_lesson(
                f"Failed: {task.title}: {str(exc)[:100]}",
                source=self._config.name,
            )
            await self._memory.save()
        except Exception as mem_exc:
            logger.debug(
                "Memory lesson failed for %s: %s", self._config.name, mem_exc
            )

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
        memory: AgentMemoryBank | None = None,
    ) -> AgentRunner:
        """Create, start, and register an agent.

        Args:
            config: Agent configuration.
            provider: Optional LLM provider.
            sandbox: Optional code sandbox.
            memory: Optional self-editing memory bank.

        Returns:
            The started AgentRunner.
        """
        runner = AgentRunner(config, provider=provider, sandbox=sandbox, memory=memory)
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
