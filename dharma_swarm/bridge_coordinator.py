"""Bridge Coordinator -- auto-discovers cross-graph bridge edges during sleep.

Part of the Graph Nexus architecture.  Runs as the BRIDGE phase in the
SleepCycle, connecting nodes across different graph subsystems:

- ConceptGraph nodes <-> TemporalKnowledgeGraph terms (by name matching)
- CatalyticGraph nodes <-> TelosGraph objectives (by name overlap)
- ConceptNode source_file fields -> Code reference bridges

Each discovery algorithm is fault-isolated: one failing discoverer does not
prevent the others from completing.

Integration:
    sleep_cycle.py  -- call ``BridgeCoordinator.discover_all()`` from a BRIDGE phase
    bridge_registry.py -- all discovered edges persist through BridgeRegistry
    semantic_gravity.py -- ConceptGraph is the primary semantic source
    temporal_graph.py -- TemporalKnowledgeGraph provides temporal term data
    catalytic_graph.py -- CatalyticGraph tracks artifact interdependencies
    telos_graph.py -- TelosGraph holds strategic objectives

Persistence: edges written to ``~/.dharma/db/bridges.db`` via BridgeRegistry.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dharma_swarm.bridge_registry import BridgeRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class BridgeDiscoveryResult(BaseModel):
    """Result of a bridge discovery run.

    Attributes:
        discovered: Total new bridge edges discovered across all algorithms.
        updated: Edges that were re-observed and had confidence refreshed.
        errors: Human-readable descriptions of any failures.
        duration_seconds: Wall-clock time for the full discovery pass.
        phase_counts: Per-discoverer breakdown of edge counts.
    """

    discovered: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    phase_counts: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class BridgeCoordinator:
    """Discovers cross-graph bridge edges during sleep cycle.

    Runs as the BRIDGE phase in SleepCycle, connecting:

    - ConceptGraph nodes <-> TemporalKnowledgeGraph terms (by name matching)
    - CatalyticGraph nodes <-> TelosGraph objectives (by ID/name matching)
    - File paths in ConceptNodes -> code references (Code<->Semantic bridges)

    All graph module imports are late (inside methods) to avoid import-time
    circular dependencies and to keep startup cost near zero when the
    coordinator is instantiated but not yet invoked.

    Args:
        state_dir: Root state directory.  Defaults to ``~/.dharma``.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"

    # -- public API ----------------------------------------------------------

    async def discover_all(self) -> BridgeDiscoveryResult:
        """Run all discovery algorithms.  Called from sleep_cycle BRIDGE phase.

        Each discoverer runs in fault isolation.  Errors are captured in the
        result but do not abort the remaining discoverers.

        Returns:
            A BridgeDiscoveryResult summarizing what was found and any errors.
        """
        result = BridgeDiscoveryResult()
        started = time.monotonic()

        # Late import -- avoid circular deps at module load time
        from dharma_swarm.bridge_registry import BridgeRegistry

        registry = BridgeRegistry(db_path=self._state_dir / "db" / "bridges.db")
        await registry.init()

        discoverers = [
            self._discover_semantic_temporal,
            self._discover_catalytic_telos,
            self._discover_concept_files,
        ]

        for discoverer in discoverers:
            name = discoverer.__name__
            try:
                count = await discoverer(registry)
                result.discovered += count
                result.phase_counts[name] = count
                logger.info(
                    "Bridge discovery %s: %d edges", name, count,
                )
            except Exception as exc:
                msg = f"{name}: {exc}"
                result.errors.append(msg)
                logger.warning("Bridge discovery %s failed: %s", name, exc)

        await registry.close()
        result.duration_seconds = round(time.monotonic() - started, 3)

        logger.info(
            "Bridge discovery complete: %d discovered, %d errors in %.2fs",
            result.discovered,
            len(result.errors),
            result.duration_seconds,
        )
        return result

    # -- individual discoverers ----------------------------------------------

    async def _discover_semantic_temporal(
        self, registry: BridgeRegistry,
    ) -> int:
        """Match ConceptGraph node names to TemporalKnowledgeGraph terms.

        For each ConceptNode, normalizes the name to a term key and checks
        whether the temporal graph's ``concepts`` table has a matching row.
        If so, creates a RELATES_TO bridge edge between the semantic node
        and the temporal term.

        Args:
            registry: An initialized BridgeRegistry to write edges into.

        Returns:
            Number of bridge edges upserted.
        """
        from dharma_swarm.bridge_registry import (
            BridgeEdge,
            BridgeEdgeKind,
            GraphOrigin,
        )
        from dharma_swarm.semantic_gravity import ConceptGraph
        from dharma_swarm.temporal_graph import TemporalKnowledgeGraph

        # Load concept graph from default persistence path
        cg_path = self._state_dir / "semantic" / "concept_graph.json"
        cg = await ConceptGraph.load(cg_path)  # returns empty graph if missing

        # Open temporal graph (creates tables if needed)
        tkg = TemporalKnowledgeGraph(
            db_path=self._state_dir / "db" / "temporal_graph.db",
        )

        count = 0
        for node in cg.all_nodes():
            # Normalize name to match temporal term conventions
            term_underscore = node.name.lower().replace(" ", "_").replace("-", "_")
            term_lower = node.name.lower()

            try:
                with tkg._connect() as conn:
                    row = conn.execute(
                        "SELECT term, frequency FROM concepts "
                        "WHERE term = ? OR term = ?",
                        (term_underscore, term_lower),
                    ).fetchone()
            except Exception:
                continue

            if row is None:
                continue

            matched_term: str = row["term"] if hasattr(row, "__getitem__") else row[0]

            edge = BridgeEdge(
                source_graph=GraphOrigin.SEMANTIC,
                source_id=node.id,
                target_graph=GraphOrigin.TEMPORAL,
                target_id=matched_term,
                edge_type=BridgeEdgeKind.RELATES_TO,
                confidence=0.8,
                discovered_by="bridge_coordinator.semantic_temporal",
            )
            await registry.upsert(edge)
            count += 1

        logger.debug(
            "semantic_temporal: scanned %d concept nodes, bridged %d",
            cg.node_count,
            count,
        )
        return count

    async def _discover_catalytic_telos(
        self, registry: BridgeRegistry,
    ) -> int:
        """Match CatalyticGraph node IDs to TelosGraph objective names.

        For each catalytic node, checks whether any telos objective name
        shares significant word overlap (words longer than 3 characters).
        Matching pairs get an ADVANCES_GOAL bridge edge.

        Args:
            registry: An initialized BridgeRegistry to write edges into.

        Returns:
            Number of bridge edges upserted.
        """
        from dharma_swarm.bridge_registry import (
            BridgeEdge,
            BridgeEdgeKind,
            GraphOrigin,
        )
        from dharma_swarm.catalytic_graph import CatalyticGraph
        from dharma_swarm.telos_graph import TelosGraph

        cat = CatalyticGraph(
            persist_path=self._state_dir / "meta" / "catalytic_graph.json",
        )
        cat.load()  # sync load, returns bool

        telos = TelosGraph(telos_dir=self._state_dir / "telos")
        try:
            await telos.load()
        except Exception as exc:
            logger.debug("TelosGraph load failed (may not exist yet): %s", exc)
            return 0

        objectives = telos.list_objectives()
        if not objectives:
            return 0

        count = 0
        for node_id in cat._nodes:
            node_words = set(
                w for w in node_id.lower().replace("_", " ").replace("-", " ").split()
                if len(w) > 3
            )
            if not node_words:
                continue

            for obj in objectives:
                obj_lower = obj.name.lower()
                obj_words = set(
                    w for w in obj_lower.replace("_", " ").replace("-", " ").split()
                    if len(w) > 3
                )

                # Require at least one significant word overlap
                overlap = node_words & obj_words
                if not overlap:
                    # Also check substring containment
                    node_flat = node_id.lower().replace("_", " ")
                    if node_flat not in obj_lower and obj_lower not in node_flat:
                        continue

                # Confidence scales with overlap size relative to total words
                total_words = len(node_words | obj_words)
                overlap_ratio = len(overlap) / max(total_words, 1)
                confidence = min(0.5 + overlap_ratio * 0.4, 0.9)

                edge = BridgeEdge(
                    source_graph=GraphOrigin.CATALYTIC,
                    source_id=node_id,
                    target_graph=GraphOrigin.TELOS,
                    target_id=obj.id,
                    edge_type=BridgeEdgeKind.ADVANCES_GOAL,
                    confidence=confidence,
                    discovered_by="bridge_coordinator.catalytic_telos",
                    metadata={"objective_name": obj.name, "overlap": sorted(overlap)},
                )
                await registry.upsert(edge)
                count += 1

        logger.debug(
            "catalytic_telos: scanned %d catalytic nodes x %d objectives, bridged %d",
            len(cat._nodes),
            len(objectives),
            count,
        )
        return count

    async def _discover_concept_files(
        self, registry: BridgeRegistry,
    ) -> int:
        """Create Code<->Semantic bridges from ConceptNode.source_file.

        For each ConceptNode that has a non-empty ``source_file`` attribute,
        creates a REFERENCES_CONCEPT bridge edge linking the semantic concept
        to a pseudo-node representing the file path.

        Args:
            registry: An initialized BridgeRegistry to write edges into.

        Returns:
            Number of bridge edges upserted.
        """
        from dharma_swarm.bridge_registry import (
            BridgeEdge,
            BridgeEdgeKind,
            GraphOrigin,
        )
        from dharma_swarm.semantic_gravity import ConceptGraph

        cg_path = self._state_dir / "semantic" / "concept_graph.json"
        cg = await ConceptGraph.load(cg_path)

        count = 0
        for node in cg.all_nodes():
            if not node.source_file:
                continue

            edge = BridgeEdge(
                source_graph=GraphOrigin.SEMANTIC,
                source_id=node.id,
                target_graph=GraphOrigin.SEMANTIC,
                target_id=f"file::{node.source_file}",
                edge_type=BridgeEdgeKind.REFERENCES_CONCEPT,
                confidence=0.95,
                discovered_by="bridge_coordinator.concept_files",
                metadata={"source_file": node.source_file, "concept_name": node.name},
            )
            await registry.upsert(edge)
            count += 1

        logger.debug(
            "concept_files: scanned %d nodes, bridged %d with source files",
            cg.node_count,
            count,
        )
        return count

    # -- helper for external integration -------------------------------------

    async def discover_single(
        self, algorithm: str,
    ) -> BridgeDiscoveryResult:
        """Run a single named discovery algorithm.

        Useful for targeted re-scanning without running the full suite.

        Args:
            algorithm: One of ``"semantic_temporal"``, ``"catalytic_telos"``,
                or ``"concept_files"``.

        Returns:
            A BridgeDiscoveryResult with results from only the named algorithm.

        Raises:
            ValueError: If the algorithm name is unrecognized.
        """
        dispatch = {
            "semantic_temporal": self._discover_semantic_temporal,
            "catalytic_telos": self._discover_catalytic_telos,
            "concept_files": self._discover_concept_files,
        }
        discoverer = dispatch.get(algorithm)
        if discoverer is None:
            raise ValueError(
                f"Unknown algorithm {algorithm!r}. "
                f"Valid: {sorted(dispatch.keys())}"
            )

        result = BridgeDiscoveryResult()
        started = time.monotonic()

        from dharma_swarm.bridge_registry import BridgeRegistry

        registry = BridgeRegistry(db_path=self._state_dir / "db" / "bridges.db")
        await registry.init()

        try:
            count = await discoverer(registry)
            result.discovered = count
            result.phase_counts[algorithm] = count
        except Exception as exc:
            result.errors.append(f"{algorithm}: {exc}")
            logger.warning("Bridge discovery %s failed: %s", algorithm, exc)

        await registry.close()
        result.duration_seconds = round(time.monotonic() - started, 3)
        return result

    async def summary(self) -> dict[str, Any]:
        """Return a diagnostic summary of current bridge state.

        Queries the BridgeRegistry for edge counts by type and graph origin,
        useful for health checks and monitoring.

        Returns:
            Dict with counts and breakdowns.
        """
        from dharma_swarm.bridge_registry import BridgeRegistry

        registry = BridgeRegistry(db_path=self._state_dir / "db" / "bridges.db")
        await registry.init()

        info: dict[str, Any] = {
            "total_bridges": 0,
            "by_source_graph": {},
            "by_edge_type": {},
        }

        try:
            with registry._connect() as conn:
                # Total count
                row = conn.execute(
                    "SELECT COUNT(*) FROM bridge_edges",
                ).fetchone()
                info["total_bridges"] = row[0] if row else 0

                # By source graph
                rows = conn.execute(
                    "SELECT source_graph, COUNT(*) AS cnt "
                    "FROM bridge_edges GROUP BY source_graph",
                ).fetchall()
                info["by_source_graph"] = {r["source_graph"]: r["cnt"] for r in rows}

                # By edge type
                rows = conn.execute(
                    "SELECT edge_type, COUNT(*) AS cnt "
                    "FROM bridge_edges GROUP BY edge_type",
                ).fetchall()
                info["by_edge_type"] = {r["edge_type"]: r["cnt"] for r in rows}
        except Exception as exc:
            logger.warning("Bridge summary query failed: %s", exc)
            info["error"] = str(exc)

        await registry.close()
        return info
