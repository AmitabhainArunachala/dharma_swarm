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
from dharma_swarm.telos_gates import check_with_reflective_reroute

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
        session_id: str | None = None,
        event_memory: Any = None,
    ) -> None:
        self._board = task_board
        self._pool = agent_pool
        self._bus = message_bus
        self._event_memory = event_memory
        self._ledger = ledger or SessionLedger(
            base_dir=ledger_dir,
            session_id=session_id,
        )
        self._running = False
        self._active_dispatches: dict[str, TaskDispatch] = {}
        # Track running asyncio tasks for actual LLM execution
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._default_timeout_seconds = 300.0
        self._default_claim_timeout_seconds = 420.0
        self._default_max_retries = 0
        self._default_retry_backoff_seconds = 0.0

    async def dispatch(
        self,
        task: Task,
        topology: TopologyType = TopologyType.FAN_OUT,
    ) -> list[TaskDispatch]:
        """Assign task to available agents based on topology."""
        if self._pool is None:
            return []

        idle: list[AgentState] = await self._pool.get_idle_agents()
        if not idle:
            return []

        if topology in (TopologyType.FAN_OUT, TopologyType.BROADCAST):
            return await self.fan_out(task, idle)

        # PIPELINE / FAN_IN: single agent per step
        td = TaskDispatch(
            task_id=task.id,
            agent_id=idle[0].id,
            topology=topology,
            timeout_seconds=self._resolve_timeout_seconds(task, self._default_timeout_seconds),
        )
        await self._assign_dispatch(td)
        return [td]

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
        if self._board is None or self._pool is None:
            return []

        ready = await self._board.get_ready_tasks()
        idle = await self._pool.get_idle_agents()
        if not ready or not idle:
            return []

        # Skip tasks already being executed or waiting for retry backoff.
        ready = [t for t in ready if t.id not in self._running_tasks]
        ready = [t for t in ready if self._is_retry_window_open(t)]

        dispatches: list[TaskDispatch] = []
        for task, agent in zip(ready, idle):
            td = TaskDispatch(
                task_id=task.id,
                agent_id=agent.id,
                timeout_seconds=self._resolve_timeout_seconds(
                    task,
                    self._default_timeout_seconds,
                ),
            )
            await self._assign_dispatch(td)
            dispatches.append(td)
        return dispatches

    async def tick(self) -> None:
        """One orchestration cycle: collect completed, then route pending."""
        await self._collect_completed()
        await self.route_next()

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
        failure_signature = self._failure_signature(error)
        retry_count, max_retries, backoff = self._resolve_retry_policy(task)
        if source in {"claim_timeout", "dispatch_dropoff"}:
            max_retries = max(max_retries, 1)

        meta = self._task_meta(task)
        meta.pop("active_claim", None)
        meta["last_error"] = error
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
                failure_signature=failure_signature,
            )
            self._record_progress_event(
                "task_retry_scheduled",
                task_id=td.task_id,
                agent_id=td.agent_id,
                retry_count=next_retry,
                max_retries=max_retries,
                source=source,
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
                "retry_count": retry_count,
                "max_retries": max_retries,
            },
        )

    async def _assign_dispatch(self, td: TaskDispatch) -> None:
        """Record dispatch, update board + pool, kick off execution, notify via bus."""
        td.metadata["dispatch_started_monotonic"] = time.monotonic()
        task_for_gate = await self._safe_get_task(td.task_id)

        action_ref = (
            f"dispatch task {task_for_gate.title} -> {td.agent_id}"
            if task_for_gate
            else f"dispatch task {td.task_id} -> {td.agent_id}"
        )
        content_ref = task_for_gate.description if task_for_gate else ""
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

        if self._pool is not None:
            await self._pool.assign(td.agent_id, td.task_id)
        await self._safe_update_task(
            td.task_id,
            status=TaskStatus.ASSIGNED,
            assigned_to=td.agent_id,
            metadata=claim_meta,
        )
        self._active_dispatches[td.task_id] = td
        if self._bus is not None:
            await self._bus.send(Message(
                from_agent="orchestrator",
                to_agent=td.agent_id,
                subject=f"Task assigned: {td.task_id}",
                body=f"You have been assigned task {td.task_id}.",
            ))
        self._record_task_event(
            "dispatch_assigned",
            task_id=td.task_id,
            agent_id=td.agent_id,
            topology=td.topology.value,
            witness_reroutes=td.metadata.get("witness_reroutes", 0),
        )
        await self._emit_lifecycle_event(
            "dispatch_assigned",
            task_id=td.task_id,
            agent_id=td.agent_id,
            extra={"topology": td.topology.value},
        )

        # Actually execute the task via the agent runner
        pool_get = getattr(self._pool, "get", None)
        runner = await pool_get(td.agent_id) if pool_get else None
        task = task_for_gate or await self._safe_get_task(td.task_id)
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
            success_meta = self._task_meta(task)
            success_meta.pop("active_claim", None)
            success_meta.pop("retry_not_before_epoch", None)
            success_meta["last_completed_at"] = datetime.now(timezone.utc).isoformat()
            success_meta["last_result_chars"] = len(result or "")
            await self._safe_update_task(
                td.task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                metadata=success_meta,
            )
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
            logger.info("Task %s completed by agent %s", td.task_id, td.agent_id)
            duration_sec = max(0.0, time.monotonic() - run_started)
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
            self._running_tasks.pop(td.task_id, None)

    async def _persist_result(
        self,
        *,
        agent_name: str,
        model_name: str,
        provider_name: str,
        task: Task,
        result: str,
    ) -> None:
        """Write agent result to shared notes and stigmergy marks.

        This is the critical persistence step that makes agent output
        visible to future sessions. Without it, the colony has no memory.
        """
        from pathlib import Path
        from datetime import datetime, timezone

        shared_dir = Path.home() / ".dharma" / "shared"
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

        # Leave stigmergic mark
        try:
            from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

            store = StigmergyStore()
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

    async def _collect_completed(self) -> None:
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
