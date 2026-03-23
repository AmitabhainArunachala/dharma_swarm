"""Tests for Phase 7b: Semantic Graph integration with ContextCompiler."""

from __future__ import annotations

import pytest
import pytest_asyncio

from dharma_swarm.context_compiler import ContextCompiler, ContextSection
from dharma_swarm.graph_store import SQLiteGraphStore


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def graph_store(tmp_path):
    """Fresh SQLiteGraphStore with some seeded concept data."""
    db = tmp_path / "test_graphs.db"
    store = SQLiteGraphStore(db)

    # Seed concepts
    store.upsert_node("semantic", {
        "id": "c-autopoiesis",
        "kind": "concept",
        "name": "autopoiesis",
        "data": {
            "definition": "Self-producing system that maintains its own organization",
            "domain": "biology",
        },
    })
    store.upsert_node("semantic", {
        "id": "c-vsm",
        "kind": "concept",
        "name": "viable system model",
        "data": {
            "definition": "Stafford Beer's model for viable organizational structure",
            "domain": "cybernetics",
        },
    })
    store.upsert_edge("semantic", {
        "source_id": "c-autopoiesis",
        "target_id": "c-vsm",
        "kind": "related_to",
    })

    # Seed a code file node and bridge
    store.upsert_node("code", {
        "id": "file::dharma_swarm/organism.py",
        "kind": "file",
        "name": "dharma_swarm/organism.py",
    })
    store.upsert_bridge({
        "id": "bridge-organism-autopoiesis",
        "source_graph": "code",
        "source_id": "file::dharma_swarm/organism.py",
        "target_graph": "semantic",
        "target_id": "c-autopoiesis",
        "kind": "references_concept",
        "description": "organism.py references autopoiesis",
        "confidence": 0.9,
    })

    yield store
    store.close()


@pytest.fixture
def mock_runtime_state(tmp_path):
    """Minimal mock RuntimeStateStore."""
    class MockRuntimeState:
        async def init_db(self): pass
        async def get_session(self, sid): return None
        async def list_delegation_runs(self, **kw): return []
        async def list_memory_facts(self, **kw): return []
        async def list_artifacts(self, **kw): return []
        async def list_workspace_leases(self, **kw): return []
        async def record_context_bundle(self, b): return b
        async def upsert_session(self, s): return s
        def new_bundle_id(self): return "test-bundle-001"
    return MockRuntimeState()


@pytest.fixture
def mock_memory_lattice():
    """Minimal mock MemoryLattice."""
    class MockLattice:
        async def init_db(self): pass
        async def replay_session(self, sid, limit=6): return []
        async def recall(self, query, limit=6, session_id=None, task_id=None): return []
        async def always_on_context(self, max_chars=1000): return ""
    return MockLattice()


# ── Semantic search tests ────────────────────────────────────────────────


class TestSemanticGraphSearch:
    def test_search_finds_concepts(self, graph_store):
        """_search_semantic_graph should find seeded concepts."""
        compiler = ContextCompiler(
            runtime_state=None,
            memory_lattice=None,
            graph_store=graph_store,
        )
        results = compiler._search_semantic_graph("autopoiesis")
        assert len(results) >= 1
        assert results[0]["name"] == "autopoiesis"
        assert "Self-producing" in results[0]["definition"]

    def test_search_includes_related_concepts(self, graph_store):
        """Search results should include related concept names."""
        compiler = ContextCompiler(
            runtime_state=None,
            memory_lattice=None,
            graph_store=graph_store,
        )
        results = compiler._search_semantic_graph("autopoiesis")
        assert len(results) >= 1
        # autopoiesis → vsm edge exists
        assert "viable system model" in results[0]["related"]

    def test_search_includes_code_locations(self, graph_store):
        """Search results should include code file paths from bridges."""
        compiler = ContextCompiler(
            runtime_state=None,
            memory_lattice=None,
            graph_store=graph_store,
        )
        results = compiler._search_semantic_graph("autopoiesis")
        assert len(results) >= 1
        assert "dharma_swarm/organism.py" in results[0]["code_locations"]

    def test_search_returns_empty_without_graph_store(self):
        """Search with no graph_store returns empty list."""
        compiler = ContextCompiler(
            runtime_state=None,
            memory_lattice=None,
            graph_store=None,
        )
        results = compiler._search_semantic_graph("anything")
        assert results == []

    def test_search_handles_no_match(self, graph_store):
        """Search for non-existent concept returns empty."""
        compiler = ContextCompiler(
            runtime_state=None,
            memory_lattice=None,
            graph_store=graph_store,
        )
        results = compiler._search_semantic_graph("xyznonexistent99")
        assert results == []


# ── Context compilation with semantic section ─────────────────────────────


class TestCompileBundleWithSemantic:
    @pytest.mark.asyncio
    async def test_compile_bundle_includes_semantic_section(
        self, mock_runtime_state, mock_memory_lattice, graph_store,
    ):
        """compile_bundle should include a Semantic Context section."""
        compiler = ContextCompiler(
            runtime_state=mock_runtime_state,
            memory_lattice=mock_memory_lattice,
            graph_store=graph_store,
        )
        bundle = await compiler.compile_bundle(
            session_id="test-session",
            query="autopoiesis",
            token_budget=2000,
        )
        assert "Semantic Context" in bundle.rendered_text

    @pytest.mark.asyncio
    async def test_compile_bundle_no_semantic_without_graph(
        self, mock_runtime_state, mock_memory_lattice,
    ):
        """compile_bundle without graph_store should have no semantic section."""
        compiler = ContextCompiler(
            runtime_state=mock_runtime_state,
            memory_lattice=mock_memory_lattice,
            graph_store=None,
        )
        bundle = await compiler.compile_bundle(
            session_id="test-session",
            task_description="General task",
            token_budget=2000,
        )
        assert "Semantic Context" not in bundle.rendered_text

    @pytest.mark.asyncio
    async def test_semantic_section_weight(self):
        """Semantic Context should have 5% weight in section weights."""
        assert ContextCompiler._SECTION_WEIGHTS["Semantic Context"] == 0.05
