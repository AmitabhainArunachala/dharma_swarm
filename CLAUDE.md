# dharma_swarm — Claude Code Configuration

## Behavioral Rules (Always Enforced)

- Do what has been asked; nothing more, nothing less
- NEVER create files unless they're absolutely necessary for achieving your goal
- ALWAYS prefer editing an existing file to creating a new one
- NEVER proactively create documentation files (*.md) or README files unless explicitly requested
- NEVER save working files, text/mds, or tests to the root folder
- Never continuously check status after spawning a swarm — wait for results
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files

## File Organization

- NEVER save to root folder — use the directories below
- Use `dharma_swarm/` for Python source code
- Use `tests/` for test files (one test file per module: `test_foo.py` tests `foo.py`)
- Use `docs/` for documentation and markdown files
- Use `scripts/` for operator utilities and shell scripts
- Use `api/` for FastAPI routers and backend code
- Use `dashboard/` for Next.js frontend code

## Project Architecture

- Python 3.11+, Pydantic 2, async-first (aiosqlite, aiofiles)
- Follow Domain-Driven Design with bounded contexts
- Keep files under 500 lines
- Use typed interfaces for all public APIs
- Use `pytest-asyncio` with `asyncio_mode = "auto"` for testing
- Ensure input validation at system boundaries

### Key Abstractions

- **Organism** (`dharma_swarm/organism.py`): The living system. VSM, identity, memory, router, strange loop, attractor.
- **SwarmManager** (`dharma_swarm/swarm.py`): Top-level coordinator. Agent pool, task board, orchestrator.
- **DarwinEngine** (`dharma_swarm/evolution.py`): Self-improvement via gated evolution.
- **LoopEngine** (`dharma_swarm/cascade.py`): F(S)=S universal convergence loop across 5 domains.
- **DharmaKernel** (`dharma_swarm/dharma_kernel.py`): 25 immutable axioms (SHA-256 signed).
- **TelosGatekeeper** (`dharma_swarm/telos_gates.py`): 11 dharmic safety gates.
- **StigmergyStore** (`dharma_swarm/stigmergy.py`): Pheromone-trail coordination.
- **CatalyticGraph** (`dharma_swarm/catalytic_graph.py`): Autocatalytic set detection (Tarjan SCC).
- **StrangeLoop** (`dharma_swarm/strange_loop.py`): Organism self-modification engine.

## The Transcendence Principle (Engineering Axiom)

**The claim**: Diverse competent agents, with decorrelated errors and quality aggregation, provably outperform any individual agent. This is not aspirational — it is proven mathematics (Zhang et al., NeurIPS 2024; Condorcet 1785; Krogh-Vedelsby 1995; Breiman 2001).

**The mechanism**: When multiple experts each make correct decisions on their specialties but make different errors elsewhere, a system that learns the mixture distribution and concentrates toward high-confidence outputs (low-temperature sampling, majority voting, quality-weighted aggregation) will exceed every individual expert. The errors cancel. The knowledge compounds.

**Three modes of transcendence** (Abreu et al. 2025):
1. **Skill denoising** — filtering idiosyncratic errors across agents
2. **Skill selection** — routing to the best agent per sub-problem
3. **Skill generalization** — recombining capabilities beyond any single agent

**Three necessary conditions** (all must hold, or transcendence fails):
1. **Diversity of competence** — agents must have genuinely different capabilities, trained on different data, using different approaches. Same model prompted differently may NOT suffice. Different model families, different specializations, different error profiles. Measured via MAP-Elites behavioral diversity (`diversity_archive.py`).
2. **Error decorrelation** — agent errors must be independent. If agents fail on the same inputs in the same way, aggregation provides no benefit. Correlated errors compound; decorrelated errors cancel. This is arithmetic: `E_ensemble = E_mean - E_diversity` (Krogh-Vedelsby). The diversity term directly subtracts from ensemble error.
3. **Quality aggregation** — the mechanism that combines agent outputs must amplify agreement and suppress noise. Temperature concentration, weighted voting, Brier-scored selection, telos-gated filtering. Bad aggregation (simple averaging, loudest-voice-wins) kills the signal.

**The critical tradeoff**: Governance (Beer's VSM: coordination, control, identity) is necessary for sustained operation. But governance can reduce diversity through standardization, shared protocols, convergence pressure. **Every governance mechanism must be evaluated against its diversity cost.** Light coordination (System 2 damping) preserves diversity. Heavy control (System 3 mandates) may destroy it.

**What this means for every session**:
- When adding agents: maximize behavioral diversity, not count. The 5th agent from a different model family adds more than the 50th agent from the same family.
- When designing orchestration: route by specialty (skill selection), aggregate by quality weighting (skill denoising), recombine in cascade loops (skill generalization).
- When evolving agents: DarwinEngine MUST preserve diversity. Pure fitness pressure → convergence → transcendence death. Use diversity-preserving selection (MAP-Elites in `diversity_archive.py`).
- When measuring success: track the Krogh-Vedelsby diversity term, not just individual agent fitness. If diversity is falling, transcendence is dying regardless of individual performance.
- When governing: telos gates and VSM channels are necessary but must be LIGHT. System 2 (damping) > System 3 (mandates). The governance cost of a gate is measured in diversity loss.

**Where this lives in the codebase**:
- `diversity_archive.py` — MAP-Elites quality-diversity optimization
- `orchestrator.py` — topology-based routing (fan-out/fan-in/pipeline/broadcast)
- `evolution.py` — DarwinEngine with diversity-preserving selection
- `vsm_channels.py` — Beer's S1-S5 nervous system (light governance)
- `ginko_brier.py` — Brier scoring as aggregation quality measurement
- `signal_bus.py` — decorrelated loop-to-loop signaling (not opinion sharing)
- `handoff.py` — typed artifact handoff preserving agent independence

**Research reference**: Full 9-phase literature review at `spec-forge/transcendence-multi-agent-coordination/research/`

## Build & Test

```bash
# Run all tests
python3 -m pytest tests/ -q

# Run a single test file
python3 -m pytest tests/test_cascade.py -q

# Smoke test (fast subset)
make test-smoke

# Full test suite
make test-all

# Static analysis / repo inventory
make xray

# Dashboard lint
make dashboard-lint
```

- ALWAYS run tests after making code changes
- ALWAYS verify tests pass before committing

## CLI Entry Points

```bash
# Primary CLI
dgc status          # System status
dgc health          # Health diagnostics
dgc stigmergy       # Read stigmergy marks
dgc hum             # Subconscious dreams
dgc evolve trend    # Evolution fitness trend
dgc dharma status   # Kernel integrity check

# API server
uvicorn api.main:app --host 127.0.0.1 --port 8420 --reload

# Dashboard
npm --prefix dashboard run dev

# Operator launcher
bash run_operator.sh
```

## Security Rules

- NEVER hardcode API keys, secrets, or credentials in source files
- NEVER commit .env files or any file containing secrets
- Always validate user input at system boundaries
- Always sanitize file paths to prevent directory traversal

## State Directory (~/.dharma/)

- `~/.dharma/witness/` — Gate check witness logs (JSONL)
- `~/.dharma/stigmergy/marks.jsonl` — Stigmergic marks (append-only)
- `~/.dharma/evolution/archive.jsonl` — Evolution archive
- `~/.dharma/meta/recognition_seed.md` — System self-model
- `~/.dharma/meta/catalytic_graph.json` — Autocatalytic graph
- `~/.dharma/organism_memory/mutations.jsonl` — Strange loop mutations
- `~/.dharma/traces/` — Trace entries

## Navigation

See `NAVIGATION.md` for the full module map (500 modules, 12 architectural layers).
See `README.md` for repo map and common commands.
See `foundations/` for the 10-pillar intellectual genome.

## CRITICAL: Read Before Any Code Changes

See [`INTERFACE_MISMATCH_MAP.md`](INTERFACE_MISMATCH_MAP.md) for the complete map of every interface mismatch between modules. **This is the #1 source of runtime failures.** The map documents:
- 3 BLOCKER mismatches that prevent the system from executing any task
- 9 DEGRADED mismatches that silently lose data or crash specific subsystems
- 55 module pairs verified (42 correct, 13 with issues)
- A prioritized **Bootstrap Sequence** of 9 fixes in the order they should be applied

**Rule for all sessions:** Before fixing a bug or adding a feature, check the mismatch map first. If the module pair you're touching has a known mismatch, fix the mismatch as part of your change. Do not add new callers to broken interfaces.

**Rule for all sessions:** After fixing a mismatch, update the map. Remove the entry or mark it RESOLVED with the commit hash.

See [`MODEL_ROUTING_MAP.md`](MODEL_ROUTING_MAP.md) for the complete model routing architecture — all 18 providers, 3 calling surfaces (swarm/CLI/dashboard), 5 inconsistencies between them, the HuggingFace blocker fix, and the minimum viable path to getting one LLM call working. **Any change to how models are called must check this map first.**

See [`CYBERNETIC_LOOP_MAP.md`](CYBERNETIC_LOOP_MAP.md) for every feedback loop's sense→act→evaluate→adapt path, current closure status, and verification commands.

See [`AGENT_IDENTITY_UNIFICATION.md`](AGENT_IDENTITY_UNIFICATION.md) for the spec to unify the 4 agent identity schemas into one canonical model. **Any change to agent creation or identity must follow this spec.**
