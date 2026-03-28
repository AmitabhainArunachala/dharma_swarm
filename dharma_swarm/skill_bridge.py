"""Skill Bridge -- routes Claude Code skill outputs to swarm feedback loops.

Claude Code skills (fitness-evaluator, diversity-archive, retro, hypothesis,
knowledge-distiller) produce outputs during interactive sessions.  This module
provides a file-based inbox that Claude Code sessions can write to, and a
drain function that the orchestrator calls to route those outputs to the
appropriate swarm subsystem.

Inbox protocol:
    Each line in ``~/.dharma/skill_bridge/inbox.jsonl`` is a JSON object with:
    - ``skill_name``: str  (e.g. "retro", "fitness-evaluator")
    - ``timestamp``: str (ISO 8601)
    - ``payload``: dict (skill-specific data)

Routes:
    - retro findings      → ``~/.dharma/evolution/pending_proposals.jsonl``
    - fitness-evaluator   → ``benchmark_registry.update()``
    - diversity-archive   → ``~/.dharma/evolution/diversity_grid.json``
    - knowledge-distiller → best-effort memory compression signal
    - hypothesis          → ``~/.dharma/evolution/pending_proposals.jsonl``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.pending_proposals import (
    PENDING_PROPOSALS_FILE as _DEFAULT_PENDING_PROPOSALS_FILE,
    append_pending_proposals,
)

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
INBOX_DIR = STATE_DIR / "skill_bridge"
INBOX_FILE = INBOX_DIR / "inbox.jsonl"
PROPOSALS_FILE = _DEFAULT_PENDING_PROPOSALS_FILE


class SkillBridge:
    """File-based inbox for Claude Code skill outputs → swarm feedback."""

    def __init__(self, inbox_path: Path | None = None) -> None:
        self._inbox = inbox_path or INBOX_FILE

    # -- inbox management --------------------------------------------------

    def drain_inbox(self) -> list[dict[str, Any]]:
        """Read all entries from inbox and truncate the file.

        Returns list of inbox entries.  Each entry is a dict with
        ``skill_name``, ``timestamp``, and ``payload`` keys.
        """
        if not self._inbox.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            lines = self._inbox.read_text().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed inbox entry")
            # Atomic truncate
            self._inbox.write_text("")
        except Exception as exc:
            logger.warning("Failed to drain skill bridge inbox: %s", exc)
        return entries

    @staticmethod
    def submit(skill_name: str, payload: dict[str, Any]) -> None:
        """Write an entry to the inbox (called from Claude Code sessions).

        This is a static method so it can be called without instantiation:
        ``SkillBridge.submit("retro", {"findings": [...]})``
        """
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "skill_name": skill_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        try:
            with open(INBOX_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("Failed to write to skill bridge inbox: %s", exc)

    # -- routing -----------------------------------------------------------

    def process_entries(self, entries: list[dict[str, Any]]) -> dict[str, int]:
        """Route each entry to its destination.  Returns counts by skill."""
        counts: dict[str, int] = {}
        for entry in entries:
            skill = entry.get("skill_name", "")
            payload = entry.get("payload", {})
            counts[skill] = counts.get(skill, 0) + 1
            try:
                if skill == "retro":
                    self._ingest_retro(payload)
                elif skill == "fitness-evaluator":
                    self._ingest_fitness_evaluation(payload)
                elif skill == "diversity-archive":
                    self._ingest_diversity_grid(payload)
                elif skill == "hypothesis":
                    self._ingest_hypothesis(payload)
                elif skill == "knowledge-distiller":
                    self._ingest_knowledge_distiller(payload)
                else:
                    logger.debug("Unknown skill bridge entry: %s", skill)
            except Exception as exc:
                logger.warning("Failed to process %s entry: %s", skill, exc)
        return counts

    # -- handlers ----------------------------------------------------------

    def _ingest_retro(self, payload: dict[str, Any]) -> None:
        """Convert retro findings into evolution proposals."""
        findings = payload.get("findings", [])
        if not findings:
            return
        append_pending_proposals(
            [
                {
                    "component": finding.get("component", "system"),
                    "change_type": "retro_finding",
                    "description": f"[retro] {finding.get('description', '')}",
                    "diff": "",
                    "spec_ref": "skill_bridge_retro",
                }
                for finding in findings
            ],
            path=PROPOSALS_FILE,
        )
        logger.info("Ingested %d retro findings as proposals", len(findings))

    def _ingest_fitness_evaluation(self, payload: dict[str, Any]) -> None:
        """Feed fitness-evaluator output into benchmark registry."""
        try:
            from dharma_swarm.benchmark_registry import BenchmarkRegistry
            registry = BenchmarkRegistry()

            # Map fitness dimensions to benchmarks
            dimensions = payload.get("dimensions", {})
            for name, value in dimensions.items():
                if name in registry:
                    registry.update(name, float(value))
            registry.save()
            logger.info("Updated benchmarks from fitness evaluation: %s", list(dimensions.keys()))
        except Exception as exc:
            logger.warning("Fitness evaluation ingestion failed: %s", exc)

    def _ingest_diversity_grid(self, payload: dict[str, Any]) -> None:
        """Feed diversity-archive grid into evolution archive."""
        grid_path = STATE_DIR / "evolution" / "diversity_grid.json"
        grid_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            grid_path.write_text(json.dumps(payload, indent=2))
            logger.info("Updated diversity grid from skill bridge")
        except Exception as exc:
            logger.warning("Diversity grid update failed: %s", exc)

    def _ingest_hypothesis(self, payload: dict[str, Any]) -> None:
        """Convert hypothesis into evolution proposals."""
        hypotheses = payload.get("hypotheses", [])
        if not hypotheses:
            return
        append_pending_proposals(
            [
                {
                    "component": hyp.get("target_module", "system"),
                    "change_type": "hypothesis_test",
                    "description": f"[hypothesis] {hyp.get('statement', '')}",
                    "diff": "",
                    "spec_ref": "skill_bridge_hypothesis",
                }
                for hyp in hypotheses
            ],
            path=PROPOSALS_FILE,
        )
        logger.info("Ingested %d hypotheses as proposals", len(hypotheses))

    def _ingest_knowledge_distiller(self, payload: dict[str, Any]) -> None:
        """Signal that memory compression ran — log and emit signal."""
        compressed = payload.get("entries_compressed", 0)
        logger.info("Knowledge distiller compressed %d entries", compressed)
        try:
            from dharma_swarm.signal_bus import SignalBus
            SignalBus.get().emit({
                "type": "KNOWLEDGE_DISTILLED",
                "entries_compressed": compressed,
            })
        except Exception:
            pass
