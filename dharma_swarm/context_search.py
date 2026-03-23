"""Context Search Engine — lazy context loading via search.

Instead of preloading all 42 ecosystem paths into every agent's context
(Warp's MCP subagent insight: saves 26% tokens), agents get a search
function that pulls only relevant context on demand.

Builds a keyword index from ecosystem paths + file metadata.
Agents call search() with their task description to get just the
context they need.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ContextResult(BaseModel):
    """A single search result with path, relevance, and snippet."""

    path: str
    relevance: float
    category: str = "unknown"
    snippet: str = ""
    size_bytes: int = 0
    age_hours: float = 0.0


class ContextSearchEngine:
    """Builds and searches a keyword index over the dharma ecosystem.

    Replaces the brute-force approach of loading everything into
    every agent's context. Instead, agents search for what they need.
    """

    def __init__(
        self,
        ecosystem_paths: dict[str, dict] | None = None,
        index_path: Path | None = None,
    ):
        self._paths = ecosystem_paths or {}
        self._index_path = index_path
        self._keyword_index: dict[str, list[str]] = {}
        self._path_meta: dict[str, dict] = {}
        self._built = False

    def build_index(self, force: bool = False) -> int:
        """Build keyword index from ecosystem paths.

        Indexes file names, directory names, and first few lines of files.
        Returns number of paths indexed.
        """
        if self._built and not force:
            return len(self._keyword_index)

        # If no explicit paths, use ecosystem map
        if not self._paths:
            self._paths = self._load_ecosystem_map()

        count = 0
        for path_str, meta in self._paths.items():
            path = Path(path_str).expanduser()
            if not path.exists():
                continue

            category = meta.get("category", "unknown")
            keywords = self._extract_keywords(path, category)

            for kw in keywords:
                self._keyword_index.setdefault(kw, []).append(path_str)

            self._path_meta[path_str] = {
                "category": category,
                "size": path.stat().st_size if path.is_file() else 0,
                "mtime": path.stat().st_mtime,
            }
            count += 1

        self._built = True
        logger.info("Indexed %d paths with %d keywords",
                     count, len(self._keyword_index))
        return count

    def search(
        self,
        query: str,
        max_results: int = 5,
        category: str | None = None,
    ) -> list[ContextResult]:
        """Search for relevant context paths.

        Args:
            query: Natural language search query.
            max_results: Maximum results to return.
            category: Filter to specific category.

        Returns:
            Sorted list of ContextResult by relevance.
        """
        if not self._built:
            self.build_index()

        query_words = set(re.findall(r'\w+', query.lower()))
        scores: dict[str, float] = {}

        for word in query_words:
            # Exact keyword match
            for path in self._keyword_index.get(word, []):
                scores[path] = scores.get(path, 0) + 2.0

            # Prefix match (e.g., "test" matches "testing")
            for kw, paths in self._keyword_index.items():
                if kw.startswith(word) and kw != word:
                    for path in paths:
                        scores[path] = scores.get(path, 0) + 0.5

        # Filter by category if specified
        if category:
            scores = {
                p: s for p, s in scores.items()
                if self._path_meta.get(p, {}).get("category") == category
            }

        # Sort by score, build results
        sorted_paths = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results: list[ContextResult] = []

        for path_str, score in sorted_paths[:max_results]:
            meta = self._path_meta.get(path_str, {})
            age_h = (time.time() - meta.get("mtime", time.time())) / 3600

            snippet = self._get_snippet(Path(path_str))

            results.append(ContextResult(
                path=path_str,
                relevance=min(score / 10.0, 1.0),
                category=meta.get("category", "unknown"),
                snippet=snippet,
                size_bytes=meta.get("size", 0),
                age_hours=round(age_h, 1),
            ))

        return results

    def get_context_for_task(
        self,
        task: str,
        budget: int = 10_000,
    ) -> str:
        """Search and assemble context for a specific task.

        Reads the most relevant files up to the character budget.
        This is what agents call instead of getting the full 30K dump.
        """
        results = self.search(task, max_results=8)

        if not results:
            return ""

        sections: list[str] = ["# Task-Relevant Context"]
        used = 0

        for result in results:
            if used >= budget:
                break

            path = Path(result.path).expanduser()
            if not path.exists() or not path.is_file():
                continue

            try:
                content = path.read_text()
            except Exception:
                continue

            remaining = budget - used
            if len(content) > remaining:
                content = content[:remaining] + "\n... [truncated]"

            sections.append(
                f"\n## {path.name} (relevance: {result.relevance:.1f})\n{content}"
            )
            used += len(content)

        return "\n".join(sections)

    def _extract_keywords(self, path: Path, category: str) -> list[str]:
        """Extract searchable keywords from a path."""
        keywords: list[str] = []

        # Path components as keywords
        for part in path.parts:
            words = re.findall(r'[a-z]+', part.lower())
            keywords.extend(words)

        # Category
        keywords.append(category.lower())

        # File extension
        if path.suffix:
            keywords.append(path.suffix.lstrip(".").lower())

        # First 5 lines of file content for keyword extraction
        if path.is_file() and path.stat().st_size < 100_000:
            try:
                with open(path) as f:
                    for i, line in enumerate(f):
                        if i >= 5:
                            break
                        words = re.findall(r'[a-z]{3,}', line.lower())
                        keywords.extend(words)
            except Exception:
                logger.debug("Keyword extraction failed", exc_info=True)

        return list(set(keywords))

    def _get_snippet(self, path: Path, max_chars: int = 200) -> str:
        """Get a brief snippet from a file for search results."""
        if not path.exists() or not path.is_file():
            return f"[directory: {path}]"
        try:
            with open(path) as f:
                text = f.read(max_chars)
            # Clean up
            text = text.replace("\n", " ").strip()
            return text[:max_chars]
        except Exception:
            return "[unreadable]"

    def _load_ecosystem_map(self) -> dict[str, dict]:
        """Load paths from dharma_swarm's ecosystem map."""
        try:
            from dharma_swarm.ecosystem_map import ECOSYSTEM_MAP
            result: dict[str, dict] = {}
            for domain, entries in ECOSYSTEM_MAP.items():
                if isinstance(entries, dict):
                    for _name, path_str in entries.items():
                        if isinstance(path_str, str):
                            result[path_str] = {"category": domain}
                        elif isinstance(path_str, dict) and "path" in path_str:
                            result[path_str["path"]] = {"category": domain}
            return result
        except ImportError:
            return {}
