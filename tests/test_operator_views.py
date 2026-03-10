from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.operator_views import OperatorViews
from dharma_swarm.runtime_state import RuntimeStateStore


@pytest.mark.asyncio
async def test_operator_views_surface_bridge_queue_and_runtime_overview(tmp_path) -> None:
    bus = MessageBus(tmp_path / "bridge.db")
    runtime_state = RuntimeStateStore(tmp_path / "runtime.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_views",
        runtime_state=runtime_state,
    )
    await bridge.init_db()
    record = await bridge.enqueue_task(
        task="Surface queue state in operator cockpit",
        sender="operator",
    )
    await bridge.claim_task(claimed_by="codex-runner", task_id=record.id)
    await bridge.acknowledge_task_claim(
        task_id=record.id,
        acknowledged_by="codex-runner",
    )
    await bridge.heartbeat_task(
        task_id=record.id,
        heartbeat_by="codex-runner",
        summary="working",
        progress=0.25,
    )
    await bridge.respond_task(
        task_id=record.id,
        status="done",
        summary="Delivered.",
        metadata={"ack_timeout_seconds": 1},
    )

    views = OperatorViews(runtime_state, bridge=bridge)
    queue = await views.bridge_queue(
        limit=10,
        now=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    overview = await views.runtime_overview(session_id="sess_views")
    overdue = await views.overdue_response_acks(
        limit=10,
        now=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    actions = await views.recent_operator_actions(session_id="sess_views", limit=10)

    assert len(queue) == 1
    assert queue[0].task_id == record.id
    assert queue[0].has_claim_ack is True
    assert queue[0].overdue_response_ack is True
    assert queue[0].last_heartbeat_at is not None
    assert len(overdue) == 1
    assert overdue[0].task_id == record.id
    assert overview.sessions == 1
    assert overview.claims == 1
    assert overview.runs == 1
    assert overview.operator_actions >= 4
    assert any(action["action_name"] == "bridge_task_responded" for action in actions)
