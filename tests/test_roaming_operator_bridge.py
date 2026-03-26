from __future__ import annotations

import json

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.roaming_mailbox import RoamingMailbox
from dharma_swarm.roaming_operator_bridge import RoamingOperatorBridge


@pytest.mark.asyncio
async def test_dispatch_next_claims_bridge_task_and_enqueues_mailbox_task(tmp_path) -> None:
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_roaming_dispatch",
    )
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    adapter = RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)

    queued = await bridge.enqueue_task(
        task="Research tariff changes for semiconductors",
        sender="research_director",
        scope=["research", "tariffs"],
        output=["memo"],
    )

    mailbox_task = await adapter.dispatch_next(recipient="kimi-claw-phone")

    assert mailbox_task is not None
    assert mailbox_task.recipient == "kimi-claw-phone"
    assert mailbox_task.metadata["bridge_task_id"] == queued.id

    claimed = await bridge.get_task(queued.id)
    assert claimed is not None
    assert claimed.status == "in_progress"
    assert claimed.claimed_by == "kimi-claw-phone"


@pytest.mark.asyncio
async def test_collect_response_completes_bridge_task_and_writes_receipt(tmp_path) -> None:
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_roaming_collect",
    )
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    adapter = RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)

    queued = await bridge.enqueue_task(
        task="Draft a one-paragraph market note",
        sender="quant_director",
    )
    mailbox_task = await adapter.dispatch_next(recipient="kimi-claw-phone")
    assert mailbox_task is not None

    mailbox.claim_task(mailbox_task.task_id, claimed_by="kimi-claw-phone")
    mailbox.respond_to_task(
        task_id=mailbox_task.task_id,
        responder="kimi-claw-phone",
        summary="Market note drafted",
        body=json.dumps(
            {
                "status": "completed",
                "report_path": "/tmp/kimi-market-note.md",
                "thesis": "AI infra remains in consolidation.",
            }
        ),
        metadata={"source": "openclaw_mobile"},
    )

    updated = await adapter.collect_response(
        mailbox_task_id=mailbox_task.task_id,
        responder="kimi-claw-phone",
    )

    assert updated.id == queued.id
    assert updated.status == "completed"
    assert updated.response is not None
    assert updated.response.report_path == "/tmp/kimi-market-note.md"
    assert updated.response.metadata["mailbox_task_id"] == mailbox_task.task_id
    assert updated.response.metadata["roaming_responder"] == "kimi-claw-phone"

    sender_msgs = await bus.receive("quant_director")
    assert len(sender_msgs) == 1
    assert sender_msgs[0].metadata["bridge_task_id"] == queued.id

    receipt_path = mailbox.receipts_dir / f"{mailbox_task.task_id}.kimi-claw-phone.imported.json"
    assert receipt_path.exists()
