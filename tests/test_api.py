"""Tests for the REST API Gateway.

Covers health, ontology (types/objects/actions), schema, tasks,
lineage, and workflow endpoints using FastAPI TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dharma_swarm.api import ApiResponse, create_app
from dharma_swarm.lineage import LineageGraph
from dharma_swarm.ontology import OntologyRegistry
from dharma_swarm.workflow import _REGISTRY, workflow


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def registry():
    return OntologyRegistry.create_dharma_registry()


@pytest.fixture()
def lineage(tmp_path):
    return LineageGraph(db_path=tmp_path / "lineage.db")


@pytest.fixture()
def client(registry, lineage):
    app = create_app(registry=registry, lineage_graph=lineage)
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_workflow_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["data"]["status"] == "healthy"

    def test_health_includes_ontology_stats(self, client):
        resp = client.get("/api/health")
        data = resp.json()["data"]
        assert "ontology" in data
        assert "registered_types" in data["ontology"]

    def test_health_includes_lineage_stats(self, client):
        resp = client.get("/api/health")
        data = resp.json()["data"]
        assert "lineage" in data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ontology: Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOntologyTypes:
    def test_list_types(self, client):
        resp = client.get("/api/ontology")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) > 0
        names = [t["name"] for t in data]
        assert "Experiment" in names

    def test_list_types_has_expected_fields(self, client):
        resp = client.get("/api/ontology")
        first = resp.json()["data"][0]
        assert "name" in first
        assert "description" in first
        assert "telos_alignment" in first
        assert "shakti" in first
        assert "property_count" in first

    def test_describe_existing_type(self, client):
        resp = client.get("/api/ontology/Experiment")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "description" in data
        assert "links" in data
        assert "actions" in data

    def test_describe_nonexistent_type_404(self, client):
        resp = client.get("/api/ontology/Nonexistent")
        assert resp.status_code == 404

    def test_describe_type_links_structure(self, client):
        resp = client.get("/api/ontology/Experiment")
        data = resp.json()["data"]
        for link in data["links"]:
            assert "name" in link
            assert "target" in link
            assert "cardinality" in link

    def test_describe_type_actions_structure(self, client):
        resp = client.get("/api/ontology/Experiment")
        data = resp.json()["data"]
        for action in data["actions"]:
            assert "name" in action
            assert "deterministic" in action
            assert "gates" in action


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Schema (OAG)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSchema:
    def test_full_schema(self, client):
        resp = client.get("/api/schema")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "schema" in data
        assert "graph" in data
        assert "stats" in data

    def test_schema_is_string(self, client):
        resp = client.get("/api/schema")
        data = resp.json()["data"]
        assert isinstance(data["schema"], str)
        assert isinstance(data["graph"], str)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ontology: Objects
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOntologyObjects:
    def test_list_objects_empty(self, client):
        resp = client.get("/api/ontology/objects")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create_object(self, client):
        resp = client.post("/api/ontology/objects", json={
            "type_name": "Experiment",
            "properties": {"name": "test_exp", "hypothesis": "test"},
            "created_by": "tester",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "Experiment"
        assert data["properties"]["name"] == "test_exp"
        assert "id" in data

    def test_create_object_invalid_type(self, client):
        resp = client.post("/api/ontology/objects", json={
            "type_name": "FakeType",
            "properties": {},
        })
        assert resp.status_code == 400

    def test_list_objects_after_creation(self, client):
        client.post("/api/ontology/objects", json={
            "type_name": "Experiment",
            "properties": {"name": "exp1", "hypothesis": "h1"},
        })
        resp = client.get("/api/ontology/objects")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["type"] == "Experiment"

    def test_list_objects_filter_by_type(self, client):
        client.post("/api/ontology/objects", json={
            "type_name": "Experiment",
            "properties": {"name": "exp1", "hypothesis": "h1"},
        })
        resp = client.get("/api/ontology/objects?type_name=Experiment")
        assert len(resp.json()["data"]) == 1

        resp = client.get("/api/ontology/objects?type_name=Agent")
        assert len(resp.json()["data"]) == 0

    def test_get_object_by_id(self, client):
        create_resp = client.post("/api/ontology/objects", json={
            "type_name": "Experiment",
            "properties": {"name": "exp_get", "hypothesis": "test"},
        })
        obj_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/api/ontology/objects/{obj_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == obj_id
        assert data["properties"]["name"] == "exp_get"
        assert "context" in data

    def test_get_nonexistent_object_404(self, client):
        resp = client.get("/api/ontology/objects/nonexistent_id")
        assert resp.status_code == 404

    def test_object_fields(self, client):
        client.post("/api/ontology/objects", json={
            "type_name": "Experiment",
            "properties": {"name": "fields_test", "hypothesis": "h"},
            "created_by": "tester",
        })
        resp = client.get("/api/ontology/objects")
        obj = resp.json()["data"][0]
        assert "id" in obj
        assert "type" in obj
        assert "properties" in obj
        assert "created_by" in obj
        assert "version" in obj


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ontology: Actions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOntologyActions:
    def test_execute_action(self, client):
        resp = client.post("/api/ontology/actions", json={
            "object_type": "Experiment",
            "action_name": "Run",
            "params": {"config": "test"},
            "executed_by": "tester",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "result" in data
        assert "action" in data

    def test_execute_nonexistent_action(self, client):
        resp = client.post("/api/ontology/actions", json={
            "object_type": "Experiment",
            "action_name": "nonexistent_action",
            "executed_by": "tester",
        })
        assert resp.status_code == 400


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tasks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTasks:
    def test_create_task(self, client):
        resp = client.post("/api/tasks", json={
            "title": "Test Task",
            "description": "A test task",
            "priority": "high",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Test Task"
        assert data["priority"] == "high"
        assert "id" in data
        assert "status" in data

    def test_create_task_default_priority(self, client):
        resp = client.post("/api/tasks", json={"title": "Default priority"})
        data = resp.json()["data"]
        assert data["priority"] == "normal"

    def test_create_task_invalid_priority_fallback(self, client):
        resp = client.post("/api/tasks", json={
            "title": "Bad priority",
            "priority": "invalid_priority",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["priority"] == "normal"  # falls back

    def test_create_task_with_metadata(self, client):
        resp = client.post("/api/tasks", json={
            "title": "Meta task",
            "metadata": {"experiment_id": "e123"},
        })
        assert resp.status_code == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Lineage
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLineage:
    def test_provenance_empty(self, client):
        resp = client.get("/api/lineage/unknown_artifact")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["artifact_id"] == "unknown_artifact"
        assert data["chain"] == []

    def test_provenance_after_recording(self, client, lineage):
        lineage.record_transformation(
            task_id="t1",
            operation="compute",
            inputs=["raw_data"],
            outputs=["result"],
            agent="researcher",
        )
        resp = client.get("/api/lineage/result")
        data = resp.json()["data"]
        assert data["artifact_id"] == "result"
        assert len(data["chain"]) >= 1
        assert data["chain"][0]["operation"] == "compute"

    def test_impact_empty(self, client):
        resp = client.get("/api/lineage/unknown/impact")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["root_artifact"] == "unknown"
        assert data["total_descendants"] == 0

    def test_impact_after_recording(self, client, lineage):
        lineage.record_transformation(
            task_id="t1",
            operation="transform",
            inputs=["source"],
            outputs=["derived_a", "derived_b"],
            agent="agent1",
        )
        resp = client.get("/api/lineage/source/impact")
        data = resp.json()["data"]
        assert data["root_artifact"] == "source"
        assert data["total_descendants"] >= 2

    def test_lineage_chain_fields(self, client, lineage):
        lineage.record_transformation(
            task_id="t1",
            operation="load",
            inputs=[],
            outputs=["data"],
            agent="loader",
        )
        resp = client.get("/api/lineage/data")
        edge = resp.json()["data"]["chain"][0]
        assert "edge_id" in edge
        assert "task_id" in edge
        assert "operation" in edge
        assert "inputs" in edge
        assert "outputs" in edge
        assert "agent" in edge
        assert "timestamp" in edge


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Workflows
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestWorkflows:
    def test_list_workflows_empty(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_workflows_after_registration(self, client):
        @workflow("test_wf")
        def define(wf):
            wf.step("a", lambda i, c: 1)

        resp = client.get("/api/workflows")
        assert "test_wf" in resp.json()["data"]

    def test_execute_workflow(self, client):
        @workflow("run_me")
        def define(wf):
            wf.step("load", lambda i, c: {"x": 42})
            wf.step("compute", lambda i, c: {"y": 7})

        resp = client.post("/api/workflows/run_me", json={"context": {}})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "run_me"
        assert data["status"] == "completed"
        assert data["deterministic_ratio"] == 1.0
        assert len(data["steps"]) == 2

    def test_execute_nonexistent_workflow_404(self, client):
        resp = client.post("/api/workflows/no_such_wf", json={"context": {}})
        assert resp.status_code == 404

    def test_execute_workflow_with_context(self, client):
        received = {}

        @workflow("ctx_wf")
        def define(wf):
            def check(inputs, ctx):
                received.update(ctx)
                return "ok"
            wf.step("check", check)

        resp = client.post("/api/workflows/ctx_wf", json={
            "context": {"seed": 42, "model": "mistral"},
        })
        assert resp.status_code == 200
        assert received["seed"] == 42

    def test_workflow_step_fields(self, client):
        @workflow("fields_wf")
        def define(wf):
            wf.step("det", lambda i, c: 1, deterministic=True)
            wf.step("llm", lambda i, c: 2, deterministic=False)

        resp = client.post("/api/workflows/fields_wf", json={"context": {}})
        steps = resp.json()["data"]["steps"]
        assert steps[0]["deterministic"] is True
        assert steps[1]["deterministic"] is False
        for s in steps:
            assert "name" in s
            assert "status" in s
            assert "duration" in s


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Response Model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestApiResponse:
    def test_default_response(self):
        r = ApiResponse()
        assert r.status == "ok"
        assert r.data is None
        assert r.error == ""

    def test_response_with_data(self):
        r = ApiResponse(data={"key": "value"})
        assert r.data == {"key": "value"}

    def test_response_with_error(self):
        r = ApiResponse(status="error", error="something broke")
        assert r.status == "error"
        assert r.error == "something broke"
