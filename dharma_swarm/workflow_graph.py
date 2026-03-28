"""DAG-based workflow execution with topological ordering.

Define tasks as a directed acyclic graph. Execute in dependency order.
Parallel-ready steps execute concurrently. Failed steps can be retried
or skipped.

Inspired by:
  - LangGraph: graph-based state machines for agent orchestration
  - Ralphinho RFC pipeline: decompose into DAG, execute per layer
  - Airflow/Prefect: DAG-based workflow orchestration

Grounded in:
  - Beer VSM (Pillar 8): S1 operations follow dependency-determined order
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from dharma_swarm.durable_execution import (
    DurableWorkflow,
    StepStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Cycle detection (Kahn's algorithm)
# ---------------------------------------------------------------------------


def detect_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Check whether a directed graph contains a cycle using Kahn's algorithm.

    Args:
        adjacency: Mapping from node_id to list of successor node_ids.

    Returns:
        True if a cycle exists, False if the graph is a DAG.
    """
    in_degree: dict[str, int] = defaultdict(int)
    all_nodes: set[str] = set()

    for node, successors in adjacency.items():
        all_nodes.add(node)
        for succ in successors:
            all_nodes.add(succ)
            in_degree[succ] += 1

    # Ensure every node appears in in_degree
    for node in all_nodes:
        in_degree.setdefault(node, 0)

    queue: deque[str] = deque(
        node for node, deg in in_degree.items() if deg == 0
    )
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for succ in adjacency.get(node, []):
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    return visited < len(all_nodes)


# ---------------------------------------------------------------------------
# Graph node
# ---------------------------------------------------------------------------


class GraphNode:
    """A node in the workflow graph."""

    __slots__ = ("node_id", "name", "handler_fn")

    def __init__(
        self,
        node_id: str,
        name: str,
        handler_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.node_id = node_id
        self.name = name
        self.handler_fn = handler_fn


# ---------------------------------------------------------------------------
# Workflow graph
# ---------------------------------------------------------------------------


class WorkflowGraph:
    """DAG-based workflow with topological execution and durable checkpointing.

    Build a graph of task nodes with dependency edges, then execute them
    in topological order. Each layer of the topological sort can run in
    parallel. A DurableWorkflow tracks state at every step so execution
    can resume from the last successful checkpoint after a crash.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, list[str]] = defaultdict(list)  # from -> [to]
        self._reverse: dict[str, list[str]] = defaultdict(list)  # to -> [from]

    # -- Graph construction --------------------------------------------------

    def add_node(
        self,
        node_id: str,
        name: str,
        handler_fn: Callable[..., Any] | None = None,
    ) -> None:
        """Add a task node to the graph.

        Args:
            node_id: Unique identifier for the node.
            name: Human-readable name.
            handler_fn: Async or sync callable to execute for this node.
                Receives a dict of upstream results keyed by node_id.

        Raises:
            ValueError: If node_id already exists.
        """
        if node_id in self._nodes:
            raise ValueError(f"Node '{node_id}' already exists")
        self._nodes[node_id] = GraphNode(
            node_id=node_id, name=name, handler_fn=handler_fn
        )

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge: to_id depends on from_id.

        Args:
            from_id: The upstream node.
            to_id: The downstream node that depends on from_id.

        Raises:
            ValueError: If either node doesn't exist.
        """
        if from_id not in self._nodes:
            raise ValueError(f"Source node '{from_id}' not found")
        if to_id not in self._nodes:
            raise ValueError(f"Target node '{to_id}' not found")
        self._edges[from_id].append(to_id)
        self._reverse[to_id].append(from_id)

    # -- Validation ----------------------------------------------------------

    def validate(self) -> bool:
        """Check that the graph is a valid DAG (no cycles).

        Returns:
            True if the graph is acyclic, False otherwise.
        """
        return not detect_cycle(dict(self._edges))

    # -- Topological sort ----------------------------------------------------

    def topological_sort(self) -> list[list[str]]:
        """Return nodes grouped into parallel layers (topological generations).

        Each inner list contains node_ids that can execute concurrently.
        The layers are ordered so that all dependencies of nodes in layer N
        are in layers < N.

        Returns:
            List of layers, each layer a list of node_ids.

        Raises:
            ValueError: If the graph contains a cycle.
        """
        if not self.validate():
            raise ValueError("Graph contains a cycle, cannot sort topologically")

        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        for _from, targets in self._edges.items():
            for t in targets:
                in_degree[t] += 1

        layers: list[list[str]] = []
        remaining = set(self._nodes.keys())

        while remaining:
            layer = [nid for nid in remaining if in_degree[nid] == 0]
            if not layer:
                break  # guard -- should not happen after validate()

            layers.append(sorted(layer))  # sorted for determinism
            for nid in layer:
                remaining.discard(nid)
                for succ in self._edges.get(nid, []):
                    if succ in remaining:
                        in_degree[succ] -= 1

        return layers

    # -- Execution -----------------------------------------------------------

    async def execute(
        self,
        on_step_complete: Callable[[WorkflowStep], Any] | None = None,
        workflow_id: str | None = None,
        persist_dir: Any | None = None,
    ) -> dict[str, Any]:
        """Execute all nodes in topological order with durable checkpointing.

        Each layer runs concurrently via asyncio.gather. If a node fails,
        all its transitive dependents are marked SKIPPED.

        Args:
            on_step_complete: Optional callback fired after each step.
            workflow_id: Override workflow ID (default: "wfg_<timestamp>").
            persist_dir: Override persist directory for the DurableWorkflow.

        Returns:
            Dict with keys:
              - "results": mapping of node_id -> result
              - "summary": step counts by status
              - "elapsed_seconds": total wall-clock time
              - "workflow_id": the workflow ID used
        """
        from pathlib import Path

        wf_id = workflow_id or f"wfg_{int(time.time())}"
        p_dir = Path(persist_dir) if persist_dir else None

        dw = DurableWorkflow(workflow_id=wf_id, persist_dir=p_dir)

        # Register all nodes as steps in the DurableWorkflow
        # Build dependency list per node from reverse edges
        layers = self.topological_sort()
        node_deps: dict[str, list[str]] = defaultdict(list)
        for _from, targets in self._edges.items():
            for t in targets:
                node_deps[t].append(_from)

        # Add steps in topological order so dependencies are always registered first
        for layer in layers:
            for nid in layer:
                node = self._nodes[nid]
                dw.add_step(
                    step_id=nid,
                    name=node.name,
                    depends_on=node_deps.get(nid, []),
                )

        t0 = time.monotonic()
        results: dict[str, Any] = {}
        failed_nodes: set[str] = set()

        for layer in layers:
            # Filter to nodes that are still runnable (not skipped due to upstream failure)
            runnable: list[str] = []
            for nid in layer:
                # Node already marked for skipping by upstream propagation
                if nid in failed_nodes:
                    step = dw.get_step(nid)
                    if step.status not in (StepStatus.FAILED, StepStatus.SKIPPED):
                        step.status = StepStatus.SKIPPED
                        dw.checkpoint()
                    continue
                # Check if any dependency failed
                deps = node_deps.get(nid, [])
                if any(d in failed_nodes for d in deps):
                    dw.get_step(nid).status = StepStatus.SKIPPED
                    dw.checkpoint()
                    self._propagate_skip(nid, failed_nodes, dw)
                    continue
                runnable.append(nid)

            if not runnable:
                continue

            # Execute layer concurrently
            coros = [
                self._run_node(nid, dw, results)
                for nid in runnable
            ]
            outcomes = await asyncio.gather(*coros, return_exceptions=True)

            for nid, outcome in zip(runnable, outcomes):
                step = dw.get_step(nid)

                if isinstance(outcome, Exception):
                    # mark_failed was already called inside _run_node for
                    # exceptions raised by the handler. But asyncio.gather
                    # can also return exceptions for unexpected failures.
                    if step.status != StepStatus.FAILED:
                        dw.mark_failed(nid, str(outcome))
                    failed_nodes.add(nid)
                    self._propagate_skip(nid, failed_nodes, dw)
                elif step.status == StepStatus.FAILED:
                    failed_nodes.add(nid)
                    self._propagate_skip(nid, failed_nodes, dw)
                else:
                    results[nid] = step.result

                # Fire callback
                if on_step_complete:
                    cb = on_step_complete(step)
                    if asyncio.iscoroutine(cb):
                        await cb

        elapsed = time.monotonic() - t0

        return {
            "results": results,
            "summary": dw.summary(),
            "elapsed_seconds": elapsed,
            "workflow_id": wf_id,
        }

    def _propagate_skip(
        self, failed_id: str, failed_set: set[str], dw: DurableWorkflow | None = None,
    ) -> None:
        """Mark all transitive dependents of a failed node for skipping."""
        queue: deque[str] = deque(self._edges.get(failed_id, []))
        while queue:
            nid = queue.popleft()
            if nid not in failed_set:
                failed_set.add(nid)
                if dw is not None:
                    step = dw.get_step(nid)
                    if step.status not in (StepStatus.FAILED, StepStatus.SKIPPED):
                        step.status = StepStatus.SKIPPED
                        dw.checkpoint()
                queue.extend(self._edges.get(nid, []))

    async def _run_node(
        self,
        node_id: str,
        dw: DurableWorkflow,
        results: dict[str, Any],
    ) -> None:
        """Execute a single node's handler function."""
        node = self._nodes[node_id]
        dw.mark_running(node_id)

        if node.handler_fn is None:
            # No handler -- treat as a pass-through node
            dw.mark_completed(node_id, result=None)
            return

        # Gather upstream results for this node
        upstream: dict[str, Any] = {}
        for dep_id in self._reverse.get(node_id, []):
            if dep_id in results:
                upstream[dep_id] = results[dep_id]

        try:
            result = node.handler_fn(upstream)
            if asyncio.iscoroutine(result):
                result = await result
            dw.mark_completed(node_id, result=result)
        except Exception as exc:
            dw.mark_failed(node_id, str(exc))
            raise
