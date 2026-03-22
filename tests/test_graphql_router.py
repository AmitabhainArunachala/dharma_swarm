from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import graphql_router
from dharma_swarm.models import AgentRole, AgentState, AgentStatus
from dharma_swarm.ontology_agents import upsert_agent_identity
from dharma_swarm.ontology_runtime import get_shared_registry, reset_shared_registry


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(graphql_router.router)
    return TestClient(app)


@pytest.fixture()
def isolated_shared_ontology(tmp_path, monkeypatch):
    monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
    reset_shared_registry()
    yield tmp_path / "ontology.json"
    reset_shared_registry()


def test_graphql_agent_route_reads_shared_ontology_first(isolated_shared_ontology) -> None:
    upsert_agent_identity(
        AgentState(
            id="agent-1",
            name="qwen35-surgeon",
            role=AgentRole.SURGEON,
            status=AgentStatus.BUSY,
            provider="ollama",
            model="qwen3-coder:480b-cloud",
            tasks_completed=7,
        )
    )
    client = _client()

    resp = client.get("/graphql/agent/agent-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Qwen35 Surgeon"
    assert data["status"] == "busy"
    assert data["model_key"] == "ollama::qwen3-coder:480b-cloud"
    assert data["tasks_completed"] == 7


def test_graphql_connection_graph_reads_shared_ontology_first(
    isolated_shared_ontology,
) -> None:
    registry = get_shared_registry()
    agent, agent_errors = registry.create_object(
        "AgentIdentity",
        {
            "name": "qwen35-surgeon",
            "display_name": "Qwen35 Surgeon",
            "agent_id": "agent-graph-1",
            "agent_slug": "agent-graph-1",
            "role": "surgeon",
            "status": "busy",
        },
    )
    assert agent_errors == []
    assert agent is not None

    task, task_errors = registry.create_object(
        "TypedTask",
        {
            "title": "Patch GraphQL route",
            "status": "assigned",
            "priority": "high",
            "task_type": "build",
        },
    )
    assert task_errors == []
    assert task is not None

    link, link_errors = registry.create_link(
        "assigned_to",
        source_id=task.id,
        target_id=agent.id,
        metadata={"source": "test"},
    )
    assert link_errors == []
    assert link is not None

    client = _client()
    resp = client.get(f"/graphql/connection_graph/{task.id}?depth=2")

    assert resp.status_code == 200
    payload = resp.json()
    nodes = {node["id"]: node for node in payload["nodes"]}
    edges = payload["edges"]

    assert nodes[task.id]["type"] == "TypedTask"
    assert nodes[task.id]["label"] == "Patch GraphQL route"
    assert nodes[agent.id]["type"] == "AgentIdentity"
    assert nodes[agent.id]["label"] == "qwen35-surgeon"
    assert any(
        edge["source"] == task.id
        and edge["target"] == agent.id
        and edge["type"] == "assigned_to"
        for edge in edges
    )
    assert not any(node_id.startswith("mark:") for node_id in nodes)


def test_graphql_connection_graph_falls_back_to_stigmergy(
    isolated_shared_ontology,
    tmp_path,
    monkeypatch,
) -> None:
    marks_path = tmp_path / "stigmergy" / "marks.jsonl"
    marks_path.parent.mkdir(parents=True, exist_ok=True)
    marks_path.write_text(
        json.dumps(
            {
                "id": "mark-1",
                "agent": "agent-fallback",
                "file_path": "/tmp/work/runtime_state.py",
                "action": "inspect",
                "observation": "runtime slice needs migration",
                "semantic_type": "investigation",
                "salience": 0.91,
                "confidence": 0.87,
                "impact_score": 0.66,
                "pillar_refs": ["ontology"],
                "linked_objects": [],
                "timestamp": "2026-03-20T00:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    agents_dir = tmp_path / "ginko" / "agents"
    identity_dir = agents_dir / "agent-fallback"
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "identity.json").write_text(
        json.dumps(
            {
                "name": "Fallback Agent",
                "role": "researcher",
                "model": "gpt-5.4",
                "status": "busy",
                "last_active": "2026-03-20T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(graphql_router, "STIGMERGY_MARKS_PATH", marks_path)
    monkeypatch.setattr(graphql_router, "GINKO_AGENTS_DIR", agents_dir)

    client = _client()
    resp = client.get("/graphql/connection_graph/agent-fallback?depth=2")

    assert resp.status_code == 200
    payload = resp.json()
    nodes = {node["id"]: node for node in payload["nodes"]}
    edge_types = {edge["type"] for edge in payload["edges"]}

    assert nodes["agent-fallback"]["type"] == "agent"
    assert nodes["agent-fallback"]["label"] == "Fallback Agent"
    assert any(node["type"] == "mark" for node in payload["nodes"])
    assert any(node["type"] == "file" for node in payload["nodes"])
    assert any(node["type"] == "pillar" for node in payload["nodes"])
    assert "left_by" in edge_types
    assert "touches" in edge_types
    assert "references" in edge_types
