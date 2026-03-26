from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm.roaming_mailbox import RoamingMailbox


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_enqueue_task_persists_queue_record(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")

    task = mailbox.enqueue_task(
        recipient="kimi-claw-phone",
        sender="dharma_swarm",
        summary="Ping",
        body="Return one-line status.",
        capabilities=["research"],
    )

    task_path = mailbox.task_path(task.task_id)
    assert task.status == "queued"
    assert task_path.exists()

    stored = _load_json(task_path)
    assert stored["recipient"] == "kimi-claw-phone"
    assert stored["summary"] == "Ping"
    assert stored["capabilities"] == ["research"]


def test_claim_next_task_prefers_oldest_queued_for_recipient(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    first = mailbox.enqueue_task(
        recipient="kimi-claw-phone",
        sender="dharma_swarm",
        summary="First",
        body="first body",
    )
    mailbox.enqueue_task(
        recipient="other-agent",
        sender="dharma_swarm",
        summary="Other",
        body="other body",
    )
    second = mailbox.enqueue_task(
        recipient="kimi-claw-phone",
        sender="dharma_swarm",
        summary="Second",
        body="second body",
    )

    claimed = mailbox.claim_next_task("kimi-claw-phone")

    assert claimed is not None
    assert claimed.task_id == first.task_id
    assert claimed.status == "claimed"
    assert claimed.claimed_by == "kimi-claw-phone"
    assert mailbox.load_task(second.task_id).status == "queued"


def test_respond_to_task_writes_response_and_updates_task(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    task = mailbox.enqueue_task(
        recipient="kimi-claw-phone",
        sender="dharma_swarm",
        summary="Status request",
        body="Return JSON status.",
    )
    mailbox.claim_task(task.task_id, claimed_by="kimi-claw-phone")

    response = mailbox.respond_to_task(
        task_id=task.task_id,
        responder="kimi-claw-phone",
        summary="Ready",
        body='{"status":"online"}',
    )

    task_after = mailbox.load_task(task.task_id)
    response_path = mailbox.response_path(task.task_id, "kimi-claw-phone")

    assert response_path.exists()
    assert response.status == "responded"
    assert task_after.status == "responded"
    assert task_after.response_ref == str(response_path)


def test_write_heartbeat_persists_presence_record(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")

    heartbeat = mailbox.write_heartbeat(
        agent_id="kimi-claw-phone",
        callsign="kimi-claw-phone",
        status="working",
        summary="Handling trade memo",
        current_task_id="mbx_123",
        progress=0.4,
        metadata={"provider": "moonshot"},
    )

    stored = mailbox.load_heartbeat("kimi-claw-phone")
    assert stored is not None
    assert heartbeat.agent_id == "kimi-claw-phone"
    assert stored.status == "working"
    assert stored.current_task_id == "mbx_123"
    assert stored.progress == 0.4
    assert stored.metadata["provider"] == "moonshot"
