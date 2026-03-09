"""Tests for the canonical operator bridge lifecycle."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import (
    BRIDGE_STATUS_IN_PROGRESS,
    BRIDGE_STATUS_QUEUED,
    OperatorBridge,
)


def _read_events(path):
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


@pytest.fixture
async def bridge_env(tmp_path):
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_bridge",
    )
    await bridge.init_db()
    return bridge, bus, tmp_path / "ledgers" / "sess_bridge"


@pytest.mark.asyncio
async def test_enqueue_task_persists_queue_state_and_bus_notifications(bridge_env):
    bridge, bus, ledger_dir = bridge_env
    await bus.subscribe("watcher-1", "operator.bridge.lifecycle")

    record = await bridge.enqueue_task(
        task="Investigate queue semantics",
        sender="openclaw",
        scope=["dharma_swarm"],
        output=["patch", "report"],
        constraints=["non-destructive"],
        payload={"priority": "high"},
    )

    assert record.status == BRIDGE_STATUS_QUEUED
    assert record.request_message_id is not None

    bridge_inbox = await bus.receive("operator_bridge")
    assert len(bridge_inbox) == 1
    assert bridge_inbox[0].metadata["bridge_task_id"] == record.id
    assert "## Scope" in bridge_inbox[0].body

    watcher_msgs = await bus.receive("watcher-1")
    assert len(watcher_msgs) == 1
    assert watcher_msgs[0].metadata["bridge_event"] == "bridge_task_enqueued"

    task_events = _read_events(ledger_dir / "task_ledger.jsonl")
    assert task_events[-1]["event"] == "bridge_task_enqueued"


@pytest.mark.asyncio
async def test_claim_task_claims_oldest_queued_record(bridge_env):
    bridge, _, ledger_dir = bridge_env
    first = await bridge.enqueue_task(task="first task", sender="openclaw")
    second = await bridge.enqueue_task(task="second task", sender="openclaw")

    claimed = await bridge.claim_task(claimed_by="codex-runner")

    assert claimed is not None
    assert claimed.id == first.id
    assert claimed.status == BRIDGE_STATUS_IN_PROGRESS
    assert claimed.claimed_by == "codex-runner"
    assert claimed.claimed_at is not None

    remaining = await bridge.list_tasks(status=BRIDGE_STATUS_QUEUED)
    assert [task.id for task in remaining] == [second.id]

    task_events = _read_events(ledger_dir / "task_ledger.jsonl")
    assert task_events[-1]["event"] == "bridge_task_claimed"


@pytest.mark.asyncio
async def test_recover_stale_tasks_requeues_claimed_work(bridge_env):
    bridge, _, ledger_dir = bridge_env
    record = await bridge.enqueue_task(
        task="recover me",
        sender="openclaw",
        claim_timeout_seconds=60,
    )
    claimed_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    claimed = await bridge.claim_task(claimed_by="codex-runner", task_id=record.id, now=claimed_at)

    assert claimed is not None

    recovered = await bridge.recover_stale_tasks(now=datetime.now(timezone.utc))
    assert len(recovered) == 1
    assert recovered[0].id == record.id
    assert recovered[0].status == BRIDGE_STATUS_QUEUED
    assert recovered[0].retry_count == 1
    assert recovered[0].claimed_by is None
    assert recovered[0].recovery_reason is not None
    assert "stale after" in recovered[0].recovery_reason

    task_events = _read_events(ledger_dir / "task_ledger.jsonl")
    assert task_events[-1]["event"] == "bridge_task_recovered"


@pytest.mark.asyncio
async def test_respond_task_sends_reply_to_sender_and_records_progress(bridge_env):
    bridge, bus, ledger_dir = bridge_env
    record = await bridge.enqueue_task(task="respond to me", sender="openclaw")
    await bridge.claim_task(claimed_by="codex-runner", task_id=record.id)

    responded = await bridge.respond_task(
        task_id=record.id,
        status="done",
        summary="Implemented the requested change.",
        report_path="/tmp/report.md",
    )

    assert responded.status == "done"
    assert responded.completed_at is not None
    assert responded.response is not None
    assert responded.response.response_message_id is not None
    assert responded.response.metadata["responded_by"] == "codex-runner"
    assert responded.response.metadata["require_delivery_ack"] is True
    assert responded.response.metadata["ack_deadline_at"]

    sender_msgs = await bus.receive("openclaw")
    assert len(sender_msgs) == 1
    assert sender_msgs[0].reply_to == record.request_message_id
    assert sender_msgs[0].metadata["bridge_task_id"] == record.id
    assert sender_msgs[0].metadata["report_path"] == "/tmp/report.md"
    assert sender_msgs[0].from_agent == "codex-runner"

    task_events = _read_events(ledger_dir / "task_ledger.jsonl")
    progress_events = _read_events(ledger_dir / "progress_ledger.jsonl")
    assert task_events[-1]["event"] == "bridge_task_responded"
    assert progress_events[-1]["event"] == "bridge_response_emitted"


@pytest.mark.asyncio
async def test_acknowledge_response_marks_delivery_and_emits_events(bridge_env):
    bridge, _, ledger_dir = bridge_env
    record = await bridge.enqueue_task(task="ack me", sender="openclaw")
    await bridge.claim_task(claimed_by="codex-runner", task_id=record.id)
    await bridge.respond_task(
        task_id=record.id,
        status="done",
        summary="Completed.",
    )

    updated = await bridge.acknowledge_response(
        task_id=record.id,
        acknowledged_by="operator",
        note="received",
    )

    delivery_ack = updated.metadata.get("delivery_ack")
    assert isinstance(delivery_ack, dict)
    assert delivery_ack["acknowledged_by"] == "operator"
    assert delivery_ack["note"] == "received"

    task_events = _read_events(ledger_dir / "task_ledger.jsonl")
    progress_events = _read_events(ledger_dir / "progress_ledger.jsonl")
    assert task_events[-1]["event"] == "bridge_response_acknowledged"
    assert progress_events[-1]["event"] == "bridge_response_acknowledged"


@pytest.mark.asyncio
async def test_list_unacknowledged_responses_only_returns_overdue(bridge_env):
    bridge, _, _ = bridge_env
    record = await bridge.enqueue_task(task="await ack", sender="openclaw")
    await bridge.claim_task(claimed_by="codex-runner", task_id=record.id)
    await bridge.respond_task(
        task_id=record.id,
        status="done",
        summary="Delivered.",
        metadata={"ack_timeout_seconds": 1},
    )

    pending = await bridge.list_unacknowledged_responses(
        now=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    assert [p.id for p in pending] == [record.id]

    await bridge.acknowledge_response(task_id=record.id, acknowledged_by="operator")
    pending_after_ack = await bridge.list_unacknowledged_responses(
        now=datetime.now(timezone.utc) + timedelta(seconds=5),
    )
    assert pending_after_ack == []
