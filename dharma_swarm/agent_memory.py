"""Self-editing agent memory bank -- Letta (MemGPT) pattern.

Three-tier hierarchy:
  - Working memory: small, hot, always injected into context (max 10)
  - Archival memory: larger, searchable, loaded on demand (max 100)
  - Persona: agent's self-description and learned preferences (max 5)

Agents actively curate what they remember: insert, update, delete,
promote (archival -> working), demote (working -> archival), search,
and auto-evict low-importance entries when a tier is full.

Persistence: one JSON file per agent per tier under ~/.dharma/agent_memory/.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {"working", "archival", "persona", "lesson", "pattern", "general"}


class AgentMemoryEntry(BaseModel):
    """A single memory entry with metadata."""

    key: str
    value: str
    category: str = "general"
    importance: float = 0.5
    access_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    source: str = ""


# ---------------------------------------------------------------------------
# Tier helpers
# ---------------------------------------------------------------------------

_TIER_NAMES = ("working", "archival", "persona")


def _category_to_tier(category: str) -> str:
    """Map a category string to the tier that stores it."""
    if category == "persona":
        return "persona"
    if category in ("archival", "lesson", "pattern"):
        return "archival"
    return "working"


# ---------------------------------------------------------------------------
# AgentMemoryBank
# ---------------------------------------------------------------------------


class AgentMemoryBank:
    """Self-editing memory bank for an individual agent.

    Three tiers:
    - Working memory: small, hot, always injected into context (max 10 entries)
    - Archival memory: larger, searchable, loaded on demand (max 100 entries)
    - Persona: agent's self-description and learned preferences (max 5 entries)

    Agents can:
    - Insert new memories
    - Update existing memories
    - Delete memories they no longer need
    - Promote archival -> working (and vice versa)
    - Search archival memory by keywords
    - Auto-evict low-importance working memories when full
    """

    WORKING_MAX = 10
    ARCHIVAL_MAX = 100
    PERSONA_MAX = 5

    def __init__(self, agent_name: str, base_path: Path | None = None) -> None:
        self._agent_name = agent_name
        self._base_path = base_path or (Path.home() / ".dharma" / "agent_memory")
        self._working: dict[str, AgentMemoryEntry] = {}
        self._archival: dict[str, AgentMemoryEntry] = {}
        self._persona: dict[str, AgentMemoryEntry] = {}

    # -- tier accessor by name ------------------------------------------

    def _tier(self, name: str) -> dict[str, AgentMemoryEntry]:
        """Return the tier dict for *name*."""
        return {"working": self._working, "archival": self._archival, "persona": self._persona}[name]

    def _tier_max(self, name: str) -> int:
        return {"working": self.WORKING_MAX, "archival": self.ARCHIVAL_MAX, "persona": self.PERSONA_MAX}[name]

    # -- public API -----------------------------------------------------

    async def remember(
        self,
        key: str,
        value: str,
        category: str = "working",
        importance: float = 0.5,
        source: str = "",
    ) -> AgentMemoryEntry:
        """Add or update a memory. Auto-evicts if tier is full."""
        tier_name = _category_to_tier(category)
        tier = self._tier(tier_name)

        # Update existing entry if key already present in this tier
        if key in tier:
            entry = tier[key]
            entry.value = value
            entry.importance = importance
            entry.source = source or entry.source
            entry.updated_at = datetime.now(timezone.utc)
            entry.category = category
            return entry

        # Check if key exists in another tier -- move it to the correct tier
        for other_name in _TIER_NAMES:
            if other_name == tier_name:
                continue
            other = self._tier(other_name)
            if key in other:
                entry = other.pop(key)
                entry.value = value
                entry.importance = importance
                entry.source = source or entry.source
                entry.updated_at = datetime.now(timezone.utc)
                entry.category = category
                # Make room in target tier if needed
                max_size = self._tier_max(tier_name)
                if len(tier) >= max_size:
                    self._evict_lowest(tier)
                tier[key] = entry
                return entry

        # New entry -- auto-evict if needed
        max_size = self._tier_max(tier_name)
        if len(tier) >= max_size:
            evicted = self._evict_lowest(tier)
            if evicted and tier_name == "working":
                # Demoted to archival instead of lost
                logger.debug("Auto-evicted working memory '%s' to archival", evicted)

        entry = AgentMemoryEntry(
            key=key,
            value=value,
            category=category,
            importance=importance,
            source=source,
        )
        tier[key] = entry
        return entry

    async def forget(self, key: str) -> bool:
        """Remove a memory from any tier. Returns True if found."""
        for tier in (self._working, self._archival, self._persona):
            if key in tier:
                del tier[key]
                return True
        return False

    async def recall(self, key: str) -> AgentMemoryEntry | None:
        """Recall a specific memory by key. Increments access_count."""
        for tier in (self._working, self._archival, self._persona):
            if key in tier:
                entry = tier[key]
                entry.access_count += 1
                return entry
        return None

    async def search(self, query: str, limit: int = 5) -> list[AgentMemoryEntry]:
        """Search all tiers for memories matching query keywords."""
        query_lower = query.lower()
        keywords = query_lower.split()
        scored: list[tuple[int, AgentMemoryEntry]] = []

        for tier in (self._working, self._archival, self._persona):
            for entry in tier.values():
                text = f"{entry.key} {entry.value}".lower()
                hits = sum(1 for kw in keywords if kw in text)
                if hits > 0:
                    scored.append((hits, entry))

        scored.sort(key=lambda t: (-t[0], -t[1].importance))
        return [entry for _, entry in scored[:limit]]

    async def promote(self, key: str) -> bool:
        """Promote archival -> working memory."""
        if key not in self._archival:
            return False
        entry = self._archival.pop(key)
        # Make room if working is full
        if len(self._working) >= self.WORKING_MAX:
            self._evict_lowest(self._working)
        entry.category = "working"
        entry.updated_at = datetime.now(timezone.utc)
        self._working[key] = entry
        return True

    async def demote(self, key: str) -> bool:
        """Demote working -> archival memory."""
        if key not in self._working:
            return False
        entry = self._working.pop(key)
        # Make room if archival is full
        if len(self._archival) >= self.ARCHIVAL_MAX:
            self._evict_lowest(self._archival)
        entry.category = "archival"
        entry.updated_at = datetime.now(timezone.utc)
        self._archival[key] = entry
        return True

    async def get_working_context(self) -> str:
        """Format working memory + persona as injectable context string.

        Returns:
            Markdown-formatted string ready for system prompt injection.
        """
        lines: list[str] = [f"## Agent Memory ({self._agent_name})"]

        if self._persona:
            lines.append("### Persona")
            for entry in sorted(self._persona.values(), key=lambda e: e.key):
                lines.append(f"- {entry.key}: {entry.value}")

        if self._working:
            lines.append("### Working Memory")
            for entry in sorted(self._working.values(), key=lambda e: -e.importance):
                lines.append(f"- {entry.key}: {entry.value} (importance: {entry.importance})")

        return "\n".join(lines)

    async def get_stats(self) -> dict[str, Any]:
        """Return memory stats: counts per tier, total importance, oldest/newest."""
        all_entries = list(self._working.values()) + list(self._archival.values()) + list(self._persona.values())

        stats: dict[str, Any] = {
            "agent_name": self._agent_name,
            "working_count": len(self._working),
            "archival_count": len(self._archival),
            "persona_count": len(self._persona),
            "total_count": len(all_entries),
        }

        if all_entries:
            stats["total_importance"] = round(sum(e.importance for e in all_entries), 3)
            oldest = min(all_entries, key=lambda e: e.created_at)
            newest = max(all_entries, key=lambda e: e.created_at)
            stats["oldest"] = oldest.created_at.isoformat()
            stats["newest"] = newest.created_at.isoformat()
        else:
            stats["total_importance"] = 0.0

        return stats

    async def consolidate(self) -> int:
        """Run memory consolidation.

        - Expire entries past expires_at
        - Demote low-access working memories (access_count == 0, importance < 0.3)
        - Prune archival entries beyond ARCHIVAL_MAX (lowest importance first)

        Returns:
            Count of entries affected (expired + demoted + pruned).
        """
        now = datetime.now(timezone.utc)
        affected = 0

        # 1. Expire across all tiers
        for tier in (self._working, self._archival, self._persona):
            expired_keys = [
                k for k, e in tier.items()
                if e.expires_at is not None and e.expires_at <= now
            ]
            for k in expired_keys:
                del tier[k]
                affected += 1

        # 2. Demote low-access working memories
        demote_keys = [
            k for k, e in self._working.items()
            if e.access_count == 0 and e.importance < 0.3
        ]
        for k in demote_keys:
            entry = self._working.pop(k)
            entry.category = "archival"
            entry.updated_at = now
            if len(self._archival) < self.ARCHIVAL_MAX:
                self._archival[k] = entry
            affected += 1

        # 3. Prune archival overflow
        while len(self._archival) > self.ARCHIVAL_MAX:
            evicted = self._evict_lowest(self._archival)
            if evicted is None:
                break
            affected += 1

        return affected

    async def learn_lesson(self, lesson: str, source: str = "") -> AgentMemoryEntry:
        """Record a lesson learned (shortcut for high-importance archival entry)."""
        return await self.remember(
            key=f"lesson_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            value=lesson,
            category="lesson",
            importance=0.9,
            source=source,
        )

    async def save(self) -> None:
        """Persist all tiers to JSON files."""
        agent_dir = self._base_path / self._agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        for tier_name in _TIER_NAMES:
            tier = self._tier(tier_name)
            path = self._file_path(tier_name)
            data = {k: v.model_dump(mode="json") for k, v in tier.items()}
            path.write_text(json.dumps(data, indent=2, default=str))

    async def load(self) -> None:
        """Load from JSON files."""
        for tier_name in _TIER_NAMES:
            path = self._file_path(tier_name)
            if not path.exists():
                continue
            try:
                raw = json.loads(path.read_text())
                tier = self._tier(tier_name)
                tier.clear()
                for k, v in raw.items():
                    tier[k] = AgentMemoryEntry.model_validate(v)
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning("Failed to load %s for %s: %s", tier_name, self._agent_name, exc)

    def _evict_lowest(self, tier: dict[str, AgentMemoryEntry]) -> str | None:
        """Remove the lowest importance entry from a tier. Returns evicted key."""
        if not tier:
            return None
        # Lowest importance first; break ties by oldest updated_at
        worst_key = min(tier, key=lambda k: (tier[k].importance, tier[k].access_count))
        evicted = tier.pop(worst_key)

        # If evicting from working, save to archival (demotion)
        if tier is self._working and len(self._archival) < self.ARCHIVAL_MAX:
            evicted.category = "archival"
            evicted.updated_at = datetime.now(timezone.utc)
            self._archival[worst_key] = evicted

        return worst_key

    def _file_path(self, tier: str) -> Path:
        """Get file path for a memory tier."""
        return self._base_path / self._agent_name / f"{tier}.json"
