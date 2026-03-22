"""Unified Conversation Logger — every interface, every exchange, timestamped.

Captures all user↔system interactions from:
  - Claude Code sessions (via hook → same JSONL files)
  - Textual TUI (via log_exchange())
  - Dashboard API (via log_exchange())
  - AgentRunner task dispatch (via log_agent_turn())

All entries go to ~/.dharma/conversation_log/:
  - YYYY-MM-DD.jsonl   (daily, human-browsable)
  - all.jsonl           (master, append-only)
  - promises.jsonl      (extracted commitments)

Thread-safe via file locking. No external deps beyond stdlib.
"""

from __future__ import annotations

import fcntl
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOG_DIR = Path.home() / ".dharma" / "conversation_log"
_MASTER_MAX_BYTES = 50 * 1024 * 1024  # 50 MB rotation threshold

# Promise detection patterns
_PROMISE_PATTERNS = [
    re.compile(r"(?i)\bI will\b"),
    re.compile(r"(?i)\bI'll\b"),
    re.compile(r"(?i)\bLet me\b"),
    re.compile(r"(?i)\bI'm going to\b"),
    re.compile(r"(?i)\bNext[,:]?\s+I\b"),
    re.compile(r"(?i)\bwill be (implemented|built|added|created|fixed)"),
    re.compile(r"(?i)\bPhase \d+"),
]


def _atomic_append(path: Path, line: str) -> None:
    """Append a line to a file with advisory file locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line + "\n")
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _extract_promises(text: str) -> list[str]:
    """Extract lines containing commitments/promises."""
    promises = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or len(stripped) < 15:
            continue
        for pattern in _PROMISE_PATTERNS:
            if pattern.search(stripped):
                promises.append(stripped[:300])
                break
    return promises[:20]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_exchange(
    role: str,
    content: str,
    *,
    interface: str = "unknown",
    session_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log a single conversation turn (user input or assistant response).

    Args:
        role: "user", "assistant", or "system"
        content: The message content
        interface: Source interface ("tui", "api", "agent", "claude_code", "cli")
        session_id: Optional session/thread identifier
        metadata: Optional extra data (model, provider, task_id, etc.)
    """
    now = datetime.now(timezone.utc)
    entry = {
        "timestamp": now.isoformat(),
        "role": role,
        "interface": interface,
        "session_id": session_id,
        "content": content[:50000],
    }
    if metadata:
        entry["metadata"] = metadata

    line = json.dumps(entry, ensure_ascii=False)

    # Write to daily log
    daily = LOG_DIR / f"{now.strftime('%Y-%m-%d')}.jsonl"
    _atomic_append(daily, line)

    # Write to master log (with rotation at 50 MB)
    master = LOG_DIR / "all.jsonl"
    try:
        if master.exists() and master.stat().st_size > _MASTER_MAX_BYTES:
            stamp = now.strftime("%Y%m%d_%H%M%S")
            master.rename(LOG_DIR / f"all.{stamp}.jsonl")
            logger.info("Conversation master log rotated → all.%s.jsonl", stamp)
    except Exception:
        logger.debug("Conversation log rotation failed", exc_info=True)
    _atomic_append(master, line)

    # Extract promises from assistant responses
    if role == "assistant" and content:
        promises = _extract_promises(content)
        if promises:
            promise_entry = {
                "timestamp": now.isoformat(),
                "session_id": session_id,
                "interface": interface,
                "type": "promises_detected",
                "count": len(promises),
                "promises": promises,
            }
            _atomic_append(
                LOG_DIR / "promises.jsonl",
                json.dumps(promise_entry, ensure_ascii=False),
            )


def log_agent_turn(
    agent_id: str,
    task_id: str,
    role: str,
    content: str,
    *,
    model: str = "",
    provider: str = "",
) -> None:
    """Log an agent↔LLM turn (dispatched task or received response).

    Args:
        agent_id: Which agent (e.g. "architect", "coder")
        task_id: Task being worked on
        role: "user" (prompt to LLM) or "assistant" (LLM response)
        content: The prompt or response text
        model: Model used
        provider: Provider used
    """
    log_exchange(
        role=role,
        content=content,
        interface="agent",
        session_id=f"agent:{agent_id}:{task_id}",
        metadata={
            "agent_id": agent_id,
            "task_id": task_id,
            "model": model,
            "provider": provider,
        },
    )


# ---------------------------------------------------------------------------
# Query API (same as promise_checker.py but importable)
# ---------------------------------------------------------------------------

def load_recent(hours: float = 24, role: str | None = None) -> list[dict]:
    """Load recent conversation entries."""
    master = LOG_DIR / "all.jsonl"
    if not master.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    entries = []
    for line in master.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts >= cutoff:
                if role is None or entry.get("role") == role:
                    entries.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return entries


def load_promises(hours: float = 24) -> list[dict]:
    """Load recent promise entries."""
    pfile = LOG_DIR / "promises.jsonl"
    if not pfile.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    entries = []
    for line in pfile.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            if ts >= cutoff:
                entries.append(entry)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return entries


def stats(hours: float = 168) -> dict[str, Any]:
    """Return conversation statistics for the last N hours (default 7 days)."""
    entries = load_recent(hours=hours)
    by_role = {"user": 0, "assistant": 0, "system": 0}
    by_interface = {}
    sessions = set()
    for e in entries:
        r = e.get("role", "unknown")
        by_role[r] = by_role.get(r, 0) + 1
        iface = e.get("interface", "unknown")
        by_interface[iface] = by_interface.get(iface, 0) + 1
        sessions.add(e.get("session_id", ""))

    promises = load_promises(hours=hours)
    total_promises = sum(p.get("count", 0) for p in promises)

    return {
        "total_entries": len(entries),
        "by_role": by_role,
        "by_interface": by_interface,
        "unique_sessions": len(sessions),
        "promises_detected": total_promises,
        "hours_covered": hours,
    }
