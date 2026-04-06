"""Concrete SearchBackend implementations for AutoResearch engine.

Wraps dharma_swarm.web_search.SearchRouter into the AutoResearch protocol.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .models import ResearchBrief, ResearchQuery, SourceDocument
from .search import SearchBackend, RawSourceDocument


class WebSearchBackend:
    """Concrete AutoResearch SearchBackend backed by web_search.SearchRouter.

    Drop-in replacement for NullSearchBackend. Tries 5 backends with fallback:
    Perplexity → Exa → Brave → Jina → DuckDuckGo.

    Usage:
        from dharma_swarm.auto_research.backends import WebSearchBackend
        from dharma_swarm.auto_research.engine import AutoResearchEngine
        engine = AutoResearchEngine(search_backend=WebSearchBackend())
    """

    def __init__(self, max_results_per_query: int = 5) -> None:
        self.max_results_per_query = max_results_per_query

    def search(
        self,
        brief: ResearchBrief,
        queries: list[ResearchQuery],
    ) -> list[RawSourceDocument]:
        """Synchronous wrapper — AutoResearch engine calls this synchronously."""
        return asyncio.get_event_loop().run_until_complete(
            self._async_search(brief, queries)
        )

    async def _async_search(
        self,
        brief: ResearchBrief,
        queries: list[ResearchQuery],
    ) -> list[RawSourceDocument]:
        from dharma_swarm.web_search import get_router
        router = get_router()
        all_results: list[RawSourceDocument] = []
        seen_urls: set[str] = set()

        # Determine domain hint from brief
        domain = None
        topic = (brief.topic or "").lower()
        if any(k in topic for k in ("paper", "arxiv", "research", "study", "interpretability")):
            domain = "research"
        elif any(k in topic for k in ("stock", "market", "finance", "trading", "crypto")):
            domain = "finance"

        for q in queries[:5]:  # cap at 5 queries to control costs
            query_str = q.text if hasattr(q, "text") else str(q)
            results = await router.search(
                query_str,
                max_results=self.max_results_per_query,
                domain=domain,
            )
            for r in results:
                if r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                all_results.append({
                    "url": r.url,
                    "title": r.title,
                    "snippet": r.snippet,
                    "published_date": r.published_date,
                    "source": r.source,
                    "query": query_str,
                })

        return all_results
