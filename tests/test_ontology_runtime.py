"""Tests for ontology_runtime.py — shared runtime ontology registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.ontology_runtime import (
    _configured_path,
    _legacy_ontology_json_path,
    ontology_path,
    get_shared_registry,
    persist_shared_registry,
    reset_shared_registry,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test starts with a clean singleton."""
    reset_shared_registry()
    yield
    reset_shared_registry()


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestConfiguredPath:
    def test_explicit_path(self):
        p = _configured_path("/tmp/custom.db")
        assert p == Path("/tmp/custom.db")

    def test_env_override(self, monkeypatch, tmp_path):
        target = tmp_path / "onto.db"
        monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(target))
        p = _configured_path()
        assert p == target

    def test_default_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
        # Avoid matching .dharma in cwd
        monkeypatch.chdir(tmp_path)
        p = _configured_path()
        assert p.name == "ontology.db"

    def test_local_dharma_dir(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
        (tmp_path / ".dharma").mkdir()
        monkeypatch.chdir(tmp_path)
        p = _configured_path()
        assert p == tmp_path / ".dharma" / "ontology.db"


class TestOntologyPath:
    def test_db_extension_passthrough(self):
        assert ontology_path("/tmp/test.db") == Path("/tmp/test.db")

    def test_json_extension_converts(self):
        result = ontology_path("/tmp/test.json")
        assert result == Path("/tmp/test.db")


class TestLegacyPath:
    def test_json_stays_json(self):
        result = _legacy_ontology_json_path("/tmp/test.json")
        assert result == Path("/tmp/test.json")

    def test_db_becomes_json(self):
        result = _legacy_ontology_json_path("/tmp/test.db")
        assert result == Path("/tmp/test.json")


# ---------------------------------------------------------------------------
# get/persist/reset shared registry
# ---------------------------------------------------------------------------


class TestSharedRegistry:
    def test_get_creates_registry(self, tmp_path):
        db_path = tmp_path / "test.db"
        registry = get_shared_registry(db_path)
        assert registry is not None

    def test_get_returns_same_instance(self, tmp_path):
        db_path = tmp_path / "test.db"
        r1 = get_shared_registry(db_path)
        r2 = get_shared_registry(db_path)
        assert r1 is r2

    def test_force_reload(self, tmp_path):
        db_path = tmp_path / "test.db"
        r1 = get_shared_registry(db_path)
        r2 = get_shared_registry(db_path, force_reload=True)
        assert r1 is not r2

    def test_persist_returns_path(self, tmp_path):
        db_path = tmp_path / "test.db"
        get_shared_registry(db_path)
        result = persist_shared_registry(path=db_path)
        assert result == db_path

    def test_reset_clears(self, tmp_path):
        db_path = tmp_path / "test.db"
        r1 = get_shared_registry(db_path)
        reset_shared_registry()
        r2 = get_shared_registry(db_path)
        assert r1 is not r2

    def test_legacy_json_import(self, tmp_path):
        """If a .json file exists, its contents are imported on first load."""
        json_path = tmp_path / "test.json"
        db_path = tmp_path / "test.db"

        # Write a legacy JSON with a minimal object
        legacy = {
            "objects": {
                "obj-1": {
                    "id": "obj-1",
                    "type_name": "concept",
                    "properties": {},
                }
            },
            "link_instances": {},
            "action_log": [],
        }
        json_path.write_text(json.dumps(legacy), encoding="utf-8")

        # Request via .json path → internally uses .db but imports .json
        registry = get_shared_registry(json_path)
        # The imported object should exist
        assert registry.get_object("obj-1") is not None
