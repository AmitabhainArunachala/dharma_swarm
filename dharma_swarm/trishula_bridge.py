"""Trishula Bridge -- converts Trishula inbox messages into swarm tasks.

Classifies messages as: actionable, informational, or ack-noise.
Actionable -> create Task. Informational -> log. Ack-noise -> skip.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.models import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

HOME = Path.home()
TRISHULA_INBOX = HOME / "trishula" / "inbox"
PROCESSED_LOG = HOME / ".dharma" / "trishula_processed.json"

# Supported file extensions in the inbox.
_INBOX_EXTENSIONS = frozenset({".json", ".md", ".txt", ".py", ".log", ".out"})

# Patterns matched against message body (case-insensitive).
_ACTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bBLOCKING\b"),
    re.compile(r"\bURGENT\b", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
    re.compile(r"\baction required\b", re.IGNORECASE),
    re.compile(r"\bneeds\b", re.IGNORECASE),
    re.compile(r"\bimplement\b", re.IGNORECASE),
    re.compile(r"\bfix\b", re.IGNORECASE),
    re.compile(r"\bdeploy\b", re.IGNORECASE),
]

_URGENT_PATTERN = re.compile(r"\bURGENT\b|\bBLOCKING\b", re.IGNORECASE)
_HIGH_PATTERN = re.compile(r"\bdeadline\b|\baction required\b", re.IGNORECASE)

# Short bodies that match these are pure ack noise.
_ACK_BODY_PATTERN = re.compile(
    r"^(acknowledged|ack|ok|received|roger|copy that|confirmed|ping|pong)[.!]?$",
    re.IGNORECASE,
)


class MessageClassification:
    """Classification result for a single message."""

    __slots__ = ("path", "category", "priority", "summary")

    def __init__(
        self,
        path: Path,
        category: str,
        priority: TaskPriority | None = None,
        summary: str = "",
    ) -> None:
        self.path = path
        self.category = category  # "actionable", "informational", "ack_noise"
        self.priority = priority
        self.summary = summary

    def __repr__(self) -> str:
        return (
            f"MessageClassification({self.path.name!r}, "
            f"{self.category!r}, {self.priority})"
        )


def _extract_text(path: Path) -> tuple[str, str]:
    """Read a file and return (subject_or_title, body).

    JSON files with a ``body`` key are unpacked.  Markdown / plain-text files
    use the first non-empty line as the title.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix == ".json":
        try:
            data: dict[str, Any] = json.loads(raw)
            subject = str(data.get("subject", ""))
            body = str(data.get("body", ""))
            return subject or path.stem, body
        except (json.JSONDecodeError, TypeError):
            pass  # fall through to plain-text handling

    # Markdown / plain text: first non-blank line is title.
    lines = raw.splitlines()
    title = ""
    for line in lines:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            title = stripped
            break
    return title or path.stem, raw


class TrishulaBridge:
    """Converts Trishula messages into swarm tasks."""

    def __init__(self, inbox: Path | None = None) -> None:
        self.inbox = inbox or TRISHULA_INBOX
        self._processed: set[str] = self._load_processed()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_processed(self) -> set[str]:
        """Load set of already-processed filenames."""
        if PROCESSED_LOG.exists():
            try:
                data = json.loads(PROCESSED_LOG.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return set(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load processed log: %s", exc)
        return set()

    def _save_processed(self) -> None:
        """Persist the processed set."""
        PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
        PROCESSED_LOG.write_text(
            json.dumps(sorted(self._processed), indent=2) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, path: Path | str) -> MessageClassification:
        path = Path(path) if isinstance(path, str) else path
        """Classify a single message file.

        Rules:
        - Filename contains 'ack' or body is short boilerplate -> ack_noise
        - Body contains action keywords (TODO, BLOCKING, URGENT, deadline,
          action required, needs, implement, fix, deploy) -> actionable
        - Body mentions file paths, code, or technical specs -> informational
        - Everything else -> ack_noise

        Priority mapping:
        - "URGENT" or "BLOCKING" in body -> URGENT
        - "deadline" or "action required" in body -> HIGH
        - Otherwise -> NORMAL
        """
        title, body = _extract_text(path)
        body_stripped = body.strip()
        fname_lower = path.stem.lower()

        # --- ack noise: filename heuristic ---
        if "ack" in fname_lower and "comms_check" in fname_lower:
            return MessageClassification(path, "ack_noise", summary=title)

        # --- ack noise: tiny body with boilerplate ---
        if len(body_stripped) < 100 and _ACK_BODY_PATTERN.search(body_stripped):
            return MessageClassification(path, "ack_noise", summary=title)

        # --- ack noise: JSON type=ack with short body ---
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(data, dict) and data.get("type") == "ack":
                    return MessageClassification(path, "ack_noise", summary=title)
            except (json.JSONDecodeError, OSError):
                pass

        # --- actionable: keyword scan ---
        combined = f"{title} {body}"
        if any(pat.search(combined) for pat in _ACTION_PATTERNS):
            priority = TaskPriority.NORMAL
            if _URGENT_PATTERN.search(combined):
                priority = TaskPriority.URGENT
            elif _HIGH_PATTERN.search(combined):
                priority = TaskPriority.HIGH
            return MessageClassification(
                path, "actionable", priority=priority, summary=title
            )

        # --- informational: technical references ---
        informational_markers = [
            r"R_V\b", r"Layer\s*\d+", r"mech-interp", r"[~/][\w/]+\.\w+",
            r"Cohen", r"activation[_ ]patching", r"AUROC", r"Pythia",
            r"Mistral", r"SAB", r"dharmic.agora",
        ]
        if any(re.search(m, combined, re.IGNORECASE) for m in informational_markers):
            return MessageClassification(
                path, "informational", summary=title
            )

        # --- default: ack_noise ---
        return MessageClassification(path, "ack_noise", summary=title)

    # ------------------------------------------------------------------
    # Task creation
    # ------------------------------------------------------------------

    def create_task_from_message(
        self, classification: MessageClassification
    ) -> Task:
        """Create a Task from an actionable message classification."""
        title, body = _extract_text(classification.path)

        # Truncate overly long titles.
        if len(title) > 120:
            title = title[:117] + "..."

        return Task(
            title=f"[trishula] {title}",
            description=body,
            status=TaskStatus.PENDING,
            priority=classification.priority or TaskPriority.NORMAL,
            created_by="trishula_bridge",
            metadata={
                "source": "trishula",
                "source_file": classification.path.name,
                "classified_as": classification.category,
            },
        )

    # ------------------------------------------------------------------
    # Inbox processing
    # ------------------------------------------------------------------

    def _inbox_files(self) -> list[Path]:
        """Return inbox files sorted by name (chronological)."""
        if not self.inbox.is_dir():
            return []
        return sorted(
            p for p in self.inbox.iterdir()
            if p.is_file() and p.suffix in _INBOX_EXTENSIONS
        )

    def process_inbox(self) -> dict[str, int | list[Task]]:
        """Process all unprocessed messages in inbox.

        Returns:
            Dictionary with counts and created tasks::

                {
                    "total_scanned": int,
                    "actionable": int,
                    "informational": int,
                    "ack_noise": int,
                    "tasks_created": list[Task],
                    "already_processed": int,
                }
        """
        files = self._inbox_files()
        actionable = 0
        informational = 0
        ack_noise = 0
        already_processed = 0
        tasks_created: list[Task] = []

        for path in files:
            if path.name in self._processed:
                already_processed += 1
                continue

            try:
                cls = self.classify(path)
            except Exception:
                logger.exception("Failed to classify %s", path.name)
                continue

            if cls.category == "actionable":
                actionable += 1
                task = self.create_task_from_message(cls)
                tasks_created.append(task)
                logger.info("Task created: %s [%s]", task.title, task.priority.value)
            elif cls.category == "informational":
                informational += 1
                logger.debug("Informational: %s", path.name)
            else:
                ack_noise += 1

            self._processed.add(path.name)

        self._save_processed()
        return {
            "total_scanned": len(files),
            "actionable": actionable,
            "informational": informational,
            "ack_noise": ack_noise,
            "tasks_created": tasks_created,
            "already_processed": already_processed,
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def triage_report(self) -> str:
        """Generate a human-readable triage report of the inbox state."""
        files = self._inbox_files()
        buckets: dict[str, list[MessageClassification]] = {
            "actionable": [],
            "informational": [],
            "ack_noise": [],
        }

        for path in files:
            try:
                cls = self.classify(path)
            except Exception:
                continue
            buckets[cls.category].append(cls)

        lines: list[str] = [
            "=== Trishula Inbox Triage Report ===",
            f"Total files:    {len(files)}",
            f"Actionable:     {len(buckets['actionable'])}",
            f"Informational:  {len(buckets['informational'])}",
            f"Ack noise:      {len(buckets['ack_noise'])}",
            f"Already processed: {len(self._processed)}",
            "",
        ]

        if buckets["actionable"]:
            lines.append("--- Actionable Items ---")
            for cls in buckets["actionable"]:
                prio = cls.priority.value if cls.priority else "normal"
                processed = " [done]" if cls.path.name in self._processed else ""
                lines.append(f"  [{prio.upper():6s}] {cls.path.name}{processed}")
                if cls.summary:
                    lines.append(f"           {cls.summary}")
            lines.append("")

        if buckets["informational"]:
            lines.append("--- Informational ---")
            for cls in buckets["informational"][:20]:
                lines.append(f"  {cls.path.name}")
                if cls.summary:
                    lines.append(f"    {cls.summary}")
            remaining = len(buckets["informational"]) - 20
            if remaining > 0:
                lines.append(f"  ... and {remaining} more")
            lines.append("")

        lines.append(f"Ack noise: {len(buckets['ack_noise'])} messages (skipped)")
        return "\n".join(lines)
