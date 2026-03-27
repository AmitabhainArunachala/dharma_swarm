"""Tests for dharma_swarm.knowledge_units — Proposition, Prescription, KnowledgeStore."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from dharma_swarm.knowledge_units import (
    KnowledgeStore,
    Proposition,
    Prescription,
    get_default_knowledge_db_path,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_prop(**overrides) -> Proposition:
    defaults = {
        "id": str(uuid.uuid4()),
        "content": "GPT-4 achieves 86.4% on MMLU",
        "concepts": ["GPT-4", "MMLU", "benchmark"],
        "confidence": 0.92,
    }
    defaults.update(overrides)
    return Proposition(**defaults)


def _make_presc(**overrides) -> Prescription:
    defaults = {
        "id": str(uuid.uuid4()),
        "intent": "debug a failing pytest test",
        "workflow": [
            "Read the error traceback",
            "Locate the failing assertion",
            "Check the test fixture setup",
        ],
        "return_score": 0.85,
        "concepts": ["debugging", "pytest", "testing"],
    }
    defaults.update(overrides)
    return Prescription(**defaults)


# ── Proposition dataclass tests ──────────────────────────────────────


class TestProposition:
    def test_creation_defaults(self):
        p = Proposition()
        assert p.id
        assert p.content == ""
        assert p.concepts == []
        assert p.confidence == 1.0
        assert p.access_count == 0
        assert p.superseded_by is None

    def test_creation_with_values(self):
        p = _make_prop()
        assert p.content == "GPT-4 achieves 86.4% on MMLU"
        assert "GPT-4" in p.concepts
        assert p.confidence == 0.92

    def test_to_dict(self):
        p = _make_prop()
        d = p.to_dict()
        assert d["content"] == p.content
        assert d["concepts"] == p.concepts
        assert d["confidence"] == p.confidence
        assert isinstance(d["created_at"], str)
        assert isinstance(d["last_accessed"], str)

    def test_from_dict(self):
        p = _make_prop()
        d = p.to_dict()
        p2 = Proposition.from_dict(d)
        assert p2.id == p.id
        assert p2.content == p.content
        assert p2.concepts == p.concepts
        assert p2.confidence == p.confidence

    def test_from_dict_missing_fields(self):
        p = Proposition.from_dict({"content": "hello"})
        assert p.content == "hello"
        assert p.id  # auto-generated
        assert p.concepts == []

    def test_from_dict_empty(self):
        p = Proposition.from_dict({})
        assert p.content == ""
        assert p.id  # auto-generated

    def test_roundtrip_serialization(self):
        p = _make_prop(
            provenance_event_id="event-123",
            provenance_context="some context",
            superseded_by="other-id",
        )
        d = p.to_dict()
        p2 = Proposition.from_dict(d)
        assert p2.provenance_event_id == "event-123"
        assert p2.provenance_context == "some context"
        assert p2.superseded_by == "other-id"


# ── Prescription dataclass tests ─────────────────────────────────────


class TestPrescription:
    def test_creation_defaults(self):
        p = Prescription()
        assert p.id
        assert p.intent == ""
        assert p.workflow == []
        assert p.return_score == 0.0
        assert p.success_count == 0
        assert p.attempt_count == 0

    def test_creation_with_values(self):
        p = _make_presc()
        assert p.intent == "debug a failing pytest test"
        assert len(p.workflow) == 3
        assert p.return_score == 0.85

    def test_to_dict(self):
        p = _make_presc()
        d = p.to_dict()
        assert d["intent"] == p.intent
        assert d["workflow"] == p.workflow
        assert d["return_score"] == p.return_score

    def test_from_dict(self):
        p = _make_presc()
        d = p.to_dict()
        p2 = Prescription.from_dict(d)
        assert p2.id == p.id
        assert p2.intent == p.intent
        assert p2.workflow == p.workflow
        assert p2.return_score == p.return_score

    def test_roundtrip_serialization(self):
        p = _make_presc(
            success_count=5,
            attempt_count=7,
            provenance_event_id="evt-456",
        )
        d = p.to_dict()
        p2 = Prescription.from_dict(d)
        assert p2.success_count == 5
        assert p2.attempt_count == 7
        assert p2.provenance_event_id == "evt-456"


# ── KnowledgeStore CRUD tests ────────────────────────────────────────


class TestKnowledgeStoreCRUD:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        yield s
        s.close()

    def test_store_and_retrieve_proposition(self, store):
        prop = _make_prop()
        pid = store.store_proposition(prop)
        assert pid == prop.id

        # Retrieve by concept
        results = store.get_by_concepts(["MMLU"], unit_type="proposition")
        assert len(results) >= 1
        assert any(r.id == prop.id for r in results)

    def test_store_and_retrieve_prescription(self, store):
        presc = _make_presc()
        pid = store.store_prescription(presc)
        assert pid == presc.id

        results = store.get_by_concepts(["pytest"], unit_type="prescription")
        assert len(results) >= 1
        assert any(r.id == presc.id for r in results)

    def test_store_multiple_propositions(self, store):
        for i in range(5):
            store.store_proposition(
                _make_prop(
                    content=f"Fact number {i}",
                    concepts=["shared_concept", f"unique_{i}"],
                )
            )
        results = store.get_by_concepts(["shared_concept"], unit_type="proposition")
        assert len(results) == 5

    def test_upsert_overwrites(self, store):
        prop = _make_prop(content="v1")
        store.store_proposition(prop)

        prop.content = "v2"
        store.store_proposition(prop)

        results = store.get_by_concepts(["MMLU"])
        assert len(results) == 1
        assert results[0].content == "v2"


# ── Concept-centric retrieval tests ──────────────────────────────────


class TestConceptRetrieval:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        # Pre-populate with knowledge
        s.store_proposition(
            _make_prop(
                id="p1",
                content="Python uses indentation for blocks",
                concepts=["python", "syntax", "indentation"],
            )
        )
        s.store_proposition(
            _make_prop(
                id="p2",
                content="Python 3.12 adds PEP 695 type syntax",
                concepts=["python", "type-hints", "PEP-695"],
            )
        )
        s.store_proposition(
            _make_prop(
                id="p3",
                content="Rust uses ownership for memory safety",
                concepts=["rust", "memory-safety", "ownership"],
            )
        )
        s.store_prescription(
            _make_presc(
                id="rx1",
                intent="write a Python unit test",
                concepts=["python", "testing", "pytest"],
                return_score=0.9,
            )
        )
        yield s
        s.close()

    def test_exact_concept_match(self, store):
        results = store.get_by_concepts(["python"])
        ids = {r.id for r in results}
        assert "p1" in ids
        assert "p2" in ids
        assert "rx1" in ids
        assert "p3" not in ids

    def test_partial_concept_match(self, store):
        results = store.get_by_concepts(["python", "testing"])
        # rx1 matches both concepts; p1 and p2 match only python
        assert len(results) >= 1
        # rx1 should be highest ranked (matches 2 concepts)
        assert results[0].id == "rx1"

    def test_empty_concepts_returns_nothing(self, store):
        assert store.get_by_concepts([]) == []

    def test_no_match_returns_empty(self, store):
        results = store.get_by_concepts(["javascript"])
        assert results == []

    def test_unit_type_filter(self, store):
        props_only = store.get_by_concepts(["python"], unit_type="proposition")
        assert all(isinstance(r, Proposition) for r in props_only)

        prescs_only = store.get_by_concepts(["python"], unit_type="prescription")
        assert all(isinstance(r, Prescription) for r in prescs_only)

    def test_both_type_filter(self, store):
        results = store.get_by_concepts(["python"], unit_type="both")
        types = {type(r).__name__ for r in results}
        assert "Proposition" in types
        assert "Prescription" in types

    def test_limit_respected(self, store):
        results = store.get_by_concepts(["python"], limit=1)
        assert len(results) <= 1

    def test_case_insensitive_concepts(self, store):
        results = store.get_by_concepts(["PYTHON"])
        assert len(results) >= 1

    def test_concept_overlap_scoring(self, store):
        # Add a proposition matching 3 target concepts
        store.store_proposition(
            _make_prop(
                id="p_multi",
                content="multi-concept fact",
                concepts=["python", "testing", "syntax"],
            )
        )
        results = store.get_by_concepts(["python", "testing", "syntax"])
        # p_multi should rank high due to 3-concept overlap
        assert results[0].id == "p_multi"


# ── Token budget tests ───────────────────────────────────────────────


class TestTokenBudget:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        for i in range(20):
            s.store_proposition(
                _make_prop(
                    id=f"long_{i}",
                    content=f"This is fact number {i} with some long content that takes up tokens. " * 5,
                    concepts=["shared"],
                    confidence=0.9,
                )
            )
        yield s
        s.close()

    def test_token_budget_limits_results(self, store):
        # With a very small token budget, fewer propositions should be returned
        results_small = store.get_propositions_for_context(["shared"], max_tokens=50)
        results_large = store.get_propositions_for_context(["shared"], max_tokens=5000)
        assert len(results_small) < len(results_large)

    def test_zero_budget_returns_nothing(self, store):
        results = store.get_propositions_for_context(["shared"], max_tokens=0)
        assert results == []


# ── Proposition supersession tests ───────────────────────────────────


class TestSupersession:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        yield s
        s.close()

    def test_supersede_proposition(self, store):
        old = _make_prop(id="old1", content="Earth has 8 planets")
        store.store_proposition(old)

        new = _make_prop(id="new1", content="Solar system has 8 planets")
        store.supersede_proposition("old1", new)

        # Old should be superseded
        results = store.get_by_concepts(["MMLU"])
        superseded = [r for r in results if r.id == "old1"]
        assert len(superseded) == 0  # Superseded items are filtered out

    def test_new_proposition_retrievable(self, store):
        old = _make_prop(id="old2", content="Old fact", concepts=["topic"])
        store.store_proposition(old)

        new = _make_prop(id="new2", content="New fact", concepts=["topic"])
        store.supersede_proposition("old2", new)

        results = store.get_by_concepts(["topic"])
        ids = {r.id for r in results}
        assert "new2" in ids
        assert "old2" not in ids


# ── Return score update tests ────────────────────────────────────────


class TestReturnScore:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        yield s
        s.close()

    def test_update_return_score_success(self, store):
        presc = _make_presc(id="rx_score", return_score=0.0)
        store.store_prescription(presc)

        store.update_return_score("rx_score", success=True)
        results = store.get_by_concepts(["debugging"], unit_type="prescription")
        rx = next(r for r in results if r.id == "rx_score")
        assert rx.return_score == 1.0  # 1 success / 1 attempt
        assert rx.success_count == 1
        assert rx.attempt_count == 1

    def test_update_return_score_failure(self, store):
        presc = _make_presc(id="rx_fail", return_score=1.0)
        store.store_prescription(presc)

        store.update_return_score("rx_fail", success=False)
        results = store.get_by_concepts(["debugging"], unit_type="prescription")
        rx = next(r for r in results if r.id == "rx_fail")
        assert rx.return_score == 0.0  # 0 success / 1 attempt
        assert rx.attempt_count == 1

    def test_update_return_score_mixed(self, store):
        presc = _make_presc(id="rx_mix")
        store.store_prescription(presc)

        store.update_return_score("rx_mix", success=True)
        store.update_return_score("rx_mix", success=True)
        store.update_return_score("rx_mix", success=False)

        results = store.get_by_concepts(["debugging"], unit_type="prescription")
        rx = next(r for r in results if r.id == "rx_mix")
        assert abs(rx.return_score - 2.0 / 3.0) < 0.01  # 2/3

    def test_update_nonexistent_is_noop(self, store):
        # Should not raise
        store.update_return_score("nonexistent_id", success=True)


# ── Prescriptions for intent tests ───────────────────────────────────


class TestPrescriptionsForIntent:
    @pytest.fixture
    def store(self):
        s = KnowledgeStore(":memory:")
        s.store_prescription(
            _make_presc(
                id="rx_debug",
                intent="debug a failing test",
                concepts=["debugging", "testing"],
                return_score=0.9,
            )
        )
        s.store_prescription(
            _make_presc(
                id="rx_deploy",
                intent="deploy a production service",
                concepts=["deployment", "production"],
                return_score=0.7,
            )
        )
        s.store_prescription(
            _make_presc(
                id="rx_test",
                intent="write integration tests",
                concepts=["testing", "integration"],
                return_score=0.6,
            )
        )
        yield s
        s.close()

    def test_intent_matching(self, store):
        results = store.get_prescriptions_for_intent(
            "debug a failing test case", ["debugging", "testing"]
        )
        assert len(results) >= 1
        # rx_debug should be top match (intent overlap + concept match)
        assert results[0].id == "rx_debug"

    def test_no_matching_intent(self, store):
        results = store.get_prescriptions_for_intent(
            "cook a recipe", ["cooking"]
        )
        assert results == []


# ── Context manager tests ────────────────────────────────────────────


class TestContextManager:
    def test_context_manager(self):
        with KnowledgeStore(":memory:") as store:
            store.store_proposition(_make_prop())
            results = store.get_by_concepts(["MMLU"])
            assert len(results) >= 1

    def test_file_backed_store(self, tmp_path):
        db_path = str(tmp_path / "knowledge.db")
        with KnowledgeStore(db_path) as store:
            store.store_proposition(_make_prop(id="persist_test"))

        # Reopen and verify persistence
        with KnowledgeStore(db_path) as store:
            results = store.get_by_concepts(["MMLU"])
            assert any(r.id == "persist_test" for r in results)


# ── Default DB path helper tests ─────────────────────────────────────


class TestDefaultDbPath:
    def test_returns_string(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DHARMA_STATE_DIR", str(tmp_path))
        monkeypatch.delenv("KNOWLEDGE_DB_PATH", raising=False)
        path = get_default_knowledge_db_path()
        assert path.endswith("knowledge.db")
        assert str(tmp_path) in path

    def test_explicit_env_override(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_DB_PATH", "/custom/path.db")
        path = get_default_knowledge_db_path()
        assert path == "/custom/path.db"
