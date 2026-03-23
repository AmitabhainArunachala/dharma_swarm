"""Graph Nexus -- unified query interface over dharma_swarm's graph ecosystem.

Six independent graphs, each with different persistence (JSON, SQLite, JSONL),
different node/edge models, and different query interfaces.  GraphNexus wraps
them into a single queryable surface:

    nexus = GraphNexus()
    await nexus.init()
    result = await nexus.query_about("autocatalytic")
    print(result.total_hits, result.graphs_queried)

Every graph is lazily loaded on first use.  If a graph fails to load
(ImportError, missing DB, corrupt file), the nexus logs a warning and
continues with the remaining graphs.  Partial results are always better
than no results.

Graphs wrapped:
  1. ConceptGraph       (semantic_gravity)   -- JSON file
  2. CatalyticGraph     (catalytic_graph)    -- JSON file
  3. TemporalKnowledgeGraph (temporal_graph) -- SQLite
  4. LineageGraph        (lineage)           -- SQLite
  5. TelosGraph          (telos_graph)       -- JSONL  (NEW, may not exist yet)
  6. BridgeRegistry      (bridge_registry)   -- SQLite (NEW, may not exist yet)
"""

from __future__ import annotations

import inspect
import logging
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GraphOrigin(str, Enum):
    """Identifies which graph a hit came from."""

    SEMANTIC = "semantic"
    CATALYTIC = "catalytic"
    TEMPORAL = "temporal"
    LINEAGE = "lineage"
    TELOS = "telos"
    BRIDGE = "bridge"


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class NexusHit(BaseModel):
    """A single hit from a cross-graph query."""

    graph: str  # GraphOrigin value
    node_id: str
    node_type: str  # "concept", "term", "objective", "artifact", etc.
    name: str
    relevance: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class NexusQueryResult(BaseModel):
    """Result of a cross-graph query."""

    query: str
    semantic_hits: list[NexusHit] = Field(default_factory=list)
    temporal_hits: list[NexusHit] = Field(default_factory=list)
    telos_hits: list[NexusHit] = Field(default_factory=list)
    lineage_hits: list[NexusHit] = Field(default_factory=list)
    catalytic_hits: list[NexusHit] = Field(default_factory=list)
    bridge_edges: list[Any] = Field(default_factory=list)
    total_hits: int = 0
    graphs_queried: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class NexusHealth(BaseModel):
    """Health report for the graph nexus."""

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    graphs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    total_nodes: int = 0
    total_edges: int = 0
    healthy_count: int = 0
    failed_count: int = 0


# ---------------------------------------------------------------------------
# GraphNexus
# ---------------------------------------------------------------------------


class GraphNexus:
    """Unified query interface over dharma_swarm's graph ecosystem.

    Wraps 6 independent graphs into a single queryable system.
    Each graph is lazily loaded on first use.  If a subsystem fails to
    initialize, the nexus logs the error and continues with the others.

    Args:
        state_dir: Root directory for dharma state files.
            Defaults to ``~/.dharma``.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"
        self._concept_graph: Any | None = None
        self._catalytic_graph: Any | None = None
        self._temporal_graph: Any | None = None
        self._lineage_graph: Any | None = None
        self._telos_graph: Any | None = None
        self._bridge_registry: Any | None = None
        self._init_errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Initialize all graph subsystems.

        Fault-tolerant: if one graph fails to load, the error is recorded
        and the nexus continues with the remaining graphs.
        """
        loaders = [
            (GraphOrigin.SEMANTIC, self._load_concept_graph),
            (GraphOrigin.CATALYTIC, self._load_catalytic_graph),
            (GraphOrigin.TEMPORAL, self._load_temporal_graph),
            (GraphOrigin.LINEAGE, self._load_lineage_graph),
            (GraphOrigin.TELOS, self._load_telos_graph),
            (GraphOrigin.BRIDGE, self._load_bridge_registry),
        ]
        for origin, loader in loaders:
            try:
                await loader()
            except Exception as exc:
                msg = f"{origin.value}: {type(exc).__name__}: {exc}"
                self._init_errors[origin.value] = msg
                logger.warning("GraphNexus: failed to load %s — %s", origin.value, msg)

    async def _load_concept_graph(self) -> None:
        from dharma_swarm.semantic_gravity import ConceptGraph

        path = self._state_dir / "meta" / "concept_graph.json"
        self._concept_graph = await ConceptGraph.load(path)

    async def _load_catalytic_graph(self) -> None:
        from dharma_swarm.catalytic_graph import CatalyticGraph

        path = self._state_dir / "meta" / "catalytic_graph.json"
        cg = CatalyticGraph(persist_path=path)
        cg.load()
        self._catalytic_graph = cg

    async def _load_temporal_graph(self) -> None:
        from dharma_swarm.temporal_graph import TemporalKnowledgeGraph

        db_path = self._state_dir / "db" / "temporal_graph.db"
        self._temporal_graph = TemporalKnowledgeGraph(db_path=db_path)

    async def _load_lineage_graph(self) -> None:
        from dharma_swarm.lineage import LineageGraph

        db_path = self._state_dir / "db" / "lineage.db"
        self._lineage_graph = LineageGraph(db_path=db_path)

    async def _load_telos_graph(self) -> None:
        from dharma_swarm.telos_graph import TelosGraph

        telos_dir = self._state_dir / "telos"
        self._telos_graph = TelosGraph(telos_dir=telos_dir)
        await self._telos_graph.load()

    async def _load_bridge_registry(self) -> None:
        from dharma_swarm.bridge_registry import BridgeRegistry

        db_path = self._state_dir / "db" / "bridges.db"
        self._bridge_registry = BridgeRegistry(db_path=db_path)
        await self._bridge_registry.init()

    # ------------------------------------------------------------------
    # Lazy graph accessors
    # ------------------------------------------------------------------

    async def _get_concept_graph(self) -> Any | None:
        """Lazy-load ConceptGraph from semantic_gravity."""
        if self._concept_graph is None and GraphOrigin.SEMANTIC.value not in self._init_errors:
            try:
                await self._load_concept_graph()
            except Exception as exc:
                self._init_errors[GraphOrigin.SEMANTIC.value] = str(exc)
                logger.warning("GraphNexus: lazy-load concept_graph failed — %s", exc)
        return self._concept_graph

    async def _get_catalytic_graph(self) -> Any | None:
        """Lazy-load CatalyticGraph from catalytic_graph."""
        if self._catalytic_graph is None and GraphOrigin.CATALYTIC.value not in self._init_errors:
            try:
                await self._load_catalytic_graph()
            except Exception as exc:
                self._init_errors[GraphOrigin.CATALYTIC.value] = str(exc)
                logger.warning("GraphNexus: lazy-load catalytic_graph failed — %s", exc)
        return self._catalytic_graph

    async def _get_temporal_graph(self) -> Any | None:
        """Lazy-load TemporalKnowledgeGraph from temporal_graph."""
        if self._temporal_graph is None and GraphOrigin.TEMPORAL.value not in self._init_errors:
            try:
                await self._load_temporal_graph()
            except Exception as exc:
                self._init_errors[GraphOrigin.TEMPORAL.value] = str(exc)
                logger.warning("GraphNexus: lazy-load temporal_graph failed — %s", exc)
        return self._temporal_graph

    async def _get_lineage_graph(self) -> Any | None:
        """Lazy-load LineageGraph from lineage."""
        if self._lineage_graph is None and GraphOrigin.LINEAGE.value not in self._init_errors:
            try:
                await self._load_lineage_graph()
            except Exception as exc:
                self._init_errors[GraphOrigin.LINEAGE.value] = str(exc)
                logger.warning("GraphNexus: lazy-load lineage_graph failed — %s", exc)
        return self._lineage_graph

    async def _get_telos_graph(self) -> Any | None:
        """Lazy-load TelosGraph from telos_graph."""
        if self._telos_graph is None and GraphOrigin.TELOS.value not in self._init_errors:
            try:
                await self._load_telos_graph()
            except Exception as exc:
                self._init_errors[GraphOrigin.TELOS.value] = str(exc)
                logger.warning("GraphNexus: lazy-load telos_graph failed — %s", exc)
        return self._telos_graph

    async def _get_bridge_registry(self) -> Any | None:
        """Lazy-load BridgeRegistry from bridge_registry."""
        if self._bridge_registry is None and GraphOrigin.BRIDGE.value not in self._init_errors:
            try:
                await self._load_bridge_registry()
            except Exception as exc:
                self._init_errors[GraphOrigin.BRIDGE.value] = str(exc)
                logger.warning("GraphNexus: lazy-load bridge_registry failed — %s", exc)
        return self._bridge_registry

    # ------------------------------------------------------------------
    # Core queries
    # ------------------------------------------------------------------

    async def query_about(self, term: str) -> NexusQueryResult:
        """Query ALL graphs for information about a term or concept.

        This is the primary entry point -- one query, all graphs,
        cross-referenced via bridge edges where available.

        Each graph search is wrapped in its own try/except so a failure
        in one graph never prevents results from the others.

        Args:
            term: The concept, keyword, or artifact name to search for.

        Returns:
            Aggregated results from all available graphs.
        """
        result = NexusQueryResult(query=term)

        # --- 1. ConceptGraph (semantic_gravity) ---
        try:
            cg = await self._get_concept_graph()
            if cg is not None:
                result.graphs_queried.append(GraphOrigin.SEMANTIC.value)
                nodes = cg.find_by_name(term)
                # Also search by category as a fallback
                if not nodes:
                    nodes = cg.find_by_category(term)
                for node in nodes:
                    result.semantic_hits.append(NexusHit(
                        graph=GraphOrigin.SEMANTIC.value,
                        node_id=node.id,
                        node_type="concept",
                        name=node.name,
                        relevance=node.salience,
                        metadata={
                            "definition": node.definition,
                            "source_file": node.source_file,
                            "category": node.category,
                        },
                    ))
        except Exception as exc:
            result.errors.append(f"semantic: {exc}")
            logger.warning("GraphNexus.query_about semantic error: %s", exc)

        # --- 2. TemporalKnowledgeGraph ---
        try:
            tkg = await self._get_temporal_graph()
            if tkg is not None:
                result.graphs_queried.append(GraphOrigin.TEMPORAL.value)
                normalized = term.lower().replace("-", "_")

                # Direct concept lookup via SQL
                with tkg._connect() as conn:
                    row = conn.execute(
                        "SELECT term, first_seen, last_seen, frequency "
                        "FROM concepts WHERE term = ?",
                        (normalized,),
                    ).fetchone()
                if row is not None:
                    result.temporal_hits.append(NexusHit(
                        graph=GraphOrigin.TEMPORAL.value,
                        node_id=row["term"],
                        node_type="term",
                        name=row["term"],
                        relevance=min(row["frequency"] / 100.0, 1.0),
                        metadata={
                            "frequency": row["frequency"],
                            "first_seen": row["first_seen"],
                            "last_seen": row["last_seen"],
                        },
                    ))

                # Co-occurring terms as additional hits
                co_terms = tkg.co_occurring(term, limit=5)
                for co in co_terms:
                    result.temporal_hits.append(NexusHit(
                        graph=GraphOrigin.TEMPORAL.value,
                        node_id=co["term"],
                        node_type="co_occurring_term",
                        name=co["term"],
                        relevance=min(co["weight"] / 50.0, 1.0),
                        metadata={
                            "weight": co["weight"],
                            "first_co": co["first_co"],
                            "last_co": co["last_co"],
                            "relation": f"co-occurs with '{term}'",
                        },
                    ))

                # Fuzzy match: terms containing the search string
                with tkg._connect() as conn:
                    like_rows = conn.execute(
                        "SELECT term, first_seen, last_seen, frequency "
                        "FROM concepts WHERE term LIKE ? AND term != ? "
                        "ORDER BY frequency DESC LIMIT 5",
                        (f"%{normalized}%", normalized),
                    ).fetchall()
                for row in like_rows:
                    result.temporal_hits.append(NexusHit(
                        graph=GraphOrigin.TEMPORAL.value,
                        node_id=row["term"],
                        node_type="term",
                        name=row["term"],
                        relevance=min(row["frequency"] / 100.0, 0.8),
                        metadata={
                            "frequency": row["frequency"],
                            "first_seen": row["first_seen"],
                            "last_seen": row["last_seen"],
                            "match_type": "substring",
                        },
                    ))
        except Exception as exc:
            result.errors.append(f"temporal: {exc}")
            logger.warning("GraphNexus.query_about temporal error: %s", exc)

        # --- 3. CatalyticGraph ---
        try:
            cat = await self._get_catalytic_graph()
            if cat is not None:
                result.graphs_queried.append(GraphOrigin.CATALYTIC.value)
                normalized_cat = term.lower().replace(" ", "_")
                # Check exact node match
                if normalized_cat in cat._nodes:
                    meta = cat._nodes[normalized_cat]
                    result.catalytic_hits.append(NexusHit(
                        graph=GraphOrigin.CATALYTIC.value,
                        node_id=normalized_cat,
                        node_type="catalytic_node",
                        name=normalized_cat,
                        relevance=1.0,
                        metadata=dict(meta),
                    ))
                # Substring search across node IDs
                for nid, meta in cat._nodes.items():
                    if normalized_cat in nid and nid != normalized_cat:
                        result.catalytic_hits.append(NexusHit(
                            graph=GraphOrigin.CATALYTIC.value,
                            node_id=nid,
                            node_type="catalytic_node",
                            name=nid,
                            relevance=0.7,
                            metadata=dict(meta),
                        ))
        except Exception as exc:
            result.errors.append(f"catalytic: {exc}")
            logger.warning("GraphNexus.query_about catalytic error: %s", exc)

        # --- 4. LineageGraph ---
        try:
            lg = await self._get_lineage_graph()
            if lg is not None:
                result.graphs_queried.append(GraphOrigin.LINEAGE.value)
                # Search for the term as an artifact ID
                producers = lg.producers_of(term)
                consumers = lg.consumers_of(term)
                if producers or consumers:
                    result.lineage_hits.append(NexusHit(
                        graph=GraphOrigin.LINEAGE.value,
                        node_id=term,
                        node_type="artifact",
                        name=term,
                        relevance=1.0,
                        metadata={
                            "producer_count": len(producers),
                            "consumer_count": len(consumers),
                            "producers": [e.operation for e in producers[:5]],
                            "consumers": [e.operation for e in consumers[:5]],
                        },
                    ))
        except Exception as exc:
            result.errors.append(f"lineage: {exc}")
            logger.warning("GraphNexus.query_about lineage error: %s", exc)

        # --- 5. TelosGraph ---
        try:
            tg = await self._get_telos_graph()
            if tg is not None:
                result.graphs_queried.append(GraphOrigin.TELOS.value)
                needle = term.lower()
                # list_objectives() is synchronous
                objectives = tg.list_objectives()
                for obj in objectives:
                    if needle in obj.name.lower() or needle in obj.description.lower():
                        status_val = obj.status
                        if hasattr(status_val, "value"):
                            status_val = status_val.value
                        result.telos_hits.append(NexusHit(
                            graph=GraphOrigin.TELOS.value,
                            node_id=obj.id,
                            node_type="objective",
                            name=obj.name,
                            relevance=min(obj.priority / 10.0, 1.0),
                            metadata={
                                "description": obj.description,
                                "status": str(status_val),
                                "perspective": obj.perspective.value,
                                "progress": obj.progress,
                            },
                        ))
        except Exception as exc:
            result.errors.append(f"telos: {exc}")
            logger.warning("GraphNexus.query_about telos error: %s", exc)

        # --- 6. BridgeRegistry cross-references ---
        try:
            br = await self._get_bridge_registry()
            if br is not None:
                from dharma_swarm.bridge_registry import GraphOrigin as BridgeGraphOrigin

                result.graphs_queried.append(GraphOrigin.BRIDGE.value)
                # Collect all matched node IDs and look for bridges
                matched_ids: list[tuple[str, str]] = []  # (graph, node_id)
                for hit in result.semantic_hits:
                    matched_ids.append((hit.graph, hit.node_id))
                for hit in result.temporal_hits:
                    if hit.node_type == "term":
                        matched_ids.append((hit.graph, hit.node_id))
                for hit in result.catalytic_hits:
                    matched_ids.append((hit.graph, hit.node_id))
                for hit in result.lineage_hits:
                    matched_ids.append((hit.graph, hit.node_id))
                for hit in result.telos_hits:
                    matched_ids.append((hit.graph, hit.node_id))

                for graph_name, nid in matched_ids:
                    try:
                        bridge_origin = BridgeGraphOrigin(graph_name)
                    except ValueError:
                        continue
                    bridges = await br.find_bridges(bridge_origin, nid)
                    result.bridge_edges.extend(bridges)
        except Exception as exc:
            result.errors.append(f"bridge: {exc}")
            logger.warning("GraphNexus.query_about bridge error: %s", exc)

        # Compute totals
        result.total_hits = (
            len(result.semantic_hits)
            + len(result.temporal_hits)
            + len(result.telos_hits)
            + len(result.lineage_hits)
            + len(result.catalytic_hits)
        )
        return result

    async def query_node(self, graph: str, node_id: str) -> NexusHit | None:
        """Look up a specific node in a specific graph.

        Args:
            graph: One of the GraphOrigin values (e.g. ``"semantic"``).
            node_id: The node identifier within that graph.

        Returns:
            A NexusHit if found, None otherwise.
        """
        try:
            if graph == GraphOrigin.SEMANTIC.value:
                cg = await self._get_concept_graph()
                if cg is None:
                    return None
                node = cg.get_node(node_id)
                if node is None:
                    return None
                return NexusHit(
                    graph=graph,
                    node_id=node.id,
                    node_type="concept",
                    name=node.name,
                    relevance=node.salience,
                    metadata={
                        "definition": node.definition,
                        "source_file": node.source_file,
                        "category": node.category,
                    },
                )

            elif graph == GraphOrigin.CATALYTIC.value:
                cat = await self._get_catalytic_graph()
                if cat is None or node_id not in cat._nodes:
                    return None
                meta = cat._nodes[node_id]
                return NexusHit(
                    graph=graph,
                    node_id=node_id,
                    node_type="catalytic_node",
                    name=node_id,
                    relevance=1.0,
                    metadata=dict(meta),
                )

            elif graph == GraphOrigin.TEMPORAL.value:
                tkg = await self._get_temporal_graph()
                if tkg is None:
                    return None
                normalized = node_id.lower().replace("-", "_")
                with tkg._connect() as conn:
                    row = conn.execute(
                        "SELECT term, first_seen, last_seen, frequency "
                        "FROM concepts WHERE term = ?",
                        (normalized,),
                    ).fetchone()
                if row is None:
                    return None
                return NexusHit(
                    graph=graph,
                    node_id=row["term"],
                    node_type="term",
                    name=row["term"],
                    relevance=min(row["frequency"] / 100.0, 1.0),
                    metadata={
                        "frequency": row["frequency"],
                        "first_seen": row["first_seen"],
                        "last_seen": row["last_seen"],
                    },
                )

            elif graph == GraphOrigin.LINEAGE.value:
                lg = await self._get_lineage_graph()
                if lg is None:
                    return None
                producers = lg.producers_of(node_id)
                consumers = lg.consumers_of(node_id)
                if not producers and not consumers:
                    return None
                return NexusHit(
                    graph=graph,
                    node_id=node_id,
                    node_type="artifact",
                    name=node_id,
                    relevance=1.0,
                    metadata={
                        "producer_count": len(producers),
                        "consumer_count": len(consumers),
                    },
                )

            elif graph == GraphOrigin.TELOS.value:
                tg = await self._get_telos_graph()
                if tg is None:
                    return None
                obj = await tg.get_objective(node_id)
                if obj is None:
                    return None
                status_val = obj.status
                if hasattr(status_val, "value"):
                    status_val = status_val.value
                return NexusHit(
                    graph=graph,
                    node_id=obj.id,
                    node_type="objective",
                    name=obj.name,
                    relevance=min(obj.priority / 10.0, 1.0),
                    metadata={
                        "description": obj.description,
                        "status": str(status_val),
                        "perspective": obj.perspective.value,
                        "progress": obj.progress,
                    },
                )

        except Exception as exc:
            logger.warning("GraphNexus.query_node(%s, %s) failed: %s", graph, node_id, exc)
            return None

        return None

    async def query_neighbors(self, graph: str, node_id: str) -> list[NexusHit]:
        """Find neighbors of a node in its own graph.

        Args:
            graph: One of the GraphOrigin values.
            node_id: The node to find neighbors for.

        Returns:
            List of NexusHit for each neighboring node.
        """
        hits: list[NexusHit] = []
        try:
            if graph == GraphOrigin.SEMANTIC.value:
                cg = await self._get_concept_graph()
                if cg is not None:
                    for neighbor in cg.neighbors(node_id):
                        hits.append(NexusHit(
                            graph=graph,
                            node_id=neighbor.id,
                            node_type="concept",
                            name=neighbor.name,
                            relevance=neighbor.salience,
                            metadata={
                                "definition": neighbor.definition,
                                "category": neighbor.category,
                            },
                        ))

            elif graph == GraphOrigin.CATALYTIC.value:
                cat = await self._get_catalytic_graph()
                if cat is not None:
                    # Outgoing neighbors
                    for target in cat._adj.get(node_id, []):
                        meta = cat._nodes.get(target, {})
                        hits.append(NexusHit(
                            graph=graph,
                            node_id=target,
                            node_type="catalytic_node",
                            name=target,
                            relevance=0.8,
                            metadata={**meta, "direction": "outgoing"},
                        ))
                    # Incoming neighbors
                    for source in cat._rev.get(node_id, []):
                        if source not in {h.node_id for h in hits}:
                            meta = cat._nodes.get(source, {})
                            hits.append(NexusHit(
                                graph=graph,
                                node_id=source,
                                node_type="catalytic_node",
                                name=source,
                                relevance=0.8,
                                metadata={**meta, "direction": "incoming"},
                            ))

            elif graph == GraphOrigin.TEMPORAL.value:
                tkg = await self._get_temporal_graph()
                if tkg is not None:
                    co_terms = tkg.co_occurring(node_id, limit=10)
                    for co in co_terms:
                        hits.append(NexusHit(
                            graph=graph,
                            node_id=co["term"],
                            node_type="co_occurring_term",
                            name=co["term"],
                            relevance=min(co["weight"] / 50.0, 1.0),
                            metadata={"weight": co["weight"]},
                        ))

            elif graph == GraphOrigin.LINEAGE.value:
                lg = await self._get_lineage_graph()
                if lg is not None:
                    # Upstream (producers)
                    for edge in lg.producers_of(node_id):
                        for art in edge.input_artifacts:
                            hits.append(NexusHit(
                                graph=graph,
                                node_id=art,
                                node_type="artifact",
                                name=art,
                                relevance=0.9,
                                metadata={
                                    "direction": "upstream",
                                    "operation": edge.operation,
                                    "agent": edge.agent,
                                },
                            ))
                    # Downstream (consumers)
                    for edge in lg.consumers_of(node_id):
                        for art in edge.output_artifacts:
                            hits.append(NexusHit(
                                graph=graph,
                                node_id=art,
                                node_type="artifact",
                                name=art,
                                relevance=0.9,
                                metadata={
                                    "direction": "downstream",
                                    "operation": edge.operation,
                                    "agent": edge.agent,
                                },
                            ))

        except Exception as exc:
            logger.warning("GraphNexus.query_neighbors(%s, %s) failed: %s", graph, node_id, exc)

        return hits

    async def query_bridges(self, graph: str, node_id: str) -> list[Any]:
        """Find all cross-graph connections for a node via bridge_registry.

        Args:
            graph: The graph the node belongs to (a GraphOrigin value).
            node_id: The node identifier.

        Returns:
            List of BridgeEdge objects (or empty list if bridge_registry
            is not available).
        """
        try:
            br = await self._get_bridge_registry()
            if br is None:
                return []
            from dharma_swarm.bridge_registry import GraphOrigin as BridgeGraphOrigin

            try:
                bridge_origin = BridgeGraphOrigin(graph)
            except ValueError:
                logger.warning("GraphNexus.query_bridges: unknown graph origin %r", graph)
                return []
            return list(await br.find_bridges(bridge_origin, node_id))
        except Exception as exc:
            logger.warning("GraphNexus.query_bridges(%s, %s) failed: %s", graph, node_id, exc)
        return []

    async def traverse(
        self,
        graph: str,
        start_id: str,
        edge_types: list[str] | None = None,
        max_depth: int = 3,
    ) -> list[NexusHit]:
        """Traverse a graph from a starting node using BFS.

        Walks outward from ``start_id`` up to ``max_depth`` hops, optionally
        filtering by edge types.

        Args:
            graph: The graph to traverse.
            start_id: Starting node ID.
            edge_types: Optional filter for edge types.
            max_depth: Maximum traversal depth.

        Returns:
            List of NexusHit for all reachable nodes.
        """
        hits: list[NexusHit] = []
        visited: set[str] = {start_id}

        try:
            if graph == GraphOrigin.SEMANTIC.value:
                cg = await self._get_concept_graph()
                if cg is None:
                    return hits
                frontier = [start_id]
                for depth in range(max_depth):
                    next_frontier: list[str] = []
                    for nid in frontier:
                        edges = cg.edges_from(nid)
                        for edge in edges:
                            if edge_types and edge.edge_type.value not in edge_types:
                                continue
                            if edge.target_id not in visited:
                                visited.add(edge.target_id)
                                next_frontier.append(edge.target_id)
                                node = cg.get_node(edge.target_id)
                                if node is not None:
                                    hits.append(NexusHit(
                                        graph=graph,
                                        node_id=node.id,
                                        node_type="concept",
                                        name=node.name,
                                        relevance=max(0.1, 1.0 - (depth + 1) * 0.25),
                                        metadata={
                                            "depth": depth + 1,
                                            "edge_type": edge.edge_type.value,
                                            "edge_weight": edge.weight,
                                            "category": node.category,
                                        },
                                    ))
                    frontier = next_frontier
                    if not frontier:
                        break

            elif graph == GraphOrigin.CATALYTIC.value:
                cat = await self._get_catalytic_graph()
                if cat is None:
                    return hits
                frontier = [start_id]
                for depth in range(max_depth):
                    next_frontier: list[str] = []
                    for nid in frontier:
                        for target in cat._adj.get(nid, []):
                            if target not in visited:
                                # Optionally filter by edge type
                                if edge_types:
                                    has_match = any(
                                        e.edge_type in edge_types
                                        for e in cat._edges
                                        if e.source == nid and e.target == target
                                    )
                                    if not has_match:
                                        continue
                                visited.add(target)
                                next_frontier.append(target)
                                meta = cat._nodes.get(target, {})
                                hits.append(NexusHit(
                                    graph=graph,
                                    node_id=target,
                                    node_type="catalytic_node",
                                    name=target,
                                    relevance=max(0.1, 1.0 - (depth + 1) * 0.25),
                                    metadata={**meta, "depth": depth + 1},
                                ))
                    frontier = next_frontier
                    if not frontier:
                        break

            elif graph == GraphOrigin.LINEAGE.value:
                lg = await self._get_lineage_graph()
                if lg is None:
                    return hits
                # Walk downstream (consumers)
                frontier = [start_id]
                for depth in range(max_depth):
                    next_frontier: list[str] = []
                    for art_id in frontier:
                        for edge in lg.consumers_of(art_id):
                            for out in edge.output_artifacts:
                                if out not in visited:
                                    visited.add(out)
                                    next_frontier.append(out)
                                    hits.append(NexusHit(
                                        graph=graph,
                                        node_id=out,
                                        node_type="artifact",
                                        name=out,
                                        relevance=max(0.1, 1.0 - (depth + 1) * 0.25),
                                        metadata={
                                            "depth": depth + 1,
                                            "operation": edge.operation,
                                            "agent": edge.agent,
                                        },
                                    ))
                    frontier = next_frontier
                    if not frontier:
                        break

        except Exception as exc:
            logger.warning("GraphNexus.traverse(%s, %s) failed: %s", graph, start_id, exc)

        return hits

    # ------------------------------------------------------------------
    # Health & introspection
    # ------------------------------------------------------------------

    async def health(self) -> NexusHealth:
        """Report on all graph subsystems -- node counts, edge counts, status.

        Returns:
            NexusHealth with per-graph status and aggregate counts.
        """
        report = NexusHealth()
        total_n: int = 0
        total_e: int = 0

        # --- Semantic ---
        try:
            cg = await self._get_concept_graph()
            if cg is not None:
                nc = cg.node_count
                ec = cg.edge_count
                total_n += nc
                total_e += ec
                report.graphs[GraphOrigin.SEMANTIC.value] = {
                    "status": "ok",
                    "nodes": nc,
                    "edges": ec,
                    "annotations": cg.annotation_count,
                    "density": round(cg.density(), 4),
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.SEMANTIC.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.SEMANTIC.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.SEMANTIC.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        # --- Catalytic ---
        try:
            cat = await self._get_catalytic_graph()
            if cat is not None:
                nc = cat.node_count
                ec = cat.edge_count
                total_n += nc
                total_e += ec
                report.graphs[GraphOrigin.CATALYTIC.value] = {
                    "status": "ok",
                    "nodes": nc,
                    "edges": ec,
                    "autocatalytic_sets": len(cat.detect_autocatalytic_sets()),
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.CATALYTIC.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.CATALYTIC.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.CATALYTIC.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        # --- Temporal ---
        try:
            tkg = await self._get_temporal_graph()
            if tkg is not None:
                with tkg._connect() as conn:
                    nc = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
                    ec = conn.execute("SELECT COUNT(*) FROM co_occurrences").fetchone()[0]
                    ns = conn.execute(
                        "SELECT COUNT(DISTINCT source) FROM concept_sources"
                    ).fetchone()[0]
                total_n += nc
                total_e += ec
                report.graphs[GraphOrigin.TEMPORAL.value] = {
                    "status": "ok",
                    "concepts": nc,
                    "co_occurrences": ec,
                    "sources": ns,
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.TEMPORAL.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.TEMPORAL.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.TEMPORAL.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        # --- Lineage ---
        try:
            lg = await self._get_lineage_graph()
            if lg is not None:
                stats = lg.stats()
                total_e += stats["total_edges"]
                total_n += stats["unique_artifacts"]
                report.graphs[GraphOrigin.LINEAGE.value] = {
                    "status": "ok",
                    "edges": stats["total_edges"],
                    "artifacts": stats["unique_artifacts"],
                    "pipelines": stats["unique_pipelines"],
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.LINEAGE.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.LINEAGE.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.LINEAGE.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        # --- Telos ---
        try:
            tg = await self._get_telos_graph()
            if tg is not None:
                objectives = tg.list_objectives()
                edge_count = len(tg._edges)
                total_n += len(objectives)
                total_e += edge_count
                report.graphs[GraphOrigin.TELOS.value] = {
                    "status": "ok",
                    "objectives": len(objectives),
                    "key_results": len(tg._key_results),
                    "strategies": len(tg._strategies),
                    "hypotheses": len(tg._hypotheses),
                    "edges": edge_count,
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.TELOS.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.TELOS.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.TELOS.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        # --- Bridge ---
        try:
            br = await self._get_bridge_registry()
            if br is not None:
                cnt = await br.count()
                total_e += cnt
                report.graphs[GraphOrigin.BRIDGE.value] = {
                    "status": "ok",
                    "total_edges": cnt,
                }
                report.healthy_count += 1
            else:
                report.graphs[GraphOrigin.BRIDGE.value] = {
                    "status": "unavailable",
                    "error": self._init_errors.get(GraphOrigin.BRIDGE.value, "not loaded"),
                }
                report.failed_count += 1
        except Exception as exc:
            report.graphs[GraphOrigin.BRIDGE.value] = {"status": "error", "error": str(exc)}
            report.failed_count += 1

        report.total_nodes = total_n
        report.total_edges = total_e
        return report

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Clean up all graph connections.

        Safe to call multiple times.  Graphs that don't support explicit
        close (e.g. in-memory ConceptGraph) are simply dereferenced.
        """
        for graph_obj in [
            self._concept_graph,
            self._catalytic_graph,
            self._temporal_graph,
            self._lineage_graph,
            self._telos_graph,
            self._bridge_registry,
        ]:
            if graph_obj is not None and hasattr(graph_obj, "close"):
                try:
                    close_fn = graph_obj.close
                    if inspect.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                except Exception as close_exc:
                    logger.warning("GraphNexus: error closing graph: %s", close_exc)

        self._concept_graph = None
        self._catalytic_graph = None
        self._temporal_graph = None
        self._lineage_graph = None
        self._telos_graph = None
        self._bridge_registry = None
        self._init_errors.clear()

    async def __aenter__(self) -> GraphNexus:
        await self.init()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


__all__ = [
    "GraphNexus",
    "GraphOrigin",
    "NexusHealth",
    "NexusHit",
    "NexusQueryResult",
]
