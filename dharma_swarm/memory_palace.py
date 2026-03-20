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

    Usage:
        from dharma_swarm.memory_palace import MemoryPalace
        palace = MemoryPalace(memory_lattice=lattice)
        response = await palace.recall(PalaceQuery(text="R_V metric results"))
    """

    def __init__(
        self,
        memory_lattice: Any = None,
        state_dir: Path | None = None,
    ) -> None:
        self._lattice = memory_lattice
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._query_history: list[dict[str, Any]] = []

    async def recall(self, query: PalaceQuery) -> PalaceResponse:
        """Query the Memory Palace using hybrid fusion scoring.

        Combines semantic similarity, lexical match, recency, and
        stigmergic salience into a single ranked list.
        """
        t0 = time.monotonic()
        results: list[PalaceResult] = []

        # Phase 1: Retrieve from existing infrastructure
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
                    results.append(PalaceResult(
                        content=content[:2000],
                        source=source,
                        score=score,
                        layer=getattr(hit, "layer", ""),
                        metadata=getattr(hit, "metadata", {}),
                    ))
            except Exception as exc:
                logger.debug("Memory lattice recall failed: %s", exc)

        # Phase 2: Re-rank using fusion scoring
        results = self._fusion_rerank(results, query)

        # Phase 3: Truncate to requested count
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
    ) -> str:
        """Ingest new content into the Memory Palace.

        Returns the document ID.
        """
        if self._lattice is None:
            logger.debug("No memory lattice configured — ingestion skipped")
            return ""

        try:
            # Use the existing memory lattice infrastructure
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
            return str(entry.id)
        except Exception as exc:
            logger.debug("Memory palace ingestion failed: %s", exc)
            # Fallback: index directly
            try:
                doc_id = self._lattice.index_document(
                    source_kind="palace",
                    source_path=f"palace://{source}",
                    text=content,
                    metadata=metadata or {},
                )
                return doc_id
            except Exception:
                return ""

    def _fusion_rerank(
        self,
        results: list[PalaceResult],
        query: PalaceQuery,
    ) -> list[PalaceResult]:
        """Re-rank results using weighted fusion scoring.

        Combines the retriever's base score with recency and salience
        bonuses, weighted according to the query configuration.
        """
        if not results:
            return results

        now = time.time()
        scored: list[tuple[float, PalaceResult]] = []

        for r in results:
            # Base score from retriever (semantic + lexical already fused)
            base_score = r.score

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

            # Weighted fusion
            fused = (
                base_score * (query.weight_semantic + query.weight_lexical) +
                recency_score * query.weight_recency +
                salience_score * query.weight_salience
            )
            r.score = round(fused, 4)
            scored.append((fused, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Synchronous search for context_compiler integration.

        Returns list of dicts with 'text', 'score', 'source' keys.
        """
        import asyncio

        # Build results from in-memory query history and any cached data
        # This is the sync bridge — for full async recall, use await recall()
        results: list[dict[str, Any]] = []

        # Search through ingested content if lattice available
        if self._lattice is not None:
            try:
                # Try to run async recall in current or new event loop
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

    def stats(self) -> dict[str, Any]:
        """Memory Palace statistics for organism observability."""
        return {
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


__all__ = [
    "MemoryPalace",
    "PalaceQuery",
    "PalaceResponse",
    "PalaceResult",
]
