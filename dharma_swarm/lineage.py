"""Data Lineage — Every output traces to its inputs.

Palantir's Funnel gives every data transformation a lineage DAG.
Anduril's Lattice tracks sensor→track→action provenance.
NATO JC3IEDM records reporting-data alongside effective-data.

This module gives dharma_swarm the same capability:
  - Every task execution records what it consumed and produced
  - Ancestor/descendant traversal for impact analysis
  - Root cause tracing (follow lineage back to original source)
  - Pipeline-aware: knows which Pipeline produced each artifact
  - SQLite-backed for persistence, async for non-blocking ops

Integration:
  logic_layer.py  — Pipeline records lineage edges automatically
  ontology.py     — Artifact IDs are OntologyObj IDs
  agent_runner.py — Wire into task completion to auto-record
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    from uuid import uuid4
    return uuid4().hex[:12]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LineageEdge(BaseModel):
    """Records that output artifacts were produced from input artifacts by a task.

    This is the atomic unit of provenance: task X consumed [A, B] and
    produced [C, D] at time T, executed by agent Y in pipeline Z.
    """
    edge_id: str = Field(default_factory=_new_id)
    task_id: str
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    agent: str = ""
    pipeline_id: str = ""
    pipeline_label: str = ""
    block_id: str = ""
    operation: str = ""  # e.g., "compute_rv", "archive", "design"
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageNode(BaseModel):
    """Summary of a single artifact's lineage position."""
    artifact_id: str
    produced_by: list[str] = Field(default_factory=list)  # edge IDs that created it
    consumed_by: list[str] = Field(default_factory=list)  # edge IDs that consumed it
    first_seen: str = ""
    last_seen: str = ""


class ImpactReport(BaseModel):
    """What downstream artifacts are affected if a given artifact changes."""
    root_artifact: str
    affected_artifacts: list[str] = Field(default_factory=list)
    affected_tasks: list[str] = Field(default_factory=list)
    depth: int = 0
    total_descendants: int = 0


class ProvenanceChain(BaseModel):
    """Full chain from an artifact back to its root sources."""
    artifact_id: str
    chain: list[LineageEdge] = Field(default_factory=list)
    root_sources: list[str] = Field(default_factory=list)
    depth: int = 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LINEAGE GRAPH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_edges (
    edge_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent TEXT DEFAULT '',
    pipeline_id TEXT DEFAULT '',
    pipeline_label TEXT DEFAULT '',
    block_id TEXT DEFAULT '',
    operation TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS lineage_inputs (
    edge_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    FOREIGN KEY (edge_id) REFERENCES lineage_edges(edge_id)
);

CREATE TABLE IF NOT EXISTS lineage_outputs (
    edge_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    FOREIGN KEY (edge_id) REFERENCES lineage_edges(edge_id)
);

CREATE INDEX IF NOT EXISTS idx_inputs_artifact ON lineage_inputs(artifact_id);
CREATE INDEX IF NOT EXISTS idx_outputs_artifact ON lineage_outputs(artifact_id);
CREATE INDEX IF NOT EXISTS idx_inputs_edge ON lineage_inputs(edge_id);
CREATE INDEX IF NOT EXISTS idx_outputs_edge ON lineage_outputs(edge_id);
CREATE INDEX IF NOT EXISTS idx_edges_task ON lineage_edges(task_id);
CREATE INDEX IF NOT EXISTS idx_edges_pipeline ON lineage_edges(pipeline_id);
"""


class LineageGraph:
    """SQLite-backed DAG of artifact dependencies.

    Thread-safe via per-call connections (SQLite handles locking).
    Async methods use synchronous SQLite under the hood — safe for
    the IO patterns in dharma_swarm (no concurrent write contention).

    Usage::

        graph = LineageGraph()
        graph.record(LineageEdge(
            task_id="task_01",
            input_artifacts=["prompts_v1", "model_config"],
            output_artifacts=["rv_results_001"],
            agent="researcher",
            operation="compute_rv",
        ))

        # What produced this result?
        chain = graph.provenance("rv_results_001")

        # What breaks if prompts change?
        impact = graph.impact("prompts_v1")
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            db_path = Path.home() / ".dharma" / "lineage.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Recording ─────────────────────────────────────────────────────

    def record(self, edge: LineageEdge) -> str:
        """Record a lineage edge.  Returns the edge ID."""
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO lineage_edges
                   (edge_id, task_id, agent, pipeline_id, pipeline_label,
                    block_id, operation, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge.edge_id, edge.task_id, edge.agent,
                    edge.pipeline_id, edge.pipeline_label,
                    edge.block_id, edge.operation, edge.timestamp,
                    json.dumps(edge.metadata),
                ),
            )
            for art_id in edge.input_artifacts:
                conn.execute(
                    "INSERT INTO lineage_inputs (edge_id, artifact_id) VALUES (?, ?)",
                    (edge.edge_id, art_id),
                )
            for art_id in edge.output_artifacts:
                conn.execute(
                    "INSERT INTO lineage_outputs (edge_id, artifact_id) VALUES (?, ?)",
                    (edge.edge_id, art_id),
                )
        return edge.edge_id

    def record_transformation(
        self,
        task_id: str,
        inputs: list[str],
        outputs: list[str],
        agent: str = "",
        operation: str = "",
        pipeline_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Convenience method for recording a transformation."""
        edge = LineageEdge(
            task_id=task_id,
            input_artifacts=inputs,
            output_artifacts=outputs,
            agent=agent,
            operation=operation,
            pipeline_id=pipeline_id,
            metadata=metadata or {},
        )
        return self.record(edge)

    # ── Querying ──────────────────────────────────────────────────────

    def _row_to_edge(self, row: tuple) -> LineageEdge:
        """Convert a DB row + its inputs/outputs to a LineageEdge."""
        edge_id = row[0]
        with self._conn() as conn:
            inputs = [
                r[0] for r in conn.execute(
                    "SELECT artifact_id FROM lineage_inputs WHERE edge_id = ?",
                    (edge_id,),
                ).fetchall()
            ]
            outputs = [
                r[0] for r in conn.execute(
                    "SELECT artifact_id FROM lineage_outputs WHERE edge_id = ?",
                    (edge_id,),
                ).fetchall()
            ]
        return LineageEdge(
            edge_id=row[0],
            task_id=row[1],
            agent=row[2] or "",
            pipeline_id=row[3] or "",
            pipeline_label=row[4] or "",
            block_id=row[5] or "",
            operation=row[6] or "",
            timestamp=row[7],
            metadata=json.loads(row[8]) if row[8] else {},
            input_artifacts=inputs,
            output_artifacts=outputs,
        )

    def get_edge(self, edge_id: str) -> LineageEdge | None:
        """Retrieve a single edge by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM lineage_edges WHERE edge_id = ?", (edge_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_edge(row)

    def edges_for_task(self, task_id: str) -> list[LineageEdge]:
        """Get all lineage edges for a task."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM lineage_edges WHERE task_id = ? ORDER BY timestamp",
                (task_id,),
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def edges_for_pipeline(self, pipeline_id: str) -> list[LineageEdge]:
        """Get all lineage edges for a pipeline execution."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM lineage_edges WHERE pipeline_id = ? ORDER BY timestamp",
                (pipeline_id,),
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def producers_of(self, artifact_id: str) -> list[LineageEdge]:
        """Get edges that produced this artifact (immediate parents)."""
        with self._conn() as conn:
            edge_ids = [
                r[0] for r in conn.execute(
                    "SELECT edge_id FROM lineage_outputs WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchall()
            ]
        if not edge_ids:
            return []
        with self._conn() as conn:
            placeholders = ",".join("?" * len(edge_ids))
            rows = conn.execute(
                f"SELECT * FROM lineage_edges WHERE edge_id IN ({placeholders})",
                edge_ids,
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def consumers_of(self, artifact_id: str) -> list[LineageEdge]:
        """Get edges that consumed this artifact (immediate children)."""
        with self._conn() as conn:
            edge_ids = [
                r[0] for r in conn.execute(
                    "SELECT edge_id FROM lineage_inputs WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchall()
            ]
        if not edge_ids:
            return []
        with self._conn() as conn:
            placeholders = ",".join("?" * len(edge_ids))
            rows = conn.execute(
                f"SELECT * FROM lineage_edges WHERE edge_id IN ({placeholders})",
                edge_ids,
            ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    # ── Traversal ─────────────────────────────────────────────────────

    def ancestors(self, artifact_id: str, max_depth: int = 50) -> list[LineageEdge]:
        """Walk backward: all edges in the provenance chain."""
        visited_edges: set[str] = set()
        result: list[LineageEdge] = []
        frontier = [artifact_id]
        depth = 0

        while frontier and depth < max_depth:
            next_frontier: list[str] = []
            for art_id in frontier:
                for edge in self.producers_of(art_id):
                    if edge.edge_id not in visited_edges:
                        visited_edges.add(edge.edge_id)
                        result.append(edge)
                        next_frontier.extend(edge.input_artifacts)
            frontier = next_frontier
            depth += 1

        return result

    def descendants(self, artifact_id: str, max_depth: int = 50) -> list[LineageEdge]:
        """Walk forward: all edges downstream of an artifact."""
        visited_edges: set[str] = set()
        result: list[LineageEdge] = []
        frontier = [artifact_id]
        depth = 0

        while frontier and depth < max_depth:
            next_frontier: list[str] = []
            for art_id in frontier:
                for edge in self.consumers_of(art_id):
                    if edge.edge_id not in visited_edges:
                        visited_edges.add(edge.edge_id)
                        result.append(edge)
                        next_frontier.extend(edge.output_artifacts)
            frontier = next_frontier
            depth += 1

        return result

    def provenance(self, artifact_id: str, max_depth: int = 50) -> ProvenanceChain:
        """Full provenance chain from artifact back to root sources."""
        chain = self.ancestors(artifact_id, max_depth=max_depth)

        # Root sources: inputs that have no producers
        all_inputs: set[str] = set()
        all_outputs: set[str] = set()
        for edge in chain:
            all_inputs.update(edge.input_artifacts)
            all_outputs.update(edge.output_artifacts)
        root_sources = sorted(all_inputs - all_outputs)

        return ProvenanceChain(
            artifact_id=artifact_id,
            chain=chain,
            root_sources=root_sources,
            depth=len(chain),
        )

    def impact(self, artifact_id: str, max_depth: int = 50) -> ImpactReport:
        """What downstream artifacts and tasks are affected if this changes."""
        desc_edges = self.descendants(artifact_id, max_depth=max_depth)

        affected_artifacts: set[str] = set()
        affected_tasks: set[str] = set()
        max_d = 0
        frontier_depth: dict[str, int] = {artifact_id: 0}

        for edge in desc_edges:
            task_depth = 0
            for inp in edge.input_artifacts:
                if inp in frontier_depth:
                    task_depth = max(task_depth, frontier_depth[inp] + 1)
            affected_tasks.add(edge.task_id)
            for out in edge.output_artifacts:
                affected_artifacts.add(out)
                frontier_depth[out] = task_depth
                max_d = max(max_d, task_depth)

        return ImpactReport(
            root_artifact=artifact_id,
            affected_artifacts=sorted(affected_artifacts),
            affected_tasks=sorted(affected_tasks),
            depth=max_d,
            total_descendants=len(affected_artifacts),
        )

    def root_causes(self, artifact_id: str) -> list[str]:
        """Trace to the original source inputs (leaves of ancestor DAG)."""
        return self.provenance(artifact_id).root_sources

    # ── Introspection ─────────────────────────────────────────────────

    def stats(self) -> dict[str, int]:
        """Basic statistics about the lineage graph."""
        with self._conn() as conn:
            edges = conn.execute("SELECT COUNT(*) FROM lineage_edges").fetchone()[0]
            inputs = conn.execute("SELECT COUNT(*) FROM lineage_inputs").fetchone()[0]
            outputs = conn.execute("SELECT COUNT(*) FROM lineage_outputs").fetchone()[0]
            unique_artifacts = conn.execute(
                """SELECT COUNT(DISTINCT artifact_id) FROM (
                    SELECT artifact_id FROM lineage_inputs
                    UNION
                    SELECT artifact_id FROM lineage_outputs
                )"""
            ).fetchone()[0]
            pipelines = conn.execute(
                "SELECT COUNT(DISTINCT pipeline_id) FROM lineage_edges WHERE pipeline_id != ''"
            ).fetchone()[0]
        return {
            "total_edges": edges,
            "total_input_refs": inputs,
            "total_output_refs": outputs,
            "unique_artifacts": unique_artifacts,
            "unique_pipelines": pipelines,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        s = self.stats()
        return (
            f"Lineage Graph: {s['total_edges']} edges, "
            f"{s['unique_artifacts']} artifacts, "
            f"{s['unique_pipelines']} pipelines"
        )

    def clear(self) -> None:
        """Clear all lineage data.  Use with caution."""
        with self._conn() as conn:
            conn.execute("DELETE FROM lineage_inputs")
            conn.execute("DELETE FROM lineage_outputs")
            conn.execute("DELETE FROM lineage_edges")
