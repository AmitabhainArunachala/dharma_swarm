---
title: dharma_swarm Navigation Map
path: docs/architecture/NAVIGATION.md
slug: dharma-swarm-navigation-map
doc_type: note
status: active
summary: dharma swarm Navigation Map
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - CLAUDE.md
  - dharma_swarm/models.py
  - dharma_swarm/config.py
  - dharma_swarm/telos_gates.py
  - dharma_swarm/providers.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- software_architecture
- knowledge_management
- cybernetics
- research_methodology
inspiration:
- stigmergy
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- dharma_swarm/models.py
- dharma_swarm/config.py
- dharma_swarm/telos_gates.py
- dharma_swarm/providers.py
- garden_daemon.py
connected_python_modules:
- dharma_swarm.models
- dharma_swarm.config
- dharma_swarm.telos_gates
- dharma_swarm.providers
- garden_daemon
connected_relevant_files:
- CLAUDE.md
- dharma_swarm/models.py
- dharma_swarm/config.py
- dharma_swarm/telos_gates.py
- dharma_swarm/providers.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/architecture/NAVIGATION.md
  retrieval_terms:
  - navigation
  - map
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: dharma swarm Navigation Map
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/NAVIGATION.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# dharma_swarm Navigation Map

Generated: 2026-03-29 | 500 Python modules | 494 test files | 8,848 tests

---

## Quick Reference

| Need to... | Go to... |
|------------|----------|
| Understand the system | `CLAUDE.md` (this repo root) |
| Run the live orchestrator | `dgc orchestrate-live` (or `--background`) |
| Check system health | `dgc status` / `dgc health` |
| Run all tests | `python3 -m pytest tests/ -q` (~6 min) |
| Run one test file | `python3 -m pytest tests/test_foo.py -q` |
| Start/stop daemon | `dgc up [--background]` / `dgc down` |
| Check daemon | `dgc daemon-status` |
| Launch TUI | `dgc` (no args) |
| Read stigmergy | `dgc stigmergy` |
| Check kernel integrity | `dgc dharma status` |
| See evolution trend | `dgc evolve trend` |
| See subconscious dreams | `dgc hum` |
| Find a module | Search this file or `ls dharma_swarm/dharma_swarm/*.py` |
| Find the data model | `dharma_swarm/models.py` |
| Find the config | `dharma_swarm/config.py` (env var overrides) |
| Add a new gate | `dharma_swarm/telos_gates.py` (GateRegistry.propose) |
| Add a new provider | `dharma_swarm/providers.py` + `providers_extended.py` |
| Understand the pillar foundations | `foundations/PILLAR_*.md` |
| See spec-forge specs | `spec-forge/` |

---

## Core Architecture (dharma_swarm/dharma_swarm/)

### Layer 0: Schema & Configuration

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `models.py` | 337 | Pydantic data models: Task, AgentConfig, AgentState, Message, enums (TaskStatus, AgentRole, ProviderType, GateTier, GateResult, GateDecision). ALL shared types. | Adding new shared data types |
| `config.py` | 248 | Central config (Pydantic models). OrchestratorConfig, AgentConfig_, LiveLoopConfig, SwarmConfig. Env var overrides. `DEFAULT_CONFIG` singleton. | Changing timeouts, thresholds, intervals |
| `profiles.py` | 158 | Agent profile definitions (capabilities, model preferences) | Adding/modifying agent profiles |

### Layer 1: Governance (S5 Identity + S3 Control)

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `dharma_kernel.py` | 396 | 25 immutable meta-principles (SHA-256 signed). `MetaPrinciple` enum, `PrincipleSpec`, `DharmaKernel` with `compute_signature()` / `verify_integrity()`. | Never (immutable by design) |
| `dharma_corpus.py` | 416 | Versioned claims with lifecycle (proposed/active/deprecated). JSONL persistence. The mutable knowledge layer that kernel constrains. | Adding/evolving system claims |
| `telos_gates.py` | 879 | 11 core gates (AHIMSA, SATYA, CONSENT, etc.), 3 tiers (A=block, B=block, C=review). `TelosGatekeeper.check()` returns `GateCheckResult`. Variety Expansion Protocol via `GateRegistry`. Witness logging to `~/.dharma/witness/`. | Adding gates via proposal protocol |
| `anekanta_gate.py` | 105 | Anekantavada (many-sidedness) gate evaluation | Modifying epistemic diversity checks |
| `dogma_gate.py` | 78 | Dogma drift detection gate | Modifying dogma detection patterns |
| `steelman_gate.py` | 87 | Steelman gate (charitable interpretation) | Modifying steelman heuristics |
| `guardrails.py` | 575 | 4 guardrail types, 5 autonomy levels. Constraint enforcement layer. | Adding guardrail types |
| `samvara.py` | 520 | Karmic influx prevention (Jain concept). No ungated mutations. | Changing mutation gating rules |
| `identity.py` | 547 | Beer S5 identity layer. System self-model. | Modifying identity assertions |
| `policy_compiler.py` | 167 | Compiles governance policies into enforceable rules | Adding policy compilation rules |
| `agent_constitution.py` | 540 | Constitutional constraints on agent behavior | Modifying agent behavioral constraints |
| `pramana.py` | 480 | Epistemology layer (valid means of knowledge). Jain pramana applied to AI claims. | Modifying epistemological validation |

### Layer 2: Runtime Core (S1 Operations + S2 Coordination)

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `swarm.py` | 2,359 | **SwarmManager** -- the facade. Integrates agent pool, task board, message bus, orchestrator, evolution, monitoring. Uses `TYPE_CHECKING` for lazy imports of 20+ subsystems. | Adding new subsystem integrations |
| `orchestrator.py` | 2,078 | Task routing, dispatching, priority management, retry logic | Modifying task dispatch strategy |
| `agent_runner.py` | 2,094 | **AgentRunner** (single agent lifecycle) + **AgentPool** (fleet management). Heartbeats, task execution, fitness signal emission. | Modifying agent execution behavior |
| `providers.py` | 2,098 | 9 LLM providers: Anthropic, OpenAI, OpenRouter, NVIDIA NIM, Local, ClaudeCode, Codex, OpenRouter Free, Ollama. `create_default_router()`. | Adding providers or changing routing |
| `providers_extended.py` | 214 | Extended provider configurations | Provider-specific extensions |
| `base_provider.py` | 198 | Abstract base class for all providers | Only if changing provider contract |
| `free_fleet.py` | 408 | Free model fleet (Ollama Cloud, NVIDIA NIM, OpenRouter Free) | Adding free model sources |
| `provider_policy.py` | 428 | Provider selection policies and cost optimization | Changing provider selection logic |
| `model_registry.py` | 170 | Model capability registry (context windows, costs, features) | Registering new models |
| `ontology.py` | 1,778 | **THE foundation.** Palantir-pattern typed objects: ObjectType, OntologyObj, LinkDef, Link, ActionDef, ActionExec, SecurityPolicy, OntologyRegistry. Everything flows through this. | Extending the ontology schema |
| `ontology_runtime.py` | var | Runtime ontology engine (query, mutate, link) | Modifying ontology query/mutation |
| `ontology_hub.py` | var | Central ontology catalog | Adding object type registrations |
| `ontology_agents.py` | var | Agent representations in the ontology | Modifying agent-as-ontology-object |
| `ontology_adapters.py` | var | Adapters between ontology and external systems | Adding external integrations |
| `ontology_query.py` | var | Query DSL for ontology objects | Adding query capabilities |
| `message_bus.py` | 615 | Async SQLite pub/sub (aiosqlite). Messages, heartbeats, subscriptions, artifact attachments. Ported from CHAIWALA. | Adding message types or channels |
| `signal_bus.py` | 171 | In-process event bus for inter-loop signaling. Emit/drain typed signals. `SignalBus.get()` singleton. NOT for agent communication (that is message_bus). | Adding signal types between loops |
| `task_board.py` | 522 | Task lifecycle management, priority queues, dependency tracking | Modifying task management |
| `handoff.py` | 363 | Agent-to-agent handoff protocol with typed artifacts | Modifying handoff behavior |

### Layer 3: Intelligence (S4)

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `thinkodynamic_director.py` | 5,006 | **Largest single module.** Orchestrates thinkodynamic scoring, routing, and decision-making. The "brain" that directs task allocation. | Modifying intelligence routing |
| `thinkodynamic_scorer.py` | 360 | Scores tasks/outputs on thinkodynamic dimensions | Changing scoring criteria |
| `context.py` | 1,344 | Agent orientation protocol. What context an agent gets before working. | Modifying agent context injection |
| `context_compiler.py` | 537 | Compiles context from multiple sources into agent prompts | Adding context sources |
| `context_agent.py` | 968 | Agent that manages context for other agents | Modifying context management behavior |
| `context_search.py` | 250 | Semantic search over context | Improving context retrieval |
| `zeitgeist.py` | 377 | S4 environmental scanning. Reads field state, competitive landscape. | Adding environment signals |
| `active_inference.py` | 495 | Friston free energy minimization applied to agent decisions | Modifying inference strategies |
| `decision_ontology.py` | 537 | First-class decisions with quality scoring | Adding decision types |
| `decision_router.py` | 323 | Routes decisions to appropriate evaluators | Modifying routing logic |
| `intent_router.py` | 563 | Routes user/agent intents to handlers | Adding intent types |
| `swarm_router.py` | 383 | Routes tasks across the swarm | Modifying swarm routing |
| `router_v1.py` | 391 | V1 routing algorithm | Legacy; prefer decision_router |
| `routing_memory.py` | 579 | Remembers routing outcomes for learning | Modifying routing feedback |
| `selector.py` | 252 | Parent selection for evolution | Changing selection algorithm |
| `ucb_selector.py` | 97 | UCB1 (Upper Confidence Bound) parent selection | Changing exploration/exploitation balance |
| `smart_seed_selector.py` | 359 | Intelligent seed selection for evolution | Modifying seed selection |

### Layer 4: Evolution & Learning

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `evolution.py` | 2,675 | **DarwinEngine** -- full evolution pipeline: propose, gate-check, write code, test, evaluate fitness, archive, select parents. | Modifying evolution pipeline |
| `cascade.py` | 491 | `F(S)=S` universal loop across 5 domains (code, skill, product, research, meta). The eigenform convergence cycle. | Adding cascade domains |
| `meta_evolution.py` | var | Meta-level evolution (evolving the evolution parameters) | Modifying meta-evolution |
| `genome_inheritance.py` | 299 | How agents inherit capabilities from parents | Modifying inheritance rules |
| `fitness_predictor.py` | var | Predicts mutation fitness before evaluation | Improving prediction accuracy |
| `training_flywheel.py` | 379 | Trajectory scoring, strategy reinforcement, dataset building | Modifying training data pipeline |
| `trajectory_collector.py` | var | Collects agent execution trajectories | Adding trajectory metadata |
| `strategy_reinforcer.py` | var | Reinforces successful strategies | Changing reinforcement logic |
| `population_control.py` | 656 | Agent population management (spawn, retire, balance) | Modifying population dynamics |
| `replication_protocol.py` | 842 | Agent self-replication protocol | Modifying replication rules |
| `convergence.py` | var | Convergence detection for evolution cycles | Adjusting convergence criteria |
| `elegance.py` | 345 | Code elegance scoring | Modifying elegance heuristics |

### Layer 5: Memory & Knowledge

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `stigmergy.py` | 373 | Pheromone-trail coordination. Agents leave marks; accumulated marks form shared intelligence. JSONL persistence, channeled visibility, salience thresholds. | Modifying stigmergy channels or mark schema |
| `memory.py` | 270 | StrangeLoopMemory -- agent memory with layers (immediate/session/development/witness/meta) | Modifying memory layer structure |
| `agent_memory.py` | 368 | AgentMemoryBank -- per-agent persistent memory | Modifying per-agent memory |
| `graph_nexus.py` | 1,108 | Unifies 6 existing graphs + telos graph + bridge layer | Adding graph types or bridge connections |
| `telos_graph.py` | 668 | Graph of telos alignment relationships | Modifying telos graph structure |
| `field_graph.py` | 406 | Competitive field knowledge graph | Adding field intelligence nodes |
| `temporal_graph.py` | var | Time-aware relationship graph | Adding temporal relationships |
| `catalytic_graph.py` | 395 | Autocatalytic set tracking (Kauffman) | Modifying catalytic set detection |
| `memory_lattice.py` | var | Lattice-structured memory organization | Modifying memory topology |
| `semantic_briefs.py` | 320 | Semantic summary generation | Improving summary quality |
| `semantic_digester.py` | 880 | Deep semantic digestion of content | Modifying digestion pipeline |
| `semantic_gravity.py` | 660 | Semantic distance/attraction calculations | Changing gravity model |
| `semantic_hardener.py` | 677 | Hardens semantic claims into verified knowledge | Modifying hardening criteria |
| `semantic_memory_bridge.py` | 430 | Bridge between semantic memory and other subsystems | Adding bridge endpoints |
| `semantic_researcher.py` | 420 | Autonomous semantic research agent | Modifying research behavior |
| `semantic_synthesizer.py` | 358 | Synthesizes knowledge from multiple sources | Changing synthesis logic |
| `traces.py` | 187 | Atomic JSON event log. `TraceEntry` model, `TraceStore` with lineage tracking. `atomic_write_json()` (tmpfile + os.replace). | Adding trace event types |
| `lineage.py` | 464 | Palantir Funnel provenance tracking, impact analysis | Adding provenance dimensions |

### Layer 6: Monitoring & Observability

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `monitor.py` | 585 | SystemMonitor -- anomaly detection, auto-healing | Adding anomaly detectors |
| `witness.py` | 394 | WitnessAuditor -- sporadic random audit of agent behavior (S3*) | Modifying audit sampling |
| `auditor.py` | 305 | Systematic audit engine | Adding audit dimensions |
| `metrics.py` | 410 | System metrics collection and aggregation | Adding metric types |
| `xray.py` | 1,218 | Deep diagnostic tool for system state | Adding diagnostic views |
| `doctor.py` | 1,124 | System health doctor -- diagnoses and prescribes fixes | Adding health checks |
| `pulse.py` | 640 | Heartbeat system with thread rotation and telos gate evaluation | Modifying pulse behavior |
| `canary.py` | 156 | Canary deployment (promote/rollback) | Modifying deployment strategy |
| `cost_tracker.py` | var | LLM API cost tracking | Adding cost tracking for new providers |
| `telemetry_plane.py` | var | Telemetry data plane | Adding telemetry channels |
| `telemetry_views.py` | var | Telemetry visualization | Adding views |
| `telemetry_optimizer.py` | var | Optimizes telemetry overhead | Modifying optimization rules |

### Layer 7: Living Layers (Subconscious / Creative)

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `shakti.py` | 200 | Creative perception layer (ShaktiLoop) | Modifying creative prompts |
| `subconscious.py` | 200 | Dream layer -- background pattern synthesis | Modifying dream generation |
| `subconscious_hum.py` | 327 | Extended subconscious with "hum" (background resonance) | Modifying hum behavior |
| `subconscious_v2.py` | var | V2 subconscious with fleet awareness | Upgrading subconscious |
| `subconscious_fleet.py` | var | Fleet-wide subconscious coordination | Modifying fleet dreaming |
| `sleep_cycle.py` | 488 | Consolidation during idle periods (neural consolidator) | Modifying sleep behavior |
| `hypnagogic.py` | var | Hypnagogic state processing (edge-of-sleep insights) | Adding hypnagogic patterns |
| `ouroboros.py` | 544 | Self-referential loop processing | Modifying ouroboros cycle |

### Layer 8: External Bridges

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `trishula_bridge.py` | 347 | Bridge to Trishula (three-agent Mac + 2 VPS comms) | Modifying cross-machine messaging |
| `ecosystem_map.py` | 216 | 42 paths across 6 domains mapping the full ecosystem | Adding ecosystem paths |
| `ecosystem_bridge.py` | var | Bridges between ecosystem components | Adding bridge connections |
| `vault_bridge.py` | var | Bridge to PSMV and other vaults | Modifying vault access |
| `bridge.py` | 583 | Generic bridge infrastructure | Adding bridge types |
| `bridge_coordinator.py` | 449 | Coordinates multiple bridges | Modifying bridge orchestration |
| `bridge_registry.py` | var | Registry of available bridges | Registering new bridges |

### Layer 9: Ginko (Trading Subsystem)

| File | Lines | What It Does |
|------|-------|-------------|
| `ginko_agents.py` | 1,134 | Trading agent definitions |
| `ginko_orchestrator.py` | 831 | Trading strategy orchestration |
| `ginko_audit.py` | 1,202 | Trading audit and compliance |
| `ginko_backtest.py` | 985 | Backtesting engine |
| `ginko_report_gen.py` | 1,018 | Report generation |
| `ginko_sec.py` | 1,001 | SEC compliance checks |
| `ginko_risk.py` | 820 | Risk management |
| `ginko_evolution.py` | 794 | Strategy evolution |
| `ginko_signals.py` | 761 | Signal generation |
| `ginko_brier.py` | 746 | Brier score calibration |
| `ginko_paper_trade.py` | 595 | Paper trading simulation |
| `ginko_attribution.py` | 523 | Performance attribution |
| `ginko_live_test.py` | 515 | Live testing harness |
| `ginko_data.py` | 455 | Data ingestion |
| `ginko_sentiment.py` | 473 | Sentiment analysis |
| `ginko_regime.py` | 336 | Market regime detection |
| **Total** | **12,189** | 16 modules |

### Layer 10: CLI & Interface

| File | Lines | What It Does | When to Touch |
|------|-------|-------------|---------------|
| `dgc_cli.py` | 6,308 | **Primary CLI.** Entry point for `dgc` command. All subcommands: status, health, stigmergy, hum, evolve, orchestrate, up/down, etc. | Adding CLI subcommands |
| `cli.py` | 610 | Typer-based CLI (secondary, `dharma-swarm` entry point) | Adding Typer commands |
| `tui/app.py` | 2,518 | Textual TUI application (launched by `dgc` with no args) | Modifying TUI layout |
| `tui/screens/` | dir | TUI screen definitions | Adding TUI screens |
| `tui/widgets/` | dir | TUI widget components | Adding TUI widgets |
| `tui/commands/` | dir | TUI slash commands (/evolve, /thread, /self) | Adding TUI commands |
| `tui/engine/` | dir | TUI backend engine | Modifying TUI data flow |
| `api.py` | 365 | FastAPI REST endpoints | Adding API endpoints |
| `mcp_server.py` | 202 | MCP (Model Context Protocol) server | Extending MCP tools |
| `splash.py` | var | Startup splash screen | Cosmetic changes |

### Layer 11: Jikoku (Temporal Instrumentation)

| File | Lines | What It Does |
|------|-------|-------------|
| `jikoku_samaya.py` | 443 | Temporal awareness engine (Jain samaya concept) |
| `jikoku_fitness.py` | 262 | Time-aware fitness scoring |
| `jikoku_instrumentation.py` | 451 | `@jikoku_auto_span` decorator for automatic tracing |

### Layer 12: Mathematical Foundations

| File | Lines | What It Does |
|------|-------|-------------|
| `coalgebra.py` | 536 | Coalgebraic structures for system dynamics |
| `info_geometry.py` | 665 | Information geometry (Fisher metrics, KL divergence) |
| `monad.py` | 575 | Monadic composition for effect management |
| `sheaf.py` | 456 | Sheaf-theoretic consistency checking |
| `math_bridges.py` | var | Bridges between mathematical abstractions and runtime |
| `cohomology_cechcohomology_to_sheaf_coord.py` | var | Cech cohomology to sheaf coordinate transforms |

### Subdirectory Packages

| Package | Contents | Purpose |
|---------|----------|---------|
| `dharma_swarm/assurance/` | 14 files | Automated quality assurance scanners (API, context, lifecycle, storage, routes, test gaps) |
| `dharma_swarm/cascade_domains/` | 6 files | Domain-specific cascade scoring (code, skill, product, research, meta) |
| `dharma_swarm/contracts/` | 12 files | Interface contracts (intelligence stack, runtime adapters, factory, evaluation, telemetry) |
| `dharma_swarm/engine/` | 12+ files | Core engine (chunker, conversation memory, event memory, hybrid retriever, knowledge store, provenance, unified index) |
| `dharma_swarm/gateway/` | 4 files | External gateways (Telegram, base runner) |
| `dharma_swarm/integrations/` | 5 files | Third-party integrations (data flywheel, KaizenOps, NVIDIA RAG, reciprocity commons) |
| `dharma_swarm/skills/` | 9 .skill.md | Embedded skill definitions (archeologist, architect, builder, cartographer, etc.) |
| `dharma_swarm/tui/` | 20+ files | Full Textual TUI (screens, widgets, commands, engine, theme) |

---

## Top-Level Files

| File | Lines | What It Does |
|------|-------|-------------|
| `CLAUDE.md` | 383 | System genome. Read this first. 10 pillars, 8 principles, 7-star telos, 25 axioms. |
| `pyproject.toml` | 56 | Build config. Entry points: `dgc` and `dharma-swarm`. Python >= 3.11. |
| `garden_daemon.py` | 356 | Spawns `claude -p` subprocesses for autonomous skill execution |
| `deep_reading_daemon.py` | var | Autonomous deep reading of ecosystem content |
| `overnight_summary.py` | var | Generates overnight activity summaries |
| `run_mcp_stdio.py` | var | MCP server launcher for stdio transport |
| `hooks/telos_gate.py` | 183 | Git hook version of telos gate checking |

---

## Foundations (foundations/)

| File | Subject | Pillar |
|------|---------|--------|
| `PILLAR_01_LEVIN.md` | Multi-scale cognition, cognitive light cone | Levin |
| `PILLAR_02_KAUFFMAN.md` | Adjacent possible, autocatalytic sets | Kauffman |
| `PILLAR_03_JANTSCH.md` | Self-organizing universe | Jantsch |
| `PILLAR_05_DEACON.md` | Absential causation | Deacon |
| `PILLAR_06_FRISTON.md` | Free energy principle, active inference | Friston |
| `PILLAR_07_HOFSTADTER.md` | Strange loops, self-reference | Hofstadter |
| `PILLAR_08_AUROBINDO.md` | Supramental descent, downward causation | Aurobindo |
| `PILLAR_09_DADA_BHAGWAN.md` | Witness architecture, karma mechanics | Dada Bhagwan |
| `PILLAR_10_VARELA.md` | Autopoiesis, enactive cognition | Varela |
| `PILLAR_11_BEER.md` | Viable System Model (S1-S5) | Beer |
| `FOUNDATIONS_SYNTHESIS.md` | Lattice + 5 unified principles | All |
| `SYNTHESIS_DEACON_FRISTON.md` | Absential causation = precision-weighted prediction error | Deacon + Friston |
| `META_SYNTHESIS.md` | Meta-level synthesis | All |
| `GLOSSARY.md` | Term definitions | All |
| `INDEX.md` | Master index | All |
| `FIVE_FOURTEEN_A.md` | 5.14a moonshot document | Vision |
| `ECONOMIC_VISION.md` | Economic model | Business |
| `EMPIRICAL_CLAIMS_REGISTRY.md` | Registry of testable claims | Research |
| `SACRED_GEOMETRY.md` | Geometric patterns in the architecture | Theory |
| `SAMAYA_PROTOCOL.md` | Jain logical instruments mapped to PyTorch ops | Theory |
| `THINKODYNAMIC_BRIDGE.md` | Bridge between thinkodynamics and code | Architecture |
| `PSMV_CROWN_JEWELS.md` | Key documents from the PSMV vault | Reference |
| `RESIDUAL_STREAM_DIGEST.md` | Distilled residual stream insights | MI |

---

## Specs (spec-forge/)

| Directory | What It Specifies |
|-----------|-------------------|
| `causal-depth-compression/` | Causal compression of agent traces |
| `discerning-autonomy/` | Viveka function for autonomous decision-making |
| `graph-nexus/` | Unified graph architecture |
| `harness-engineering/` | Test harness engineering |
| `hierarchical-prompt-cascade/` | Prompt cascade architecture |
| `moonshot-agentic-ai/` | VIVEKA/SHAKTI/KALYAN three-organ organism vision |
| `prompt-evolution/` | Evolving prompts through fitness scoring |
| `prompt-quality-scorecard/` | Prompt quality evaluation |
| `self-replicating-agents/` | Agent self-replication protocol |
| `telos-threading/` | Telos alignment threading through all operations |
| `thinkodynamic-agent-protocol/` | Thinkodynamic agent communication |
| `transmission-prompt-research/` | TPP research |

---

## Docs (docs/)

Key directories inside `docs/`:

| Path | Contents |
|------|----------|
| `docs/archive/` | Historical documents |
| `docs/clusters/` | Agent cluster configurations |
| `docs/doctor/` | Doctor diagnostic reports |
| `docs/dse/` | DSE (Darwin Semantic Evolution) docs |
| `docs/merge/` | Merge proposals |
| `docs/missions/` | Mission definitions |
| `docs/plans/` | Execution plans |
| `docs/reports/` | Generated reports |
| `docs/research/` | Research documents |
| `docs/superpowers/` | System capability docs |
| `docs/telos-engine/` | Telos engine design docs |

Notable standalone docs:
- `docs/archive/DHARMA_SWARM_1000X_MASTERPLAN_2026-03-16.md`
- `docs/architecture/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md`
- `docs/architecture/PRODUCTION_DEPLOYMENT_GUIDE.md`
- `docs/architecture/DARWIN_ENGINE_QUICK_START_GUIDE.md`

---

## Tests (tests/)

- **351 test files** in `tests/`
- **4,300+ tests** total
- `conftest.py` provides shared fixtures: `state_dir`, `db_path`, `tmp_path_factory_custom`, Docker skip marker, Hypothesis profiles, DGC env var isolation
- Pattern: one test file per module (`test_telos_gates.py` tests `telos_gates.py`)
- Uses `pytest-asyncio` with `asyncio_mode = "auto"` (from pyproject.toml)
- Tests use `tmp_path` for isolated state, `unittest.mock.patch` for dependency isolation

---

## State (~/.dharma/)

| Path | What It Stores |
|------|---------------|
| `~/.dharma/` | Root state directory |
| `~/.dharma/daemon.pid` | Running daemon PID |
| `~/.dharma/witness/` | Gate check witness logs (JSON) |
| `~/.dharma/stigmergy/marks.jsonl` | Stigmergic marks (append-only) |
| `~/.dharma/shared/` | Shared agent notes |
| `~/.dharma/agent_memory/` | Per-agent persistent memory |
| `~/.dharma/evolution/` | Evolution archive (generations, fitness) |
| `~/.dharma/traces/` | Trace entries (history/, archive/, patterns/) |
| `~/.dharma/logs/` | System logs |
| `~/.dharma/locks/` | File locks for multi-agent safety |
| `~/.dharma/meta/` | Gate proposals, metadata |
| `~/.dharma/vault/` | Computational concept index (50K concepts, 30K edges) |
| `~/.dharma/subconscious/` | Dream layer outputs |
| `~/.dharma/seeds/` | Archaeology seeds |
| `~/.dharma/garden/` | Garden daemon cycle reports |
| `~/.dharma/legacy/` | Rescued code from deleted repos |

---

## External Systems

| System | Access | Purpose |
|--------|--------|---------|
| AGNI VPS (157.245.193.15) | `ssh agni` | OpenClaw, 56 skills, 8 agents, Playwright |
| RUSHABDEV VPS (167.172.95.184) | `ssh rushabdev` | Secondary compute |
| Trishula | `~/trishula/` local, both VPSes | Three-agent cross-machine messaging |
| AGNI workspace mirror | `~/agni-workspace/` | Synced every 30s from VPS |
| R_V paper repo | `~/mech-interp-latent-lab-phase1/` | COLM 2026 submission |
| PSMV vault | `~/Persistent-Semantic-Memory-Vault/` | 1,174 files, knowledge base |
| KAILASH Obsidian | `~/Desktop/KAILASH ABODE OF SHIVA/` | 4,156 spiritual/AI notes |
| Jagat Kalyan | `~/jagat_kalyan/` | Welfare-ton matching service MVP |

---

## Architecture Flow

```
models.py (schema contract)
    |
    v
providers.py (9 LLM providers) ---> agent_runner.py (agent lifecycle)
    |                                      |
    v                                      v
orchestrator.py (task routing) <--- swarm.py (facade, 2359 lines)
    |                                      |
    v                                      v
telos_gates.py (governance) <--- dharma_kernel.py (25 axioms)
    |                                      |
    v                                      v
evolution.py (DarwinEngine)         stigmergy.py (coordination)
    |                                      |
    v                                      v
cascade.py (F(S)=S loop)           graph_nexus.py (unified graphs)
    |                                      |
    v                                      v
orchestrate_live.py (8 concurrent loops)
    |
    v
dgc_cli.py (CLI) / tui/app.py (TUI) / api.py (REST)
```

---

## Module Count by Category

| Category | Count | Combined Lines (approx) |
|----------|-------|------------------------|
| Core runtime (swarm, orchestrator, agent, provider) | 12 | ~12,000 |
| Governance (kernel, gates, guardrails, samvara) | 12 | ~5,000 |
| Intelligence (director, context, routers, zeitgeist) | 15 | ~12,000 |
| Evolution (darwin, cascade, selectors, population) | 12 | ~7,000 |
| Memory & knowledge (stigmergy, graphs, semantic) | 18 | ~9,000 |
| Monitoring (monitor, witness, auditor, xray, doctor) | 12 | ~5,000 |
| Living layers (shakti, subconscious, sleep, ouroboros) | 8 | ~2,500 |
| Ginko trading | 16 | ~12,000 |
| CLI & interface (dgc_cli, tui, api, mcp) | 10 | ~12,000 |
| Mathematical foundations | 6 | ~3,000 |
| Bridges & integrations | 12 | ~4,000 |
| Ontology stack | 6 | ~4,000 |
| Jikoku temporal | 3 | ~1,200 |
| Infrastructure (config, daemon, cron, file_lock) | 10 | ~3,000 |
| Remaining (misc, helpers, utilities) | ~120 | ~25,000+ |
| **Total** | **274** | **~118,000+** |
