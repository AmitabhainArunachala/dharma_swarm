"""Tests for ontology_runtime.py — shared registry singleton and path resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dharma_swarm.ontology_runtime as _mod
from dharma_swarm.ontology_runtime import (
    _configured_path,
    _legacy_ontology_json_path,
    get_shared_registry,
    ontology_path,
    persist_shared_registry,
    reset_shared_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_singleton():
    """Reset global singleton before and after each test."""
    reset_shared_registry()
    yield
    reset_shared_registry()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_ontology_path_explicit(self, tmp_path):
        p = ontology_path(tmp_path / "custom.db")
        assert p == tmp_path / "custom.db"

    def test_ontology_path_json_suffix_becomes_db(self, tmp_path):
        p = ontology_path(tmp_path / "ontology.json")
        assert p.suffix == ".db"
        assert p.stem == "ontology"

    def test_ontology_path_from_env(self, tmp_path, monkeypatch):
        target = tmp_path / "env.db"
        monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(target))
        p = ontology_path()
        assert p == target

    def test_ontology_path_env_json_becomes_db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "onto.json"))
        p = ontology_path()
        assert p.suffix == ".db"

    def test_ontology_path_falls_back_to_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        p = ontology_path()
        assert str(p).endswith("ontology.db")

    def test_configured_path_explicit(self, tmp_path):
        p = _configured_path(tmp_path / "my.db")
        assert p == tmp_path / "my.db"

    def test_configured_path_expands_tilde(self, monkeypatch):
        monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
        p = _configured_path("~/test.db")
        assert "~" not in str(p)

    def test_legacy_json_path_from_db(self, tmp_path):
        p = _legacy_ontology_json_path(tmp_path / "ontology.db")
        assert p == tmp_path / "ontology.json"

    def test_legacy_json_path_from_json(self, tmp_path):
        p = _legacy_ontology_json_path(tmp_path / "ontology.json")
        assert p == tmp_path / "ontology.json"

    def test_local_dharma_dir_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".dharma").mkdir()
        p = ontology_path()
        assert p == tmp_path / ".dharma" / "ontology.db"


# ---------------------------------------------------------------------------
# Shared registry singleton
# ---------------------------------------------------------------------------


class TestSharedRegistry:
    def test_get_creates_registry(self, tmp_path):
        reg = get_shared_registry(tmp_path / "test.db")
        assert reg is not None
        # Should have dharma types registered
        assert reg.get_type("AgentIdentity") is not None

    def test_get_returns_same_instance(self, tmp_path):
        db = tmp_path / "test.db"
        r1 = get_shared_registry(db)
        r2 = get_shared_registry(db)
        assert r1 is r2

    def test_force_reload_gives_new_instance(self, tmp_path):
        db = tmp_path / "test.db"
        r1 = get_shared_registry(db)
        r2 = get_shared_registry(db, force_reload=True)
        assert r1 is not r2

    def test_different_path_gives_new_instance(self, tmp_path):
        r1 = get_shared_registry(tmp_path / "a.db")
        r2 = get_shared_registry(tmp_path / "b.db")
        assert r1 is not r2


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_singleton(self, tmp_path):
        get_shared_registry(tmp_path / "test.db")
        reset_shared_registry()
        # After reset, module globals should be None
        assert _mod._SHARED_REGISTRY is None
        assert _mod._SHARED_REGISTRY_PATH is None
        assert _mod._SHARED_HUB is None

    def test_reset_idempotent(self):
        reset_shared_registry()
        reset_shared_registry()  # should not raise


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------


class TestPersist:
    def test_persist_returns_path(self, tmp_path):
        db = tmp_path / "test.db"
        get_shared_registry(db)
        result = persist_shared_registry(path=db)
        assert result == db

    def test_persist_json_compat_writes_json(self, tmp_path):
        """When configured path has .json suffix, persist writes .json too."""
        json_path = tmp_path / "ontology.json"
        reg = get_shared_registry(json_path)
        persist_shared_registry(registry=reg, path=json_path)
        assert json_path.exists()


# ---------------------------------------------------------------------------
# Legacy JSON import
# ---------------------------------------------------------------------------


class TestLegacyImport:
    def test_import_objects_from_json(self, tmp_path):
        """Legacy JSON with objects is imported into an empty registry."""
        json_path = tmp_path / "ontology.json"
        json_path.write_text(json.dumps({
            "objects": {
                "obj-1": {
                    "id": "obj-1",
                    "type_name": "AgentIdentity",
                    "properties": {"name": "test_agent", "role": "general", "status": "idle"},
                }
            },
            "link_instances": {},
            "action_log": [],
        }), encoding="utf-8")

        reg = get_shared_registry(json_path)
        obj = reg.get_object("obj-1")
        assert obj is not None
        assert obj.properties["name"] == "test_agent"

    def test_import_skips_if_hub_not_empty(self, tmp_path):
        """If the hub already has data, JSON import is skipped."""
        # First load creates the hub
        json_path = tmp_path / "ontology.json"
        json_path.write_text(json.dumps({
            "objects": {
                "obj-1": {
                    "id": "obj-1",
                    "type_name": "AgentIdentity",
                    "properties": {"name": "first", "role": "general", "status": "idle"},
                }
            },
        }), encoding="utf-8")

        reg = get_shared_registry(json_path)
        persist_shared_registry(registry=reg, path=json_path)

        # Now modify the JSON
        json_path.write_text(json.dumps({
            "objects": {
                "obj-2": {
                    "id": "obj-2",
                    "type_name": "AgentIdentity",
                    "properties": {"name": "second", "role": "general", "status": "idle"},
                }
            },
        }), encoding="utf-8")

        # Force reload, but hub already has data so JSON import is skipped
        reg2 = get_shared_registry(json_path, force_reload=True)
        assert reg2.get_object("obj-2") is None  # not imported

    def test_import_corrupted_json(self, tmp_path):
        """Corrupted JSON doesn't crash, registry still loads."""
        json_path = tmp_path / "ontology.json"
        json_path.write_text("not valid json at all", encoding="utf-8")

        reg = get_shared_registry(json_path)
        assert reg is not None  # still functional

    def test_import_missing_json(self, tmp_path):
        """Missing JSON file doesn't crash."""
        reg = get_shared_registry(tmp_path / "nonexistent.json")
        assert reg is not None
