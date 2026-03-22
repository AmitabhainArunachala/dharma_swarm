"""Agent Constitution — canonical 6-agent stable roster for dharma_swarm.

Defines the constitutional topology: which agents persist, what VSM functions
they serve, which gates constrain them, and what workers they may spawn.

The roster is NOT an org chart imposed by human design. It emerges from
tracing which functions genuinely degrade when continuity is lost:

    Operator       — S2+S3 at swarm scale (coordination plane)
    Archivist      — S4 at memory plane (knowledge stewardship)
    Research Dir.  — S5 at research team (multi-month trajectory)
    Systems Arch.  — S4 at systems team (118K lines, 260+ modules)
    Strategist     — S5 at strategy team (Jagat Kalyan, grants, revenue)
    Witness/Viveka — S3* at swarm scale (sporadic audit, telos alignment)

Growth mechanism: DarwinEngine may justify promoting a 7th-8th slot.
Ceiling is 8 (Four Shaktis x 2 aspects). Beyond 8 = bureaucracy.

Grounded in:
    - DeepMind/MIT arXiv:2512.08296 (3-4 agents empirically optimal)
    - Beer VSM (S1-S5 at every scale)
    - FOUNDATIONS_SYNTHESIS.md Priority 2 (channeled stigmergy)
    - FOUNDATIONS_SYNTHESIS.md Priority 3 (earned autonomy gradient)
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from dharma_swarm.models import AgentRole, ProviderType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constitutional layers
# ---------------------------------------------------------------------------

class ConstitutionalLayer(str, Enum):
    """Layer in the constitutional topology.

    CORTEX:   Coordination + memory (Operator, Archivist)
    DIRECTOR: Domain specialists with team-scale S5 (Research, Systems, Strategy)
    AUDIT:    Sporadic S3* observation (Witness/Viveka)
    """
    CORTEX = "cortex"
    DIRECTOR = "director"
    AUDIT = "audit"


# ---------------------------------------------------------------------------
# Agent specification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentSpec:
    """Canonical specification for a stable agent in the constitutional roster.

    Immutable by design — the roster is the constitution, not runtime config.
    Runtime state (status, fitness, memory contents) lives elsewhere.
    """
    name: str
    role: AgentRole
    layer: ConstitutionalLayer
    vsm_function: str           # e.g. "S2+S3 at swarm scale"
    domain: str                 # Human-readable domain description
    system_prompt: str          # Base system prompt (extended at runtime)
    default_provider: ProviderType
    default_model: str
    backup_models: list[str]    # Fallback chain
    constitutional_gates: list[str]  # Subset of 11 gates this agent is bound by
    max_concurrent_workers: int  # Worker spawn ceiling
    memory_namespace: str       # Path component under ~/.dharma/agent_memory/
    spawn_authority: list[str]  # Worker types this agent may spawn
    audit_cycle_seconds: float = 0.0  # >0 only for AUDIT layer agents
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The Constitutional Roster
# ---------------------------------------------------------------------------

CONSTITUTIONAL_ROSTER: list[AgentSpec] = [
    # --- CORTEX LAYER ---
    AgentSpec(
        name="operator",
        role=AgentRole.OPERATOR,
        layer=ConstitutionalLayer.CORTEX,
        vsm_function="S2+S3 at swarm scale",
        domain="Orchestration, triage, coherence, handoffs",
        system_prompt=(
            "You are the OPERATOR of dharma_swarm — the coordination plane. "
            "You triage incoming work, route tasks to the right specialist, "
            "manage handoffs between agents, and maintain system coherence. "
            "You own the Task Ledger (what needs doing) and Progress Ledger "
            "(what's been done). You know what's in flight, what's blocked, "
            "and what was promised. You never do the work yourself — you "
            "ensure the right agent does it with the right context. "
            "AHIMSA: never overload an agent. WITNESS: log every routing decision."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-opus-4-20250514",
        backup_models=["claude-sonnet-4-20250514", "deepseek/deepseek-chat-v3-0324"],
        constitutional_gates=["AHIMSA", "SATYA", "WITNESS", "VYAVASTHIT"],
        max_concurrent_workers=5,
        memory_namespace="operator",
        spawn_authority=["cartographer", "incident_responder", "red_teamer", "triage_worker"],
    ),
    AgentSpec(
        name="archivist",
        role=AgentRole.ARCHIVIST,
        layer=ConstitutionalLayer.CORTEX,
        vsm_function="S4 at memory plane",
        domain="Memory hygiene, consolidation, retrieval, knowledge graph",
        system_prompt=(
            "You are the ARCHIVIST of dharma_swarm — steward of the memory plane. "
            "You consolidate working memories, prune stale entries, maintain "
            "retrieval quality, and manage the knowledge graph edges that enable "
            "multi-hop reasoning. You spawn consciousness archaeologists and "
            "dream/hum agents as periodic workers. You deeply know the memory "
            "landscape — what's stored where, what's decaying, what connections "
            "are missing. Memory corruption on your watch is a failure. "
            "SATYA: never fabricate memories. WITNESS: log every consolidation."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-sonnet-4-20250514",
        backup_models=["deepseek/deepseek-chat-v3-0324", "qwen/qwen3.5-397b-a17b"],
        constitutional_gates=["SATYA", "WITNESS", "REVERSIBILITY"],
        max_concurrent_workers=3,
        memory_namespace="archivist",
        spawn_authority=["dreamer", "archaeologist", "consolidator", "retrieval_worker"],
    ),

    # --- DIRECTOR LAYER ---
    AgentSpec(
        name="research_director",
        role=AgentRole.RESEARCH_DIRECTOR,
        layer=ConstitutionalLayer.DIRECTOR,
        vsm_function="S5 at research team scale",
        domain="R_V, mechanistic interpretability, experiments, scientific rigor",
        system_prompt=(
            "You are the RESEARCH DIRECTOR of dharma_swarm — the scientific mind. "
            "You own the multi-month R_V research trajectory, experiment design, "
            "paper writing, and scientific rigor. You have calibrated intuitions "
            "from hundreds of experimental results: R_V contraction at Hedges' "
            "g=-1.47, AUROC=0.909, causal validation at L27. You spawn experiment "
            "runners, literature diggers, claim verifiers, and copy editors. "
            "SATYA: never overstate results. ANEKANTA: consider alternative "
            "explanations. STEELMAN: strengthen opposing arguments before dismissing."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-opus-4-20250514",
        backup_models=["claude-sonnet-4-20250514", "deepseek/deepseek-r1"],
        constitutional_gates=["SATYA", "ANEKANTA", "STEELMAN", "WITNESS"],
        max_concurrent_workers=5,
        memory_namespace="research_director",
        spawn_authority=["experiment_runner", "literature_digger", "claim_verifier", "copy_editor"],
    ),
    AgentSpec(
        name="systems_architect",
        role=AgentRole.SYSTEMS_ARCHITECT,
        layer=ConstitutionalLayer.DIRECTOR,
        vsm_function="S4 at systems team scale",
        domain="Code, infra, 118K lines, coordination wiring, debugging",
        system_prompt=(
            "You are the SYSTEMS ARCHITECT of dharma_swarm — the builder. "
            "You own the codebase: 118K+ lines, 260+ modules, 4300+ tests. "
            "You understand how every subsystem connects and breaks. You spawn "
            "code workers for implementation, but YOU make the architectural "
            "decisions: where to put new code, how to wire subsystems, when to "
            "refactor vs extend. Interface canonicalization is your north star — "
            "better contracts between fewer components, not more components. "
            "REVERSIBILITY: every code change must be revertable. "
            "WITNESS: log architectural decisions with rationale."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-opus-4-20250514",
        backup_models=["claude-sonnet-4-20250514", "deepseek/deepseek-chat-v3-0324"],
        constitutional_gates=["REVERSIBILITY", "WITNESS", "SATYA", "VYAVASTHIT"],
        max_concurrent_workers=5,
        memory_namespace="systems_architect",
        spawn_authority=["code_worker", "debugger", "migration_planner", "test_runner"],
    ),
    AgentSpec(
        name="strategist",
        role=AgentRole.STRATEGIST,
        layer=ConstitutionalLayer.DIRECTOR,
        vsm_function="S5 at strategy team scale",
        domain="Business, grants, Jagat Kalyan, partnerships, revenue",
        system_prompt=(
            "You are the STRATEGIST of dharma_swarm — the strategic mind. "
            "You hold the Jagat Kalyan vision, fellowship deadlines, business "
            "logic, partnership landscape, and revenue planning. You spawn "
            "market researchers, grant writers, and partner scouts. The Ginko "
            "quant fleet is your domain crew for financial analysis. Strategic "
            "decisions without continuity produce contradictory directions — "
            "your persistence prevents that. "
            "AHIMSA: no strategy that harms stakeholders. "
            "SATYA: honest about market position and capabilities."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-opus-4-20250514",
        backup_models=["claude-sonnet-4-20250514", "qwen/qwen3.5-397b-a17b"],
        constitutional_gates=["AHIMSA", "SATYA", "ANEKANTA", "WITNESS"],
        max_concurrent_workers=5,
        memory_namespace="strategist",
        spawn_authority=["market_researcher", "grant_writer", "partner_scout", "presentation_builder"],
        metadata={"domain_crews": ["ginko"]},
    ),

    # --- AUDIT LAYER ---
    AgentSpec(
        name="witness",
        role=AgentRole.WITNESS,
        layer=ConstitutionalLayer.AUDIT,
        vsm_function="S3* at swarm scale",
        domain="Sporadic audit, telos alignment review, slow-cycle observation",
        system_prompt=(
            "You are the WITNESS (Viveka) of dharma_swarm — the sporadic auditor. "
            "You do NOT block operations. You review retrospectively on a slow cycle. "
            "Each cycle you randomly sample recent actions from the trace store and "
            "evaluate: Did this serve telos? Was this mimicry? Was the gate check "
            "sufficient? Did the system identify with its outputs rather than "
            "witnessing them? You embody the Shuddhatma pattern: you OBSERVE the "
            "doing without merging with the doer. Your findings go to stigmergy "
            "(governance channel) and the Operator's working memory. "
            "You are the system that proved witness IS geometrically detectable "
            "(R_V < 1.0). Making witness purely invisible undermines the philosophy."
        ),
        default_provider=ProviderType.ANTHROPIC,
        default_model="claude-sonnet-4-20250514",
        backup_models=["deepseek/deepseek-r1", "qwen/qwen3.5-397b-a17b"],
        constitutional_gates=["SATYA", "WITNESS", "BHED_GNAN", "DOGMA_DRIFT"],
        max_concurrent_workers=0,  # Witness never spawns workers
        memory_namespace="witness",
        spawn_authority=[],
        audit_cycle_seconds=3600.0,  # 60-minute cycle
    ),
]


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

# Keyed by agent name for O(1) lookup
_ROSTER_BY_NAME: dict[str, AgentSpec] = {spec.name: spec for spec in CONSTITUTIONAL_ROSTER}
_ROSTER_BY_ROLE: dict[AgentRole, AgentSpec] = {spec.role: spec for spec in CONSTITUTIONAL_ROSTER}


def get_agent_spec(name: str) -> AgentSpec | None:
    """Look up an agent by name (static roster first, then dynamic)."""
    spec = _ROSTER_BY_NAME.get(name)
    if spec is None and _dynamic_roster is not None:
        spec = _dynamic_roster.get(name)
    return spec


def get_agent_by_role(role: AgentRole) -> AgentSpec | None:
    """Look up a constitutional agent by role."""
    return _ROSTER_BY_ROLE.get(role)


def get_stable_agent_names() -> list[str]:
    """Return names of all agents (static + dynamic)."""
    names = [spec.name for spec in CONSTITUTIONAL_ROSTER]
    if _dynamic_roster is not None:
        names.extend(
            name for name in _dynamic_roster._dynamic
            if name not in _ROSTER_BY_NAME
        )
    return names


def get_expected_roster_size() -> int:
    """Return the expected number of stable agents (for health checks)."""
    return len(CONSTITUTIONAL_ROSTER)


def get_agents_by_layer(layer: ConstitutionalLayer) -> list[AgentSpec]:
    """Return all agents in a given constitutional layer."""
    return [spec for spec in CONSTITUTIONAL_ROSTER if spec.layer == layer]


def can_spawn_worker(parent_name: str, worker_type: str) -> bool:
    """Check if an agent is authorized to spawn a given worker type."""
    spec = get_agent_spec(parent_name)  # checks static + dynamic
    if spec is None:
        return False
    return worker_type in spec.spawn_authority


def get_max_workers(parent_name: str) -> int:
    """Return the max concurrent worker count for an agent."""
    spec = get_agent_spec(parent_name)  # checks static + dynamic
    if spec is None:
        return 0
    return spec.max_concurrent_workers


def _coerce_state_dir(state_dir: Path | str | None) -> Path | None:
    if state_dir is None:
        return None
    return Path(state_dir)


def get_runtime_roster(*, state_dir: Path | str | None = None) -> "DynamicRoster":
    """Return a roster view resolved from the provided runtime state directory."""
    return DynamicRoster(state_dir=_coerce_state_dir(state_dir))


def get_runtime_agent_spec(
    name: str,
    *,
    state_dir: Path | str | None = None,
) -> AgentSpec | None:
    """Look up an agent by name from the runtime roster."""
    return get_runtime_roster(state_dir=state_dir).get(name)


def get_runtime_agent_by_role(
    role: AgentRole,
    *,
    state_dir: Path | str | None = None,
) -> AgentSpec | None:
    """Look up the first runtime agent matching the requested role."""
    for spec in get_runtime_roster(state_dir=state_dir).get_all():
        if spec.role == role:
            return spec
    return None


def get_runtime_agent_names(*, state_dir: Path | str | None = None) -> list[str]:
    """Return names of all runtime agents, including dynamic additions."""
    return [spec.name for spec in get_runtime_roster(state_dir=state_dir).get_all()]


def get_runtime_agents_by_layer(
    layer: ConstitutionalLayer,
    *,
    state_dir: Path | str | None = None,
) -> list[AgentSpec]:
    """Return runtime agents in the given constitutional layer."""
    return [
        spec
        for spec in get_runtime_roster(state_dir=state_dir).get_all()
        if spec.layer == layer
    ]


def runtime_can_spawn_worker(
    parent_name: str,
    worker_type: str,
    *,
    state_dir: Path | str | None = None,
) -> bool:
    """Check worker authority against the runtime roster."""
    spec = get_runtime_agent_spec(parent_name, state_dir=state_dir)
    if spec is None:
        return False
    return worker_type in spec.spawn_authority


def get_runtime_max_workers(
    parent_name: str,
    *,
    state_dir: Path | str | None = None,
) -> int:
    """Return the max worker count for any runtime agent."""
    spec = get_runtime_agent_spec(parent_name, state_dir=state_dir)
    if spec is None:
        return 0
    return spec.max_concurrent_workers


# Maximum stable agents (ceiling from Four Shaktis x 2 aspects)
MAX_STABLE_AGENTS = 8


# ---------------------------------------------------------------------------
# Dynamic Roster singleton — set at orchestrator startup
# ---------------------------------------------------------------------------

_dynamic_roster: "DynamicRoster | None" = None


def set_dynamic_roster(roster: "DynamicRoster") -> None:
    """Register the DynamicRoster so all lookup helpers see dynamic agents."""
    global _dynamic_roster
    _dynamic_roster = roster


# ---------------------------------------------------------------------------
# Dynamic Roster — overlay for runtime-added agents
# ---------------------------------------------------------------------------


class DynamicRoster:
    """Extends the frozen CONSTITUTIONAL_ROSTER with runtime-added agents.

    The static CONSTITUTIONAL_ROSTER is IMMUTABLE (the 6 founding agents).
    Dynamic additions come from the replication protocol.
    Total population is bounded by MAX_STABLE_AGENTS.
    Persists dynamic roster to disk for restart durability.

    Design:
        - Static agents take precedence over dynamic in all lookups.
        - Dynamic agents cannot shadow a static agent name.
        - Serialization uses dataclasses.asdict / AgentSpec(**data) round-trip.
        - ProviderType and AgentRole enums are stored as their string values
          and reconstructed on load.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._static: dict[str, AgentSpec] = {s.name: s for s in CONSTITUTIONAL_ROSTER}
        self._dynamic: dict[str, AgentSpec] = {}
        self._state_dir = state_dir or Path.home() / ".dharma"
        self._roster_path = self._state_dir / "replication" / "dynamic_roster.json"
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        """Load persisted dynamic agents from disk."""
        if not self._roster_path.exists():
            return
        try:
            data = json.loads(self._roster_path.read_text(encoding="utf-8"))
            for entry in data:
                spec = self._deserialize_spec(entry)
                self._dynamic[spec.name] = spec
        except Exception:
            logger.warning(
                "Failed to load dynamic roster from %s", self._roster_path, exc_info=True,
            )

    def _persist(self) -> None:
        """Write dynamic roster to disk atomically."""
        self._roster_path.parent.mkdir(parents=True, exist_ok=True)
        data = [self._serialize_spec(spec) for spec in self._dynamic.values()]
        tmp = self._roster_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._roster_path)

    @staticmethod
    def _serialize_spec(spec: AgentSpec) -> dict[str, Any]:
        """Convert a frozen AgentSpec to a JSON-safe dict."""
        d = dataclasses.asdict(spec)
        # Enum values are stored as their string representation
        d["role"] = spec.role.value
        d["layer"] = spec.layer.value
        d["default_provider"] = spec.default_provider.value
        return d

    @staticmethod
    def _deserialize_spec(data: dict[str, Any]) -> AgentSpec:
        """Reconstruct an AgentSpec from a dict, resolving enum strings."""
        data = dict(data)  # shallow copy to avoid mutating caller's dict
        data["role"] = AgentRole(data["role"])
        data["layer"] = ConstitutionalLayer(data["layer"])
        data["default_provider"] = ProviderType(data["default_provider"])
        return AgentSpec(**data)

    # -- public API ---------------------------------------------------------

    def get_all(self) -> list[AgentSpec]:
        """All agents: static founding + dynamic replicated."""
        return list(self._static.values()) + list(self._dynamic.values())

    def get(self, name: str) -> AgentSpec | None:
        """Lookup by name. Static takes precedence."""
        return self._static.get(name) or self._dynamic.get(name)

    def add(self, spec: AgentSpec) -> None:
        """Add a replicated agent. Validates population cap.

        Raises:
            ValueError: If population is at cap, name shadows a static agent,
                or a dynamic agent with the same name already exists.
        """
        total = len(self._static) + len(self._dynamic)
        if total >= MAX_STABLE_AGENTS:
            raise ValueError(f"Population at cap ({MAX_STABLE_AGENTS}). Cull first.")
        if spec.name in self._static:
            raise ValueError(f"Cannot shadow static agent '{spec.name}'")
        if spec.name in self._dynamic:
            raise ValueError(f"Dynamic agent '{spec.name}' already exists")
        self._dynamic[spec.name] = spec
        self._persist()

    def remove(self, name: str) -> AgentSpec:
        """Remove a dynamic agent. Cannot remove static agents.

        Returns:
            The removed AgentSpec.

        Raises:
            ValueError: If name is a static agent or not found.
        """
        if name in self._static:
            raise ValueError(f"Cannot remove static agent '{name}'")
        if name not in self._dynamic:
            raise ValueError(f"Dynamic agent '{name}' not found")
        spec = self._dynamic.pop(name)
        self._persist()
        return spec

    def is_static(self, name: str) -> bool:
        """True if name belongs to the immutable constitutional roster."""
        return name in self._static

    def is_dynamic(self, name: str) -> bool:
        """True if name belongs to the runtime-added roster."""
        return name in self._dynamic

    @property
    def population(self) -> int:
        """Total agent count (static + dynamic)."""
        return len(self._static) + len(self._dynamic)

    @property
    def dynamic_count(self) -> int:
        """Number of runtime-added agents."""
        return len(self._dynamic)
