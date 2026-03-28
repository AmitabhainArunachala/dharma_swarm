#!/usr/bin/env python3
"""Rebind live cybernetics directive tasks to the persistent cyber-* steward seats."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from dharma_swarm.models import TaskStatus
from dharma_swarm.task_board import TaskBoard
from dharma_swarm.thinkodynamic_director import CYBERNETICS_STEWARD_AGENTS


STATE_DIR = Path.home() / ".dharma"
TASK_DB = STATE_DIR / "db" / "tasks.db"

CYBERNETICS_BACKENDS = ["provider-fallback", "codex-cli", "claude-cli"]
CYBERNETICS_PROVIDER_ALLOWLIST = ["ollama"]


def _refreshed_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    updated = dict(metadata)
    key = str(updated.get("director_task_key", "")).strip()
    if key in CYBERNETICS_STEWARD_AGENTS:
        updated["director_preferred_agents"] = list(CYBERNETICS_STEWARD_AGENTS[key])
    updated["director_preferred_backends"] = list(CYBERNETICS_BACKENDS)
    updated["available_provider_types"] = list(CYBERNETICS_PROVIDER_ALLOWLIST)
    updated.pop("active_claim", None)
    return updated


async def _amain(*, requeue_stale_running: bool) -> int:
    board = TaskBoard(TASK_DB)
    await board.init_db()

    changed: list[tuple[str, str, str]] = []
    pending = await board.list_tasks(status=TaskStatus.PENDING, limit=500)
    running = await board.list_tasks(status=TaskStatus.RUNNING, limit=500)

    for task in [*pending, *running]:
        metadata = dict(task.metadata or {})
        if metadata.get("director_theme") != "cybernetics":
            continue
        refreshed = _refreshed_metadata(metadata)
        if task.status == TaskStatus.RUNNING and requeue_stale_running:
            await board.update_task(
                task.id,
                status=TaskStatus.PENDING,
                result="Requeued after cybernetics roster rebinding.",
                metadata=refreshed,
            )
            changed.append((task.id, task.title, "requeued"))
            continue
        if refreshed != metadata:
            await board.update_task(task.id, metadata=refreshed)
            changed.append((task.id, task.title, "updated"))

    note_path = STATE_DIR / "shared" / "cybernetics_directive_rebind_latest.json"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(
        json.dumps(
            {
                "task_db": str(TASK_DB),
                "requeue_stale_running": requeue_stale_running,
                "changed": [
                    {"task_id": task_id, "title": title, "action": action}
                    for task_id, title, action in changed
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    for task_id, title, action in changed:
        print(f"{action}: {task_id} :: {title}")
    print(f"wrote: {note_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requeue-stale-running",
        action="store_true",
        help="Requeue running cybernetics tasks after rebinding metadata.",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(requeue_stale_running=args.requeue_stale_running))


if __name__ == "__main__":
    raise SystemExit(main())
