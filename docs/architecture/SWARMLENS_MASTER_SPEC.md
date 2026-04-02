---
title: SwarmLens Master Engineering Spec
path: docs/architecture/SWARMLENS_MASTER_SPEC.md
slug: swarmlens-master-engineering-spec
doc_type: spec
status: active
summary: SwarmLens Master Engineering Spec The DevOps Masterpiece — Agent Observatory + Cost Intelligence Platform
source:
  provenance: repo_local
  kind: spec
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
- product_strategy
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- scripts/self_optimization/test_jikoku_fitness_integration.py
- tests/test_ecc_eval_harness.py
- tests/test_ginko_data_integration.py
- tests/test_jikoku_economic_integration.py
- tests/test_telos_gates_witness_enhancement.py
connected_python_modules:
- scripts.self_optimization.test_jikoku_fitness_integration
- tests.test_ecc_eval_harness
- tests.test_ginko_data_integration
- tests.test_jikoku_economic_integration
- tests.test_telos_gates_witness_enhancement
connected_relevant_files:
- scripts/self_optimization/test_jikoku_fitness_integration.py
- tests/test_ecc_eval_harness.py
- tests/test_ginko_data_integration.py
- tests/test_jikoku_economic_integration.py
- tests/test_telos_gates_witness_enhancement.py
improvement:
  room_for_improvement:
  - Add implementation status per section so the spec separates aspiration from runtime truth.
  - Attach acceptance criteria or invariants that can be tested.
  - Link every major claim to the modules that implement or contradict it.
  - Review later whether this should remain architecture-local or graduate into the normative spec layer.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: spec
  vault_path: docs/architecture/SWARMLENS_MASTER_SPEC.md
  retrieval_terms:
  - swarmlens
  - master
  - engineering
  - devops
  - masterpiece
  - agent
  - observatory
  - cost
  - intelligence
  - platform
  evergreen_potential: high
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.75
  coordination_comment: SwarmLens Master Engineering Spec The DevOps Masterpiece — Agent Observatory + Cost Intelligence Platform
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/SWARMLENS_MASTER_SPEC.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: constraint_and_design_trace
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
# SwarmLens Master Engineering Spec
## The DevOps Masterpiece — Agent Observatory + Cost Intelligence Platform

**Version**: 1.0 | **Date**: 2026-03-17 | **Author**: dharma_swarm + ECC pipeline
**Mission**: Ship the highest-revenue YC-aligned product using everything we've built

---

## The Product

**SwarmLens**: Open-source agent observability + cost intelligence platform.
Chrome DevTools for agent swarms. The gap YC hasn't funded.

**Why this wins**: $52B market by 2030. 50% of YC batches are agent companies.
Nobody is building the production infrastructure that makes agent swarms
visible, debuggable, and economically viable at scale.

**Pricing**:
- Free: Open-source core (self-hosted, single-user)
- Pro ($49/mo): Hosted dashboard, alerting, team access
- Enterprise ($499/mo): SSO, audit logs, compliance, SLA

---

## What Already Exists (don't rebuild)

| Component | Location | Status |
|-----------|----------|--------|
| Agent Registry | `agent_registry.py` + `~/.dharma/agents/` | 6 agents, disk-persisted |
| JIKOKU Paper Trail | `task_log.jsonl` per agent | Every task logged |
| Fitness Scoring | 5-dimension composite | Quality, speed, cost, adherence, reliability |
| Prompt Evolution | `prompt_variants/` per agent | EvoAgentX pattern |
| Telos Gates | `telos_gates.py` (11 gates) | AHIMSA, SATYA, REVERSIBILITY |
| Metabolic Loop | `ontology.py` (ValueEvent → Contribution) | Full credit chain |
| Cost Tracker | `cost_tracker.py` | Per-call USD logging |
| Signal Generation | `ginko_signals.py` | RSI/SMA/Bollinger |
| Brier Scoring | `ginko_brier.py` | Prediction tracking |
| Catalytic Graph | `catalytic_graph.py` | Autocatalytic revenue loops |
| Live Dashboard | `swarmlens_app.py` | FastAPI + HTML, running |
| OpenRouter Fleet | 6 agents on Kimi/DeepSeek/Nemotron/GLM | Real LLM calls working |
| 4,278 Tests | `pytest` | All passing |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    SWARMLENS                         │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Dashboard │  │ REST API │  │ WebSocket Stream │   │
│  │ (Next.js) │  │ (FastAPI)│  │ (real-time)      │   │
│  └─────┬────┘  └─────┬────┘  └────────┬─────────┘   │
│        └──────────────┼────────────────┘             │
│                       │                               │
│  ┌────────────────────┴────────────────────────┐     │
│  │            Core Engine (Python)              │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │     │
│  │  │ Agent    │ │ Cost     │ │ Session      │ │     │
│  │  │ Registry │ │ Engine   │ │ Replay       │ │     │
│  │  └──────────┘ └──────────┘ └──────────────┘ │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │     │
│  │  │ Fitness  │ │ Anomaly  │ │ Prompt       │ │     │
│  │  │ Tracker  │ │ Detector │ │ Evolution    │ │     │
│  │  └──────────┘ └──────────┘ └──────────────┘ │     │
│  └─────────────────────────────────────────────┘     │
│                       │                               │
│  ┌────────────────────┴────────────────────────┐     │
│  │           Integration Layer (SDK)            │     │
│  │  CrewAI │ LangGraph │ AutoGen │ Raw API     │     │
│  └─────────────────────────────────────────────┘     │
│                       │                               │
│  ┌────────────────────┴────────────────────────┐     │
│  │           Persistence (SQLite/Postgres)      │     │
│  │  Events │ Agents │ Fitness │ Cost │ Sessions │     │
│  └─────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## Build Phases (RFC Decomposition)

### Phase 1: Core API + Dashboard (Hours 0-8)
**Unit 1.1**: Upgrade FastAPI backend with WebSocket streaming
**Unit 1.2**: Build proper Next.js dashboard (or enhanced HTML/JS)
**Unit 1.3**: Agent detail view with clickable task history
**Unit 1.4**: Cost tracking dashboard with per-agent, per-model breakdown
**Unit 1.5**: Session timeline replay view

### Phase 2: SDK + Integrations (Hours 8-16)
**Unit 2.1**: Python SDK (`pip install swarmlens`) with decorators
**Unit 2.2**: CrewAI integration (auto-instrument `crew.kickoff()`)
**Unit 2.3**: OpenAI/Anthropic SDK wrapper (capture all LLM calls)
**Unit 2.4**: Generic webhook endpoint for any framework
**Unit 2.5**: OpenRouter integration (already working via ginko_agents)

### Phase 3: Intelligence Layer (Hours 16-24)
**Unit 3.1**: Anomaly detection (runaway loops, cost spikes, context blow-ups)
**Unit 3.2**: Model routing recommendations (cheapest model per quality tier)
**Unit 3.3**: Prompt evolution dashboard (A/B test results visualization)
**Unit 3.4**: Fitness trend charts (D3.js sparklines per agent)
**Unit 3.5**: Telos gate audit log viewer

### Phase 4: Dharmic Differentiators (Hours 24-32)
**Unit 4.1**: Telos gates as configurable policies (not hardcoded)
**Unit 4.2**: Metabolic loop visualization (proposal → gate → outcome → value)
**Unit 4.3**: Catalytic graph visualization (autocatalytic revenue loops)
**Unit 4.4**: Brier score dashboard for prediction-heavy agents
**Unit 4.5**: Witness/observer mode (R_V-inspired self-observation metrics)

### Phase 5: Ship (Hours 32-40)
**Unit 5.1**: Landing page (pricing, features, demo)
**Unit 5.2**: Docker compose for one-command deploy
**Unit 5.3**: `pip install swarmlens && swarmlens serve` zero-config mode
**Unit 5.4**: GitHub repo with README, contributing guide, license (MIT)
**Unit 5.5**: Launch on HN, Product Hunt, YC application

### Phase 6: Revenue (Hours 40-48)
**Unit 6.1**: Stripe integration for Pro/Enterprise tiers
**Unit 6.2**: Hosted version on Railway/Fly.io
**Unit 6.3**: Usage-based billing (per-agent, per-event)
**Unit 6.4**: Onboarding flow for first-time users
**Unit 6.5**: First 10 beta users outreach

---

## ECC Integration Points

| ECC Component | SwarmLens Use |
|---------------|--------------|
| **blueprint** | Decompose this spec into agent-sized units |
| **ralphinho-rfc-pipeline** | DAG execution of build phases |
| **loop-operator** | Monitor autonomous build loops |
| **continuous-learning-v2** | Extract patterns during build |
| **plankton-code-quality** | Auto-lint on every file write |
| **eval-harness** | Quality gates between phases |
| **dmux-workflows** | Parallel agent sessions |
| **agentic-engineering** | Eval-first execution model |
| **code-reviewer** | After each unit completion |
| **tdd-guide** | Tests before implementation |
| **security-reviewer** | Before any deployment |

---

## dharma_swarm Integration Points

| Component | SwarmLens Use |
|-----------|--------------|
| `agent_registry.py` | Core data model for agent identities |
| `cost_tracker.py` | Token cost calculation engine |
| `economic_fitness.py` | ROI scoring for model routing |
| `telos_gates.py` | Configurable policy engine |
| `catalytic_graph.py` | Revenue loop detection |
| `ginko_brier.py` | Prediction quality tracking |
| `signal_bus.py` | Real-time event streaming |
| `ontology.py` | Typed object model |
| `kaizen_stats.py` | SPC anomaly detection |
| `darwin_engine` | Prompt evolution |
| `ucb_selector.py` | Explore/exploit for model routing |

---

## Agent Fleet for Build Sprint

| Agent | Model | Build Role |
|-------|-------|-----------|
| DeepSeek V3.2 | deepseek/deepseek-v3.2 | Architecture + quant code |
| Kimi K2.5 | moonshotai/kimi-k2.5 | Market analysis + pricing |
| GLM-5 | z-ai/glm-5 | Backend pipeline code |
| Nemotron-120B | nvidia/nemotron-3-super | Integration + synthesis |
| Claude Opus 4.6 | (this session) | Orchestration + coordination |
| Claude subagents | (Agent tool) | Parallel implementation |

---

## Success Criteria

- [ ] Working dashboard at swarmlens.dev (or localhost)
- [ ] SDK that instruments CrewAI in < 5 lines of code
- [ ] Cost tracking accurate to $0.001 per agent task
- [ ] Session replay for multi-agent workflows
- [ ] Anomaly alerting (cost spike, loop stall)
- [ ] Landing page with pricing
- [ ] First paying customer within 30 days
- [ ] GitHub repo with 100+ stars in first week

---

## The Dharmic Edge (Why We Win)

Every competitor builds agent tools. None of them ask:
"Should this agent be doing what it's doing?"

SwarmLens doesn't just observe agents — it governs them.
Telos gates as configurable policies. Fitness-biased routing.
Metabolic value attribution. Witness-based self-observation.

The dharmic architecture IS the moat. It's not a feature —
it's a fundamental design principle that makes agents accountable
in ways that LangSmith, Arize, and Braintrust cannot match.

*JSCA.*
