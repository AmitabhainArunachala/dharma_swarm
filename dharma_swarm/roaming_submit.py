"""Operator-facing targeted task submission for roaming workers."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge


def _json_load(raw: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


async def submit_roaming_task(
    *,
    db_path: Path,
    recipient: str,
    task: str,
    sender: str = "operator",
    scope: list[str] | None = None,
    output: list[str] | None = None,
    constraints: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    ledger_dir: Path | None = None,
) -> dict[str, Any]:
    bus = MessageBus(db_path)
    bridge = OperatorBridge(message_bus=bus, ledger_dir=ledger_dir)
    merged_payload = dict(payload or {})
    merged_payload.setdefault("target_agent", recipient)
    merged_metadata = dict(metadata or {})
    merged_metadata.setdefault("target_agent", recipient)
    merged_metadata.setdefault("routing_mode", "roaming_targeted")
    queued = await bridge.enqueue_task(
        task=task,
        sender=sender,
        scope=list(scope or []),
        output=list(output or []),
        constraints=list(constraints or []),
        payload=merged_payload,
        metadata=merged_metadata,
    )
    return {
        "bridge_task_id": queued.id,
        "recipient": recipient,
        "sender": sender,
        "task": task,
        "status": queued.status,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Submit a targeted roaming task.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--ledger-dir", default="")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--sender", default="operator")
    parser.add_argument("--task", required=True)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--metadata-json", default="{}")
    return parser


async def _main_async(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = await submit_roaming_task(
        db_path=Path(args.db_path),
        ledger_dir=Path(args.ledger_dir) if args.ledger_dir else None,
        recipient=args.recipient,
        sender=args.sender,
        task=args.task,
        scope=list(args.scope or []),
        output=list(args.output or []),
        constraints=list(args.constraint or []),
        payload=_json_load(args.payload_json),
        metadata=_json_load(args.metadata_json),
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
