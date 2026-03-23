from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import ontology as ontology_router
from dharma_swarm.ontology_runtime import (
    get_shared_registry,
    persist_shared_registry,
    reset_shared_registry,
)


def _ontology_client() -> TestClient:
    app = FastAPI()
    app.include_router(ontology_router.router)
    return TestClient(app)


@pytest.fixture()
def isolated_shared_ontology(tmp_path, monkeypatch):
    monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
    reset_shared_registry()
    yield tmp_path / "ontology.json"
    reset_shared_registry()


def test_router_reads_persisted_shared_registry_objects(isolated_shared_ontology) -> None:
    registry = get_shared_registry()
    obj, errors = registry.create_object(
        "Experiment",
        {"name": "router_exp", "status": "designed"},
        created_by="tester",
    )

    assert obj is not None
    assert errors == []

    persist_shared_registry(registry)
    reset_shared_registry()

    client = _ontology_client()
    resp = client.get("/api/ontology/objects")

    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()["data"]] == [obj.id]


def test_router_graph_runtime_counts_follow_shared_registry(isolated_shared_ontology) -> None:
    registry = get_shared_registry()
    registry.create_object(
        "Experiment",
        {"name": "graph_exp", "status": "designed"},
        created_by="tester",
    )

    persist_shared_registry(registry)
    reset_shared_registry()

    client = _ontology_client()
    resp = client.get("/api/ontology/graph")

    assert resp.status_code == 200
    nodes = {node["id"]: node for node in resp.json()["data"]["nodes"]}
    assert nodes["Experiment"]["data"]["runtimeCount"] == 1


def test_router_get_object_resolves_agent_identity_alias(
    isolated_shared_ontology,
) -> None:
    registry = get_shared_registry()
    obj, errors = registry.create_object(
        "AgentIdentity",
        {
            "name": "glm-researcher",
            "agent_slug": "glm-researcher",
            "display_name": "GLM Researcher",
            "role": "researcher",
            "status": "idle",
            "provider": "openrouter",
            "model": "z-ai/glm-5",
            "tasks_completed": 7,
            "fitness_average": 0.82,
            "last_heartbeat": "2026-03-20T00:00:00Z",
        },
        created_by="tester",
    )

    assert obj is not None
    assert errors == []

    client = _ontology_client()
    resp = client.get("/api/ontology/objects/agent_identity_ecosystem_synthesizer")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["id"] == obj.id
    assert body["name"] == "glm-researcher"
    assert body["roles"] == ["researcher"]
    assert body["tasks_completed"] == 7
    assert body["avg_quality"] == 0.82


def test_router_list_objects_supports_type_query_alias(
    isolated_shared_ontology,
) -> None:
    registry = get_shared_registry()
    experiment, experiment_errors = registry.create_object(
        "Experiment",
        {"name": "exp_alias", "status": "designed"},
        created_by="tester",
    )
    agent, agent_errors = registry.create_object(
        "AgentIdentity",
        {"name": "alias-agent", "role": "general"},
        created_by="tester",
    )

    assert experiment is not None
    assert agent is not None
    assert experiment_errors == []
    assert agent_errors == []

    client = _ontology_client()
    resp = client.get("/api/ontology/objects?type=experiment")

    assert resp.status_code == 200
    assert [item["id"] for item in resp.json()["data"]] == [experiment.id]


def test_router_list_objects_unknown_type_filter_returns_empty(
    isolated_shared_ontology,
) -> None:
    registry = get_shared_registry()
    registry.create_object(
        "Experiment",
        {"name": "unknown_filter_exp", "status": "designed"},
        created_by="tester",
    )

    client = _ontology_client()
    resp = client.get("/api/ontology/objects?type=synthesis_report")

    assert resp.status_code == 200
    assert resp.json()["data"] == []
