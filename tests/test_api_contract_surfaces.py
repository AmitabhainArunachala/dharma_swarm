from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import agents as agents_router
from api.routers import health as health_router
from api.routers import ontology as ontology_router
from dharma_swarm.models import AgentRole, AgentState, AgentStatus
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

    async def list_tasks(self) -> list[object]:
        return []


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


class _HealthyMonitor:
    async def check_health(self):
        class _Report:
            overall_status = "healthy"
            agent_health = []
            anomalies = []
            total_traces = 0
            traces_last_hour = 0
            failure_rate = 0.0
            mean_fitness = None

        return _Report()

    async def detect_anomalies(self, window_hours: float = 1):
        return []


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(health_router.router)
    app.include_router(agents_router.router)
    app.include_router(ontology_router.router)
    return TestClient(app)


@pytest.fixture()
def isolated_shared_ontology(tmp_path, monkeypatch):
    monkeypatch.setenv("DHARMA_ONTOLOGY_PATH", str(tmp_path / "ontology.json"))
    reset_shared_registry()
    yield tmp_path / "ontology.json"
    reset_shared_registry()


def test_openapi_exposes_specific_contract_models() -> None:
    app = FastAPI()
    app.include_router(health_router.router)
    app.include_router(agents_router.router)
    app.include_router(ontology_router.router)

    openapi = app.openapi()

    assert openapi["paths"]["/api/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/HealthResponse")
    assert openapi["paths"]["/api/agents/{agent_id}/detail"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("/AgentDetailResponse")
    assert openapi["paths"]["/api/ontology/objects/{obj_id}"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"].endswith("/OntologyObjectResponse")
    assert openapi["paths"]["/api/ontology/stats"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/OntologyStatsResponse")


def test_agent_detail_payload_validates_against_contract(
    monkeypatch,
    isolated_shared_ontology,
) -> None:
    from api.models import AgentDetailOut

    monkeypatch.setattr(agents_router, "_get_swarm", lambda: _DummySwarm())
    monkeypatch.setattr(agents_router, "_get_trace_store", lambda: _EmptyTraceStore())
    monkeypatch.setattr(agents_router, "_get_agent_registry", lambda: _EmptyAgentRegistry())

    client = _client()
    response = client.get("/api/agents/agent-1/detail")

    assert response.status_code == 200
    payload = response.json()["data"]
    contract = AgentDetailOut.model_validate(payload)
    assert contract.agent.id == "agent-1"
    assert contract.health_stats.total_actions == 0
    assert contract.available_roles


def test_ontology_object_payload_validates_against_contract(
    isolated_shared_ontology,
) -> None:
    from api.models import OntologyObjectOut

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
            "last_active": "2026-03-20T00:00:00Z",
        },
        created_by="tester",
    )

    assert obj is not None
    assert errors == []

    client = _client()
    response = client.get(f"/api/ontology/objects/{obj.id}")

    assert response.status_code == 200
    payload = response.json()["data"]
    contract = OntologyObjectOut.model_validate(payload)
    assert contract.id == obj.id
    assert contract.runtime_agent_id == obj.id
    assert contract.context


def test_health_payload_validates_against_contract(monkeypatch, tmp_path) -> None:
    from api.models import HealthOut

    monkeypatch.setattr(
        health_router,
        "_get_deps",
        lambda: (_DummySwarm(), _EmptyTraceStore(), _HealthyMonitor()),
    )
    monkeypatch.setenv("DHARMA_HOME", str(tmp_path / "runtime-state"))

    client = _client()
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()["data"]
    contract = HealthOut.model_validate(payload)
    assert contract.overall_status == "healthy"
