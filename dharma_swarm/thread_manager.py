"""Thread Manager — manages active research thread and rotation.

Extracted from PSMV Garden Daemon Spec. Handles thread selection,
rotation modes, focus overrides, and contribution tracking per thread.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.daemon_config import THREAD_PROMPTS, DaemonConfig


class ThreadManager:
    """Manages thread rotation for the swarm daemon cycle."""

    def __init__(self, config: DaemonConfig, state_dir: Path) -> None:
        self._config = config
        self._state_file = state_dir / "thread_state.json"
        self._current_index: int = 0
        self._current_thread: str = config.threads[0]
        self._contributions: dict[str, int] = {t: 0 for t in config.threads}
        self._load_state()

    def _load_state(self) -> None:
        if self._state_file.exists():
            data = json.loads(self._state_file.read_text())
            self._current_index = data.get("current_index", 0)
            self._current_thread = data.get("current_thread", self._config.threads[0])
            self._contributions = data.get("contributions", self._contributions)

    def _save_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps({
            "current_index": self._current_index,
            "current_thread": self._current_thread,
            "contributions": self._contributions,
            "updated": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

    @property
    def current_thread(self) -> str:
        return self._current_thread

    @property
    def current_prompt(self) -> str:
        return THREAD_PROMPTS.get(self._current_thread, "")

    def check_focus_override(self, state_dir: Path) -> str | None:
        """Check if a .FOCUS file exists with a thread override."""
        focus_path = state_dir / self._config.focus_file
        if focus_path.exists():
            thread = focus_path.read_text().strip()
            if thread in self._config.threads:
                return thread
        return None

    def check_inject_override(self, state_dir: Path) -> str | None:
        """Check if a .INJECT file exists with a custom prompt."""
        inject_path = state_dir / self._config.inject_file
        if inject_path.exists():
            return inject_path.read_text().strip() or None
        return None

    def rotate(self) -> str:
        """Select the next thread based on rotation mode."""
        mode = self._config.rotation_mode

        if mode == "sequential":
            self._current_index = (self._current_index + 1) % len(self._config.threads)
            self._current_thread = self._config.threads[self._current_index]
        elif mode == "random":
            self._current_thread = random.choice(self._config.threads)
            self._current_index = self._config.threads.index(self._current_thread)
        elif mode == "continuation":
            pass  # stay on current thread
        else:
            # Default to sequential
            self._current_index = (self._current_index + 1) % len(self._config.threads)
            self._current_thread = self._config.threads[self._current_index]

        self._save_state()
        return self._current_thread

    def record_contribution(self, thread: str | None = None) -> None:
        """Record a contribution to the current (or specified) thread."""
        t = thread or self._current_thread
        self._contributions[t] = self._contributions.get(t, 0) + 1
        self._save_state()

    def stats(self) -> dict[str, Any]:
        """Return thread statistics."""
        return {
            "current_thread": self._current_thread,
            "rotation_mode": self._config.rotation_mode,
            "contributions": dict(self._contributions),
            "total": sum(self._contributions.values()),
        }
