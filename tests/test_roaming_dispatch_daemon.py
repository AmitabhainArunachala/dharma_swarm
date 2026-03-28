from __future__ import annotations

import json

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.roaming_mailbox import RoamingMailbox
from dharma_swarm.roaming_operator_bridge import RoamingOperatorBridge


@pytest.mark.asyncio
async def test_dispatch_daemon_cycles_dispatch_then_collect(tmp_path) -> None:
    from dharma_swarm.roaming_dispatch_daemon import RoamingDispatchDaemon

    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_roaming_daemon",
    )
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    adapter = RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)
    daemon = RoamingDispatchDaemon(
        adapter=adapter,
        recipient="kimi-claw-phone",
        responder="kimi-claw-phone",
        dispatch_limit=1,
    )

    queued = await bridge.enqueue_task(
        task="Draft a trade-risk memo",
        sender="quant_director",
    )

    first = await daemon.cycle_once()

    assert len(first.dispatched_mailbox_task_ids) == 1
    assert first.collected_bridge_task_ids == []

    mailbox_task_id = first.dispatched_mailbox_task_ids[0]
    mailbox.claim_task(mailbox_task_id, claimed_by="kimi-claw-phone")
    mailbox.respond_to_task(
        task_id=mailbox_task_id,
        responder="kimi-claw-phone",
        summary="Trade-risk memo drafted",
        body=json.dumps({"status": "completed", "report_path": "/tmp/trade-risk.md"}),
    )

    second = await daemon.cycle_once()

    assert second.dispatched_mailbox_task_ids == []
    assert second.collected_bridge_task_ids == [queued.id]

    updated = await bridge.get_task(queued.id)
    assert updated is not None
    assert updated.status == "completed"
    assert updated.response is not None
    assert updated.response.report_path == "/tmp/trade-risk.md"
