"""Tests for Sprint 2 memory integration — end-to-end knowledge pipeline.

Tests the full flow: task context → SleepTimeAgent consolidation →
KnowledgeStore → ContextCompiler retrieval, plus backward compatibility.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.knowledge_units import (
    KnowledgeStore,
    Proposition,
    Prescription,
)
from dharma_swarm.knowledge_extractor import KnowledgeExtractor
from dharma_swarm.sleep_time_agent import SleepTimeAgent
from dharma_swarm.context_compiler import ContextCompiler, ContextSection


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def knowledge_store():
    store = KnowledgeStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def populated_store():
    """KnowledgeStore pre-populated with test knowledge."""
    store = KnowledgeStore(":memory:")
    store.store_proposition(
        Proposition(
            id="p_python",
            content="Python uses GIL for thread safety",
            concepts=["python", "GIL", "threading"],
            confidence=0.95,
        )
    )
    store.store_proposition(
        Proposition(
            id="p_rust",
            content="Rust uses ownership model for memory safety",
            concepts=["rust", "ownership", "memory"],
            confidence=0.90,
        )
    )
    store.store_proposition(
        Proposition(
            id="p_testing",
            content="Unit tests should be fast and isolated",
            concepts=["testing", "python", "best-practices"],
            confidence=0.85,
        )
    )
    store.store_prescription(
        Prescription(
            id="rx_debug",
            intent="debug a Python test failure",
            workflow=[
                "Read the traceback",
                "Check assertions",
                "Verify fixtures",
                "Run with -v flag",
            ],
            return_score=0.9,
            concepts=["debugging", "python", "testing"],
        )
    )
    store.store_prescription(
        Prescription(
            id="rx_deploy",
            intent="deploy a Python service",
            workflow=[
                "Run tests",
                "Build container",
                "Push to registry",
                "Deploy via kubectl",
            ],
            return_score=0.75,
            concepts=["deployment", "python", "docker"],
        )
    )
    yield store
    store.close()


def _make_mock_llm_client(propositions=None, prescriptions=None):
    """Create a mock LLM client for consolidation tests."""

    async def _complete(request):
        prompt = request.messages[0]["content"] if request.messages else ""
        if "atomic factual claims" in prompt and propositions is not None:
            return MagicMock(content=json.dumps(propositions))
        elif "reusable skills" in prompt and prescriptions is not None:
            return MagicMock(content=json.dumps(prescriptions))
        return MagicMock(content="[]")

    client = MagicMock()
    client.model = "mock-model"
    client.complete = _complete
    return client


# ── End-to-end consolidation tests ───────────────────────────────────


class TestConsolidationPipeline:
    """Test: task → SleepTimeAgent consolidation → KnowledgeStore."""

    @pytest.mark.asyncio
    async def test_consolidate_extracts_propositions(self, knowledge_store):
        agent = SleepTimeAgent()
        llm = _make_mock_llm_client(
            propositions=[
                {
                    "content": "Redis supports pub/sub",
                    "concepts": ["redis", "pub-sub", "messaging"],
                    "confidence": 0.9,
                }
            ],
            prescriptions=[],
        )

        result = await agent.consolidate_knowledge(
            task_context="We used Redis pub/sub for event distribution",
            task_outcome={"success": True},
            llm_client=llm,
            knowledge_store=knowledge_store,
        )

        assert result["propositions"] == 1
        assert result["prescriptions"] == 0

        # Verify stored
        props = knowledge_store.get_by_concepts(["redis"], unit_type="proposition")
        assert len(props) == 1
        assert "Redis supports pub/sub" in props[0].content

    @pytest.mark.asyncio
    async def test_consolidate_extracts_prescriptions(self, knowledge_store):
        agent = SleepTimeAgent()
        llm = _make_mock_llm_client(
            propositions=[],
            prescriptions=[
                {
                    "intent": "set up Redis pub/sub",
                    "workflow": ["Install Redis", "Configure channels", "Subscribe"],
                    "concepts": ["redis", "pub-sub"],
                    "return_score": 0.5,
                }
            ],
        )

        result = await agent.consolidate_knowledge(
            task_context="We set up Redis pub/sub successfully",
            task_outcome={"success": True},
            llm_client=llm,
            knowledge_store=knowledge_store,
        )

        assert result["prescriptions"] == 1
        prescs = knowledge_store.get_by_concepts(["redis"], unit_type="prescription")
        assert len(prescs) == 1
        # Success outcome should boost return_score to at least 0.7
        assert prescs[0].return_score >= 0.7

    @pytest.mark.asyncio
    async def test_consolidate_scores_failure(self, knowledge_store):
        agent = SleepTimeAgent()
        llm = _make_mock_llm_client(
            propositions=[],
            prescriptions=[
                {
                    "intent": "deploy with bad config",
                    "workflow": ["Deploy directly"],
                    "concepts": ["deployment"],
                    "return_score": 0.8,
                }
            ],
        )

        result = await agent.consolidate_knowledge(
            task_context="Deployment failed due to bad config",
            task_outcome={"success": False},
            llm_client=llm,
            knowledge_store=knowledge_store,
        )

        assert result["prescriptions"] == 1
        prescs = knowledge_store.get_by_concepts(["deployment"], unit_type="prescription")
        # Failure should cap return_score at 0.3
        assert prescs[0].return_score <= 0.3

    @pytest.mark.asyncio
    async def test_consolidate_disabled_by_env(self, monkeypatch, knowledge_store):
        monkeypatch.setenv("ENABLE_KNOWLEDGE_EXTRACTION", "false")
        agent = SleepTimeAgent()

        result = await agent.consolidate_knowledge(
            task_context="Some context",
            llm_client=MagicMock(),
            knowledge_store=knowledge_store,
        )

        assert result.get("skipped") is True
        assert result.get("reason") == "knowledge_extraction_disabled"

    @pytest.mark.asyncio
    async def test_consolidate_empty_context(self, knowledge_store):
        agent = SleepTimeAgent()
        result = await agent.consolidate_knowledge(
            task_context="",
            llm_client=MagicMock(),
            knowledge_store=knowledge_store,
        )
        assert result.get("skipped") is True

    @pytest.mark.asyncio
    async def test_consolidate_no_llm_produces_empty(self, knowledge_store):
        """Without an LLM, extraction returns empty arrays."""
        agent = SleepTimeAgent()
        result = await agent.consolidate_knowledge(
            task_context="Some context",
            task_outcome={"success": True},
            llm_client=None,
            knowledge_store=knowledge_store,
        )
        assert result["propositions"] == 0
        assert result["prescriptions"] == 0


# ── Context compilation with knowledge block ─────────────────────────


class TestContextCompilerKnowledge:
    """Test that ContextCompiler injects knowledge block."""

    def test_format_knowledge_block_with_propositions(self, populated_store):
        props = populated_store.get_propositions_for_context(["python"])
        prescs = populated_store.get_prescriptions_for_intent("debug", ["python"])

        block = ContextCompiler._format_knowledge_block(props, prescs)
        assert "### Facts" in block
        assert "### Applicable Skills" in block
        assert "confidence:" in block
        assert "success rate:" in block

    def test_format_knowledge_block_empty(self):
        block = ContextCompiler._format_knowledge_block([], [])
        assert block == ""

    def test_format_knowledge_block_facts_only(self, populated_store):
        props = populated_store.get_propositions_for_context(["rust"])
        block = ContextCompiler._format_knowledge_block(props, [])
        assert "### Facts" in block
        assert "### Applicable Skills" not in block

    def test_format_knowledge_block_skills_only(self, populated_store):
        prescs = populated_store.get_prescriptions_for_intent("debug", ["debugging"])
        block = ContextCompiler._format_knowledge_block([], prescs)
        assert "### Facts" not in block
        assert "### Applicable Skills" in block

    def test_extract_concepts_simple(self):
        concepts = ContextCompiler._extract_concepts_simple(
            "Debug a failing pytest test in Python"
        )
        assert len(concepts) >= 1
        assert "debug" in concepts or "failing" in concepts
        assert "pytest" in concepts
        assert "python" in concepts

    def test_extract_concepts_simple_filters_stopwords(self):
        concepts = ContextCompiler._extract_concepts_simple(
            "the quick brown fox jumps over the lazy dog"
        )
        assert "the" not in concepts
        assert "over" not in concepts
        assert "quick" in concepts

    def test_extract_concepts_simple_empty(self):
        assert ContextCompiler._extract_concepts_simple("") == []

    def test_extract_concepts_simple_caps_at_7(self):
        long_text = " ".join(f"concept{i}" for i in range(20))
        concepts = ContextCompiler._extract_concepts_simple(long_text)
        assert len(concepts) <= 7

    def test_retrieve_knowledge_block(self, populated_store):
        """Test _retrieve_knowledge_block returns formatted content."""
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=populated_store,
        )

        block = compiler._retrieve_knowledge_block("debug a Python test")
        assert block  # Non-empty
        assert "### Facts" in block or "### Applicable Skills" in block

    def test_retrieve_knowledge_block_empty_store(self):
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        empty_store = KnowledgeStore(":memory:")
        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=empty_store,
        )

        block = compiler._retrieve_knowledge_block("debug a Python test")
        assert block == ""
        empty_store.close()

    def test_retrieve_knowledge_block_no_store(self):
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=None,
        )

        block = compiler._retrieve_knowledge_block("some task")
        assert block == ""


# ── Backward compatibility tests ─────────────────────────────────────


class TestBackwardCompatibility:
    """Ensure existing code paths still work without knowledge store."""

    def test_context_compiler_works_without_knowledge_store(self):
        """ContextCompiler should work normally when knowledge_store=None."""
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=None,
        )
        # No exception
        assert compiler.knowledge_store is None

    def test_sleep_time_agent_tick_unchanged(self):
        """Existing tick() method should work without knowledge-related changes."""
        agent = SleepTimeAgent(tick_interval=1)

        # Mock organism
        organism = MagicMock()
        organism.memory = None
        organism.palace = None
        organism._pulses = []

        stats = agent.tick(1, organism)
        assert "phases" in stats
        assert stats["cycle"] == 1

    def test_sleep_time_agent_learned_context(self):
        agent = SleepTimeAgent()
        assert agent.learned_context() == ""

    def test_context_section_weights_sum(self):
        """Section weights should sum to approximately 1.0."""
        total = sum(ContextCompiler._SECTION_WEIGHTS.values())
        assert 0.95 <= total <= 1.05

    def test_build_sections_accepts_knowledge_block(self):
        """_build_sections should work with or without knowledge_block."""
        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
        )

        # Without knowledge block
        sections = compiler._build_sections(
            session=None,
            task_id="t1",
            run_id="r1",
            operator_intent="test",
            task_description="testing",
            policy_constraints=[],
            provider_request=None,
            always_on="",
            recent_events=[],
            recall_hits=[],
            palace_hits=[],
            semantic_hits=[],
            knowledge_block="",
            facts=[],
            artifacts=[],
            workspace_root=None,
            active_paths=[],
            runs=[],
            leases=[],
        )
        assert isinstance(sections, list)

        # With knowledge block
        sections_with_kb = compiler._build_sections(
            session=None,
            task_id="t1",
            run_id="r1",
            operator_intent="test",
            task_description="testing",
            policy_constraints=[],
            provider_request=None,
            always_on="",
            recent_events=[],
            recall_hits=[],
            palace_hits=[],
            semantic_hits=[],
            knowledge_block="### Facts\n- Test fact [confidence: 0.9]",
            facts=[],
            artifacts=[],
            workspace_root=None,
            active_paths=[],
            runs=[],
            leases=[],
        )
        kb_sections = [s for s in sections_with_kb if s.name == "Relevant Knowledge"]
        assert len(kb_sections) == 1
        assert "Test fact" in kb_sections[0].content


# ── Knowledge block token budget tests ───────────────────────────────


class TestKnowledgeBlockBudget:
    def test_token_budget_respected(self, populated_store, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_MAX_TOKENS", "50")

        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=populated_store,
        )

        block = compiler._retrieve_knowledge_block("python threading GIL")
        # With only 50 tokens (~200 chars), the block should be limited
        if block:
            # The block exists but should be reasonably sized
            assert len(block) < 2000  # Sanity check

    def test_default_token_budget(self, populated_store, monkeypatch):
        monkeypatch.delenv("KNOWLEDGE_MAX_TOKENS", raising=False)

        from dharma_swarm.memory_lattice import MemoryLattice
        from dharma_swarm.runtime_state import RuntimeStateStore

        compiler = ContextCompiler(
            runtime_state=MagicMock(spec=RuntimeStateStore),
            memory_lattice=MagicMock(spec=MemoryLattice),
            knowledge_store=populated_store,
        )

        block = compiler._retrieve_knowledge_block("python testing")
        # Default 500 tokens should allow reasonable content
        assert block  # Non-empty with our populated store


# ── Graph store knowledge node tests ─────────────────────────────────


class TestGraphStoreKnowledgeNodes:
    @pytest.fixture
    def graph_store(self, tmp_path):
        from dharma_swarm.graph_store import SQLiteGraphStore

        db = tmp_path / "test_graphs.db"
        with SQLiteGraphStore(db) as s:
            yield s

    def test_add_proposition_node(self, graph_store):
        prop = Proposition(
            id="prop-1",
            content="Python uses GIL",
            concepts=["python", "GIL"],
            confidence=0.95,
            provenance_event_id="evt-1",
        )
        graph_store.add_knowledge_node(prop)

        node = graph_store.get_node("semantic", "prop::prop-1")
        assert node is not None
        assert node["kind"] == "fact"
        assert node["data"]["content"] == "Python uses GIL"

        # Concept edges should exist
        edges = graph_store.get_edges("semantic", "prop::prop-1", direction="out")
        concept_edges = [e for e in edges if e["kind"] == "tagged_with"]
        assert len(concept_edges) == 2

    def test_add_prescription_node(self, graph_store):
        presc = Prescription(
            id="presc-1",
            intent="debug tests",
            workflow=["read traceback", "check assertions"],
            return_score=0.85,
            concepts=["debugging", "testing"],
        )
        graph_store.add_knowledge_node(presc)

        node = graph_store.get_node("semantic", "presc::presc-1")
        assert node is not None
        assert node["kind"] == "skill"
        assert node["data"]["intent"] == "debug tests"

    def test_query_by_concept(self, graph_store):
        prop = Proposition(
            id="prop-q1",
            content="Python fact",
            concepts=["python"],
        )
        presc = Prescription(
            id="presc-q1",
            intent="Python skill",
            concepts=["python"],
        )
        graph_store.add_knowledge_node(prop)
        graph_store.add_knowledge_node(presc)

        results = graph_store.query_by_concept(["python"])
        ids = {r["id"] for r in results}
        assert "prop::prop-q1" in ids
        assert "presc::presc-q1" in ids

    def test_query_by_concept_type_filter(self, graph_store):
        prop = Proposition(id="prop-f1", content="fact", concepts=["topic"])
        presc = Prescription(id="presc-f1", intent="skill", concepts=["topic"])
        graph_store.add_knowledge_node(prop)
        graph_store.add_knowledge_node(presc)

        props_only = graph_store.query_by_concept(["topic"], node_type="proposition")
        assert all(r["id"].startswith("prop::") for r in props_only)

        prescs_only = graph_store.query_by_concept(["topic"], node_type="prescription")
        assert all(r["id"].startswith("presc::") for r in prescs_only)

    def test_query_by_concept_empty(self, graph_store):
        results = graph_store.query_by_concept([])
        assert results == []

    def test_concept_nodes_created(self, graph_store):
        prop = Proposition(
            id="prop-c1",
            content="fact",
            concepts=["unique_concept"],
        )
        graph_store.add_knowledge_node(prop)

        concept_node = graph_store.get_node("semantic", "concept::unique_concept")
        assert concept_node is not None
        assert concept_node["kind"] == "concept"
        assert concept_node["name"] == "unique_concept"

    def test_provenance_edge_created(self, graph_store):
        prop = Proposition(
            id="prop-prov",
            content="fact with provenance",
            concepts=["topic"],
            provenance_event_id="runtime-event-123",
        )
        graph_store.add_knowledge_node(prop)

        edges = graph_store.get_edges("semantic", "prop::prop-prov", direction="out")
        prov_edges = [e for e in edges if e["kind"] == "sourced_from"]
        assert len(prov_edges) == 1
        assert prov_edges[0]["target_id"] == "event::runtime-event-123"


# ── Full pipeline integration test ───────────────────────────────────


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_consolidate_then_retrieve(self):
        """End-to-end: consolidate knowledge, then retrieve it in context."""
        store = KnowledgeStore(":memory:")

        # Step 1: Consolidate
        agent = SleepTimeAgent()
        llm = _make_mock_llm_client(
            propositions=[
                {
                    "content": "Redis pub/sub supports pattern subscriptions",
                    "concepts": ["redis", "pub-sub", "patterns"],
                    "confidence": 0.88,
                }
            ],
            prescriptions=[
                {
                    "intent": "set up Redis pub/sub with patterns",
                    "workflow": ["Install Redis", "Configure pattern channels"],
                    "concepts": ["redis", "pub-sub"],
                    "return_score": 0.75,
                }
            ],
        )

        result = await agent.consolidate_knowledge(
            task_context="Set up Redis pub/sub with pattern matching",
            task_outcome={"success": True},
            llm_client=llm,
            knowledge_store=store,
        )
        assert result["propositions"] == 1
        assert result["prescriptions"] == 1

        # Step 2: Retrieve via ContextCompiler
        block = ContextCompiler._format_knowledge_block(
            store.get_propositions_for_context(["redis", "pub-sub"]),
            store.get_prescriptions_for_intent("redis pub/sub", ["redis"]),
        )
        assert "### Facts" in block
        assert "Redis pub/sub" in block
        assert "### Applicable Skills" in block
        assert "success rate:" in block

        store.close()
