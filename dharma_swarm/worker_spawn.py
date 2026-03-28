"""Worker Spawn Protocol — ephemeral worker lifecycle management.

Workers are short-lived agents spawned by stable constitutional agents
for bounded tasks. They execute, return results, and are cleaned up.

Key properties:
  - Parent reference: every worker knows who spawned it
  - Metrics rollup: worker fitness feeds parent's rolling score
  - Memory access: read-only access to parent's archival memory
  - FSM constraints: max 3 concurrent workers before requiring
    explicit state machine transitions (prevents coordination blowup)
  - Model diversity: different provider per spawn for +11.4% performance

Grounded in:
  - DeepMind/MIT: T = 2.72 × (n+0.5)^1.724 coordination overhead
  - DyLAN: dynamic selection beats fixed teams by 9.7-17.7%
  - Agent Constitution: max_concurrent_workers per stable agent
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from dharma_swarm.models import (
    LLMRequest,
    LLMResponse,
    ProviderType,
    TaskPriority,
    _new_id,
    _utc_now,
)
from dharma_swarm.model_catalog import apply_model_pack_metadata

logger = logging.getLogger(__name__)

# FSM constraint: above this threshold, spawning requires explicit justification
_FSM_THRESHOLD = 3

# Default timeout for worker execution (seconds)
_DEFAULT_TIMEOUT = 300.0

# Provider rotation for diversity gain (+11.4% from heterogeneity)
_PROVIDER_ROTATION: list[ProviderType] = [
    ProviderType.ANTHROPIC,
    ProviderType.OPENROUTER,
    ProviderType.OPENAI,
    ProviderType.OPENROUTER_FREE,
]


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


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


def _worker_available_provider_types(metadata: dict[str, Any]) -> list[ProviderType] | None:
    metadata = apply_model_pack_metadata(metadata)
    explicit = _parse_provider_types(
        metadata.get("available_provider_types") or metadata.get("provider_allowlist")
    )
    if explicit:
        return explicit
    allow_provider_routing = _coerce_bool(metadata.get("allow_provider_routing"))
    if allow_provider_routing:
        return None
    preferred = _parse_provider_types(metadata.get("preferred_provider"))
    if preferred:
        return preferred
    return None


# ---------------------------------------------------------------------------
# Worker state machine
# ---------------------------------------------------------------------------

class WorkerStatus(str, Enum):
    """Lifecycle states for an ephemeral worker."""
    PENDING = "pending"       # Created, not yet executing
    RUNNING = "running"       # Actively executing task
    COMPLETED = "completed"   # Successfully returned result
    FAILED = "failed"         # Execution error
    TIMEOUT = "timeout"       # Exceeded time limit
    CANCELLED = "cancelled"   # Cancelled by parent


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WorkerSpec:
    """Specification for spawning an ephemeral worker.

    The parent agent creates this to define what the worker should do.
    """
    worker_type: str              # e.g. "code_worker", "literature_digger"
    task_title: str
    task_description: str
    parent_agent: str             # Name of the stable agent that spawned this
    system_prompt: str = ""       # Task-specific system prompt
    model: str = ""               # Empty = use provider rotation
    provider: ProviderType | None = None  # None = use rotation
    timeout_seconds: float = _DEFAULT_TIMEOUT
    priority: TaskPriority = TaskPriority.NORMAL
    read_memory_from_parent: bool = True  # Read-only access to parent memory
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerResult:
    """Result returned by a completed worker."""
    worker_id: str
    worker_type: str
    parent_agent: str
    status: WorkerStatus
    result: str = ""
    error: str = ""
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime = field(default_factory=_utc_now)
    duration_seconds: float = 0.0
    tokens_used: int = 0
    model_used: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Worker Spawner
# ---------------------------------------------------------------------------

class WorkerSpawner:
    """Manages the lifecycle of ephemeral workers for a stable agent.

    Each stable constitutional agent gets one WorkerSpawner instance.
    The spawner enforces:
      - Max concurrent workers (from AgentSpec)
      - FSM transitions above _FSM_THRESHOLD
      - Provider rotation for diversity
      - Metrics rollup to parent
    """

    def __init__(
        self,
        parent_name: str,
        max_concurrent: int = 5,
    ) -> None:
        self._parent_name = parent_name
        self._max_concurrent = max_concurrent
        self._active_workers: dict[str, WorkerSpec] = {}
        self._completed: list[WorkerResult] = []
        self._spawn_count = 0  # Total spawns for provider rotation
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Number of currently active workers."""
        return len(self._active_workers)

    @property
    def above_fsm_threshold(self) -> bool:
        """True if active workers exceed the FSM constraint threshold."""
        return self.active_count >= _FSM_THRESHOLD

    def can_spawn(self) -> bool:
        """Check if spawning another worker is allowed."""
        return self.active_count < self._max_concurrent

    def _next_provider(self) -> ProviderType:
        """Rotate through providers for diversity gain."""
        idx = self._spawn_count % len(_PROVIDER_ROTATION)
        return _PROVIDER_ROTATION[idx]

    async def spawn(
        self,
        spec: WorkerSpec,
        provider: Any | None = None,
    ) -> WorkerResult:
        """Spawn a worker, execute its task, and return the result.

        Args:
            spec: Worker specification defining the task.
            provider: Optional completion provider. If None, a stub result
                      is returned (for use in tests or when no LLM is available).

        Returns:
            WorkerResult with status, output, and metrics.

        Raises:
            RuntimeError: If max concurrent workers exceeded.
        """
        async with self._lock:
            if not self.can_spawn():
                raise RuntimeError(
                    f"Worker spawn rejected: {self._parent_name} has "
                    f"{self.active_count}/{self._max_concurrent} active workers"
                )

            worker_id = _new_id()
            self._active_workers[worker_id] = spec
            self._spawn_count += 1
            spawn_index = self._spawn_count

        if self.above_fsm_threshold:
            logger.warning(
                "FSM threshold exceeded: %s has %d active workers (threshold: %d). "
                "Explicit state machine transition required.",
                self._parent_name, self.active_count, _FSM_THRESHOLD,
            )

        started_at = _utc_now()
        start_mono = time.monotonic()

        try:
            result_text = await self._execute(spec, provider, spawn_index)
            status = WorkerStatus.COMPLETED
            error = ""
        except asyncio.TimeoutError:
            result_text = ""
            status = WorkerStatus.TIMEOUT
            error = f"Worker timed out after {spec.timeout_seconds}s"
        except Exception as exc:
            result_text = ""
            status = WorkerStatus.FAILED
            error = str(exc)

        duration = time.monotonic() - start_mono
        completed_at = _utc_now()

        result = WorkerResult(
            worker_id=worker_id,
            worker_type=spec.worker_type,
            parent_agent=self._parent_name,
            status=status,
            result=result_text,
            error=error,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=round(duration, 3),
            model_used=spec.model or "rotated",
            metadata=spec.metadata,
        )

        # Cleanup: remove from active, add to completed history
        async with self._lock:
            self._active_workers.pop(worker_id, None)
            self._completed.append(result)
            # Keep bounded history
            if len(self._completed) > 100:
                self._completed = self._completed[-50:]

        # Emit fitness signal for rollup
        self._emit_worker_fitness(result)

        return result

    async def _execute(
        self,
        spec: WorkerSpec,
        provider: Any | None,
        spawn_index: int,
    ) -> str:
        """Execute the worker's task via the provider.

        If no provider is given, returns a placeholder (useful for testing).
        """
        if provider is None:
            return f"[Worker {spec.worker_type}] No provider — dry run for: {spec.task_title}"

        # Build the LLM request
        system_parts = [spec.system_prompt] if spec.system_prompt else [
            f"You are a {spec.worker_type} worker spawned by {spec.parent_agent}. "
            f"Complete the following task precisely and return your result."
        ]

        # Inject parent memory context if requested
        if spec.read_memory_from_parent:
            try:
                from dharma_swarm.agent_memory import AgentMemoryBank
                bank = AgentMemoryBank(spec.parent_agent)
                await bank.load()
                ctx = await bank.get_working_context()
                if ctx:
                    system_parts.append(f"\n## Parent Context\n{ctx}")
            except Exception:
                logger.debug("Best-effort memory injection failed", exc_info=True)

        metadata = apply_model_pack_metadata(spec.metadata)
        model = spec.model
        if not model:
            # Use provider rotation for diversity
            model = str(metadata.get("preferred_model") or "claude-sonnet-4-20250514")

        request = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": f"## Task: {spec.task_title}\n\n{spec.task_description}"}],
            system="\n\n".join(system_parts),
        )

        complete_for_task = getattr(provider, "complete_for_task", None)
        if callable(complete_for_task):
            from dharma_swarm.provider_policy import ProviderRouteRequest

            available_provider_types = _worker_available_provider_types(metadata)
            preferred_provider = _parse_provider_types(metadata.get("preferred_provider"))
            preserve_requested_model = bool(
                available_provider_types
                and len(available_provider_types) == 1
                and preferred_provider
                and available_provider_types[0] == preferred_provider[0]
            )
            route_request = ProviderRouteRequest(
                action_name=spec.worker_type,
                risk_score=0.18,
                uncertainty=0.24,
                novelty=0.20,
                urgency=0.30,
                expected_impact=0.22,
                context={
                    "source": "worker_spawn",
                    "worker_type": spec.worker_type,
                    "parent_agent": spec.parent_agent,
                    "task_brief": spec.task_description or spec.task_title,
                    "preferred_provider": (
                        preferred_provider[0].value if preferred_provider else ""
                    ),
                    "preferred_model": model,
                    "preserve_requested_model": preserve_requested_model,
                    "model_catalog_selector": str(metadata.get("model_catalog_selector", "")),
                },
            )
            _, response = await asyncio.wait_for(
                complete_for_task(
                    route_request,
                    request,
                    available_provider_types=available_provider_types,
                ),
                timeout=spec.timeout_seconds,
            )
        else:
            response = await asyncio.wait_for(
                provider.complete(request),
                timeout=spec.timeout_seconds,
            )
        return response.content

    def _emit_worker_fitness(self, result: WorkerResult) -> None:
        """Emit a fitness signal for the worker, tagged with parent for rollup."""
        try:
            from dharma_swarm.signal_bus import SignalBus

            bus = SignalBus.get()
            bus.emit({
                "type": "WORKER_FITNESS",
                "parent_agent": result.parent_agent,
                "worker_id": result.worker_id,
                "worker_type": result.worker_type,
                "status": result.status.value,
                "duration_seconds": result.duration_seconds,
                "tokens_used": result.tokens_used,
            })
        except Exception as exc:
            logger.debug("Worker fitness signal failed: %s", exc)

    def get_active_workers(self) -> list[str]:
        """Return worker IDs of currently active workers."""
        return list(self._active_workers.keys())

    def get_completed_results(self, limit: int = 10) -> list[WorkerResult]:
        """Return recent completed worker results."""
        return self._completed[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Return spawner statistics for health reporting."""
        completed = self._completed
        successes = sum(1 for r in completed if r.status == WorkerStatus.COMPLETED)
        failures = sum(1 for r in completed if r.status == WorkerStatus.FAILED)
        timeouts = sum(1 for r in completed if r.status == WorkerStatus.TIMEOUT)
        return {
            "parent": self._parent_name,
            "active_workers": self.active_count,
            "max_concurrent": self._max_concurrent,
            "total_spawns": self._spawn_count,
            "completed": len(completed),
            "success_rate": round(successes / max(1, len(completed)), 3),
            "failures": failures,
            "timeouts": timeouts,
            "above_fsm_threshold": self.above_fsm_threshold,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_spawner_for_agent(
    agent_name: str,
    *,
    state_dir: str | Path | None = None,
) -> WorkerSpawner:
    """Create a WorkerSpawner configured for a runtime agent.

    Uses the agent's max_concurrent_workers from the runtime roster.
    Falls back to 3 only when the agent cannot be resolved at all.
    """
    try:
        from dharma_swarm.agent_constitution import get_runtime_agent_spec

        spec = get_runtime_agent_spec(agent_name, state_dir=state_dir)
        max_workers = spec.max_concurrent_workers if spec is not None else 3
    except Exception:
        max_workers = 3
    return WorkerSpawner(parent_name=agent_name, max_concurrent=max_workers)
