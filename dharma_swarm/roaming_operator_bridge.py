"""Bridge real OperatorBridge work orders into the roaming mailbox.

This keeps the git-backed mailbox as a transport, not a second task system.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge, OperatorBridgeTask
from dharma_swarm.roaming_mailbox import MailboxResponse, MailboxTask, RoamingMailbox


def _safe_body(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        return {"mailbox_body": raw}
    if isinstance(data, dict):
        return dict(data)
    return {"mailbox_body": raw}


class RoamingOperatorBridge:
    """Adapts canonical operator tasks to roaming mailbox transport."""

    def __init__(
        self,
        *,
        bridge: OperatorBridge,
        mailbox: RoamingMailbox,
    ) -> None:
        self.bridge = bridge
        self.mailbox = mailbox

    def _receipt_path(self, *, task_id: str, responder: str) -> Path:
        safe = responder.replace("/", "_").replace("\\", "_")
        return self.mailbox.receipts_dir / f"{task_id}.{safe}.imported.json"

    async def dispatch_next(self, *, recipient: str) -> MailboxTask | None:
        claimed = await self.bridge.claim_task(claimed_by=recipient)
        if claimed is None:
            return None
        return self.mailbox.enqueue_task(
            recipient=recipient,
            sender=claimed.sender,
            summary=claimed.task,
            body=claimed.render_work_order(),
            capabilities=list(claimed.scope),
            metadata={
                "bridge_task_id": claimed.id,
                "bridge_status": claimed.status,
                "request_message_id": claimed.request_message_id or "",
                "bridge_payload": claimed.payload,
                "bridge_constraints": list(claimed.constraints),
                "bridge_output": list(claimed.output),
            },
        )

    async def collect_response(
        self,
        *,
        mailbox_task_id: str,
        responder: str,
    ) -> OperatorBridgeTask:
        task = self.mailbox.load_task(mailbox_task_id)
        response_path = self.mailbox.response_path(mailbox_task_id, responder)
        response = MailboxResponse(**json.loads(response_path.read_text(encoding="utf-8")))

        receipt_path = self._receipt_path(task_id=mailbox_task_id, responder=responder)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            bridge_task_id = str(receipt.get("bridge_task_id", ""))
            if bridge_task_id:
                existing = await self.bridge.get_task(bridge_task_id)
                if existing is not None:
                    return existing

        bridge_task_id = str(task.metadata.get("bridge_task_id", "")).strip()
        if not bridge_task_id:
            raise ValueError(f"Mailbox task {mailbox_task_id} is missing bridge_task_id")

        parsed = _safe_body(response.body)
        status = str(
            response.metadata.get("status")
            or parsed.get("status")
            or "completed"
        )
        report_path = response.metadata.get("report_path") or parsed.get("report_path")
        patch_path = response.metadata.get("patch_path") or parsed.get("patch_path")
        error = response.metadata.get("error") or parsed.get("error")

        metadata = {
            "mailbox_task_id": task.task_id,
            "mailbox_response_path": str(response_path),
            "mailbox_sender": task.sender,
            "mailbox_summary": response.summary,
            "mailbox_body": response.body,
            "mailbox_metadata": response.metadata,
            "roaming_responder": responder,
        }
        updated = await self.bridge.respond_task(
            task_id=bridge_task_id,
            status=status,
            summary=response.summary,
            claimed_by=responder,
            report_path=str(report_path) if report_path else None,
            patch_path=str(patch_path) if patch_path else None,
            error=str(error) if error else None,
            metadata=metadata,
        )

        receipt_path.write_text(
            json.dumps(
                {
                    "mailbox_task_id": mailbox_task_id,
                    "bridge_task_id": bridge_task_id,
                    "responder": responder,
                    "bridge_status": updated.status,
                    "response_message_id": (
                        updated.response.response_message_id
                        if updated.response is not None
                        else None
                    ),
                },
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return updated


def _build_bridge(*, db_path: Path, mailbox_root: Path | None, ledger_dir: Path | None) -> RoamingOperatorBridge:
    bus = MessageBus(db_path)
    bridge = OperatorBridge(message_bus=bus, ledger_dir=ledger_dir)
    mailbox = RoamingMailbox(queue_root=mailbox_root)
    return RoamingOperatorBridge(bridge=bridge, mailbox=mailbox)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge OperatorBridge tasks into the roaming mailbox.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--mailbox-root", default="")
    parser.add_argument("--ledger-dir", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    dispatch = sub.add_parser("dispatch-next")
    dispatch.add_argument("--recipient", required=True)

    collect = sub.add_parser("collect-response")
    collect.add_argument("--mailbox-task-id", required=True)
    collect.add_argument("--responder", required=True)
    return parser


async def _main_async(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    adapter = _build_bridge(
        db_path=Path(args.db_path),
        mailbox_root=Path(args.mailbox_root) if args.mailbox_root else None,
        ledger_dir=Path(args.ledger_dir) if args.ledger_dir else None,
    )
    if args.command == "dispatch-next":
        task = await adapter.dispatch_next(recipient=args.recipient)
        print(json.dumps(None if task is None else task.to_dict(), indent=2, ensure_ascii=True))
        return 0
    if args.command == "collect-response":
        result = await adapter.collect_response(
            mailbox_task_id=args.mailbox_task_id,
            responder=args.responder,
        )
        print(
            json.dumps(
                {
                    "bridge_task_id": result.id,
                    "status": result.status,
                    "summary": result.response.summary if result.response else "",
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0
    parser.error("unknown command")
    return 2


def main(argv: list[str] | None = None) -> int:
    import asyncio

    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
