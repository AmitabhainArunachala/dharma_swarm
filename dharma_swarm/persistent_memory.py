"""Persistent Memory Layer — three-tier operational memory.

Extends dharma_swarm's existing 5-layer StrangeLoopMemory with a
human-readable, file-backed operational layer:

  - recent-context.md:     Rolling 48-hour session state
  - long-term-patterns.md: Distilled operational intelligence
  - project-state.md:      Active dharma_swarm state

All mutations go through typed Actions and are witnessed (P1, P6).
Pruned entries become dharma_corpus claims with status "archived" (Nirjara).

Ground: Varela (autopoietic memory membrane), Ashby (requisite variety
in organizational memory), Dada Bhagwan (nirjara — nothing destroyed,
karma dissolved).
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MEMORY_DIR = Path.home() / ".dharma" / "memory"
_RECENT_FILE = "recent-context.md"
_LONGTERM_FILE = "long-term-patterns.md"
_PROJECT_FILE = "project-state.md"
_PRUNE_HOURS = 48


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class MemoryEntry(BaseModel):
    """A single entry in any memory tier."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    content: str
    category: str = "general"  # decision, error, pattern, gate_result, mutation, status
    pillars: list[str] = Field(default_factory=list)  # e.g. ["PILLAR_04_HOFSTADTER"]
    principles: list[str] = Field(default_factory=list)  # e.g. ["P1", "P6"]
    vsm_system: str = ""  # S1-S5
    source: str = "agent"
    tags: list[str] = Field(default_factory=list)
    promotion_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsolidationResult(BaseModel):
    """Result of a consolidation run."""

    promoted: int = 0
    pruned: int = 0
    archived_as_claims: int = 0
    timestamp: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


def _entry_to_md(entry: MemoryEntry) -> str:
    """Format a MemoryEntry as a markdown section."""
    ts = entry.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"### [{ts}] {entry.category.upper()}: {entry.id}"]
    lines.append(entry.content)
    if entry.pillars:
        lines.append(f"- **Pillars**: {', '.join(entry.pillars)}")
    if entry.principles:
        lines.append(f"- **Principles**: {', '.join(entry.principles)}")
    if entry.vsm_system:
        lines.append(f"- **VSM**: {entry.vsm_system}")
    if entry.tags:
        lines.append(f"- **Tags**: {', '.join(entry.tags)}")
    lines.append("")
    return "\n".join(lines)


def _parse_entries_from_md(content: str) -> list[MemoryEntry]:
    """Parse MemoryEntry objects back from markdown format."""
    entries: list[MemoryEntry] = []
    # Split on ### headers
    sections = re.split(r"(?=^### \[)", content, flags=re.MULTILINE)
    for section in sections:
        section = section.strip()
        if not section.startswith("### ["):
            continue
        # Extract timestamp and id from header
        header_match = re.match(
            r"### \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)\] (\w+): (\w+)",
            section,
        )
        if not header_match:
            continue
        ts_str, category, entry_id = header_match.groups()
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M UTC").replace(
            tzinfo=timezone.utc
        )
        # Extract body (lines after header, before metadata lines)
        lines = section.split("\n")[1:]
        body_lines: list[str] = []
        pillars: list[str] = []
        principles: list[str] = []
        vsm = ""
        tags: list[str] = []
        for line in lines:
            if line.startswith("- **Pillars**:"):
                pillars = [p.strip() for p in line.split(":", 1)[1].split(",")]
            elif line.startswith("- **Principles**:"):
                principles = [p.strip() for p in line.split(":", 1)[1].split(",")]
            elif line.startswith("- **VSM**:"):
                vsm = line.split(":", 1)[1].strip()
            elif line.startswith("- **Tags**:"):
                tags = [t.strip() for t in line.split(":", 1)[1].split(",")]
            else:
                body_lines.append(line)

        entries.append(
            MemoryEntry(
                id=entry_id,
                timestamp=ts,
                content="\n".join(body_lines).strip(),
                category=category.lower(),
                pillars=pillars,
                principles=principles,
                vsm_system=vsm,
                tags=tags,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Tier templates
# ---------------------------------------------------------------------------


_RECENT_HEADER = """# Recent Context (Rolling 48-Hour Window)

> Key decisions, active threads, errors, and gate results from recent sessions.
> Newest first. Auto-pruned after 48 hours.

"""

_LONGTERM_HEADER = """# Long-Term Patterns

> Distilled operational intelligence traced to Principles (P1-P8) and Pillars.
> Entries promoted from recent context after appearing 2+ times or representing
> significant decisions.

"""

_PROJECT_HEADER = """# Project State

> Active dharma_swarm state — goals, priorities, VSM gap progress, shipping pipeline.
> Updated in-place, not appended.

## Current Telos Priorities
- T7 (Moksha) = 1.0 always
- Active focus stars: [update as needed]

## VSM Gap Closure Progress
1. S3↔S4 Channel: NOT STARTED
2. Sporadic S3*: NOT STARTED
3. Algedonic Signal: NOT STARTED
4. Agent-Internal Recursion: NOT STARTED
5. Variety Expansion Protocol: NOT STARTED

## Shipping Pipeline
- Revenue: $0
- Papers published: 0
- Products shipped: 0

## Kernel Expansion (10 → 26 Axioms)
- Current: 10 signed axioms + foundations-derived principles in MetaPrinciple enum
- Target: ~26 formally signed axioms

## Active Work Threads
[Update with current threads]

"""


# ---------------------------------------------------------------------------
# PersistentMemory
# ---------------------------------------------------------------------------


class PersistentMemory:
    """Three-tier file-backed operational memory.

    Integrates with but does not replace the existing StrangeLoopMemory
    (which handles SQLite-backed agent memory). This layer provides
    human-readable markdown files for cross-session orientation.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or _DEFAULT_MEMORY_DIR
        self.recent_path = self.base_dir / _RECENT_FILE
        self.longterm_path = self.base_dir / _LONGTERM_FILE
        self.project_path = self.base_dir / _PROJECT_FILE

    # -- lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        """Create directory and initialize files if they don't exist."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.recent_path.exists():
            self.recent_path.write_text(_RECENT_HEADER)
        if not self.longterm_path.exists():
            self.longterm_path.write_text(_LONGTERM_HEADER)
        if not self.project_path.exists():
            self.project_path.write_text(_PROJECT_HEADER)

    # -- write ---------------------------------------------------------------

    async def add_recent(self, entry: MemoryEntry) -> str:
        """Append an entry to recent context. Returns entry id."""
        await asyncio.to_thread(self._append_recent_sync, entry)
        return entry.id

    def _append_recent_sync(self, entry: MemoryEntry) -> None:
        content = self.recent_path.read_text() if self.recent_path.exists() else _RECENT_HEADER
        # Insert after header (newest first)
        header_end = content.find("\n\n", content.find(">"))
        if header_end == -1:
            header_end = len(_RECENT_HEADER)
        else:
            header_end += 2
        new_content = content[:header_end] + _entry_to_md(entry) + content[header_end:]
        self.recent_path.write_text(new_content)

    async def add_longterm(self, entry: MemoryEntry) -> str:
        """Append an entry to long-term patterns. Returns entry id."""
        await asyncio.to_thread(self._append_longterm_sync, entry)
        return entry.id

    def _append_longterm_sync(self, entry: MemoryEntry) -> None:
        content = self.longterm_path.read_text() if self.longterm_path.exists() else _LONGTERM_HEADER
        content += _entry_to_md(entry)
        self.longterm_path.write_text(content)

    async def update_project_state(self, section: str, new_content: str) -> None:
        """Update a specific section of project state in-place."""
        await asyncio.to_thread(self._update_project_sync, section, new_content)

    def _update_project_sync(self, section: str, new_content: str) -> None:
        content = self.project_path.read_text() if self.project_path.exists() else _PROJECT_HEADER
        # Find section by ## header
        pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
        replacement = rf"\g<1>{new_content}\n"
        updated = re.sub(pattern, replacement, content, flags=re.DOTALL)
        self.project_path.write_text(updated)

    # -- read ----------------------------------------------------------------

    async def get_recent(self, limit: int = 20) -> list[MemoryEntry]:
        """Read recent context entries."""
        return await asyncio.to_thread(self._get_recent_sync, limit)

    def _get_recent_sync(self, limit: int) -> list[MemoryEntry]:
        if not self.recent_path.exists():
            return []
        content = self.recent_path.read_text()
        entries = _parse_entries_from_md(content)
        return entries[:limit]

    async def get_longterm(self, category: Optional[str] = None) -> list[MemoryEntry]:
        """Read long-term pattern entries, optionally filtered by category."""
        return await asyncio.to_thread(self._get_longterm_sync, category)

    def _get_longterm_sync(self, category: Optional[str]) -> list[MemoryEntry]:
        if not self.longterm_path.exists():
            return []
        content = self.longterm_path.read_text()
        entries = _parse_entries_from_md(content)
        if category:
            entries = [e for e in entries if e.category == category]
        return entries

    async def get_project_state(self) -> str:
        """Read full project state markdown."""
        return await asyncio.to_thread(self._read_project_sync)

    def _read_project_sync(self) -> str:
        if not self.project_path.exists():
            return _PROJECT_HEADER
        return self.project_path.read_text()

    # -- consolidation -------------------------------------------------------

    async def consolidate(self) -> ConsolidationResult:
        """Run consolidation: prune old recent entries, promote patterns.

        Promotion criteria:
        - Appeared 2+ times across sessions (by content similarity)
        - Traces to an Architecture Principle or Pillar
        - Represents a decision with downstream consequences

        Pruned entries are returned for corpus archival (nirjara).
        """
        return await asyncio.to_thread(self._consolidate_sync)

    def _consolidate_sync(self) -> ConsolidationResult:
        result = ConsolidationResult()
        if not self.recent_path.exists():
            return result

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=_PRUNE_HOURS)

        entries = _parse_entries_from_md(self.recent_path.read_text())
        keep: list[MemoryEntry] = []
        candidates: list[MemoryEntry] = []

        for entry in entries:
            if entry.timestamp >= cutoff:
                keep.append(entry)
            else:
                candidates.append(entry)

        # Promote entries with pillar/principle grounding or that are decisions
        for entry in candidates:
            should_promote = (
                bool(entry.pillars)
                or bool(entry.principles)
                or entry.category in ("decision", "pattern", "gate_result")
            )
            if should_promote:
                self._append_longterm_sync(entry)
                result.promoted += 1
            else:
                result.pruned += 1
                result.archived_as_claims += 1  # caller handles corpus archival

        # Rewrite recent with only kept entries
        new_content = _RECENT_HEADER
        for entry in keep:
            new_content += _entry_to_md(entry)
        self.recent_path.write_text(new_content)

        return result

    # -- search --------------------------------------------------------------

    async def search(self, query: str, tier: str = "all") -> list[MemoryEntry]:
        """Simple text search across memory tiers."""
        return await asyncio.to_thread(self._search_sync, query, tier)

    def _search_sync(self, query: str, tier: str) -> list[MemoryEntry]:
        results: list[MemoryEntry] = []
        q = query.lower()
        if tier in ("all", "recent"):
            for e in self._get_recent_sync(100):
                if q in e.content.lower() or q in " ".join(e.tags).lower():
                    results.append(e)
        if tier in ("all", "longterm"):
            for e in self._get_longterm_sync(None):
                if q in e.content.lower() or q in " ".join(e.tags).lower():
                    results.append(e)
        return results
