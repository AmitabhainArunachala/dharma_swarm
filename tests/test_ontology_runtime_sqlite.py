"""Tests for the shared ontology runtime using SQLite persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.ontology_runtime import (
    get_shared_registry,
    ontology_path,
    persist_shared_registry,
    reset_shared_registry,
)


@pytest.fixture(autouse=True)
def isolated_shared_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
    reset_shared_registry()
    yield tmp_path
    reset_shared_registry()


def test_shared_registry_persists_to_sqlite_and_reloads(isolated_shared_runtime: Path) -> None:
    registry = get_shared_registry()
    obj, errors = registry.create_object(
        "Experiment",
        {"name": "sqlite_exp", "status": "designed"},
        created_by="tester",
    )

    assert obj is not None
    assert errors == []

    saved_path = persist_shared_registry(registry)
    assert saved_path == ontology_path()
    assert saved_path.exists()
    assert saved_path.suffix == ".db"
    assert (isolated_shared_runtime / "ontology.json").exists()

    reset_shared_registry()
    reloaded = get_shared_registry()
    restored = reloaded.get_object(obj.id)

    assert restored is not None
    assert restored.properties["name"] == "sqlite_exp"


def test_legacy_json_imports_once_into_sqlite(isolated_shared_runtime: Path) -> None:
    legacy_path = isolated_shared_runtime / "ontology.json"
    legacy = OntologyRegistry.create_dharma_registry()
    obj, errors = legacy.create_object(
        "WitnessLog",
        {"observation": "legacy truth", "observer": "agent-1"},
        created_by="tester",
    )

    assert obj is not None
    assert errors == []

    legacy.save(legacy_path)

    loaded = get_shared_registry()
    imported = loaded.get_object(obj.id)
    db_path = ontology_path()

    assert imported is not None
    assert imported.properties["observation"] == "legacy truth"
    assert db_path.exists()
    assert db_path.suffix == ".db"

    legacy_path.unlink()
    reset_shared_registry()

    reloaded = get_shared_registry()
    imported_again = reloaded.get_object(obj.id)

    assert imported_again is not None
    assert imported_again.properties["observation"] == "legacy truth"


def test_ontology_path_prefers_local_dharma_when_env_unset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DHARMA_ONTOLOGY_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dharma").mkdir()

    assert ontology_path() == tmp_path / ".dharma" / "ontology.db"
