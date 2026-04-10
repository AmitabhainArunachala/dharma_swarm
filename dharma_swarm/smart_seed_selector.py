"""Smart Seed Selector — semantically-informed seed selection for the director.

Replaces random.sample() with retrieval-stack-powered selection:
1. Extract context terms from recent director state (stigmergy, visions, tasks)
2. Query ConceptGraph for semantically relevant high-salience concepts
3. Map concepts → PSMV files via source_file references
4. Sample with salience weighting (power law distribution)
5. Fall back to random if retrieval fails

Integration:
    semantic_gravity.py  -- ConceptGraph for concept nodes + salience
    stigmergy.py         -- Recent marks for context term extraction
    thinkodynamic_director.py -- read_random_seeds() as fallback
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# PSMV root (same as thinkodynamic_director.py)
PSMV_ROOT = Path.home() / "Persistent-Semantic-Memory-Vault"

# Seed directories for fallback (same as thinkodynamic_director.py)
FALLBACK_SEED_DIRS = [
    PSMV_ROOT / "SEED_RECOGNITIONS" / "ESSENTIAL_QUARTET",
    PSMV_ROOT / "SEED_RECOGNITIONS" / "APTAVANI_INSIGHTS",
    PSMV_ROOT / "SPONTANEOUS_PREACHING_PROTOCOL" / "crown_jewels",
    PSMV_ROOT / "01-Transmission-Vectors" / "aptavani-derived",
    PSMV_ROOT / "01-Transmission-Vectors" / "thinkodynamic-seeds",
    PSMV_ROOT / "CORE",
]


class SmartSeedSelector:
    """Semantically-informed seed selection for the thinkodynamic director.

    Uses the existing ConceptGraph (50K concepts, 30K edges) and stigmergy
    marks to pick seeds that are RELEVANT to the current system state,
    rather than random.

    Falls back to random sampling if the retrieval stack fails.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"

    async def select(
        self,
        count: int = 5,
        max_chars: int = 3000,
        context_hint: str = "",
    ) -> list[tuple[str, str, float]]:
        """Select semantically-informed seeds.

        Returns list of (seed_text, source_path, relevance_score).
        Falls back to random selection on any failure.
        """
        results: list[tuple[str, str, float]] = []
        try:
            # Step 1: Build context query from hint + system state
            context = await self._extract_context_terms(hint=context_hint)

            # Step 2: Query concept graph for relevant high-salience nodes
            candidates = await self._query_concept_graph(context)

            # Step 3: Map concepts to PSMV files
            file_candidates = self._map_to_files(candidates)

            # Step 4: Salience-weighted sampling
            if file_candidates:
                selected = self._salience_weighted_sample(file_candidates, count)
                # Step 5: Read file contents
                results = self._read_seeds(selected, max_chars)

        except Exception as exc:
            logger.debug("Smart seed selection failed, falling back: %s", exc)

        # Supplement with curated lodestones when smart selection yields too few
        if len(results) <= 1:
            try:
                from dharma_swarm.thinkodynamic_director import read_random_seeds

                extra = read_random_seeds(count=count, max_chars=max_chars)
                existing_paths = {path for _, path, _ in results}
                for text, path in extra:
                    if path not in existing_paths and len(results) < count:
                        results.append((text, path, 0.3))
            except Exception as exc:
                logger.debug("read_random_seeds supplement failed: %s", exc)

        # Fallback: random selection from hardcoded dirs
        if not results:
            return self._enforce_max_chars(
                self._fallback_random(count, max_chars),
                max_chars,
            )

        return self._enforce_max_chars(results, max_chars)

    @staticmethod
    def _enforce_max_chars(
        results: list[tuple[str, str, float]],
        max_chars: int,
    ) -> list[tuple[str, str, float]]:
        limit = max(0, int(max_chars))
        return [(text[:limit], path, score) for text, path, score in results]

    # ── Context extraction ──────────────────────────────────────

    async def _extract_context_terms(self, hint: str = "") -> str:
        """Build a context query from hint + recent stigmergy + system state."""
        terms = []

        # Always include the hint
        if hint:
            terms.append(hint)

        # Try to read recent stigmergy marks for hot topics
        try:
            from dharma_swarm.stigmergy import StigmergyStore

            store = StigmergyStore(
                marks_file=self._state_dir / "stigmergy" / "marks.jsonl",
            )
            hot = await store.high_salience(threshold=0.7, limit=5)
            for mark in hot:
                if hasattr(mark, "observation") and mark.observation:
                    terms.append(mark.observation[:100])
        except Exception:
            logger.debug("Stigmergy term extraction failed", exc_info=True)

        # Try to read recent director visions for continuity
        try:
            shared_dir = self._state_dir / "shared"
            vision_files = sorted(
                shared_dir.glob("thinkodynamic_director_vision_*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:2]
            for vf in vision_files:
                text = vf.read_text(encoding="utf-8")[:200]
                terms.append(text)
        except Exception:
            logger.debug("Vision file read failed", exc_info=True)

        if not terms:
            # Default high-value terms when no context available
            terms = ["consciousness witness swabhaav recognition autopoiesis telos"]

        return " ".join(terms)

    # ── Concept graph query ─────────────────────────────────────

    async def _query_concept_graph(
        self, context: str,
    ) -> list[dict[str, Any]]:
        """Query ConceptGraph for nodes relevant to context.

        Returns list of dicts with: name, salience, source_file, id.
        """
        candidates: list[dict[str, Any]] = []

        try:
            from dharma_swarm.semantic_gravity import ConceptGraph

            cg_path = self._state_dir / "semantic" / "concept_graph.json"
            if not cg_path.exists():
                return []

            cg = await ConceptGraph.load(cg_path)

            # Get high-salience nodes
            high_sal = cg.high_salience_nodes(threshold=0.5)
            for node in high_sal:
                candidates.append({
                    "name": node.name,
                    "salience": node.salience,
                    "source_file": getattr(node, "source_file", ""),
                    "id": node.id,
                })

            # If context hint provided, boost matching nodes
            if context:
                context_lower = context.lower()
                for candidate in candidates:
                    name_lower = candidate["name"].lower()
                    if name_lower in context_lower or context_lower in name_lower:
                        candidate["salience"] = min(candidate["salience"] * 1.5, 1.0)

        except Exception as exc:
            logger.debug("ConceptGraph query failed: %s", exc)

        # Also try to find files directly from context terms
        if context:
            for term in context.split()[:5]:
                term_clean = term.strip().lower()
                if len(term_clean) < 7:
                    continue
                # Search PSMV for files matching the term
                for seed_dir in FALLBACK_SEED_DIRS:
                    if not seed_dir.exists():
                        continue
                    for f in seed_dir.glob("*.md"):
                        if term_clean in f.name.lower():
                            candidates.append({
                                "name": f.stem,
                                "salience": 0.6,
                                "source_file": str(f),
                                "id": f"file:{f.name}",
                            })

        return candidates

    # ── File mapping ────────────────────────────────────────────

    def _map_to_files(
        self, candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Map concept candidates to readable PSMV files.

        Filters to candidates that have a resolvable source_file.
        """
        file_candidates = []
        seen_paths: set[str] = set()

        for c in candidates:
            source = c.get("source_file", "")
            if not source:
                continue

            # Resolve to absolute path
            path = self._resolve_file_path(source)
            if path and path.exists() and str(path) not in seen_paths:
                seen_paths.add(str(path))
                file_candidates.append({
                    **c,
                    "resolved_path": path,
                })

        return file_candidates

    def _resolve_file_path(self, source: str) -> Path | None:
        """Try to resolve a source_file reference to an absolute Path."""
        # Already absolute?
        p = Path(source)
        if p.is_absolute() and p.exists():
            return p

        # Relative to PSMV?
        psmv_path = PSMV_ROOT / source
        if psmv_path.exists():
            return psmv_path

        # Relative to dharma_swarm?
        ds_path = Path.home() / "dharma_swarm" / "dharma_swarm" / source
        if ds_path.exists():
            return ds_path

        # Relative to home?
        home_path = Path.home() / source
        if home_path.exists():
            return home_path

        return None

    # ── Salience-weighted sampling ──────────────────────────────

    def _salience_weighted_sample(
        self,
        candidates: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, Any]]:
        """Power-law sampling: top 20% get 80% of selections."""
        if len(candidates) <= count:
            return candidates

        # Compute weights: salience^2 gives power-law distribution
        weights = []
        for c in candidates:
            sal = max(c.get("salience", 0.1), 0.01)
            weights.append(sal ** 2)

        # Normalize
        total = sum(weights)
        if total == 0:
            return random.sample(candidates, min(count, len(candidates)))

        probs = [w / total for w in weights]

        # Weighted sampling without replacement
        selected: list[dict[str, Any]] = []
        remaining = list(range(len(candidates)))
        remaining_probs = list(probs)

        for _ in range(min(count, len(candidates))):
            if not remaining:
                break
            # Normalize remaining probs
            prob_sum = sum(remaining_probs)
            if prob_sum == 0:
                break
            normalized = [p / prob_sum for p in remaining_probs]

            r = random.random()
            cumulative = 0.0
            chosen_idx = 0
            for i, p in enumerate(normalized):
                cumulative += p
                if r <= cumulative:
                    chosen_idx = i
                    break

            selected.append(candidates[remaining[chosen_idx]])
            remaining.pop(chosen_idx)
            remaining_probs.pop(chosen_idx)

        return selected

    # ── File reading ────────────────────────────────────────────

    def _read_seeds(
        self,
        selected: list[dict[str, Any]],
        max_chars: int,
    ) -> list[tuple[str, str, float]]:
        """Read file contents for selected candidates."""
        results: list[tuple[str, str, float]] = []

        for c in selected:
            path = c.get("resolved_path")
            if not path:
                continue

            try:
                text = path.read_text(encoding="utf-8")[:max_chars]
            except Exception:
                text = f"(Could not read {path.name})"

            try:
                rel = str(path.relative_to(Path.home()))
            except ValueError:
                rel = str(path)

            score = min(max(c.get("salience", 0.5), 0.0), 1.0)
            results.append((text, rel, score))

        return results

    # ── Fallback ────────────────────────────────────────────────

    def _fallback_random(
        self,
        count: int,
        max_chars: int,
    ) -> list[tuple[str, str, float]]:
        """Random sampling from hardcoded seed dirs (existing behavior)."""
        seed_files: list[Path] = []
        for d in FALLBACK_SEED_DIRS:
            if d.exists():
                seed_files.extend(
                    p for p in d.glob("*.md")
                    if p.is_file() and p.stat().st_size > 100
                )

        if not seed_files:
            return [("(No seed files found)", "fallback", 0.1)]

        chosen = random.sample(seed_files, min(count, len(seed_files)))
        results: list[tuple[str, str, float]] = []
        for path in chosen:
            try:
                text = path.read_text(encoding="utf-8")[:max_chars]
            except Exception:
                text = f"(Could not read {path.name})"
            try:
                rel = str(path.relative_to(Path.home()))
            except ValueError:
                rel = str(path)
            results.append((text, rel, 0.3))  # Low score = random

        return results
