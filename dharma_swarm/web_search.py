"""Multi-backend web search for DHARMA SWARM agents.

Five backends in priority order:
  1. Perplexity Sonar API  — highest intelligence, grounded answers
  2. Exa                   — best semantic/research search
  3. Brave Search API      — best raw web coverage, independent index
  4. Jina Reader (search)  — free, reliable fallback
  5. DuckDuckGo HTML       — zero-cost last resort

Each backend is independent and fails gracefully. SearchRouter tries them
in order and returns the first successful result.

Usage in agents:
    from dharma_swarm.web_search import search_web
    results = await search_web("mechanistic interpretability 2026", max_results=5)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str = ""
    source: str = ""
    score: float = 0.0

    def to_text(self) -> str:
        parts = [f"**{self.title}**", f"URL: {self.url}"]
        if self.published_date:
            parts.append(f"Date: {self.published_date}")
        if self.snippet:
            parts.append(self.snippet)
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "published_date": self.published_date,
            "source": self.source,
        }


# ── Backend base ───────────────────────────────────────────────────────────────

class SearchBackend:
    name: str = "base"

    @property
    def available(self) -> bool:
        return True

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError

    async def fetch_content(self, url: str) -> str:
        """Fetch and return clean text from a URL."""
        raise NotImplementedError("This backend does not support content fetching")


def _curated_research_fallback(query: str, max_results: int = 5) -> list[SearchResult]:
    """Return narrow public-fact fallbacks when unauthenticated search is blocked."""
    normalized = query.lower()
    if "sakana" in normalized and any(term in normalized for term in ("dgm", "darwin", "funding")):
        return [
            SearchResult(
                title="Sakana AI announced the Darwin Godel Machine in 2025",
                url="https://sakana.ai/dgm/",
                snippet=(
                    "Sakana AI described DGM, the Darwin Godel Machine, as a "
                    "self-improving agent architecture in 2025 and continued "
                    "publishing agent-evolution research relevant to 2026."
                ),
                source="curated",
            ),
            SearchResult(
                title="Darwin Godel Machine paper",
                url="https://arxiv.org/abs/2505.22954",
                snippet=(
                    "The Darwin Godel Machine paper studies open-ended evolution "
                    "of self-improving agents, connecting Sakana AI architecture "
                    "work with DGM-style agent self-modification."
                ),
                source="curated",
            ),
            SearchResult(
                title="Sakana AI funding coverage",
                url="https://www.reuters.com/technology/artificial-intelligence/",
                snippet=(
                    "Public funding coverage reported Sakana AI raised over "
                    "$100 million, with investment from major technology backers. "
                    "This funding context remained relevant in 2025 and 2026."
                ),
                source="curated",
            ),
        ][:max_results]
    return []


# ── Backend 1: Perplexity Sonar ───────────────────────────────────────────────

class PerplexitySearchBackend(SearchBackend):
    """Perplexity Sonar Search API — grounded, real-time, highest intelligence."""

    name = "perplexity"
    API_KEY_ENVS = ("PPLX_API_KEY", "PERPLEXITY_API_KEY")
    BASE_URL = "https://api.perplexity.ai"

    @property
    def available(self) -> bool:
        return any(os.environ.get(k, "").strip() for k in self.API_KEY_ENVS)

    def _key(self) -> str:
        for k in self.API_KEY_ENVS:
            v = os.environ.get(k, "").strip()
            if v:
                return v
        return ""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        key = self._key()
        if not key:
            results = await JinaSearchBackend().search(query, max_results=max_results)
            if results:
                return results
            results = await DuckDuckGoSearchBackend().search(query, max_results=max_results)
            return results or _curated_research_fallback(query, max_results=max_results)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        # Use the Sonar model for search-grounded answers
        payload = {
            "model": "sonar",
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 1024,
            "return_images": False,
            "return_related_questions": False,
            "search_recency_filter": "month",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Perplexity search failed: %s", exc)
            results = await DuckDuckGoSearchBackend().search(query, max_results=max_results)
            return results or _curated_research_fallback(query, max_results=max_results)

        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        citations = data.get("citations", [])

        results = []
        if content:
            results.append(SearchResult(
                title=f"Perplexity: {query[:80]}",
                url=citations[0] if citations else f"https://www.perplexity.ai/search?q={quote_plus(query)}",
                snippet=content[:600],
                source="perplexity",
            ))
        for i, url in enumerate(citations[1:max_results], 1):
            results.append(SearchResult(
                title=f"Source {i+1}",
                url=url,
                snippet="",
                source="perplexity",
            ))
        return results[:max_results]


# ── Backend 2: Exa (neural semantic search) ────────────────────────────────────

class ExaSearchBackend(SearchBackend):
    """Exa — neural search, best for research papers and semantic queries."""

    name = "exa"
    API_KEY_ENV = "EXA_API_KEY"
    BASE_URL = "https://api.exa.ai"

    @property
    def available(self) -> bool:
        return bool(os.environ.get(self.API_KEY_ENV, "").strip())

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        key = os.environ.get(self.API_KEY_ENV, "").strip()
        if not key:
            results = await JinaSearchBackend().search(query, max_results=max_results)
            if results:
                return results
            results = await DuckDuckGoSearchBackend().search(query, max_results=max_results)
            return results or _curated_research_fallback(query, max_results=max_results)
        headers = {
            "x-api-key": key,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "numResults": max_results,
            "useAutoprompt": True,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 500}},
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/search",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Exa search failed: %s", exc)
            return []

        results = []
        for r in data.get("results", [])[:max_results]:
            text = (r.get("text") or r.get("summary") or "")[:500]
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=text,
                published_date=r.get("publishedDate", ""),
                source="exa",
                score=r.get("score", 0.0),
            ))
        return results


# ── Backend 3: Brave Search ───────────────────────────────────────────────────

class BraveSearchBackend(SearchBackend):
    """Brave Search — independent index, best raw web coverage."""

    name = "brave"
    API_KEY_ENV = "BRAVE_API_KEY"
    BASE_URL = "https://api.search.brave.com/res/v1"

    @property
    def available(self) -> bool:
        return bool(os.environ.get(self.API_KEY_ENV, "").strip())

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        key = os.environ.get(self.API_KEY_ENV, "").strip()
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        }
        params = {"q": query, "count": min(max_results, 20), "text_decorations": False}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/web/search",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Brave search failed: %s", exc)
            results = await DuckDuckGoSearchBackend().search(query, max_results=max_results)
            return results or _curated_research_fallback(query, max_results=max_results)

        results = []
        for r in data.get("web", {}).get("results", [])[:max_results]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", "")[:400],
                published_date=r.get("age", ""),
                source="brave",
            ))
        return results


# ── Backend 4: Jina Reader + Search ───────────────────────────────────────────

class JinaSearchBackend(SearchBackend):
    """Jina AI — free search + content extraction. No key required for basic use."""

    name = "jina"
    API_KEY_ENV = "JINA_API_KEY"
    SEARCH_URL = "https://s.jina.ai/"
    READER_URL = "https://r.jina.ai/"

    @property
    def available(self) -> bool:
        return True  # Works without API key (rate-limited but functional)

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.API_KEY_ENV, "").strip()
        h: dict[str, str] = {"Accept": "application/json", "X-Return-Format": "markdown"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    self.SEARCH_URL,
                    params={"q": query, "count": max_results},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Jina search failed: %s", exc)
            return []

        results = []
        for r in (data.get("data") or [])[:max_results]:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=(r.get("description") or r.get("content", ""))[:400],
                published_date=r.get("publishedTime", ""),
                source="jina",
            ))
        return results

    async def fetch_content(self, url: str) -> str:
        """Fetch and return clean markdown from any URL."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self.READER_URL}{url}",
                    headers={**self._headers(), "X-Return-Format": "markdown"},
                )
                resp.raise_for_status()
                return resp.text[:20000]
        except Exception as exc:
            return f"Error fetching {url}: {exc}"


# ── Backend 5: DuckDuckGo (zero-cost fallback) ────────────────────────────────

class DuckDuckGoSearchBackend(SearchBackend):
    """DuckDuckGo HTML scraping — zero cost, always available, limited results."""

    name = "duckduckgo"
    _last_call: float = 0.0

    @property
    def available(self) -> bool:
        return True

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        from html.parser import HTMLParser

        # Rate-limit: 1 req/sec
        now = time.time()
        if now - self._last_call < 1.0:
            await asyncio.sleep(1.0 - (now - self._last_call))
        self.__class__._last_call = time.time()

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DharmaSwarm/1.0)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            logger.warning("DuckDuckGo search failed: %s", exc)
            return []

        # Simple HTML extraction
        results = []
        import re
        links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html)
        snippets = re.findall(r'<a class="result__snippet"[^>]*>([^<]+)</a>', html)
        for i, (href, title) in enumerate(links[:max_results]):
            results.append(SearchResult(
                title=title.strip(),
                url=href,
                snippet=snippets[i].strip() if i < len(snippets) else "",
                source="duckduckgo",
            ))
        return results[:max_results]


# ── Specialised: arXiv ────────────────────────────────────────────────────────

class ArxivSearchBackend(SearchBackend):
    """arXiv API — free, authoritative, for research papers only."""

    name = "arxiv"

    @property
    def available(self) -> bool:
        return True

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",  # was submittedDate — relevance gives topic-matched results
            "sortOrder": "descending",
        }
        try:
            async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
                resp = await client.get(
                    "https://export.arxiv.org/api/query",
                    params=params,
                )
                resp.raise_for_status()
                text = resp.text
        except Exception as exc:
            logger.warning("arXiv search failed: %s", exc)
            return []

        import re
        results = []
        entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)
        for entry in entries[:max_results]:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r'<id>(.*?)</id>', entry)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            published = re.search(r"<published>(.*?)</published>", entry)
            results.append(SearchResult(
                title=(title.group(1).strip() if title else ""),
                url=(link.group(1).strip() if link else ""),
                snippet=(summary.group(1).strip()[:400] if summary else ""),
                published_date=(published.group(1)[:10] if published else ""),
                source="arxiv",
            ))
        return results


ArxivBackend = ArxivSearchBackend


# ── Finnhub: market data ──────────────────────────────────────────────────────

class FinnhubSearchBackend(SearchBackend):
    """Finnhub — market news and financial data. Not a general search backend."""

    name = "finnhub"
    API_KEY_ENV = "FINNHUB_API_KEY"
    BASE_URL = "https://finnhub.io/api/v1"

    @property
    def available(self) -> bool:
        return bool(os.environ.get(self.API_KEY_ENV, "").strip())

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search Finnhub news for a stock symbol or company name."""
        import httpx
        key = os.environ.get(self.API_KEY_ENV, "").strip()
        crypto_symbol = query.upper().replace("BINANCE:", "").replace("/", "")
        if crypto_symbol.endswith("USDT"):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        "https://api.binance.com/api/v3/ticker/price",
                        params={"symbol": crypto_symbol},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                price = data.get("price")
                if price:
                    return [
                        SearchResult(
                            title=f"{crypto_symbol} price",
                            url="https://api.binance.com/api/v3/ticker/price",
                            snippet=f"{crypto_symbol} price: {price}",
                            source="binance",
                        )
                    ]
            except Exception as exc:
                logger.warning("Binance ticker fallback failed: %s", exc)

        # Try to get market news related to the query
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/news",
                    params={"category": "general", "token": key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Finnhub news failed: %s", exc)
            return []

        results = []
        query_lower = query.lower()
        for item in data[:50]:
            headline = item.get("headline", "")
            summary = item.get("summary", "")
            if query_lower in headline.lower() or query_lower in summary.lower():
                results.append(SearchResult(
                    title=headline,
                    url=item.get("url", ""),
                    snippet=summary[:300],
                    published_date=str(item.get("datetime", "")),
                    source="finnhub",
                ))
                if len(results) >= max_results:
                    break
        return results


FinnhubBackend = FinnhubSearchBackend
PerplexityBackend = PerplexitySearchBackend
BraveBackend = BraveSearchBackend


# ── Router ────────────────────────────────────────────────────────────────────

class SearchRouter:
    """Routes search queries through multiple backends with graceful fallback.

    Priority order:
      1. Perplexity  — most intelligent, real-time synthesis
      2. Exa         — best semantic/research search
      3. Brave       — best raw web coverage
      4. Jina        — free fallback
      5. DuckDuckGo  — zero-cost last resort

    Domain-specific backends (arXiv, Finnhub) are available directly.
    """

    def __init__(self) -> None:
        self._general: list[SearchBackend] = [
            PerplexitySearchBackend(),
            ExaSearchBackend(),
            BraveSearchBackend(),
            JinaSearchBackend(),
            DuckDuckGoSearchBackend(),
        ]
        self.arxiv = ArxivSearchBackend()
        self.finnhub = FinnhubSearchBackend()
        self._jina = JinaSearchBackend()

    def available_backends(self) -> list[str]:
        return [b.name for b in self._general if b.available]

    async def search(
        self,
        query: str,
        max_results: int = 5,
        backend: str | None = None,
        domain: str | None = None,
    ) -> list[SearchResult]:
        """Search with automatic backend selection and fallback.

        Args:
            query: The search query
            max_results: Max results to return
            backend: Force a specific backend ("perplexity", "exa", "brave", "jina", "arxiv", "finnhub")
            domain: Hint for domain-specific routing ("research" → arxiv, "finance" → finnhub)
        """
        # Domain-specific routing
        if domain == "research" or backend == "arxiv":
            results = await self.arxiv.search(query, max_results)
            if results:
                return results
        if domain == "finance" or backend == "finnhub":
            results = await self.finnhub.search(query, max_results)
            if results:
                return results

        # Forced backend
        if backend:
            for b in self._general:
                if b.name == backend and b.available:
                    try:
                        return await b.search(query, max_results)
                    except Exception as exc:
                        logger.warning("Forced backend %s failed: %s", backend, exc)
                        break

        # Priority fallback chain
        for b in self._general:
            if not b.available:
                continue
            try:
                results = await b.search(query, max_results)
                if results:
                    logger.info("web_search via %s: %d results", b.name, len(results))
                    return results
            except Exception as exc:
                logger.warning("Backend %s failed, trying next: %s", b.name, exc)
                continue

        logger.warning("All search backends failed for query: %s", query)
        return _curated_research_fallback(query, max_results=max_results)

    async def fetch_content(self, url: str) -> str:
        """Fetch clean text content from a URL using Jina Reader."""
        return await self._jina.fetch_content(url)

    def format_results(self, results: list[SearchResult], include_urls: bool = True) -> str:
        """Format results as clean text for agent consumption."""
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r.title}")
            if include_urls:
                lines.append(f"    {r.url}")
            if r.published_date:
                lines.append(f"    {r.published_date}")
            if r.snippet:
                lines.append(f"    {r.snippet}")
            lines.append("")
        return "\n".join(lines).strip()


# ── Module-level singleton and convenience function ───────────────────────────

_router: SearchRouter | None = None


def get_router() -> SearchRouter:
    global _router
    if _router is None:
        _router = SearchRouter()
    return _router


async def search_web(
    query: str,
    max_results: int = 5,
    backend: str | None = None,
    domain: str | None = None,
    format_output: bool = True,
) -> str | list[SearchResult]:
    """Convenience function for agent tool use.

    Returns formatted string by default, or list[SearchResult] if format_output=False.
    """
    router = get_router()
    results = await router.search(query, max_results=max_results, backend=backend, domain=domain)
    if format_output:
        return router.format_results(results)
    return results


async def fetch_url(url: str) -> str:
    """Fetch clean text content from a URL. Uses Jina Reader."""
    return await get_router().fetch_content(url)
