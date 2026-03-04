"""Async task orchestrator with fan-out/fan-in routing.

The orchestrator connects a task_board to an agent_pool, dispatching work
via topology patterns. It owns neither dependency -- both are duck-typed.

Duck-type contracts:
    task_board:  get_ready_tasks() -> list[Task], update_task(id, **kw)
    agent_pool:  get_idle_agents() -> list[AgentState], assign(aid, tid),
                 release(aid), get_result(aid) -> str | None
    message_bus: send(Message) -> str  (optional)
"""

from __future__ import annotations

import asyncio
import logging
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

logger = logging.getLogger(__name__)


@runtime_checkable
class TaskBoard(Protocol):
    """Duck-type protocol for task storage."""
    async def get_ready_tasks(self) -> list[Task]: ...
    async def update_task(self, task_id: str, **fields: Any) -> None: ...


@runtime_checkable
class AgentPool(Protocol):
    """Duck-type protocol for agent management."""
    async def get_idle_agents(self) -> list[AgentState]: ...
    async def assign(self, agent_id: str, task_id: str) -> None: ...
    async def release(self, agent_id: str) -> None: ...
    async def get_result(self, agent_id: str) -> str | None: ...


class Orchestrator:
    """Async task orchestrator routing work to agents via fan-out/fan-in."""

    def __init__(
        self,
        task_board: Any = None,
        agent_pool: Any = None,
        message_bus: Any = None,
    ) -> None:
        self._board = task_board
        self._pool = agent_pool
        self._bus = message_bus
        self._running = False
        self._active_dispatches: dict[str, TaskDispatch] = {}

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

    # -- internals ---------------------------------------------------------

    async def _assign_dispatch(self, td: TaskDispatch) -> None:
        """Record dispatch, update board + pool, optionally notify via bus."""
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
        logger.debug("Dispatched task %s -> agent %s", td.task_id, td.agent_id)

    async def _collect_completed(self) -> None:
        """Poll active dispatches for results and finalize completed ones."""
        if self._pool is None or self._board is None:
            return

        done: list[str] = []
        for task_id, td in self._active_dispatches.items():
            result = await self._pool.get_result(td.agent_id)
            if result is not None:
                await self._board.update_task(
                    task_id, status=TaskStatus.COMPLETED, result=result
                )
                await self._pool.release(td.agent_id)
                done.append(task_id)
                logger.debug("Collected result for task %s", task_id)

        for task_id in done:
            self._active_dispatches.pop(task_id, None)
