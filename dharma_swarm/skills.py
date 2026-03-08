"""Skill Discovery and Registry — auto-discovers SKILL.md files.

Inspired by Warp's Oz skill system but evolved: skills are discoverable
markdown files with YAML frontmatter. Hot-reloadable. Matchable by
keyword/intent. The bridge between human-readable role definitions
and machine-executable agent configurations.

Skill files live in:
  - dharma_swarm/skills/          (built-in)
  - ~/.dharma/skills/             (user-defined)
  - .dharma/skills/               (project-local)

Format: SKILL.md with YAML frontmatter (see skills/ directory for examples).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _safe_int(value: object, default: int = 5) -> int:
    """Convert *value* to int, returning *default* on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return default


# ── Skill Definition ──────────────────────────────────────────────────

class ContextWeights(BaseModel):
    """How much of each context layer this skill needs (0.0-1.0)."""
    vision: float = 0.2
    research: float = 0.2
    engineering: float = 0.3
    ops: float = 0.2
    swarm: float = 0.1


class SkillDefinition(BaseModel):
    """A discovered skill parsed from a SKILL.md file."""

    name: str
    model: str = "claude-code"
    provider: str = "CLAUDE_CODE"
    autonomy: str = "balanced"  # locked/cautious/balanced/aggressive/full
    thread: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    context_weights: ContextWeights = Field(default_factory=ContextWeights)
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    description: str = ""
    system_prompt: str = ""
    source_path: Optional[str] = None
    priority: int = 5  # 1=critical, 10=nice-to-have


# ── YAML Frontmatter Parser ──────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_yaml_lite(text: str) -> dict:
    """Minimal YAML parser for frontmatter — no PyYAML dependency.

    Handles: key: value, key: [a, b, c], nested objects (one level).
    Good enough for SKILL.md files without pulling in a YAML library.
    """
    result: dict = {}
    current_key: str | None = None
    current_dict: dict | None = None

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Nested key (indented)
        if line.startswith("  ") and current_key and ":" in stripped:
            if current_dict is None:
                current_dict = {}
                result[current_key] = current_dict
            k, v = stripped.split(":", 1)
            current_dict[k.strip()] = _parse_value(v.strip())
            continue

        # Top-level key
        if ":" in stripped:
            current_dict = None
            k, v = stripped.split(":", 1)
            current_key = k.strip()
            val = v.strip()
            if val:
                result[current_key] = _parse_value(val)
            # If no value, might be a dict (handled in next iterations)

    return result


def _parse_value(val: str):
    """Parse a single YAML value."""
    # Array: [a, b, c]
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1]
        return [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
    # Boolean
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    # Number
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        pass
    # String (strip quotes)
    return val.strip("'\"")


def parse_skill_file(path: Path) -> SkillDefinition | None:
    """Parse a SKILL.md file into a SkillDefinition.

    Returns None if the file can't be parsed.
    """
    try:
        content = path.read_text()
    except Exception:
        return None

    # Extract frontmatter
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    frontmatter = _parse_yaml_lite(match.group(1))
    body = content[match.end():].strip()

    # Extract description (first paragraph) and system_prompt (rest)
    parts = body.split("\n\n", 1)
    description = parts[0].lstrip("# ").strip() if parts else ""
    system_prompt = parts[1].strip() if len(parts) > 1 else ""

    # Build context weights
    cw_data = frontmatter.get("context_weights", {})
    if isinstance(cw_data, dict):
        context_weights = ContextWeights(**{
            k: float(v) for k, v in cw_data.items()
            if k in ContextWeights.model_fields
        })
    else:
        context_weights = ContextWeights()

    name = frontmatter.get("name", path.stem.replace(".skill", ""))

    return SkillDefinition(
        name=name,
        model=str(frontmatter.get("model", "claude-code")),
        provider=str(frontmatter.get("provider", "CLAUDE_CODE")),
        autonomy=str(frontmatter.get("autonomy", "balanced")),
        thread=frontmatter.get("thread"),
        tools=frontmatter.get("tools", []),
        context_weights=context_weights,
        tags=frontmatter.get("tags", []),
        keywords=frontmatter.get("keywords", []),
        description=description,
        system_prompt=system_prompt,
        source_path=str(path),
        priority=_safe_int(frontmatter.get("priority", 5), default=5),
    )


# ── Skill Registry ───────────────────────────────────────────────────

# Default search paths for skill files
_DEFAULT_SKILL_DIRS = [
    Path(__file__).parent / "skills",       # built-in
    Path.home() / ".dharma" / "skills",     # user-defined
    Path(".dharma") / "skills",             # project-local
]


class SkillRegistry:
    """Discovers, caches, and hot-reloads skills from SKILL.md files.

    Skills are matched to tasks via keywords, tags, and name.
    Hot-reload checks file mtimes on each access.
    """

    def __init__(self, skill_dirs: list[Path] | None = None):
        self._dirs = skill_dirs or _DEFAULT_SKILL_DIRS
        self._skills: dict[str, SkillDefinition] = {}
        self._mtimes: dict[str, float] = {}
        self._last_scan: float = 0.0
        self._scan_interval: float = 5.0  # seconds between re-scans

    def discover(self) -> dict[str, SkillDefinition]:
        """Scan all skill directories, parse SKILL.md files.

        Returns dict of name -> SkillDefinition.
        """
        found: dict[str, SkillDefinition] = {}

        for skill_dir in self._dirs:
            if not skill_dir.exists():
                continue
            for path in sorted(skill_dir.glob("*.md")):
                skill = parse_skill_file(path)
                if skill:
                    found[skill.name] = skill
                    self._mtimes[str(path)] = path.stat().st_mtime

        self._skills = found
        self._last_scan = time.time()
        logger.info("Discovered %d skills from %d directories",
                     len(found), len(self._dirs))
        return found

    def get(self, name: str) -> SkillDefinition | None:
        """Get a skill by exact name. Auto-discovers if empty."""
        if not self._skills:
            self.discover()
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        """List all discovered skills."""
        if not self._skills:
            self.discover()
        return list(self._skills.values())

    def hot_reload(self) -> list[str]:
        """Check for changed skill files, reload them.

        Returns list of skill names that were reloaded.
        """
        reloaded: list[str] = []

        for skill_dir in self._dirs:
            if not skill_dir.exists():
                continue
            for path in skill_dir.glob("*.md"):
                path_str = str(path)
                current_mtime = path.stat().st_mtime
                if path_str in self._mtimes and current_mtime > self._mtimes[path_str]:
                    skill = parse_skill_file(path)
                    if skill:
                        self._skills[skill.name] = skill
                        self._mtimes[path_str] = current_mtime
                        reloaded.append(skill.name)
                        logger.info("Hot-reloaded skill: %s", skill.name)

        return reloaded

    def match(self, query: str, top_k: int = 3) -> list[SkillDefinition]:
        """Match skills to a natural language query.

        Uses keyword overlap scoring. Returns top_k best matches.
        """
        if not self._skills:
            self.discover()

        # Auto-reload if stale
        if time.time() - self._last_scan > self._scan_interval:
            self.hot_reload()
            self._last_scan = time.time()

        query_words = set(query.lower().split())
        scored: list[tuple[float, SkillDefinition]] = []

        for skill in self._skills.values():
            score = 0.0

            # Name match (highest weight)
            if skill.name.lower() in query.lower():
                score += 10.0

            # Keyword match
            for kw in skill.keywords:
                if kw.lower() in query.lower():
                    score += 3.0

            # Tag match
            for tag in skill.tags:
                if tag.lower() in query.lower():
                    score += 2.0

            # Word overlap with description
            desc_words = set(skill.description.lower().split())
            overlap = len(query_words & desc_words)
            score += overlap * 0.5

            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    def match_best(self, query: str) -> SkillDefinition | None:
        """Return the single best matching skill, or None."""
        matches = self.match(query, top_k=1)
        return matches[0] if matches else None
