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
    """Runtime configuration for a specific agent instance.

    Supports identity evolution: profiles track performance metrics and
    adapt autonomy, temperature, and timeout based on observed outcomes.
    """

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

    # ── Performance tracking (identity evolution) ──
    tasks_completed: int = 0
    tasks_failed: int = 0
    gates_passed: int = 0
    gates_blocked: int = 0
    total_tokens_used: int = 0
    avg_task_duration_s: float = 0.0
    specialization: str = ""  # learned focus area (e.g., "code_review", "research")
    adapted_at: Optional[str] = None  # ISO timestamp of last adaptation

    def is_allowed(self, action: str) -> bool:
        """Check if an action is allowed by this profile's permissions."""
        for deny in self.denied:
            if deny.lower() in action.lower():
                return False
        if not self.permissions:
            return True
        return any(p.lower() in action.lower() for p in self.permissions)

    @property
    def success_rate(self) -> float:
        """Task success rate (0.0 to 1.0)."""
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 0.0

    @property
    def gate_pass_rate(self) -> float:
        """Gate pass rate (0.0 to 1.0)."""
        total = self.gates_passed + self.gates_blocked
        return self.gates_passed / total if total > 0 else 1.0

    def record_task(self, *, success: bool, tokens: int = 0, duration_s: float = 0.0) -> None:
        """Record a task outcome for performance tracking."""
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        self.total_tokens_used += tokens
        # Running average of task duration
        total = self.tasks_completed + self.tasks_failed
        self.avg_task_duration_s = (
            (self.avg_task_duration_s * (total - 1) + duration_s) / total
            if total > 0 else duration_s
        )

    def record_gate(self, *, passed: bool) -> None:
        """Record a gate check outcome."""
        if passed:
            self.gates_passed += 1
        else:
            self.gates_blocked += 1

    def adapt(self) -> dict[str, str]:
        """Evolve profile parameters based on accumulated performance.

        Returns a dict of changes made (empty if no adaptation needed).
        """
        from datetime import datetime, timezone
        changes: dict[str, str] = {}
        total_tasks = self.tasks_completed + self.tasks_failed

        # Need minimum 10 tasks before adapting
        if total_tasks < 10:
            return changes

        # ── Autonomy evolution ──
        # High success + high gate pass → increase autonomy
        # Low success or low gate pass → decrease autonomy
        _LEVELS = list(AutonomyLevel)
        current_idx = _LEVELS.index(self.autonomy)

        if self.success_rate >= 0.85 and self.gate_pass_rate >= 0.90 and current_idx < len(_LEVELS) - 1:
            old = self.autonomy
            self.autonomy = _LEVELS[current_idx + 1]
            changes["autonomy"] = f"{old.value} → {self.autonomy.value}"
        elif self.success_rate < 0.50 and current_idx > 0:
            old = self.autonomy
            self.autonomy = _LEVELS[current_idx - 1]
            changes["autonomy"] = f"{old.value} → {self.autonomy.value}"

        # ── Temperature evolution ──
        # High success → slightly lower temperature (more focused)
        # Low success → slightly higher temperature (more exploratory)
        if self.success_rate >= 0.80 and self.temperature > 0.3:
            old_t = self.temperature
            self.temperature = max(0.3, self.temperature - 0.05)
            if self.temperature != old_t:
                changes["temperature"] = f"{old_t:.2f} → {self.temperature:.2f}"
        elif self.success_rate < 0.50 and self.temperature < 0.9:
            old_t = self.temperature
            self.temperature = min(0.9, self.temperature + 0.05)
            if self.temperature != old_t:
                changes["temperature"] = f"{old_t:.2f} → {self.temperature:.2f}"

        # ── Timeout evolution ──
        # If avg duration > 80% of timeout, increase timeout
        if self.avg_task_duration_s > self.timeout * 0.8:
            old_to = self.timeout
            self.timeout = min(600, int(self.timeout * 1.25))
            if self.timeout != old_to:
                changes["timeout"] = f"{old_to}s → {self.timeout}s"

        if changes:
            self.adapted_at = datetime.now(timezone.utc).isoformat()

        return changes


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
