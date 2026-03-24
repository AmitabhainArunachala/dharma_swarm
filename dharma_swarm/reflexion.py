"""Reflexion -- verbal reinforcement learning for agent self-correction.

After a task attempt fails, the system generates a structured reflection
analyzing what went wrong and how to improve. This reflection is prepended
to the next attempt's context, creating a verbal reinforcement loop.

Inspired by:
  - Shinn et al., "Reflexion" (NeurIPS 2023): inner/outer loop with verbal RL
  - Spotify Honk: 25% judge veto rate, 50% self-correction on retry
  - dharma_swarm consolidation.py: behavioral corrections as "backprop"

Grounded in:
  - Dada Bhagwan (Pillar 6): pratikraman -- active error correction
  - Friston (Pillar 10): reduce surprise by updating predictions
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

_DEFAULT_REFLEXION_DIR = Path.home() / ".dharma" / "reflexion"

# Type alias matching group_chat.ProviderFn for consistency.
ProviderFn = Callable[[str, str], Awaitable[str]]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReflexionEntry:
    """One recorded reflection after a task attempt."""

    task_id: str
    attempt_number: int
    outcome: str  # "success" or "fail"
    error_summary: str
    reflection_text: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflexionEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__slots__})


# ---------------------------------------------------------------------------
# ReflexionMemory
# ---------------------------------------------------------------------------


class ReflexionMemory:
    """Persistent memory of task reflections for the verbal RL loop.

    Stores reflections keyed by task_id so that subsequent attempts on the
    same task can retrieve what went wrong previously and how to adjust.

    Args:
        max_entries: Maximum entries to hold in memory (FIFO eviction).
        persist_path: Path to a JSONL file for durable storage.
            Defaults to ``~/.dharma/reflexion/entries.jsonl``.
    """

    def __init__(
        self,
        max_entries: int = 50,
        persist_path: Path | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._persist_path = persist_path or (_DEFAULT_REFLEXION_DIR / "entries.jsonl")
        self._entries: list[ReflexionEntry] = []

    # -- write API ----------------------------------------------------------

    def add_reflection(
        self,
        task_id: str,
        attempt: int,
        outcome: str,
        error: str,
        reflection: str,
    ) -> ReflexionEntry:
        """Record a new reflection entry and return it.

        Evicts the oldest entry when ``max_entries`` is exceeded.
        """
        entry = ReflexionEntry(
            task_id=task_id,
            attempt_number=attempt,
            outcome=outcome,
            error_summary=error,
            reflection_text=reflection,
        )
        self._entries.append(entry)
        # FIFO eviction
        while len(self._entries) > self._max_entries:
            self._entries.pop(0)
        return entry

    # -- read API -----------------------------------------------------------

    def get_reflections(self, task_id: str, limit: int = 3) -> list[ReflexionEntry]:
        """Retrieve the most recent reflections for a given task.

        Returns up to *limit* entries, most recent last.
        """
        matches = [e for e in self._entries if e.task_id == task_id]
        return matches[-limit:]

    def build_context(self, task_id: str) -> str:
        """Format all reflections for *task_id* as context to prepend.

        The returned string is designed to be injected into the system
        prompt for the next attempt, giving the agent verbal memory of
        prior failures and the reasoning about what to change.
        """
        entries = self.get_reflections(task_id)
        if not entries:
            return ""

        lines: list[str] = [
            "=== Prior Attempt Reflections ===",
            f"Task: {task_id}",
            "",
        ]
        for entry in entries:
            lines.append(
                f"Attempt {entry.attempt_number} ({entry.outcome}):"
            )
            if entry.error_summary:
                lines.append(f"  Error: {entry.error_summary}")
            lines.append(f"  Reflection: {entry.reflection_text}")
            lines.append("")
        lines.append(
            "Use the above reflections to avoid repeating mistakes. "
            "Adjust your approach accordingly."
        )
        return "\n".join(lines)

    def success_rate(self, task_id: str) -> float:
        """Fraction of attempts for *task_id* that succeeded.

        Returns 0.0 if there are no entries for the task.
        """
        entries = [e for e in self._entries if e.task_id == task_id]
        if not entries:
            return 0.0
        successes = sum(1 for e in entries if e.outcome == "success")
        return successes / len(entries)

    # -- persistence --------------------------------------------------------

    def persist(self) -> None:
        """Append all in-memory entries to the JSONL file on disk."""
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self._persist_path.open("a", encoding="utf-8") as fh:
            for entry in self._entries:
                fh.write(json.dumps(entry.to_dict()) + "\n")
        logger.info(
            "Persisted %d reflexion entries to %s",
            len(self._entries),
            self._persist_path,
        )

    def load(self) -> None:
        """Load entries from the JSONL file, replacing in-memory state."""
        if not self._persist_path.exists():
            logger.debug("No reflexion file at %s — starting empty", self._persist_path)
            return
        loaded: list[ReflexionEntry] = []
        with self._persist_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    loaded.append(ReflexionEntry.from_dict(data))
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Skipping malformed reflexion entry: %s", line[:120])
        # Apply max_entries cap (keep most recent)
        self._entries = loaded[-self._max_entries:]
        logger.info(
            "Loaded %d reflexion entries from %s",
            len(self._entries),
            self._persist_path,
        )

    @property
    def entries(self) -> list[ReflexionEntry]:
        """Read-only view of in-memory entries."""
        return list(self._entries)


# ---------------------------------------------------------------------------
# LLM-powered reflection generation
# ---------------------------------------------------------------------------

_REFLECTION_SYSTEM = (
    "You are a reflective analysis system. Given a task description and the "
    "error that occurred, produce a structured reflection with three sections:\n"
    "1. WHAT WENT WRONG: Describe the failure mode concisely.\n"
    "2. ROOT CAUSE: Identify the underlying reason.\n"
    "3. NEXT ATTEMPT: Specify concrete changes for the next try.\n"
    "Be direct and actionable. No filler."
)


async def generate_reflection(
    task_description: str,
    error: str,
    provider_fn: ProviderFn,
) -> str:
    """Call an LLM to generate a structured verbal reflection.

    Args:
        task_description: What the agent was trying to do.
        error: The error message or failure description.
        provider_fn: Async callable ``(system_prompt, user_prompt) -> str``.

    Returns:
        A structured reflection string suitable for prepending to the
        next attempt's context.
    """
    user_prompt = (
        f"Task: {task_description}\n\n"
        f"Error: {error}\n\n"
        "Generate a structured reflection following the three-section format."
    )
    try:
        return await provider_fn(_REFLECTION_SYSTEM, user_prompt)
    except Exception:
        logger.exception("Failed to generate reflection for task %r", task_description)
        return (
            f"WHAT WENT WRONG: {error}\n"
            f"ROOT CAUSE: Unable to generate detailed reflection (provider error).\n"
            f"NEXT ATTEMPT: Retry with additional error handling."
        )
