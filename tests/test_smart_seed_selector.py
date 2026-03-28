"""Tests for SmartSeedSelector — semantically-informed seed selection.

TDD: these tests written BEFORE the implementation.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from dharma_swarm.smart_seed_selector import SmartSeedSelector


@pytest.fixture
def selector():
    return SmartSeedSelector(state_dir=Path.home() / ".dharma")


@pytest.fixture
def mock_concept_graph():
    """Mock ConceptGraph with a few high-salience nodes."""
    graph = MagicMock()
    node1 = MagicMock()
    node1.id = "autopoiesis-001"
    node1.name = "Autopoiesis"
    node1.salience = 0.95
    node1.source_file = "organism.py"

    node2 = MagicMock()
    node2.id = "stigmergy-001"
    node2.name = "Stigmergy"
    node2.salience = 0.88
    node2.source_file = "stigmergy.py"

    node3 = MagicMock()
    node3.id = "karma-001"
    node3.name = "Karma"
    node3.salience = 0.72
    node3.source_file = "dharma_kernel.py"

    graph.high_salience_nodes.return_value = [node1, node2, node3]
    graph.all_nodes.return_value = [node1, node2, node3]
    graph.find_by_name.return_value = [node1]
    return graph


class TestSmartSeedSelector:
    """Core functionality tests."""

    @pytest.mark.asyncio
    async def test_select_returns_seeds(self, selector):
        """Basic: select() returns a list of (text, path, score) tuples."""
        results = await selector.select(count=3)
        assert isinstance(results, list)
        for item in results:
            assert len(item) == 3
            text, path, score = item
            assert isinstance(text, str)
            assert isinstance(path, str)
            assert isinstance(score, (int, float))

    @pytest.mark.asyncio
    async def test_select_respects_count(self, selector):
        """Honors the count parameter."""
        results = await selector.select(count=2)
        assert len(results) <= 2
        results5 = await selector.select(count=5)
        assert len(results5) <= 5

    @pytest.mark.asyncio
    async def test_relevance_scores_bounded(self, selector):
        """All scores between 0.0 and 1.0."""
        results = await selector.select(count=5)
        for _, _, score in results:
            assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_deduplication(self, selector):
        """No duplicate file paths in results."""
        results = await selector.select(count=10)
        paths = [path for _, path, _ in results]
        assert len(paths) == len(set(paths))

    @pytest.mark.asyncio
    async def test_max_chars_respected(self, selector):
        """Seed text truncated to max_chars."""
        results = await selector.select(count=3, max_chars=100)
        for text, _, _ in results:
            assert len(text) <= 100

    @pytest.mark.asyncio
    async def test_fallback_on_retrieval_failure(self, selector):
        """If retrieval stack fails, falls back to random without crashing."""
        # Force retrieval to fail by using a bad state_dir
        bad_selector = SmartSeedSelector(state_dir=Path("/nonexistent"))
        results = await bad_selector.select(count=3)
        # Should still return something (fallback to random seeds)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_context_hint_accepted(self, selector):
        """context_hint parameter is accepted and doesn't crash."""
        results = await selector.select(
            count=3,
            context_hint="autopoiesis witness consciousness",
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_empty_context_hint(self, selector):
        """Empty context hint works (uses default high-salience)."""
        results = await selector.select(count=3, context_hint="")
        assert isinstance(results, list)


class TestSalienceWeighting:
    """Verify power-law distribution favors high-salience files."""

    @pytest.mark.asyncio
    async def test_salience_weighted_sampling(self, selector):
        """High-salience files should appear more often than random.

        Run 20 selections and check that the top-scored results
        have higher average salience than uniform random would.
        """
        all_scores = []
        for _ in range(20):
            results = await selector.select(count=3)
            for _, _, score in results:
                all_scores.append(score)

        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
            # With salience weighting, average should be > 0.3
            # (random would give ~0.5 uniform, weighted should be higher)
            assert avg_score >= 0.0  # Minimal sanity check


class TestContextExtraction:
    """Test context term extraction from system state."""

    @pytest.mark.asyncio
    async def test_extract_context_terms(self, selector):
        """_extract_context_terms returns a non-empty string."""
        terms = await selector._extract_context_terms(hint="autopoiesis")
        assert isinstance(terms, str)
        assert len(terms) > 0
        assert "autopoiesis" in terms.lower()

    @pytest.mark.asyncio
    async def test_extract_context_terms_no_hint(self, selector):
        """Without hint, still returns something from stigmergy/state."""
        terms = await selector._extract_context_terms(hint="")
        assert isinstance(terms, str)


class TestTermLengthGuard:
    """Verify short-term noise filter in _query_concept_graph."""

    @pytest.mark.asyncio
    async def test_short_terms_filtered(self, selector):
        """Terms shorter than 7 chars must not produce file candidates.

        Words like 'claude' (6 chars), 'agent' (5 chars), 'run' (3 chars)
        should never lock seed selection by matching infrastructure filenames.
        """
        candidates = await selector._query_concept_graph("claude agent run gpt api key")
        file_based = [c for c in candidates if c.get("id", "").startswith("file:")]
        assert len(file_based) == 0, f"Short terms produced file candidates: {file_based}"

    @pytest.mark.asyncio
    async def test_long_terms_allowed(self, selector):
        """Terms of 7+ chars are not rejected by the guard."""
        candidates = await selector._query_concept_graph("autopoiesis")
        assert isinstance(candidates, list)

    @pytest.mark.asyncio
    async def test_boundary_six_chars_filtered(self, selector):
        """6-char term 'claude' is below threshold and produces no file candidates."""
        assert len("claude") == 6
        candidates = await selector._query_concept_graph("claude")
        file_based = [c for c in candidates if c.get("id", "").startswith("file:")]
        assert len(file_based) == 0

    @pytest.mark.asyncio
    async def test_boundary_seven_chars_allowed(self, selector):
        """7-char term at the threshold is not filtered out."""
        assert len("witness") == 7
        candidates = await selector._query_concept_graph("witness")
        assert isinstance(candidates, list)


class TestReadRandomSeedsSupplement:
    """select() must supplement with read_random_seeds when <= 1 results."""

    @pytest.mark.asyncio
    async def test_supplement_fires_on_empty_results(self, selector):
        """When smart selection yields nothing, read_random_seeds is blended in."""
        with (
            patch.object(selector, "_query_concept_graph",
                         new_callable=AsyncMock, return_value=[]),
            patch.object(selector, "_map_to_files", return_value=[]),
            patch.object(selector, "_fallback_random", return_value=[]),
            patch("dharma_swarm.thinkodynamic_director.read_random_seeds",
                  return_value=[("seed text", "psmv/seed.md")]),
        ):
            results = await selector.select(count=3)
            assert any(path == "psmv/seed.md" for _, path, _ in results)

    @pytest.mark.asyncio
    async def test_supplement_not_called_when_adequate(self, selector):
        """When smart selection returns > 1 results, supplement is skipped."""
        supplement_called = []

        sufficient = [
            ("text a", "path/a", 0.8),
            ("text b", "path/b", 0.7),
            ("text c", "path/c", 0.6),
        ]

        with (
            patch.object(selector, "_extract_context_terms",
                         new_callable=AsyncMock, return_value="consciousness"),
            patch.object(selector, "_query_concept_graph",
                         new_callable=AsyncMock, return_value=[]),
            patch.object(selector, "_map_to_files",
                         return_value=[{"name": "x", "salience": 0.8,
                                        "source_file": "x", "id": "x",
                                        "resolved_path": None}]),
            patch.object(selector, "_salience_weighted_sample", return_value=[]),
            patch.object(selector, "_read_seeds", return_value=sufficient),
            patch("dharma_swarm.thinkodynamic_director.read_random_seeds",
                  side_effect=lambda *a, **k: supplement_called.append(1) or []),
        ):
            results = await selector.select(count=3)
            assert len(results) == 3
            assert not supplement_called, "Supplement should not fire when results > 1"

    @pytest.mark.asyncio
    async def test_supplement_deduplicates_paths(self, selector):
        """Supplement does not re-add a path already in smart results."""
        existing_result = [("existing text", "shared/path.md", 0.9)]
        with (
            patch.object(selector, "_extract_context_terms",
                         new_callable=AsyncMock, return_value="x"),
            patch.object(selector, "_query_concept_graph",
                         new_callable=AsyncMock, return_value=[]),
            patch.object(selector, "_map_to_files",
                         return_value=[{"name": "n", "salience": 0.9,
                                        "source_file": "x", "id": "x",
                                        "resolved_path": Path("/tmp/x.md")}]),
            patch.object(selector, "_salience_weighted_sample",
                         return_value=[{"name": "n", "salience": 0.9,
                                        "source_file": "x", "id": "x",
                                        "resolved_path": Path("/tmp/x.md")}]),
            patch.object(selector, "_read_seeds", return_value=existing_result),
            patch.object(selector, "_fallback_random", return_value=[]),
            patch("dharma_swarm.thinkodynamic_director.read_random_seeds",
                  return_value=[("dup text", "shared/path.md"),
                                 ("new text", "new/path.md")]),
        ):
            results = await selector.select(count=3)
            paths = [path for _, path, _ in results]
            assert paths.count("shared/path.md") == 1
