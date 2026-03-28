"""Git-friendly roaming mailbox for cross-harness agent task exchange.

The mailbox is intentionally simple:

- tasks live as one JSON file each under ``roaming_mailbox/tasks/``
- responses live as one JSON file each under ``roaming_mailbox/responses/``

Because the mailbox is plain files, it can be synced through git between a
local dharma_swarm checkout and a remote OpenClaw/Claude/Codex checkout.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n"


def _default_queue_root() -> Path:
    return Path(__file__).resolve().parent.parent / "roaming_mailbox"


@dataclass(frozen=True)
class MailboxTask:
    task_id: str
    recipient: str
    sender: str
    summary: str
    body: str
    status: str = "queued"
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)
    claimed_at: str = ""
    claimed_by: str = ""
    responded_at: str = ""
    response_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailboxTask:
        return cls(
            task_id=str(data.get("task_id", "")),
            recipient=str(data.get("recipient", "")),
            sender=str(data.get("sender", "")),
            summary=str(data.get("summary", "")),
            body=str(data.get("body", "")),
            status=str(data.get("status", "queued")),
            capabilities=list(data.get("capabilities") or []),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at", "")) or _utc_now_iso(),
            claimed_at=str(data.get("claimed_at", "")),
            claimed_by=str(data.get("claimed_by", "")),
            responded_at=str(data.get("responded_at", "")),
            response_ref=str(data.get("response_ref", "")),
        )


@dataclass(frozen=True)
class MailboxResponse:
    task_id: str
    responder: str
    summary: str
    body: str
    status: str = "responded"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RoamingMailbox:
    def __init__(self, queue_root: Path | None = None) -> None:
        self.queue_root = queue_root or _default_queue_root()
        self.tasks_dir = self.queue_root / "tasks"
        self.responses_dir = self.queue_root / "responses"
        self.receipts_dir = self.queue_root / "receipts"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def response_path(self, task_id: str, responder: str) -> Path:
        safe = responder.replace("/", "_").replace("\\", "_")
        return self.responses_dir / f"{task_id}.{safe}.json"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dump(payload), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _new_task_id(self) -> str:
        return f"mbx_{uuid4().hex[:16]}"

    def enqueue_task(
        self,
        *,
        recipient: str,
        sender: str,
        summary: str,
        body: str,
        capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MailboxTask:
        task = MailboxTask(
            task_id=self._new_task_id(),
            recipient=recipient,
            sender=sender,
            summary=summary,
            body=body,
            capabilities=list(capabilities or []),
            metadata=dict(metadata or {}),
        )
        self._write_json(self.task_path(task.task_id), task.to_dict())
        return task

    def load_task(self, task_id: str) -> MailboxTask:
        return MailboxTask.from_dict(self._read_json(self.task_path(task_id)))

    def list_tasks(
        self,
        *,
        recipient: str | None = None,
        status: str | None = None,
    ) -> list[MailboxTask]:
        tasks: list[MailboxTask] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            task = MailboxTask.from_dict(self._read_json(path))
            if recipient is not None and task.recipient != recipient:
                continue
            if status is not None and task.status != status:
                continue
            tasks.append(task)
        tasks.sort(key=lambda task: task.created_at)
        return tasks

    def claim_task(self, task_id: str, *, claimed_by: str) -> MailboxTask:
        task = self.load_task(task_id)
        claimed = MailboxTask(
            **{
                **task.to_dict(),
                "status": "claimed",
                "claimed_by": claimed_by,
                "claimed_at": _utc_now_iso(),
            }
        )
        self._write_json(self.task_path(task_id), claimed.to_dict())
        return claimed

    def claim_next_task(self, recipient: str) -> MailboxTask | None:
        queued = self.list_tasks(recipient=recipient, status="queued")
        if not queued:
            return None
        return self.claim_task(queued[0].task_id, claimed_by=recipient)

    def respond_to_task(
        self,
        *,
        task_id: str,
        responder: str,
        summary: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> MailboxResponse:
        response = MailboxResponse(
            task_id=task_id,
            responder=responder,
            summary=summary,
            body=body,
            metadata=dict(metadata or {}),
        )
        response_path = self.response_path(task_id, responder)
        self._write_json(response_path, response.to_dict())

        task = self.load_task(task_id)
        updated = MailboxTask(
            **{
                **task.to_dict(),
                "status": "responded",
                "responded_at": response.created_at,
                "response_ref": str(response_path),
            }
        )
        self._write_json(self.task_path(task_id), updated.to_dict())
        return response


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git-friendly roaming mailbox")
    parser.add_argument("--queue-root", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--recipient", required=True)
    enqueue.add_argument("--sender", default="dharma_swarm")
    enqueue.add_argument("--summary", required=True)
    enqueue.add_argument("--body", required=True)
    enqueue.add_argument("--capability", action="append", default=[])

    claim = sub.add_parser("claim-next")
    claim.add_argument("--recipient", required=True)

    respond = sub.add_parser("respond")
    respond.add_argument("--task-id", required=True)
    respond.add_argument("--responder", required=True)
    respond.add_argument("--summary", required=True)
    respond.add_argument("--body", required=True)

    listing = sub.add_parser("list")
    listing.add_argument("--recipient", default="")
    listing.add_argument("--status", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    mailbox = RoamingMailbox(queue_root=Path(args.queue_root) if args.queue_root else None)

    if args.command == "enqueue":
        task = mailbox.enqueue_task(
            recipient=args.recipient,
            sender=args.sender,
            summary=args.summary,
            body=args.body,
            capabilities=list(args.capability or []),
        )
        print(_json_dump(task.to_dict()).rstrip())
        return 0

    if args.command == "claim-next":
        task = mailbox.claim_next_task(args.recipient)
        print(_json_dump(task.to_dict() if task else {}).rstrip())
        return 0

    if args.command == "respond":
        response = mailbox.respond_to_task(
            task_id=args.task_id,
            responder=args.responder,
            summary=args.summary,
            body=args.body,
        )
        print(_json_dump(response.to_dict()).rstrip())
        return 0

    if args.command == "list":
        tasks = [
            task.to_dict()
            for task in mailbox.list_tasks(
                recipient=args.recipient or None,
                status=args.status or None,
            )
        ]
        print(_json_dump(tasks).rstrip())
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
