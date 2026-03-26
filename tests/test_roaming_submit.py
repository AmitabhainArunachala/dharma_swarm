from __future__ import annotations

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.roaming_operator_bridge import RoamingOperatorBridge
from dharma_swarm.roaming_submit import submit_roaming_task
from dharma_swarm.roaming_mailbox import RoamingMailbox


@pytest.mark.asyncio
async def test_submit_roaming_task_targets_recipient(tmp_path) -> None:
    result = await submit_roaming_task(
        db_path=tmp_path / "bridge.db",
        ledger_dir=tmp_path / "ledgers",
        recipient="kimi-claw-phone",
        sender="operator",
        task="Draft a one-line market view",
        payload={"priority": "high"},
    )

    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(message_bus=bus, ledger_dir=tmp_path / "ledgers")
    queued = await bridge.get_task(result["bridge_task_id"])
    assert queued is not None
    assert queued.payload["target_agent"] == "kimi-claw-phone"
    assert queued.metadata["routing_mode"] == "roaming_targeted"


@pytest.mark.asyncio
async def test_dispatch_next_skips_tasks_targeted_to_other_agent(tmp_path) -> None:
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(message_bus=bus, ledger_dir=tmp_path / "ledgers")
    await bridge.init_db()
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    adapter = RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)

    other = await bridge.enqueue_task(
        task="For Hermes only",
        sender="operator",
        payload={"target_agent": "hermes-vps"},
    )
    kimi = await bridge.enqueue_task(
        task="For Kimi",
        sender="operator",
        payload={"target_agent": "kimi-claw-phone"},
    )

    mailbox_task = await adapter.dispatch_next(recipient="kimi-claw-phone")

    assert mailbox_task is not None
    assert mailbox_task.metadata["bridge_task_id"] == kimi.id
    other_task = await bridge.get_task(other.id)
    kimi_task = await bridge.get_task(kimi.id)
    assert other_task is not None
    assert other_task.status == "queued"
    assert kimi_task is not None
    assert kimi_task.status == "in_progress"
