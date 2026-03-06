"""Tests for dharma_swarm.engine.knowledge_store."""

from __future__ import annotations

from dharma_swarm.engine.knowledge_store import (
    InMemoryKnowledgeStore,
    KnowledgeRecord,
    create_knowledge_store,
)


def test_add_and_search_returns_best_match():
    store = InMemoryKnowledgeStore()
    store.add(KnowledgeRecord(text="GPU kernel optimization with Triton", metadata={"kind": "code"}))
    store.add(KnowledgeRecord(text="Dharmic contemplative protocol notes", metadata={"kind": "research"}))

    results = store.search("optimize triton kernel", k=2)
    assert len(results) == 2
    assert "Triton" in results[0][0].text
    assert results[0][1] >= results[1][1]


def test_search_with_metadata_filters():
    store = InMemoryKnowledgeStore()
    store.add(KnowledgeRecord(text="signal from codebase", metadata={"kind": "code", "session": "s1"}))
    store.add(KnowledgeRecord(text="signal from research", metadata={"kind": "research", "session": "s1"}))

    results = store.search("signal", filters={"kind": "research"})
    assert len(results) == 1
    assert results[0][0].metadata["kind"] == "research"


def test_k_limit_enforced():
    store = InMemoryKnowledgeStore()
    for i in range(10):
        store.add(KnowledgeRecord(text=f"entry {i}"))

    results = store.search("entry", k=3)
    assert len(results) == 3


def test_create_knowledge_store_returns_local_implementation():
    store = create_knowledge_store(prefer_qdrant=True)
    assert isinstance(store, InMemoryKnowledgeStore)


def test_create_knowledge_store_invalid_backend_falls_back_to_local():
    store = create_knowledge_store(backend="weird")
    assert isinstance(store, InMemoryKnowledgeStore)


def test_create_knowledge_store_qdrant_success_path(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(
        "dharma_swarm.engine.knowledge_store._make_qdrant_store",
        lambda **_: sentinel,
    )
    store = create_knowledge_store(backend="qdrant")
    assert store is sentinel


def test_create_knowledge_store_qdrant_failure_falls_back(monkeypatch):
    def _boom(**_):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(
        "dharma_swarm.engine.knowledge_store._make_qdrant_store",
        _boom,
    )
    store = create_knowledge_store(backend="qdrant")
    assert isinstance(store, InMemoryKnowledgeStore)


def test_create_knowledge_store_uses_settings_object(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(
        "dharma_swarm.engine.knowledge_store._make_qdrant_store",
        lambda **_: sentinel,
    )

    class _Settings:
        knowledge_backend = "qdrant"
        qdrant_url = "http://fake:6333"
        qdrant_collection = "x"
        qdrant_vector_size = 128

    store = create_knowledge_store(settings=_Settings())
    assert store is sentinel
