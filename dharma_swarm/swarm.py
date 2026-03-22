"""Swarm Manager — integrates agent pool, task board, message bus, and orchestrator.

Layer 4: The swarm lifecycle manager. Spawns agents, assigns tasks,
monitors health, and provides the unified API for the CLI and MCP server.

Now wired with Garden Daemon config (heartbeat, thread rotation, circuit
breakers, quality gates, human overrides) and v7 induction prompts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from dharma_swarm.daemon_config import DaemonConfig, THREAD_PROMPTS
from dharma_swarm.contracts.intelligence_agents import (
    DEFAULT_TEAM_ID,
    resolve_team_id,
    sync_live_agent_registration,
    sync_live_agent_registrations,
)
from dharma_swarm.yoga_node import YogaScheduler
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span
from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    MemoryLayer,
    ProviderType,
    SwarmState,
    Task,
    TaskPriority,
    TaskStatus,
    TopologyType,
)
from dharma_swarm.providers import create_default_router

if TYPE_CHECKING:
    from dharma_swarm.adaptive_autonomy import AdaptiveAutonomy
    from dharma_swarm.agent_memory import AgentMemoryBank
    from dharma_swarm.agent_runner import AgentPool
    from dharma_swarm.canary import CanaryDeployer
    from dharma_swarm.context_search import ContextSearchEngine
    from dharma_swarm.dharma_corpus import DharmaCorpus
    from dharma_swarm.dharma_kernel import KernelGuard
    from dharma_swarm.engine.event_memory import EventMemoryStore
    from dharma_swarm.evolution import DarwinEngine
    from dharma_swarm.handoff import HandoffProtocol
    from dharma_swarm.intent_router import IntentRouter
    from dharma_swarm.memory import StrangeLoopMemory
    from dharma_swarm.message_bus import MessageBus
    from dharma_swarm.monitor import SystemMonitor
    from dharma_swarm.orchestrator import Orchestrator
    from dharma_swarm.policy_compiler import PolicyCompiler
    from dharma_swarm.profiles import ProfileManager
    from dharma_swarm.skill_composer import SkillComposer
    from dharma_swarm.skills import SkillRegistry
    from dharma_swarm.stigmergy import StigmergyStore
    from dharma_swarm.task_board import TaskBoard
    from dharma_swarm.telemetry_plane import TelemetryPlaneStore
    from dharma_swarm.thinkodynamic_director import ThinkodynamicDirector
    from dharma_swarm.thread_manager import ThreadManager
    from dharma_swarm.traces import TraceStore
    from dharma_swarm.organism import OrganismRuntime, HeartbeatResult
    from dharma_swarm.witness import WitnessAuditor

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class SubsystemNotReady(RuntimeError):
    """Raised when a required subsystem hasn't been initialized yet.

    Ashby's requisite variety: type system variety must match runtime variety.
    """


def _make_trace_id() -> str:
    return f"trc_{uuid4().hex}"


class SwarmCoordinationState(BaseModel):
    """Compact runtime summary of sheaf-based swarm coordination."""

    observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_count: int = 0
    message_count: int = 0
    task_count: int = 0
    overlap_pairs: int = 0
    published_agents: list[str] = Field(default_factory=list)
    global_truths: int = 0
    productive_disagreements: int = 0
    cohomological_dimension: int = 0
    is_globally_coherent: bool = True
    global_truth_claim_keys: list[str] = Field(default_factory=list)
    productive_disagreement_claim_keys: list[str] = Field(default_factory=list)


class SwarmManager:
    """Top-level swarm coordinator.

    Integrates: agent pool, task board, message bus, memory, orchestrator,
    telos gates, ecosystem bridge, daemon config, and thread manager.
    """

    def __init__(
        self,
        state_dir: Path | str = ".dharma",
        daemon_config: DaemonConfig | None = None,
    ):
        self.state_dir = Path(state_dir)
        self._start_time = time.monotonic()
        self._running = False
        self._daemon = daemon_config or DaemonConfig()

        # ── Subsystem declarations (typed, not Any) ──
        # CRITICAL: must init or swarm cannot operate
        self._task_board: TaskBoard | None = None
        self._agent_pool: AgentPool | None = None
        self._message_bus: MessageBus | None = None
        self._orchestrator: Orchestrator | None = None
        self._gatekeeper: Any = None  # TelosGatekeeper (no stable type yet)

        # CRITICAL: core infrastructure
        self._memory: StrangeLoopMemory | None = None
        self._event_memory: EventMemoryStore | None = None
        self._telemetry: TelemetryPlaneStore | None = None
        self._thread_mgr: ThreadManager | None = None
        self._router = create_default_router()

        # v0.2.0 subsystems (CRITICAL: evolution + monitoring)
        self._engine: DarwinEngine | None = None
        self._monitor: SystemMonitor | None = None
        self._trace_store: TraceStore | None = None

        # v0.3.0: Gödel Claw (CRITICAL: kernel + corpus)
        self._kernel_guard: KernelGuard | None = None
        self._corpus: DharmaCorpus | None = None
        self._compiler: PolicyCompiler | None = None
        self._canary: CanaryDeployer | None = None
        self._bridge_rv: Any = None  # ResearchBridge (optional)
        self._stigmergy: StigmergyStore | None = None

        # v0.4.0: Oz-inspired (OPTIONAL: can fail gracefully)
        self._skill_registry: SkillRegistry | None = None
        self._profile_mgr: ProfileManager | None = None
        self._intent_router: IntentRouter | None = None
        self._context_search: ContextSearchEngine | None = None
        self._autonomy: AdaptiveAutonomy | None = None
        self._skill_composer: SkillComposer | None = None
        self._handoff: HandoffProtocol | None = None
        self._agent_memories: dict[str, AgentMemoryBank] = {}
        self._agent_configs: dict[str, AgentConfig] = {}
        self._worker_spawners: dict[str, Any] = {}  # name → WorkerSpawner

        # v0.5.0: Thinkodynamic Director (OPTIONAL)
        self._director: ThinkodynamicDirector | None = None
        self._tick_count: int = 0

        # v0.7.0: Organism brain — Gnani/Samvara wired into the heartbeat
        self._organism: OrganismRuntime | None = None
        self._organism_interval_ticks: int = 4  # heartbeat every ~2 min (4 × 30s)

        # v0.8.0: Witness (S3* sporadic audit) — Beer VSM gap #2
        self._witness: WitnessAuditor | None = None
        self._witness_interval_ticks: int = 120  # audit every ~60 min (120 × 30s)

        # v0.9.0: Decision Ontology — structured decision governance
        self._decision_log: Any = None  # DecisionLog

        # Central config (Beer's S5 — identity at the parameter level)
        from dharma_swarm.config import DEFAULT_CONFIG
        self._config = DEFAULT_CONFIG
        _sm = self._config.swarm
        self._director_interval_ticks: int = _sm.director_interval_ticks
        self._living_interval_ticks: int = _sm.living_interval_ticks

        # v0.6.0: Hermes-inspired integration (OPTIONAL)
        self._tool_registry: Any = None    # ToolRegistry
        self._cron_scheduler: Any = None   # module ref
        self._gateway: Any = None          # GatewayRunner

        # Subsystem initialization tracking
        self._initialized: set[str] = set()

        # Daemon state
        self._last_contribution: datetime | None = None
        self._daily_contributions: int = 0
        self._daily_reset: datetime | None = None
        self._last_auto_rescue_scan: datetime | None = None
        self._auto_rescue_scan_interval_seconds = _sm.auto_rescue_scan_interval_seconds
        self._auto_rescue_max_age = timedelta(hours=_sm.auto_rescue_max_age_hours)
        self._auto_rescue_max_attempts = _sm.auto_rescue_max_attempts

    # ── Subsystem access helpers ──

    # Subsystems classified by criticality
    _CRITICAL_SUBSYSTEMS = frozenset({
        "task_board", "agent_pool", "orchestrator", "gatekeeper",
    })
    _OPTIONAL_SUBSYSTEMS = frozenset({
        "stigmergy", "bridge_rv", "director", "skill_registry",
        "profile_mgr", "intent_router", "context_search", "autonomy",
        "skill_composer", "handoff", "tool_registry", "cron_scheduler",
        "gateway", "decision_log",
    })

    def _require_subsystem(self, name: str) -> Any:
        """Return a subsystem or raise SubsystemNotReady.

        Ashby: the check variety must match the failure variety.
        """
        attr = f"_{name}"
        value = getattr(self, attr, None)
        if value is None:
            raise SubsystemNotReady(
                f"Subsystem {name!r} not initialized. "
                f"Call init() first or check is_ready({name!r})."
            )
        return value

    def is_ready(self, subsystem_name: str) -> bool:
        """Check if a subsystem has been initialized."""
        return getattr(self, f"_{subsystem_name}", None) is not None

    async def init(self) -> None:
        """Initialize all subsystems."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

        from dharma_swarm.agent_constitution import bootstrap_dynamic_roster

        from dharma_swarm.agent_runner import AgentPool
        from dharma_swarm.engine.event_memory import EventMemoryStore
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.message_bus import MessageBus
        from dharma_swarm.orchestrator import Orchestrator
        from dharma_swarm.task_board import TaskBoard
        from dharma_swarm.telemetry_plane import TelemetryPlaneStore
        from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER
        from dharma_swarm.thread_manager import ThreadManager

        db_dir = self.state_dir / "db"
        db_dir.mkdir(exist_ok=True)
        state_runtime_db = self.state_dir / "state" / "runtime.db"

        self._task_board = TaskBoard(db_dir / "tasks.db")
        await self._task_board.init_db()

        self._message_bus = MessageBus(db_dir / "messages.db")
        await self._message_bus.init_db()

        self._dynamic_roster = bootstrap_dynamic_roster(state_dir=self.state_dir)
        self._memory = StrangeLoopMemory(db_dir / "memory.db")
        await self._memory.init_db()
        self._event_memory = EventMemoryStore(db_dir / "memory_plane.db")
        await self._event_memory.init_db()
        self._telemetry = TelemetryPlaneStore(state_runtime_db)
        await self._telemetry.init_db()

        self._agent_pool = AgentPool()
        self._gatekeeper = DEFAULT_GATEKEEPER
        self._thread_mgr = ThreadManager(self._daemon, self.state_dir)

        self._yoga = YogaScheduler(
            quiet_hours=self._daemon.quiet_hours,
            max_daily_tasks=self._daemon.max_daily_contributions * 5,
        )
        self._orchestrator = Orchestrator(
            task_board=self._task_board,
            agent_pool=self._agent_pool,
            message_bus=self._message_bus,
            ledger_dir=self.state_dir / "ledgers",
            runtime_db_path=state_runtime_db,
            event_memory=self._event_memory,
            yoga=self._yoga,
        )

        self._running = True

        # Load ecosystem awareness on every init
        from dharma_swarm.ecosystem_bridge import MANIFEST_PATH, update_manifest

        fallback_manifest_path = self.state_dir / "ecosystem_manifest.json"
        try:
            self._manifest = update_manifest()
        except PermissionError:
            logger.debug(
                "Global ecosystem manifest %s not writable; using state-local manifest %s",
                MANIFEST_PATH,
                fallback_manifest_path,
            )
            self._manifest = update_manifest(manifest_path=fallback_manifest_path)

        # Spawn default crew and seed tasks if this is a fresh start
        from dharma_swarm.startup_crew import spawn_default_crew, create_seed_tasks
        crew = await spawn_default_crew(self)
        seeds = await create_seed_tasks(self)
        if crew:
            logger.info("Spawned %d agents from default crew", len(crew))
        if seeds:
            logger.info("Created %d seed tasks", len(seeds))

        await self._memory.remember(
            f"Swarm initialized — {len(crew)} agents, {len(seeds)} seed tasks",
            layer=MemoryLayer.SESSION,
            source="swarm",
        )

        # v0.2.0: Darwin Engine + System Monitor
        from dharma_swarm.evolution import DarwinEngine
        from dharma_swarm.monitor import SystemMonitor
        from dharma_swarm.traces import TraceStore

        evo_dir = self.state_dir / "evolution"
        traces_dir = self.state_dir / "traces"

        self._trace_store = TraceStore(base_path=traces_dir)
        await self._trace_store.init()

        self._engine = DarwinEngine(
            archive_path=evo_dir / "archive.jsonl",
            traces_path=traces_dir,
            predictor_path=evo_dir / "predictor_data.jsonl",
        )
        await self._engine.init()

        self._monitor = SystemMonitor(trace_store=self._trace_store)

        # v0.3.0: Gödel Claw — Dharma Kernel, Corpus, Policy, Canary, Stigmergy
        from dharma_swarm.dharma_kernel import KernelGuard
        from dharma_swarm.dharma_corpus import DharmaCorpus
        from dharma_swarm.policy_compiler import PolicyCompiler
        from dharma_swarm.canary import CanaryDeployer

        kernel_path = self.state_dir / "kernel.json"
        corpus_path = self.state_dir / "corpus.jsonl"

        self._kernel_guard = KernelGuard(kernel_path=kernel_path)
        try:
            await self._kernel_guard.load()
        except (FileNotFoundError, ValueError):
            # First run or tampered — create default kernel
            from dharma_swarm.dharma_kernel import DharmaKernel
            default = DharmaKernel.create_default()
            await self._kernel_guard.save(default)

        self._corpus = DharmaCorpus(path=corpus_path)
        await self._corpus.load()

        self._compiler = PolicyCompiler()

        self._canary = CanaryDeployer(archive=self._engine.archive)

        # Stigmergy (may not exist yet — created by Agent 11)
        try:
            from dharma_swarm.stigmergy import StigmergyStore
            stigmergy_path = self.state_dir / "stigmergy"
            self._stigmergy = StigmergyStore(base_path=stigmergy_path)
        except ImportError:
            self._stigmergy = None
            logger.debug("Stigmergy module not available yet")

        logger.info("Gödel Claw v1 subsystems initialized")

        # v0.4.0: Oz-inspired systems (skill registry, profiles, intent router,
        # context search, adaptive autonomy)
        try:
            from dharma_swarm.skills import SkillRegistry
            from dharma_swarm.profiles import ProfileManager
            from dharma_swarm.intent_router import IntentRouter
            from dharma_swarm.context_search import ContextSearchEngine
            from dharma_swarm.adaptive_autonomy import AdaptiveAutonomy

            self._skill_registry = SkillRegistry()
            self._skill_registry.discover()

            profiles_dir = self.state_dir / "profiles"
            self._profile_mgr = ProfileManager(profile_dir=profiles_dir)
            self._profile_mgr.load_all()

            self._intent_router = IntentRouter(registry=self._skill_registry)

            self._context_search = ContextSearchEngine()
            self._context_search.build_index()

            self._autonomy = AdaptiveAutonomy(base_level="balanced")

            # v0.4.1: Composition, handoff, agent memory
            from dharma_swarm.skill_composer import SkillComposer
            from dharma_swarm.handoff import HandoffProtocol
            self._skill_composer = SkillComposer(
                registry=self._skill_registry,
                router=self._intent_router,
            )
            self._handoff = HandoffProtocol(
                store_path=self.state_dir / "handoffs.jsonl",
            )

            logger.info("v0.4.0+ Oz-inspired systems initialized")
        except Exception as e:
            logger.warning("v0.4.0 systems init failed (non-fatal): %s", e)

        # v0.5.0: Thinkodynamic Director
        try:
            from dharma_swarm.thinkodynamic_director import ThinkodynamicDirector

            self._director = ThinkodynamicDirector(
                state_dir=self.state_dir,
                swarm=self,
            )
            await self._director.init()
            logger.info("ThinkodynamicDirector initialized")
        except Exception as e:
            logger.warning("ThinkodynamicDirector init failed (non-fatal): %s", e)

        # v0.7.0: OrganismRuntime — Gnani, Samvara, LiveCoherence
        # v0.7.1: Algedonic channel wired — pain signals → file + macOS notification
        try:
            from dharma_swarm.organism import OrganismRuntime

            self._organism = OrganismRuntime(
                state_dir=self.state_dir,
                on_algedonic=self._algedonic_handler,
            )
            logger.info("OrganismRuntime initialized — Gnani/Samvara/Algedonic active")
        except Exception as e:
            logger.warning("OrganismRuntime init failed (non-fatal): %s", e)

        # v0.8.0: Witness auditor (Beer S3* — sporadic random audit)
        try:
            from dharma_swarm.witness import WitnessAuditor

            self._witness = WitnessAuditor(
                cycle_seconds=3600.0,
                provider=self._router,
            )
            logger.info("WitnessAuditor initialized — S3* sporadic audit active")
        except Exception as e:
            logger.warning("WitnessAuditor init failed (non-fatal): %s", e)

        # v0.9.0: Decision Ontology (structured decision governance + quality scoring)
        try:
            from dharma_swarm.decision_ontology import DecisionLog

            self._decision_log = DecisionLog(
                path=self.state_dir / "meta" / "decisions.jsonl",
            )
            logger.info("DecisionLog initialized — structured decision governance active")
        except Exception as e:
            logger.warning("DecisionLog init failed (non-fatal): %s", e)

        # v0.9.1: Telos Substrate — seed ConceptGraph + TelosGraph with pillar data
        # Deferred to first tick() to avoid heavyweight I/O during init.
        self._telos_substrate_seeded = False

        # Track which subsystems successfully initialized
        for name, attr in [
            ("task_board", self._task_board),
            ("agent_pool", self._agent_pool),
            ("message_bus", self._message_bus),
            ("orchestrator", self._orchestrator),
            ("gatekeeper", self._gatekeeper),
            ("memory", self._memory),
            ("event_memory", self._event_memory),
            ("engine", self._engine),
            ("monitor", self._monitor),
            ("kernel_guard", self._kernel_guard),
            ("corpus", self._corpus),
            ("stigmergy", self._stigmergy),
            ("skill_registry", self._skill_registry),
            ("director", self._director),
            ("organism", self._organism),
            ("witness", self._witness),
            ("decision_log", self._decision_log),
        ]:
            if attr is not None:
                self._initialized.add(name)

        logger.info(
            "Subsystems initialized: %d/%d critical, %d optional",
            len(self._initialized & self._CRITICAL_SUBSYSTEMS),
            len(self._CRITICAL_SUBSYSTEMS),
            len(self._initialized - self._CRITICAL_SUBSYSTEMS),
        )

    # --- Agent Operations ---

    async def spawn_agent(
        self,
        name: str,
        role: AgentRole = AgentRole.GENERAL,
        model: str = "claude-code",
        provider_type: ProviderType = ProviderType.CLAUDE_CODE,
        system_prompt: str = "",
        thread: str | None = None,
    ) -> AgentState:
        """Spawn a new agent into the pool.

        If no system_prompt is given, v7 induction rules + role briefing are used.
        If a thread is specified, the thread focus prompt is appended.

        When the agent name matches the constitutional roster, roster defaults
        are applied for role, model, provider, and system_prompt (caller values
        override only when explicitly non-default).
        """
        # Constitutional roster check: apply spec defaults for stable agents
        try:
            from dharma_swarm.agent_constitution import get_runtime_agent_spec

            spec = get_runtime_agent_spec(name, state_dir=self.state_dir)
            if spec is not None:
                # Stable agent — use constitutional defaults unless caller overrides
                if role == AgentRole.GENERAL:
                    role = spec.role
                if model == "claude-code" and spec.default_model:
                    model = spec.default_model
                if provider_type == ProviderType.CLAUDE_CODE and spec.default_provider:
                    provider_type = spec.default_provider
                if not system_prompt and spec.system_prompt:
                    system_prompt = spec.system_prompt
                logger.info(
                    "Constitutional agent %s: role=%s, model=%s, gates=%s",
                    name, role.value, model, spec.constitutional_gates,
                )
                # Create worker spawner for constitutional agents
                try:
                    from dharma_swarm.worker_spawn import create_spawner_for_agent
                    self._worker_spawners[name] = create_spawner_for_agent(
                        name,
                        state_dir=self.state_dir,
                    )
                except Exception:
                    logger.debug("Worker spawner creation failed for %s", name, exc_info=True)
        except Exception:
            logger.debug("Constitutional roster check failed", exc_info=True)

        async with jikoku_auto_span(
            category="execute.agent_spawn",
            intent=f"Spawn agent {name} ({role.value})",
            agent_name=name,
            role=role.value,
            model=model,
            provider=provider_type.value,
        ):
            # Build system prompt with thread context if applicable
            extra_prompt = ""
            if thread and thread in THREAD_PROMPTS:
                extra_prompt = f"\n\nCurrent research thread: {thread}\n{THREAD_PROMPTS[thread]}"

            config = AgentConfig(
                name=name,
                role=role,
                model=model,
                provider=provider_type,
                system_prompt=system_prompt + extra_prompt if system_prompt else extra_prompt,
                thread=thread,
                metadata={"state_dir": str(self.state_dir)},
            )
            # Route through the shared ModelRouter so live agent tasks contribute
            # to routing memory, retries, and audit trails while staying pinned
            # to config.provider unless task metadata widens the lane set.
            spawner = self._worker_spawners.get(name)
            runner = await self._agent_pool.spawn(
                config,
                provider=self._router,
                message_bus=self._message_bus,
                worker_spawner=spawner,
            )
            self._agent_configs[runner.state.id] = config
            await self._sync_agent_contracts(runner.state)
            await self._memory.remember(
                f"Agent spawned: {name} ({role.value})"
                + (f" [thread: {thread}]" if thread else ""),
                layer=MemoryLayer.SESSION,
                source="swarm",
            )
            return runner.state

    def get_worker_spawner(self, agent_name: str) -> Any | None:
        """Return the WorkerSpawner for a constitutional agent, or None."""
        return self._worker_spawners.get(agent_name)

    async def list_agents(self) -> list[AgentState]:
        """List all agents in the pool."""
        agents = await self._agent_pool.list_agents()
        await self._sync_agent_contracts_batch(agents, include_kaizenops=False)
        return agents

    async def stop_agent(self, agent_id: str) -> None:
        """Stop a specific agent."""
        runner = await self._agent_pool.get(agent_id)
        if runner:
            await runner.stop()
            await self._sync_agent_contracts(runner.state, include_kaizenops=False)

    async def sync_agents(
        self,
        *,
        include_kaizenops: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Refresh live agent contracts across telemetry and optional KaizenOps."""
        agents = await self._agent_pool.list_agents()
        return await self._sync_agent_contracts_batch(
            agents,
            include_kaizenops=include_kaizenops,
        )

    async def _sync_agent_contracts_batch(
        self,
        agents: list[AgentState],
        *,
        include_kaizenops: bool | None = None,
    ) -> list[dict[str, Any]]:
        metadata_by_agent_id: dict[str, dict[str, Any]] = {}
        thread_by_agent_id: dict[str, str | None] = {}
        managed_team_ids: list[str] = []
        for agent in agents:
            config = self._agent_configs.get(agent.id)
            metadata = dict(config.metadata) if config is not None else {}
            metadata.setdefault("provider", agent.provider)
            metadata.setdefault("model", agent.model)
            metadata.setdefault(
                "source",
                "swarm.spawn_agent" if config is not None else "swarm.sync_agents",
            )
            metadata_by_agent_id[agent.id] = metadata
            thread_by_agent_id[agent.id] = config.thread if config is not None else None
            managed_team_ids.append(
                resolve_team_id(thread=thread_by_agent_id[agent.id], metadata=metadata)
            )
        if not managed_team_ids:
            managed_team_ids.append(resolve_team_id(metadata={"team_id": DEFAULT_TEAM_ID}))
        results = await sync_live_agent_registrations(
            agents,
            telemetry=self._telemetry,
            metadata_by_agent_id=metadata_by_agent_id,
            thread_by_agent_id=thread_by_agent_id,
            message_bus=self._message_bus,
            include_kaizenops=include_kaizenops,
            managed_team_ids=managed_team_ids,
        )
        return [item.as_dict() for item in results]

    async def _sync_agent_contracts(
        self,
        agent: AgentState,
        *,
        include_kaizenops: bool | None = None,
    ) -> dict[str, Any]:
        config = self._agent_configs.get(agent.id)
        metadata = dict(config.metadata) if config is not None else {}
        metadata.setdefault("provider", agent.provider)
        metadata.setdefault("model", agent.model)
        metadata.setdefault("source", "swarm.spawn_agent" if config is not None else "swarm.list_agents")
        result = await sync_live_agent_registration(
            agent,
            telemetry=self._telemetry,
            thread=config.thread if config is not None else None,
            metadata=metadata,
            message_bus=self._message_bus,
            include_kaizenops=include_kaizenops,
        )
        return result.as_dict()

    # --- Task Operations ---

    @staticmethod
    def _is_self_referential_heartbeat_task(
        *,
        title: str,
        description: str,
        metadata: dict[str, Any],
    ) -> bool:
        """Block heartbeat loops that create tasks about heartbeat artifacts."""
        source = str(metadata.get("source", "")).lower()
        if source not in {"heartbeat", "pulse", "daemon", "system_heartbeat"}:
            return False
        text = f"{title}\n{description}".lower()
        has_heartbeat = "heartbeat" in text
        self_referential = any(
            marker in text
            for marker in (
                "heartbeat.md",
                "parse heartbeat",
                "summarize heartbeat",
                "analyze heartbeat",
                "task about heartbeat",
            )
        )
        return has_heartbeat and self_referential

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            values = [part.strip() for part in value.split(",")]
        elif isinstance(value, (list, tuple, set)):
            values = [str(part).strip() for part in value]
        else:
            return []
        return cls._dedupe_strings([item for item in values if item])

    @staticmethod
    def _coordination_claim_key(metadata: dict[str, Any], title: str = "") -> str:
        for key in (
            "coordination_claim_key",
            "claim_key",
            "coordination_topic",
            "topic",
            "task_group",
        ):
            value = str(metadata.get(key, "")).strip()
            if value:
                return value
        return title.strip()

    @staticmethod
    def _clamp_coordination_uncertainty(value: Any) -> float | None:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return None

    @classmethod
    def _normalize_coordination_metadata(
        cls,
        metadata: dict[str, Any],
        *,
        title: str = "",
    ) -> dict[str, Any]:
        normalized = dict(metadata)
        claim_key = cls._coordination_claim_key(normalized, title)
        if claim_key:
            normalized["coordination_claim_key"] = claim_key
            normalized.setdefault("coordination_topic", claim_key)

        context = cls._coerce_string_list(
            normalized.get("coordination_shared_context")
        )
        if context:
            normalized["coordination_shared_context"] = context

        preferred_roles = cls._coerce_string_list(
            normalized.get("coordination_preferred_roles")
            or normalized.get("preferred_roles")
        )
        if preferred_roles:
            normalized["coordination_preferred_roles"] = [
                role.lower() for role in preferred_roles
            ]

        uncertainty = cls._clamp_coordination_uncertainty(
            normalized.get("coordination_uncertainty", normalized.get("uncertainty"))
        )
        if uncertainty is not None:
            normalized["coordination_uncertainty"] = uncertainty

        state = str(normalized.get("coordination_state", "")).strip().lower()
        if not state and claim_key:
            if uncertainty is not None and uncertainty >= 0.5:
                state = "uncertain"
            elif bool(normalized.get("coordination_review_required")):
                state = "uncertain"
            else:
                state = "local"
        if state:
            normalized["coordination_state"] = state

        route = str(normalized.get("coordination_route", "")).strip().lower()
        if (
            route == "synthesis_review"
            or bool(normalized.get("coordination_review_required"))
            or state == "uncertain"
        ):
            normalized["coordination_review_required"] = True
            normalized["coordination_route"] = "synthesis_review"
            normalized.setdefault(
                "coordination_preferred_roles",
                ["reviewer", "researcher", "general"],
            )
        return normalized

    async def create_task(
        self,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Create a new task on the board."""
        incoming = dict(metadata or {})
        if "trace_id" not in incoming:
            incoming["trace_id"] = _make_trace_id()
        incoming.setdefault("created_via", "swarm.create_task")
        incoming.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        incoming = self._normalize_coordination_metadata(incoming, title=title)

        async with jikoku_auto_span(
            category="execute.task_create",
            intent=f"Create task: {title}",
            priority=priority.value,
            desc_length=len(description),
            trace_id=incoming["trace_id"],
        ):
            if self._is_self_referential_heartbeat_task(
                title=title,
                description=description,
                metadata=incoming,
            ):
                raise ValueError(
                    "Self-referential heartbeat task blocked to prevent autoimmune loop"
                )
            gate_result = self._gatekeeper.check(action=title, content=description)
            if gate_result.decision.value == "block":
                raise ValueError(f"Telos gate blocked: {gate_result.reason}")
            return await self._task_board.create(
                title=title,
                description=description,
                priority=priority,
                metadata=incoming,
            )

    async def create_task_batch(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[Task]:
        """Create multiple tasks in a single batch operation.

        JIKOKU-optimized: Uses single transaction to eliminate SQLite
        write lock contention when creating multiple tasks.

        Args:
            tasks: List of task specs, each dict with keys:
                   {title, description?, priority?}

        Returns:
            List of created Task objects.
        """
        async with jikoku_auto_span(
            category="execute.task_create_batch",
            intent=f"Create {len(tasks)} tasks in batch",
            task_count=len(tasks),
        ):
            batch_id = f"batch_{uuid4().hex}"
            enriched: list[dict[str, Any]] = []

            # Run telos gates on all tasks first
            for spec in tasks:
                spec_copy = dict(spec)
                meta = dict(spec_copy.get("metadata") or {})
                if "trace_id" not in meta:
                    meta["trace_id"] = _make_trace_id()
                meta.setdefault("batch_id", batch_id)
                meta.setdefault("created_via", "swarm.create_task_batch")
                meta.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                meta = self._normalize_coordination_metadata(
                    meta,
                    title=str(spec_copy.get("title", "")),
                )
                spec_copy["metadata"] = meta

                if self._is_self_referential_heartbeat_task(
                    title=str(spec_copy.get("title", "")),
                    description=str(spec_copy.get("description", "")),
                    metadata=meta,
                ):
                    raise ValueError(
                        "Self-referential heartbeat task blocked to prevent autoimmune loop"
                    )

                gate_result = self._gatekeeper.check(
                    action=spec_copy["title"],
                    content=spec_copy.get("description", ""),
                )
                if gate_result.decision.value == "block":
                    raise ValueError(
                        f"Telos gate blocked task '{spec_copy['title']}': {gate_result.reason}"
                    )
                enriched.append(spec_copy)

            # Batch create all tasks in single transaction
            return await self._task_board.create_batch(enriched)

    @staticmethod
    def _latent_gold_task_title(shard: Any) -> str:
        prefix = {
            "question": "Answer latent question",
            "warning": "Resolve latent warning",
            "todo": "Follow up latent todo",
            "hypothesis": "Test latent hypothesis",
            "insight": "Develop latent insight",
            "proposal": "Reopen latent branch",
        }.get(str(getattr(shard, "shard_kind", "")), "Reopen latent branch")
        stem = str(getattr(shard, "text", "")).strip().rstrip(".")
        return f"{prefix}: {stem[:72]}".strip()

    @staticmethod
    def _latent_gold_task_description(shard: Any) -> str:
        return (
            "This task was reopened automatically from a high-salience latent branch "
            "captured during prior conversation flow.\n\n"
            f"Original shard:\n{getattr(shard, 'text', '').strip()}\n\n"
            f"State: {getattr(shard, 'state', 'unknown')}\n"
            f"Kind: {getattr(shard, 'shard_kind', 'unknown')}\n"
            f"Salience: {float(getattr(shard, 'salience', 0.0)):.2f}\n"
            f"Source task: {getattr(shard, 'task_id', '') or 'n/a'}\n\n"
            "Goal: decide whether this branch should be implemented, tested, "
            "archived, or explicitly rejected. If you resolve it, mention the "
            "originating latent branch in the result."
        )

    async def spawn_latent_gold_tasks(
        self,
        *,
        limit: int = 2,
        max_pending: int = 12,
        min_salience: float = 0.72,
    ) -> list[Task]:
        """Promote unresolved high-salience latent branches into real tasks."""
        if self._task_board is None:
            return []

        plane_path = self.state_dir / "db" / "memory_plane.db"
        if not plane_path.exists():
            return []

        from dharma_swarm.engine.conversation_memory import ConversationMemoryStore

        counts = await self._task_board.stats()
        active = (
            int(counts.get("pending", 0))
            + int(counts.get("assigned", 0))
            + int(counts.get("running", 0))
        )
        if active >= max_pending:
            return []

        existing = await self._task_board.list_tasks(limit=500)
        claimed_shards = {
            str(task.metadata.get("latent_gold_shard_id"))
            for task in existing
            if isinstance(task.metadata, dict)
            and isinstance(task.metadata.get("latent_gold_shard_id"), str)
            and str(task.metadata.get("latent_gold_shard_id")).strip()
        }

        store = ConversationMemoryStore(plane_path)
        candidates = [
            shard
            for shard in store.latent_gold("", limit=200)
            if shard.state in {"orphaned", "deferred"}
            and float(shard.salience) >= min_salience
            and shard.shard_id not in claimed_shards
        ]
        if not candidates:
            return []

        capacity = max(0, max_pending - active)
        planned = candidates[: max(0, min(limit, capacity))]
        if not planned:
            return []

        task_specs: list[dict[str, Any]] = []
        for shard in planned:
            priority = (
                TaskPriority.HIGH
                if float(shard.salience) >= 0.85
                else TaskPriority.NORMAL
            )
            task_specs.append(
                {
                    "title": self._latent_gold_task_title(shard),
                    "description": self._latent_gold_task_description(shard),
                    "priority": priority,
                    "metadata": {
                        "memory_plane_db": str(plane_path),
                        "latent_gold_reopened": True,
                        "latent_gold_shard_id": shard.shard_id,
                        "latent_gold_source_task_id": shard.task_id,
                        "latent_gold_source_turn_id": shard.turn_id,
                        "latent_gold_state": shard.state,
                        "latent_gold_kind": shard.shard_kind,
                        "latent_gold_salience": round(float(shard.salience), 6),
                        "source": "swarm.latent_gold",
                    },
                }
            )

        created = await self.create_task_batch(task_specs)
        for task in created:
            shard_id = str(task.metadata.get("latent_gold_shard_id", "")).strip()
            if shard_id:
                store.record_follow_up_task(
                    shard_id=shard_id,
                    follow_up_task_id=task.id,
                    title=task.title,
                )

        if created and self._memory is not None:
            await self._memory.remember(
                f"Latent gold reopened into {len(created)} follow-up task(s)",
                layer=MemoryLayer.SESSION,
                source="swarm",
            )
        return created

    async def list_tasks(
        self, status: TaskStatus | None = None
    ) -> list[Task]:
        """List tasks with optional status filter."""
        return await self._task_board.list_tasks(status=status)

    async def get_task(self, task_id: str) -> Task | None:
        """Get a specific task."""
        return await self._task_board.get(task_id)

    @staticmethod
    def _coordination_synthesis_title(claim_key: str) -> str:
        return f"Synthesize disagreement: {claim_key[:72]}".strip()

    @staticmethod
    def _coordination_synthesis_description(claim_key: str) -> str:
        return (
            "The sheaf coordination layer detected a productive disagreement.\n\n"
            f"Claim: {claim_key}\n\n"
            "Produce a synthesis that:\n"
            "1. names the competing local positions,\n"
            "2. identifies evidence for each,\n"
            "3. distinguishes resolvable uncertainty from durable pluralism,\n"
            "4. recommends the safest next action for the swarm.\n\n"
            "Do not force a fake consensus. Preserve uncertainty explicitly when needed."
        )

    async def spawn_coordination_tasks(
        self,
        *,
        coordination: SwarmCoordinationState | None = None,
        limit: int = 2,
        max_pending: int = 12,
    ) -> list[Task]:
        """Spawn bounded synthesis tasks for active productive disagreements."""
        if self._task_board is None:
            return []

        state = coordination or await self.coordination_status(refresh=False)
        if state.productive_disagreements <= 0:
            return []

        counts = await self._task_board.stats()
        active = (
            int(counts.get("pending", 0))
            + int(counts.get("assigned", 0))
            + int(counts.get("running", 0))
        )
        if active >= max_pending:
            return []

        existing = await self._task_board.list_tasks(limit=500)
        active_claims = {
            str(task.metadata.get("coordination_claim_key", "")).strip()
            for task in existing
            if task.status in {TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING}
            and isinstance(task.metadata, dict)
            and str(task.metadata.get("coordination_origin", "")).strip()
            == "sheaf_disagreement"
            and str(task.metadata.get("coordination_claim_key", "")).strip()
        }

        task_specs: list[dict[str, Any]] = []
        capacity = max(0, max_pending - active)
        planned_limit = max(0, min(limit, capacity))
        for claim_key in state.productive_disagreement_claim_keys:
            if len(task_specs) >= planned_limit:
                break
            if claim_key in active_claims:
                continue
            task_specs.append(
                {
                    "title": self._coordination_synthesis_title(claim_key),
                    "description": self._coordination_synthesis_description(claim_key),
                    "priority": TaskPriority.HIGH,
                    "metadata": {
                        "source": "swarm.coordination_synthesis",
                        "coordination_origin": "sheaf_disagreement",
                        "coordination_claim_key": claim_key,
                        "coordination_topic": claim_key,
                        "coordination_state": "uncertain",
                        "coordination_uncertainty": 1.0,
                        "coordination_review_required": True,
                        "coordination_route": "synthesis_review",
                        "coordination_preferred_roles": [
                            "reviewer",
                            "researcher",
                            "general",
                        ],
                        "coordination_shared_context": [
                            (
                                f"Productive disagreement remains active for claim "
                                f"'{claim_key}'."
                            )
                        ],
                        "task_group": f"coordination:{claim_key}",
                        "coordination_triggered_at": state.observed_at,
                    },
                }
            )

        if not task_specs:
            return []

        created = await self.create_task_batch(task_specs)
        if created and self._memory is not None:
            await self._memory.remember(
                f"Spawned {len(created)} coordination synthesis task(s)",
                layer=MemoryLayer.SESSION,
                source="swarm.coordination_synthesis",
            )
        return created

    # --- Orchestration ---

    async def dispatch_next(self) -> int:
        """Run one orchestration tick. Returns number of tasks dispatched."""
        await self.spawn_latent_gold_tasks()
        dispatches = await self._orchestrator.route_next()
        coordination = await self.coordination_status(refresh=True)
        await self.spawn_coordination_tasks(coordination=coordination)
        return len(dispatches)

    # ── Algedonic Channel (Beer S5 bypass to operator) ─────────────
    def _algedonic_handler(self, signal: Any) -> None:
        """Beer's algedonic channel: pain signal → file + macOS notification.

        This is the S5 bypass — critical signals skip S1-S4 and reach
        the operator (Dhyana) directly.  Wired as on_algedonic callback
        in OrganismRuntime.
        """
        import json as _json
        import subprocess

        # 1. Append to persistent signal log
        log_path = self.state_dir / "algedonic_signals.jsonl"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "kind": getattr(signal, "kind", "unknown"),
                "severity": getattr(signal, "severity", "unknown"),
                "action": getattr(signal, "action", ""),
                "value": getattr(signal, "value", 0.0),
                "timestamp": getattr(signal, "timestamp", 0.0),
            }
            with log_path.open("a", encoding="utf-8") as f:
                f.write(_json.dumps(entry) + "\n")
        except OSError as exc:
            logger.warning("Algedonic log write failed: %s", exc)

        # 2. Write EMERGENCY_HOLD marker if critical
        severity = getattr(signal, "severity", "")
        if severity == "critical":
            hold_path = self.state_dir / "EMERGENCY_HOLD"
            try:
                hold_path.write_text(
                    f"{getattr(signal, 'kind', 'unknown')}: "
                    f"value={getattr(signal, 'value', 0):.3f}\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.warning("EMERGENCY_HOLD write failed: %s", exc)

        # 3. macOS notification (non-blocking, best-effort)
        kind = getattr(signal, "kind", "unknown")
        value = getattr(signal, "value", 0)
        try:
            subprocess.Popen(
                [
                    "osascript", "-e",
                    f'display notification "ALGEDONIC [{severity}]: {kind} = {value:.3f}" '
                    f'with title "DHARMA SWARM" sound name "Sosumi"',
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            logger.debug("macOS notification failed", exc_info=True)

        logger.warning(
            "ALGEDONIC SIGNAL [%s] %s = %.3f → %s",
            severity, kind, value, getattr(signal, "action", ""),
        )

    def _check_human_overrides(self) -> dict[str, Any]:
        """Check .PAUSE, .FOCUS, .INJECT, EMERGENCY_HOLD files."""
        result: dict[str, Any] = {"paused": False, "focus": None, "inject": None}

        pause_path = self.state_dir / self._daemon.pause_file
        if pause_path.exists():
            result["paused"] = True
            return result

        # Algedonic EMERGENCY_HOLD — persists across restarts until operator clears
        emergency_path = self.state_dir / "EMERGENCY_HOLD"
        if emergency_path.exists():
            logger.warning("EMERGENCY_HOLD active — dispatch paused (rm %s to clear)", emergency_path)
            result["paused"] = True
            return result

        if self._thread_mgr:
            result["focus"] = self._thread_mgr.check_focus_override(self.state_dir)
            result["inject"] = self._thread_mgr.check_inject_override(self.state_dir)

        return result

    def _in_quiet_hours(self) -> bool:
        """Check if current hour is in quiet hours."""
        return datetime.now().hour in self._daemon.quiet_hours

    def _contribution_allowed(self) -> bool:
        """Check rate limits: daily max, min interval between contributions."""
        now = datetime.now()

        # Reset daily counter at midnight
        if self._daily_reset is None or now.date() != self._daily_reset.date():
            self._daily_contributions = 0
            self._daily_reset = now

        if self._daily_contributions >= self._daemon.max_daily_contributions:
            return False

        if self._last_contribution:
            elapsed = (now - self._last_contribution).total_seconds()
            if elapsed < self._daemon.min_between_contributions:
                return False

        return True

    @staticmethod
    def _tick_did_work(activity: Any) -> bool:
        """Return True when an orchestration tick performed real work."""
        if isinstance(activity, dict):
            for key in ("dispatched", "settled", "recovered"):
                try:
                    if int(activity.get(key, 0) or 0) > 0:
                        return True
                except Exception:
                    continue
            return False
        if isinstance(activity, (int, float)):
            return activity > 0
        return bool(activity)

    async def _tick_living_layers(self) -> dict[str, int]:
        """Run stigmergy decay and other living-layer maintenance."""
        summary: dict[str, int] = {}
        if self._stigmergy:
            try:
                decayed = await self._stigmergy.decay()
                summary["stigmergy_decayed"] = decayed
            except Exception as exc:
                logger.info("Stigmergy decay failed (transient): %s", exc)
            try:
                faded = await self._stigmergy.access_decay()
                summary["stigmergy_faded"] = faded
            except Exception as exc:
                logger.debug("Stigmergy access_decay failed: %s", exc)
        return summary

    def _derive_failure_source(self, task: Task) -> str:
        meta = dict(task.metadata or {})
        source = str(meta.get("last_failure_source", "")).strip()
        if source:
            return source
        result = str(task.result or "").lower()
        if "timed out" in result or result.startswith("timeout:"):
            return "timeout"
        return "execution_error"

    async def rescue_recent_failures(
        self,
        *,
        limit: int = 4,
        max_age: timedelta | None = None,
    ) -> list[Task]:
        """Requeue recent transient failures once under the current retry policy."""
        if self._task_board is None or self._orchestrator is None:
            return []

        failed = await self._task_board.list_tasks(status=TaskStatus.FAILED, limit=200)
        if not failed:
            return []

        active_titles: set[str] = set()
        for status in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING):
            tasks = await self._task_board.list_tasks(status=status, limit=500)
            for item in tasks:
                title = item.title.strip().lower()
                if title:
                    active_titles.add(title)

        now = datetime.now(timezone.utc)
        age_limit = max_age or self._auto_rescue_max_age
        rescued: list[Task] = []

        for task in sorted(failed, key=lambda item: item.updated_at, reverse=True):
            if len(rescued) >= limit:
                break
            if now - task.updated_at > age_limit:
                continue

            meta = dict(task.metadata or {})
            rescue_count = int(meta.get("auto_rescue_count", 0) or 0)
            if rescue_count >= self._auto_rescue_max_attempts:
                continue
            if meta.get("auto_rescue_disabled"):
                continue

            title_key = task.title.strip().lower()
            if title_key and title_key in active_titles:
                continue

            source = self._derive_failure_source(task)
            failure_class = self._orchestrator._classify_failure(
                error=str(task.result or ""),
                source=source,
                task=task,
            )
            if failure_class not in {"connection_transient", "long_timeout"}:
                continue

            retry_count, max_retries, backoff = self._orchestrator._resolve_retry_policy(task)
            max_retries, backoff = self._orchestrator._apply_failure_retry_defaults(
                task=task,
                meta=meta,
                failure_class=failure_class,
                max_retries=max_retries,
                backoff=backoff,
            )

            meta["retry_count"] = 0
            meta["max_retries"] = max_retries
            meta["retry_backoff_seconds"] = backoff
            meta.pop("retry_not_before_epoch", None)
            meta.pop("active_claim", None)
            meta["last_failure_class"] = failure_class
            meta["auto_rescue_count"] = rescue_count + 1
            meta["auto_rescued_at"] = now.isoformat()
            meta["auto_rescue_reason"] = "daemon.failure_rescue_sweep"

            await self._task_board.requeue(
                task.id,
                reason="Requeued by automatic failure rescue sweep",
                metadata=meta,
            )
            refreshed = await self._task_board.get(task.id)
            if refreshed is not None:
                rescued.append(refreshed)
                if title_key:
                    active_titles.add(title_key)

        if rescued and self._memory is not None:
            await self._memory.remember(
                f"Automatic rescue sweep requeued {len(rescued)} failed task(s)",
                layer=MemoryLayer.SESSION,
                source="swarm.failure_rescue",
            )
        return rescued

    async def _director_pulse(self) -> list[Task]:
        """Run one ThinkodynamicDirector vision pulse.

        Uses the lightweight ``sense()`` path (ecosystem signal ranking and
        opportunity detection) to avoid shelling out to an LLM on every tick.
        Tasks are enqueued via the director's own ``enqueue_workflow`` which
        writes to the shared task-board database.

        Returns:
            List of tasks created by the director, possibly empty.
        """
        if self._director is None:
            return []

        try:
            # Saturation guard: skip if the director already has plenty in-flight
            active_count = await self._director.active_director_task_count()
            if active_count >= self._director.max_active_tasks:
                logger.debug(
                    "Director pulse skipped: director tasks saturated (%d active)",
                    active_count,
                )
                return []

            # STRATOSPHERE: lightweight ecosystem sensing (no LLM call)
            sense_result = self._director.sense()
            opportunities = sense_result.get("opportunities", [])
            if not opportunities:
                logger.debug("Director pulse: no opportunities detected")
                return []

            # GROUND: compile a workflow from the top opportunity
            import time as _time

            cycle_id = f"swarm-{int(_time.time())}"
            # Build a minimal vision stub so compile_workflow_from_vision
            # falls through to the opportunity-based planner.
            vision_stub: dict[str, Any] = {
                "proposed_tasks": [],
                "vision_text": "",
                "vision_success": False,
                "seeds": [],
                "ecosystem": sense_result.get("signals", {}),
            }
            workflow = self._director.compile_workflow_from_vision(
                vision_stub, sense_result, cycle_id=cycle_id,
            )

            # DELEGATE: enqueue into the shared task board
            created = await self._director.enqueue_workflow(workflow)

            if created and self._memory is not None:
                primary = sense_result.get("primary")
                label = primary.title if primary else "ecosystem signal"
                await self._memory.remember(
                    f"Director pulse: {len(created)} task(s) from '{label}'",
                    layer=MemoryLayer.SESSION,
                    source="thinkodynamic_director",
                )
                logger.info(
                    "Director pulse created %d task(s) for '%s'",
                    len(created),
                    label,
                )
            return created

        except Exception as exc:
            logger.debug("Director pulse error: %s", exc)
            return []

    async def tick(self) -> dict[str, Any]:
        """Execute one full swarm lifecycle tick.

        This is the unified control path -- the ONLY way to advance
        swarm state.  Both run() and orchestrate_live call this.

        v0.7.0: OrganismRuntime heartbeat runs every _organism_interval_ticks.
        When the Gnani says HOLD, autonomous generation and dispatch are
        suppressed — the organism's pain signal overrides busywork.
        """
        result: dict[str, Any] = {
            "paused": False, "circuit_broken": False,
            "dispatched": 0, "settled": 0, "rescued": 0,
            "synthesized": 0, "director_proposals": 0,
            "reopened": 0, "living_summary": {},
            "organism_verdict": None, "organism_power": None,
        }
        overrides = self._check_human_overrides()
        if overrides["paused"]:
            result["paused"] = True
            return result
        if overrides["focus"] and self._thread_mgr:
            self._thread_mgr._current_thread = overrides["focus"]
        if self._daemon.circuit_breaker.is_broken:
            result["circuit_broken"] = True
            return result

        # v0.9.1: Deferred Telos Substrate seeding (once, first tick)
        if not self._telos_substrate_seeded:
            self._telos_substrate_seeded = True
            try:
                from dharma_swarm.telos_substrate import TelosSubstrate

                substrate = TelosSubstrate(state_dir=self.state_dir)
                seed_result = await substrate.seed_all()
                logger.info("TelosSubstrate seeded: %s", seed_result)
            except Exception as e:
                logger.warning("TelosSubstrate seeding failed (non-fatal): %s", e)

        allow_autonomous_generation = True
        if self._in_quiet_hours():
            allow_autonomous_generation = False
        if not self._contribution_allowed():
            allow_autonomous_generation = False

        # ── Organism heartbeat: Gnani / Samvara ──
        # Runs every _organism_interval_ticks. When the Gnani says HOLD,
        # we suppress autonomous generation — no new busywork until
        # coherence recovers or Samvara completes its diagnostic cycle.
        self._tick_count += 1
        gnani_holds = False
        if (self._organism is not None
                and self._tick_count % self._organism_interval_ticks == 0):
            try:
                hb = await self._organism.heartbeat()
                result["organism_verdict"] = hb.gnani_verdict.decision if hb.gnani_verdict else None
                result["organism_power"] = (
                    self._organism.samvara.current_power.value
                    if self._organism.samvara.active else None
                )
                if hb.gnani_verdict and hb.gnani_verdict.decision == "HOLD":
                    gnani_holds = True
                    allow_autonomous_generation = False
                    logger.warning(
                        "Gnani HOLD (cycle %d, power=%s): %s — suppressing dispatch",
                        hb.cycle,
                        result["organism_power"] or "—",
                        hb.gnani_verdict.reason,
                    )
                # ── Samvara corrections → task pipeline ──
                # When Samvara diagnoses issues, turn corrections into
                # high-priority tasks so the TD can act on them.
                if hb.samvara_diagnostic and hb.samvara_diagnostic.corrections:
                    try:
                        corrections_created = 0
                        for corr in hb.samvara_diagnostic.corrections[:3]:
                            await self._task_board.create(
                                title=f"[samvara] {corr[:80]}",
                                description=(
                                    f"Samvara correction (power={result['organism_power'] or 'unknown'}, "
                                    f"cycle={hb.cycle}): {corr}"
                                ),
                                priority=TaskPriority.HIGH,
                                created_by="samvara",
                            )
                            corrections_created += 1
                        if corrections_created:
                            logger.info(
                                "Samvara → %d correction tasks enqueued", corrections_created,
                            )
                    except Exception as corr_exc:
                        logger.debug("Samvara correction task creation failed: %s", corr_exc)
            except Exception as exc:
                logger.debug("Organism heartbeat error: %s", exc)

        rescued: list[Task] = []
        now = datetime.now(timezone.utc)
        if (self._last_auto_rescue_scan is None
            or (now - self._last_auto_rescue_scan).total_seconds()
            >= self._auto_rescue_scan_interval_seconds):
            rescued = await self.rescue_recent_failures()
            self._last_auto_rescue_scan = now
        result["rescued"] = len(rescued)

        reopened: list[Any] = []
        if allow_autonomous_generation:
            reopened = await self.spawn_latent_gold_tasks()
        result["reopened"] = len(reopened)

        # When Gnani holds, skip orchestrator dispatch — no new task execution
        if not gnani_holds:
            activity = await self._orchestrator.tick()
            result["dispatched"] = activity.get("dispatched", 0)
            result["settled"] = activity.get("settled", 0)
        else:
            # Still settle completed tasks, just don't dispatch new ones
            activity = await self._orchestrator.tick_settle_only()

        coordination = await self.coordination_status(refresh=False)
        synthesized = await self.spawn_coordination_tasks(coordination=coordination)
        result["synthesized"] = len(synthesized)

        director_proposals: list[Task] = []
        if (allow_autonomous_generation and self._director is not None
            and self._tick_count % self._director_interval_ticks == 0):
            try:
                director_proposals = await self._director_pulse()
            except Exception:
                logger.debug("Director pulse failed", exc_info=True)
        result["director_proposals"] = len(director_proposals)

        living_summary: dict[str, int] = {}
        if self._tick_count % self._living_interval_ticks == 0:
            living_summary = await self._tick_living_layers()
        result["living_summary"] = living_summary

        # ── Witness audit (Beer S3*): sporadic random audit ──
        if (self._witness is not None
                and self._tick_count % self._witness_interval_ticks == 0):
            try:
                findings = await self._witness.run_cycle()
                result["witness_findings"] = len(findings)
                actionable = sum(1 for f in findings if f.is_actionable)
                if actionable:
                    logger.info(
                        "Witness S3* audit: %d findings, %d actionable",
                        len(findings), actionable,
                    )
            except Exception as exc:
                logger.debug("Witness audit error: %s", exc)

        did_work = (bool(reopened) or bool(rescued) or bool(synthesized)
                    or bool(director_proposals) or self._tick_did_work(activity))
        if did_work:
            self._last_contribution = datetime.now()
            self._daily_contributions += 1
            self._daemon.circuit_breaker.record_success()
            if self._thread_mgr:
                self._thread_mgr.record_contribution()
        return result

    async def run(self, interval: float | None = None) -> None:
        """Run the orchestration loop with Garden Daemon parameters.

        In daemon mode (interval=None), uses heartbeat_interval from config.
        In interactive mode, uses the provided interval.
        """
        tick_interval = interval if interval is not None else self._daemon.heartbeat_interval

        while self._running:
            try:
                activity = await self.tick()
                if activity.get("paused"):
                    await asyncio.sleep(60)
                    continue
                if activity.get("circuit_broken"):
                    await asyncio.sleep(min(tick_interval, 300))
                    continue
            except Exception as exc:
                logger.exception("Tick failed: %s", exc)
                tripped = self._daemon.circuit_breaker.record_failure()
                if tripped:
                    if self._thread_mgr:
                        self._thread_mgr.rotate()
            await asyncio.sleep(tick_interval)

    def stop(self) -> None:
        """Stop the swarm."""
        self._running = False
        if self._orchestrator:
            self._orchestrator.stop()

    # --- Status ---

    async def status(self) -> SwarmState:
        """Get current swarm state snapshot."""
        agents = await self._agent_pool.list_agents() if self._agent_pool else []
        task_stats = await self._task_board.stats() if self._task_board else {}
        state = SwarmState(
            agents=agents,
            tasks_pending=task_stats.get("pending", 0),
            tasks_running=task_stats.get("running", 0),
            tasks_completed=task_stats.get("completed", 0),
            tasks_failed=task_stats.get("failed", 0),
            uptime_seconds=time.monotonic() - self._start_time,
        )
        # Attach organism status if available
        if self._organism is not None:
            state.organism = self._organism.status()
        return state

    async def coordination_status(
        self,
        *,
        refresh: bool = True,
    ) -> SwarmCoordinationState:
        """Return a compact sheaf-based coordination snapshot."""
        if self._orchestrator is None:
            return SwarmCoordinationState()
        getter = getattr(self._orchestrator, "get_coordination_summary", None)
        if getter is None:
            return SwarmCoordinationState()
        payload = getter(refresh=refresh)
        if asyncio.iscoroutine(payload):
            payload = await payload
        if not isinstance(payload, dict):
            return SwarmCoordinationState()
        state = SwarmCoordinationState.model_validate(payload)
        if refresh and self._engine is not None:
            observer = getattr(self._engine, "observe_coordination_summary", None)
            if callable(observer):
                observer(state.model_dump())
        return state

    # --- Thread ---

    @property
    def current_thread(self) -> str | None:
        return self._thread_mgr.current_thread if self._thread_mgr else None

    def rotate_thread(self) -> str | None:
        if self._thread_mgr:
            return self._thread_mgr.rotate()
        return None

    # --- Memory ---

    async def remember(self, content: str) -> None:
        """Store a memory in the swarm's strange loop."""
        await self._memory.remember(
            content, layer=MemoryLayer.SESSION, source="user"
        )

    async def recall(self, limit: int = 10) -> list:
        """Recall recent memories."""
        return await self._memory.recall(limit=limit)

    # --- Decision Ontology (v0.9.0) ---

    def record_decision(self, decision: Any) -> Any:
        """Evaluate and persist a DecisionRecord. Returns DecisionQualityAssessment."""
        if self._decision_log is None:
            raise SubsystemNotReady("decision_log not initialized")
        return self._decision_log.record(decision)

    def list_decisions(self, *, limit: int = 50) -> list:
        """Return recent decisions from the log."""
        if self._decision_log is None:
            return []
        return self._decision_log.list_decisions(limit=limit)

    # --- Evolution (v0.2.0) ---

    async def evolve(
        self,
        component: str,
        change_type: str,
        description: str,
        diff: str = "",
        test_results: dict | None = None,
        code: str | None = None,
    ) -> dict:
        """Run a single evolution proposal through the full pipeline.

        Returns a summary dict with entry_id, fitness, and status.
        """
        if self._engine is None:
            raise RuntimeError("Swarm not initialized — call init() first")

        proposal = await self._engine.propose(
            component=component,
            change_type=change_type,
            description=description,
            diff=diff,
        )
        await self._engine.gate_check(proposal)
        if proposal.status.value == "rejected":
            return {"status": "rejected", "reason": proposal.gate_reason}

        await self._engine.evaluate(proposal, test_results=test_results, code=code)
        entry_id = await self._engine.archive_result(proposal)

        fitness = proposal.actual_fitness
        return {
            "status": "archived",
            "entry_id": entry_id,
            "weighted_fitness": fitness.weighted() if fitness else 0.0,
        }

    async def health_check(self) -> dict:
        """Run system health check. Returns report as dict."""
        if self._monitor is None:
            return {"status": "unknown", "reason": "monitor not initialized"}
        report = await self._monitor.check_health()
        return report.model_dump()

    async def fitness_trend(self, component: str | None = None) -> list:
        """Get fitness trend from the evolution archive."""
        if self._engine is None:
            return []
        return await self._engine.get_fitness_trend(component=component)

    # --- Dharma Status (v0.3.0) ---

    async def dharma_status(self) -> dict:
        """Return Dharma subsystem status."""
        result: dict = {
            "kernel": False,
            "corpus": False,
            "compiler": False,
            "canary": False,
            "stigmergy": False,
        }
        if self._kernel_guard:
            try:
                kernel = self._kernel_guard._kernel
                result["kernel"] = kernel is not None
                if kernel:
                    result["kernel_axioms"] = len(kernel.principles)
                    result["kernel_integrity"] = kernel.verify_integrity()
            except Exception:
                logger.debug("Kernel status check failed", exc_info=True)
        if self._corpus:
            claims = await self._corpus.list_claims()
            result["corpus"] = True
            result["corpus_claims"] = len(claims)
        if self._compiler:
            result["compiler"] = True
        if self._canary:
            result["canary"] = True
        if self._stigmergy:
            result["stigmergy"] = True
            result["stigmergy_density"] = self._stigmergy.density()
        return result

    async def gaia_health(self) -> dict:
        """Return GAIA ecological subsystem health."""
        try:
            from dharma_swarm.gaia_ledger import GaiaLedger
            from dharma_swarm.gaia_fitness import (
                EcologicalFitness,
                detect_goodhart_drift,
            )

            ledger_dir = self.state_dir / "gaia_ledger"
            if not ledger_dir.exists():
                return {"status": "no_ledger", "message": "No GAIA ledger found"}

            ledger = GaiaLedger(data_dir=ledger_dir)
            ledger.load()
            eco = EcologicalFitness()
            drift = detect_goodhart_drift(ledger)

            return {
                "status": "active",
                "weighted_fitness": eco.weighted_score(ledger),
                "is_drifting": drift["is_drifting"],
                "verification_ratio": drift["verification_ratio"],
                "diagnosis": drift["diagnosis"],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def propose_claim(
        self, statement: str, category: str = "operational", **kwargs: Any
    ) -> dict:
        """Propose a new claim to the Dharma Corpus."""
        if self._corpus is None:
            raise RuntimeError("Corpus not initialized")
        from dharma_swarm.dharma_corpus import ClaimCategory
        cat = ClaimCategory(category)
        claim = await self._corpus.propose(statement=statement, category=cat, **kwargs)
        return {"id": claim.id, "statement": claim.statement, "status": claim.status.value}

    async def review_claim(
        self, claim_id: str, reviewer: str, action: str, comment: str
    ) -> dict:
        """Review a claim in the Dharma Corpus."""
        if self._corpus is None:
            raise RuntimeError("Corpus not initialized")
        claim = await self._corpus.review(
            claim_id, reviewer=reviewer, action=action, comment=comment
        )
        return {
            "id": claim.id,
            "status": claim.status.value,
            "reviews": len(claim.review_history),
        }

    async def promote_claim(self, claim_id: str) -> dict:
        """Promote a claim to ACCEPTED status."""
        if self._corpus is None:
            raise RuntimeError("Corpus not initialized")
        claim = await self._corpus.promote(claim_id)
        return {"id": claim.id, "status": claim.status.value}

    async def canary_check(self, entry_id: str, canary_fitness: float) -> dict:
        """Evaluate a canary deployment."""
        if self._canary is None:
            raise RuntimeError("Canary not initialized")
        result = await self._canary.evaluate_canary(entry_id, canary_fitness)
        return {
            "decision": result.decision.value,
            "delta": result.delta,
            "reason": result.reason,
        }

    async def compile_policy(self, context: str = "default") -> dict:
        """Compile a policy from kernel + accepted corpus claims."""
        if self._compiler is None or self._kernel_guard is None or self._corpus is None:
            raise RuntimeError("Policy subsystems not initialized")
        principles = self._kernel_guard.get_all_principles()
        from dharma_swarm.dharma_corpus import ClaimStatus
        accepted_objs = await self._corpus.list_claims(status=ClaimStatus.ACCEPTED)
        policy = self._compiler.compile(
            kernel_principles=principles,
            accepted_claims=accepted_objs,
            context=context,
        )
        return {
            "total_rules": len(policy.rules),
            "immutable": len(policy.get_immutable_rules()),
            "mutable": len(policy.get_mutable_rules()),
            "context": policy.context,
        }

    # --- v0.4.0: Oz-Inspired Operations ---

    async def route_task(self, description: str) -> dict:
        """Route a task to the best skill via intent detection.

        Returns intent analysis including recommended skill, complexity,
        risk level, and agent count.
        """
        if self._intent_router is None:
            return {"error": "Intent router not initialized"}
        skill_name, intent = self._intent_router.route(description)
        return {
            "skill": skill_name,
            "confidence": intent.confidence,
            "complexity": intent.complexity,
            "risk": intent.risk_level,
            "recommended_agents": intent.recommended_agents,
            "parallel": intent.parallel,
        }

    async def decompose_task(self, description: str) -> dict:
        """Decompose a complex task into sub-tasks.

        Returns decomposed task with sub-tasks, agent recommendations,
        and parallelism analysis.
        """
        if self._intent_router is None:
            return {"error": "Intent router not initialized"}
        result = self._intent_router.decompose(description)
        return {
            "original": result.original,
            "sub_tasks": [
                {
                    "task": st.task,
                    "skill": st.primary_skill,
                    "complexity": st.complexity,
                    "risk": st.risk_level,
                }
                for st in result.sub_tasks
            ],
            "total_agents": result.total_agents,
            "has_parallel_work": result.has_parallel_work,
            "estimated_complexity": result.estimated_complexity,
        }

    async def search_context(self, query: str, budget: int = 10_000) -> str:
        """Search for task-relevant context (lazy loading).

        Instead of dumping all 30K of context, returns only what's
        relevant to the query. Saves ~26% tokens (Warp's finding).
        """
        if self._context_search is None:
            return ""
        return self._context_search.get_context_for_task(query, budget=budget)

    async def check_autonomy(self, action: str) -> dict:
        """Check if an action should be auto-approved.

        Returns autonomy decision with risk level, confidence,
        and whether to auto-approve or escalate.
        """
        if self._autonomy is None:
            return {"auto_approve": False, "reason": "Autonomy engine not initialized"}
        decision = self._autonomy.should_auto_approve(action)
        return {
            "auto_approve": decision.auto_approve,
            "risk": decision.risk.value,
            "reason": decision.reason,
            "escalate_to": decision.escalate_to,
        }

    def list_skills(self) -> list[dict]:
        """List all discovered skills."""
        if self._skill_registry is None:
            return []
        return [
            {
                "name": s.name,
                "model": s.model,
                "provider": s.provider,
                "autonomy": s.autonomy,
                "tags": s.tags,
                "description": s.description[:100],
            }
            for s in self._skill_registry.list_all()
        ]

    def hot_reload_skills(self) -> list[str]:
        """Hot-reload changed skill files. Returns names of reloaded skills."""
        if self._skill_registry is None:
            return []
        return self._skill_registry.hot_reload()

    async def compose_task(self, description: str) -> dict:
        """Compose a task into a DAG execution plan."""
        if self._skill_composer is None:
            return {"error": "Skill composer not initialized"}
        plan = self._skill_composer.compose(description)
        waves = plan.execution_order()
        return {
            "task": plan.task,
            "status": plan.status,
            "steps": [{"id": s.step_id, "skill": s.skill_name,
                       "task": s.task, "deps": s.depends_on}
                      for s in plan.steps],
            "waves": [[s.step_id for s in wave] for wave in waves],
            "ready": [s.step_id for s in plan.ready_steps()],
        }

    async def execute_composition(self, description: str) -> dict:
        """Compose and execute a task as a DAG plan.

        Builds a composition plan via SkillComposer, then runs it
        through the DAGExecutor with a runner that creates real tasks.

        Args:
            description: Natural language task description.

        Returns:
            Execution result dict with step-by-step outcomes.
        """
        if self._skill_composer is None:
            return {"error": "Skill composer not initialized"}

        plan = self._skill_composer.compose(description)

        from dharma_swarm.dag_executor import DAGExecutor
        from dharma_swarm.skill_composer import SkillStep

        async def _runner(step: SkillStep, context: str) -> str:
            """Execute a composition step by creating and running a swarm task."""
            task = await self.create_task(
                title=step.task,
                description=f"{step.task}\n\nContext:\n{context}" if context else step.task,
            )
            return f"Task {task.id} created: {step.task}"

        executor = DAGExecutor(composer=self._skill_composer, runner_fn=_runner)
        result = await executor.execute(plan)

        return {
            "task": result.plan_task,
            "status": result.status,
            "steps_completed": result.steps_completed,
            "steps_failed": result.steps_failed,
            "steps_skipped": result.steps_skipped,
            "duration": round(result.total_duration_seconds, 2),
            "steps": [
                {
                    "id": sr.step_id,
                    "skill": sr.skill_name,
                    "success": sr.success,
                    "output": sr.output[:200] if sr.output else "",
                    "error": sr.error,
                }
                for sr in result.step_results
            ],
        }

    async def create_handoff(
        self, from_agent: str, to_agent: str, task_context: str,
        artifacts: list[dict],
    ) -> dict:
        """Create a structured handoff between agents."""
        if self._handoff is None:
            return {"error": "Handoff protocol not initialized"}
        from dharma_swarm.handoff import Artifact, ArtifactType
        typed = [
            Artifact(
                artifact_type=ArtifactType(a.get("type", "context")),
                content=a.get("content", ""),
                summary=a.get("summary", ""),
                files_touched=a.get("files", []),
            )
            for a in artifacts
        ]
        h = await self._handoff.create_handoff(
            from_agent=from_agent, to_agent=to_agent,
            task_context=task_context, artifacts=typed,
        )
        return {"id": h.id, "status": h.status, "summary": h.summary()}

    async def get_agent_memory(self, agent_name: str) -> dict:
        """Get or create an agent's memory bank and return stats."""
        if agent_name not in self._agent_memories:
            from dharma_swarm.agent_memory import AgentMemoryBank
            bank = AgentMemoryBank(
                agent_name=agent_name,
                base_path=self.state_dir / "agent_memory",
            )
            await bank.load()
            self._agent_memories[agent_name] = bank
        bank = self._agent_memories[agent_name]
        return await bank.get_stats()

    async def agent_remember(self, agent_name: str, key: str, value: str,
                             category: str = "working", importance: float = 0.5) -> dict:
        """Store a memory for an agent."""
        if agent_name not in self._agent_memories:
            await self.get_agent_memory(agent_name)
        bank = self._agent_memories[agent_name]
        entry = await bank.remember(key, value, category=category,
                                    importance=importance, source=agent_name)
        await bank.save()
        return {"key": entry.key, "category": entry.category,
                "importance": entry.importance}

    # --- Shutdown ---

    async def shutdown(self, drain_timeout: float = 30.0) -> None:
        """Graceful ordered shutdown of entire swarm.

        Varela's autopoiesis: clean death is part of the lifecycle.
        Teardown order is reverse of init — coordination first,
        then agents, then infrastructure.
        """
        self._running = False
        logger.info("Swarm shutdown initiated (drain_timeout=%.1fs)", drain_timeout)

        # 1. Stop orchestrator (cancel in-flight tasks with drain)
        if self._orchestrator:
            try:
                await self._orchestrator.graceful_stop(timeout=drain_timeout)
            except Exception as exc:
                logger.warning("Orchestrator graceful stop failed: %s", exc)
                self._orchestrator.stop()

        # 2. Stop director (optional subsystem)
        if self._director:
            try:
                stop_fn = getattr(self._director, "stop", None)
                if stop_fn:
                    result = stop_fn()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:
                logger.debug("Director stop failed (non-fatal): %s", exc)

        # 3. Shutdown agents
        if self._agent_pool:
            try:
                await self._agent_pool.shutdown_all()
            except Exception as exc:
                logger.warning("Agent pool shutdown failed: %s", exc)

        # 4. Close closeable providers in the router
        try:
            for provider in getattr(self._router, "_providers", {}).values():
                close_fn = getattr(provider, "close", None)
                if close_fn:
                    result = close_fn()
                    if asyncio.iscoroutine(result):
                        await result
        except Exception as exc:
            logger.debug("Provider close failed (non-fatal): %s", exc)

        # 5. Record shutdown in memory
        if self._memory:
            try:
                await self._memory.remember(
                    "Swarm shutdown", layer=MemoryLayer.SESSION, source="swarm"
                )
            except Exception:
                logger.debug("Shutdown memory write failed", exc_info=True)

        self._initialized.clear()
        logger.info("Swarm shutdown complete")

    async def __aenter__(self) -> "SwarmManager":
        """Async context manager: init on enter."""
        await self.init()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager: shutdown on exit."""
        await self.shutdown()
