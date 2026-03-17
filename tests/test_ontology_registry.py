"""Tests for the Palantir-grade typed ontology layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dharma_swarm.ontology import (
    ActionDef,
    ActionExecution,
    Link,
    LinkCardinality,
    LinkDef,
    ObjectType,
    OntologyObj,
    OntologyRegistry,
    PropertyDef,
    PropertyType,
    SecurityLevel,
    SecurityPolicy,
    ShaktiEnergy,
    check_security,
    validate_link,
    validate_object,
    # Legacy API
    Entity,
    ONTOLOGY,
    blocked_entities,
    deadline_pressure,
    deadline_summary,
    entities_by_type,
    entity_context,
    entity_graph,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def registry() -> OntologyRegistry:
    return OntologyRegistry.create_dharma_registry()


@pytest.fixture
def populated_registry(registry: OntologyRegistry) -> OntologyRegistry:
    """Registry with sample objects and links."""
    thread, _ = registry.create_object("ResearchThread", {
        "name": "mechanistic", "domain": "mechanistic",
        "status": "active", "priority": 0.9,
    })
    exp, _ = registry.create_object("Experiment", {
        "name": "L27 causal", "status": "running",
        "model": "mistral-7b", "r_v_value": 0.72,
    })
    agent, _ = registry.create_object("AgentIdentity", {
        "name": "researcher-01", "role": "researcher",
    })
    artifact, _ = registry.create_object("KnowledgeArtifact", {
        "title": "Patching results", "artifact_type": "result",
        "domain": "mech_interp", "verified": True,
    })
    task, _ = registry.create_object("TypedTask", {
        "title": "Run pipeline", "status": "pending",
        "priority": "high", "task_type": "experiment",
    })
    registry.create_link("has_experiment", thread.id, exp.id)
    registry.create_link("produces", exp.id, artifact.id)
    registry.create_link("assigned_to", task.id, agent.id)
    return registry


# ── Registry Factory ────────────────────────────────────────────────


class TestRegistryFactory:
    def test_create_dharma_registry(self, registry: OntologyRegistry) -> None:
        stats = registry.stats()
        assert stats["registered_types"] == 14  # 8 original + 6 metabolic
        assert stats["registered_links"] >= 40  # 12+8 defs, each with inverse
        assert stats["registered_actions"] >= 15

    def test_all_type_names(self, registry: OntologyRegistry) -> None:
        names = registry.type_names()
        expected = [
            "ActionProposal", "AgentIdentity", "Contribution",
            "EvolutionEntry", "Experiment", "GateDecisionRecord",
            "KnowledgeArtifact", "Outcome", "Paper", "ResearchThread",
            "TypedTask", "ValueEvent", "VentureCell", "WitnessLog",
        ]
        assert names == expected

    def test_each_type_has_properties(self, registry: OntologyRegistry) -> None:
        for obj_type in registry.get_types():
            assert len(obj_type.properties) > 0, f"{obj_type.name} has no properties"

    def test_each_type_has_telos(self, registry: OntologyRegistry) -> None:
        for obj_type in registry.get_types():
            assert 0.0 <= obj_type.telos_alignment <= 1.0


# ── Object CRUD ─────────────────────────────────────────────────────


class TestObjectCRUD:
    def test_create_valid_object(self, registry: OntologyRegistry) -> None:
        obj, errs = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })
        assert obj is not None
        assert errs == []
        assert obj.type_name == "Experiment"
        assert obj.properties["name"] == "test"

    def test_create_missing_required(self, registry: OntologyRegistry) -> None:
        obj, errs = registry.create_object("Experiment", {"status": "designed"})
        assert obj is None
        assert any("required" in e for e in errs)

    def test_create_invalid_enum(self, registry: OntologyRegistry) -> None:
        obj, errs = registry.create_object("Experiment", {
            "name": "test", "status": "nonexistent",
        })
        assert obj is None
        assert any("enum" in e for e in errs)

    def test_create_unknown_type(self, registry: OntologyRegistry) -> None:
        obj, errs = registry.create_object("FakeType", {})
        assert obj is None
        assert any("unknown" in e for e in errs)

    def test_get_object(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("WitnessLog", {
            "observation": "test", "observer": "test-agent",
        })
        found = registry.get_object(obj.id)
        assert found is not None
        assert found.id == obj.id

    def test_get_objects_by_type(self, registry: OntologyRegistry) -> None:
        registry.create_object("WitnessLog", {
            "observation": "a", "observer": "agent-1",
        })
        registry.create_object("WitnessLog", {
            "observation": "b", "observer": "agent-2",
        })
        logs = registry.get_objects_by_type("WitnessLog")
        assert len(logs) == 2

    def test_update_valid(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })
        updated, errs = registry.update_object(obj.id, {"status": "running"})
        assert updated is not None
        assert errs == []
        assert updated.properties["status"] == "running"
        assert updated.version == 2

    def test_update_immutable_blocked(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("AgentIdentity", {
            "name": "agent-x", "role": "researcher",
        })
        _, errs = registry.update_object(obj.id, {"name": "renamed"})
        assert any("immutable" in e for e in errs)

    def test_update_nonexistent(self, registry: OntologyRegistry) -> None:
        _, errs = registry.update_object("fake-id", {"status": "running"})
        assert any("not found" in e for e in errs)


# ── Links ───────────────────────────────────────────────────────────


class TestLinks:
    def test_create_valid_link(self, populated_registry: OntologyRegistry) -> None:
        links = populated_registry.get_links(link_name="has_experiment")
        assert len(links) == 1

    def test_link_type_enforcement(self, registry: OntologyRegistry) -> None:
        thread, _ = registry.create_object("ResearchThread", {
            "name": "test", "status": "active",
        })
        agent, _ = registry.create_object("AgentIdentity", {
            "name": "agent", "role": "researcher",
        })
        _, errs = registry.create_link("has_experiment", thread.id, agent.id)
        assert any("target" in e for e in errs)

    def test_cardinality_enforcement(self, registry: OntologyRegistry) -> None:
        task, _ = registry.create_object("TypedTask", {
            "title": "test", "status": "pending",
        })
        a1, _ = registry.create_object("AgentIdentity", {
            "name": "a1", "role": "coder",
        })
        a2, _ = registry.create_object("AgentIdentity", {
            "name": "a2", "role": "coder",
        })
        link1, errs1 = registry.create_link("assigned_to", task.id, a1.id)
        assert link1 is not None
        _, errs2 = registry.create_link("assigned_to", task.id, a2.id)
        assert any("cardinality" in e for e in errs2)

    def test_many_to_many_allows_multiple(self, registry: OntologyRegistry) -> None:
        task, _ = registry.create_object("TypedTask", {
            "title": "test", "status": "pending",
        })
        k1, _ = registry.create_object("KnowledgeArtifact", {
            "title": "a1", "artifact_type": "file",
        })
        k2, _ = registry.create_object("KnowledgeArtifact", {
            "title": "a2", "artifact_type": "note",
        })
        l1, _ = registry.create_link("consumes", task.id, k1.id)
        l2, _ = registry.create_link("consumes", task.id, k2.id)
        assert l1 is not None
        assert l2 is not None

    def test_get_linked_objects(self, populated_registry: OntologyRegistry) -> None:
        threads = populated_registry.get_objects_by_type("ResearchThread")
        exps = populated_registry.get_linked_objects(threads[0].id, "has_experiment")
        assert len(exps) == 1
        assert exps[0].properties["name"] == "L27 causal"

    def test_inverse_link_registered(self, registry: OntologyRegistry) -> None:
        inv = registry.get_link_def("Experiment", "belongs_to_thread")
        assert inv is not None
        assert inv.target_type == "ResearchThread"

    def test_source_not_found(self, registry: OntologyRegistry) -> None:
        target, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })
        _, errs = registry.create_link("has_experiment", "fake-id", target.id)
        assert any("source" in e for e in errs)


# ── Actions ─────────────────────────────────────────────────────────


class TestActions:
    def test_execute_success(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })
        result = registry.execute_action("Experiment", "Run", obj.id, {"gpu": "A100"})
        assert result.result == "success"

    def test_execute_unknown_action(self, registry: OntologyRegistry) -> None:
        result = registry.execute_action("Experiment", "FakeAction", "id", {})
        assert result.result == "failed"
        assert "no action" in result.error

    def test_telos_gate_blocks(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })

        def block_gates(name, params):
            return {"SATYA": "BLOCK"}

        result = registry.execute_action(
            "Experiment", "Run", obj.id, {}, gate_check=block_gates,
        )
        assert result.result == "blocked"

    def test_telos_gate_passes(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })

        def pass_gates(name, params):
            return {"AHIMSA": "PASS", "SATYA": "PASS"}

        result = registry.execute_action(
            "Experiment", "Run", obj.id, {}, gate_check=pass_gates,
        )
        assert result.result == "success"

    def test_telos_required_type_blocks_without_gate(
        self, registry: OntologyRegistry,
    ) -> None:
        obj, _ = registry.create_object("EvolutionEntry", {
            "component": "test.py", "change_type": "mutation",
        })
        result = registry.execute_action(
            "EvolutionEntry", "Propose", obj.id, {},
        )
        assert result.result == "blocked"
        assert "telos gate required" in result.error

    def test_action_history(self, registry: OntologyRegistry) -> None:
        obj, _ = registry.create_object("Experiment", {
            "name": "test", "status": "designed",
        })
        registry.execute_action("Experiment", "Design", obj.id, {})
        registry.execute_action("Experiment", "Run", obj.id, {})
        history = registry.action_history(object_id=obj.id)
        assert len(history) == 2
        assert history[0].action_name == "Run"  # most recent first


# ── Security ────────────────────────────────────────────────────────


class TestSecurity:
    def test_wildcard_allows_all(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("Experiment")
        ok, msg = check_security(obj_type, "anyone", "read")
        assert ok is True

    def test_restricted_roles(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("Paper")
        ok, msg = check_security(obj_type, "coder", "write")
        assert ok is False
        assert "denied" in msg

    def test_allowed_role(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("Paper")
        ok, msg = check_security(obj_type, "researcher", "write")
        assert ok is True

    def test_delete_restricted(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("AgentIdentity")
        ok, msg = check_security(obj_type, "researcher", "delete")
        assert ok is False

    def test_witness_log_no_delete(self, registry: OntologyRegistry) -> None:
        obj_type = registry.get_type("WitnessLog")
        ok, msg = check_security(obj_type, "system", "delete")
        assert ok is False  # empty delete_roles = nobody can delete


# ── OAG (Ontology-Augmented Generation) ─────────────────────────────


class TestOAG:
    def test_describe_type(self, registry: OntologyRegistry) -> None:
        desc = registry.describe_type("Experiment")
        assert "Experiment" in desc
        assert "r_v_value" in desc
        assert "mahasaraswati" in desc

    def test_describe_unknown(self, registry: OntologyRegistry) -> None:
        assert "Unknown" in registry.describe_type("Fake")

    def test_schema_for_llm_all(self, registry: OntologyRegistry) -> None:
        schema = registry.schema_for_llm()
        assert "Ontology Context" in schema
        for name in registry.type_names():
            assert name in schema

    def test_schema_for_llm_subset(self, registry: OntologyRegistry) -> None:
        schema = registry.schema_for_llm(["WitnessLog", "Paper"])
        assert "WitnessLog" in schema
        assert "Paper" in schema
        assert "Experiment" not in schema

    def test_object_context(self, populated_registry: OntologyRegistry) -> None:
        exps = populated_registry.get_objects_by_type("Experiment")
        ctx = populated_registry.object_context_for_llm(exps[0].id)
        assert "L27 causal" in ctx
        assert "produces" in ctx

    def test_object_context_not_found(self, registry: OntologyRegistry) -> None:
        ctx = registry.object_context_for_llm("fake-id")
        assert "not found" in ctx.lower()


# ── Persistence ─────────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load(self, populated_registry: OntologyRegistry) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            populated_registry.save(path)
            assert path.exists()

            reg2 = OntologyRegistry()
            loaded = reg2.load(path)
            assert loaded > 0

            s1 = populated_registry.stats()
            s2 = reg2.stats()
            assert s2["registered_types"] == s1["registered_types"]
            assert s2["total_objects"] == s1["total_objects"]
            assert s2["total_links"] == s1["total_links"]

    def test_load_nonexistent(self, registry: OntologyRegistry) -> None:
        loaded = registry.load(Path("/tmp/nonexistent_ontology.json"))
        assert loaded == 0

    def test_graph_summary(self, registry: OntologyRegistry) -> None:
        summary = registry.graph_summary()
        assert "Ontology Graph" in summary
        assert "Experiment" in summary


# ── Validation ──────────────────────────────────────────────────────


class TestValidation:
    def test_validate_object_type_mismatch(self) -> None:
        obj = OntologyObj(type_name="Wrong", properties={})
        obj_type = ObjectType(name="Right")
        errs = validate_object(obj, obj_type)
        assert any("mismatch" in e for e in errs)

    def test_validate_link_name_mismatch(self) -> None:
        link = Link(
            link_name="wrong",
            source_id="a", source_type="X",
            target_id="b", target_type="Y",
        )
        link_def = LinkDef(name="right", source_type="X", target_type="Y")
        errs = validate_link(link, link_def)
        assert any("mismatch" in e for e in errs)

    def test_validate_float_type(self) -> None:
        obj_type = ObjectType(
            name="Test",
            properties={"val": PropertyDef(
                name="val", property_type=PropertyType.FLOAT,
            )},
        )
        obj = OntologyObj(type_name="Test", properties={"val": "not_a_number"})
        errs = validate_object(obj, obj_type)
        assert any("numeric" in e for e in errs)

    def test_validate_boolean_type(self) -> None:
        obj_type = ObjectType(
            name="Test",
            properties={"flag": PropertyDef(
                name="flag", property_type=PropertyType.BOOLEAN,
            )},
        )
        obj = OntologyObj(type_name="Test", properties={"flag": "true"})
        errs = validate_object(obj, obj_type)
        assert any("boolean" in e for e in errs)


# ── Legacy API ──────────────────────────────────────────────────────


class TestLegacyAPI:
    def test_ontology_dict_populated(self) -> None:
        assert len(ONTOLOGY) >= 14

    def test_rv_paper_entity(self) -> None:
        rv = ONTOLOGY["rv_paper"]
        assert rv.type == "research_paper"
        assert rv.deadline is not None

    def test_entities_by_type(self) -> None:
        papers = entities_by_type("research_paper")
        assert len(papers) >= 2

    def test_entity_graph(self) -> None:
        graph = entity_graph()
        assert "rv_paper" in graph
        assert "mech_interp_lab" in graph["rv_paper"]

    def test_deadline_pressure(self) -> None:
        dl = deadline_pressure()
        assert len(dl) >= 1

    def test_deadline_summary(self) -> None:
        s = deadline_summary()
        assert "rv_paper" in s

    def test_entity_context(self) -> None:
        ctx = entity_context("rv_paper")
        assert "COLM" in ctx

    def test_entity_context_unknown(self) -> None:
        ctx = entity_context("nonexistent")
        assert "Unknown" in ctx

    def test_blocked_entities(self) -> None:
        # No blocked entities currently
        blocked = blocked_entities()
        assert isinstance(blocked, list)


# ── Dharmic Extensions ──────────────────────────────────────────────


class TestDharmicExtensions:
    def test_witness_log_max_telos(self, registry: OntologyRegistry) -> None:
        wl = registry.get_type("WitnessLog")
        assert wl.telos_alignment == 1.0

    def test_evolution_telos_required(self, registry: OntologyRegistry) -> None:
        ev = registry.get_type("EvolutionEntry")
        assert ev.security.telos_required is True

    def test_shakti_energies_diverse(self, registry: OntologyRegistry) -> None:
        energies = {t.shakti_energy for t in registry.get_types()}
        assert len(energies) >= 3  # at least 3 of 4 shaktis represented

    def test_actions_have_telos_gates(self, registry: OntologyRegistry) -> None:
        gated_actions = [
            a for a in registry._actions.values()
            if a.telos_gates
        ]
        assert len(gated_actions) >= 5
