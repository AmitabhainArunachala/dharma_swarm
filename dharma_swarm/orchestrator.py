"""Async task orchestrator with fan-out/fan-in routing.

The orchestrator connects a task_board to an agent_pool, dispatching work
via topology patterns. It owns neither dependency -- both are duck-typed.

Duck-type contracts:
    task_board:  get_ready_tasks() -> list[Task], update_task(id, **kw),
                 get(task_id) -> Task | None
    agent_pool:  get_idle_agents() -> list[AgentState], assign(aid, tid),
                 release(aid), get_result(aid) -> str | None,
                 get(aid) -> AgentRunner | None
    message_bus: send(Message) -> str  (optional)
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from dharma_swarm.models import (
    AgentState,
    Message,
    Task,
    TaskDispatch,
    TaskStatus,
    TopologyType,
    _new_id,
)
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.session_ledger import SessionLedger
from dharma_swarm.sheaf import (
    CoordinationProtocol,
    CoordinationResult,
    Discovery,
    InformationChannel,
    NoosphereSite,
)
from dharma_swarm.telos_gates import check_with_reflective_reroute
from dharma_swarm.yoga_node import ConstraintVerdict, YogaScheduler

logger = logging.getLogger(__name__)


@runtime_checkable
class TaskBoard(Protocol):
    """Duck-type protocol for task storage."""
    async def get_ready_tasks(self) -> list[Task]: ...
    async def update_task(self, task_id: str, **fields: Any) -> None: ...
    async def get(self, task_id: str) -> Task | None: ...


@runtime_checkable
class AgentPool(Protocol):
    """Duck-type protocol for agent management."""
    async def get_idle_agents(self) -> list[AgentState]: ...
    async def assign(self, agent_id: str, task_id: str) -> None: ...
    async def release(self, agent_id: str) -> None: ...
    async def get_result(self, agent_id: str) -> str | None: ...
    async def get(self, agent_id: str) -> Any: ...


class Orchestrator:
    """Async task orchestrator routing work to agents via fan-out/fan-in."""

    def __init__(
        self,
        task_board: Any = None,
        agent_pool: Any = None,
        message_bus: Any = None,
        ledger: SessionLedger | None = None,
        ledger_dir: Path | None = None,
        runtime_db_path: Path | None = None,
        shared_dir: Path | None = None,
        stigmergy_dir: Path | None = None,
        session_id: str | None = None,
        event_memory: Any = None,
        yoga: YogaScheduler | None = None,
    ) -> None:
        from dharma_swarm.config import DEFAULT_CONFIG
        _cfg = DEFAULT_CONFIG.orchestrator
        resolved_ledger_dir = Path(ledger_dir) if ledger_dir is not None else None
        resolved_runtime_db_path = runtime_db_path
        if (
            resolved_runtime_db_path is None
            and ledger is None
            and resolved_ledger_dir is not None
        ):
            if resolved_ledger_dir.name == "ledgers":
                resolved_runtime_db_path = (
                    resolved_ledger_dir.parent / "state" / "runtime.db"
                )
            else:
                resolved_runtime_db_path = resolved_ledger_dir / "runtime.db"

        self._board = task_board
        self._pool = agent_pool
        self._bus = message_bus
        self._event_memory = event_memory
        self._yoga = yoga
        self._ledger = ledger or SessionLedger(
            base_dir=resolved_ledger_dir,
            session_id=session_id,
            runtime_db_path=resolved_runtime_db_path,
        )
        self._telic_seam = self._init_telic_seam()
        self._shared_dir = shared_dir or self._derive_runtime_artifact_dir("shared")
        self._stigmergy_dir = stigmergy_dir or self._derive_runtime_artifact_dir("stigmergy")
        self._running = False
        self._active_dispatches: dict[str, TaskDispatch] = {}
        # Track running asyncio tasks for actual LLM execution
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._default_timeout_seconds = _cfg.task_timeout_seconds
        self._default_claim_timeout_seconds = _cfg.claim_timeout_seconds
        self._default_max_retries = _cfg.max_retries
        self._default_retry_backoff_seconds = _cfg.retry_backoff_seconds
        self._transient_failure_retry_limit = _cfg.transient_failure_retry_limit
        self._transient_failure_backoff_seconds = _cfg.transient_failure_backoff_seconds
        self._long_timeout_retry_limit = _cfg.long_timeout_retry_limit
        self._long_timeout_backoff_seconds = _cfg.long_timeout_backoff_seconds
        self._long_timeout_retry_threshold_seconds = _cfg.long_timeout_threshold_seconds
        self._timeout_retry_growth_factor = _cfg.timeout_retry_growth_factor
        self._max_timeout_retry_seconds = _cfg.max_timeout_retry_seconds
        self._last_coordination_result: CoordinationResult | None = None
        self._last_coordination_summary: dict[str, Any] = self._empty_coordination_summary()
        self._last_coordination_signature = ""
        self._last_coordination_refresh_at: float = 0.0  # monotonic timestamp
        self._coordination_refresh_interval_s: float = 120.0  # skip if refreshed within this window

    def _runtime_root(self) -> Path:
        base_dir = self._ledger.base_dir
        if base_dir.name == "ledgers":
            return base_dir.parent
        return base_dir

    def _init_telic_seam(self) -> Any | None:
        """Prefer a state-local ontology seam over the global singleton."""
        try:
            from dharma_swarm.ontology_runtime import get_shared_registry
            from dharma_swarm.telic_seam import TelicSeam

            ontology_db = self._runtime_root() / "ontology.db"
            registry = get_shared_registry(path=ontology_db)
            return TelicSeam(registry=registry, registry_path=ontology_db)
        except Exception:
            logger.debug("Failed to initialize local telic seam", exc_info=True)
            return None

    def _derive_runtime_artifact_dir(self, leaf: str) -> Path:
        """Resolve state-local artifact directories from the ledger root when possible."""
        return self._runtime_root() / leaf

    async def dispatch(
        self,
        task: Task,
        topology: TopologyType | Any = TopologyType.FAN_OUT,
    ) -> list[TaskDispatch]:
        """Assign task to available agents based on topology."""
        if self._pool is None:
            return []

        if self._is_topology_genome(topology):
            return await self._dispatch_topology_genome(task, topology)

        idle: list[AgentState] = await self._pool.get_idle_agents()
        if not idle:
            return []

        if topology in (TopologyType.FAN_OUT, TopologyType.BROADCAST):
            return await self.fan_out(task, idle)

        # PIPELINE / FAN_IN: single agent per step
        selected = self._select_idle_agent(task, list(idle))
        if selected is None:
            return []
        td = TaskDispatch(
            task_id=task.id,
            agent_id=selected.id,
            topology=topology,
            timeout_seconds=self._resolve_timeout_seconds(task, self._default_timeout_seconds),
        )
        await self._assign_dispatch(td)
        return [td]

    @staticmethod
    def _is_topology_genome(topology: Any) -> bool:
        return all(
            hasattr(topology, attr)
            for attr in ("nodes", "entrypoints", "validate_structure")
        )

    async def _dispatch_topology_genome(
        self,
        task: Task,
        genome: Any,
    ) -> list[TaskDispatch]:
        if self._pool is None:
            return []

        genome.validate_structure()
        idle: list[AgentState] = await self._pool.get_idle_agents()
        if not idle:
            return []

        available = list(idle)
        dispatches: list[TaskDispatch] = []
        entrypoints = list(genome.entrypoints)
        topology_type = TopologyType.FAN_OUT if len(entrypoints) > 1 else TopologyType.PIPELINE

        for node_id in entrypoints or [genome.nodes[0].node_id]:
            agent = self._select_idle_agent(task, available)
            if agent is None:
                break
            td = TaskDispatch(
                task_id=task.id,
                agent_id=agent.id,
                topology=topology_type,
                timeout_seconds=self._resolve_timeout_seconds(
                    task,
                    self._default_timeout_seconds,
                ),
                metadata={
                    "topology_genome_id": genome.genome_id,
                    "topology_node_id": node_id,
                    "topology_entrypoints": list(entrypoints),
                    "topology_edge_ids": list(genome.incoming_edge_ids(node_id)),
                },
            )
            await self._assign_dispatch(td)
            dispatches.append(td)
        return dispatches

    async def fan_out(
        self, task: Task, agents: list[AgentState]
    ) -> list[TaskDispatch]:
        """Split task across multiple agents, one dispatch per agent."""
        dispatches: list[TaskDispatch] = []
        for agent in agents:
            td = TaskDispatch(
                task_id=task.id,
                agent_id=agent.id,
                topology=TopologyType.FAN_OUT,
                timeout_seconds=self._resolve_timeout_seconds(
                    task,
                    self._default_timeout_seconds,
                ),
                metadata={"sub_task_id": _new_id(), "parent_task": task.id},
            )
            await self._assign_dispatch(td)
            dispatches.append(td)
        return dispatches

    async def fan_in(self, dispatches: list[TaskDispatch]) -> str:
        """Collect results from completed dispatches, concatenate them."""
        if self._pool is None:
            return ""
        fragments: list[str] = []
        for td in dispatches:
            result = await self._pool.get_result(td.agent_id)
            if result is not None:
                fragments.append(result)
            await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
        return "\n".join(fragments)

    async def route_next(self) -> list[TaskDispatch]:
        """Match ready tasks to idle agents, one-to-one. Returns dispatches."""
        import time as _tt; _rn0 = _tt.monotonic()
        if self._board is None or self._pool is None:
            return []

        ready = await self._board.get_ready_tasks()
        logger.info("route_next: ready=%d (%.1fs)", len(ready), _tt.monotonic() - _rn0)
        idle = await self._pool.get_idle_agents()
        logger.info("route_next: idle=%d (%.1fs)", len(idle), _tt.monotonic() - _rn0)
        if not ready or not idle:
            return []

        # Skip tasks already being executed or waiting for retry backoff.
        ready = [t for t in ready if t.id not in self._running_tasks]
        ready = [t for t in ready if self._is_retry_window_open(t)]

        dispatches: list[TaskDispatch] = []
        available = list(idle)
        for task in ready:
            agent = self._select_idle_agent(task, available)
            if agent is None:
                break

            # YogaNode constraint check — if wired, filter before dispatch
            if self._yoga is not None:
                checks = self._yoga.can_dispatch(task, agent)
                blocking = [
                    c for c in checks
                    if c.verdict != ConstraintVerdict.ALLOW
                ]
                if blocking:
                    for c in blocking:
                        logger.info(
                            "YogaNode blocked dispatch: task=%s agent=%s "
                            "constraint=%s verdict=%s reason=%s",
                            task.id, agent.id,
                            c.constraint_name, c.verdict.value, c.reason,
                        )
                    continue  # skip this task, try next

            td = TaskDispatch(
                task_id=task.id,
                agent_id=agent.id,
                timeout_seconds=self._resolve_timeout_seconds(
                    task,
                    self._default_timeout_seconds,
                ),
            )
            _ad_t0 = _tt.monotonic()
            await self._assign_dispatch(td)
            logger.info("route_next: assign_dispatch took %.1fs (total %.1fs)", _tt.monotonic() - _ad_t0, _tt.monotonic() - _rn0)

            # Record dispatch in YogaNode usage tracker
            if self._yoga is not None:
                cost = self._yoga.estimate_cost(task)
                self._yoga.record_dispatch(
                    agent_id=agent.id,
                    provider=cost.required_providers[0] if cost.required_providers else None,
                    estimated_tokens=cost.estimated_tokens,
                )

            dispatches.append(td)
        return dispatches

    async def tick(self) -> dict[str, int]:
        """One orchestration cycle: collect completed, then route pending."""
        import time as _tt
        _t0 = _tt.monotonic()

        # Snapshot completed count BEFORE this tick so we can compute delta
        _pre_completed = 0
        try:
            _pre_stats = await self._board.stats()
            _pre_completed = _pre_stats.get("completed", 0)
        except Exception:
            pass

        settled, recovered = await self._collect_completed()
        logger.info("orchestrator.tick: collect=%.1fs", _tt.monotonic() - _t0)
        dispatches = await self.route_next()
        logger.info("orchestrator.tick: dispatched=%d route=%.1fs", len(dispatches), _tt.monotonic() - _t0)
        coordination = self._empty_coordination_summary()
        _since_last_refresh = _tt.monotonic() - self._last_coordination_refresh_at
        if _since_last_refresh >= self._coordination_refresh_interval_s:
            logger.info("orchestrator.tick: entering coordination refresh (%.0fs since last)", _since_last_refresh)
            try:
                coordination = await asyncio.wait_for(
                    self._refresh_coordination_state(), timeout=30.0
                )
                self._last_coordination_refresh_at = _tt.monotonic()
            except asyncio.TimeoutError:
                logger.warning("Coordination refresh timed out after 30s — skipping")
            except Exception as exc:
                logger.warning("Coordination refresh failed: %s", exc)
            logger.info("orchestrator.tick: coordination done")
        else:
            coordination = dict(self._last_coordination_summary)
            logger.info("orchestrator.tick: coordination cached (%.0fs ago)", _since_last_refresh)

        # Compute actual completions from task board delta
        _post_completed = 0
        try:
            _post_stats = await self._board.stats()
            _post_completed = _post_stats.get("completed", 0)
        except Exception:
            pass
        _board_settled = max(0, _post_completed - _pre_completed)
        # Use the larger of asyncio-based and board-based counts
        actual_settled = max(settled, _board_settled)

        summary = {
            "settled": actual_settled,
            "recovered": recovered,
            "dispatched": len(dispatches),
            "coordination_global_truths": int(coordination.get("global_truths", 0) or 0),
            "coordination_disagreements": int(
                coordination.get("productive_disagreements", 0) or 0
            ),
        }

        # Emit a tick-level runtime event when work happened
        if (settled or recovered or dispatches) and self._event_memory is not None:
            try:
                dispatch_ids = [td.task_id for td in dispatches]
                envelope = RuntimeEnvelope.create(
                    event_type=RuntimeEventType.ACTION_EVENT,
                    source="orchestrator.tick",
                    agent_id="orchestrator",
                    session_id=self._ledger.session_id,
                    trace_id=f"tick:{self._ledger.session_id}",
                    payload={
                        "action_name": "tick_summary",
                        "decision": "recorded",
                        "confidence": 1.0,
                        "settled": settled,
                        "recovered": recovered,
                        "dispatched_count": len(dispatches),
                        "dispatched_task_ids": dispatch_ids[:20],
                        "coordination_global_truths": summary["coordination_global_truths"],
                        "coordination_disagreements": summary["coordination_disagreements"],
                    },
                )
                ingest = getattr(self._event_memory, "ingest_envelope", None)
                if ingest:
                    result = ingest(envelope)
                    if inspect.isawaitable(result):
                        await result
            except Exception:
                logger.debug("Tick event emission failed", exc_info=True)

        return summary

    async def tick_settle_only(self) -> dict[str, int]:
        """Settle completed tasks without dispatching new ones.

        Used when the Gnani says HOLD — let in-flight work finish,
        but don't create more.
        """
        settled, recovered = await self._collect_completed()
        return {"settled": settled, "recovered": recovered, "dispatched": 0}

    async def run(self, interval: float = 1.0) -> None:
        """Continuous loop calling tick() until stop() is called."""
        self._running = True
        logger.info("Orchestrator started (interval=%.1fs)", interval)
        try:
            while self._running:
                await self.tick()
                await asyncio.sleep(interval)
        finally:
            self._running = False
            logger.info("Orchestrator stopped")

    def stop(self) -> None:
        """Signal the run loop to exit after the current tick."""
        self._running = False

    async def graceful_stop(self, timeout: float = 30.0) -> dict[str, int]:
        """Cancel all in-flight tasks, gather with timeout, then stop.

        Varela's autopoiesis: clean death is part of the lifecycle.

        Returns a summary of what was cancelled vs completed.
        """
        self._running = False
        cancelled = 0
        completed = 0

        if not self._running_tasks:
            return {"cancelled": 0, "completed": 0}

        # First, cancel all running asyncio tasks
        for task_id, atask in self._running_tasks.items():
            if not atask.done():
                atask.cancel()
                cancelled += 1
            else:
                completed += 1

        # Wait for cancellation to propagate (with timeout)
        if self._running_tasks:
            pending = [t for t in self._running_tasks.values() if not t.done()]
            if pending:
                done, timed_out = await asyncio.wait(
                    pending, timeout=timeout,
                    return_when=asyncio.ALL_COMPLETED,
                )
                # Suppress CancelledError from gathered tasks
                for task in done:
                    try:
                        task.result()
                    except (asyncio.CancelledError, Exception):
                        pass
                for task in timed_out:
                    task.cancel()

        self._running_tasks.clear()
        self._active_dispatches.clear()

        logger.info(
            "Orchestrator graceful stop: %d cancelled, %d already completed",
            cancelled, completed,
        )
        return {"cancelled": cancelled, "completed": completed}

    async def __aenter__(self) -> "Orchestrator":
        """Async context manager support."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Graceful stop on context exit."""
        await self.graceful_stop()

    @property
    def ledger_paths(self) -> dict[str, str]:
        return {
            "session_id": self._ledger.session_id,
            "task_ledger": str(self._ledger.task_path),
            "progress_ledger": str(self._ledger.progress_path),
        }

    # -- internals ---------------------------------------------------------

    def _record_task_event(self, event: str, **payload: Any) -> None:
        self._ledger.task_event(event, **payload)

    def _record_progress_event(self, event: str, **payload: Any) -> None:
        self._ledger.progress_event(event, **payload)

    async def _emit_lifecycle_event(
        self,
        event: str,
        *,
        task_id: str,
        agent_id: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Fire-and-forget lifecycle event — non-blocking to avoid stalling dispatch."""
        asyncio.create_task(
            self._emit_lifecycle_event_impl(event, task_id=task_id, agent_id=agent_id, extra=extra),
            name=f"lifecycle-{event}-{task_id[:8]}",
        )

    async def _emit_lifecycle_event_impl(
        self,
        event: str,
        *,
        task_id: str,
        agent_id: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "event": event,
            "task_id": task_id,
            "agent_id": agent_id,
            **(extra or {}),
        }
        if self._bus is not None:
            publish = getattr(self._bus, "publish", None)
            if publish:
                msg = Message(
                    from_agent="orchestrator",
                    to_agent="*",
                    subject=f"Lifecycle: {event}",
                    body=f"{event} task={task_id} agent={agent_id}",
                    metadata=metadata,
                )
                try:
                    await publish("orchestrator.lifecycle", msg)
                except Exception as exc:
                    logger.debug("Lifecycle publish failed (non-critical): %s", exc)

        if self._event_memory is not None:
            ingest = getattr(self._event_memory, "ingest_envelope", None)
            if ingest:
                envelope = RuntimeEnvelope.create(
                    event_type=RuntimeEventType.ACTION_EVENT,
                    source="orchestrator.lifecycle",
                    agent_id=agent_id,
                    session_id=self._ledger.session_id,
                    trace_id=f"task:{task_id}",
                    payload={
                        "action_name": event,
                        "decision": "recorded",
                        "confidence": 1.0,
                        "task_id": task_id,
                        **metadata,
                    },
                )
                try:
                    result = ingest(envelope)
                    if inspect.isawaitable(result):
                        await result
                except Exception as exc:
                    logger.debug(
                        "Lifecycle event ingestion failed (non-critical): %s", exc
                    )

    @staticmethod
    def _failure_signature(error: str) -> str:
        base = (error or "").strip().splitlines()[0] if error else "unknown_error"
        lowered = base.lower()
        lowered = re.sub(r"[0-9a-f]{12,}", "<id>", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered[:200]

    @staticmethod
    def _is_transient_connection_failure(signature: str) -> bool:
        patterns = (
            "connection error",
            "api connection error",
            "connecterror",
            "nodename nor servname provided",
            "temporary failure in name resolution",
            "dns",
            "service unavailable",
            "server disconnected",
            "timeout while reading provider stream",
            "rate limit",
            "429",
            "too many requests",
        )
        return any(pattern in signature for pattern in patterns)

    def _classify_failure(
        self,
        *,
        error: str,
        source: str,
        task: Task | None,
    ) -> str:
        signature = self._failure_signature(error)
        if source in {"claim_timeout", "dispatch_dropoff"}:
            return source
        if source == "timeout":
            timeout_seconds = self._resolve_timeout_seconds(task, self._default_timeout_seconds)
            if timeout_seconds >= self._long_timeout_retry_threshold_seconds:
                return "long_timeout"
            return "timeout"
        if source == "execution_error" and self._is_transient_connection_failure(signature):
            return "connection_transient"
        return source

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _task_meta(task: Task | None) -> dict[str, Any]:
        if task is None or not isinstance(task.metadata, dict):
            return {}
        return dict(task.metadata)

    def _resolve_timeout_seconds(self, task: Task | None, fallback: float) -> float:
        meta = self._task_meta(task)
        raw = (
            meta.get("timeout_seconds")
            or meta.get("run_timeout_seconds")
            or meta.get("task_timeout_seconds")
        )
        timeout = self._coerce_float(raw, fallback if fallback > 0 else self._default_timeout_seconds)
        return max(0.01, timeout)

    def _resolve_claim_timeout_seconds(self, task: Task | None, run_timeout_seconds: float) -> float:
        meta = self._task_meta(task)
        raw = meta.get("claim_timeout_seconds")
        computed = max(self._default_claim_timeout_seconds, run_timeout_seconds + 30.0)
        claim_timeout = self._coerce_float(raw, computed)
        return max(run_timeout_seconds + 5.0, claim_timeout)

    def _resolve_retry_policy(self, task: Task | None) -> tuple[int, int, float]:
        meta = self._task_meta(task)
        retry_count = max(0, self._coerce_int(meta.get("retry_count"), 0))
        max_retries = max(
            0,
            self._coerce_int(meta.get("max_retries"), self._default_max_retries),
        )
        backoff = max(
            0.0,
            self._coerce_float(
                meta.get("retry_backoff_seconds"),
                self._default_retry_backoff_seconds,
            ),
        )
        return retry_count, max_retries, backoff

    def _apply_failure_retry_defaults(
        self,
        *,
        task: Task | None,
        meta: dict[str, Any],
        failure_class: str,
        max_retries: int,
        backoff: float,
    ) -> tuple[int, float]:
        if failure_class in {"claim_timeout", "dispatch_dropoff"}:
            return (max(max_retries, 1), backoff)
        if failure_class == "connection_transient":
            updated_max = max(max_retries, self._transient_failure_retry_limit)
            updated_backoff = max(backoff, self._transient_failure_backoff_seconds)
            meta["retry_backoff_seconds"] = updated_backoff
            return (updated_max, updated_backoff)
        if failure_class == "long_timeout":
            updated_max = max(max_retries, self._long_timeout_retry_limit)
            updated_backoff = max(backoff, self._long_timeout_backoff_seconds)
            current_timeout = self._resolve_timeout_seconds(task, self._default_timeout_seconds)
            grown_timeout = min(
                max(
                    current_timeout * self._timeout_retry_growth_factor,
                    current_timeout + 60.0,
                ),
                self._max_timeout_retry_seconds,
            )
            meta["timeout_seconds"] = round(grown_timeout, 3)
            meta["retry_backoff_seconds"] = updated_backoff
            meta["timeout_retry_growth_applied"] = round(grown_timeout, 3)
            return (updated_max, updated_backoff)
        return (max_retries, backoff)

    def _is_retry_window_open(self, task: Task) -> bool:
        meta = self._task_meta(task)
        not_before_raw = meta.get("retry_not_before_epoch")
        if not_before_raw is None:
            return True
        not_before = self._coerce_float(not_before_raw, 0.0)
        return time.time() >= not_before

    def _prepare_claim(self, task: Task | None, td: TaskDispatch) -> dict[str, Any]:
        meta = self._task_meta(task)
        retry_count, max_retries, _ = self._resolve_retry_policy(task)
        td.timeout_seconds = self._resolve_timeout_seconds(task, td.timeout_seconds)
        claim_timeout_seconds = self._resolve_claim_timeout_seconds(task, td.timeout_seconds)
        claim_id = _new_id()
        now_epoch = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        claim = {
            "claim_id": claim_id,
            "agent_id": td.agent_id,
            "claimed_at": now_iso,
            "claimed_at_epoch": now_epoch,
            "claim_timeout_seconds": claim_timeout_seconds,
            "claim_expires_at_epoch": now_epoch + claim_timeout_seconds,
            "dispatch_timeout_seconds": td.timeout_seconds,
            "dispatch_attempt": retry_count + 1,
        }
        meta.update(
            {
                "retry_count": retry_count,
                "max_retries": max_retries,
                "last_claim": claim,
                "active_claim": claim,
            }
        )
        td.metadata["claim_id"] = claim_id
        td.metadata["claim_timeout_seconds"] = claim_timeout_seconds
        td.metadata["claim_expires_monotonic"] = time.monotonic() + claim_timeout_seconds
        td.metadata["retry_count"] = retry_count
        td.metadata["max_retries"] = max_retries
        return meta

    def _memory_plane_db_path(self, task: Task | None) -> Path | None:
        meta = self._task_meta(task)
        raw = meta.get("memory_plane_db")
        if isinstance(raw, str) and raw.strip():
            return Path(raw)
        event_path = getattr(self._event_memory, "db_path", None)
        if event_path:
            return Path(event_path)
        return None

    def _latent_gold_query(self, task: Task | None) -> str:
        if task is None:
            return ""
        return "\n".join(
            part.strip()
            for part in (task.title, task.description)
            if isinstance(part, str) and part.strip()
        )

    def _attach_latent_gold(self, task: Task | None, meta: dict[str, Any]) -> dict[str, Any]:
        plane_path = self._memory_plane_db_path(task)
        query = self._latent_gold_query(task)
        if task is None or plane_path is None or not query:
            return meta
        try:
            from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

            shards = ConversationMemoryStore(plane_path).latent_gold(query, limit=3)
        except Exception as exc:
            logger.debug("Latent gold lookup failed for %s: %s", getattr(task, "id", "?"), exc)
            return meta
        if not shards:
            meta.pop("latent_gold", None)
            meta["latent_gold_count"] = 0
            return meta

        meta["latent_gold"] = [
            {
                "shard_id": shard.shard_id,
                "kind": shard.shard_kind,
                "state": shard.state,
                "salience": round(float(shard.salience), 6),
                "text": shard.text[:220],
                "created_at": shard.created_at.isoformat(),
            }
            for shard in shards
        ]
        meta["latent_gold_count"] = len(shards)
        meta["latent_gold_query"] = query[:280]
        meta["latent_gold_refreshed_at"] = datetime.now(timezone.utc).isoformat()
        return meta

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @staticmethod
    def _coerce_string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            values = [part.strip() for part in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            values = [str(part).strip() for part in value]
        else:
            return []
        return [item for item in values if item]

    def _task_preferred_roles(self, task: Task | None) -> list[str]:
        meta = self._task_meta(task)
        raw = meta.get("coordination_preferred_roles")
        if raw is None:
            raw = meta.get("preferred_roles")
        roles = self._dedupe_strings(
            [role.lower() for role in self._coerce_string_list(raw)]
        )
        if roles:
            return roles
        if (
            str(meta.get("coordination_route", "")).strip().lower()
            == "synthesis_review"
            or bool(meta.get("coordination_review_required"))
        ):
            return ["reviewer", "researcher", "general"]
        return []

    def _task_preferred_agent_names(self, task: Task | None) -> list[str]:
        meta = self._task_meta(task)
        raw = meta.get("director_preferred_agents")
        if raw is None:
            raw = meta.get("preferred_agents")
        return self._dedupe_strings(self._coerce_string_list(raw))

    _EXPLORATION_RATE = 0.1  # 10% random exploration

    def _select_idle_agent(
        self,
        task: Task | None,
        idle_agents: list[AgentState],
    ) -> AgentState | None:
        if not idle_agents:
            return None

        preferred_names = self._task_preferred_agent_names(task)
        preferred_roles = self._task_preferred_roles(task)

        # Prefer exact agent-name routing when the task already knows its seats.
        name_matched: list[AgentState] = []
        if preferred_names:
            seen: set[str] = set()
            for preferred_name in preferred_names:
                wanted = preferred_name.strip()
                if not wanted:
                    continue
                for agent in idle_agents:
                    if agent.name != wanted or agent.id in seen:
                        continue
                    name_matched.append(agent)
                    seen.add(agent.id)
                    break

        # Collect ALL role-matched candidates (not just first match)
        role_matched: list[AgentState] = []
        for agent in idle_agents:
            role_value = str(getattr(agent.role, "value", agent.role)).lower()
            if any(role_value == p for p in preferred_roles):
                role_matched.append(agent)

        # Pick from name-matched subset first, then role-matched subset, else all candidates.
        candidates = name_matched or role_matched or list(idle_agents)

        # Active inference EFE-based selection (Friston P10)
        best = self._efe_biased_pick(candidates, task)
        if best is not None:
            idle_agents.remove(best)
            return best

        # Fitness-biased selection (feature-flagged, best-effort)
        best = self._fitness_biased_pick(candidates, task)
        if best is not None:
            idle_agents.remove(best)
            return best

        # FIFO fallback (original behavior)
        if name_matched:
            pick = name_matched[0]
            idle_agents.remove(pick)
            return pick
        if role_matched:
            pick = role_matched[0]
            idle_agents.remove(pick)
            return pick
        return idle_agents.pop(0)

    def _efe_biased_pick(
        self,
        candidates: list[AgentState],
        task: Task | None,
    ) -> AgentState | None:
        """Expected Free Energy routing — Friston P10 embodiment.

        Routes tasks to agents that minimize expected surprise (Risk + Ambiguity).
        Feature-flagged via ENABLE_EFE_ROUTING env var.
        """
        if len(candidates) <= 1:
            return candidates[0] if candidates else None

        import os
        if os.getenv("ENABLE_EFE_ROUTING", "").lower() not in ("1", "true", "yes"):
            return None  # Falls through to fitness-biased or FIFO

        try:
            from dharma_swarm.active_inference import get_engine
            engine = get_engine()
            task_meta = task.metadata if task and isinstance(task.metadata, dict) else {}
            task_type = str(task_meta.get("task_type", "general") or "general")

            scored: list[tuple[float, AgentState]] = []
            for agent in candidates:
                efe = engine.expected_free_energy(agent.id, task_type)
                scored.append((efe, agent))

            # Sort ascending: lower EFE = better match
            scored.sort(key=lambda x: x[0])
            logger.debug(
                "EFE routing: %s",
                [(round(s, 3), a.id) for s, a in scored[:3]],
            )
            return scored[0][1]
        except Exception:
            logger.debug("EFE routing failed", exc_info=True)
            return None

    def _fitness_biased_pick(
        self,
        candidates: list[AgentState],
        task: Task | None,
    ) -> AgentState | None:
        """Fitness-biased agent selection with Bayesian smoothing and exploration."""
        if len(candidates) <= 1:
            return candidates[0] if candidates else None

        # Feature flag: ENABLE_FITNESS_ROUTING (default off until enough data)
        import os
        if os.getenv("ENABLE_FITNESS_ROUTING", "").lower() not in ("1", "true", "yes"):
            return None  # Falls through to FIFO

        try:
            import random
            seam = self._telic_seam
            if seam is None:
                return None

            # Exploration: 10% of the time, pick randomly
            if random.random() < self._EXPLORATION_RATE:
                return random.choice(candidates)

            task_meta = task.metadata if task and isinstance(task.metadata, dict) else {}
            task_type = task_meta.get("task_type", "")
            cell_id = task_meta.get("cell_id", "")

            scored: list[tuple[float, int, AgentState]] = []
            for agent in candidates:
                score, n = seam.query_agent_fitness(
                    agent.id, cell_id=cell_id, task_type=task_type,
                )
                scored.append((score, n, agent))

            # Sort by score descending, then sample count descending
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return scored[0][2]
        except Exception:
            return None  # Falls through to FIFO

    @staticmethod
    def _empty_coordination_summary() -> dict[str, Any]:
        return {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "agent_count": 0,
            "message_count": 0,
            "task_count": 0,
            "overlap_pairs": 0,
            "published_agents": [],
            "global_truths": 0,
            "productive_disagreements": 0,
            "cohomological_dimension": 0,
            "is_globally_coherent": True,
            "global_truth_claim_keys": [],
            "productive_disagreement_claim_keys": [],
        }

    @classmethod
    def _merge_coordination_context(
        cls,
        existing: Any,
        additions: list[str],
    ) -> list[str]:
        base = cls._coerce_string_list(existing)
        return cls._dedupe_strings([*base, *additions])

    @classmethod
    def _coordination_signature_payload(cls, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_count": int(summary.get("agent_count", 0) or 0),
            "message_count": int(summary.get("message_count", 0) or 0),
            "task_count": int(summary.get("task_count", 0) or 0),
            "overlap_pairs": int(summary.get("overlap_pairs", 0) or 0),
            "published_agents": cls._dedupe_strings(
                list(summary.get("published_agents", []))
            ),
            "global_truths": int(summary.get("global_truths", 0) or 0),
            "productive_disagreements": int(
                summary.get("productive_disagreements", 0) or 0
            ),
            "cohomological_dimension": int(
                summary.get("cohomological_dimension", 0) or 0
            ),
            "is_globally_coherent": bool(
                summary.get("is_globally_coherent", True)
            ),
            "global_truth_claim_keys": cls._dedupe_strings(
                list(summary.get("global_truth_claim_keys", []))
            ),
            "productive_disagreement_claim_keys": cls._dedupe_strings(
                list(summary.get("productive_disagreement_claim_keys", []))
            ),
        }

    @staticmethod
    def _coordination_confidence(value: Any, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return max(0.0, min(1.0, float(default)))

    async def _list_coordination_agents(self) -> list[AgentState]:
        if self._pool is None:
            return []
        list_agents = getattr(self._pool, "list_agents", None)
        if list_agents:
            result = list_agents()
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, list):
                return [agent for agent in result if isinstance(agent, AgentState)]
        idle_agents = await self._pool.get_idle_agents()
        return [agent for agent in idle_agents if isinstance(agent, AgentState)]

    async def _list_coordination_tasks(self) -> list[Task]:
        if self._board is None:
            return []
        list_tasks = getattr(self._board, "list_tasks", None)
        if list_tasks:
            try:
                result = list_tasks(limit=200)
            except TypeError:
                result = list_tasks()
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, list):
                return [task for task in result if isinstance(task, Task)]
        task_items = getattr(self._board, "tasks", None)
        if isinstance(task_items, list):
            # Read-only for coordination analysis — skip expensive deep copy
            return [task for task in task_items if isinstance(task, Task)][:200]
        return []

    async def _list_coordination_messages(self, *, limit: int = 200) -> list[Message]:
        if self._bus is None:
            return []

        list_messages = getattr(self._bus, "list_messages", None)
        if list_messages:
            result = list_messages(limit=limit)
            if inspect.isawaitable(result):
                result = await result
            messages = result if isinstance(result, list) else []
        else:
            messages = []
            sent = getattr(self._bus, "sent", None)
            if isinstance(sent, list):
                messages.extend(
                    message
                    for message in sent
                    if isinstance(message, Message)
                )
            published = getattr(self._bus, "published", None)
            if isinstance(published, list):
                messages.extend(
                    message
                    for _, message in published
                    if isinstance(message, Message)
                )

        unique: dict[str, Message] = {}
        for message in messages:
            if isinstance(message, Message):
                unique[message.id] = message
        return sorted(unique.values(), key=lambda message: message.created_at)

    @classmethod
    def _coordination_claim_key_from_message(cls, message: Message) -> str:
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        for key in ("coordination_claim_key", "claim_key", "topic"):
            value = str(metadata.get(key, "")).strip()
            if value:
                return value
        if message.subject and message.subject.strip():
            return message.subject.strip()
        body = (message.body or "").strip()
        return body[:120] if body else message.id

    @classmethod
    def _coordination_claim_key_from_task(cls, task: Task) -> str:
        metadata = cls._task_meta(task)
        for key in (
            "coordination_claim_key",
            "claim_key",
            "coordination_topic",
            "topic",
            "parent_task",
            "task_group",
        ):
            value = str(metadata.get(key, "")).strip()
            if value:
                return value
        title = (task.title or "").strip()
        return title or task.id

    @classmethod
    def _coordination_task_agent_id(cls, task: Task) -> str:
        metadata = cls._task_meta(task)
        for key in ("coordination_agent_id", "assigned_agent_id", "last_agent_id"):
            value = str(metadata.get(key, "")).strip()
            if value:
                return value
        return str(task.assigned_to or "").strip()

    @classmethod
    def _coordination_task_metadata(
        cls,
        task: Task,
        summary: dict[str, Any],
    ) -> dict[str, Any] | None:
        claim_key = cls._coordination_claim_key_from_task(task)
        if not claim_key:
            return None

        meta = cls._task_meta(task)
        updated = dict(meta)
        changed = False

        def assign(key: str, value: Any) -> None:
            nonlocal changed
            if updated.get(key) != value:
                updated[key] = value
                changed = True

        def remove(key: str) -> None:
            nonlocal changed
            if key in updated:
                updated.pop(key, None)
                changed = True

        assign("coordination_claim_key", claim_key)
        if not str(updated.get("coordination_topic", "")).strip():
            assign("coordination_topic", claim_key)

        global_truths = set(summary.get("global_truth_claim_keys", []))
        disagreements = set(summary.get("productive_disagreement_claim_keys", []))

        if claim_key in global_truths:
            assign("coordination_state", "coherent")
            assign(
                "coordination_uncertainty",
                min(
                    cls._coordination_confidence(
                        updated.get("coordination_uncertainty"),
                        1.0,
                    ),
                    0.15,
                ),
            )
            assign("coordination_global_truth", True)
            assign("coordination_review_required", False)
            assign("coordination_route", "default")
            assign(
                "coordination_shared_context",
                cls._merge_coordination_context(
                    updated.get("coordination_shared_context"),
                    [f"Global truth established for claim '{claim_key}'."],
                ),
            )
            remove("coordination_preferred_roles")
        elif claim_key in disagreements:
            assign("coordination_state", "uncertain")
            assign(
                "coordination_uncertainty",
                max(
                    cls._coordination_confidence(
                        updated.get("coordination_uncertainty"),
                        0.0,
                    ),
                    0.85,
                ),
            )
            assign("coordination_global_truth", False)
            assign("coordination_review_required", True)
            assign("coordination_route", "synthesis_review")
            assign(
                "coordination_preferred_roles",
                ["reviewer", "researcher", "general"],
            )
            assign(
                "coordination_shared_context",
                cls._merge_coordination_context(
                    updated.get("coordination_shared_context"),
                    [
                        (
                            f"Productive disagreement detected for claim '{claim_key}'. "
                            "Prefer synthesis and review over unilateral execution."
                        )
                    ],
                ),
            )
        else:
            return None

        if changed:
            updated["coordination_last_observed_at"] = str(
                summary.get("observed_at", datetime.now(timezone.utc).isoformat())
            )
            return updated
        return None

    async def _apply_coordination_task_policy(
        self,
        tasks: list[Task],
        summary: dict[str, Any],
    ) -> int:
        updated_tasks = 0
        for task in tasks:
            if task.status not in {
                TaskStatus.PENDING,
                TaskStatus.ASSIGNED,
                TaskStatus.RUNNING,
            }:
                continue
            metadata = self._coordination_task_metadata(task, summary)
            if metadata is None:
                continue
            await self._safe_update_task(task.id, metadata=metadata)
            updated_tasks += 1

        if updated_tasks:
            self._record_progress_event(
                "coordination_task_policy",
                updated_tasks=updated_tasks,
                global_truth_claim_keys=self._dedupe_strings(
                    list(summary.get("global_truth_claim_keys", []))
                ),
                productive_disagreement_claim_keys=self._dedupe_strings(
                    list(summary.get("productive_disagreement_claim_keys", []))
                ),
            )
        return updated_tasks

    @classmethod
    def _task_discovery(
        cls,
        task: Task,
        *,
        agent_ids: set[str],
    ) -> Discovery | None:
        agent_id = cls._coordination_task_agent_id(task)
        if not agent_id or agent_id not in agent_ids:
            return None
        metadata = cls._task_meta(task)
        content = str(
            metadata.get("coordination_content")
            or task.result
            or task.description
            or task.title
        ).strip()
        if not content:
            return None
        confidence_by_status = {
            TaskStatus.PENDING: 0.45,
            TaskStatus.ASSIGNED: 0.55,
            TaskStatus.RUNNING: 0.70,
            TaskStatus.COMPLETED: 0.95,
            TaskStatus.FAILED: 0.35,
            TaskStatus.CANCELLED: 0.25,
        }
        return Discovery(
            agent_id=agent_id,
            claim_key=cls._coordination_claim_key_from_task(task),
            content=content,
            confidence=cls._coordination_confidence(
                metadata.get("coordination_confidence"),
                confidence_by_status.get(task.status, 0.50),
            ),
            evidence=[f"task:{task.id}"],
            perspective=f"task:{task.status.value}",
            metadata={
                "source": "task_board",
                "task_id": task.id,
                "task_status": task.status.value,
            },
        )

    @classmethod
    def _message_discovery(
        cls,
        message: Message,
        *,
        agent_ids: set[str],
    ) -> Discovery | None:
        if message.from_agent not in agent_ids or message.to_agent not in agent_ids:
            return None
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        content = str(message.body or message.subject or "").strip()
        if not content:
            return None
        return Discovery(
            agent_id=message.from_agent,
            claim_key=cls._coordination_claim_key_from_message(message),
            content=content,
            confidence=cls._coordination_confidence(
                metadata.get("confidence"),
                0.65,
            ),
            evidence=[message.id],
            perspective=f"message:{message.from_agent}->{message.to_agent}",
            metadata={
                "source": "message_bus",
                "message_id": message.id,
                "topic": str(metadata.get("topic", "")).strip(),
                "subject": str(message.subject or ""),
            },
        )

    @classmethod
    def _task_overlap_channels(
        cls,
        tasks: list[Task],
        *,
        agent_ids: set[str],
    ) -> dict[tuple[str, str], InformationChannel]:
        claim_participants: dict[str, set[str]] = {}
        for task in tasks:
            agent_id = cls._coordination_task_agent_id(task)
            if not agent_id or agent_id not in agent_ids:
                continue
            claim_key = cls._coordination_claim_key_from_task(task)
            claim_participants.setdefault(claim_key, set()).add(agent_id)

        channels: dict[tuple[str, str], InformationChannel] = {}
        for claim_key, participants in claim_participants.items():
            if len(participants) < 2:
                continue
            for left, right in combinations(sorted(participants), 2):
                for source, target in ((left, right), (right, left)):
                    key = (source, target)
                    existing = channels.get(key)
                    if existing is None:
                        existing = InformationChannel(
                            source_agent=source,
                            target_agent=target,
                            weight=0.0,
                            metadata={
                                "source": "task_overlap",
                                "claim_keys": [],
                            },
                        )
                        channels[key] = existing
                    existing.weight += 1.0
                    existing.topics = cls._dedupe_strings(
                        [*existing.topics, claim_key]
                    )
                    claim_keys = existing.metadata.setdefault("claim_keys", [])
                    if isinstance(claim_keys, list):
                        existing.metadata["claim_keys"] = cls._dedupe_strings(
                            [*claim_keys, claim_key]
                        )
        return channels

    @classmethod
    def _merge_coordination_channels(
        cls,
        base: dict[tuple[str, str], InformationChannel],
        extra: dict[tuple[str, str], InformationChannel],
    ) -> dict[tuple[str, str], InformationChannel]:
        merged = {
            key: channel.model_copy(deep=True)
            for key, channel in base.items()
        }
        for key, channel in extra.items():
            existing = merged.get(key)
            if existing is None:
                merged[key] = channel.model_copy(deep=True)
                continue
            existing.topics = cls._dedupe_strings([*existing.topics, *channel.topics])
            existing.message_ids = cls._dedupe_strings(
                [*existing.message_ids, *channel.message_ids]
            )
            existing.weight = float(existing.weight) + float(channel.weight)
            existing.metadata["coordination_sources"] = cls._dedupe_strings(
                [
                    str(existing.metadata.get("source", "")).strip(),
                    str(channel.metadata.get("source", "")).strip(),
                    *list(existing.metadata.get("coordination_sources", [])),
                ]
            )
            existing.metadata["claim_keys"] = cls._dedupe_strings(
                [
                    *list(existing.metadata.get("claim_keys", [])),
                    *list(channel.metadata.get("claim_keys", [])),
                ]
            )
        return merged

    async def _refresh_coordination_state(self) -> dict[str, Any]:
        import time as _t; _cs_t0 = _t.monotonic()
        logger.info("_refresh_coordination: entering")
        agents = await self._list_coordination_agents()
        logger.info("_refresh_coordination: agents=%.1fs (n=%d)", _t.monotonic() - _cs_t0, len(agents))
        tasks = await self._list_coordination_tasks()
        logger.info("_refresh_coordination: tasks=%.1fs", _t.monotonic() - _cs_t0)
        messages = await self._list_coordination_messages(limit=200)
        logger.info("_refresh_coordination: messages=%.1fs (n=%d)", _t.monotonic() - _cs_t0, len(messages))
        agent_ids = {agent.id for agent in agents}

        relevant_messages = [
            message
            for message in messages
            if message.from_agent in agent_ids and message.to_agent in agent_ids
        ]
        base_site = NoosphereSite.from_messages(agents, relevant_messages)
        channels = self._merge_coordination_channels(
            base_site.channels,
            self._task_overlap_channels(tasks, agent_ids=agent_ids),
        )
        site = NoosphereSite(agents, channels=channels)
        protocol = CoordinationProtocol(site)

        for message in relevant_messages:
            discovery = self._message_discovery(message, agent_ids=agent_ids)
            if discovery is not None:
                protocol.publish(discovery.agent_id, [discovery])
        for task in tasks:
            discovery = self._task_discovery(task, agent_ids=agent_ids)
            if discovery is not None:
                protocol.publish(discovery.agent_id, [discovery])

        logger.info("_refresh_coordination: sheaf_compute=%.1fs", _t.monotonic() - _cs_t0)
        result = protocol.coordinate()
        logger.info("_refresh_coordination: coordinate_done=%.1fs", _t.monotonic() - _cs_t0)
        self._last_coordination_result = result.model_copy(deep=True)
        summary = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "agent_count": len(agents),
            "message_count": len(relevant_messages),
            "task_count": len(tasks),
            "overlap_pairs": len(site.overlap_pairs()),
            "published_agents": self._dedupe_strings(
                list(result.descent_data.published_agents)
            ),
            "global_truths": len(result.global_truths),
            "productive_disagreements": len(result.productive_disagreements),
            "cohomological_dimension": result.cohomological_dimension,
            "is_globally_coherent": result.is_globally_coherent,
            "global_truth_claim_keys": self._dedupe_strings(
                [
                    discovery.claim_key or discovery.canonical_claim_key
                    for discovery in result.global_truths
                ]
            ),
            "productive_disagreement_claim_keys": self._dedupe_strings(
                [
                    obstruction.claim_key
                    for obstruction in result.productive_disagreements
                ]
            ),
        }
        summary["policy_tasks_updated"] = await self._apply_coordination_task_policy(
            tasks,
            summary,
        )
        signature_payload = self._coordination_signature_payload(summary)
        signature = json.dumps(
            signature_payload,
            ensure_ascii=True,
            sort_keys=True,
        )
        if signature != self._last_coordination_signature:
            self._record_progress_event(
                "coordination_snapshot",
                **signature_payload,
            )
            if summary["productive_disagreements"] > 0:
                self._record_progress_event(
                    "coordination_disagreement",
                    productive_disagreements=summary["productive_disagreements"],
                    claim_keys=summary["productive_disagreement_claim_keys"],
                )
            self._last_coordination_signature = signature
        self._last_coordination_summary = dict(summary)
        logger.info("_refresh_coordination: total=%.1fs", _t.monotonic() - _cs_t0)
        return dict(summary)

    async def get_coordination_summary(self, *, refresh: bool = True) -> dict[str, Any]:
        if refresh:
            return await self._refresh_coordination_state()
        return dict(self._last_coordination_summary)

    async def _safe_get_task(self, task_id: str) -> Task | None:
        board_get = getattr(self._board, "get", None)
        if not board_get:
            return None
        try:
            return await board_get(task_id)
        except Exception:
            return None

    async def _safe_update_task(self, task_id: str, **fields: Any) -> None:
        if self._board is None:
            return
        try:
            await self._board.update_task(task_id, **fields)
        except Exception as exc:
            logger.warning("Task board update failed for %s: %s", task_id, exc)

    async def _handle_task_failure(
        self,
        *,
        td: TaskDispatch,
        task: Task | None,
        error: str,
        source: str,
    ) -> None:
        # Release YogaNode capacity on failure too
        if self._yoga is not None:
            self._yoga.record_completion(td.agent_id)
        failure_signature = self._failure_signature(error)
        retry_count, max_retries, backoff = self._resolve_retry_policy(task)
        meta = self._task_meta(task)
        failure_class = self._classify_failure(error=error, source=source, task=task)
        max_retries, backoff = self._apply_failure_retry_defaults(
            task=task,
            meta=meta,
            failure_class=failure_class,
            max_retries=max_retries,
            backoff=backoff,
        )
        meta.pop("active_claim", None)
        meta["last_error"] = error
        meta["last_failure_class"] = failure_class
        meta["last_failure_signature"] = failure_signature
        meta["last_failure_source"] = source
        meta["last_failed_agent"] = td.agent_id
        meta["last_failed_at"] = datetime.now(timezone.utc).isoformat()

        retry_scheduled = retry_count < max_retries
        if retry_scheduled:
            next_retry = retry_count + 1
            meta["retry_count"] = next_retry
            meta["max_retries"] = max_retries
            if backoff > 0:
                meta["retry_not_before_epoch"] = time.time() + backoff
            else:
                meta.pop("retry_not_before_epoch", None)

            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.FAILED,
                result=error,
                metadata=meta,
            )
            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.PENDING,
                result=error,
                metadata=meta,
                assigned_to=None,
            )
            self._record_task_event(
                "task_requeued",
                task_id=td.task_id,
                agent_id=td.agent_id,
                retry_count=next_retry,
                max_retries=max_retries,
                source=source,
                failure_class=failure_class,
                failure_signature=failure_signature,
            )
            self._record_progress_event(
                "task_retry_scheduled",
                task_id=td.task_id,
                agent_id=td.agent_id,
                retry_count=next_retry,
                max_retries=max_retries,
                source=source,
                failure_class=failure_class,
                failure_signature=failure_signature,
            )
            await self._emit_lifecycle_event(
                "task_retry_scheduled",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={
                    "retry_count": next_retry,
                    "max_retries": max_retries,
                    "source": source,
                    "failure_class": failure_class,
                },
            )
            return

        meta["max_retries"] = max_retries
        await self._safe_update_task(
            td.task_id,
            status=TaskStatus.FAILED,
            result=error,
            metadata=meta,
        )
        self._record_progress_event(
            "task_failed",
            task_id=td.task_id,
            agent_id=td.agent_id,
            failure_signature=failure_signature,
            error=error,
            source=source,
            failure_class=failure_class,
            retry_count=retry_count,
            max_retries=max_retries,
        )
        await self._emit_lifecycle_event(
            "task_failed",
            task_id=td.task_id,
            agent_id=td.agent_id,
            extra={
                "failure_signature": failure_signature,
                "source": source,
                "failure_class": failure_class,
                "retry_count": retry_count,
                "max_retries": max_retries,
            },
        )
        # ── Algedonic signal: task exhausted all retries → pain to S5 ──
        try:
            from dharma_swarm.signal_bus import SignalBus
            task_title = task.title[:100] if task else td.task_id
            SignalBus.get().emit({
                "type": "ALGEDONIC_TASK_DEAD",
                "severity": "warning",
                "task_id": td.task_id,
                "task_title": task_title,
                "agent_id": td.agent_id,
                "failure_class": failure_class,
                "retry_count": retry_count,
                "max_retries": max_retries,
                "error": error[:300],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # Also persist to algedonic log (S5 bypass)
            _alg_path = Path.home() / ".dharma" / "algedonic_signals.jsonl"
            _alg_path.parent.mkdir(parents=True, exist_ok=True)
            with _alg_path.open("a", encoding="utf-8") as _af:
                _af.write(json.dumps({
                    "kind": "task_retries_exhausted",
                    "severity": "warning",
                    "value": retry_count,
                    "action": f"dead-letter: {task_title}",
                    "timestamp": time.time(),
                }) + "\n")
            logger.warning(
                "ALGEDONIC: task %s exhausted %d retries — dead-lettered",
                td.task_id, max_retries,
            )
        except Exception:
            logger.debug("Algedonic signal emission failed", exc_info=True)

    async def _assign_dispatch(self, td: TaskDispatch) -> None:
        """Record dispatch, update board + pool, kick off execution, notify via bus."""
        import time as _adt; _ad0 = _adt.monotonic()
        td.metadata["dispatch_started_monotonic"] = time.monotonic()
        task_for_gate = await self._safe_get_task(td.task_id)
        logger.info("_assign_dispatch(%s): get_task=%.2fs", td.task_id[:8], _adt.monotonic() - _ad0)

        # ── Telic Seam: record ActionProposal in ontology ──
        proposal_id: str | None = None
        if task_for_gate is not None:
            try:
                if self._telic_seam is not None:
                    proposal_id = self._telic_seam.record_dispatch(
                        task_for_gate,
                        td.agent_id,
                        topology=td.topology.value if td.topology else "dispatch",
                    )
                    td.metadata["telic_proposal_id"] = proposal_id or ""
            except Exception:
                logger.debug("Telic seam dispatch recording failed", exc_info=True)

        action_ref = (
            f"dispatch task {task_for_gate.title} -> {td.agent_id}"
            if task_for_gate
            else f"dispatch task {td.task_id} -> {td.agent_id}"
        )
        content_ref = task_for_gate.description if task_for_gate else ""
        _gate_t0 = _adt.monotonic()
        gate = check_with_reflective_reroute(
            action=action_ref,
            content=content_ref,
            tool_name="orchestrator_dispatch",
            think_phase="before_write",
            reflection=(
                f"Dispatching task {td.task_id} to agent {td.agent_id}. "
                "Keep scope bounded and reversible."
            ),
            max_reroutes=1,
            requirement_refs=[f"task:{td.task_id}", f"agent:{td.agent_id}"],
        )
        logger.info("_assign_dispatch(%s): gate=%.2fs total=%.2fs", td.task_id[:8], _adt.monotonic() - _gate_t0, _adt.monotonic() - _ad0)

        # Yield after sync gate check so other coroutines can progress
        await asyncio.sleep(0)

        # ── Telic Seam: record GateDecision in ontology ──
        if proposal_id is not None:
            try:
                if self._telic_seam is not None:
                    self._telic_seam.record_gate_decision(
                        proposal_id,
                        gate.result,
                        witness_reroutes=gate.attempts,
                    )
            except Exception:
                logger.debug("Telic seam gate decision recording failed", exc_info=True)

        if gate.result.decision.value == "block":
            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.FAILED,
                result=f"TELOS BLOCK (dispatch): {gate.result.reason}",
            )
            self._record_task_event(
                "dispatch_blocked",
                task_id=td.task_id,
                agent_id=td.agent_id,
                topology=td.topology.value,
                reason=gate.result.reason,
            )
            self._record_progress_event(
                "task_blocked",
                task_id=td.task_id,
                agent_id=td.agent_id,
                failure_signature=self._failure_signature(gate.result.reason),
                source="telos_gate",
            )
            await self._emit_lifecycle_event(
                "dispatch_blocked",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={"reason": gate.result.reason},
            )
            logger.warning(
                "Dispatch blocked for task %s -> %s: %s",
                td.task_id,
                td.agent_id,
                gate.result.reason,
            )
            return

        if gate.attempts:
            td.metadata["witness_reroutes"] = gate.attempts

        claim_meta = self._prepare_claim(task_for_gate, td)
        claim_meta = self._attach_latent_gold(task_for_gate, claim_meta)
        if task_for_gate is not None:
            task_for_gate.metadata = dict(claim_meta)
        if proposal_id is not None:
            try:
                if self._telic_seam is not None:
                    self._telic_seam.record_execution_lease(
                        proposal_id,
                        claim_meta.get("active_claim"),
                    )
            except Exception:
                logger.debug("Telic seam execution lease recording failed", exc_info=True)

        _pe_t0 = _adt.monotonic()
        if self._pool is not None:
            await self._pool.assign(td.agent_id, td.task_id)
        logger.info("_assign_dispatch(%s): pool_assign=%.2fs", td.task_id[:8], _adt.monotonic() - _pe_t0)
        _pe_t1 = _adt.monotonic()
        await self._safe_update_task(
            td.task_id,
            status=TaskStatus.ASSIGNED,
            assigned_to=td.agent_id,
            metadata=claim_meta,
        )
        logger.info("_assign_dispatch(%s): update_task=%.2fs", td.task_id[:8], _adt.monotonic() - _pe_t1)
        self._active_dispatches[td.task_id] = td
        _pe_t2 = _adt.monotonic()
        if self._bus is not None:
            await self._bus.send(Message(
                from_agent="orchestrator",
                to_agent=td.agent_id,
                subject=f"Task assigned: {td.task_id}",
                body=f"You have been assigned task {td.task_id}.",
            ))
        logger.info("_assign_dispatch(%s): bus_send=%.2fs", td.task_id[:8], _adt.monotonic() - _pe_t2)
        self._record_task_event(
            "dispatch_assigned",
            task_id=td.task_id,
            agent_id=td.agent_id,
            topology=td.topology.value,
            witness_reroutes=td.metadata.get("witness_reroutes", 0),
        )
        latent_gold_count = int(claim_meta.get("latent_gold_count", 0) or 0)
        if latent_gold_count > 0:
            td.metadata["latent_gold_count"] = latent_gold_count
            self._record_task_event(
                "latent_gold_attached",
                task_id=td.task_id,
                agent_id=td.agent_id,
                latent_gold_count=latent_gold_count,
            )
            self._record_progress_event(
                "latent_gold_attached",
                task_id=td.task_id,
                agent_id=td.agent_id,
                latent_gold_count=latent_gold_count,
            )
            await self._emit_lifecycle_event(
                "latent_gold_attached",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={
                    "latent_gold_count": latent_gold_count,
                    "latent_gold_states": [
                        str(item.get("state", "unknown"))
                        for item in claim_meta.get("latent_gold", [])
                        if isinstance(item, dict)
                    ],
                },
            )
        _pe_t3 = _adt.monotonic()
        await self._emit_lifecycle_event(
            "dispatch_assigned",
            task_id=td.task_id,
            agent_id=td.agent_id,
            extra={"topology": td.topology.value},
        )
        logger.info("_assign_dispatch(%s): lifecycle_event=%.2fs", td.task_id[:8], _adt.monotonic() - _pe_t3)

        logger.info("_assign_dispatch(%s): pre_execute=%.2fs", td.task_id[:8], _adt.monotonic() - _ad0)
        # Actually execute the task via the agent runner
        pool_get = getattr(self._pool, "get", None)
        runner = await pool_get(td.agent_id) if pool_get else None
        task = task_for_gate or await self._safe_get_task(td.task_id)
        logger.info(
            "_assign_dispatch(%s): runner=%s task=%s pool_agents=%s",
            td.task_id[:8], bool(runner), bool(task),
            list((await self._pool.list_agents()) if self._pool else [])[:3],
        )
        if runner and task:
            run_meta = self._task_meta(task)
            run_meta.pop("retry_not_before_epoch", None)
            run_meta["active_claim"] = claim_meta.get("active_claim")
            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.RUNNING,
                metadata=run_meta,
            )
            td.metadata["run_started_monotonic"] = time.monotonic()
            self._record_progress_event(
                "task_started",
                task_id=td.task_id,
                agent_id=td.agent_id,
                topology=td.topology.value,
                timeout_seconds=td.timeout_seconds,
            )
            await self._emit_lifecycle_event(
                "task_started",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={"timeout_seconds": td.timeout_seconds},
            )
            bg = asyncio.create_task(
                self._execute_task(runner, task, td),
                name=f"exec-{td.task_id[:8]}",
            )
            self._running_tasks[td.task_id] = bg
            logger.info("_assign_dispatch(%s): bg_task_created total=%.2fs", td.task_id[:8], _adt.monotonic() - _ad0)
        else:
            reason = (
                f"Dispatch accepted but worker unavailable "
                f"(runner={bool(runner)} task={bool(task)})"
            )
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
            await self._handle_task_failure(
                td=td,
                task=task_for_gate,
                error=reason,
                source="dispatch_dropoff",
            )
            logger.warning("Dispatch dropped for task %s: %s", td.task_id, reason)
            return

        logger.info("Dispatched task %s -> agent %s", td.task_id, td.agent_id)

    async def _execute_task(self, runner: Any, task: Task, td: TaskDispatch) -> None:
        """Run agent.run_task() in background, update board on completion/failure."""
        # Yield immediately so the dispatching coroutine can finish its loop
        # before this background task starts its synchronous pre-LLM work
        await asyncio.sleep(0)
        run_started = float(td.metadata.get("run_started_monotonic", time.monotonic()))
        timeout_seconds = max(
            0.01,
            self._coerce_float(td.timeout_seconds, self._default_timeout_seconds),
        )
        try:
            result = await asyncio.wait_for(
                runner.run_task(task),
                timeout=timeout_seconds,
            )
            try:
                from dharma_swarm.mission_contract import (
                    honors_checkpoint_passed,
                    load_completion_contract,
                    load_honors_checkpoint,
                )

                completion_contract = load_completion_contract(task.metadata)
                honors_checkpoint = load_honors_checkpoint(task.metadata)
                if completion_contract is not None and not honors_checkpoint_passed(task.metadata):
                    error = (
                        "Honors checkpoint missing or failed: task returned a result "
                        "without a passing judge pack"
                    )
                    if self._pool is not None:
                        await self._pool.release(td.agent_id)
                    self._active_dispatches.pop(td.task_id, None)
                    await self._handle_task_failure(
                        td=td,
                        task=task,
                        error=error,
                        source="honors_checkpoint",
                    )
                    return
            except Exception as exc:
                logger.exception("Task %s honors checkpoint validation failed: %s", td.task_id, exc)
                if self._pool is not None:
                    await self._pool.release(td.agent_id)
                self._active_dispatches.pop(td.task_id, None)
                await self._handle_task_failure(
                    td=td,
                    task=task,
                    error=f"Honors checkpoint validation failed: {exc}",
                    source="honors_checkpoint",
                )
                return
            success_meta = self._task_meta(task)
            success_meta.pop("active_claim", None)
            success_meta.pop("retry_not_before_epoch", None)
            success_meta["last_completed_at"] = datetime.now(timezone.utc).isoformat()
            success_meta["last_result_chars"] = len(result or "")
            try:
                from dharma_swarm.mission_contract import load_honors_checkpoint

                honors_checkpoint = load_honors_checkpoint(success_meta)
                if honors_checkpoint is not None:
                    success_meta["honors_checkpoint_score"] = honors_checkpoint.judge_pack.final_score
                    success_meta["honors_checkpoint_accepted"] = honors_checkpoint.judge_pack.accepted
            except Exception:
                logger.debug("Honors checkpoint summary extraction failed", exc_info=True)
            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                metadata=success_meta,
            )
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
            # Release YogaNode capacity for this agent
            if self._yoga is not None:
                self._yoga.record_completion(td.agent_id)
            logger.info("Task %s completed by agent %s", td.task_id, td.agent_id)
            duration_sec = max(0.0, time.monotonic() - run_started)

            # Emit to signal_bus so organism heartbeat, evolution loop,
            # and consolidation loop can sense completed work.
            try:
                from dharma_swarm.signal_bus import SignalBus, SIGNAL_LIFECYCLE_COMPLETED
                SignalBus.get().emit({
                    "type": SIGNAL_LIFECYCLE_COMPLETED,
                    "task_id": td.task_id,
                    "agent_id": td.agent_id,
                    "duration_sec": round(duration_sec, 4),
                    "result_chars": len(result or ""),
                })
            except Exception:
                pass  # signal_bus emission is non-critical

            # P1: Perception loop — task completion → TelosGraph progress
            # Uses supervised task tracking to prevent silent GC before completion
            try:
                from dharma_swarm.telos_tracker import record_task_completion
                _t1 = asyncio.create_task(
                    record_task_completion(
                        task_title=getattr(task, 'title', ''),
                        task_description=getattr(task, 'description', ''),
                        result=result,
                        state_dir=self._runtime_root(),
                    )
                )
                _t1.add_done_callback(
                    lambda t: (
                        logger.debug("telos_tracker failed: %s", t.exception())
                        if not t.cancelled() and t.exception() else None
                    )
                )
            except Exception:
                pass  # Never block task completion

            # P4: Knowledge consolidation → KnowledgeStore via SleepTimeAgent.
            # REQUIRES llm_client — without it, KnowledgeExtractor returns []
            # and nothing is stored. Pass a lightweight provider wrapper.
            try:
                from dharma_swarm.sleep_time_agent import SleepTimeAgent
                from dharma_swarm.runtime_provider import complete_via_preferred_runtime_providers
                from dharma_swarm.models import LLMRequest

                class _MinimalLLMClient:
                    """Thin adapter matching KnowledgeExtractor._call_llm interface.

                    Targets cheap/free models only — knowledge extraction doesn't
                    need frontier intelligence, just reliable JSON output.
                    Provider order: Ollama Cloud → Groq → NVIDIA NIM → fallback.
                    Avoids claude_code (billing issues) and respects circuit breakers.
                    """
                    async def complete(self, request_or_prompt, **kwargs):
                        from dharma_swarm.models import ProviderType
                        # Accept both LLMRequest objects and raw prompt strings
                        if isinstance(request_or_prompt, str):
                            req = LLMRequest(
                                model="",
                                messages=[{"role": "user", "content": request_or_prompt}],
                                system=(
                                    "Extract factual claims and recommendations from text. "
                                    "Return valid JSON array only."
                                ),
                                max_tokens=kwargs.get("max_tokens", 512),
                                temperature=0.1,
                            )
                        else:
                            req = request_or_prompt
                            req.model = req.model or ""
                            req.max_tokens = min(getattr(req, 'max_tokens', 512) or 512, 512)

                        # Try cheap providers in order, skip dead ones
                        cheap_providers = [
                            ProviderType.OLLAMA,
                            ProviderType.GROQ,
                            ProviderType.NVIDIA_NIM,
                            ProviderType.CEREBRAS,
                        ]
                        for ptype in cheap_providers:
                            try:
                                from dharma_swarm.runtime_provider import create_default_provider_map
                                provider_map = create_default_provider_map()
                                provider = provider_map.get(ptype)
                                if provider and getattr(provider, 'available', False):
                                    response = await provider.complete(req)
                                    if response and getattr(response, 'content', None):
                                        return response
                            except Exception:
                                continue  # Try next provider

                        # Final fallback via full router
                        try:
                            return await complete_via_preferred_runtime_providers(req)
                        except Exception as exc:
                            logger.debug("_MinimalLLMClient: all providers failed: %s", exc)
                            class _EmptyResponse:
                                content = "[]"
                                text = "[]"
                            return _EmptyResponse()

                _sta = SleepTimeAgent()
                _t4 = asyncio.create_task(
                    _sta.consolidate_knowledge(
                        task_context=result or "",
                        task_outcome={
                            "success": True,
                            "task_title": getattr(task, 'title', ''),
                            "source": "task_completion",
                        },
                        llm_client=_MinimalLLMClient(),
                    )
                )
                _t4.add_done_callback(
                    lambda t: (
                        logger.warning("SleepTimeAgent consolidation failed: %s", t.exception())
                        if not t.cancelled() and t.exception() else None
                    )
                )
            except Exception:
                pass  # Never block task completion

            # Record edge in catalytic graph: agent → task_type
            try:
                from dharma_swarm.catalytic_graph import CatalyticGraph
                cg = CatalyticGraph()
                cg.load()
                quality = min(1.0, len(result or "") / 2000.0)
                cg.add_edge(
                    source=f"agent:{agent_name}",
                    target=f"task:{task.title[:40]}",
                    edge_type="enables",
                    strength=round(max(0.1, quality), 2),
                    evidence=f"Completed in {duration_sec:.0f}s",
                )
                cg.save()
            except Exception:
                pass

            self._record_progress_event(
                "task_completed",
                    task_id=td.task_id,
                    agent_id=td.agent_id,
                    duration_sec=round(duration_sec, 4),
                    result_chars=len(result or ""),
                    timeout_seconds=timeout_seconds,
                )
            await self._emit_lifecycle_event(
                "task_completed",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={"duration_sec": round(duration_sec, 4)},
            )
            # Emit durable event for evolution loop consumption
            if self._bus is not None:
                emit = getattr(self._bus, "emit_event", None)
                if emit:
                    try:
                        await emit(
                            "AGENT_LIFECYCLE_COMPLETED",
                            task_id=td.task_id,
                            agent_id=td.agent_id,
                            payload={"event": "task_completed", "duration_sec": round(duration_sec, 4)},
                        )
                    except Exception:
                        logger.debug("Lifecycle event emit failed (non-critical)", exc_info=True)

            # Auto-extract: if task says "write to <path>", save result there
            try:
                import re as _re_extract
                desc = task.description or ""
                path_match = _re_extract.search(
                    r"[Ww]rite [\w\s]*?(?:to |report to |results to |output to |findings to )(~/[^\s,\"]+\.md)",
                    desc,
                )
                if path_match and result and len(result) > 200:
                    from pathlib import Path as _P
                    target = _P(path_match.group(1)).expanduser()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(result, encoding="utf-8")
                    logger.info(
                        "Auto-extracted %d chars to %s",
                        len(result), target,
                    )
            except Exception:
                logger.debug("Auto-extract failed", exc_info=True)

            # Persist result to shared notes and stigmergy
            runner_cfg = getattr(runner, "_config", None)
            agent_name = runner_cfg.name if runner_cfg else td.agent_id[:8]
            model_name = getattr(runner_cfg, "model", "unknown")
            provider_name = (
                getattr(getattr(runner_cfg, "provider", None), "value", None)
                or str(getattr(runner_cfg, "provider", "unknown"))
            )
            await self._persist_result(
                agent_name=agent_name,
                model_name=str(model_name),
                provider_name=str(provider_name),
                task=task,
                result=result,
            )

        except asyncio.TimeoutError:
            error = f"Task execution timed out after {timeout_seconds:.1f}s"
            logger.warning("Task %s timeout on agent %s", td.task_id, td.agent_id)
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
            await self._handle_task_failure(
                td=td,
                task=task,
                error=error,
                source="timeout",
            )
        except Exception as exc:
            logger.exception("Task %s failed: %s", td.task_id, exc)
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
            await self._handle_task_failure(
                td=td,
                task=task,
                error=str(exc),
                source="execution_error",
            )
        finally:
            # NOTE: Do NOT pop from _running_tasks here.
            # _collect_completed() is the sole cleanup mechanism — it checks
            # atask.done() and counts settled tasks. If we pop here, the task
            # vanishes before _collect_completed can see it, causing settled=0.
            pass

    async def _persist_result(
        self,
        *,
        agent_name: str,
        model_name: str,
        provider_name: str,
        task: Task,
        result: str | None,
    ) -> None:
        """Write agent result to shared notes and stigmergy marks.

        This is the critical persistence step that makes agent output
        visible to future sessions. Without it, the colony has no memory.
        """
        if result is None:
            logger.debug("_persist_result: result is None for task %s, skipping", task.id)
            return

        from datetime import datetime, timezone

        shared_dir = self._shared_dir
        shared_dir.mkdir(parents=True, exist_ok=True)

        # Write shared notes (append, not overwrite)
        notes_file = shared_dir / f"{agent_name}_notes.md"
        provenance_dir = shared_dir / "provenance"
        provenance_dir.mkdir(parents=True, exist_ok=True)
        trace_id = (
            str(task.metadata.get("trace_id")) if isinstance(task.metadata, dict) else ""
        ) or f"task:{task.id}"
        result_hash = hashlib.sha256((result or "").encode("utf-8")).hexdigest()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # Truncate very long results for notes (full result is in task board)
        summary = result[:2000] if len(result) > 2000 else result
        provenance_record = {
            "trace_id": trace_id,
            "task_id": task.id,
            "task_title": task.title,
            "agent": agent_name,
            "model": model_name,
            "provider": provider_name,
            "session_id": self._ledger.session_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "result_chars": len(result or ""),
            "result_sha256": result_hash,
            "notes_file": str(notes_file),
            "source": "orchestrator._persist_result",
        }
        provenance_path = provenance_dir / f"{task.id}.json"
        entry = (
            f"\n---\n## {task.title}\n"
            f"*{timestamp} | task: {task.id[:8]} | trace: {trace_id}*\n\n"
            f"_provenance_: `{provenance_path}`\n\n"
            f"{summary}\n"
        )
        try:
            with open(notes_file, "a") as f:
                f.write(entry)
            with open(provenance_path, "w") as f:
                f.write(json.dumps(provenance_record, ensure_ascii=True, sort_keys=True, indent=2) + "\n")
            logger.info("Wrote notes for %s -> %s", agent_name, notes_file.name)
            self._record_task_event(
                "result_persisted",
                task_id=task.id,
                agent_id=agent_name,
                notes_file=str(notes_file),
                provenance_file=str(provenance_path),
                trace_id=trace_id,
                result_chars=len(result or ""),
            )
        except Exception as exc:
            logger.warning("Failed to write notes for %s: %s", agent_name, exc)
            self._record_progress_event(
                "result_persist_failed",
                task_id=task.id,
                agent_id=agent_name,
                trace_id=trace_id,
                error=str(exc),
            )

        # Write a shared artifact with task-specific path so dependent tasks can find it
        try:
            # Create a slug from task title for predictable cross-task path
            slug = re.sub(r'[^a-z0-9]+', '_', (task.title or 'task').lower()).strip('_')[:40]
            shared_artifact = shared_dir / f"{task.id[:8]}_{slug}.md"
            shared_artifact.write_text(
                f"# {task.title}\n\n"
                f"**Task ID:** {task.id}\n"
                f"**Agent:** {agent_name}\n"
                f"**Completed:** {datetime.now(timezone.utc).isoformat()}\n\n"
                f"---\n\n"
                f"{result}",
                encoding="utf-8",
            )
            logger.debug("Shared artifact written: %s", shared_artifact.name)
        except Exception as exc:
            logger.debug("Shared artifact write failed (non-fatal): %s", exc)

        # Fix 2: Feed result into MemoryPalace for cross-session semantic recall.
        # Even with TF-IDF only (sqlite-vec not installed), this builds the corpus
        # that future vector/hybrid search will query.
        try:
            from dharma_swarm.memory_palace import MemoryPalace
            palace = MemoryPalace(state_dir=self._runtime_root())
            _t_palace = asyncio.create_task(
                palace.ingest(
                    content=result,
                    source=f"task:{task.id[:8]}:{task.title[:60]}",
                    layer="working",
                    tags=["task_output"],
                )
            )
            _t_palace.add_done_callback(
                lambda t: (
                    logger.debug("MemoryPalace ingest failed: %s", t.exception())
                    if not t.cancelled() and t.exception() else None
                )
            )
        except Exception as exc:
            logger.debug("MemoryPalace ingest failed (non-fatal): %s", exc)

        # Leave stigmergic mark
        try:
            from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

            store = StigmergyStore(self._stigmergy_dir)
            # Extract first meaningful line as observation
            lines = [l.strip() for l in result.split("\n") if l.strip()]
            observation = lines[0][:200] if lines else f"Completed: {task.title}"
            mark = StigmergicMark(
                agent=agent_name,
                file_path=f"task:{task.id[:8]}",
                action="write",
                observation=observation,
                salience=0.6,
                connections=[],
            )
            await store.leave_mark(mark)
            logger.info("Stigmergy mark left by %s", agent_name)
        except Exception as exc:
            logger.debug("Stigmergy mark failed (non-critical): %s", exc)

    async def _collect_completed(self) -> tuple[int, int]:
        """Clean up finished background tasks and stale dispatches."""
        # Clean up any asyncio tasks that finished (with exceptions we missed)
        done_tasks: list[str] = []
        for task_id, atask in self._running_tasks.items():
            if atask.done():
                done_tasks.append(task_id)
                # Surface any unhandled exceptions
                try:
                    exc = atask.exception()
                    if exc is not None:
                        logger.error(
                            "Background task %s had unhandled exception: %s",
                            task_id, exc,
                        )
                except asyncio.CancelledError:
                    logger.warning(
                        "Background task %s was cancelled", task_id
                    )
        for task_id in done_tasks:
            self._running_tasks.pop(task_id, None)
            self._active_dispatches.pop(task_id, None)

        # Recover stale dispatch claims that never started execution.
        now_mono = time.monotonic()
        stale: list[tuple[str, TaskDispatch]] = []
        for task_id, td in self._active_dispatches.items():
            if task_id in self._running_tasks:
                continue
            claim_deadline = self._coerce_float(
                td.metadata.get("claim_expires_monotonic"),
                0.0,
            )
            if claim_deadline <= 0.0:
                continue
            if now_mono >= claim_deadline:
                stale.append((task_id, td))

        for task_id, td in stale:
            task = await self._safe_get_task(task_id)
            reason = (
                f"Dispatch claim expired before execution after "
                f"{td.metadata.get('claim_timeout_seconds', 'unknown')}s"
            )
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(task_id, None)
            await self._handle_task_failure(
                td=td,
                task=task,
                error=reason,
                source="claim_timeout",
            )
        return len(done_tasks), len(stale)
