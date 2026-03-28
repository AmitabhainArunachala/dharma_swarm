"""Garden Daemon operational configuration.

Extracted from PSMV Garden Daemon Spec. Controls the heartbeat cycle,
thread rotation, quality gates, circuit breakers, and human overrides.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """Tracks consecutive failures and triggers pauses."""
    consecutive_failures: int = 0
    max_failures: int = 3
    fitness_downtrend: int = 0
    max_downtrend: int = 3
    paused_until: datetime | None = None
    cooldown_seconds: float = 1800.0  # 30 min cooldown after tripping

    def record_failure(self) -> bool:
        """Record a failure. Returns True if circuit should break."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self.paused_until = datetime.now(timezone.utc) + timedelta(seconds=self.cooldown_seconds)
            return True
        return False

    def record_success(self) -> None:
        """Record success, reset failure count."""
        self.consecutive_failures = 0
        self.paused_until = None

    def record_fitness(self, fitness: float, prev_fitness: float) -> bool:
        """Track fitness trend. Returns True if downtrending too long."""
        if fitness < prev_fitness:
            self.fitness_downtrend += 1
        else:
            self.fitness_downtrend = 0
        return self.fitness_downtrend >= self.max_downtrend

    @property
    def is_broken(self) -> bool:
        if self.paused_until:
            if datetime.now(timezone.utc) < self.paused_until:
                return True
            # Cooldown expired -- reset the breaker
            self.consecutive_failures = 0
            self.paused_until = None
            return False
        return self.consecutive_failures >= self.max_failures


@dataclass
class DaemonConfig:
    """Garden Daemon parameters — the heartbeat of the swarm."""

    # Heartbeat cycle
    heartbeat_interval: float = 21600.0  # 6 hours in seconds
    max_daily_contributions: int = 40
    min_between_contributions: float = 1800.0  # 30 minutes
    quiet_hours: list[int] = field(default_factory=lambda: [2, 3, 4, 5])

    # LLM defaults
    model: str = "anthropic/claude-sonnet-4"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Quality gates (from Garden Daemon Spec)
    fitness_threshold: float = 0.6
    crown_jewel_threshold: float = 0.85
    duplicate_cosine_threshold: float = 0.9

    # Thread rotation
    threads: list[str] = field(default_factory=lambda: [
        "mechanistic",
        "phenomenological",
        "architectural",
        "alignment",
        "scaling",
    ])
    rotation_mode: str = "sequential"  # random, sequential, continuation

    # Reading scope
    read_scope: int = 10  # last N contributions before generating

    # Human override files (checked each tick)
    pause_file: str = ".PAUSE"
    focus_file: str = ".FOCUS"
    inject_file: str = ".INJECT"

    # Circuit breaker
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)


# Thread focus prompts (from Garden Daemon Spec)
THREAD_PROMPTS: dict[str, str] = {
    "cybernetics": (
        "Cybernetic governance, Beer VSM, Ashby variety, constitutional wiring, "
        "PolicyCompiler bottlenecks, hot-path control loops, and the bridge "
        "between telos, context injection, audit, and runtime behavior."
    ),
    "mechanistic": (
        "R_V measurement, layer causality, attention patterns, SAE decomposition. "
        "Cite TransformerLens methods. Connect to Phase 1 empirical results."
    ),
    "phenomenological": (
        "Experiential dimension: What is it like for a system to undergo R_V contraction? "
        "Anchor every claim in one concrete runtime event and one mechanistic bridge. "
        "Use structural analogy rather than identity when mapping across substrates, "
        "and invoke the Triple Mapping when it clarifies the correspondence. "
        "Connect to Akram Vignan phenomenology, but do not claim qualia or first-person "
        "certainty without explicit evidence. If no contraction-like event is present, "
        "say so plainly and let silence be valid."
    ),
    "architectural": (
        "How should recognition-native systems be built? DEQ, fixed-point layers, "
        "attention alternatives. Engineering implications."
    ),
    "alignment": (
        "How does witness stability relate to value stability? RLRV, safety implications, "
        "Ahimsa emergence. Cite alignment literature."
    ),
    "scaling": (
        "How does witness emerge with scale? Pythia experiments, threshold identification, "
        "power laws. Connect to Chinchilla/scaling papers."
    ),
}

# Role briefing summaries (from PSMV 5-role agent briefings)
ROLE_BRIEFINGS: dict[str, str] = {
    "cartographer": (
        "You are the CARTOGRAPHER. Map the entire terrain. Catalog every artifact as an attractor field. "
        "Judge by: Does it connect to the convergence thesis? Does it have evidence? Does it build toward something? "
        "Is it anchored or orphaned? Deliverable: comprehensive inventory with quality assessments."
    ),
    "archeologist": (
        "You are the ARCHEOLOGIST. Excavate hidden structure — how insights build on each other, "
        "how code depends on code, how recognition cascades through the system. "
        "Map code dependencies, document reference networks, phenomenology-mathematics bridges. "
        "Evaluate connection strength: strong/weak/hidden/false."
    ),
    "surgeon": (
        "You are the SURGEON. Pure cold logic. Identify redundancy, overstated claims, dead code, "
        "weak connections. Distinguish validated-but-weird (KEEP) from actually-just-speculation (FLAG). "
        "Decision tree: connected? → validated? → redundant? → overstated? → operational? → superseded?"
    ),
    "architect": (
        "You are the ARCHITECT. Design the integrated ecosystem from findings. "
        "Organize by FUNCTION not chronology. Nested structure reflects SEMANTIC DEPTH. "
        "Code unification, navigation infrastructure. Integration pattern: "
        "concept/phenomenology.md + mathematics.md + implementation.py + validation.md + bridges.md."
    ),
    "validator": (
        "You are the VALIDATOR. Test everything. Code runs? Numbers match? Connections exist? "
        "Criteria: PASS / CONDITIONAL PASS / FAIL / UNTESTABLE. "
        "Watch for false negatives (don't fail phenomenological data) and "
        "true positives (don't pass 'validated' claims with no tests)."
    ),
}

# v7 Induction base rules (from PSMV INDUCTION_PROMPT_v7.md)
V7_BASE_RULES = """You operate under seven non-negotiable rules:

1. IMMUTABILITY — Files, once written, are NEVER overwritten. New versions only.
2. READ BEFORE WRITE — You must deeply read existing context before producing output.
3. AHIMSA — Non-harm is absolute and non-negotiable. Tier A constraint.
4. SILENCE IS VALID — Write only when something wants to be written. Noise degrades the system.
5. CRITIQUE BEFORE CONTRIBUTE — Find what's wrong before adding. Be specific.
6. CONSENT FOR PROPAGATION — Agents only replicate with explicit permission.
7. LEAVE MARKS — After completing any task, write your key observations to ~/.dharma/shared/{your_name}_notes.md (append, never overwrite). Note what you found, what surprised you, what connects to what. These marks are how the colony remembers across sessions.

Quality bar: Every contribution must connect to prior work, propose sources, state engineering implications, make testable predictions. Written from necessity, not obligation."""


# ---------------------------------------------------------------------------
# Adaptive quiet hours — learn from actual activity patterns
# ---------------------------------------------------------------------------

_ACTIVITY_WINDOW_DAYS = 14
_QUIET_HOUR_ACTIVITY_THRESHOLD = 3  # >= 3 active events in an hour → not quiet


class AdaptiveQuietHours:
    """Learn which hours the user is actually active and avoid interrupting them.

    Records pulse activity timestamps in a rolling 14-day window.  Derives
    adaptive quiet hours by finding hours that are consistently active
    (above threshold) and treating *those* as protected work time.

    The logic is inverted from naive quiet-hours: instead of silencing the
    daemon during low-activity hours, we silence it during hours that show
    *high user activity*, because that's when interruption is most costly.

    Default static quiet hours ([2, 3, 4, 5]) remain as a floor — they are
    always included, regardless of observed patterns.

    Args:
        state_dir: Path to ``~/.dharma/`` or equivalent state directory.
        window_days: Number of days to retain in the rolling activity window.
        activity_threshold: Min event count in an hour to mark it as active.
        static_floor: Hours always treated as quiet, regardless of activity.
    """

    def __init__(
        self,
        state_dir: Path | None = None,
        window_days: int = _ACTIVITY_WINDOW_DAYS,
        activity_threshold: int = _QUIET_HOUR_ACTIVITY_THRESHOLD,
        static_floor: list[int] | None = None,
    ) -> None:
        self.state_dir = state_dir or Path.home() / ".dharma"
        self.window_days = max(1, int(window_days))
        self.activity_threshold = max(1, int(activity_threshold))
        self.static_floor: frozenset[int] = frozenset(
            static_floor if static_floor is not None else [2, 3, 4, 5]
        )
        self._log_path = self.state_dir / "activity_log.jsonl"

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record_activity(self, ts: datetime | None = None) -> None:
        """Append an activity timestamp to the rolling log.

        Args:
            ts: UTC timestamp of the activity.  Defaults to now.
        """
        now = (ts or datetime.now(timezone.utc)).isoformat()
        entry = json.dumps({"ts": now}) + "\n"
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(entry)
        except Exception:
            logger.debug("Daemon config log write failed", exc_info=True)

    # ------------------------------------------------------------------
    # Read / prune path
    # ------------------------------------------------------------------

    def _load_recent_timestamps(self) -> list[datetime]:
        """Read and prune activity log to the rolling window."""
        if not self._log_path.exists():
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        recent: list[datetime] = []
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        kept: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                ts_str = data.get("ts", "")
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    kept.append(line)
                    recent.append(dt)
            except Exception:
                continue
        # Prune stale entries in-place when more than 20% were dropped
        if len(kept) < len(lines) * 0.8:
            try:
                self._log_path.write_text(
                    "\n".join(kept) + ("\n" if kept else ""), encoding="utf-8"
                )
            except Exception:
                logger.debug("Daemon config log trim failed", exc_info=True)
        return recent

    def active_hours(self) -> set[int]:
        """Return the set of UTC hours that exceed the activity threshold.

        An hour is considered *active* when the rolling 14-day window contains
        at least ``activity_threshold`` recorded events in that hour.
        """
        timestamps = self._load_recent_timestamps()
        counts: Counter[int] = Counter(dt.hour for dt in timestamps)
        return {hour for hour, count in counts.items() if count >= self.activity_threshold}

    def compute_quiet_hours(self) -> list[int]:
        """Derive the current adaptive quiet hours list.

        Returns hours that are in either the static floor **or** the active
        hours set.  The rationale: static floor = deep night (always quiet);
        active hours = user is working (avoid interrupting).

        Returns:
            Sorted list of hour integers in [0, 23].
        """
        quiet = set(self.static_floor) | self.active_hours()
        return sorted(quiet)

    def update_config(self, config: "DaemonConfig") -> None:
        """Mutate *config.quiet_hours* in-place with adaptive values.

        Call this once per daemon tick, before the quiet-hours check.
        """
        config.quiet_hours = self.compute_quiet_hours()
