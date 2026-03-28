"""Shared helpers for Darwin's pending proposal queue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

PENDING_PROPOSALS_FILE = Path.home() / ".dharma" / "evolution" / "pending_proposals.jsonl"


def append_pending_proposal(
    proposal: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one proposal payload to the durable pending queue."""
    resolved = path or PENDING_PROPOSALS_FILE
    payload = dict(proposal)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return payload


def append_pending_proposals(
    proposals: Iterable[dict[str, Any]],
    *,
    path: Path | None = None,
) -> int:
    """Append multiple proposal payloads to the durable pending queue."""
    payloads = [dict(proposal) for proposal in proposals]
    if not payloads:
        return 0
    resolved = path or PENDING_PROPOSALS_FILE
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return len(payloads)
