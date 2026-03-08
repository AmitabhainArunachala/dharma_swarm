"""Tests for Context Search Engine — lazy context loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.context_search import ContextResult, ContextSearchEngine


class TestContextSearchEngine:
    """Tests for the keyword-indexed context search."""

    @pytest.fixture
    def search_dir(self, tmp_path: Path) -> tuple[Path, dict]:
        """Create a mock ecosystem with searchable files."""
        # Create test files
        (tmp_path / "rv_paper.md").write_text(
            "# R_V Paper\nParticipation ratio measurements.\nSVD contraction."
        )
        (tmp_path / "metrics.py").write_text(
            "# Behavioral metrics\ndef analyze(text): pass\nswabhaav_ratio = 0.6"
        )
        (tmp_path / "bridge.py").write_text(
            "# Research bridge\nCorrelation between R_V and behavior.\nPearson r."
        )
        (tmp_path / "readme.txt").write_text(
            "# Setup Guide\nInstall dependencies with pip."
        )

        paths = {
            str(tmp_path / "rv_paper.md"): {"category": "research"},
            str(tmp_path / "metrics.py"): {"category": "engineering"},
            str(tmp_path / "bridge.py"): {"category": "research"},
            str(tmp_path / "readme.txt"): {"category": "docs"},
        }
        return tmp_path, paths

    def test_build_index(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        count = engine.build_index()
        assert count == 4

    def test_search_by_keyword(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("R_V participation ratio SVD")
        assert len(results) > 0
        # rv_paper.md should be most relevant
        assert "rv_paper" in results[0].path

    def test_search_by_category(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("correlation research", category="research")
        for r in results:
            assert r.category == "research"

    def test_search_returns_snippets(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("metrics behavioral")
        for r in results:
            assert r.snippet != ""

    def test_search_no_results(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("quantum entanglement black holes")
        assert len(results) == 0

    def test_max_results_limit(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("paper metrics bridge", max_results=2)
        assert len(results) <= 2

    def test_get_context_for_task(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        context = engine.get_context_for_task(
            "analyze R_V correlation data",
            budget=5000,
        )
        assert "Task-Relevant Context" in context
        assert len(context) > 0
        assert len(context) <= 6000  # budget + headers

    def test_get_context_empty_query(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        context = engine.get_context_for_task("")
        assert context == ""

    def test_context_budget_respected(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        context = engine.get_context_for_task("everything", budget=100)
        # Should truncate to near budget
        assert len(context) < 500  # some overhead for headers

    def test_nonexistent_paths_skipped(self, tmp_path: Path):
        paths = {
            "/nonexistent/file.md": {"category": "ghost"},
        }
        engine = ContextSearchEngine(ecosystem_paths=paths)
        count = engine.build_index()
        assert count == 0

    def test_relevance_scoring(self, search_dir):
        _, paths = search_dir
        engine = ContextSearchEngine(ecosystem_paths=paths)
        engine.build_index()
        results = engine.search("R_V contraction SVD participation")
        if results:
            # Results should be sorted by relevance (descending)
            for i in range(len(results) - 1):
                assert results[i].relevance >= results[i + 1].relevance
