from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.roaming_mailbox import RoamingMailbox
from dharma_swarm.roaming_onboarding import RoamingAgentRegistration, onboard_roaming_agent
from dharma_swarm.roaming_operator_bridge import RoamingOperatorBridge
from dharma_swarm.roaming_presence import RoamingPresenceProjector
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


@pytest.mark.asyncio
async def test_project_presence_updates_canonical_surfaces(tmp_path: Path) -> None:
    dharma_home = tmp_path / "dharma"
    telemetry_db = dharma_home / "state" / "runtime.db"
    await onboard_roaming_agent(
        RoamingAgentRegistration(
            callsign="kimi-claw-phone",
            harness="openclaw_mobile",
            role="analyst",
            department="research",
            model="moonshotai/kimi-k2.5",
            provider="moonshot",
        ),
        dharma_home=dharma_home,
        telemetry_db_path=telemetry_db,
    )

    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_roaming_presence",
        telemetry=TelemetryPlaneStore(telemetry_db),
    )
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    mailbox.write_heartbeat(
        agent_id="kimi-claw-phone",
        callsign="kimi-claw-phone",
        status="working",
        summary="Reviewing task",
        current_task_id="",
        progress=0.5,
        metadata={"provider": "moonshot"},
    )

    projector = RoamingPresenceProjector(
        mailbox=mailbox,
        bridge=bridge,
        dharma_home=dharma_home,
        telemetry=TelemetryPlaneStore(telemetry_db),
    )

    results = await projector.project_all()

    assert [item.agent_id for item in results] == ["kimi-claw-phone"]

    living_agent = json.loads(
        (dharma_home / "agents" / "kimi-claw-phone" / "living_agent.json").read_text(encoding="utf-8")
    )
    assert living_agent["status"] == "working"
    assert living_agent["metadata"]["last_roaming_heartbeat"]["summary"] == "Reviewing task"

    card = json.loads(
        (dharma_home / "a2a" / "cards" / "kimi-claw-phone.json").read_text(encoding="utf-8")
    )
    assert card["status"] == "working"

    telemetry = TelemetryPlaneStore(telemetry_db)
    identity = await telemetry.get_agent_identity("kimi-claw-phone")
    assert identity is not None
    assert identity.status == "working"

    status = await bus.get_agent_status("kimi-claw-phone")
    assert status is not None
    assert status["status"] == "online"
    assert status["metadata"]["source"] == "roaming_mailbox"


@pytest.mark.asyncio
async def test_project_presence_heartbeats_bridge_task_when_working(tmp_path: Path) -> None:
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_roaming_presence_bridge",
    )
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    adapter = RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)
    queued = await bridge.enqueue_task(
        task="Draft a risk memo",
        sender="quant_director",
    )
    mailbox_task = await adapter.dispatch_next(recipient="kimi-claw-phone")
    assert mailbox_task is not None
    mailbox.write_heartbeat(
        agent_id="kimi-claw-phone",
        callsign="kimi-claw-phone",
        status="working",
        summary="Halfway done",
        current_task_id=mailbox_task.task_id,
        progress=0.5,
    )

    projector = RoamingPresenceProjector(
        mailbox=mailbox,
        bridge=bridge,
        dharma_home=tmp_path / "dharma",
    )
    await projector.project_all()

    updated = await bridge.get_task(queued.id)
    assert updated is not None
    last_heartbeat = updated.metadata.get("last_heartbeat", {})
    assert last_heartbeat.get("heartbeat_by") == "kimi-claw-phone"
    assert last_heartbeat.get("summary") == "Halfway done"
