"""Async agent lifecycle manager.

Spawns agents, runs their work loop, handles heartbeats and shutdown.
Each AgentRunner manages a single agent; AgentPool manages the fleet.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    GateDecision,
    LLMRequest,
    LLMResponse,
    ProviderType,
    Task,
    TaskPriority,
)
from dharma_swarm.agent_memory import AgentMemoryBank
from dharma_swarm.telos_gates import check_with_reflective_reroute

logger = logging.getLogger(__name__)

from dharma_swarm.config import DEFAULT_CONFIG as _SWARM_CFG

_HEARTBEAT_THRESHOLD = timedelta(seconds=_SWARM_CFG.agent.heartbeat_threshold_seconds)
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
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_TOOLING_HINTS = (
    "apply patch",
    "bug",
    "code",
    "edit",
    "file",
    "fix",
    "implement",
    "module",
    "patch",
    "pytest",
    "refactor",
    "script",
    "test",
)
_FRONTIER_HINTS = (
    "analyze",
    "architecture",
    "compare",
    "debug",
    "design",
    "evaluate",
    "incident",
    "investigate",
    "prove",
    "research",
    "root cause",
    "security",
)
_PRIVILEGED_HINTS = (
    "credential",
    "delete",
    "deploy",
    "drop table",
    "kill ",
    "launchctl",
    "production",
    "rm -rf",
    "secret",
    "ssh",
    "sudo",
)


# ---------------------------------------------------------------------------
# Duck-typed protocols for provider and sandbox (no direct imports)
# ---------------------------------------------------------------------------

@runtime_checkable
class CompletionProvider(Protocol):
    """Anything with an async ``complete`` method returning an LLMResponse."""

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


@runtime_checkable
class RoutedCompletionProvider(Protocol):
    """Router-capable provider that can choose a lane per task."""

    async def complete_for_task(
        self,
        route_request: Any,
        request: LLMRequest,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> tuple[Any, LLMResponse]: ...

    def record_task_feedback(
        self,
        *,
        route_request: Any,
        request: LLMRequest,
        decision: Any,
        quality_score: float,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...


@runtime_checkable
class CodeSandbox(Protocol):
    """Anything with an async ``execute`` method."""

    async def execute(self, command: str, timeout: float = 30.0) -> Any: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return None


def _task_metadata(task: Task) -> dict[str, Any]:
    return task.metadata if isinstance(task.metadata, dict) else {}


def _task_text(task: Task) -> str:
    return "\n".join(part for part in (task.title, task.description) if part).strip()


def _task_action_name(task: Task) -> str:
    raw = str(_task_metadata(task).get("action_name") or task.title or "task").strip().lower()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in raw)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "task"


def _metadata_number(metadata: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                return float(text)
            except ValueError:
                continue
    return None


def _metadata_bool(metadata: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in metadata:
            continue
        value = _coerce_bool(metadata.get(key))
        if value is not None:
            return value
    return None


def _priority_score(priority: TaskPriority) -> float:
    return {
        TaskPriority.LOW: 0.18,
        TaskPriority.NORMAL: 0.40,
        TaskPriority.HIGH: 0.72,
        TaskPriority.URGENT: 0.95,
    }.get(priority, 0.40)


def _supports_provider_method(provider: object | None, method_name: str) -> bool:
    if provider is None:
        return False
    cls_attr = getattr(type(provider), method_name, None)
    if callable(cls_attr):
        return True
    instance_dict = getattr(provider, "__dict__", {})
    return callable(instance_dict.get(method_name))


def _is_routed_provider(provider: object | None) -> bool:
    return _supports_provider_method(provider, "complete_for_task") and _supports_provider_method(
        provider, "record_task_feedback"
    )


def _requires_tooling(task: Task, config: AgentConfig) -> bool:
    metadata = _task_metadata(task)
    override = _metadata_bool(
        metadata,
        "requires_tooling",
        "writes_files",
        "code_task",
    )
    if override is not None:
        return override
    if metadata.get("modified"):
        return True
    if config.provider in {ProviderType.CLAUDE_CODE, ProviderType.CODEX}:
        return True
    if config.role in {AgentRole.CODER, AgentRole.TESTER, AgentRole.SURGEON}:
        return True
    lowered = _task_text(task).lower()
    return any(marker in lowered for marker in _TOOLING_HINTS)


def _requires_frontier_precision(task: Task, config: AgentConfig) -> bool:
    metadata = _task_metadata(task)
    override = _metadata_bool(
        metadata,
        "requires_frontier_precision",
        "frontier_precision",
    )
    if override is not None:
        return override
    lowered = _task_text(task).lower()
    if any(marker in lowered for marker in _FRONTIER_HINTS):
        return True
    return config.role in {
        AgentRole.ARCHITECT,
        AgentRole.RESEARCHER,
        AgentRole.VALIDATOR,
    } and task.priority in {TaskPriority.HIGH, TaskPriority.URGENT}


def _is_privileged_action(task: Task) -> bool:
    metadata = _task_metadata(task)
    override = _metadata_bool(
        metadata,
        "privileged_action",
        "requires_human_consent",
    )
    if override is not None:
        return override
    lowered = _task_text(task).lower()
    return any(marker in lowered for marker in _PRIVILEGED_HINTS)


def _allow_provider_routing(task: Task, config: AgentConfig) -> bool:
    metadata = _task_metadata(task)
    override = _metadata_bool(
        metadata,
        "allow_provider_routing",
        "routed_execution",
        "use_router",
    )
    if override is not None:
        return override
    override = _metadata_bool(
        config.metadata,
        "allow_provider_routing",
        "routed_execution",
        "use_router",
    )
    if override is not None:
        return override
    return (
        os.environ.get("DGC_AGENT_ROUTED_EXECUTION", "").strip().lower() in _TRUE_VALUES
    )


def _parse_provider_types(value: Any) -> list[ProviderType]:
    if value is None:
        return []
    if isinstance(value, (str, ProviderType)):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    out: list[ProviderType] = []
    for item in items:
        provider: ProviderType | None = None
        if isinstance(item, ProviderType):
            provider = item
        elif isinstance(item, str):
            normalized = item.strip().lower()
            provider = next(
                (candidate for candidate in ProviderType if candidate.value == normalized),
                None,
            )
        if provider is not None and provider not in out:
            out.append(provider)
    return out


def _available_provider_types(
    task: Task,
    config: AgentConfig,
) -> list[ProviderType] | None:
    metadata = _task_metadata(task)
    explicit = _parse_provider_types(
        metadata.get("available_provider_types")
        or metadata.get("provider_allowlist")
        or config.metadata.get("available_provider_types")
        or config.metadata.get("provider_allowlist")
    )
    if explicit:
        return explicit
    if _allow_provider_routing(task, config):
        return None
    return [config.provider]


def _estimate_requested_tokens(request: LLMRequest, *, requires_tooling: bool) -> int:
    text = "\n".join(
        [request.system, *[msg.get("content", "") for msg in request.messages]]
    ).strip()
    if not text:
        return 256
    estimate = max(int(len(text) / 3.8), int(len(text.split()) * 1.3), 1)
    if requires_tooling:
        estimate = max(estimate, 1200)
    return max(estimate, 256)


def _build_route_request(
    task: Task,
    config: AgentConfig,
    request: LLMRequest,
    *,
    available_provider_types: list[ProviderType] | None,
) -> Any:
    from dharma_swarm.provider_policy import ProviderRouteRequest

    metadata = _task_metadata(task)
    lowered = _task_text(task).lower()
    requires_tooling = _requires_tooling(task, config)
    requires_frontier = _requires_frontier_precision(task, config)
    privileged_action = _is_privileged_action(task)

    urgency = _metadata_number(metadata, "urgency", "urgency_score")
    if urgency is None:
        urgency = _priority_score(task.priority)

    risk_score = _metadata_number(metadata, "risk_score")
    if risk_score is None:
        risk_score = 0.10
        if requires_tooling:
            risk_score = max(risk_score, 0.28)
        if requires_frontier:
            risk_score = max(risk_score, 0.40)
        if privileged_action:
            risk_score = max(risk_score, 0.78)
        if task.priority in {TaskPriority.HIGH, TaskPriority.URGENT}:
            risk_score = min(1.0, risk_score + 0.08)

    uncertainty = _metadata_number(metadata, "uncertainty", "uncertainty_score")
    if uncertainty is None:
        uncertainty = 0.18
        if any(
            marker in lowered
            for marker in ("analyze", "compare", "debug", "investigate", "research", "why")
        ):
            uncertainty = 0.42
        if config.role in {AgentRole.ARCHITECT, AgentRole.RESEARCHER, AgentRole.VALIDATOR}:
            uncertainty = max(uncertainty, 0.30)

    novelty = _metadata_number(metadata, "novelty", "novelty_score")
    if novelty is None:
        novelty = 0.12
        if any(
            marker in lowered
            for marker in ("architecture", "design", "explore", "new", "prototype", "research")
        ):
            novelty = 0.48

    expected_impact = _metadata_number(metadata, "expected_impact", "impact_score")
    if expected_impact is None:
        expected_impact = max(
            0.20,
            urgency * 0.85 + (0.12 if requires_frontier else 0.0),
        )

    preferred_low_cost = _metadata_bool(
        metadata,
        "preferred_low_cost",
        "prefer_low_cost",
    )
    if preferred_low_cost is None:
        preferred_low_cost = not requires_frontier and not privileged_action and task.priority in {
            TaskPriority.LOW,
            TaskPriority.NORMAL,
        }

    requires_human_consent = _metadata_bool(
        metadata,
        "requires_human_consent",
        "human_consent_required",
    )
    if requires_human_consent is None:
        requires_human_consent = privileged_action and task.priority == TaskPriority.URGENT

    estimated_latency_ms = int(
        _metadata_number(metadata, "estimated_latency_ms") or (
            2200 if requires_tooling or requires_frontier else 800
        )
    )
    estimated_tokens = int(
        _metadata_number(metadata, "estimated_tokens", "token_estimate")
        or _estimate_requested_tokens(request, requires_tooling=requires_tooling)
    )

    route_context = metadata.get("route_context")
    context = dict(route_context) if isinstance(route_context, dict) else {}
    context.update(
        {
            "task_id": task.id,
            "task_priority": task.priority.value,
            "task_title": task.title,
            "agent_id": config.id,
            "agent_name": config.name,
            "agent_role": config.role.value,
            "preferred_provider": config.provider.value,
            "session_id": str(
                metadata.get("session_id")
                or metadata.get("trace_id")
                or config.metadata.get("session_id")
                or f"task:{task.id}"
            ),
            "requires_tooling": requires_tooling,
            "trace_id": metadata.get("trace_id"),
            "source": metadata.get("source"),
            "task_brief": task.description or task.title,
        }
    )
    if available_provider_types is not None:
        context["available_provider_types"] = [
            provider.value for provider in available_provider_types
        ]
    context["preserve_requested_model"] = bool(
        available_provider_types
        and len(available_provider_types) == 1
        and available_provider_types[0] == config.provider
    )

    return ProviderRouteRequest(
        action_name=_task_action_name(task),
        risk_score=_clamp01(risk_score),
        uncertainty=_clamp01(uncertainty),
        novelty=_clamp01(novelty),
        urgency=_clamp01(urgency),
        expected_impact=_clamp01(expected_impact),
        estimated_latency_ms=max(200, estimated_latency_ms),
        estimated_tokens=max(64, estimated_tokens),
        preferred_low_cost=bool(preferred_low_cost),
        requires_frontier_precision=requires_frontier,
        privileged_action=privileged_action,
        requires_human_consent=bool(requires_human_consent),
        context=context,
    )


def _response_total_tokens(response: LLMResponse | None) -> int:
    if response is None:
        return 0
    usage = response.usage or {}
    return int(
        usage.get("total_tokens")
        or (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
        or 0
    )


def _feedback_quality_score(
    task: Task,
    config: AgentConfig,
    *,
    success: bool,
    result_text: str,
) -> float:
    metadata = _task_metadata(task)
    explicit = _metadata_number(
        metadata,
        "quality_score",
        "judge_score",
        "review_score",
        "router_quality_score",
        "result_quality",
    )
    if explicit is not None:
        return _clamp01(explicit)
    if not success:
        return 0.0
    text = result_text.strip()
    score = 0.64
    if len(text) >= 120:
        score += 0.08
    if len(text) >= 480:
        score += 0.06
    if len(text) < 60:
        score -= 0.12
    if _requires_tooling(task, config):
        if any(marker in text for marker in ("```", ".py", ".md", "pytest", "`")):
            score += 0.08
    lowered = text.lower()
    if any(marker in lowered for marker in ("i can't", "i cannot", "not sure", "todo")):
        score -= 0.15
    return _clamp01(score)


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
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    metadata.pop("_memory_recall_consumer", None)
    memory_query = "\n".join(
        part.strip()
        for part in (task.title, task.description)
        if isinstance(part, str) and part.strip()
    )
    if memory_query:
        memory_mode = os.getenv("DGC_AGENT_PROMPT_MEMORY_MODE", "recent_only").strip().lower()
        try:
            from dharma_swarm.context import read_memory_context
            from dharma_swarm.context import read_latent_gold_context

            memory_context = read_memory_context(
                query=memory_query,
                limit=3,
                consumer="agent_runner.prompt",
                task_id=task.id,
                allow_semantic_search=memory_mode not in {"recent", "recent_only", "off"},
            )
            latent_gold = read_latent_gold_context(query=memory_query, limit=3)
        except Exception:
            memory_context = ""
            latent_gold = ""
        if memory_mode == "off":
            memory_context = ""
        if (
            memory_context
            and not memory_context.startswith("No memory")
            and not memory_context.startswith("Memory unavailable")
            and not memory_context.startswith("Memory plane unavailable")
        ):
            user_parts.append(f"\n\n## Memory Recall\n{memory_context}")
            metadata["_memory_recall_consumer"] = "agent_runner.prompt"
        if latent_gold:
            user_parts.append(f"\n\n## Latent Gold\n{latent_gold}")
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
    """Infer file path context for a task mark.

    Priority:
    1. Explicit metadata keys (file_path / target_file / path)
    2. File path extracted from task title or description via regex
    3. Fallback: task:<id>
    """
    import re

    meta = task.metadata or {}
    for key in ("file_path", "target_file", "path"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Try to extract a file path from the task text
    text = f"{task.title} {task.description}"
    # Match paths like dharma_swarm/foo.py, ~/foo/bar.md, ./foo.json, /abs/path.txt
    pattern = r'(?:[\w./~-]+/[\w./~-]*\.(?:py|md|json|yaml|yml|txt|ts|js|toml|cfg|ini|sh))'
    match = re.search(pattern, text)
    if match:
        return match.group(0)

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
        provider: CompletionProvider | RoutedCompletionProvider | None = None,
        sandbox: CodeSandbox | None = None,
        memory: AgentMemoryBank | None = None,
        message_bus: Any | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._sandbox = sandbox
        self._memory = memory
        self._message_bus = message_bus
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

        request: LLMRequest | None = None
        route_request: Any | None = None
        route_decision: Any | None = None
        response: LLMResponse | None = None
        completion_latency_ms = 0.0

        try:
            meta = task.metadata if isinstance(task.metadata, dict) else {}
            telic_agent_id = self.agent_id
            telic_cell_id = str(meta.get("cell_id", "") or "")
            telic_task_type = str(meta.get("task_type", "general") or "general")
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
            self._record_conversation_turn(
                task,
                role="user",
                content=request.messages[0]["content"],
                turn_index=1,
            )
            # Unified conversation log
            try:
                from dharma_swarm.conversation_log import log_agent_turn
                log_agent_turn(
                    agent_id=self._config.name,
                    task_id=task.id,
                    role="user",
                    content=request.messages[0]["content"][:5000],
                )
            except Exception:
                pass

            # Inject agent self-editing memory into system prompt
            if self._memory is not None:
                memory_ctx = await self._memory.get_working_context()
                if memory_ctx.strip():
                    request.system = request.system + "\n\n" + memory_ctx

            if self._provider is not None:
                completion_started = time.monotonic()
                if _is_routed_provider(self._provider):
                    available_provider_types = _available_provider_types(task, self._config)
                    route_request = _build_route_request(
                        task,
                        self._config,
                        request,
                        available_provider_types=available_provider_types,
                    )
                    route_decision, response = await self._provider.complete_for_task(
                        route_request,
                        request,
                        available_provider_types=available_provider_types,
                    )
                else:
                    response = await self._provider.complete(request)
                completion_latency_ms = (time.monotonic() - completion_started) * 1000.0
                result = response.content
                if _looks_like_provider_failure(result):
                    raise RuntimeError(result or "Provider returned empty response")
            else:
                result = (
                    f"[mock] Agent {self._config.name} completed: {task.title}"
                )
            self._record_conversation_turn(
                task,
                role="assistant",
                content=result,
                turn_index=2,
            )
            # Unified conversation log
            try:
                from dharma_swarm.conversation_log import log_agent_turn
                log_agent_turn(
                    agent_id=self._config.name,
                    task_id=task.id,
                    role="assistant",
                    content=result[:5000],
                    model=getattr(response, "model", ""),
                    provider=getattr(response, "provider", ""),
                )
            except Exception:
                pass
            self._record_router_feedback(
                task=task,
                request=request,
                route_request=route_request,
                route_decision=route_decision,
                response=response,
                latency_ms=completion_latency_ms,
                success=True,
                result_text=result,
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
            self._record_idea_uptake(task, result)
            self._record_follow_up_shard_outcome(task, outcome="success", evidence_text=result)
            self._record_retrieval_citation_uptake(task, result)
            self._mark_idea_outcome(task, outcome="success")
            self._record_retrieval_outcome(task, outcome="success")

            # Strange loop: score agent output and emit fitness signal
            self._emit_fitness_signal(task, result)

            # ── Telic Seam: record Outcome + ValueEvent + Contribution ──
            try:
                from dharma_swarm.telic_seam import get_seam
                seam = get_seam()
                outcome_id = seam.record_outcome(
                    task,
                    telic_agent_id,
                    success=True,
                    result_summary=result[:200] if result else "",
                    duration_ms=completion_latency_ms,
                )
                if outcome_id:
                    ve_id = seam.record_value_event(
                        outcome_id, task, telic_agent_id,
                        result_text=result[:200] if result else "",
                        success=True,
                        duration_ms=completion_latency_ms,
                        cell_id=telic_cell_id,
                    )
                    if ve_id:
                        ve_obj = seam.registry.get_object(ve_id)
                        cv = ve_obj.properties.get("composite_value", 0.0) if ve_obj else 0.0
                        seam.record_contribution(
                            ve_id, telic_agent_id,
                            composite_value=cv,
                            cell_id=telic_cell_id,
                            task_type=telic_task_type,
                        )
            except Exception:
                pass  # Seam recording is never fatal

            logger.info(
                "Agent %s finished task %s", self._config.name, task.id
            )
            return result

        except Exception as exc:
            self._record_conversation_turn(
                task,
                role="assistant_error",
                content=str(exc),
                turn_index=2,
            )
            self._record_router_feedback(
                task=task,
                request=request,
                route_request=route_request,
                route_decision=route_decision,
                response=response,
                latency_ms=completion_latency_ms,
                success=False,
                result_text=str(exc),
            )
            await _leave_task_mark(
                agent_name=self._config.name,
                task=task,
                result_text=str(exc),
                success=False,
            )

            # Record failure as a learned lesson
            await self._record_failure_memory(task, exc)
            self._record_follow_up_shard_outcome(task, outcome="failure", evidence_text=str(exc))
            self._mark_idea_outcome(task, outcome="failure")
            self._record_retrieval_outcome(task, outcome="failure")

            # ── Telic Seam: record failure Outcome + ValueEvent + Contribution ──
            try:
                from dharma_swarm.telic_seam import get_seam
                seam = get_seam()
                outcome_id = seam.record_outcome(
                    task,
                    telic_agent_id,
                    success=False,
                    error=str(exc)[:200],
                    duration_ms=completion_latency_ms,
                )
                if outcome_id:
                    ve_id = seam.record_value_event(
                        outcome_id, task, telic_agent_id,
                        result_text=str(exc)[:200],
                        success=False,
                        duration_ms=completion_latency_ms,
                        cell_id=telic_cell_id,
                    )
                    if ve_id:
                        ve_obj = seam.registry.get_object(ve_id)
                        cv = ve_obj.properties.get("composite_value", 0.0) if ve_obj else 0.0
                        seam.record_contribution(
                            ve_id, telic_agent_id,
                            composite_value=cv,
                            cell_id=telic_cell_id,
                            task_type=telic_task_type,
                        )
            except Exception:
                pass  # Seam recording is never fatal

            async with self._lock:
                self._state.status = AgentStatus.IDLE
                self._state.current_task = None
                self._state.error = str(exc)
            logger.exception(
                "Agent %s failed task %s", self._config.name, task.id
            )
            raise

    def _record_router_feedback(
        self,
        *,
        task: Task,
        request: LLMRequest | None,
        route_request: Any,
        route_decision: Any,
        response: LLMResponse | None,
        latency_ms: float,
        success: bool,
        result_text: str,
    ) -> None:
        if (
            route_request is None
            or route_decision is None
            or request is None
            or self._provider is None
            or not _is_routed_provider(self._provider)
        ):
            return
        metadata = _task_metadata(task)
        feedback_metadata = {
            "feedback_origin": "agent_runner",
            "task_id": task.id,
            "task_priority": task.priority.value,
            "agent_name": self._config.name,
            "agent_role": self._config.role.value,
            "trace_id": metadata.get("trace_id"),
            "stop_reason": response.stop_reason if response else None,
        }
        if not success:
            feedback_metadata["error"] = result_text[:240]
        try:
            self._provider.record_task_feedback(
                route_request=route_request,
                request=request,
                decision=route_decision,
                quality_score=_feedback_quality_score(
                    task,
                    self._config,
                    success=success,
                    result_text=result_text,
                ),
                total_tokens=_response_total_tokens(response),
                latency_ms=latency_ms,
                success=success,
                model=response.model if response else None,
                metadata=feedback_metadata,
            )
        except Exception as exc:
            logger.debug(
                "Routing feedback record failed for %s: %s",
                self._config.name,
                exc,
            )

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

    def _emit_fitness_signal(self, task: Task, result: str) -> None:
        """Score agent output and emit fitness signal to the bus.

        Closes the strange loop: every agent output gets a behavioral
        score that feeds into the recognition seed via the signal bus.
        Also persists to MessageBus for cross-process durability.
        Best-effort — never fails the task.
        """
        try:
            from dharma_swarm.metrics import MetricsAnalyzer
            from dharma_swarm.signal_bus import SignalBus

            sig = MetricsAnalyzer().analyze(result)
            payload = {
                "agent": self._config.name,
                "task_id": task.id,
                "swabhaav_ratio": sig.swabhaav_ratio,
                "entropy": sig.entropy,
                "recognition_type": sig.recognition_type.value,
                "word_count": sig.word_count,
            }
            # In-memory signal (same-process consumers)
            bus = SignalBus.get()
            bus.emit({"type": "AGENT_FITNESS", **payload})

            # Durable persistence (cross-process consumers)
            if self._message_bus is not None:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        self._message_bus.emit_event(
                            "AGENT_FITNESS",
                            task_id=task.id,
                            agent_id=self._config.name,
                            payload=payload,
                        )
                    )
                except RuntimeError:
                    pass  # No running loop — skip durable emit
        except Exception as exc:
            logger.debug("Fitness signal emission failed: %s", exc)

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

    def _record_retrieval_outcome(self, task: Task, *, outcome: str) -> None:
        """Persist eventual task outcome for any prompt-time retrievals."""
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        consumer = metadata.get("_memory_recall_consumer")
        if not isinstance(consumer, str) or not consumer.strip():
            return
        try:
            from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore

            RetrievalFeedbackStore().record_outcome(
                task.id,
                outcome=outcome,
                consumer=consumer,
            )
        except Exception as exc:
            logger.debug(
                "Retrieval feedback outcome record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _record_retrieval_citation_uptake(self, task: Task, result: str) -> None:
        """Mark which retrieved memory hits were actually reflected in the output."""
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        consumer = metadata.get("_memory_recall_consumer")
        if not isinstance(consumer, str) or not consumer.strip():
            return
        try:
            from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore

            RetrievalFeedbackStore().record_citation_uptake(
                task.id,
                text=result,
                consumer=consumer,
            )
        except Exception as exc:
            logger.debug(
                "Retrieval citation uptake record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _record_conversation_turn(
        self,
        task: Task,
        *,
        role: str,
        content: str,
        turn_index: int,
    ) -> None:
        """Persist raw conversation turns for later harvesting."""
        if not content.strip():
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(self._memory_plane_db_path(task)).record_turn(
                session_id=self._conversation_session_id(task),
                task_id=task.id,
                role=role,
                content=content,
                turn_index=turn_index,
                metadata={"agent_name": self._config.name, "role": self._config.role.value},
                harvest=True,
            )
        except Exception as exc:
            logger.debug(
                "Conversation turn record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _record_idea_uptake(self, task: Task, result: str) -> None:
        """Mark which harvested task ideas survived into the final output."""
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(self._memory_plane_db_path(task)).record_uptake_from_text(
                task_id=task.id,
                text=result,
                uptake_kind="implemented",
            )
        except Exception as exc:
            logger.debug(
                "Idea uptake record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _record_follow_up_shard_outcome(
        self,
        task: Task,
        *,
        outcome: str,
        evidence_text: str,
    ) -> None:
        """Close the loop for tasks explicitly reopened from latent gold."""
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        shard_id = metadata.get("latent_gold_shard_id")
        if not isinstance(shard_id, str) or not shard_id.strip():
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(self._memory_plane_db_path(task)).record_follow_up_outcome(
                shard_id=shard_id,
                follow_up_task_id=task.id,
                outcome=outcome,
                evidence_text=evidence_text,
            )
        except Exception as exc:
            logger.debug(
                "Follow-up shard outcome record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _mark_idea_outcome(self, task: Task, *, outcome: str) -> None:
        """Keep unchosen but high-salience ideas alive after task completion."""
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(self._memory_plane_db_path(task)).mark_task_outcome(
                task.id,
                outcome=outcome,
            )
        except Exception as exc:
            logger.debug(
                "Idea outcome record failed for %s: %s",
                self._config.name,
                exc,
            )

    def _conversation_session_id(self, task: Task) -> str:
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        raw = (
            metadata.get("session_id")
            or metadata.get("trace_id")
            or self._config.metadata.get("session_id")
            or f"task:{task.id}"
        )
        return str(raw)

    def _memory_plane_db_path(self, task: Task):
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        raw = metadata.get("memory_plane_db") or self._config.metadata.get("memory_plane_db")
        return raw

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
        provider: CompletionProvider | RoutedCompletionProvider | None = None,
        sandbox: CodeSandbox | None = None,
        memory: AgentMemoryBank | None = None,
        message_bus: Any | None = None,
    ) -> AgentRunner:
        """Create, start, and register an agent.

        Args:
            config: Agent configuration.
            provider: Optional LLM provider.
            sandbox: Optional code sandbox.
            memory: Optional self-editing memory bank.
            message_bus: Optional persistent MessageBus for durable fitness events.

        Returns:
            The started AgentRunner.
        """
        runner = AgentRunner(config, provider=provider, sandbox=sandbox, memory=memory, message_bus=message_bus)
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
