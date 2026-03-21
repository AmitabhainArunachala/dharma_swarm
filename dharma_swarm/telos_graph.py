"""Telos Graph -- strategic objective DAG with causal hypotheses.

Part of the Graph Nexus architecture.  Tracks strategic objectives, key
results, strategies, and causal hypotheses in a directed acyclic graph.
Persistence follows the same JSONL pattern as ``archive.py``.

Perspectives are adapted from Kaplan-Norton's Strategy Map for dharma_swarm:
Purpose, Stakeholder, Process, Foundation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TelosPerspective(str, Enum):
    """Strategy Map perspectives, adapted from Kaplan-Norton for dharma_swarm."""

    PURPOSE = "purpose"          # Why does dharma_swarm exist? (Moksha, Jagat Kalyan)
    STAKEHOLDER = "stakeholder"  # What must users/agents experience?
    PROCESS = "process"          # What processes must excel?
    FOUNDATION = "foundation"    # What capabilities must grow?


class ObjectiveStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PARTIALLY_MET = "partially_met"
    ACHIEVED = "achieved"
    BLOCKED = "blocked"
    DEPRECATED = "deprecated"


class HypothesisStatus(str, Enum):
    UNTESTED = "untested"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TelosObjective(BaseModel):
    """A strategic objective in the telos graph."""

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    perspective: TelosPerspective = TelosPerspective.PROCESS
    status: ObjectiveStatus = ObjectiveStatus.PROPOSED
    progress: float = 0.0  # 0.0 to 1.0
    owner: str = ""
    priority: int = 5  # 1-10, higher = more important
    target_date: str | None = None  # ISO date string
    parent_id: str | None = None  # For hierarchical objectives
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TelosKeyResult(BaseModel):
    """A measurable outcome linked to an objective."""

    id: str = Field(default_factory=_new_id)
    objective_id: str
    name: str
    metric_type: str = "percentage"  # percentage, count, boolean
    current_value: float = 0.0
    target_value: float = 1.0
    unit: str = ""
    measurement_method: str = ""
    last_measured: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TelosStrategy(BaseModel):
    """A concrete strategy or initiative toward an objective."""

    id: str = Field(default_factory=_new_id)
    objective_id: str
    name: str
    description: str = ""
    actions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    status: ObjectiveStatus = ObjectiveStatus.PROPOSED
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TelosHypothesis(BaseModel):
    """A causal hypothesis linking actions to outcomes."""

    id: str = Field(default_factory=_new_id)
    statement: str
    source_id: str = ""  # Objective/Strategy this hypothesis is about
    target_id: str = ""  # Objective this hypothesis impacts
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    confidence: float = 0.5  # Bayesian posterior
    status: HypothesisStatus = HypothesisStatus.UNTESTED
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TelosEdge(BaseModel):
    """A causal edge in the telos DAG."""

    source_id: str
    target_id: str
    edge_type: str  # "enables", "blocks", "contributes_to", "depends_on", "measures"
    strength: float = 1.0
    confidence: float = 1.0
    description: str = ""


# ---------------------------------------------------------------------------
# JSONL persistence helpers
# ---------------------------------------------------------------------------

async def _load_jsonl(path: Path, model_cls: type[BaseModel]) -> list[BaseModel]:
    """Read a JSONL file and return a list of Pydantic model instances."""
    if not path.exists():
        return []

    import aiofiles  # late import

    items: list[BaseModel] = []
    async with aiofiles.open(path, "r") as f:
        async for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                items.append(model_cls.model_validate(data))
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                logger.warning("Skipping malformed JSONL line in %s: %s", path.name, exc)
                continue
    return items


async def _save_jsonl(path: Path, items: Sequence[BaseModel]) -> None:
    """Rewrite a JSONL file from a list of Pydantic model instances."""
    import aiofiles  # late import

    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w") as f:
        for item in items:
            await f.write(item.model_dump_json() + "\n")


# ---------------------------------------------------------------------------
# TelosGraph
# ---------------------------------------------------------------------------


class TelosGraph:
    """Strategic objective graph with causal DAG structure.

    Persistence: JSONL files in ``~/.dharma/telos/``

    - ``objectives.jsonl``
    - ``key_results.jsonl``
    - ``strategies.jsonl``
    - ``hypotheses.jsonl``
    - ``edges.jsonl``
    """

    def __init__(self, telos_dir: Path | None = None) -> None:
        self._dir = Path(telos_dir) if telos_dir is not None else (Path.home() / ".dharma" / "telos")
        self._objectives: dict[str, TelosObjective] = {}
        self._key_results: dict[str, TelosKeyResult] = {}
        self._strategies: dict[str, TelosStrategy] = {}
        self._hypotheses: dict[str, TelosHypothesis] = {}
        self._edges: list[TelosEdge] = []
        self._write_lock = asyncio.Lock()

    # -- persistence ---------------------------------------------------------

    async def load(self) -> None:
        """Load all JSONL files into memory."""
        self._objectives.clear()
        self._key_results.clear()
        self._strategies.clear()
        self._hypotheses.clear()
        self._edges.clear()

        obj_path = self._dir / "objectives.jsonl"
        kr_path = self._dir / "key_results.jsonl"
        strat_path = self._dir / "strategies.jsonl"
        hyp_path = self._dir / "hypotheses.jsonl"
        edge_path = self._dir / "edges.jsonl"

        for obj in await _load_jsonl(obj_path, TelosObjective):
            assert isinstance(obj, TelosObjective)
            self._objectives[obj.id] = obj

        for kr in await _load_jsonl(kr_path, TelosKeyResult):
            assert isinstance(kr, TelosKeyResult)
            self._key_results[kr.id] = kr

        for strat in await _load_jsonl(strat_path, TelosStrategy):
            assert isinstance(strat, TelosStrategy)
            self._strategies[strat.id] = strat

        for hyp in await _load_jsonl(hyp_path, TelosHypothesis):
            assert isinstance(hyp, TelosHypothesis)
            self._hypotheses[hyp.id] = hyp

        for edge in await _load_jsonl(edge_path, TelosEdge):
            assert isinstance(edge, TelosEdge)
            self._edges.append(edge)

        logger.info(
            "TelosGraph loaded: %d objectives, %d KRs, %d strategies, "
            "%d hypotheses, %d edges",
            len(self._objectives),
            len(self._key_results),
            len(self._strategies),
            len(self._hypotheses),
            len(self._edges),
        )

    async def save(self) -> None:
        """Save all state to JSONL files (full rewrite).

        Protected by _write_lock to prevent concurrent coroutines from
        clobbering each other's writes in daemon mode.
        """
        async with self._write_lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            await _save_jsonl(
                self._dir / "objectives.jsonl",
                list(self._objectives.values()),
            )
            await _save_jsonl(
                self._dir / "key_results.jsonl",
                list(self._key_results.values()),
            )
            await _save_jsonl(
                self._dir / "strategies.jsonl",
                list(self._strategies.values()),
            )
            await _save_jsonl(
                self._dir / "hypotheses.jsonl",
                list(self._hypotheses.values()),
            )
            await _save_jsonl(self._dir / "edges.jsonl", self._edges)
            logger.debug("TelosGraph saved to %s", self._dir)

    # -- CRUD: objectives ----------------------------------------------------

    async def add_objective(self, obj: TelosObjective) -> TelosObjective:
        """Add an objective and persist."""
        self._objectives[obj.id] = obj
        await self.save()
        logger.info("Added objective %s: %s", obj.id[:8], obj.name)
        return obj

    async def update_objective(
        self, obj_id: str, **updates: Any
    ) -> TelosObjective | None:
        """Update fields on an existing objective and persist.

        Returns the updated objective, or ``None`` if not found.
        """
        obj = self._objectives.get(obj_id)
        if obj is None:
            return None
        for key, value in updates.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        obj.updated_at = _utc_now()
        await self.save()
        return obj

    async def get_objective(self, obj_id: str) -> TelosObjective | None:
        """Return an objective by id, or ``None``."""
        return self._objectives.get(obj_id)

    def list_objectives(
        self,
        perspective: TelosPerspective | None = None,
        status: ObjectiveStatus | None = None,
    ) -> list[TelosObjective]:
        """List objectives with optional perspective/status filters."""
        objs = list(self._objectives.values())
        if perspective is not None:
            objs = [o for o in objs if o.perspective == perspective]
        if status is not None:
            objs = [o for o in objs if o.status == status]
        objs.sort(key=lambda o: o.priority, reverse=True)
        return objs

    async def propose_objective(
        self,
        name: str,
        description: str,
        parent_id: str | None = None,
        proposed_by: str = "agent",
        perspective: TelosPerspective = TelosPerspective.PROCESS,
        priority: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> TelosObjective:
        """Agents can propose new objectives autonomously.

        Status starts as PROPOSED — requires human approval (status change
        to ACTIVE via ``update_objective()``) before the director prioritizes
        it.  This enables the telos tree to GROW through agent discovery
        while keeping Dhyana as the approval gate.
        """
        obj = TelosObjective(
            name=name,
            description=description,
            perspective=perspective,
            status=ObjectiveStatus.PROPOSED,
            priority=priority,
            parent_id=parent_id,
            metadata={**(metadata or {}), "proposed_by": proposed_by},
        )
        self._objectives[obj.id] = obj
        await self.save()
        logger.info(
            "Proposed objective %s: %s (by %s, awaiting approval)",
            obj.id[:8],
            name,
            proposed_by,
        )
        return obj

    def list_by_domain(self, domain: str) -> list[TelosObjective]:
        """List objectives filtered by metadata.domain."""
        return [
            o for o in self._objectives.values()
            if o.metadata.get("domain") == domain
        ]

    def domain_summary(self) -> dict[str, int]:
        """Count objectives per domain."""
        domains: dict[str, int] = {}
        for o in self._objectives.values():
            d = o.metadata.get("domain", "uncategorized")
            domains[d] = domains.get(d, 0) + 1
        return dict(sorted(domains.items()))

    def highest_leverage(self, top_n: int = 10) -> list[TelosObjective]:
        """Return top N objectives by priority × inverse progress.

        These are the highest-priority, least-progressed ACTIVE objectives —
        the ones where a small push creates the most movement.
        """
        active = [
            o for o in self._objectives.values()
            if o.status in (ObjectiveStatus.ACTIVE, ObjectiveStatus.PROPOSED)
        ]
        active.sort(
            key=lambda o: o.priority * (1.0 - o.progress),
            reverse=True,
        )
        return active[:top_n]

    # -- CRUD: key results ---------------------------------------------------

    async def add_key_result(self, kr: TelosKeyResult) -> TelosKeyResult:
        """Add a key result and persist."""
        self._key_results[kr.id] = kr
        await self.save()
        return kr

    async def update_key_result(
        self, kr_id: str, **updates: Any
    ) -> TelosKeyResult | None:
        """Update fields on a key result and persist.

        Returns the updated key result, or ``None`` if not found.
        """
        kr = self._key_results.get(kr_id)
        if kr is None:
            return None
        for key, value in updates.items():
            if hasattr(kr, key):
                setattr(kr, key, value)
        kr.last_measured = _utc_now()
        await self.save()
        return kr

    def key_results_for(self, objective_id: str) -> list[TelosKeyResult]:
        """Return all key results linked to an objective."""
        return [
            kr for kr in self._key_results.values()
            if kr.objective_id == objective_id
        ]

    # -- CRUD: strategies ----------------------------------------------------

    async def add_strategy(self, strategy: TelosStrategy) -> TelosStrategy:
        """Add a strategy and persist."""
        self._strategies[strategy.id] = strategy
        await self.save()
        return strategy

    def strategies_for(self, objective_id: str) -> list[TelosStrategy]:
        """Return all strategies linked to an objective."""
        return [
            s for s in self._strategies.values()
            if s.objective_id == objective_id
        ]

    # -- CRUD: hypotheses ----------------------------------------------------

    async def add_hypothesis(self, hyp: TelosHypothesis) -> TelosHypothesis:
        """Add a hypothesis and persist."""
        self._hypotheses[hyp.id] = hyp
        await self.save()
        return hyp

    async def update_hypothesis(
        self, hyp_id: str, **updates: Any
    ) -> TelosHypothesis | None:
        """Update fields on a hypothesis and persist.

        Returns the updated hypothesis, or ``None`` if not found.
        """
        hyp = self._hypotheses.get(hyp_id)
        if hyp is None:
            return None
        for key, value in updates.items():
            if hasattr(hyp, key):
                setattr(hyp, key, value)
        await self.save()
        return hyp

    # -- edges (DAG) ---------------------------------------------------------

    async def add_edge(self, edge: TelosEdge) -> None:
        """Add a causal edge and persist."""
        self._edges.append(edge)
        await self.save()

    def edges_from(self, node_id: str) -> list[TelosEdge]:
        """Return all edges originating from *node_id*."""
        return [e for e in self._edges if e.source_id == node_id]

    def edges_to(self, node_id: str) -> list[TelosEdge]:
        """Return all edges targeting *node_id*."""
        return [e for e in self._edges if e.target_id == node_id]

    # -- queries -------------------------------------------------------------

    def blocked_objectives(self) -> list[TelosObjective]:
        """Objectives with status BLOCKED."""
        return self.list_objectives(status=ObjectiveStatus.BLOCKED)

    def active_objectives(self) -> list[TelosObjective]:
        """Objectives with status ACTIVE."""
        return self.list_objectives(status=ObjectiveStatus.ACTIVE)

    def untested_hypotheses(self, min_priority: int = 0) -> list[TelosHypothesis]:
        """Hypotheses that haven't been validated yet.

        If *min_priority* > 0, only return hypotheses whose linked source
        objective has priority >= *min_priority*.
        """
        results: list[TelosHypothesis] = []
        for hyp in self._hypotheses.values():
            if hyp.status != HypothesisStatus.UNTESTED:
                continue
            if min_priority > 0 and hyp.source_id:
                obj = self._objectives.get(hyp.source_id)
                if obj is None or obj.priority < min_priority:
                    continue
            results.append(hyp)
        return results

    def objective_progress(self, obj_id: str) -> float:
        """Compute progress from key results.

        Returns the average of ``current_value / target_value`` across all
        key results linked to the objective.  If no key results exist,
        falls back to the objective's own ``progress`` field.
        """
        krs = self.key_results_for(obj_id)
        if not krs:
            obj = self._objectives.get(obj_id)
            return obj.progress if obj else 0.0

        ratios: list[float] = []
        for kr in krs:
            if kr.target_value != 0.0:
                ratios.append(min(kr.current_value / kr.target_value, 1.0))
            else:
                ratios.append(1.0 if kr.current_value > 0 else 0.0)
        return sum(ratios) / len(ratios)

    def causal_chain(
        self, start_id: str, max_depth: int = 5
    ) -> list[list[str]]:
        """Trace causal chains from *start_id* through ``enables`` edges.

        Uses BFS with cycle detection.  Returns a list of paths, where
        each path is a list of node ids from *start_id* to a leaf.
        """
        # Build adjacency map for "enables" edges
        adjacency: dict[str, list[str]] = {}
        for edge in self._edges:
            if edge.edge_type == "enables":
                adjacency.setdefault(edge.source_id, []).append(edge.target_id)

        paths: list[list[str]] = []
        queue: deque[list[str]] = deque([[start_id]])

        while queue:
            path = queue.popleft()
            if len(path) > max_depth + 1:
                continue

            current = path[-1]
            neighbors = adjacency.get(current, [])
            extended = False

            for neighbor in neighbors:
                if neighbor in path:
                    # Cycle detected -- skip
                    continue
                queue.append(path + [neighbor])
                extended = True

            if not extended:
                # Leaf node -- record completed path
                paths.append(path)

        return paths

    def strategy_map_summary(self) -> dict[str, Any]:
        """Return structured summary for CLI display.

        Objectives are grouped by perspective, each with computed progress
        and linked key results.
        """
        summary: dict[str, Any] = {}

        for perspective in TelosPerspective:
            objs = self.list_objectives(perspective=perspective)
            perspective_data: list[dict[str, Any]] = []
            for obj in objs:
                krs = self.key_results_for(obj.id)
                kr_data = [
                    {
                        "name": kr.name,
                        "current": kr.current_value,
                        "target": kr.target_value,
                        "unit": kr.unit,
                    }
                    for kr in krs
                ]
                perspective_data.append(
                    {
                        "id": obj.id,
                        "name": obj.name,
                        "status": obj.status.value,
                        "priority": obj.priority,
                        "progress": round(self.objective_progress(obj.id), 3),
                        "target_date": obj.target_date,
                        "key_results": kr_data,
                    }
                )
            summary[perspective.value] = perspective_data

        summary["_totals"] = {
            "objectives": len(self._objectives),
            "key_results": len(self._key_results),
            "strategies": len(self._strategies),
            "hypotheses": len(self._hypotheses),
            "edges": len(self._edges),
        }
        return summary

    # -- seed data -----------------------------------------------------------

    async def seed_initial_objectives(self) -> None:
        """Create initial dharma_swarm strategic objectives if none exist.

        Idempotent -- does nothing if objectives are already loaded.
        """
        if self._objectives:
            return

        seed_objectives = [
            TelosObjective(
                name="Jagat Kalyan -- Universal Welfare",
                description=(
                    "The ultimate telos: universal welfare through dharmic AI. "
                    "Every system, every agent, every action serves this purpose."
                ),
                perspective=TelosPerspective.PURPOSE,
                status=ObjectiveStatus.ACTIVE,
                priority=10,
            ),
            TelosObjective(
                name="Publish R_V Paper at COLM 2026",
                description=(
                    "Submit and publish 'Geometric Signatures of Self-Referential "
                    "Processing in Transformer Representations' at COLM 2026."
                ),
                perspective=TelosPerspective.PURPOSE,
                status=ObjectiveStatus.ACTIVE,
                priority=9,
                target_date="2026-03-31",
            ),
            TelosObjective(
                name="Enable autonomous agent coordination",
                description=(
                    "Agents discover, negotiate, and coordinate through the "
                    "ontology without manual wiring. Stigmergy-first."
                ),
                perspective=TelosPerspective.STAKEHOLDER,
                status=ObjectiveStatus.ACTIVE,
                priority=7,
            ),
            TelosObjective(
                name="Achieve cross-graph knowledge integration",
                description=(
                    "Unify knowledge across Graph Nexus layers: telos, ontology, "
                    "evolution archive, stigmergy, and memory lattice."
                ),
                perspective=TelosPerspective.PROCESS,
                status=ObjectiveStatus.PROPOSED,
                priority=6,
            ),
            TelosObjective(
                name="Build unified graph abstraction",
                description=(
                    "Common traversal, query, and persistence primitives across "
                    "all graph-structured subsystems in dharma_swarm."
                ),
                perspective=TelosPerspective.FOUNDATION,
                status=ObjectiveStatus.PROPOSED,
                priority=5,
            ),
        ]

        for obj in seed_objectives:
            self._objectives[obj.id] = obj

        await self.save()
        logger.info("Seeded %d initial telos objectives", len(seed_objectives))
