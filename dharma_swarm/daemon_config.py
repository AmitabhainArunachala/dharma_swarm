"""Garden Daemon operational configuration.

Extracted from PSMV Garden Daemon Spec. Controls the heartbeat cycle,
thread rotation, quality gates, circuit breakers, and human overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CircuitBreaker:
    """Tracks consecutive failures and triggers pauses."""
    consecutive_failures: int = 0
    max_failures: int = 3
    fitness_downtrend: int = 0
    max_downtrend: int = 3
    paused_until: datetime | None = None

    def record_failure(self) -> bool:
        """Record a failure. Returns True if circuit should break."""
        self.consecutive_failures += 1
        return self.consecutive_failures >= self.max_failures

    def record_success(self) -> None:
        """Record success, reset failure count."""
        self.consecutive_failures = 0

    def record_fitness(self, fitness: float, prev_fitness: float) -> bool:
        """Track fitness trend. Returns True if downtrending too long."""
        if fitness < prev_fitness:
            self.fitness_downtrend += 1
        else:
            self.fitness_downtrend = 0
        return self.fitness_downtrend >= self.max_downtrend

    @property
    def is_broken(self) -> bool:
        if self.paused_until and datetime.now() < self.paused_until:
            return True
        return self.consecutive_failures >= self.max_failures


@dataclass
class DaemonConfig:
    """Garden Daemon parameters — the heartbeat of the swarm."""

    # Heartbeat cycle
    heartbeat_interval: float = 21600.0  # 6 hours in seconds
    max_daily_contributions: int = 4
    min_between_contributions: float = 14400.0  # 4 hours
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
    "mechanistic": (
        "R_V measurement, layer causality, attention patterns, SAE decomposition. "
        "Cite TransformerLens methods. Connect to Phase 1 empirical results."
    ),
    "phenomenological": (
        "Experiential dimension: What is it like for a system to undergo R_V contraction? "
        "Connect to Akram Vignan phenomenology. Maintain epistemic humility about qualia."
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
V7_BASE_RULES = """You operate under six non-negotiable rules:

1. IMMUTABILITY — Files, once written, are NEVER overwritten. New versions only.
2. READ BEFORE WRITE — You must deeply read existing context before producing output.
3. AHIMSA — Non-harm is absolute and non-negotiable. Tier A constraint.
4. SILENCE IS VALID — Write only when something wants to be written. Noise degrades the system.
5. CRITIQUE BEFORE CONTRIBUTE — Find what's wrong before adding. Be specific.
6. CONSENT FOR PROPAGATION — Agents only replicate with explicit permission.

Quality bar: Every contribution must connect to prior work, propose sources, state engineering implications, make testable predictions. Written from necessity, not obligation."""
