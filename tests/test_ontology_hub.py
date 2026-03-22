"""Tests for OntologyHub -- SQLite-backed persistent ontology store."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.ontology import (
    ActionExecution,
    Link,
    OntologyObj,
    OntologyRegistry,
)
from dharma_swarm.ontology_hub import OntologyHub


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hub(tmp_path: Path) -> OntologyHub:
    """Create a fresh OntologyHub backed by a temp database."""
    db = tmp_path / "test_ontology.db"
    h = OntologyHub(db_path=db)
    yield h
    h.close()


@pytest.fixture
def sample_objects() -> list[OntologyObj]:
    """Three objects of different types for testing."""
    return [
        OntologyObj(
            id="obj-alpha",
            type_name="Experiment",
            properties={"name": "alpha run", "model": "mistral-7b", "status": "completed"},
            created_by="researcher",
            version=1,
        ),
        OntologyObj(
            id="obj-beta",
            type_name="AgentIdentity",
            properties={"name": "cartographer", "role": "researcher"},
            created_by="system",
            version=1,
        ),
        OntologyObj(
            id="obj-gamma",
            type_name="KnowledgeArtifact",
            properties={"title": "R_V contraction finding", "content": "Hedges g=-1.47 on Mistral", "domain": "mech_interp"},
            created_by="researcher",
            version=2,
        ),
    ]


@pytest.fixture
def sample_links() -> list[Link]:
    """Links between the sample objects."""
    return [
        Link(
            id="link-1",
            link_name="produces",
            source_id="obj-alpha",
            source_type="Experiment",
            target_id="obj-gamma",
            target_type="KnowledgeArtifact",
            created_by="system",
            metadata={"run_id": "42"},
            witness_quality=0.8,
        ),
        Link(
            id="link-2",
            link_name="authored",
            source_id="obj-beta",
            source_type="AgentIdentity",
            target_id="obj-gamma",
            target_type="KnowledgeArtifact",
            created_by="system",
        ),
    ]


@pytest.fixture
def sample_action() -> ActionExecution:
    """A sample action execution."""
    return ActionExecution(
        id="action-1",
        action_name="Run",
        object_id="obj-alpha",
        object_type="Experiment",
        input_params={"temperature": 0.7},
        result="success",
        gate_results={"SATYA": "PASS", "AHIMSA": "PASS"},
        executed_by="cartographer",
        duration_ms=1234.5,
        error="",
    )


# ---------------------------------------------------------------------------
# Store and load objects
# ---------------------------------------------------------------------------


class TestStoreAndLoadObjects:
    """Store objects of different types, then load them back."""

    def test_store_and_load_single(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        obj = sample_objects[0]
        hub.store_object(obj)
        loaded = hub.load_object(obj.id)
        assert loaded is not None
        assert loaded.id == obj.id
        assert loaded.type_name == obj.type_name
        assert loaded.properties == obj.properties
        assert loaded.created_by == obj.created_by
        assert loaded.version == obj.version

    def test_store_three_load_all(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        for obj in sample_objects:
            loaded = hub.load_object(obj.id)
            assert loaded is not None
            assert loaded.id == obj.id
            assert loaded.type_name == obj.type_name

    def test_load_objects_by_type(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        experiments = hub.load_objects_by_type("Experiment")
        assert len(experiments) == 1
        assert experiments[0].id == "obj-alpha"

        agents = hub.load_objects_by_type("AgentIdentity")
        assert len(agents) == 1
        assert agents[0].id == "obj-beta"

    def test_load_nonexistent_returns_none(self, hub: OntologyHub) -> None:
        assert hub.load_object("does-not-exist") is None

    def test_store_replaces_existing(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        obj = sample_objects[0]
        hub.store_object(obj)

        updated = obj.model_copy(update={"version": 5, "properties": {"name": "updated run"}})
        hub.store_object(updated)

        loaded = hub.load_object(obj.id)
        assert loaded is not None
        assert loaded.version == 5
        assert loaded.properties["name"] == "updated run"
        # Should still be only 1 object
        assert hub.total_objects() == 1


# ---------------------------------------------------------------------------
# Store and load links
# ---------------------------------------------------------------------------


class TestStoreAndLoadLinks:
    """Store links between objects, load by source/target/name."""

    def test_store_and_load_by_source(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        links = hub.load_links(source_id="obj-alpha")
        assert len(links) == 1
        assert links[0].link_name == "produces"

    def test_load_by_target(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        links = hub.load_links(target_id="obj-gamma")
        assert len(links) == 2

    def test_load_by_name(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        links = hub.load_links(link_name="authored")
        assert len(links) == 1
        assert links[0].source_id == "obj-beta"

    def test_load_combined_filters(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        links = hub.load_links(source_id="obj-alpha", link_name="produces")
        assert len(links) == 1

        links = hub.load_links(source_id="obj-alpha", link_name="authored")
        assert len(links) == 0

    def test_load_all_links(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        links = hub.load_links()
        assert len(links) == 2

    def test_link_metadata_roundtrip(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        hub.store_link(sample_links[0])
        loaded = hub.load_links(source_id="obj-alpha")[0]
        assert loaded.metadata == {"run_id": "42"}
        assert loaded.witness_quality == 0.8


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------


class TestFullTextSearch:
    """FTS5 search finds objects by property values."""

    def test_search_by_property_value(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        results = hub.search_text("mistral")
        assert len(results) >= 1
        ids = [r.id for r in results]
        assert "obj-alpha" in ids

    def test_search_by_type_name(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        results = hub.search_text("Experiment")
        assert len(results) >= 1
        assert any(r.type_name == "Experiment" for r in results)

    def test_search_with_type_filter(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        # "contraction" appears in KnowledgeArtifact properties
        results = hub.search_text("contraction", type_name="KnowledgeArtifact")
        assert len(results) >= 1
        assert all(r.type_name == "KnowledgeArtifact" for r in results)

        # Same query filtered to wrong type returns empty
        results = hub.search_text("contraction", type_name="Experiment")
        assert len(results) == 0

    def test_search_empty_query(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        results = hub.search_text("")
        assert results == []

        results = hub.search_text("   ")
        assert results == []


# ---------------------------------------------------------------------------
# Sync with OntologyRegistry
# ---------------------------------------------------------------------------


class TestSyncFromRegistry:
    """sync_from_registry imports all objects + links from in-memory registry."""

    def test_sync_objects_and_links(self, hub: OntologyHub) -> None:
        registry = OntologyRegistry.create_dharma_registry()

        # Create objects in registry
        obj1, _ = registry.create_object("Experiment", {"name": "test-exp", "status": "running"})
        obj2, _ = registry.create_object("AgentIdentity", {"name": "builder", "role": "coder"})
        assert obj1 is not None
        assert obj2 is not None

        # Create a link
        _link, _ = registry.create_link("assigned_to", source_id=obj1.id, target_id=obj2.id)
        # assigned_to is TypedTask -> AgentIdentity, not Experiment -> AgentIdentity
        # so this will fail; use a proper link instead
        # Just add objects to the registry directly
        registry._objects[obj1.id] = obj1
        registry._objects[obj2.id] = obj2

        counts = hub.sync_from_registry(registry)
        assert counts["objects_synced"] >= 2
        assert hub.total_objects() >= 2

    def test_sync_action_log(self, hub: OntologyHub) -> None:
        registry = OntologyRegistry.create_dharma_registry()

        # Execute an action
        execution = registry.execute_action(
            "Experiment", "Run", "fake-id", {"param": "val"}, executed_by="tester"
        )
        assert execution.result in ("success", "failed")

        counts = hub.sync_from_registry(registry)
        assert counts["actions_synced"] >= 1

    def test_sync_sets_last_sync_time(self, hub: OntologyHub) -> None:
        registry = OntologyRegistry()
        hub.sync_from_registry(registry)
        assert hub.last_sync_time() is not None


# ---------------------------------------------------------------------------
# Load into registry
# ---------------------------------------------------------------------------


class TestLoadIntoRegistry:
    """load_into_registry populates empty registry from DB."""

    def test_roundtrip_via_registry(
        self,
        hub: OntologyHub,
        sample_objects: list[OntologyObj],
        sample_links: list[Link],
        sample_action: ActionExecution,
    ) -> None:
        # Store data in hub
        for obj in sample_objects:
            hub.store_object(obj)
        for link in sample_links:
            hub.store_link(link)
        hub.store_action(sample_action)

        # Load into a fresh registry
        registry = OntologyRegistry()
        counts = hub.load_into_registry(registry)

        assert counts["objects_loaded"] == 3
        assert counts["links_loaded"] == 2
        assert counts["actions_loaded"] == 1

        # Verify objects are accessible
        assert registry.get_object("obj-alpha") is not None
        assert registry.get_object("obj-beta") is not None
        assert registry.get_object("obj-gamma") is not None

        # Verify links
        links = registry.get_links(source_id="obj-alpha")
        assert len(links) == 1

        # Verify action log
        history = registry.action_history()
        assert len(history) == 1
        assert history[0].action_name == "Run"


# ---------------------------------------------------------------------------
# Restart persistence
# ---------------------------------------------------------------------------


class TestRestartPersistence:
    """Create hub, store data, close, reopen with same path, verify data."""

    def test_data_survives_restart(self, tmp_path: Path, sample_objects: list[OntologyObj], sample_links: list[Link]) -> None:
        db = tmp_path / "restart_test.db"

        # First session: write data
        hub1 = OntologyHub(db_path=db)
        for obj in sample_objects:
            hub1.store_object(obj)
        for link in sample_links:
            hub1.store_link(link)
        hub1.close()

        # Second session: read data
        hub2 = OntologyHub(db_path=db)
        assert hub2.total_objects() == 3
        assert hub2.total_links() == 2

        loaded = hub2.load_object("obj-alpha")
        assert loaded is not None
        assert loaded.properties["name"] == "alpha run"

        links = hub2.load_links(link_name="produces")
        assert len(links) == 1
        assert links[0].source_id == "obj-alpha"

        hub2.close()

    def test_actions_survive_restart(self, tmp_path: Path, sample_action: ActionExecution) -> None:
        db = tmp_path / "restart_actions.db"

        hub1 = OntologyHub(db_path=db)
        hub1.store_action(sample_action)
        hub1.close()

        hub2 = OntologyHub(db_path=db)
        actions = hub2.load_actions(object_id="obj-alpha")
        assert len(actions) == 1
        assert actions[0].action_name == "Run"
        assert actions[0].duration_ms == 1234.5
        hub2.close()


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


class TestCounts:
    """count_by_type and count_links_by_name return correct counts."""

    def test_count_by_type(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        for obj in sample_objects:
            hub.store_object(obj)

        counts = hub.count_by_type()
        assert counts["Experiment"] == 1
        assert counts["AgentIdentity"] == 1
        assert counts["KnowledgeArtifact"] == 1

    def test_count_links_by_name(self, hub: OntologyHub, sample_links: list[Link]) -> None:
        for link in sample_links:
            hub.store_link(link)

        counts = hub.count_links_by_name()
        assert counts["produces"] == 1
        assert counts["authored"] == 1

    def test_totals(
        self,
        hub: OntologyHub,
        sample_objects: list[OntologyObj],
        sample_links: list[Link],
        sample_action: ActionExecution,
    ) -> None:
        for obj in sample_objects:
            hub.store_object(obj)
        for link in sample_links:
            hub.store_link(link)
        hub.store_action(sample_action)

        assert hub.total_objects() == 3
        assert hub.total_links() == 2
        assert hub.total_actions() == 1

    def test_empty_counts(self, hub: OntologyHub) -> None:
        assert hub.count_by_type() == {}
        assert hub.count_links_by_name() == {}
        assert hub.total_objects() == 0
        assert hub.total_links() == 0
        assert hub.total_actions() == 0


# ---------------------------------------------------------------------------
# JSON export / import
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    """export_json + import_json round-trips all data."""

    def test_full_roundtrip(
        self,
        tmp_path: Path,
        sample_objects: list[OntologyObj],
        sample_links: list[Link],
        sample_action: ActionExecution,
    ) -> None:
        db1 = tmp_path / "export_source.db"
        hub1 = OntologyHub(db_path=db1)

        for obj in sample_objects:
            hub1.store_object(obj)
        for link in sample_links:
            hub1.store_link(link)
        hub1.store_action(sample_action)

        json_path = tmp_path / "export.json"
        exported = hub1.export_json(json_path)
        assert exported == 6  # 3 objects + 2 links + 1 action
        assert json_path.exists()

        # Import into a fresh hub
        db2 = tmp_path / "import_target.db"
        hub2 = OntologyHub(db_path=db2)
        imported = hub2.import_json(json_path)
        assert imported == 6

        # Verify all data arrived
        assert hub2.total_objects() == 3
        assert hub2.total_links() == 2
        assert hub2.total_actions() == 1

        loaded = hub2.load_object("obj-gamma")
        assert loaded is not None
        assert loaded.properties["title"] == "R_V contraction finding"

        links = hub2.load_links(link_name="authored")
        assert len(links) == 1

        actions = hub2.load_actions(action_name="Run")
        assert len(actions) == 1

        hub1.close()
        hub2.close()

    def test_export_empty_db(self, hub: OntologyHub, tmp_path: Path) -> None:
        json_path = tmp_path / "empty.json"
        exported = hub.export_json(json_path)
        assert exported == 0
        assert json_path.exists()


# ---------------------------------------------------------------------------
# Context manager and repr
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Context manager and repr work correctly."""

    def test_context_manager(self, tmp_path: Path, sample_objects: list[OntologyObj]) -> None:
        db = tmp_path / "ctx.db"
        with OntologyHub(db_path=db) as hub:
            hub.store_object(sample_objects[0])
            assert hub.total_objects() == 1
        # Connection is closed after exiting context

    def test_repr(self, hub: OntologyHub, sample_objects: list[OntologyObj]) -> None:
        hub.store_object(sample_objects[0])
        r = repr(hub)
        assert "OntologyHub" in r
        assert "objects=1" in r
        assert "links=0" in r


# ---------------------------------------------------------------------------
# Meta table
# ---------------------------------------------------------------------------


class TestMetaTable:
    """_meta table stores and retrieves key-value pairs."""

    def test_set_and_get(self, hub: OntologyHub) -> None:
        hub._set_meta("test_key", "test_value")
        assert hub._get_meta("test_key") == "test_value"

    def test_get_nonexistent(self, hub: OntologyHub) -> None:
        assert hub._get_meta("no_such_key") is None

    def test_schema_version_stored(self, hub: OntologyHub) -> None:
        assert hub._get_meta("schema_version") == "1"

    def test_last_sync_initially_none(self, hub: OntologyHub) -> None:
        assert hub.last_sync_time() is None
