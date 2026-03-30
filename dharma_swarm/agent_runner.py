"""Async agent lifecycle manager.

Spawns agents, runs their work loop, handles heartbeats and shutdown.
Each AgentRunner manages a single agent; AgentPool manages the fleet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dharma_swarm.contracts.intelligence_agents import communication_topics
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
from dharma_swarm.agent_memory_manager import AgentMemoryManager, Scope as MemoryScope
from dharma_swarm.model_catalog import (
    apply_model_pack_metadata,
    selector_from_metadata,
)
from dharma_swarm.agent_runner_quality import (
    CompletionAssessment as _CompletionAssessment,
    assess_completion_semantics as _assess_completion_semantics,
    assess_honors_checkpoint as _assess_honors_checkpoint,
    build_semantic_repair_request as _build_semantic_repair_request,
    semantic_attempt_timeout_seconds as _semantic_attempt_timeout_seconds,
    semantic_repair_attempts as _semantic_repair_attempts,
)
from dharma_swarm.jikoku_samaya import get_global_tracer as _jikoku_tracer
from dharma_swarm.runtime_fields import (
    RuntimeFieldRegistry,
    build_runtime_field_registry_from_agent_config,
    runtime_field_manifest_for_agent_config,
)
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
_REASONING_LEAK_MARKERS = ("<think", "</think>", "<analysis", "</analysis>")
_EXPLORATION_PREAMBLE_MARKERS = (
    "i'll begin by",
    "i will begin by",
    "let me explore",
    "let me check",
    "first, i'll",
)
_FILE_REFERENCE_PATTERN = re.compile(
    r"(?<![\w/])(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+\.(?:py|md|json|yaml|yml|toml|txt|ts|tsx|js|jsx|sh))(?![\w/])"
)
_META_OBSERVATION_HINTS = (
    "system",
    "control plane",
    "orchestrator",
    "router",
    "feedback",
    "active inference",
    "mission contract",
    "evolution",
    "archive",
    "downstream",
    "upstream",
)
_OPENAI_TOOL_PROVIDER_TYPES = {
    ProviderType.OPENAI,
    ProviderType.OPENROUTER,
    ProviderType.OPENROUTER_FREE,
    ProviderType.NVIDIA_NIM,
    ProviderType.GROQ,
    ProviderType.CEREBRAS,
    ProviderType.SILICONFLOW,
    ProviderType.TOGETHER,
    ProviderType.FIREWORKS,
    ProviderType.GOOGLE_AI,
    ProviderType.SAMBANOVA,
    ProviderType.MISTRAL,
    ProviderType.CHUTES,
}
_LOCAL_TOOL_RUNTIME_DIRECTIVE = (
    "You have real local tool access for this task. "
    "Use `read_file`, `edit_file`, `write_file`, `glob_files`, `grep_search`, "
    "and `shell_exec` to inspect, modify, and verify the workspace. "
    "Do not roleplay tool use. Call tools directly when you need evidence or side effects."
)
_LOCAL_OPENAI_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the local workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "default": 1},
                    "limit": {"type": "integer", "default": 200},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a file in the local workspace, creating parents if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one exact string inside a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Execute a shell command inside the local workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "List files matching a glob pattern in the local workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search file contents with a regex pattern in the local workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "glob": {"type": "string"},
                    "max_results": {"type": "integer", "default": 30},
                },
                "required": ["pattern"],
            },
        },
    },
]


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
    metadata = _resolved_routing_metadata(task, config)
    override = _metadata_bool(metadata, "allow_provider_routing", "routed_execution", "use_router")
    if override is not None:
        return override
    # Keep agents pinned to their configured lane unless the task/config
    # explicitly widens execution. A global env toggle is too coarse here:
    # it can silently hijack dedicated seats such as cyber-glm5 onto a
    # primary-driver lane and invalidate model/provider provenance.
    return False


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
    metadata = _resolved_routing_metadata(task, config)
    explicit = _parse_provider_types(
        metadata.get("available_provider_types")
        or metadata.get("provider_allowlist")
    )
    if explicit:
        return explicit
    if _allow_provider_routing(task, config):
        return None
    return [config.provider]


def _resolved_routing_metadata(task: Task, config: AgentConfig) -> dict[str, Any]:
    config_metadata = (
        apply_model_pack_metadata(config.metadata)
        if isinstance(config.metadata, dict)
        else {}
    )
    task_metadata = apply_model_pack_metadata(_task_metadata(task))
    merged = dict(config_metadata)
    merged.update(task_metadata)
    return merged


def _preferred_model_hint(task: Task, config: AgentConfig) -> str | None:
    metadata = _resolved_routing_metadata(task, config)
    value = metadata.get("preferred_model")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _preferred_provider_hint(task: Task, config: AgentConfig) -> ProviderType | None:
    metadata = _resolved_routing_metadata(task, config)
    providers = _parse_provider_types(metadata.get("preferred_provider"))
    if providers:
        return providers[0]
    return None


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

    metadata = _resolved_routing_metadata(task, config)
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
    preferred_provider = _preferred_provider_hint(task, config) or config.provider
    preferred_model = _preferred_model_hint(task, config) or request.model
    context.update(
        {
            "task_id": task.id,
            "task_priority": task.priority.value,
            "task_title": task.title,
            "agent_id": config.id,
            "agent_name": config.name,
            "agent_role": config.role.value,
            "preferred_provider": preferred_provider.value,
            "preferred_model": preferred_model,
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
        and available_provider_types[0] == preferred_provider
    )
    selector = selector_from_metadata(metadata)
    if selector:
        context["model_catalog_selector"] = str(metadata.get("model_catalog_selector") or selector)

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
        provider=config.provider.value,
        model=config.model,
    )


def _build_self_state_block(agent_name: str) -> str:
    """Build a self-awareness context block for the agent.

    Reads identity snapshot, organism state (samvara), and recognition seed.
    Returns a compact text block (~500 chars) or empty string if unavailable.
    """
    state_dir = Path.home() / ".dharma"
    lines: list[str] = ["## Self-State"]

    # Agent identity
    identity_path = state_dir / "ginko" / "agents" / agent_name / "identity.json"
    if identity_path.exists():
        try:
            data = json.loads(identity_path.read_text())
            completed = data.get("tasks_completed", 0)
            failed = data.get("tasks_failed", 0)
            quality = data.get("avg_quality", 0.0)
            lines.append(
                f"Identity: {agent_name} | completed={completed} failed={failed} avg_quality={quality:.1f}"
            )
        except Exception:
            logger.debug("Agent identity read failed for %s", agent_name, exc_info=True)

    # Organism state (samvara — is the system in HOLD?)
    samvara_path = state_dir / "meta" / "samvara_state.json"
    if samvara_path.exists():
        try:
            data = json.loads(samvara_path.read_text())
            if data.get("active"):
                power = data.get("current_power", "unknown")
                holds = data.get("consecutive_holds", 0)
                lines.append(f"Organism: HOLD active (power={power}, holds={holds})")
            else:
                lines.append("Organism: flowing (no HOLD)")
        except Exception:
            logger.debug("Samvara state read failed", exc_info=True)

    # System coherence from recognition seed (one line)
    seed_path = state_dir / "meta" / "recognition_seed.md"
    if seed_path.exists():
        try:
            text = seed_path.read_text()
            for line in text.split("\n"):
                if "TCS=" in line:
                    lines.append(f"System: {line.strip().lstrip('#').strip()}")
                    break
        except Exception:
            logger.debug("Recognition seed read failed", exc_info=True)

    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


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

    # Inject dharmic ground — the Gnani field (ambient recognition environment)
    try:
        from dharma_swarm.dharma_attractor import DharmaAttractor
        _seed = DharmaAttractor().ambient_seed()
        if _seed:
            parts.append(_seed)
    except Exception:
        logger.debug("Attractor seed injection failed for %s", config.name, exc_info=True)

    # Inject agent self-state: identity, organism state, recent memory
    try:
        self_state = _build_self_state_block(config.name)
        if self_state:
            parts.append(self_state)
    except Exception:
        logger.debug("Self-state injection failed for %s", config.name, exc_info=True)

    # Inject neural consolidation corrections (behavioral backprop weights)
    try:
        from dharma_swarm.neural_consolidator import load_behavioral_corrections
        corrections = load_behavioral_corrections(config.name)
        if corrections:
            parts.append(corrections)
    except Exception:
        logger.debug("Correction injection failed for %s", config.name, exc_info=True)

    # Inject multi-layer context for real Claude Code agents
    if config.provider == ProviderType.CLAUDE_CODE:
        from dharma_swarm.context import build_agent_context
        ctx = build_agent_context(
            role=config.role.value,
            thread=config.thread,
        )
        if ctx:
            parts.append(ctx)

    # Inject SHAKTI_HOOK for ALL agents (universal perception mode)
    try:
        from dharma_swarm.shakti import SHAKTI_HOOK
        parts.append(SHAKTI_HOOK)
    except Exception:
        logger.debug("Shakti hook injection failed for %s", config.name, exc_info=True)

    prompt = "\n\n".join(parts)

    # Inject MemPO-style <mem> action instructions
    try:
        from dharma_swarm.mem_action import inject_mem_instruction
        prompt = inject_mem_instruction(prompt)
    except Exception:
        logger.debug("Mem instruction injection failed", exc_info=True)

    return prompt


def _resolve_config_state_dir(config: AgentConfig) -> Path | None:
    """Resolve isolated state from config or repo-local checkout."""
    for candidate in (
        config.metadata.get("memory_state_dir"),
        config.metadata.get("state_dir"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return Path(candidate).expanduser()
        if isinstance(candidate, Path):
            return candidate

    local_state_dir = Path.cwd() / ".dharma"
    if local_state_dir.exists():
        return local_state_dir
    return None


def _resolve_prompt_state_dir(task: Task, config: AgentConfig) -> Path | None:
    """Prefer task/config-local state and never silently fall back to HOME/.dharma."""
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    for candidate in (
        metadata.get("memory_state_dir"),
        metadata.get("state_dir"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return Path(candidate).expanduser()
        if isinstance(candidate, Path):
            return candidate

    return _resolve_config_state_dir(config)


def _resolve_agent_registry_dir(task: Task, config: AgentConfig) -> Path | None:
    """Resolve the per-run AgentRegistry directory, if one is configured."""
    state_dir = _resolve_prompt_state_dir(task, config)
    if state_dir is None:
        return None
    return state_dir / "ginko" / "agents"


def _resolve_config_agent_registry_dir(config: AgentConfig) -> Path | None:
    """Resolve the per-run AgentRegistry directory from config only."""
    state_dir = _resolve_config_state_dir(config)
    if state_dir is None:
        return None
    return state_dir / "ginko" / "agents"


def _resolve_ontology_path(
    task: Task,
    config: AgentConfig,
    explicit_path: Path | str | None,
) -> Path | None:
    """Resolve ontology persistence for a task without touching shared home state."""
    if explicit_path is not None:
        return Path(explicit_path).expanduser()
    state_dir = _resolve_prompt_state_dir(task, config)
    if state_dir is None:
        return None
    return state_dir / "ontology.db"


def _resolve_config_ontology_path(
    config: AgentConfig,
    explicit_path: Path | str | None,
) -> Path | None:
    """Resolve ontology persistence for agent startup without HOME fallback."""
    if explicit_path is not None:
        return Path(explicit_path).expanduser()
    state_dir = _resolve_config_state_dir(config)
    if state_dir is None:
        return None
    return state_dir / "ontology.db"


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
    try:
        from dharma_swarm.mission_contract import (
            load_completion_contract,
            render_completion_contract_brief,
        )

        completion_contract = load_completion_contract(metadata)
        if completion_contract is not None:
            user_parts.append("\n\n" + render_completion_contract_brief(completion_contract))
    except Exception:
        logger.debug("Completion contract prompt injection failed", exc_info=True)
    prompt_state_dir = _resolve_prompt_state_dir(task, config)
    memory_query = "\n".join(
        part.strip()
        for part in (task.title, task.description)
        if isinstance(part, str) and part.strip()
    )
    if memory_query and prompt_state_dir is not None:
        memory_mode = os.getenv("DGC_AGENT_PROMPT_MEMORY_MODE", "active").strip().lower()
        try:
            from dharma_swarm.context import read_memory_context
            from dharma_swarm.context import read_latent_gold_context

            memory_context = read_memory_context(
                state_dir=prompt_state_dir,
                query=memory_query,
                limit=3,
                consumer="agent_runner.prompt",
                task_id=task.id,
                allow_semantic_search=memory_mode not in {"recent", "recent_only", "off"},
            )
            latent_gold = read_latent_gold_context(
                state_dir=prompt_state_dir,
                query=memory_query,
                limit=3,
            )
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
    # Inject fitness feedback (closes the strange loop)
    try:
        from dharma_swarm.signal_bus import SignalBus

        fitness_events = SignalBus.get().get_agent_fitness(config.name, n=5)
        if fitness_events:
            fitness_lines = ["## Recent Fitness Feedback"]
            for evt in fitness_events:
                etype = evt.get("type", "")
                if etype == "AGENT_FITNESS":
                    fitness_lines.append(
                        f"- Task {evt.get('task_id', '?')}: "
                        f"swabhaav={evt.get('swabhaav_ratio', '?'):.2f}, "
                        f"entropy={evt.get('entropy', '?'):.2f}, "
                        f"recognition={evt.get('recognition_type', '?')}"
                    )
                elif etype == "WORKER_FITNESS":
                    fitness_lines.append(
                        f"- Worker {evt.get('worker_type', '?')}: "
                        f"status={evt.get('status', '?')}, "
                        f"duration={evt.get('duration_seconds', '?')}s"
                    )
            user_parts.append("\n".join(fitness_lines))
    except Exception:
        logger.debug("Fitness injection failed", exc_info=True)

    if plan_context:
        user_parts.append(f"\n\n{plan_context}")
    return LLMRequest(
        model=config.model,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
        system=system,
    )


async def _inject_stigmergy_context(
    request: LLMRequest,
    task: Task,
    config: AgentConfig,
) -> None:
    """Add relevant stigmergy marks to the prompt before execution."""
    prompt_state_dir = _resolve_prompt_state_dir(task, config)
    if prompt_state_dir is None or not request.messages:
        return

    raw_parts = [
        part.strip()
        for part in (task.title, task.description, _task_file_path(task))
        if isinstance(part, str) and part.strip()
    ]
    task_keywords: list[str] = []
    for part in raw_parts:
        task_keywords.append(part)
        for token in re.findall(r"[A-Za-z0-9_./-]{4,}", part.lower()):
            if token not in task_keywords:
                task_keywords.append(token)
    if not task_keywords:
        return

    try:
        from dharma_swarm.stigmergy import StigmergyStore, _derive_channel

        store = StigmergyStore(base_path=prompt_state_dir / "stigmergy")
        marks = await store.query_relevant(
            task_keywords,
            limit=3,
            channel=_derive_channel(config.name),
        )
    except Exception:
        logger.debug("Stigmergy prompt injection failed", exc_info=True)
        return

    if not marks:
        return

    lines = ["## Stigmergy Recall"]
    for mark in marks:
        observation = " ".join(mark.observation.split())
        if len(observation) > 220:
            observation = observation[:217] + "..."
        lines.append(f"- [{mark.agent}] {mark.file_path}: {observation}")

    request.messages[0]["content"] = (
        str(request.messages[0]["content"]).rstrip()
        + "\n\n"
        + "\n".join(lines)
    )


async def _inject_recent_traces(
    request: LLMRequest,
    task: Task,
    config: AgentConfig,
) -> None:
    """Append the 3 most recent trace consequences for this agent to the prompt."""
    prompt_state_dir = _resolve_prompt_state_dir(task, config)
    if prompt_state_dir is None or not request.messages:
        return

    try:
        from dharma_swarm.traces import TraceStore

        store = TraceStore(base_path=prompt_state_dir / "traces")
        all_recent = await store.get_recent(limit=20)
        agent_traces = [e for e in all_recent if e.agent == config.name][:3]
    except Exception:
        logger.debug("Trace prompt injection failed", exc_info=True)
        return

    if not agent_traces:
        return

    lines = ["## Recent Consequences"]
    for entry in agent_traces:
        ts = entry.timestamp.strftime("%Y-%m-%dT%H:%M")
        detail = entry.metadata.get("step_name") or entry.action
        lines.append(f"- [{ts}] {entry.action}: {detail} (state={entry.state})")

    request.messages[0]["content"] = (
        str(request.messages[0]["content"]).rstrip()
        + "\n\n"
        + "\n".join(lines)
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


def _required_artifact_paths(task: Task) -> list[Path]:
    """Return required artifact paths declared in task metadata."""
    metadata = _task_metadata(task)
    raw_values: list[Any] = []
    for key in ("target_file", "target_path", "artifact_path", "required_artifact"):
        value = metadata.get(key)
        if value:
            raw_values.append(value)
    for key in ("required_artifacts", "artifact_paths", "target_files"):
        value = metadata.get(key)
        if isinstance(value, list):
            raw_values.extend(value)
        elif value:
            raw_values.append(value)

    out: list[Path] = []
    seen: set[str] = set()
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        path = Path(text).expanduser()
        norm = str(path)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(path)
    return out


def _task_requires_local_side_effects(task: Task) -> bool:
    """Whether the task contract requires file or command side effects."""
    metadata = _task_metadata(task)
    if _required_artifact_paths(task):
        return True
    for key in (
        "required_command",
        "shell_command",
        "command",
        "pytest_command",
        "expected_command",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _provider_supports_local_tool_loop(
    config: AgentConfig,
    provider: CompletionProvider | RoutedCompletionProvider | None,
) -> bool:
    if config.provider in {ProviderType.CLAUDE_CODE, ProviderType.CODEX}:
        return False
    capabilities = getattr(provider, "capabilities", None)
    supports_tools = getattr(capabilities, "supports_tools", None)
    if isinstance(supports_tools, bool):
        return supports_tools
    return config.provider in _OPENAI_TOOL_PROVIDER_TYPES


def _provider_can_execute_local_tooling(
    config: AgentConfig,
    sandbox: CodeSandbox | None,
) -> bool:
    """Only subprocess agents or an attached sandbox can actually mutate local state."""
    if sandbox is not None:
        return True
    return config.provider in {ProviderType.CLAUDE_CODE, ProviderType.CODEX}


def _tool_loop_max_rounds(task: Task, config: AgentConfig) -> int:
    metadata = _task_metadata(task)
    raw = (
        metadata.get("max_tool_rounds")
        or config.metadata.get("max_tool_rounds")
        or 8
    )
    try:
        return max(1, min(32, int(raw)))
    except (TypeError, ValueError):
        return 8


def _local_tool_workdir(task: Task, config: AgentConfig) -> Path:
    metadata = _task_metadata(task)
    for source in (metadata, config.metadata):
        for key in ("working_dir", "workdir", "workspace_root", "repo_root", "cwd"):
            value = source.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            candidate = Path(value).expanduser()
            if candidate.exists():
                return candidate.resolve()
            if candidate.parent.exists():
                return candidate.resolve(strict=False)
    for artifact in _required_artifact_paths(task):
        parent = artifact.parent
        if parent.exists():
            return parent.resolve()
        if parent.parent.exists():
            return parent.resolve(strict=False)
    return Path.cwd().resolve()


def _resolve_local_tool_path(raw_path: str, *, workdir: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workdir / candidate
    return candidate.resolve(strict=False)


def _tool_result_text(result: Any) -> str:
    if hasattr(result, "stdout") and hasattr(result, "stderr") and hasattr(result, "exit_code"):
        stdout = str(getattr(result, "stdout", "") or "")
        stderr = str(getattr(result, "stderr", "") or "")
        exit_code = getattr(result, "exit_code", "")
        parts = [f"exit_code: {exit_code}"]
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        return "\n".join(parts)
    return str(result)


def _guard_local_tool_side_effect(*, action: str, content: str) -> str | None:
    """Run a direct telos gate before a local side effect executes."""
    try:
        from dharma_swarm.telos_gates import check_action

        gate = check_action(action=action, content=content)
    except Exception as exc:
        logger.warning("Gate evaluation failed for local tool action %s", action, exc_info=True)
        return f"ERROR: Gate evaluation failed: {exc}"

    if gate.decision == GateDecision.BLOCK:
        return f"ERROR: Gate blocked action: {gate.reason}"
    if gate.decision == GateDecision.REVIEW:
        return f"ERROR: Gate review required: {gate.reason}"
    return None


def _normalized_tool_call_payload(tool_call: dict[str, Any], *, ordinal: int) -> dict[str, Any]:
    call_id = str(tool_call.get("id") or f"tool-call-{ordinal}")
    params = _tool_call_parameters(tool_call)
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": str(tool_call.get("name") or ""),
            "arguments": json.dumps(params),
        },
    }


def _tool_call_parameters(tool_call: dict[str, Any]) -> dict[str, Any]:
    params = tool_call.get("parameters")
    if isinstance(params, dict):
        return params
    raw = tool_call.get("arguments")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, dict):
        return raw
    raw = tool_call.get("input")
    return raw if isinstance(raw, dict) else {}


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
        from dharma_swarm.stigmergy import StigmergicMark, _get_default_store

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
        await _get_default_store().leave_mark(mark)
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
        worker_spawner: Any | None = None,
        ontology_path: Path | str | None = None,
        advanced_memory: AgentMemoryManager | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._sandbox = sandbox
        self._memory = memory
        self._message_bus = message_bus
        self._worker_spawner = worker_spawner
        self._ontology_path = _resolve_config_ontology_path(config, ontology_path)
        self._state = _state_from_config(config)
        self._lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._runtime_fields = build_runtime_field_registry_from_agent_config(config)
        # Letta-inspired self-managing memory (SQLite-backed)
        self._advanced_memory = advanced_memory

        # Sprint 3: Economic tracking
        self._economic_spine: Any = None
        self._tokens_used_total: int = 0

    def set_economic_spine(self, spine: Any) -> None:
        """Attach an EconomicSpine for cost tracking."""
        self._economic_spine = spine

    @property
    def tokens_used(self) -> int:
        """Total tokens consumed by this agent across all tasks."""
        return self._tokens_used_total

    # -- properties ---------------------------------------------------------

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def agent_id(self) -> str:
        return self._config.id

    @property
    def runtime_fields(self) -> RuntimeFieldRegistry:
        """Expose runtime mutation targets for prompt/parameter evolution."""
        return self._runtime_fields

    @property
    def advanced_memory(self) -> AgentMemoryManager | None:
        """Access the SQLite-backed self-managing memory, if configured."""
        return self._advanced_memory

    async def run_auto_research_workflow(
        self,
        brief: Any,
        *,
        research_engine: Any,
        grade_engine: Any,
        trace_store: Any | None = None,
        lineage_graph: Any | None = None,
        checkpoint_dir: Path | None = None,
        grade_kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Execute AutoResearch + AutoGrade through the canonical workflow runtime."""
        from dharma_swarm.workflow import execute_auto_research_workflow

        return await execute_auto_research_workflow(
            brief=brief,
            research_engine=research_engine,
            grade_engine=grade_engine,
            agent_name=self._config.name,
            trace_store=trace_store,
            lineage_graph=lineage_graph,
            checkpoint_dir=checkpoint_dir,
            grade_kwargs=grade_kwargs,
            runtime_field_names=self._runtime_fields.names(),
        )

    def get_memory_tools(self) -> dict[str, Any]:
        """Return callable memory tools for agent sandbox injection.

        These tools let the agent explicitly manage its own memory
        during task execution (Letta/MemGPT pattern).

        Returns:
            Dict of tool_name -> async callable, or empty dict if no
            advanced_memory is configured.
        """
        if self._advanced_memory is None:
            return {}

        mgr = self._advanced_memory

        async def remember(key: str, content: str, scope: str = "working", ttl: int | None = None) -> str:
            """Store a memory. Scope: working, short_term, long_term, shared."""
            s = MemoryScope(scope)
            mem = await mgr.remember(key, content, scope=s, ttl=ttl)
            return f"Remembered '{key}' in {scope}"

        async def recall(query: str, scope: str | None = None, limit: int = 5) -> str:
            """Search memories by keyword. Returns matching memories."""
            s = MemoryScope(scope) if scope else None
            results = await mgr.recall(query, scope=s, limit=limit)
            if not results:
                return "No memories found."
            lines = [f"Found {len(results)} memories:"]
            for m in results:
                lines.append(f"  [{m.scope.value}] {m.key}: {m.content[:200]}")
            return "\n".join(lines)

        async def forget(key: str) -> str:
            """Delete a memory by key."""
            deleted = await mgr.forget(key)
            return f"Forgot '{key}'" if deleted else f"No memory found for '{key}'"

        async def share(key: str, content: str, tags: str = "") -> str:
            """Share a memory with all agents in the swarm."""
            await mgr.share(key, content, tags=tags)
            return f"Shared '{key}' with swarm"

        return {
            "remember": remember,
            "recall": recall,
            "forget": forget,
            "share": share,
        }

    async def _ensure_local_tool_sandbox(self, task: Task) -> None:
        if self._sandbox is not None:
            return
        if not _provider_supports_local_tool_loop(self._config, self._provider):
            return
        from dharma_swarm.sandbox import LocalSandbox

        self._sandbox = LocalSandbox(workdir=_local_tool_workdir(task, self._config))

    async def _invoke_provider(
        self,
        task: Task,
        request: LLMRequest,
    ) -> tuple[Any | None, Any | None, LLMResponse]:
        if self._provider is None:
            raise RuntimeError("Provider unavailable")
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
            return route_request, route_decision, response
        return None, None, await self._provider.complete(request)

    async def _execute_local_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        *,
        task: Task,
    ) -> str:
        workdir = _local_tool_workdir(task, self._config)

        if tool_name == "read_file":
            path = _resolve_local_tool_path(str(parameters.get("path", "")), workdir=workdir)
            if not path.exists():
                return f"ERROR: File not found: {path}"
            if not path.is_file():
                return f"ERROR: Not a file: {path}"
            try:
                offset = max(1, int(parameters.get("offset", 1) or 1))
                limit = max(1, min(500, int(parameters.get("limit", 200) or 200)))
            except (TypeError, ValueError):
                offset = 1
                limit = 200
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            selected = lines[offset - 1 : offset - 1 + limit]
            numbered = [f"{offset + idx:>5} | {line}" for idx, line in enumerate(selected)]
            return "\n".join(numbered) if numbered else ""

        if tool_name == "write_file":
            path = _resolve_local_tool_path(str(parameters.get("path", "")), workdir=workdir)
            content = str(parameters.get("content", ""))
            gate_error = _guard_local_tool_side_effect(
                action=f"write_file: {parameters.get('path', '')}",
                content=content,
            )
            if gate_error:
                return gate_error
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"OK: wrote {len(content)} chars to {path}"

        if tool_name == "edit_file":
            path = _resolve_local_tool_path(str(parameters.get("path", "")), workdir=workdir)
            if not path.exists():
                return f"ERROR: File not found: {path}"
            old = str(parameters.get("old_string", ""))
            new = str(parameters.get("new_string", ""))
            gate_error = _guard_local_tool_side_effect(
                action=f"edit_file: {parameters.get('path', '')}",
                content=f"{old}\n{new}",
            )
            if gate_error:
                return gate_error
            content = path.read_text(encoding="utf-8", errors="replace")
            count = content.count(old)
            if count == 0:
                return f"ERROR: old_string not found in {path}"
            if count > 1:
                return f"ERROR: old_string found {count} times in {path}"
            path.write_text(content.replace(old, new, 1), encoding="utf-8")
            return f"OK: edited {path}"

        if tool_name in {"shell_exec", "bash"}:
            if self._sandbox is None:
                raise RuntimeError("Local tool sandbox unavailable")
            command = str(parameters.get("command", "")).strip()
            gate_error = _guard_local_tool_side_effect(
                action=f"{tool_name}: {command[:200]}",
                content=command,
            )
            if gate_error:
                return gate_error
            try:
                timeout = float(parameters.get("timeout", 30) or 30)
            except (TypeError, ValueError):
                timeout = 30.0
            result = await self._sandbox.execute(command, timeout=max(1.0, min(timeout, 300.0)))
            return _tool_result_text(result)

        if tool_name in {"glob_files", "search_files"}:
            pattern = str(parameters.get("pattern", "")).strip()
            base = _resolve_local_tool_path(str(parameters.get("path", "") or parameters.get("directory", "") or "."), workdir=workdir)
            matches = sorted(base.glob(pattern))[:50]
            if not matches:
                return f"No files matching {pattern!r}"
            return "\n".join(str(match) for match in matches)

        if tool_name in {"grep_search", "search_content"}:
            pattern = str(parameters.get("pattern", "")).strip()
            if not pattern:
                return "ERROR: pattern required"
            base = _resolve_local_tool_path(str(parameters.get("path", "") or parameters.get("directory", "") or "."), workdir=workdir)
            file_glob = str(parameters.get("glob", "") or parameters.get("file_glob", "") or "**/*")
            try:
                compiled = re.compile(pattern)
            except re.error as exc:
                return f"ERROR: invalid regex: {exc}"
            try:
                max_results = max(1, min(50, int(parameters.get("max_results", 30) or 30)))
            except (TypeError, ValueError):
                max_results = 30
            results: list[str] = []
            for candidate in base.glob(file_glob):
                if not candidate.is_file():
                    continue
                try:
                    for line_no, line in enumerate(
                        candidate.read_text(encoding="utf-8", errors="replace").splitlines(),
                        start=1,
                    ):
                        if compiled.search(line):
                            results.append(f"{candidate}:{line_no}:{line}")
                            if len(results) >= max_results:
                                return "\n".join(results)
                except Exception:
                    continue
            return "\n".join(results) if results else f"No matches for {pattern!r}"

        return f"ERROR: unknown tool {tool_name}"

    async def _complete_with_tool_loop(
        self,
        task: Task,
        request: LLMRequest,
    ) -> tuple[Any | None, Any | None, LLMResponse, str]:
        tool_request = request.model_copy(
            update={
                "system": (
                    request.system
                    if _LOCAL_TOOL_RUNTIME_DIRECTIVE in request.system
                    else f"{request.system}\n\n{_LOCAL_TOOL_RUNTIME_DIRECTIVE}".strip()
                ),
                "tools": list(_LOCAL_OPENAI_TOOL_DEFINITIONS),
            }
        )
        current_request = tool_request
        last_route_request: Any | None = None
        last_route_decision: Any | None = None

        for round_index in range(1, _tool_loop_max_rounds(task, self._config) + 1):
            route_request, route_decision, response = await self._invoke_provider(
                task,
                current_request,
            )
            if route_request is not None:
                last_route_request = route_request
            if route_decision is not None:
                last_route_decision = route_decision

            if not response.tool_calls:
                return last_route_request, last_route_decision, response, response.content

            updated_messages = list(current_request.messages)
            updated_messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        _normalized_tool_call_payload(tool_call, ordinal=index)
                        for index, tool_call in enumerate(response.tool_calls, start=1)
                    ],
                }
            )

            for index, tool_call in enumerate(response.tool_calls, start=1):
                params = _tool_call_parameters(tool_call)
                tool_name = str(tool_call.get("name") or "")
                tool_id = str(tool_call.get("id") or f"tool-call-{round_index}-{index}")
                tool_result = await self._execute_local_tool(
                    tool_name,
                    params,
                    task=task,
                )
                updated_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": tool_result[:16000],
                    }
                )

            current_request = current_request.model_copy(update={"messages": updated_messages})

        raise RuntimeError(
            f"Local tool loop exceeded max rounds ({_tool_loop_max_rounds(task, self._config)})"
        )

    async def _execute_completion_attempt(
        self,
        task: Task,
        request: LLMRequest,
        *,
        attempt_index: int,
    ) -> tuple[Any | None, Any | None, LLMResponse, str, float]:
        response: LLMResponse | None = None
        completion_latency_ms = 0.0
        _tracer = _jikoku_tracer()
        _jspan = _tracer.start(
            "execute.llm_call",
            f"Agent {self._config.name}: {task.title[:80]} [attempt {attempt_index}]",
            agent_id=self._config.name,
            task_id=task.id,
        )
        try:
            if _is_routed_provider(self._provider):
                preferred_model = _preferred_model_hint(task, self._config)
                if preferred_model and preferred_model != request.model:
                    request = request.model_copy(update={"model": preferred_model})
            completion_started = time.monotonic()
            if (
                self._sandbox is not None
                and _provider_supports_local_tool_loop(self._config, self._provider)
                and _requires_tooling(task, self._config)
            ):
                route_request, route_decision, response, result = (
                    await self._complete_with_tool_loop(task, request)
                )
            else:
                route_request, route_decision, response = await self._invoke_provider(
                    task,
                    request,
                )
                result = response.content
            completion_latency_ms = (time.monotonic() - completion_started) * 1000.0
            return route_request, route_decision, response, result, completion_latency_ms
        finally:
            try:
                _tracer.end(
                    _jspan,
                    latency_ms=completion_latency_ms,
                    model=getattr(response, "model", "") if response else "",
                    provider=getattr(response, "provider", "") if response else "",
                    success=(
                        response is not None
                        and not _looks_like_provider_failure(response.content)
                    )
                    if response
                    else False,
                )
            except Exception:
                logger.debug("Trace recording failed", exc_info=True)

    def _start_active_inference(self, task: Task) -> tuple[Any | None, Any | None]:
        state_dir = _resolve_prompt_state_dir(task, self._config)
        if state_dir is None:
            return None, None
        try:
            from dharma_swarm.active_inference import get_engine

            engine = get_engine(state_dir=state_dir / "active_inference")
            task_type = str(
                _task_metadata(task).get("task_type", "general") or "general"
            )
            prediction = engine.predict(self.agent_id, task.id, task_type)
            return engine, prediction
        except Exception:
            logger.debug("Active inference prediction failed", exc_info=True)
            return None, None

    def _observe_active_inference(
        self,
        engine: Any,
        prediction: Any,
        observed_quality: float,
    ) -> None:
        if engine is None or prediction is None:
            return
        try:
            engine.observe(prediction, observed_quality)
        except Exception:
            logger.debug("Active inference observation failed", exc_info=True)

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Initialize the agent and mark it IDLE."""
        async with self._lock:
            self._state.status = AgentStatus.IDLE
            self._state.started_at = _utc_now()
            self._state.last_heartbeat = _utc_now()
            logger.info("Agent %s (%s) started", self._config.name, self.agent_id)
        await self._publish_bus_presence()
        await self._ensure_bus_subscriptions()

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

        # ── Lifecycle event: task started ──
        try:
            from dharma_swarm.signal_bus import SignalBus
            SignalBus.get().emit({
                "type": "LIFECYCLE_TASK_STARTED",
                "agent": self._config.name,
                "task_id": task.id,
                "task_title": task.title[:100],
                "timestamp": _utc_now().isoformat(),
            })
        except Exception:
            logger.debug("Lifecycle start signal failed", exc_info=True)

        request: LLMRequest | None = None
        route_request: Any | None = None
        route_decision: Any | None = None
        response: LLMResponse | None = None
        completion_latency_ms = 0.0
        active_inference_engine: Any | None = None
        active_inference_prediction: Any | None = None
        observed_quality_score: float | None = None

        _task_tracer = _jikoku_tracer()
        _task_span = _task_tracer.start(
            "execute.tool_use",
            f"run_task({self._config.name}, {task.title[:60]})",
            agent_id=self._config.name,
            task_id=task.id,
        )
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
            await _inject_stigmergy_context(request, task, self._config)
            await _inject_recent_traces(request, task, self._config)
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
                logger.debug("Conversation turn logging failed", exc_info=True)

            # Inject agent self-editing memory into system prompt
            if self._memory is not None:
                memory_ctx = await self._memory.get_working_context()
                if memory_ctx.strip():
                    request.system = request.system + "\n\n" + memory_ctx

            if _requires_tooling(task, self._config):
                await self._ensure_local_tool_sandbox(task)

            if (
                _task_requires_local_side_effects(task)
                and not _provider_can_execute_local_tooling(self._config, self._sandbox)
            ):
                raise RuntimeError(
                    f"Provider {self._config.provider.value} cannot execute local tooling task "
                    "without a subprocess agent or attached sandbox"
                )

            active_inference_engine, active_inference_prediction = (
                self._start_active_inference(task)
            )

            if self._provider is not None:
                current_request = request
                attempts_remaining = _semantic_repair_attempts(task, self._config)
                attempt_index = 1
                accepted_checkpoint: Any | None = None
                while True:
                    attempt_timeout_seconds = _semantic_attempt_timeout_seconds(
                        task,
                        self._config,
                        attempts_remaining=attempts_remaining,
                    )
                    try:
                        attempt_result = self._execute_completion_attempt(
                            task,
                            current_request,
                            attempt_index=attempt_index,
                        )
                        if attempt_timeout_seconds is not None:
                            (
                                route_request,
                                route_decision,
                                response,
                                result,
                                attempt_latency_ms,
                            ) = await asyncio.wait_for(
                                attempt_result,
                                timeout=attempt_timeout_seconds,
                            )
                        else:
                            (
                                route_request,
                                route_decision,
                                response,
                                result,
                                attempt_latency_ms,
                            ) = await attempt_result
                    except asyncio.TimeoutError:
                        attempt_label = (
                            f"{attempt_timeout_seconds:.2f}s"
                            if attempt_timeout_seconds is not None
                            else "the attempt budget"
                        )
                        completion_latency_ms += (
                            max(0.0, attempt_timeout_seconds) * 1000.0
                            if attempt_timeout_seconds is not None
                            else 0.0
                        )
                        assessment = _CompletionAssessment(
                            accepted=False,
                            quality_score=0.0,
                            reason=(
                                "Semantic acceptance failed: attempt timeout, timed out after "
                                f"{attempt_label}"
                            ),
                        )
                        observed_quality_score = 0.0
                        if attempts_remaining <= 0:
                            raise RuntimeError(assessment.reason)
                        current_request = _build_semantic_repair_request(
                            current_request,
                            failed_result=f"ATTEMPT TIMED OUT after {attempt_label}",
                            assessment=assessment,
                            attempt_index=attempt_index,
                        )
                        attempts_remaining -= 1
                        attempt_index += 1
                        continue
                    completion_latency_ms += attempt_latency_ms
                    if _looks_like_provider_failure(result):
                        raise RuntimeError(result or "Provider returned empty response")
                    assessment = await _assess_completion_semantics(
                        task,
                        self._config,
                        result,
                        requires_tooling=_requires_tooling(task, self._config),
                        requires_local_side_effects=_task_requires_local_side_effects(task),
                    )
                    accepted_checkpoint = None
                    if assessment.accepted:
                        assessment, accepted_checkpoint = _assess_honors_checkpoint(
                            task,
                            result,
                            semantic_quality_score=assessment.quality_score,
                        )
                    observed_quality_score = assessment.quality_score
                    if assessment.accepted:
                        if accepted_checkpoint is not None:
                            updated_meta = _task_metadata(task)
                            updated_meta["honors_checkpoint"] = accepted_checkpoint.model_dump(mode="json")
                            task.metadata = updated_meta
                        break
                    if attempts_remaining <= 0:
                        raise RuntimeError(assessment.reason)
                    current_request = _build_semantic_repair_request(
                        current_request,
                        failed_result=result,
                        assessment=assessment,
                        attempt_index=attempt_index,
                    )
                    attempts_remaining -= 1
                    attempt_index += 1
            else:
                result = (
                    f"[mock] Agent {self._config.name} completed: {task.title}"
                )
                observed_quality_score = 1.0

            required_artifacts = _required_artifact_paths(task)
            missing_artifacts = [path for path in required_artifacts if not path.exists()]
            if missing_artifacts:
                missing_str = ", ".join(str(path) for path in missing_artifacts[:5])
                raise RuntimeError(
                    f"Completion contract failed: required artifact missing ({missing_str})"
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
                logger.debug("Conversation turn logging failed", exc_info=True)
            self._record_router_feedback(
                task=task,
                request=request,
                route_request=route_request,
                route_decision=route_decision,
                response=response,
                latency_ms=completion_latency_ms,
                success=True,
                result_text=result,
                quality_score_override=observed_quality_score,
            )

            # ── Langfuse / local observability trace ──
            try:
                from dharma_swarm.observability import get_observer
                _usage = response.usage if response else {}
                get_observer().trace_agent_dispatch(
                    agent=self._config.name,
                    task_id=task.id,
                    task_title=task.title[:200],
                    provider=getattr(response, "provider", "") if response else "",
                    model=getattr(response, "model", "") if response else "",
                    prompt_tokens=int(_usage.get("prompt_tokens", 0)),
                    completion_tokens=int(_usage.get("completion_tokens", 0)),
                    latency_ms=completion_latency_ms,
                    success=True,
                    result_preview=result[:300] if result else "",
                )
            except Exception:
                logger.debug("Observability trace failed", exc_info=True)

            # ── Output guardrails: check agent output before accepting ──
            try:
                from dharma_swarm.guardrails import (
                    GuardrailContext,
                    create_default_runner,
                )
                _gr = create_default_runner(include_telos=False)
                _gr_ctx = GuardrailContext(
                    action="task_completion",
                    content=result[:2000] if result else "",
                    agent=self._config.name,
                    task_id=task.id,
                )
                _gr_summary = await _gr.check_outputs(_gr_ctx)
                if not _gr_summary.passed:
                    logger.warning(
                        "Output guardrail flagged %s/%s: %s",
                        self._config.name, task.id,
                        "; ".join(r.reason for r in _gr_summary.results if r.reason),
                    )
            except Exception:
                logger.debug("Guardrail check failed", exc_info=True)

            self._observe_active_inference(
                active_inference_engine,
                active_inference_prediction,
                observed_quality_score if observed_quality_score is not None else 0.0,
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

            # ── Lifecycle event: emit to SignalBus for cross-system awareness ──
            try:
                from dharma_swarm.signal_bus import SignalBus
                SignalBus.get().emit({
                    "type": "LIFECYCLE_TASK_COMPLETED",
                    "agent": self._config.name,
                    "task_id": task.id,
                    "task_title": task.title[:100],
                    "timestamp": _utc_now().isoformat(),
                })
            except Exception:
                logger.debug("Lifecycle signal failed", exc_info=True)

            # ── Lineage: record provenance edge (task consumed prompt, produced result) ──
            try:
                from dharma_swarm.lineage import LineageGraph, LineageEdge
                _lineage = LineageGraph()
                _lineage.record(LineageEdge(
                    task_id=task.id,
                    input_artifacts=[f"prompt:{task.id}"],
                    output_artifacts=[f"result:{task.id}"],
                    agent=self._config.name,
                    operation=task.title[:100],
                    metadata={
                        "task_type": meta.get("task_type", "general"),
                        "cell_id": meta.get("cell_id", ""),
                        "result_length": len(result) if result else 0,
                    },
                ))
            except Exception:
                logger.debug("Lineage recording failed", exc_info=True)

            # ── MemPO: extract and store <mem> actions from response ──
            try:
                from dharma_swarm.mem_action import parse_mem_actions, store_mem_action
                mem_actions = parse_mem_actions(
                    result or "",
                    agent_id=self._config.name,
                    task_id=task.id,
                    step_number=self._state.turns_used,
                )
                if mem_actions:
                    # Store the latest <mem> on the runner for context truncation
                    self._last_mem_action = mem_actions[-1]
                    # Persist to Memory Palace
                    palace = getattr(self, "_memory_palace", None)
                    for ma in mem_actions:
                        await store_mem_action(palace, ma)
                    logger.debug(
                        "Extracted %d <mem> action(s) from %s/%s",
                        len(mem_actions),
                        self._config.name,
                        task.id,
                    )
            except Exception:
                logger.debug("Mem action extraction failed", exc_info=True)

            # Record task result in agent memory
            await self._record_task_memory(task, result)
            self._record_idea_uptake(task, result)
            self._record_follow_up_shard_outcome(task, outcome="success", evidence_text=result)
            self._record_retrieval_citation_uptake(task, result)
            self._mark_idea_outcome(task, outcome="success")
            self._record_retrieval_outcome(task, outcome="success")

            # Strange loop: score agent output and emit fitness signal
            self._emit_fitness_signal(task, result)

            # ── AgentRegistry: log task for fitness + budget tracking ──
            try:
                from dharma_swarm.agent_registry import get_registry
                registry_dir = _resolve_agent_registry_dir(task, self._config)
                if registry_dir is not None:
                    _reg = get_registry(registry_dir)
                    _reg.log_task(
                        name=self._config.name,
                        task=task.title[:200],
                        success=True,
                        tokens=_response_total_tokens(response),
                        latency_ms=completion_latency_ms,
                        response_preview=result[:500] if result else "",
                    )
            except Exception:
                logger.debug("AgentRegistry task log failed", exc_info=True)

            # ── Telic Seam: record Outcome + ValueEvent + Contribution ──
            try:
                from dharma_swarm.telic_seam import get_seam
                ontology_path = _resolve_ontology_path(task, self._config, self._ontology_path)
                if ontology_path is not None:
                    seam = get_seam(ontology_path)
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
                logger.debug("Telic seam recording failed", exc_info=True)

            logger.info(
                "Agent %s finished task %s", self._config.name, task.id
            )

            # Sprint 3: Track token consumption via EconomicSpine
            try:
                step_tokens = _response_total_tokens(response)
                self._tokens_used_total += step_tokens
                if self._economic_spine is not None and step_tokens > 0:
                    mission_id = (
                        meta.get("mission_id", "") if isinstance(meta, dict) else ""
                    )
                    self._economic_spine.spend_tokens(
                        self._config.id, step_tokens, mission_id
                    )
            except Exception:
                logger.debug("Economic token tracking failed", exc_info=True)

            # Close outer task span (success)
            try:
                _task_tracer.end(_task_span, success=True, latency_ms=completion_latency_ms)
            except Exception:
                logger.debug("Tracer span close failed", exc_info=True)
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
                quality_score_override=observed_quality_score,
            )
            self._observe_active_inference(
                active_inference_engine,
                active_inference_prediction,
                observed_quality_score if observed_quality_score is not None else 0.0,
            )
            await _leave_task_mark(
                agent_name=self._config.name,
                task=task,
                result_text=str(exc),
                success=False,
            )

            # ── Langfuse / local observability trace (failure) ──
            try:
                from dharma_swarm.observability import get_observer
                _usage = response.usage if response else {}
                get_observer().trace_agent_dispatch(
                    agent=self._config.name,
                    task_id=task.id,
                    task_title=task.title[:200],
                    provider=getattr(response, "provider", "") if response else "",
                    model=getattr(response, "model", "") if response else "",
                    prompt_tokens=int(_usage.get("prompt_tokens", 0)),
                    completion_tokens=int(_usage.get("completion_tokens", 0)),
                    latency_ms=completion_latency_ms,
                    success=False,
                    error=str(exc)[:500],
                )
            except Exception:
                logger.debug("Observability trace (failure) failed", exc_info=True)

            # Record failure as a learned lesson
            await self._record_failure_memory(task, exc)
            self._record_follow_up_shard_outcome(task, outcome="failure", evidence_text=str(exc))
            self._mark_idea_outcome(task, outcome="failure")
            self._record_retrieval_outcome(task, outcome="failure")

            # ── AgentRegistry: log failure for fitness + budget tracking ──
            try:
                from dharma_swarm.agent_registry import get_registry
                registry_dir = _resolve_agent_registry_dir(task, self._config)
                if registry_dir is not None:
                    _reg = get_registry(registry_dir)
                    _reg.log_task(
                        name=self._config.name,
                        task=task.title[:200],
                        success=False,
                        tokens=_response_total_tokens(response),
                        latency_ms=completion_latency_ms,
                        response_preview=str(exc)[:500],
                    )
            except Exception:
                logger.debug("AgentRegistry failure log failed", exc_info=True)

            # ── Telic Seam: record failure Outcome + ValueEvent + Contribution ──
            try:
                from dharma_swarm.telic_seam import get_seam
                ontology_path = _resolve_ontology_path(task, self._config, self._ontology_path)
                if ontology_path is not None:
                    seam = get_seam(ontology_path)
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
                logger.debug("Telic seam recording failed", exc_info=True)

            async with self._lock:
                self._state.status = AgentStatus.IDLE
                self._state.current_task = None
                self._state.error = str(exc)
            # Close outer task span (failure)
            try:
                _task_tracer.end(_task_span, success=False, error=str(exc)[:200])
            except Exception:
                logger.debug("Tracer span close failed", exc_info=True)
            logger.exception(
                "Agent %s failed task %s", self._config.name, task.id
            )
            raise

    # -- worker delegation --------------------------------------------------

    async def spawn_worker(
        self,
        worker_type: str,
        task_title: str,
        task_description: str,
        **kwargs: Any,
    ) -> Any:
        """Spawn an ephemeral worker via the attached WorkerSpawner.

        Delegates to :class:`dharma_swarm.worker_spawn.WorkerSpawner`
        using this agent's LLM provider for execution.

        Returns:
            ``WorkerResult`` on success, or *None* if no spawner is attached.
        """
        if self._worker_spawner is None:
            logger.debug(
                "Agent %s has no worker_spawner — skipping spawn(%s)",
                self._config.name, worker_type,
            )
            return None

        from dharma_swarm.worker_spawn import WorkerSpec

        worker_metadata = apply_model_pack_metadata(dict(kwargs.pop("metadata", {}) or {}))
        parent_metadata = (
            apply_model_pack_metadata(self._config.metadata)
            if isinstance(self._config.metadata, dict)
            else {}
        )
        for key in (
            "model_catalog_selector",
            "model_pack",
            "provider_pack",
            "model_selector",
            "allow_provider_routing",
            "available_provider_types",
            "provider_allowlist",
            "preferred_provider",
            "preferred_model",
        ):
            if key not in worker_metadata and key in parent_metadata:
                value = parent_metadata.get(key)
                worker_metadata[key] = list(value) if isinstance(value, list) else value
        worker_metadata.setdefault("preferred_provider", self._config.provider.value)
        worker_metadata.setdefault("preferred_model", self._config.model)
        worker_metadata = apply_model_pack_metadata(worker_metadata)
        kwargs["metadata"] = worker_metadata

        spec = WorkerSpec(
            worker_type=worker_type,
            task_title=task_title,
            task_description=task_description,
            parent_agent=self._config.name,
            **kwargs,
        )
        return await self._worker_spawner.spawn(spec, provider=self._provider)

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
        quality_score_override: float | None = None,
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
                quality_score=(
                    _clamp01(float(quality_score_override))
                    if quality_score_override is not None
                    else _feedback_quality_score(
                        task,
                        self._config,
                        success=success,
                        result_text=result_text,
                    )
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
        if self._memory is not None:
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

        # Also record in advanced memory (SQLite-backed, Letta-inspired)
        if self._advanced_memory is not None:
            try:
                await self._advanced_memory.remember(
                    key=f"task:{task.id}",
                    content=result[:500],
                    scope=MemoryScope.SHORT_TERM,
                    ttl=86400,  # 24h TTL for task results
                )
                if self._state.tasks_completed % 5 == 0:
                    await self._advanced_memory.consolidate()
            except Exception as exc:
                logger.debug(
                    "Advanced memory record failed for %s: %s",
                    self._config.name, exc,
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
            # W4: Include quality_score so DarwinEngine can consume real-task fitness
            quality = _feedback_quality_score(
                task, self._config, success=True, result_text=result,
            )
            payload = {
                "agent": self._config.name,
                "task_id": task.id,
                "swabhaav_ratio": sig.swabhaav_ratio,
                "entropy": sig.entropy,
                "recognition_type": sig.recognition_type.value,
                "word_count": sig.word_count,
                "quality_score": quality,
            }
            # In-memory signal (same-process consumers)
            bus = SignalBus.get()
            bus.emit({"type": "AGENT_FITNESS", **payload})

            # Durable persistence (cross-process consumers)
            if self._message_bus is not None:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    t = loop.create_task(
                        self._message_bus.emit_event(
                            "AGENT_FITNESS",
                            task_id=task.id,
                            agent_id=self._config.name,
                            payload=payload,
                        )
                    )
                    self._background_tasks.add(t)
                    t.add_done_callback(self._background_tasks.discard)
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore

            RetrievalFeedbackStore(db_path).record_outcome(
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore

            RetrievalFeedbackStore(db_path).record_citation_uptake(
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(db_path).record_turn(
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(db_path).record_uptake_from_text(
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(db_path).record_follow_up_outcome(
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
        db_path = self._memory_plane_db_path(task)
        if db_path is None:
            return
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            ConversationMemoryStore(db_path).mark_task_outcome(
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
        if raw:
            return raw
        state_dir = _resolve_prompt_state_dir(task, self._config)
        if state_dir is None:
            return None
        return state_dir / "db" / "memory_plane.db"

    async def heartbeat(self) -> None:
        """Update the last_heartbeat timestamp."""
        async with self._lock:
            self._state.last_heartbeat = _utc_now()
        await self._publish_bus_presence()

    async def stop(self) -> None:
        """Gracefully shut down the agent."""
        async with self._lock:
            self._state.status = AgentStatus.STOPPING
        await self._publish_bus_presence()

        # P4: Mark agent retiring in ontology (Hofstadter)
        try:
            from dharma_swarm.ontology_agents import mark_agent_retiring
            mark_agent_retiring(
                self.agent_id,
                name=self._config.name,
                path=self._ontology_path,
            )
        except Exception:
            logger.debug("Ontology agent retirement skipped", exc_info=True)

        cleanup = getattr(self._sandbox, "cleanup", None)
        if callable(cleanup):
            try:
                await cleanup()
            except Exception:
                logger.debug("Sandbox cleanup failed for %s", self._config.name, exc_info=True)

        logger.info("Agent %s stopping", self._config.name)
        async with self._lock:
            self._state.status = AgentStatus.DEAD
        logger.info("Agent %s stopped", self._config.name)

    async def _publish_bus_presence(self) -> None:
        bus = self._message_bus
        if bus is None or not hasattr(bus, "heartbeat"):
            return
        metadata = {
            "runtime_agent_id": self.agent_id,
            "provider": self._state.provider,
            "model": self._state.model,
            "role": self._state.role.value if hasattr(self._state.role, "value") else str(self._state.role),
            "status": self._state.status.value if hasattr(self._state.status, "value") else str(self._state.status),
            "current_task": self._state.current_task,
            "communication_topics": list(communication_topics()),
        }
        try:
            await bus.heartbeat(self._config.name, metadata=metadata)
        except Exception as exc:
            logger.debug("Bus heartbeat failed for %s: %s", self._config.name, exc)

    async def _ensure_bus_subscriptions(self) -> None:
        bus = self._message_bus
        if bus is None or not hasattr(bus, "subscribe"):
            return
        try:
            for topic in communication_topics():
                await bus.subscribe(self._config.name, topic)
        except Exception as exc:
            logger.debug("Bus subscription failed for %s: %s", self._config.name, exc)

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
        worker_spawner: Any | None = None,
        ontology_path: Path | str | None = None,
        advanced_memory: AgentMemoryManager | None = None,
    ) -> AgentRunner:
        """Create, start, and register an agent.

        Args:
            config: Agent configuration.
            provider: Optional LLM provider.
            sandbox: Optional code sandbox.
            memory: Optional self-editing memory bank.
            message_bus: Optional persistent MessageBus for durable fitness events.
            worker_spawner: Optional WorkerSpawner for ephemeral worker delegation.
            ontology_path: Optional ontology DB path to isolate runtime projection.
            advanced_memory: Optional SQLite-backed self-managing memory (Letta-inspired).

        Returns:
            The started AgentRunner.
        """
        # Enrich config from constitutional roster if a matching spec exists
        try:
            from dharma_swarm.agent_constitution import get_agent_spec
            spec = get_agent_spec(config.name)
            if spec is not None and not config.system_prompt and spec.system_prompt:
                config = config.model_copy(update={"system_prompt": spec.system_prompt})
                logger.info("Constitution enriched %s with system_prompt", config.name)
        except Exception:
            logger.debug("Constitutional enrichment skipped", exc_info=True)

        # Auto-create advanced memory if not provided
        if advanced_memory is None:
            try:
                memory_namespace = str(
                    config.metadata.get("memory_namespace") or config.name
                ).strip() or config.name
                advanced_memory = AgentMemoryManager(memory_namespace)
            except Exception:
                logger.debug("Auto-create advanced memory failed", exc_info=True)

        runner = AgentRunner(
            config,
            provider=provider,
            sandbox=sandbox,
            memory=memory,
            message_bus=message_bus,
            worker_spawner=worker_spawner,
            ontology_path=ontology_path,
            advanced_memory=advanced_memory,
        )
        await runner.start()
        async with self._lock:
            self._agents[config.id] = runner

        # P4: Agents are objects in the ontology they operate on (Hofstadter)
        try:
            from dharma_swarm.ontology_agents import upsert_agent_identity
            resolved_ontology_path = _resolve_config_ontology_path(config, ontology_path)
            if resolved_ontology_path is not None:
                upsert_agent_identity(runner.state, path=resolved_ontology_path)
        except Exception:
            logger.debug("Ontology agent projection skipped", exc_info=True)

        # AgentRegistry: ensure agent has an identity record for fitness + budget
        try:
            from dharma_swarm.agent_registry import get_registry
            registry_dir = _resolve_config_agent_registry_dir(config)
            if registry_dir is not None:
                _reg = get_registry(registry_dir)
                _reg.register_agent(
                    name=config.name,
                    role=config.role.value if hasattr(config.role, "value") else str(config.role),
                    model=config.model or "",
                    system_prompt=config.system_prompt or "",
                    runtime_fields=runtime_field_manifest_for_agent_config(config),
                )
        except Exception:
            logger.debug("AgentRegistry registration skipped", exc_info=True)

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
