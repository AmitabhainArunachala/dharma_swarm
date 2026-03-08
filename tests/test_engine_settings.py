"""Tests for dharma_swarm.engine.settings."""

from __future__ import annotations

from dharma_swarm.engine.settings import EngineSettings


def test_from_env_defaults(monkeypatch):
    for key in [
        "DGC_KNOWLEDGE_BACKEND",
        "DGC_QDRANT_URL",
        "DGC_QDRANT_COLLECTION",
        "DGC_QDRANT_VECTOR_SIZE",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = EngineSettings.from_env()
    assert cfg.knowledge_backend == "local"
    assert cfg.qdrant_url == "http://127.0.0.1:6333"
    assert cfg.qdrant_collection == "dgc_artifacts"
    assert cfg.qdrant_vector_size == 256


def test_from_env_custom_values(monkeypatch):
    monkeypatch.setenv("DGC_KNOWLEDGE_BACKEND", "qdrant")
    monkeypatch.setenv("DGC_QDRANT_URL", "http://qdrant.local:6333")
    monkeypatch.setenv("DGC_QDRANT_COLLECTION", "custom_collection")
    monkeypatch.setenv("DGC_QDRANT_VECTOR_SIZE", "384")

    cfg = EngineSettings.from_env()
    assert cfg.knowledge_backend == "qdrant"
    assert cfg.qdrant_url == "http://qdrant.local:6333"
    assert cfg.qdrant_collection == "custom_collection"
    assert cfg.qdrant_vector_size == 384


def test_from_env_invalid_values_fallback(monkeypatch):
    monkeypatch.setenv("DGC_KNOWLEDGE_BACKEND", "bad")
    monkeypatch.setenv("DGC_QDRANT_VECTOR_SIZE", "not-an-int")

    cfg = EngineSettings.from_env()
    assert cfg.knowledge_backend == "local"
    assert cfg.qdrant_vector_size == 256


def test_from_env_backend_case_insensitive(monkeypatch):
    monkeypatch.setenv("DGC_KNOWLEDGE_BACKEND", "  QDRANT  ")
    for key in ["DGC_QDRANT_URL", "DGC_QDRANT_COLLECTION", "DGC_QDRANT_VECTOR_SIZE"]:
        monkeypatch.delenv(key, raising=False)
    cfg = EngineSettings.from_env()
    assert cfg.knowledge_backend == "qdrant"


def test_from_env_vector_size_clamps_minimum(monkeypatch):
    monkeypatch.setenv("DGC_QDRANT_VECTOR_SIZE", "2")
    for key in ["DGC_KNOWLEDGE_BACKEND", "DGC_QDRANT_URL", "DGC_QDRANT_COLLECTION"]:
        monkeypatch.delenv(key, raising=False)
    cfg = EngineSettings.from_env()
    assert cfg.qdrant_vector_size == 8  # max(8, 2) = 8


def test_defaults_without_from_env():
    cfg = EngineSettings()
    assert cfg.knowledge_backend == "local"
    assert cfg.qdrant_vector_size == 256
    assert cfg.qdrant_collection == "dgc_artifacts"
