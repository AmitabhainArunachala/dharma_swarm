"""Archaeology Ingestion — continuous indexer of DHARMA SWARM's institutional memory.

This module closes Gap 4 from WHAT_IT_WANTS_TO_BECOME.md:
    "Every time the swarm boots, it starts with whatever is in its
    configuration files and whatever the conductor loads. It cannot ask:
    'What has this system tried before? What worked? What failed? Why?'
    This is the amnesia problem."

What it does:
    Continuously ingests three streams of institutional memory into MemoryPalace
    (LanceDB), making them queryable by any agent during execution:

    Stream 1: Evolution Archive
        Every archive entry (diff, fitness, lineage, parent_id, component)
        becomes a searchable document. Agents can ask: "What has been
        tried for agent_runner.py? What was the highest-fitness mutation?"

    Stream 2: Session Transcripts
        Agent task outputs, WitnessAuditor cycles, and task completion
        records become searchable. Agents can ask: "What research has
        this swarm already done? What topics have been covered?"

    Stream 3: Research Outputs
        Files in ~/.dharma/shared/ (landscape research, competitor analyses,
        synthesis reports) are ingested. Agents avoid duplicating work.

    Stream 4: Stigmergy Marks (high-salience)
        All marks with salience >= 0.85 are ingested as permanent memory.
        The Gnani lodestone marks (salience 0.92-0.97) are always present.

Compressed Lessons (anti-amnesia):
    Every ingestion cycle produces a compressed "lessons learned" document
    that summarizes: what the system has tried, what worked, what failed,
    and what the current best-performing configurations are.
    This document is saved to ~/.dharma/meta/lessons_learned.md and loaded
    into the conductor's context at every boot.

Query interface:
    The `query_archaeology` async function provides agents with a simple
    interface: give it a natural language question, get back the most
    relevant institutional memory.

Usage (daemon)::

    daemon = ArchaeologyIngestionDaemon()
    await daemon.run_once()      # one full ingestion pass
    await daemon.run_forever()   # loop every 30 minutes

Usage (query from agent tool)::

    results = await query_archaeology(
        "What has been tried to fix provider timeout errors?",
        state_dir=Path("~/.dharma"),
    )
    # Returns list of MemoryHit with content, source, relevance_score

Reference:
    DGM open-ended archive: https://sakana.ai/dgm/
    "New agents can branch off from ANY prior agent in the archive."
    This requires the archive to be indexed and accessible, not just stored.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_INGESTION_INTERVAL = 1800  # 30 minutes


@dataclass
class MemoryHit:
    """A single archaeology query result."""
    content: str
    source: str
    layer: str
    relevance_score: float = 0.0
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated {len(text) - max_chars} chars]"


async def _ingest_into_palace(
    palace: Any,
    content: str,
    source: str,
    layer: str,
    tags: list[str],
    metadata: dict[str, Any],
) -> str | None:
    """Ingest one document into MemoryPalace. Returns doc_id or None on failure."""
    if not content.strip():
        return None
    try:
        doc_id = await palace.ingest(
            content=content,
            source=source,
            layer=layer,
            tags=tags,
            metadata=metadata,
        )
        return doc_id
    except Exception as exc:
        logger.debug("Palace ingest failed for %s: %s", source, exc)
        return None


# ---------------------------------------------------------------------------
# Stream ingestors
# ---------------------------------------------------------------------------

async def ingest_evolution_archive(
    palace: Any,
    state_dir: Path,
) -> int:
    """Ingest all evolution archive entries into MemoryPalace.

    Each entry becomes a document describing: what file was modified,
    what the diff proposed, what the fitness score was, and what the outcome was.
    Agents querying "what has been tried on agent_runner.py?" will find these.

    Returns: number of entries ingested.
    """
    archive_path = state_dir / "evolution" / "archive.jsonl"
    if not archive_path.exists():
        return 0

    ingested = 0
    try:
        lines = archive_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_id = entry.get("id", "")
            component = entry.get("component", entry.get("source_file", "unknown"))
            status = entry.get("status", "unknown")
            timestamp = entry.get("timestamp", "")
            parent_id = entry.get("parent_id", "")
            diff_text = entry.get("diff", "")
            fitness = entry.get("fitness", {})
            test_results = entry.get("test_results", {})

            # Build a human-readable document for this archive entry
            fitness_summary = ""
            if isinstance(fitness, dict):
                weighted = fitness.get("weighted", 0)
                correctness = fitness.get("correctness", 0)
                dharmic = fitness.get("dharmic_alignment", 0)
                fitness_summary = (
                    f"Fitness: weighted={weighted:.3f}, "
                    f"correctness={correctness:.3f}, "
                    f"dharmic_alignment={dharmic:.3f}"
                )

            doc = (
                f"Evolution archive entry: {entry_id}\n"
                f"Component: {component} | Status: {status} | Timestamp: {timestamp}\n"
                f"Parent: {parent_id or 'root'}\n"
                f"{fitness_summary}\n"
                f"Test results: {json.dumps(test_results)[:300]}\n"
            )
            if diff_text.strip():
                doc += f"Diff summary (first 500 chars):\n{diff_text[:500]}\n"

            source_key = f"evolution_archive:{entry_id}"
            doc_id = await _ingest_into_palace(
                palace,
                content=doc,
                source=source_key,
                layer="development",
                tags=["evolution", "archive", component, status],
                metadata={
                    "entry_id": entry_id,
                    "component": component,
                    "status": status,
                    "timestamp": timestamp,
                    "parent_id": parent_id,
                    "stream": "evolution_archive",
                },
            )
            if doc_id:
                ingested += 1

    except Exception as exc:
        logger.warning("Evolution archive ingestion failed: %s", exc)

    logger.info("Evolution archive: %d entries ingested", ingested)
    return ingested


async def ingest_shared_research(
    palace: Any,
    state_dir: Path,
) -> int:
    """Ingest research outputs from ~/.dharma/shared/ into MemoryPalace.

    These are the files produced by agents: landscape research, competitor
    analyses, synthesis reports, grant drafts, etc.

    Agents querying "what research has been done on Sakana AI?" will find these.
    This prevents agents from duplicating work that has already been completed.

    Returns: number of files ingested.
    """
    shared_dir = state_dir / "shared"
    if not shared_dir.exists():
        return 0

    artifacts_dir = state_dir / "artifacts"

    ingested = 0
    for directory in [shared_dir, artifacts_dir]:
        if not directory.exists():
            continue
        for f in directory.rglob("*.md"):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue

                source_key = f"research:{f.name}"
                doc_id = await _ingest_into_palace(
                    palace,
                    content=_truncate(content, 3000),
                    source=source_key,
                    layer="development",
                    tags=["research", "output", f.stem],
                    metadata={
                        "file_path": str(f),
                        "file_name": f.name,
                        "stream": "shared_research",
                        "size_bytes": f.stat().st_size,
                    },
                )
                if doc_id:
                    ingested += 1
            except Exception as exc:
                logger.debug("Failed to ingest %s: %s", f, exc)

    logger.info("Shared research: %d files ingested", ingested)
    return ingested


async def ingest_stigmergy_marks(
    palace: Any,
    state_dir: Path,
    min_salience: float = 0.85,
) -> int:
    """Ingest high-salience stigmergy marks into MemoryPalace as permanent memory.

    Marks at salience >= 0.85 represent critical observations that all agents
    should have access to. The Gnani lodestone marks (0.92-0.97) are always included.

    Returns: number of marks ingested.
    """
    marks_path = state_dir / "stigmergy" / "marks.jsonl"
    if not marks_path.exists():
        return 0

    ingested = 0
    try:
        lines = marks_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                mark = json.loads(line)
            except json.JSONDecodeError:
                continue

            salience = float(mark.get("salience", 0))
            if salience < min_salience:
                continue

            mark_id = mark.get("id", "")
            channel = mark.get("channel", "default")
            observation = mark.get("observation", "")
            agent = mark.get("agent", "unknown")
            file_path = mark.get("file_path", "")

            if not observation.strip():
                continue

            doc = (
                f"Stigmergy mark [{channel}] (salience={salience:.2f})\n"
                f"Agent: {agent} | File: {file_path} | ID: {mark_id}\n"
                f"Observation: {observation}\n"
            )

            source_key = f"stigmergy:{mark_id or channel}"
            doc_id = await _ingest_into_palace(
                palace,
                content=doc,
                source=source_key,
                layer="meta",
                tags=["stigmergy", channel, agent],
                metadata={
                    "mark_id": mark_id,
                    "channel": channel,
                    "salience": salience,
                    "stream": "stigmergy",
                },
            )
            if doc_id:
                ingested += 1

    except Exception as exc:
        logger.warning("Stigmergy ingestion failed: %s", exc)

    logger.info("Stigmergy marks: %d high-salience marks ingested", ingested)
    return ingested


async def ingest_task_completions(
    palace: Any,
    state_dir: Path,
) -> int:
    """Ingest completed task records into MemoryPalace.

    Agents can query: "What tasks has this swarm completed? What approaches
    succeeded? What failed and why?"

    Returns: number of task records ingested.
    """
    db_dir = state_dir / "db"
    task_log_path = state_dir / "tasks" / "completed.jsonl"
    alt_path = db_dir / "task_completions.jsonl"

    ingested = 0
    for path in [task_log_path, alt_path]:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            for line in lines[-500:]:  # Last 500 completions to avoid overwhelming
                if not line.strip():
                    continue
                try:
                    task = json.loads(line)
                except json.JSONDecodeError:
                    continue

                title = task.get("title", "unknown")
                result_summary = task.get("result_summary", task.get("output", ""))[:500]
                status = task.get("status", "unknown")
                agent = task.get("agent_id", "unknown")
                completed_at = task.get("completed_at", "")

                if not result_summary.strip():
                    continue

                doc = (
                    f"Task completion: {title}\n"
                    f"Status: {status} | Agent: {agent} | Completed: {completed_at}\n"
                    f"Result: {result_summary}\n"
                )

                source_key = f"task_completion:{task.get('id', title[:40])}"
                doc_id = await _ingest_into_palace(
                    palace,
                    content=doc,
                    source=source_key,
                    layer="session",
                    tags=["task", "completion", status, agent],
                    metadata={
                        "title": title,
                        "status": status,
                        "agent": agent,
                        "stream": "task_completions",
                    },
                )
                if doc_id:
                    ingested += 1
        except Exception as exc:
            logger.debug("Task completion ingestion from %s failed: %s", path, exc)

    logger.info("Task completions: %d records ingested", ingested)
    return ingested


# ---------------------------------------------------------------------------
# Compressed lessons synthesis
# ---------------------------------------------------------------------------

async def synthesize_lessons_learned(
    palace: Any,
    state_dir: Path,
    max_hits: int = 20,
) -> str:
    """Query MemoryPalace for the most important institutional lessons.

    Produces a compressed "lessons learned" document that captures:
    - Best-performing evolution entries (what worked)
    - Common failure patterns (what to avoid)
    - Research already completed (no duplication)
    - Active strategic constraints (from Gnani marks)

    This document is saved to ~/.dharma/meta/lessons_learned.md and loaded
    at every boot. It is the anti-amnesia mechanism.

    Returns: The lessons learned markdown text.
    """
    sections: list[str] = []
    sections.append(f"# DHARMA SWARM Lessons Learned\n*Generated: {_utc_iso()}*\n")

    # Query 1: What evolution strategies worked?
    try:
        result = await palace.recall(PalaceQuery(text="evolution applied fitness improvement success", max_results=5))
        if result.results:
            sections.append("## Evolution: What Worked\n")
            for hit in result.results[:5]:
                content = getattr(hit, 'content', '') or str(hit)
                sections.append(f"- {content[:200]}\n")
    except Exception as exc:
        logger.debug("Lessons query 1 failed: %s", exc)

    # Query 2: What failed or was rolled back?
    try:
        result = await palace.recall(PalaceQuery(text="evolution rolled_back failed rejected error", max_results=5))
        if result.results:
            sections.append("\n## Evolution: What Failed\n")
            for hit in result.results[:5]:
                content = getattr(hit, 'content', '') or str(hit)
                sections.append(f"- {content[:200]}\n")
    except Exception as exc:
        logger.debug("Lessons query 2 failed: %s", exc)

    # Query 3: Research already completed
    try:
        result = await palace.recall(PalaceQuery(text="research completed analysis landscape competitive", max_results=5))
        if result.results:
            sections.append("\n## Research: Already Completed\n")
            for hit in result.results[:5]:
                content = getattr(hit, 'content', '') or str(hit)
                source = getattr(hit, 'source', '')
                sections.append(f"- [{source}] {content[:150]}\n")
    except Exception as exc:
        logger.debug("Lessons query 3 failed: %s", exc)

    # Query 4: Gnani / strategic constraints
    try:
        result = await palace.recall(PalaceQuery(text="gnani witness telos dharmic architecture constraint", max_results=5))
        if result.results:
            sections.append("\n## Strategic Constraints (Gnani Layer)\n")
            for hit in result.results[:5]:
                content = getattr(hit, 'content', '') or str(hit)
                sections.append(f"- {content[:200]}\n")
    except Exception as exc:
        logger.debug("Lessons query 4 failed: %s", exc)

    # Query 5: Provider issues
    try:
        result = await palace.recall(PalaceQuery(text="provider error timeout groq billing access denied", max_results=3))
        if result.results:
            sections.append("\n## Known Provider Issues\n")
            for hit in result.results[:3]:
                content = getattr(hit, 'content', '') or str(hit)
                sections.append(f"- {content[:150]}\n")
    except Exception as exc:
        logger.debug("Lessons query 5 failed: %s", exc)

    lessons_text = "\n".join(sections)

    # Save to disk
    meta_dir = state_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    lessons_path = meta_dir / "lessons_learned.md"
    try:
        lessons_path.write_text(lessons_text, encoding="utf-8")
        logger.info("Lessons learned saved: %s (%d chars)", lessons_path, len(lessons_text))
    except Exception as exc:
        logger.warning("Failed to save lessons learned: %s", exc)

    return lessons_text


# ---------------------------------------------------------------------------
# Query interface for agents
# ---------------------------------------------------------------------------

async def query_archaeology(
    question: str,
    state_dir: Path | None = None,
    top_k: int = 5,
) -> list[MemoryHit]:
    """Query the institutional archaeology memory.

    This is the agent-facing interface. Agents call this when they want
    to know what the system has done before, what worked, what failed,
    or what research has been completed.

    Args:
        question: Natural language question, e.g.:
            "What has been tried to fix provider timeouts?"
            "What research has already been done on Sakana AI?"
            "What are the highest-fitness evolution archive entries?"
        state_dir: DHARMA state directory. Defaults to ~/.dharma.
        top_k: Maximum results to return.

    Returns:
        List of MemoryHit ordered by relevance.
    """
    state_dir = state_dir or Path.home() / ".dharma"

    try:
        from dharma_swarm.memory_palace import MemoryPalace, PalaceQuery

        palace = MemoryPalace(state_dir=state_dir)
        result = await palace.recall(PalaceQuery(text=question, max_results=top_k))

        hits: list[MemoryHit] = []
        for r in result.results:
            content = getattr(r, 'content', '') or str(r)
            source = getattr(r, 'source', 'unknown')
            layer = getattr(r, 'layer', 'unknown')
            score = getattr(r, 'score', 0.0)
            metadata = getattr(r, 'metadata', {})
            hits.append(MemoryHit(
                content=content,
                source=source,
                layer=layer,
                relevance_score=score,
                metadata=metadata,
            ))

        # Also check lessons_learned.md for quick answers
        lessons_path = state_dir / "meta" / "lessons_learned.md"
        if lessons_path.exists() and len(hits) < top_k:
            lessons_text = lessons_path.read_text(encoding="utf-8", errors="ignore")
            # Simple relevance check: does the question's key terms appear?
            question_terms = question.lower().split()
            relevant_lines = [
                line for line in lessons_text.splitlines()
                if any(term in line.lower() for term in question_terms if len(term) > 3)
            ]
            if relevant_lines:
                hits.insert(0, MemoryHit(
                    content="\n".join(relevant_lines[:10]),
                    source="lessons_learned.md",
                    layer="meta",
                    relevance_score=0.8,
                    metadata={"stream": "compressed_lessons"},
                ))

        return hits[:top_k]

    except Exception as exc:
        logger.warning("Archaeology query failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Main daemon class
# ---------------------------------------------------------------------------

class ArchaeologyIngestionDaemon:
    """Continuous ingestion daemon for DHARMA SWARM's institutional memory.

    Runs every 30 minutes (configurable). On each cycle:
    1. Ingests evolution archive entries
    2. Ingests shared research outputs
    3. Ingests high-salience stigmergy marks
    4. Ingests task completion records
    5. Synthesizes compressed lessons learned document

    At boot, the conductor loads lessons_learned.md as a context prefix,
    ensuring the swarm starts each session with its accumulated wisdom.

    Args:
        state_dir: DHARMA state directory. Defaults to ~/.dharma.
        interval_seconds: Time between ingestion cycles (default: 30 min).
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        interval_seconds: int = _DEFAULT_INGESTION_INTERVAL,
    ) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"
        self._interval = interval_seconds

    async def run_once(self) -> dict[str, int]:
        """Run one full ingestion cycle. Returns counts per stream."""
        try:
            from dharma_swarm.memory_palace import MemoryPalace, PalaceQuery
            palace = MemoryPalace(state_dir=self._state_dir)
        except Exception as exc:
            logger.error("ArchaeologyIngestionDaemon: MemoryPalace unavailable: %s", exc)
            return {}

        counts: dict[str, int] = {}

        counts["evolution_archive"] = await ingest_evolution_archive(palace, self._state_dir)
        counts["shared_research"] = await ingest_shared_research(palace, self._state_dir)
        counts["stigmergy_marks"] = await ingest_stigmergy_marks(palace, self._state_dir)
        counts["task_completions"] = await ingest_task_completions(palace, self._state_dir)

        # Synthesize compressed lessons
        await synthesize_lessons_learned(palace, self._state_dir)

        total = sum(counts.values())
        logger.info("Archaeology ingestion complete: %d documents total | %s", total, counts)
        return counts

    async def run_forever(self) -> None:
        """Run ingestion continuously on a fixed interval."""
        logger.info(
            "ArchaeologyIngestionDaemon starting (interval=%ds)", self._interval
        )
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("Archaeology ingestion cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(self._interval)


# ---------------------------------------------------------------------------
# Wiring into orchestrate_live.py — the ingestion loop task
# ---------------------------------------------------------------------------

async def start_archaeology_loop(
    state_dir: Path | None = None,
    interval_seconds: int = _DEFAULT_INGESTION_INTERVAL,
) -> asyncio.Task:
    """Start the archaeology ingestion daemon as a background asyncio task.

    Called from orchestrate_live.py during boot, alongside other background
    loops (evolution, witness, etc.).

    Returns the asyncio Task so it can be tracked and cancelled on shutdown.
    """
    daemon = ArchaeologyIngestionDaemon(state_dir=state_dir, interval_seconds=interval_seconds)

    # Run once immediately at boot (before the interval timer)
    try:
        await asyncio.wait_for(daemon.run_once(), timeout=120.0)
    except asyncio.TimeoutError:
        logger.warning("Boot-time archaeology ingestion timed out (120s) — continuing")
    except Exception as exc:
        logger.warning("Boot-time archaeology ingestion failed (non-fatal): %s", exc)

    # Then schedule the recurring loop
    task = asyncio.create_task(daemon.run_forever(), name="archaeology_ingestion")
    return task


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    import json

    logging.basicConfig(level=logging.INFO)
    daemon = ArchaeologyIngestionDaemon()
    counts = await daemon.run_once()
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
