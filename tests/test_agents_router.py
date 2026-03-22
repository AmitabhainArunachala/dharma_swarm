from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import agents as agents_router
from dharma_swarm.models import AgentRole, AgentState, AgentStatus, ProviderType
from dharma_swarm.ontology_runtime import get_shared_registry, reset_shared_registry


class _DummySwarm:
    async def list_agents(self) -> list[AgentState]:
        return [
            AgentState(
                id="agent-1",
                name="qwen35-surgeon",
                role=AgentRole.SURGEON,
                status=AgentStatus.IDLE,
                provider="ollama",
                model="qwen3-coder:480b-cloud",
            )
        ]

    async def spawn_agent(
        self,
        *,
        name: str,
        role: AgentRole,
        model: str,
        provider_type: ProviderType,
    ) -> AgentState:
        return AgentState(
            id="agent-2",
            name=name,
            role=role,
            status=AgentStatus.STARTING,
            provider=provider_type.value,
            model=model,
        )

    async def stop_agent(self, agent_id: str) -> None:
        return None

    async def sync_agents(self, *, include_kaizenops: bool | None = None) -> list[dict]:
        return [
            {
                "agent_id": "agent-1",
                "team_id": "dharma_swarm",
                "status": "idle",
                "kaizenops_attempted": bool(include_kaizenops),
                "kaizenops_ok": not include_kaizenops,
                "communication_topics": [
                    "orchestrator.lifecycle",
                    "operator.bridge.lifecycle",
                ],
            }
        ]


class _EmptyTraceStore:
    async def get_recent(self, limit: int = 200) -> list[object]:
        return []


class _EmptyAgentRegistry:
    def load_agent(self, name: str) -> dict:
        return {}

    def get_fitness_history(self, name: str) -> list[dict]:
        return []

    def check_budget(self, name: str) -> dict:
        return {"daily_spent": 0.0, "weekly_spent": 0.0, "status": "OK"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(agents_router.router)
    return TestClient(app)


@pytest.fixture()
def isolated_shared_ontology(tmp_path, monkeypatch):
    monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
    reset_shared_registry()
    yield tmp_path / "ontology.json"
    reset_shared_registry()


def test_list_agents_includes_identity_fields(monkeypatch, isolated_shared_ontology) -> None:
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    client = _client()

    resp = client.get("/api/agents")

    assert resp.status_code == 200
    agent = resp.json()["data"][0]
    assert agent["agent_slug"] == "qwen35-surgeon"
    assert agent["display_name"] == "Qwen35 Surgeon"
    assert agent["provider"] == "ollama"
    assert agent["model_label"] == "qwen3-coder:480b-cloud"
    assert agent["model_key"] == "ollama::qwen3-coder:480b-cloud"

    registry = get_shared_registry()
    identities = registry.get_objects_by_type("AgentIdentity")
    assert len(identities) == 1
    assert identities[0].properties["agent_id"] == "agent-1"
    assert identities[0].properties["status"] == "idle"


def test_spawn_agent_passes_provider_and_model(monkeypatch, isolated_shared_ontology) -> None:
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    client = _client()

    resp = client.post(
        "/api/agents/spawn",
        json={
            "name": "qwen35-surgeon",
            "role": "surgeon",
            "provider": "ollama",
            "model": "qwen3-coder:480b-cloud",
        },
    )

    assert resp.status_code == 200
    agent = resp.json()["data"]
    assert agent["provider"] == "ollama"
    assert agent["model"] == "qwen3-coder:480b-cloud"
    assert agent["model_key"] == "ollama::qwen3-coder:480b-cloud"

    registry = get_shared_registry()
    identities = registry.get_objects_by_type("AgentIdentity")
    assert len(identities) == 1
    assert identities[0].properties["provider"] == "ollama"


def test_stop_agent_marks_ontology_identity_stopping(
    monkeypatch,
    isolated_shared_ontology,
) -> None:
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    client = _client()

    client.get("/api/agents")
    resp = client.post("/api/agents/agent-1/stop")

    assert resp.status_code == 200
    identity = get_shared_registry().get_objects_by_type("AgentIdentity")[0]
    assert identity.properties["status"] == "stopping"


def test_sync_agents_returns_contract_refresh_payload(
    monkeypatch,
    isolated_shared_ontology,
) -> None:
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    client = _client()

    resp = client.post("/api/agents/sync?include_kaizenops=true")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 1
    assert data["results"][0]["kaizenops_attempted"] is True
    assert "orchestrator.lifecycle" in data["results"][0]["communication_topics"]


def test_agent_detail_restores_dashboard_contract(
    monkeypatch,
    isolated_shared_ontology,
) -> None:
    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    monkeypatch.setattr(agents_router, "_get_trace_store", lambda: _EmptyTraceStore())
    monkeypatch.setattr(agents_router, "_get_agent_registry", lambda: _EmptyAgentRegistry())
    client = _client()

    resp = client.get("/api/agents/agent-1/detail")

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["agent"]["id"] == "agent-1"
    assert body["agent"]["name"] == "qwen35-surgeon"
    assert body["health_stats"]["total_actions"] == 0
    assert body["assigned_tasks"] == []
    assert body["fitness_history"] == []
