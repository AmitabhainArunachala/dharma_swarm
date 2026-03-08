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
import logging
import re
import time
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
    ) -> None:
        self._board = task_board
        self._pool = agent_pool
        self._bus = message_bus
        self._ledger = ledger or SessionLedger(
            base_dir=ledger_dir,
            session_id=session_id,
        )
        self._running = False
        self._active_dispatches: dict[str, TaskDispatch] = {}
        # Track running asyncio tasks for actual LLM execution
        self._running_tasks: dict[str, asyncio.Task] = {}

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
        td = TaskDispatch(task_id=task.id, agent_id=idle[0].id, topology=topology)
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

        # Skip tasks already being executed
        ready = [t for t in ready if t.id not in self._running_tasks]

        dispatches: list[TaskDispatch] = []
        for task, agent in zip(ready, idle):
            td = TaskDispatch(task_id=task.id, agent_id=agent.id)
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
        if self._bus is None:
            return
        publish = getattr(self._bus, "publish", None)
        if not publish:
            return
        metadata = {
            "event": event,
            "task_id": task_id,
            "agent_id": agent_id,
            **(extra or {}),
        }
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

    @staticmethod
    def _failure_signature(error: str) -> str:
        base = (error or "").strip().splitlines()[0] if error else "unknown_error"
        lowered = base.lower()
        lowered = re.sub(r"[0-9a-f]{12,}", "<id>", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered[:200]

    async def _assign_dispatch(self, td: TaskDispatch) -> None:
        """Record dispatch, update board + pool, kick off execution, notify via bus."""
        td.metadata["dispatch_started_monotonic"] = time.monotonic()
        task_for_gate: Task | None = None
        board_get = getattr(self._board, "get", None)
        if board_get:
            try:
                task_for_gate = await board_get(td.task_id)
            except Exception:
                task_for_gate = None

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
            if self._board is not None:
                await self._board.update_task(
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

        self._active_dispatches[td.task_id] = td

        if self._pool is not None:
            await self._pool.assign(td.agent_id, td.task_id)
        if self._board is not None:
            await self._board.update_task(
                td.task_id, status=TaskStatus.ASSIGNED, assigned_to=td.agent_id
            )
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
        board_get = getattr(self._board, "get", None)
        if pool_get and board_get:
            runner = await pool_get(td.agent_id)
            task = task_for_gate or await board_get(td.task_id)
            if runner and task:
                await self._board.update_task(td.task_id, status=TaskStatus.RUNNING)
                td.metadata["run_started_monotonic"] = time.monotonic()
                self._record_progress_event(
                    "task_started",
                    task_id=td.task_id,
                    agent_id=td.agent_id,
                    topology=td.topology.value,
                )
                await self._emit_lifecycle_event(
                    "task_started",
                    task_id=td.task_id,
                    agent_id=td.agent_id,
                )
                bg = asyncio.create_task(
                    self._execute_task(runner, task, td),
                    name=f"exec-{td.task_id[:8]}",
                )
                self._running_tasks[td.task_id] = bg

        logger.info("Dispatched task %s -> agent %s", td.task_id, td.agent_id)

    async def _execute_task(self, runner: Any, task: Task, td: TaskDispatch) -> None:
        """Run agent.run_task() in background, update board on completion/failure."""
        run_started = float(td.metadata.get("run_started_monotonic", time.monotonic()))
        try:
            result = await runner.run_task(task)
            if self._board is not None:
                await self._board.update_task(
                    td.task_id, status=TaskStatus.COMPLETED, result=result
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
            )
            await self._emit_lifecycle_event(
                "task_completed",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={"duration_sec": round(duration_sec, 4)},
            )

            # Persist result to shared notes and stigmergy
            agent_name = getattr(runner, '_config', None)
            agent_name = agent_name.name if agent_name else td.agent_id[:8]
            await self._persist_result(agent_name, task, result)

        except Exception as exc:
            logger.exception("Task %s failed: %s", td.task_id, exc)
            if self._board is not None:
                await self._board.update_task(
                    td.task_id, status=TaskStatus.FAILED, result=str(exc)
                )
            self._record_progress_event(
                "task_failed",
                task_id=td.task_id,
                agent_id=td.agent_id,
                failure_signature=self._failure_signature(str(exc)),
                error=str(exc),
            )
            await self._emit_lifecycle_event(
                "task_failed",
                task_id=td.task_id,
                agent_id=td.agent_id,
                extra={"failure_signature": self._failure_signature(str(exc))},
            )
            if self._pool is not None:
                await self._pool.release(td.agent_id)
            self._active_dispatches.pop(td.task_id, None)
        finally:
            self._running_tasks.pop(td.task_id, None)

    async def _persist_result(
        self, agent_name: str, task: Task, result: str
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
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        # Truncate very long results for notes (full result is in task board)
        summary = result[:2000] if len(result) > 2000 else result
        entry = (
            f"\n---\n## {task.title}\n"
            f"*{timestamp} | task: {task.id[:8]}*\n\n"
            f"{summary}\n"
        )
        try:
            with open(notes_file, "a") as f:
                f.write(entry)
            logger.info("Wrote notes for %s -> %s", agent_name, notes_file.name)
            self._record_task_event(
                "result_persisted",
                task_id=task.id,
                agent_id=agent_name,
                notes_file=str(notes_file),
                result_chars=len(result or ""),
            )
        except Exception as exc:
            logger.warning("Failed to write notes for %s: %s", agent_name, exc)

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
