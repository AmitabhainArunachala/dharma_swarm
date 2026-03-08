"""Agent Profile System — model + autonomy + permissions per role.

Profiles bridge skills (what an agent CAN do) with runtime config
(what model, what autonomy level, what permissions). A profile is
created from a skill + optional overrides.

Profiles can be:
  - Auto-generated from SkillDefinitions
  - Loaded from ~/.dharma/profiles/*.json
  - Created programmatically with overrides
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    """How much freedom an agent has to act without confirmation."""
    LOCKED = "locked"           # No autonomous actions — human approves everything
    CAUTIOUS = "cautious"       # Ask before any file writes or bash commands
    BALANCED = "balanced"       # Auto for safe ops (read, search), ask for risky (write, delete)
    AGGRESSIVE = "aggressive"   # Auto most things, ask only for destructive ops
    FULL = "full"               # Complete autonomy — only dharmic gates constrain


# Map string autonomy names to levels
_AUTONOMY_MAP = {
    "locked": AutonomyLevel.LOCKED,
    "cautious": AutonomyLevel.CAUTIOUS,
    "balanced": AutonomyLevel.BALANCED,
    "aggressive": AutonomyLevel.AGGRESSIVE,
    "full": AutonomyLevel.FULL,
    "low": AutonomyLevel.CAUTIOUS,
    "medium": AutonomyLevel.BALANCED,
    "high": AutonomyLevel.AGGRESSIVE,
}


class AgentProfile(BaseModel):
    """Runtime configuration for a specific agent instance."""

    name: str
    skill_name: str = ""
    model: str = "claude-code"
    provider: str = "CLAUDE_CODE"
    autonomy: AutonomyLevel = AutonomyLevel.BALANCED
    max_tokens: int = 4096
    temperature: float = 0.7
    context_budget: int = 30_000
    timeout: int = 300
    permissions: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    thread: Optional[str] = None
    system_prompt_extra: str = ""
    tags: list[str] = Field(default_factory=list)

    def is_allowed(self, action: str) -> bool:
        """Check if an action is allowed by this profile's permissions."""
        # Denied list takes precedence
        for deny in self.denied:
            if deny.lower() in action.lower():
                return False
        # If permissions list is empty, everything not denied is allowed
        if not self.permissions:
            return True
        # Otherwise, must match a permission
        return any(p.lower() in action.lower() for p in self.permissions)


class ProfileManager:
    """Manages agent profiles — loads from disk, creates from skills."""

    def __init__(self, profile_dir: Path | None = None):
        self._dir = profile_dir or (Path.home() / ".dharma" / "profiles")
        self._profiles: dict[str, AgentProfile] = {}
        self._loaded = False

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> dict[str, AgentProfile]:
        """Load all profiles from the profile directory."""
        self._ensure_dir()
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                profile = AgentProfile(**data)
                self._profiles[profile.name] = profile
            except Exception as e:
                logger.warning("Failed to load profile %s: %s", path, e)
        self._loaded = True
        return self._profiles

    def get(self, name: str) -> AgentProfile | None:
        """Get a profile by name."""
        if not self._loaded:
            self.load_all()
        return self._profiles.get(name)

    def save(self, profile: AgentProfile) -> Path:
        """Save a profile to disk."""
        self._ensure_dir()
        path = self._dir / f"{profile.name}.json"
        path.write_text(profile.model_dump_json(indent=2))
        self._profiles[profile.name] = profile
        return path

    def create_from_skill(
        self,
        skill,  # SkillDefinition — avoid circular import
        overrides: dict | None = None,
    ) -> AgentProfile:
        """Create a profile from a SkillDefinition + optional overrides."""
        autonomy = _AUTONOMY_MAP.get(
            skill.autonomy, AutonomyLevel.BALANCED
        )

        profile = AgentProfile(
            name=skill.name,
            skill_name=skill.name,
            model=skill.model,
            provider=skill.provider,
            autonomy=autonomy,
            thread=skill.thread,
            system_prompt_extra=skill.system_prompt,
            tags=skill.tags,
        )

        if overrides:
            for key, val in overrides.items():
                if hasattr(profile, key):
                    if key == "autonomy" and isinstance(val, str):
                        val = _AUTONOMY_MAP.get(val, AutonomyLevel.BALANCED)
                    setattr(profile, key, val)

        return profile

    def list_all(self) -> list[AgentProfile]:
        """List all loaded profiles."""
        if not self._loaded:
            self.load_all()
        return list(self._profiles.values())

    def remove(self, name: str) -> bool:
        """Remove a profile from disk and cache."""
        path = self._dir / f"{name}.json"
        if path.exists():
            path.unlink()
        return self._profiles.pop(name, None) is not None
