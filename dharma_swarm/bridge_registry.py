"""Unified Bridge Edge Registry -- cross-graph connector for Graph Nexus.

Every graph in dharma_swarm (semantic, catalytic, temporal, lineage, telos,
runtime_facts, field, ontology) lives in its own module with its own schema.
This registry stores the *bridge edges* that connect nodes across graphs,
enabling cross-graph traversal, impact analysis, and coherence checks.

Architecture:
    ConceptGraph  <--bridge--> CatalyticGraph
    TemporalGraph <--bridge--> TelosGraph
    LineageGraph  <--bridge--> OntologyRegistry
    ... any origin to any origin via typed BridgeEdge

Persistence: ``~/.dharma/db/bridges.db`` (SQLite, WAL mode).

Integration:
    - semantic_gravity.py  -- ConceptGraph nodes can bridge to telos goals
    - catalytic_graph.py   -- CatalyticGraph edges can bridge to runtime facts
    - temporal_graph.py    -- TemporalKnowledgeGraph concepts bridge to lineage
    - lineage.py           -- LineageGraph artifacts bridge to ontology objects
    - telos_gates.py       -- Telos goals bridge to semantic concepts
    - runtime_state.py     -- Runtime facts bridge to catalytic observations
    - field_graph.py       -- Field intelligence bridges to semantic concepts
    - ontology.py          -- OntologyRegistry objects bridge everywhere
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Generator

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GraphOrigin(str, Enum):
    """Which graph subsystem a node belongs to."""

    SEMANTIC = "semantic"              # ConceptGraph (semantic_gravity.py)
    CATALYTIC = "catalytic"            # CatalyticGraph (catalytic_graph.py)
    TEMPORAL = "temporal"              # TemporalKnowledgeGraph (temporal_graph.py)
    LINEAGE = "lineage"                # LineageGraph (lineage.py)
    TELOS = "telos"                    # TelosGraph (telos_graph.py) -- NEW
    RUNTIME_FACTS = "runtime_facts"    # memory_facts in runtime_state.py
    FIELD = "field"                    # FieldGraph (field_graph.py)
    ONTOLOGY = "ontology"              # OntologyRegistry (ontology.py)


class BridgeEdgeKind(str, Enum):
    """Typed relationship across graph boundaries.

    Grouped by the domains they typically bridge, but any edge kind
    can connect any pair of GraphOrigins.
    """

    # Code <-> Semantic
    IMPLEMENTS_CONCEPT = "implements_concept"
    REFERENCES_CONCEPT = "references_concept"

    # Semantic <-> Runtime
    CONCEPT_OBSERVED = "concept_observed"
    CONCEPT_EMERGED = "concept_emerged"

    # Runtime <-> Telos
    ADVANCES_GOAL = "advances_goal"
    BLOCKS_GOAL = "blocks_goal"
    EVIDENCE_FOR = "evidence_for"

    # Semantic <-> Telos
    CONCEPT_REQUIRED_BY = "concept_required_by"

    # Catalytic
    ENABLES = "enables"
    VALIDATES = "validates"

    # Generic
    RELATES_TO = "relates_to"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class BridgeEdge(BaseModel):
    """A typed, weighted edge connecting nodes across two different graphs.

    Attributes:
        edge_id: Unique identifier (auto-generated 16-char hex).
        source_graph: Which graph subsystem the source node belongs to.
        source_id: Node identifier within the source graph.
        target_graph: Which graph subsystem the target node belongs to.
        target_id: Node identifier within the target graph.
        edge_type: Semantic relationship type.
        confidence: Weight in [0.0, 1.0]. Decays over time, boosted on
            re-observation.
        discovered_by: Agent or subsystem that created this edge.
        discovered_at: UTC timestamp of creation/last update.
        metadata: Arbitrary key-value pairs for provenance, evidence, etc.
    """

    edge_id: str = Field(default_factory=_new_id)
    source_graph: GraphOrigin
    source_id: str
    target_graph: GraphOrigin
    target_id: str
    edge_type: BridgeEdgeKind
    confidence: float = 0.5
    discovered_by: str = ""
    discovered_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS bridge_edges (
    edge_id TEXT PRIMARY KEY,
    source_graph TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_graph TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    discovered_by TEXT DEFAULT '',
    discovered_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    UNIQUE(source_graph, source_id, target_graph, target_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_bridge_source ON bridge_edges(source_graph, source_id);
CREATE INDEX IF NOT EXISTS idx_bridge_target ON bridge_edges(target_graph, target_id);
CREATE INDEX IF NOT EXISTS idx_bridge_type ON bridge_edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_bridge_confidence ON bridge_edges(confidence);
"""


# ---------------------------------------------------------------------------
# Row conversion
# ---------------------------------------------------------------------------


def _row_to_edge(row: sqlite3.Row) -> BridgeEdge:
    """Convert a sqlite3.Row into a BridgeEdge model.

    Handles malformed metadata gracefully by falling back to an empty dict.

    Args:
        row: A sqlite3.Row with bridge_edges column names.

    Returns:
        Hydrated BridgeEdge instance.
    """
    raw_meta = row["metadata"] or "{}"
    try:
        meta = json.loads(raw_meta)
    except (json.JSONDecodeError, TypeError):
        meta = {}

    raw_ts = row["discovered_at"] or ""
    try:
        ts = datetime.fromisoformat(raw_ts)
    except (ValueError, TypeError):
        ts = _utc_now()

    try:
        source_graph = GraphOrigin(row["source_graph"])
    except ValueError:
        source_graph = GraphOrigin.ONTOLOGY

    try:
        target_graph = GraphOrigin(row["target_graph"])
    except ValueError:
        target_graph = GraphOrigin.ONTOLOGY

    try:
        edge_type = BridgeEdgeKind(row["edge_type"])
    except ValueError:
        edge_type = BridgeEdgeKind.RELATES_TO

    return BridgeEdge(
        edge_id=row["edge_id"],
        source_graph=source_graph,
        source_id=row["source_id"],
        target_graph=target_graph,
        target_id=row["target_id"],
        edge_type=edge_type,
        confidence=float(row["confidence"] or 0.5),
        discovered_by=row["discovered_by"] or "",
        discovered_at=ts,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class BridgeRegistry:
    """SQLite-backed registry of cross-graph bridge edges.

    Provides CRUD operations, cross-graph queries, health diagnostics,
    and stale-edge pruning.  All methods are async for interface compatibility
    with the swarm's async orchestration layer, but use synchronous sqlite3
    under the hood (fast enough for this scale, consistent with
    temporal_graph.py and lineage.py patterns).

    Usage::

        registry = BridgeRegistry()
        await registry.init()

        await registry.upsert(BridgeEdge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="autopoiesis",
            target_graph=GraphOrigin.TELOS,
            target_id="goal_moksha",
            edge_type=BridgeEdgeKind.CONCEPT_REQUIRED_BY,
            confidence=0.85,
            discovered_by="semantic_scanner",
        ))

        bridges = await registry.find_bridges(GraphOrigin.SEMANTIC, "autopoiesis")
        stats = await registry.health()
        await registry.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else (Path.home() / ".dharma" / "db" / "bridges.db")
        self._conn: sqlite3.Connection | None = None

    # -- Connection management -----------------------------------------------

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection with row_factory and WAL mode set.

        Uses a persistent connection stored on the instance.  Creates it
        on first use.  The contextmanager commits on clean exit but does
        NOT close the connection (that happens in ``close()``).
        """
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                logger.debug("Bridge registry rollback failed", exc_info=True)
            raise

    # -- Lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        """Create tables and indexes if they don't already exist.

        Safe to call multiple times (all DDL uses ``IF NOT EXISTS``).
        """
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
            logger.info("BridgeRegistry initialized at %s", self._db_path)
        except Exception as exc:
            logger.error("BridgeRegistry init failed: %s", exc)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as exc:
                logger.warning("BridgeRegistry close error: %s", exc)
            finally:
                self._conn = None

    # -- Write operations ----------------------------------------------------

    async def upsert(self, edge: BridgeEdge) -> None:
        """Insert or update a bridge edge.

        On conflict (same source_graph, source_id, target_graph, target_id,
        edge_type), updates confidence, metadata, discovered_by, and
        discovered_at to the new values.

        Args:
            edge: The BridgeEdge to persist.
        """
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO bridge_edges
                       (edge_id, source_graph, source_id, target_graph, target_id,
                        edge_type, confidence, discovered_by, discovered_at, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(source_graph, source_id, target_graph, target_id, edge_type)
                       DO UPDATE SET
                           confidence = excluded.confidence,
                           discovered_by = excluded.discovered_by,
                           discovered_at = excluded.discovered_at,
                           metadata = excluded.metadata""",
                    (
                        edge.edge_id,
                        edge.source_graph.value,
                        edge.source_id,
                        edge.target_graph.value,
                        edge.target_id,
                        edge.edge_type.value,
                        edge.confidence,
                        edge.discovered_by,
                        edge.discovered_at.isoformat(),
                        json.dumps(edge.metadata),
                    ),
                )
        except Exception as exc:
            logger.error("BridgeRegistry upsert failed for edge %s: %s", edge.edge_id, exc)

    async def upsert_many(self, edges: list[BridgeEdge]) -> int:
        """Batch upsert multiple bridge edges in a single transaction.

        Args:
            edges: List of BridgeEdge models to persist.

        Returns:
            Number of edges successfully written.
        """
        if not edges:
            return 0
        written = 0
        try:
            with self._connect() as conn:
                for edge in edges:
                    try:
                        conn.execute(
                            """INSERT INTO bridge_edges
                               (edge_id, source_graph, source_id, target_graph, target_id,
                                edge_type, confidence, discovered_by, discovered_at, metadata)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                               ON CONFLICT(source_graph, source_id, target_graph, target_id, edge_type)
                               DO UPDATE SET
                                   confidence = excluded.confidence,
                                   discovered_by = excluded.discovered_by,
                                   discovered_at = excluded.discovered_at,
                                   metadata = excluded.metadata""",
                            (
                                edge.edge_id,
                                edge.source_graph.value,
                                edge.source_id,
                                edge.target_graph.value,
                                edge.target_id,
                                edge.edge_type.value,
                                edge.confidence,
                                edge.discovered_by,
                                edge.discovered_at.isoformat(),
                                json.dumps(edge.metadata),
                            ),
                        )
                        written += 1
                    except Exception as exc:
                        logger.warning("Skipping edge %s: %s", edge.edge_id, exc)
        except Exception as exc:
            logger.error("BridgeRegistry upsert_many failed: %s", exc)
        return written

    # -- Read operations -----------------------------------------------------

    async def get(self, edge_id: str) -> BridgeEdge | None:
        """Retrieve a single bridge edge by its ID.

        Args:
            edge_id: The unique edge identifier.

        Returns:
            BridgeEdge if found, None otherwise.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM bridge_edges WHERE edge_id = ?",
                    (edge_id,),
                ).fetchone()
            if row is None:
                return None
            return _row_to_edge(row)
        except Exception as exc:
            logger.error("BridgeRegistry get(%s) failed: %s", edge_id, exc)
            return None

    async def find_bridges(
        self,
        graph: GraphOrigin,
        node_id: str,
    ) -> list[BridgeEdge]:
        """Find all bridge edges connected to a node (as source or target).

        Args:
            graph: The graph subsystem the node belongs to.
            node_id: The node identifier within that graph.

        Returns:
            List of BridgeEdge instances touching this node from either side.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT * FROM bridge_edges
                       WHERE (source_graph = ? AND source_id = ?)
                          OR (target_graph = ? AND target_id = ?)
                       ORDER BY confidence DESC""",
                    (graph.value, node_id, graph.value, node_id),
                ).fetchall()
            return [_row_to_edge(r) for r in rows]
        except Exception as exc:
            logger.error("BridgeRegistry find_bridges failed: %s", exc)
            return []

    async def find_by_type(
        self,
        edge_type: BridgeEdgeKind,
        min_confidence: float = 0.0,
    ) -> list[BridgeEdge]:
        """Find all bridges of a given type, optionally filtered by confidence.

        Args:
            edge_type: The relationship type to filter on.
            min_confidence: Minimum confidence threshold (inclusive).

        Returns:
            List of matching BridgeEdge instances ordered by confidence desc.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT * FROM bridge_edges
                       WHERE edge_type = ? AND confidence >= ?
                       ORDER BY confidence DESC""",
                    (edge_type.value, min_confidence),
                ).fetchall()
            return [_row_to_edge(r) for r in rows]
        except Exception as exc:
            logger.error("BridgeRegistry find_by_type failed: %s", exc)
            return []

    async def query_across(
        self,
        source_graph: GraphOrigin,
        source_id: str,
        target_graph: GraphOrigin | None = None,
    ) -> list[BridgeEdge]:
        """Find cross-graph connections from a specific source node.

        Optionally restrict to edges landing in a specific target graph.

        Args:
            source_graph: Origin graph.
            source_id: Node ID within the origin graph.
            target_graph: If provided, only return edges to this graph.

        Returns:
            List of BridgeEdge instances from the source, ordered by
            confidence descending.
        """
        try:
            with self._connect() as conn:
                if target_graph is not None:
                    rows = conn.execute(
                        """SELECT * FROM bridge_edges
                           WHERE source_graph = ? AND source_id = ?
                             AND target_graph = ?
                           ORDER BY confidence DESC""",
                        (source_graph.value, source_id, target_graph.value),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM bridge_edges
                           WHERE source_graph = ? AND source_id = ?
                           ORDER BY confidence DESC""",
                        (source_graph.value, source_id),
                    ).fetchall()
            return [_row_to_edge(r) for r in rows]
        except Exception as exc:
            logger.error("BridgeRegistry query_across failed: %s", exc)
            return []

    async def all_edges(self, limit: int = 1000) -> list[BridgeEdge]:
        """Return all bridge edges up to a limit.

        Args:
            limit: Maximum number of edges to return.

        Returns:
            List of BridgeEdge instances ordered by discovered_at desc.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT * FROM bridge_edges
                       ORDER BY discovered_at DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [_row_to_edge(r) for r in rows]
        except Exception as exc:
            logger.error("BridgeRegistry all_edges failed: %s", exc)
            return []

    # -- Aggregation ---------------------------------------------------------

    async def count(self) -> int:
        """Return the total number of bridge edges.

        Returns:
            Integer count, 0 on error.
        """
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM bridge_edges").fetchone()
            return row[0] if row else 0
        except Exception as exc:
            logger.error("BridgeRegistry count failed: %s", exc)
            return 0

    async def health(self) -> dict[str, Any]:
        """Return bridge registry statistics.

        Returns:
            Dict with keys:
                total_edges: int
                per_source_graph: dict[str, int]
                per_target_graph: dict[str, int]
                per_edge_type: dict[str, int]
                avg_confidence: float
                min_confidence: float
                max_confidence: float
                db_path: str
        """
        result: dict[str, Any] = {
            "total_edges": 0,
            "per_source_graph": {},
            "per_target_graph": {},
            "per_edge_type": {},
            "avg_confidence": 0.0,
            "min_confidence": 0.0,
            "max_confidence": 0.0,
            "db_path": str(self._db_path),
        }
        try:
            with self._connect() as conn:
                # Total
                row = conn.execute("SELECT COUNT(*) FROM bridge_edges").fetchone()
                total = row[0] if row else 0
                result["total_edges"] = total

                if total == 0:
                    return result

                # Per source graph
                rows = conn.execute(
                    """SELECT source_graph, COUNT(*) AS cnt
                       FROM bridge_edges GROUP BY source_graph
                       ORDER BY cnt DESC""",
                ).fetchall()
                result["per_source_graph"] = {r["source_graph"]: r["cnt"] for r in rows}

                # Per target graph
                rows = conn.execute(
                    """SELECT target_graph, COUNT(*) AS cnt
                       FROM bridge_edges GROUP BY target_graph
                       ORDER BY cnt DESC""",
                ).fetchall()
                result["per_target_graph"] = {r["target_graph"]: r["cnt"] for r in rows}

                # Per edge type
                rows = conn.execute(
                    """SELECT edge_type, COUNT(*) AS cnt
                       FROM bridge_edges GROUP BY edge_type
                       ORDER BY cnt DESC""",
                ).fetchall()
                result["per_edge_type"] = {r["edge_type"]: r["cnt"] for r in rows}

                # Confidence stats
                row = conn.execute(
                    """SELECT AVG(confidence), MIN(confidence), MAX(confidence)
                       FROM bridge_edges""",
                ).fetchone()
                if row:
                    result["avg_confidence"] = round(float(row[0] or 0.0), 4)
                    result["min_confidence"] = round(float(row[1] or 0.0), 4)
                    result["max_confidence"] = round(float(row[2] or 0.0), 4)

        except Exception as exc:
            logger.error("BridgeRegistry health check failed: %s", exc)
            result["error"] = str(exc)

        return result

    # -- Maintenance ---------------------------------------------------------

    async def prune_stale(
        self,
        max_age_days: int = 90,
        min_confidence: float = 0.1,
    ) -> int:
        """Remove bridge edges that are too old AND below confidence threshold.

        An edge is pruned if BOTH conditions are met:
            1. ``discovered_at`` is older than ``max_age_days`` ago.
            2. ``confidence`` is below ``min_confidence``.

        This prevents deleting old-but-high-confidence edges (established
        relationships) and new-but-low-confidence edges (recently discovered,
        not yet validated).

        Args:
            max_age_days: Age threshold in days.
            min_confidence: Confidence threshold.

        Returns:
            Number of edges removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_iso = cutoff.isoformat()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """DELETE FROM bridge_edges
                       WHERE discovered_at < ? AND confidence < ?""",
                    (cutoff_iso, min_confidence),
                )
                removed = cursor.rowcount
            if removed > 0:
                logger.info(
                    "Pruned %d stale bridge edges (older than %d days, confidence < %.2f)",
                    removed, max_age_days, min_confidence,
                )
            return removed
        except Exception as exc:
            logger.error("BridgeRegistry prune_stale failed: %s", exc)
            return 0

    async def delete(self, edge_id: str) -> bool:
        """Delete a single bridge edge by ID.

        Args:
            edge_id: The unique edge identifier.

        Returns:
            True if an edge was deleted, False otherwise.
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM bridge_edges WHERE edge_id = ?",
                    (edge_id,),
                )
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error("BridgeRegistry delete(%s) failed: %s", edge_id, exc)
            return False

    async def delete_by_node(self, graph: GraphOrigin, node_id: str) -> int:
        """Delete all bridge edges touching a specific node.

        Useful when a node is removed from its home graph and its bridges
        should be cleaned up.

        Args:
            graph: The graph subsystem the node belongs to.
            node_id: The node identifier within that graph.

        Returns:
            Number of edges deleted.
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """DELETE FROM bridge_edges
                       WHERE (source_graph = ? AND source_id = ?)
                          OR (target_graph = ? AND target_id = ?)""",
                    (graph.value, node_id, graph.value, node_id),
                )
                removed = cursor.rowcount
            if removed > 0:
                logger.info(
                    "Deleted %d bridge edges for node %s:%s",
                    removed, graph.value, node_id,
                )
            return removed
        except Exception as exc:
            logger.error("BridgeRegistry delete_by_node failed: %s", exc)
            return 0

    # -- Topology queries ----------------------------------------------------

    async def connected_graphs(self, graph: GraphOrigin) -> list[str]:
        """List all graph origins that have at least one bridge to/from this graph.

        Args:
            graph: The graph to check connectivity for.

        Returns:
            Sorted list of GraphOrigin values connected to this graph.
        """
        try:
            with self._connect() as conn:
                # Graphs this one points TO
                rows_out = conn.execute(
                    """SELECT DISTINCT target_graph FROM bridge_edges
                       WHERE source_graph = ?""",
                    (graph.value,),
                ).fetchall()
                # Graphs that point TO this one
                rows_in = conn.execute(
                    """SELECT DISTINCT source_graph FROM bridge_edges
                       WHERE target_graph = ?""",
                    (graph.value,),
                ).fetchall()
            targets = {r["target_graph"] for r in rows_out}
            sources = {r["source_graph"] for r in rows_in}
            connected = sorted(targets | sources)
            return connected
        except Exception as exc:
            logger.error("BridgeRegistry connected_graphs failed: %s", exc)
            return []

    async def cross_graph_density(self) -> dict[str, dict[str, int]]:
        """Return a matrix of edge counts between each pair of graph origins.

        Returns:
            Nested dict: ``{source_graph: {target_graph: count}}``.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT source_graph, target_graph, COUNT(*) AS cnt
                       FROM bridge_edges
                       GROUP BY source_graph, target_graph
                       ORDER BY cnt DESC""",
                ).fetchall()
            density: dict[str, dict[str, int]] = {}
            for r in rows:
                sg = r["source_graph"]
                tg = r["target_graph"]
                if sg not in density:
                    density[sg] = {}
                density[sg][tg] = r["cnt"]
            return density
        except Exception as exc:
            logger.error("BridgeRegistry cross_graph_density failed: %s", exc)
            return {}

    # -- Boost / decay -------------------------------------------------------

    async def boost_confidence(
        self,
        edge_id: str,
        delta: float = 0.1,
    ) -> float | None:
        """Increase an edge's confidence, clamped to [0.0, 1.0].

        Used when an edge is re-observed or validated by another subsystem.

        Args:
            edge_id: Edge to boost.
            delta: Amount to increase confidence by.

        Returns:
            New confidence value, or None if edge not found.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT confidence FROM bridge_edges WHERE edge_id = ?",
                    (edge_id,),
                ).fetchone()
                if row is None:
                    return None
                new_conf = min(1.0, float(row["confidence"]) + delta)
                conn.execute(
                    """UPDATE bridge_edges
                       SET confidence = ?, discovered_at = ?
                       WHERE edge_id = ?""",
                    (new_conf, _utc_now().isoformat(), edge_id),
                )
            return round(new_conf, 4)
        except Exception as exc:
            logger.error("BridgeRegistry boost_confidence failed: %s", exc)
            return None

    async def decay_confidence(
        self,
        edge_id: str,
        delta: float = 0.05,
    ) -> float | None:
        """Decrease an edge's confidence, clamped to [0.0, 1.0].

        Used for time-based decay or when contradicting evidence appears.

        Args:
            edge_id: Edge to decay.
            delta: Amount to decrease confidence by.

        Returns:
            New confidence value, or None if edge not found.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT confidence FROM bridge_edges WHERE edge_id = ?",
                    (edge_id,),
                ).fetchone()
                if row is None:
                    return None
                new_conf = max(0.0, float(row["confidence"]) - delta)
                conn.execute(
                    "UPDATE bridge_edges SET confidence = ? WHERE edge_id = ?",
                    (new_conf, edge_id),
                )
            return round(new_conf, 4)
        except Exception as exc:
            logger.error("BridgeRegistry decay_confidence failed: %s", exc)
            return None
