from __future__ import annotations

import json

import httpx
import pytest

from dharma_swarm.contracts.intelligence_agents import (
    agent_state_to_team_roster,
    agent_state_to_telemetry_identity,
    agent_registration_to_kaizenops_events,
    sync_live_agent_registration,
)
from dharma_swarm.integrations import KaizenOpsClient, KaizenOpsConfig
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import AgentRole, AgentState, AgentStatus
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


def _agent_state() -> AgentState:
    return AgentState(
        id="agent-runtime-1",
        name="qwen35-surgeon",
        role=AgentRole.SURGEON,
        status=AgentStatus.IDLE,
        provider="ollama",
        model="qwen3-coder",
        tasks_completed=3,
    )


def _glm_agent_state() -> AgentState:
    return AgentState(
        id="agent-runtime-glm",
        name="glm5-cartographer",
        role=AgentRole.CARTOGRAPHER,
        status=AgentStatus.IDLE,
        provider="openrouter",
        model="z-ai/glm-5",
        tasks_completed=7,
    )


def test_agent_registration_to_kaizenops_events_includes_identity_and_roster() -> None:
    telemetry_identity_result = pytest.importorskip("dharma_swarm.contracts.intelligence_agents")
    identity = telemetry_identity_result.agent_state_to_telemetry_identity(
        _agent_state(),
        thread="architectural",
        metadata={"team_id": "dharma-core"},
    )
    roster = telemetry_identity_result.agent_state_to_team_roster(
        _agent_state(),
        thread="architectural",
        metadata={"team_id": "dharma-core"},
    )

    events = agent_registration_to_kaizenops_events(identity, roster)

    assert len(events) == 2
    assert events[0]["category"] == "agent_registry"
    assert events[0]["metadata"]["team_id"] == "dharma-core"
    assert events[1]["intent"] == "assign_agent_to_team"
    assert events[1]["raw_payload"]["identity"]["agent_id"] == "qwen35-surgeon"


def test_certified_lane_registration_flows_into_identity_and_kaizenops_events() -> None:
    identity = agent_state_to_telemetry_identity(
        _glm_agent_state(),
        thread="research",
        metadata={"team_id": "dharma-core"},
    )
    roster = agent_state_to_team_roster(
        _glm_agent_state(),
        thread="research",
        metadata={"team_id": "dharma-core"},
    )

    events = agent_registration_to_kaizenops_events(identity, roster)

    assert identity.codename == "glm-researcher"
    assert identity.metadata["registered_lane_id"] == "lane:glm-researcher"
    assert identity.metadata["registered_lane_profile_id"] == "glm5_researcher"
    assert identity.metadata["registered_lane_label"] == "GLM-5 Cartographer"
    assert events[0]["metadata"]["registered_lane_id"] == "lane:glm-researcher"
    assert events[0]["metadata"]["registered_lane_codename"] == "glm-researcher"
    assert events[1]["metadata"]["registered_lane_profile_id"] == "glm5_researcher"


@pytest.mark.asyncio
async def test_sync_live_agent_registration_records_telemetry_and_posts_kaizenops(
    tmp_path,
) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    await telemetry.init_db()
    bus = MessageBus(tmp_path / "message_bus.db")
    await bus.init_db()
    await bus.subscribe("qwen35-surgeon", "orchestrator.lifecycle")
    await bus.subscribe("qwen35-surgeon", "operator.bridge.lifecycle")
    await bus.heartbeat("qwen35-surgeon", metadata={"role": "surgeon"})

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert request.url.path == "/v1/ingest/events"
        assert len(payload["events"]) == 2
        assert payload["events"][0]["metadata"]["team_id"] == "dharma-core"
        return httpx.Response(200, json={"accepted": len(payload["events"])})

    client = KaizenOpsClient(
        config=KaizenOpsConfig(base_url="http://kaizen.local"),
        transport=httpx.MockTransport(_handler),
    )

    result = await sync_live_agent_registration(
        _agent_state(),
        telemetry=telemetry,
        thread="architectural",
        metadata={"team_id": "dharma-core", "department": "operators"},
        message_bus=bus,
        include_kaizenops=True,
        kaizen_client=client,
    )

    stored_identity = await telemetry.get_agent_identity("qwen35-surgeon")
    roster = await telemetry.list_team_roster(team_id="dharma-core", limit=10)

    assert stored_identity is not None
    assert stored_identity.department == "operators"
    assert stored_identity.metadata["communication_ready"] is True
    assert stored_identity.metadata["bus_status"] == "online"
    assert stored_identity.metadata["missing_topics"] == []
    assert roster[0].agent_id == "qwen35-surgeon"
    assert result.kaizenops_attempted is True
    assert result.kaizenops_ok is True
    assert result.kaizenops_response == {"accepted": 2}
    assert result.as_dict()["communication_ready"] is True


@pytest.mark.asyncio
async def test_sync_live_agent_registration_does_not_claim_bus_readiness_without_presence(
    tmp_path,
) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    await telemetry.init_db()

    result = await sync_live_agent_registration(
        _agent_state(),
        telemetry=telemetry,
        thread="architectural",
        metadata={"team_id": "dharma-core", "department": "operators"},
        include_kaizenops=False,
    )

    stored_identity = await telemetry.get_agent_identity("qwen35-surgeon")

    assert stored_identity is not None
    assert stored_identity.metadata["communication_ready"] is False
    assert stored_identity.metadata["bus_status"] == "unavailable"
    assert set(stored_identity.metadata["missing_topics"]) == {
        "orchestrator.lifecycle",
        "operator.bridge.lifecycle",
    }
    assert result.as_dict()["communication_ready"] is False
    assert result.as_dict()["bus_status"] == "unavailable"


@pytest.mark.asyncio
async def test_sync_live_agent_registration_reports_certified_lane_metadata(
    tmp_path,
) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    await telemetry.init_db()

    result = await sync_live_agent_registration(
        _glm_agent_state(),
        telemetry=telemetry,
        thread="research",
        metadata={"team_id": "dharma-core"},
        include_kaizenops=False,
    )

    stored_identity = await telemetry.get_agent_identity("glm5-cartographer")

    assert stored_identity is not None
    assert stored_identity.codename == "glm-researcher"
    assert stored_identity.metadata["registered_lane_id"] == "lane:glm-researcher"
    assert result.as_dict()["registered_lane_profile_id"] == "glm5_researcher"
