"""Memory Palace — Layer 3 of the DHARMA SWARM 7-layer stack.

Bridges the existing MemoryLattice/HybridRetriever with the organism's
heartbeat loop and AMIROS registries. Implements the architectural
vision from the 10-domain Memory Palace research sprint:

    BGE-M3 (multilingual embeddings) → LanceDB (vector storage) → FTS5 (hybrid search)

In the current implementation, we wrap the existing infrastructure:
    - UnifiedIndex provides FTS5 (SQLite full-text search)
    - HybridRetriever provides BM25 + TF-IDF fusion
    - StrangeLoopMemory provides layered memory with fitness scoring
    - This module adds: organism-aware context compilation, stigmergic
      coordination signals, and AMIROS-backed knowledge provenance.

Phase 6 upgrades:
    - VectorStore (sqlite-vec + TF-IDF) for real semantic similarity scores
    - Bi-temporal ingestion (event_time + ingestion_time)
    - _fusion_rerank() now receives actual vector similarity scores
    - decay() and gc() delegate to VectorStore
    - stats() includes VectorStore stats

Ground: Beer (S4 intelligence needs access to S1 operational memory),
        Varela (memory IS the organism — not a database query),
        Kauffman (each memory expands the adjacent possible).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PalaceQuery:
    """A structured query to the Memory Palace."""
    text: str
    agent_id: str = ""
    task_context: str = ""
    max_results: int = 10
    # Score fusion weights (sum to 1.0)
    weight_semantic: float = 0.4   # Vector similarity (BGE-M3 concept)
    weight_lexical: float = 0.3    # FTS5 / BM25
    weight_recency: float = 0.15   # Time decay
    weight_salience: float = 0.15  # Stigmergic salience


@dataclass
class PalaceResult:
    """A single result from the Memory Palace."""
    content: str
    source: str
    score: float
    layer: str = ""
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PalaceResponse:
    """Full response from a Memory Palace query."""
    results: list[PalaceResult]
    query_text: str
    duration_ms: float
    total_indexed: int = 0


class MemoryPalace:
    """The organism's memory system — not a database, a living substrate.

    Wraps the existing MemoryLattice and HybridRetriever with
    organism-aware scoring and AMIROS provenance tracking.

    Phase 6: also maintains a VectorStore for real semantic similarity
    scoring. The _fusion_rerank() method now receives actual vector scores
    instead of the placeholder base_score from the lattice.

    Phase 7b: optionally integrates GraphNexus for concept-graph-aware
    search. When a graph_store is provided, recall() also queries the
    semantic graph and merges concept hits into results.

    Usage:
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(memory_lattice=lattice)
        response = await palace.recall(PalaceQuery(text="R_V metric results"))
    """

    def __init__(
        self,
        memory_lattice: Any = None,
        state_dir: Path | None = None,
        graph_nexus: Any = None,
    ) -> None:
        self._lattice = memory_lattice
        self._graph_nexus = graph_nexus  # Phase 7b: GraphNexus bridge
        self._query_history: list[dict[str, Any]] = []

        # Phase 6: VectorStore for real semantic similarity.
        # When state_dir is None (no explicit config), use an isolated temp directory
        # so each MemoryPalace() instantiation gets a clean store (important for tests
        # and short-lived instances). When state_dir is provided (production use),
        # data persists across restarts.
        self._vector_store: Any = None  # VectorStore | None
        if state_dir is not None:
            self._state_dir = state_dir
            try:
                from dharma_swarm.vector_store import VectorStore
                self._vector_store = VectorStore(state_dir=self._state_dir)
            except Exception as exc:
                logger.debug("VectorStore init failed (non-fatal): %s", exc)
        else:
            # No state_dir provided — use a temp dir that is unique per instance.
            # This preserves the pre-Phase-6 behavior for callers that didn't
            # configure a persistent state directory.
            import tempfile
            self._tmp_dir = tempfile.mkdtemp(prefix="dharma_palace_")
            self._state_dir = Path(self._tmp_dir)
            try:
                from dharma_swarm.vector_store import VectorStore
                self._vector_store = VectorStore(state_dir=self._state_dir)
            except Exception as exc:
                logger.debug("VectorStore (ephemeral) init failed (non-fatal): %s", exc)

    async def recall(self, query: PalaceQuery) -> PalaceResponse:
        """Query the Memory Palace using hybrid fusion scoring.

        Combines semantic similarity, lexical match, recency, and
        stigmergic salience into a single ranked list.

        Phase 6: vector search results from VectorStore feed real semantic
        scores into _fusion_rerank().
        """
        t0 = time.monotonic()
        results: list[PalaceResult] = []

        # Phase 1: Retrieve from existing infrastructure (lattice)
        lattice_results: list[PalaceResult] = []
        if self._lattice is not None:
            try:
                # Use the existing hybrid retriever
                hits = await self._lattice.recall(
                    query=query.text,
                    limit=query.max_results * 2,  # Over-fetch for re-ranking
                )
                for hit in hits:
                    content = getattr(hit, "content", str(hit))
                    score = getattr(hit, "score", 0.5)
                    source = getattr(hit, "source_path", "unknown")
                    lattice_results.append(PalaceResult(
                        content=content[:2000],
                        source=source,
                        score=score,
                        layer=getattr(hit, "layer", ""),
                        metadata=getattr(hit, "metadata", {}),
                    ))
            except Exception as exc:
                logger.debug("Memory lattice recall failed: %s", exc)

        # Phase 2: Vector search — get real semantic scores
        vector_score_map: dict[str, float] = {}  # content_hash → vector_score
        vector_results: list[PalaceResult] = []
        if self._vector_store is not None:
            try:
                raw = self._vector_store.search_hybrid(
                    query_text=query.text,
                    top_k=query.max_results * 2,
                )
                for item in raw:
                    content = item.get("content", "")[:2000]
                    score = item.get("score", 0.0)
                    source = item.get("source", "vector_store")
                    layer = item.get("layer", "working")
                    meta = dict(item.get("metadata", {}))
                    # Store event_time for recency scoring
                    if item.get("event_time"):
                        meta["recorded_at"] = item["event_time"]
                    pr = PalaceResult(
                        content=content,
                        source=source,
                        score=score,
                        layer=layer,
                        metadata=meta,
                    )
                    vector_results.append(pr)
                    # Index by content for cross-referencing with lattice results
                    content_key = content[:200]
                    vector_score_map[content_key] = score
            except Exception as exc:
                logger.debug("VectorStore recall failed (non-fatal): %s", exc)

        # Phase 2b: GraphNexus query — cross-graph concept hits
        graph_results: list[PalaceResult] = []
        if self._graph_nexus is not None:
            try:
                nexus_result = await self._graph_nexus.query_about(query.text)
                for hit in getattr(nexus_result, "semantic_hits", []):
                    relevance = getattr(hit, "relevance", 0.5)
                    name = getattr(hit, "name", "")
                    node_type = getattr(hit, "node_type", "")
                    meta = getattr(hit, "metadata", {})
                    if isinstance(meta, dict):
                        meta = dict(meta)
                    else:
                        meta = {}
                    # Boost by graph centrality heuristic
                    centrality_bonus = min(0.2, len(getattr(hit, "metadata", {}).get("edges", [])) * 0.02)
                    graph_results.append(PalaceResult(
                        content=f"[{node_type}] {name}: {meta.get('description', '')}".strip()[:2000],
                        source=f"graph:{getattr(hit, 'graph', 'nexus')}",
                        score=relevance + centrality_bonus,
                        layer="semantic_graph",
                        metadata={**meta, "graph_origin": getattr(hit, "graph", "")},
                    ))
                # Also include temporal and telos hits at lower priority
                for hit_list in (
                    getattr(nexus_result, "temporal_hits", []),
                    getattr(nexus_result, "telos_hits", []),
                ):
                    for hit in hit_list[:2]:
                        name = getattr(hit, "name", "")
                        graph_results.append(PalaceResult(
                            content=f"[{getattr(hit, 'node_type', '')}] {name}".strip()[:2000],
                            source=f"graph:{getattr(hit, 'graph', 'nexus')}",
                            score=getattr(hit, "relevance", 0.3) * 0.7,
                            layer="semantic_graph",
                            metadata={"graph_origin": getattr(hit, "graph", "")},
                        ))
            except Exception as exc:
                logger.debug("GraphNexus recall failed (non-fatal): %s", exc)

        # Merge: start with lattice results, augment with vector scores
        results = list(lattice_results)

        # Add vector results not already in lattice results
        existing_contents = {r.content[:200] for r in results}
        for vr in vector_results:
            if vr.content[:200] not in existing_contents:
                results.append(vr)
                existing_contents.add(vr.content[:200])

        # Add graph results not already present
        for gr in graph_results:
            if gr.content[:200] not in existing_contents:
                results.append(gr)
                existing_contents.add(gr.content[:200])

        # Phase 3: Re-rank using fusion scoring with real vector scores
        results = self._fusion_rerank(results, query, vector_score_map)

        # Phase 4: Truncate to requested count
        results = results[:query.max_results]

        duration_ms = (time.monotonic() - t0) * 1000

        # Track query for organism observability
        self._query_history.append({
            "text": query.text[:100],
            "agent_id": query.agent_id,
            "results": len(results),
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._query_history) > 500:
            self._query_history = self._query_history[-500:]

        return PalaceResponse(
            results=results,
            query_text=query.text,
            duration_ms=duration_ms,
        )

    async def ingest(
        self,
        content: str,
        source: str,
        *,
        layer: str = "working",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        event_time: datetime | None = None,
    ) -> str:
        """Ingest new content into the Memory Palace.

        Phase 6: also upserts into VectorStore with bi-temporal metadata.
        Returns the document ID.
        """
        doc_id = ""

        # Existing lattice ingestion (unchanged)
        if self._lattice is not None:
            try:
                from dharma_swarm.strange_loop_memory import MemoryLayer
                layer_map = {
                    "immediate": MemoryLayer.IMMEDIATE,
                    "working": MemoryLayer.WORKING,
                    "consolidated": MemoryLayer.CONSOLIDATED,
                    "crystallized": MemoryLayer.CRYSTALLIZED,
                }
                mem_layer = layer_map.get(layer, MemoryLayer.WORKING)
                entry = await self._lattice.remember(
                    content,
                    mem_layer,
                    source=source,
                    tags=tags or [],
                )
                doc_id = str(entry.id)
            except Exception as exc:
                logger.debug("Memory palace lattice ingestion failed: %s", exc)
                # Fallback: index directly
                try:
                    doc_id = self._lattice.index_document(
                        source_kind="palace",
                        source_path=f"palace://{source}",
                        text=content,
                        metadata=metadata or {},
                    )
                except Exception:
                    pass

        # Phase 6: Also upsert into VectorStore (bi-temporal).
        # We always index into VectorStore as a side-effect for future recall.
        # We only use the VectorStore's ID as the primary doc_id when an explicit
        # state_dir was provided (persistent mode). In ephemeral mode (no state_dir
        # was given to __init__), we preserve backward-compat and return "".
        _has_persistent_store = hasattr(self, "_state_dir") and not hasattr(self, "_tmp_dir")
        if self._vector_store is not None and content and content.strip():
            try:
                meta = dict(metadata or {})
                if tags:
                    meta["tags"] = tags
                vec_id = self._vector_store.upsert(
                    content=content,
                    source=source,
                    layer=layer,
                    metadata=meta,
                    event_time=event_time,
                )
                # Use vec_id as doc_id only in persistent mode when lattice gave nothing
                if not doc_id and vec_id > 0 and _has_persistent_store:
                    doc_id = f"vec:{vec_id}"
            except Exception as exc:
                logger.debug("VectorStore upsert failed (non-fatal): %s", exc)

        return doc_id

    def _fusion_rerank(
        self,
        results: list[PalaceResult],
        query: PalaceQuery,
        vector_score_map: dict[str, float] | None = None,
    ) -> list[PalaceResult]:
        """Re-rank results using weighted fusion scoring.

        Phase 6: uses actual vector similarity from VectorStore as the
        semantic score component when available, rather than relying solely
        on the retriever's base_score.

        Combines:
        - semantic_score: real vector similarity (Phase 6) or base retriever score
        - lexical_score: BM25/FTS5 score from existing infrastructure
        - recency_score: exponential time decay over 7 days
        - salience_score: stigmergic salience marks
        """
        if not results:
            return results

        now = time.time()
        vmap = vector_score_map or {}
        scored: list[tuple[float, PalaceResult]] = []

        for r in results:
            # Semantic score: try vector_score_map first, fall back to base_score
            content_key = r.content[:200]
            if content_key in vmap:
                # Real vector similarity score [0, 1]
                semantic_score = vmap[content_key]
                # Lexical is the remaining base score component
                lexical_score = r.score  # Original retriever score
            else:
                # No vector score available — use base score for both components
                semantic_score = r.score
                lexical_score = r.score

            # Recency bonus: exponential decay over 7 days
            recency_score = 0.5  # default for items without timestamps
            ts_str = r.metadata.get("recorded_at", r.timestamp)
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str).timestamp()
                    age_days = (now - ts) / 86400
                    recency_score = max(0.0, 1.0 - (age_days / 7.0))
                except (ValueError, TypeError):
                    pass

            # Salience bonus: from stigmergic marks
            salience_score = r.metadata.get("salience", 0.5)
            if isinstance(salience_score, str):
                try:
                    salience_score = float(salience_score)
                except ValueError:
                    salience_score = 0.5

            # Weighted fusion with real semantic and lexical scores
            fused = (
                semantic_score * query.weight_semantic +
                lexical_score * query.weight_lexical +
                recency_score * query.weight_recency +
                salience_score * query.weight_salience
            )
            r.score = round(fused, 4)
            scored.append((fused, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    def _search_graph(self, query_text: str, limit: int = 5) -> list[PalaceResult]:
        """Search the GraphStore semantic graph for concept matches.

        Scores hits by: FTS5 relevance + edge count (centrality) + bridge
        count (cross-graph connections).  Returns PalaceResult items.
        """
        if self._graph_store is None:
            return []

        results: list[PalaceResult] = []
        try:
            nodes = self._graph_store.search_nodes("semantic", query_text, limit=limit)
        except Exception:
            return []

        for node in nodes[:limit]:
            node_id = node.get("id", "")
            name = node.get("name", "")
            data = node.get("data", {})
            definition = ""
            if isinstance(data, dict):
                definition = data.get("definition", "")

            content = f"[Concept] {name}"
            if definition:
                content += f": {definition[:300]}"

            # Score components
            try:
                edge_count = len(self._graph_store.get_edges("semantic", node_id))
            except Exception:
                edge_count = 0

            try:
                bridge_count = len(self._graph_store.get_bridges(
                    target_graph="semantic", target_id=node_id
                ))
            except Exception:
                bridge_count = 0

            # Composite score: base relevance + centrality bonus + bridge bonus
            score = 0.5 + min(edge_count * 0.05, 0.3) + min(bridge_count * 0.03, 0.2)

            results.append(PalaceResult(
                content=content[:2000],
                source=f"graph:semantic:{node_id}",
                score=round(score, 4),
                layer="semantic",
                metadata={
                    "node_id": node_id,
                    "edge_count": edge_count,
                    "bridge_count": bridge_count,
                    "origin": "graph_nexus",
                },
            ))

        return results

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Synchronous search for context_compiler integration.

        Returns list of dicts with 'text', 'score', 'source' keys.
        Phase 6: tries VectorStore first (sync), then falls back to lattice.
        """
        import asyncio

        results: list[dict[str, Any]] = []

        # Phase 6: Try VectorStore synchronously first
        if self._vector_store is not None:
            try:
                raw = self._vector_store.search_hybrid(query_text=query, top_k=top_k)
                for item in raw:
                    results.append({
                        "text": item.get("content", "")[:500],
                        "score": item.get("score", 0.0),
                        "source": item.get("source", ""),
                    })
                if results:
                    return results[:top_k]
            except Exception as exc:
                logger.debug("VectorStore sync search failed: %s", exc)

        # Fallback: async lattice search
        if self._lattice is not None:
            try:
                try:
                    loop = asyncio.get_running_loop()  # noqa: F841
                    # Already in async context — can't block
                    return results
                except RuntimeError:
                    pass

                loop = asyncio.new_event_loop()
                try:
                    palace_query = PalaceQuery(text=query, max_results=top_k)
                    response = loop.run_until_complete(self.recall(palace_query))
                    for r in response.results:
                        results.append({
                            "text": r.content[:500],
                            "score": r.score,
                            "source": r.source,
                        })
                finally:
                    loop.close()
            except Exception as exc:
                logger.debug("Palace sync search failed: %s", exc)

        return results[:top_k]

    def decay(
        self,
        max_age_days: float = 30.0,
        decay_rate: float = 0.95,
    ) -> int:
        """Delegate confidence decay to VectorStore. Returns rows updated."""
        if self._vector_store is None:
            return 0
        try:
            return self._vector_store.decay_confidence(
                max_age_days=max_age_days,
                decay_rate=decay_rate,
            )
        except Exception as exc:
            logger.debug("MemoryPalace.decay failed (non-fatal): %s", exc)
            return 0

    def gc(self, min_confidence: float = 0.01) -> int:
        """Delegate garbage collection to VectorStore. Returns removed count."""
        if self._vector_store is None:
            return 0
        try:
            return self._vector_store.gc(min_confidence=min_confidence)
        except Exception as exc:
            logger.debug("MemoryPalace.gc failed (non-fatal): %s", exc)
            return 0

    def stats(self) -> dict[str, Any]:
        """Memory Palace statistics for organism observability.

        Phase 6: includes VectorStore stats.
        """
        base = {
            "queries_served": len(self._query_history),
            "avg_latency_ms": (
                sum(q["duration_ms"] for q in self._query_history[-50:])
                / max(1, len(self._query_history[-50:]))
            ),
            "avg_results": (
                sum(q["results"] for q in self._query_history[-50:])
                / max(1, len(self._query_history[-50:]))
            ),
        }
        # Phase 6: add VectorStore stats
        if self._vector_store is not None:
            try:
                base["vector_store"] = self._vector_store.stats()
            except Exception:
                base["vector_store"] = {}
        return base


__all__ = [
    "MemoryPalace",
    "PalaceQuery",
    "PalaceResponse",
    "PalaceResult",
]
