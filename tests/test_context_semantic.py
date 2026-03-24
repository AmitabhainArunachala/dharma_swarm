"""Test Phase 7b: Semantic Context section in ContextCompiler.

Verifies:
1. _SECTION_WEIGHTS includes "Semantic Context" at ~5%
2. _query_semantic_graph returns structured concept data
3. Semantic Context section appears in compiled output
4. GraphStore failure does not break compilation
5. Empty query produces no semantic hits
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dharma_swarm.context_compiler import ContextCompiler, ContextSection


# ---------------------------------------------------------------------------
# Test 1: Section weights include Semantic Context
# ---------------------------------------------------------------------------


def test_section_weights_include_semantic_context():
    weights = ContextCompiler._SECTION_WEIGHTS
    assert "Semantic Context" in weights
    assert 0.04 <= weights["Semantic Context"] <= 0.06

    # Weights should still sum to ~1.0
    total = sum(weights.values())
    assert 0.99 <= total <= 1.01, f"Weights sum to {total}, expected ~1.0"


# ---------------------------------------------------------------------------
# Test 2: _query_semantic_graph with mock graph store
# ---------------------------------------------------------------------------


def test_query_semantic_graph_returns_concepts():
    mock_store = MagicMock()

    # search_nodes returns a concept
    mock_store.search_nodes.return_value = [
        {
            "id": "c_auto",
            "name": "autopoiesis",
            "data": json.dumps({
                "description": "Self-creating and self-maintaining systems",
                "domain": "systems_theory",
            }),
        }
    ]

    # get_edges returns a related concept edge
    mock_store.get_edges.return_value = [
        {"source_id": "c_auto", "target_id": "c_homeo", "kind": "related_to"}
    ]
    mock_store.get_node.return_value = {"id": "c_homeo", "name": "homeostasis"}

    # get_bridges returns a code location
    mock_store.get_bridges.return_value = [
        {"source_id": "dharma_swarm/organism.py::42", "source_graph": "code"}
    ]

    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.graph_store = mock_store

    results = compiler._query_semantic_graph("autopoiesis", limit=5)

    assert len(results) == 1
    hit = results[0]
    assert hit["name"] == "autopoiesis"
    assert "Self-creating" in hit["description"]
    assert "homeostasis" in hit["related"]
    assert "dharma_swarm/organism.py" in hit["code_locations"]


def test_query_semantic_graph_empty_query():
    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.graph_store = MagicMock()

    results = compiler._query_semantic_graph("", limit=5)
    assert results == []


def test_query_semantic_graph_no_store():
    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.graph_store = None

    results = compiler._query_semantic_graph("test", limit=5)
    assert results == []


def test_query_semantic_graph_handles_exception():
    mock_store = MagicMock()
    mock_store.search_nodes.side_effect = RuntimeError("DB locked")

    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.graph_store = mock_store

    # Should return empty, not raise
    results = compiler._query_semantic_graph("test", limit=5)
    assert results == []


# ---------------------------------------------------------------------------
# Test 3: Semantic Context section appears in _build_sections
# ---------------------------------------------------------------------------


def test_semantic_hits_produce_section():
    """When semantic_hits are provided, _build_sections includes the section."""
    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.provider_policy = MagicMock()

    semantic_hits = [
        {
            "name": "autopoiesis",
            "description": "Self-creating systems",
            "related": ["homeostasis", "allopoiesis"],
            "code_locations": ["organism.py"],
        }
    ]

    sections = compiler._build_sections(
        session=None,
        task_id="",
        run_id="",
        operator_intent="",
        task_description="",
        policy_constraints=[],
        provider_request=None,
        always_on="",
        recent_events=[],
        recall_hits=[],
        palace_hits=[],
        semantic_hits=semantic_hits,
        facts=[],
        artifacts=[],
        workspace_root=None,
        active_paths=[],
        runs=[],
        leases=[],
    )

    sem_sections = [s for s in sections if s.name == "Semantic Context"]
    assert len(sem_sections) == 1
    assert "autopoiesis" in sem_sections[0].content
    assert "homeostasis" in sem_sections[0].content
    assert "organism.py" in sem_sections[0].content


def test_empty_semantic_hits_no_section():
    """When semantic_hits is empty, no Semantic Context section appears."""
    compiler = ContextCompiler.__new__(ContextCompiler)
    compiler.provider_policy = MagicMock()

    sections = compiler._build_sections(
        session=None,
        task_id="",
        run_id="",
        operator_intent="",
        task_description="",
        policy_constraints=[],
        provider_request=None,
        always_on="",
        recent_events=[],
        recall_hits=[],
        palace_hits=[],
        semantic_hits=[],
        facts=[],
        artifacts=[],
        workspace_root=None,
        active_paths=[],
        runs=[],
        leases=[],
    )

    sem_sections = [s for s in sections if s.name == "Semantic Context"]
    assert len(sem_sections) == 0
