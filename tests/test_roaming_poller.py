from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm.roaming_mailbox import RoamingMailbox
from dharma_swarm.roaming_poller import RoamingPoller


def _write_responder_script(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os

task = json.loads(os.environ["ROAMING_TASK_JSON"])
payload = {
    "summary": f"Handled {task['task_id']}",
    "body": json.dumps(
        {
            "callsign": os.environ["ROAMING_RESPONDER"],
            "task_id": task["task_id"],
            "summary": task["summary"],
        }
    ),
    "metadata": {"mode": "test"},
}
print(json.dumps(payload))
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_process_once_claims_and_responds(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    task = mailbox.enqueue_task(
        recipient="kimi-claw-phone",
        sender="dharma_swarm",
        summary="Ping",
        body="return status",
        capabilities=["research"],
    )
    responder = tmp_path / "responder.py"
    _write_responder_script(responder)

    poller = RoamingPoller(
        mailbox=mailbox,
        recipient="kimi-claw-phone",
        responder="kimi-claw-phone",
        command=["python3", str(responder)],
    )

    result = poller.process_once()
    updated = mailbox.load_task(task.task_id)
    response_path = mailbox.response_path(task.task_id, "kimi-claw-phone")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    heartbeat = mailbox.load_heartbeat("kimi-claw-phone")

    assert result is not None
    assert result.task_id == task.task_id
    assert updated.status == "responded"
    assert updated.claimed_by == "kimi-claw-phone"
    assert response["summary"] == f"Handled {task.task_id}"
    assert json.loads(response["body"])["callsign"] == "kimi-claw-phone"
    assert heartbeat is not None
    assert heartbeat.status == "idle"
    assert heartbeat.summary == f"Completed {task.task_id}"


def test_process_once_returns_none_when_no_work(tmp_path: Path) -> None:
    mailbox = RoamingMailbox(queue_root=tmp_path / "mailbox")
    responder = tmp_path / "responder.py"
    _write_responder_script(responder)

    poller = RoamingPoller(
        mailbox=mailbox,
        recipient="kimi-claw-phone",
        responder="kimi-claw-phone",
        command=["python3", str(responder)],
        heartbeat_interval_seconds=60.0,
    )

    assert poller.process_once() is None
    heartbeat = mailbox.load_heartbeat("kimi-claw-phone")
    assert heartbeat is not None
    assert heartbeat.status == "idle"
    assert heartbeat.summary == "Polling for work"
