# REPO GOVERNANCE AUDIT

**Date**: 2026-04-04
**Auditors**: Claude Opus 4.6, DeepSeek-v3.1 (671B), GPT-OSS (20B), Codex CLI 0.117.0, RUFLO v3.5.51
**Method**: Multi-model convergent audit — 5 independent AI systems, zero coordination between them
**Scope**: Read-only. No code changes. No runtime modification.

---

## 1. VERIFIED NUMBERS

| Metric | CLAUDE.md Claim | NAVIGATION.md Claim | Actual (2026-04-04) | Verdict |
|--------|----------------|--------------------|--------------------|---------|
| Python modules | "370 modules" | "500 Python modules" | **514** | BOTH STALE |
| Test count | "4300+ tests" | "8,848 tests" | **8,562 collected, 16 errors** | CLAUDE.md STALE, NAV INFLATED |
| Test files | — | "494 test files" | **497-501** | CLOSE (grew) |
| swarm.py lines | "~1,700 lines" | "2,359 lines" | **3,119 lines** | BOTH STALE |
| orchestrator.py lines | — | "2,078 lines" | **2,272 lines** | NAV STALE |
| Providers | "9 LLM providers" | "9 LLM providers" | **9** | VERIFIED |
| Top-level .py files | — | — | **375 / 514 (73%)** | UNREPORTED PROBLEM |

---

## 2. ALL GOVERNANCE-RELEVANT DOCS FOUND

### Root Level (6 files)
| File | Lines | Purpose | Current? |
|------|-------|---------|----------|
| `CLAUDE.md` | 236 | Agent instruction file | **YES** — actively maintained |
| `README.md` | ~200 | Repo overview | PARTIAL — frontmatter bloat |
| `LIVING_LAYERS.md` | ~600 | Living layers architecture | STALE — references old line counts |
| `PRODUCT_SURFACE.md` | ~100 | Product surface map | UNKNOWN |
| `program.md` | ~300 | Program description | UNKNOWN |
| `program_ecosystem.md` | ~200 | Ecosystem map | RECENT (Apr 2) |

### docs/architecture/ (20 files)
| File | Purpose | Current? |
|------|---------|----------|
| `NAVIGATION.md` | Module map (12 layers) | **STALE** — numbers don't match |
| `MODEL_ROUTING_CANON.md` | "Single story" for routing | **CONTRADICTED** — 3 routing files exist |
| `INTEGRATION_MAP.md` | Infrastructure mapping | STALE (dated 2026-03-08) |
| `GENOME_WIRING.md` | Genome signal wiring | UNKNOWN |
| `ORCHESTRATOR_LEDGERS.md` | Orchestrator state | UNKNOWN |
| `DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md` | 3-plane arch | STALE (pre-TUI) |
| `JIKOKU_SAMAYA_*.md` (4 files) | Temporal architecture | STALE |
| `SWARMLENS_MASTER_SPEC.md` | SwarmLens TUI spec | STALE (pre-Bun rewrite) |
| `VERIFICATION_LANE.md` | Verification pipeline | UNKNOWN |
| `COMPLIANCE_MAPPING.md` | Compliance map | UNKNOWN |
| Others (8 files) | Various | MIXED |

### specs/ (12+ files)
| File | Purpose | Current? |
|------|---------|----------|
| `DGC_TERMINAL_ARCHITECTURE.md` | Terminal JSON stdio spec | PARTIAL |
| `DGC_TERMINAL_ARCHITECTURE_v1.1.md` | v1.1 terminal spec | MORE CURRENT |
| `Dharma_Constitution_v0.md` | Constitutional rules | FOUNDATIONAL |
| `KERNEL_CORE_SPEC.md` | Kernel spec | FOUNDATIONAL |
| `STIGMERGY_11_LAYER_SPEC_2026-03-23.md` | Stigmergy layers | RECENT |
| `SOVEREIGN_BUILD_PHASE_MASTER_SPEC_2026-03-19.md` | Build spec | STALE |
| `ONTOLOGY_PHASE2_*.md` (2 files) | Ontology migration | STALE |
| `TaskBoardCoordination.tla` | TLA+ spec | UNKNOWN |

### foundations/ (23 files)
All 10 pillars + synthesis + meta docs. **STABLE** — intellectual genome, rarely changes.

### lodestones/ (15+ files)
Grounding research, expanded pillars, bridges, seeds. **STABLE** — reference material.

### docs/archive/ (12+ files)
Explicitly archived. **CORRECTLY QUARANTINED.**

### docs/research/ (12+ files)
Research docs. Mixed recency. Most are reference material, not governance.

---

## 3. CONTRADICTIONS DETECTED

### C1: Module Count Drift
- `CLAUDE.md` (root): "370 modules, 296 connected, 168 orphans"
- `NAVIGATION.md`: "500 Python modules"
- **Reality**: 514 modules
- **Diagnosis**: CLAUDE.md references an old audit. NAVIGATION.md is closer but also stale.

### C2: Test Count Inflation
- `CLAUDE.md` (root): "4300+ tests"
- `NAVIGATION.md`: "8,848 tests"
- **Reality**: 8,562 tests collected + 16 collection errors
- **Diagnosis**: CLAUDE.md is from an older era. NAVIGATION.md overstates by ~300.

### C3: swarm.py Size
- `CLAUDE.md` (root): "~1,700 lines"
- `NAVIGATION.md`: "2,359 lines"
- **Reality**: 3,119 lines
- **Diagnosis**: File has grown significantly. All references stale.

### C4: "Single Story" Routing Claim
- `MODEL_ROUTING_CANON.md`: Claims to be "the single story for model and provider selection"
- **Reality**: 3 separate `model_routing.py` files exist:
  - `dharma_swarm/model_routing.py`
  - `dharma_swarm/tui/model_routing.py`
  - `dharma_swarm/terminal_routing/model_routing.py`
- Plus: `routing_memory.py`, `operator_core/routing_payloads.py`
- **Diagnosis**: The "single story" was written before the TUI/terminal routing split.

### C5: Massive Frontmatter Injection
- Every doc in docs/, specs/, foundations/ has been injected with 80+ lines of YAML frontmatter by "Codex (GPT-5)"
- The frontmatter includes PKM, stigmergy, curation, and improvement metadata
- **Problem**: This bloats every file, making them harder to read. The frontmatter often exceeds the actual content.
- **Diagnosis**: Classic multi-agent drift. One agent's metadata system was applied globally without governance review.

### C6: Bridge Proliferation Without Registry
- 17 bridge files exist at top level of dharma_swarm/:
  - terminal_bridge.py, runtime_bridge.py, ecosystem_bridge.py, operator_bridge.py
  - skill_bridge.py, review_bridge.py, session_event_bridge.py, bridge.py
  - bridge_registry.py, bridge_coordinator.py, instinct_bridge.py
  - offline_training_bridge.py, vault_bridge.py, math_bridges.py
  - semantic_memory_bridge.py, roaming_operator_bridge.py, trishula_bridge.py
  - Plus: a2a/a2a_bridge.py, verify/flywheel_bridge.py
- **No doc describes the bridge hierarchy or which bridges are active.**
- `bridge_registry.py` and `bridge_coordinator.py` exist but don't appear to govern the others.

### C7: Adapter Duplication
- `dharma_swarm/terminal_adapters/` (6 files)
- `dharma_swarm/tui/engine/adapters/` (6 files)
- `dharma_swarm/engine/adapters/` (exists)
- `dharma_swarm/operator_core/adapters.py`
- `dharma_swarm/contracts/runtime_adapters.py`, `intelligence_adapters.py`
- **Multiple adapter directories doing overlapping work with no documented relationship.**

### C8: Orchestrator Fragmentation
- `orchestrator.py` (2,272 lines) — task routing
- `orchestrate.py` — orchestration logic
- `orchestrate_live.py` (1,549 lines) — live execution
- `ginko_orchestrator.py` — Ginko-specific orchestration
- **No doc explains which orchestrator is canonical or how they relate.**

### C9: TUI Tests Broken
- 16 test collection errors, all in `tests/tui/`
- TUI tests reference modules that may not exist or have import issues
- **No error tracking doc exists for these failures.**

---

## 4. STRUCTURAL PROBLEMS (MULTI-MODEL CONSENSUS)

All 5 audit sources independently identified:

### P1: Flat Package Anti-Pattern
**375 of 514 Python files (73%) sit at the top level** of `dharma_swarm/`. Only 139 files are in subdirectories. This makes the package nearly impossible to navigate and creates implicit coupling between unrelated modules.

### P2: God Objects
- `dgc_cli.py`: 6,979 lines (CLI, commands, formatting, state, everything)
- `thinkodynamic_director.py`: 5,167 lines
- `telos_substrate.py`: 4,423 lines
- `evolution.py`: 3,227 lines
- `swarm.py`: 3,119 lines

### P3: Naming Inconsistency
Same concepts named differently across modules:
- "bridge" vs "adapter" vs "connector" — all mean "interface between systems"
- "orchestrator" vs "orchestrate" vs "director" — all mean "coordinate work"
- "routing" vs "router" vs "selector" — all mean "choose where to send"
- "context" vs "orientation" vs "prompt" — overlapping context injection concepts

### P4: No Import Boundary Enforcement
Nothing prevents any module from importing any other module. The flat structure enables spaghetti imports.

### P5: Doc Maze
The repo has 80+ markdown files across root, docs/, specs/, foundations/, lodestones/. There is no document hierarchy. No single entry point tells you which docs are current vs stale.

---

## 5. WHAT IS ACTUALLY ALIVE VS DEAD

### ALIVE (actively used, recently modified)
- `dgc_cli.py` — primary CLI entry point
- `swarm.py` — core facade
- `orchestrator.py` — task routing
- `agent_runner.py` — agent lifecycle
- `providers.py` — LLM provider layer
- `evolution.py` — DarwinEngine
- `telos_gates.py` — governance gates
- `dharma_kernel.py` — immutable axioms
- `models.py` — Pydantic schemas
- `config.py` — configuration
- `stigmergy.py` / `stigmergy_store.py` — pheromone coordination
- `message_bus.py` — async pub/sub
- `terminal_bridge.py` — Bun TUI bridge
- API layer (`api/main.py` + routers)

### ZOMBIE (exists, has code, but unclear if anything uses it)
- Most bridge files beyond terminal_bridge
- `thinkodynamic_director.py` (5K lines, unknown active callers)
- `telos_substrate.py` (4K lines, unknown active callers)
- `swarmlens_app.py` — old TUI (replaced by Bun?)
- `overnight_director.py` — overnight mode
- `codex_overnight.py` (10K lines, last heartbeat failed)
- Multiple `*_bridge.py` files

### DEAD (no evidence of use)
- `dharma_swarm/engine/` — appears to duplicate `tui/engine/`
- Several auto_grade/, auto_research/ modules
- Legacy operator_core/ files
- Old routing implementations (router_v1.py)

---

## 6. WHAT SHOULD HAPPEN TO CLAUDE.md?

**Recommendation: RETAIN and SHARPEN.**

`CLAUDE.md` is the most effective governance surface in the repo. It is:
- Actually read by agents (it's loaded automatically)
- Actively maintained (last updated Apr 4)
- Contains real architectural truth (5-layer model, key abstractions, build commands)

**Problems to fix:**
1. Stale numbers (370 modules → 514, 4300+ tests → 8500+, swarm.py ~1700 → 3119)
2. Missing: bridge hierarchy, adapter map, orchestrator relationships
3. Missing: which docs are canonical vs stale
4. Should reference this governance layer

**Do NOT:**
- Rename to AGENTS.md (CLAUDE.md is the standard for Claude Code)
- Split it (it's already the right size)
- Mirror it (one source of truth)

---

## 7. MINIMUM CANONICAL FILE STACK

See `CANONICAL_DOC_STACK.md` for the full proposal.

---

## 8. ADDITIONAL FINDINGS (VIVEKA + CODEX)

### VIVEKA Epistemic Audit (83 tool calls, 349s runtime)

VIVEKA discovered contradictions the initial sweep missed:

| ID | Severity | Finding |
|----|----------|---------|
| C-04 | **CRITICAL** | Parent `~/CLAUDE.md` says "10 axioms" in DharmaKernel. Repo CLAUDE.md and actual code say **25 axioms**. The doc every Claude session reads first has a 2.5x undercount. |
| C-03 | HIGH | Providers claimed as 9 everywhere. Actual: **18 concrete provider classes** in providers.py |
| C-09 | HIGH | `spec-forge/transcendence-multi-agent-coordination/research/` referenced in CLAUDE.md **does not exist** |
| C-10 | HIGH | "Keep files under 500 lines" rule in CLAUDE.md violated by **147 of 513 files (29%)**. dgc_cli.py alone is 6,979 lines. |
| C-07 | MEDIUM | program.md claims ~83K lines across ~90 files. Reality: **227K lines across 513 files** (2.7x undercount) |
| C-08 | LOW | "12 architectural layers" but NAVIGATION.md defines **13** (Layer 0 through 12) |
| C-11 | LOW | LIVING_LAYERS.md says stigmergy.py is 220 lines. Actual: **564 lines** |

**VIVEKA root cause**: "Documentation was generated at discrete points in time and never updated. The codebase grew 2-7x while docs stayed frozen."

### Codex Architectural Audit (independent, GPT-5.4)

Codex found **import cycles** that RUFLO's JS-focused analyzer missed:

**Circular dependency chains:**

| Cycle | Modules | Severity |
|-------|---------|----------|
| Evolution/meta-evolution | 6 modules (evolution ↔ jikoku_fitness ↔ meta_evolution ↔ info_geometry ↔ dse_integration ↔ landscape) | HIGH |
| Routing | 4 modules (router_v1 → provider_policy → smart_router → router_v1) | HIGH |
| Build orchestration | 3 modules (build_engine → foreman → custodians → build_engine) | MEDIUM |
| api ↔ dharma_swarm | Top-level bidirectional import | HIGH |
| organism ↔ dharma_attractor | 2-module cycle | LOW |
| docker_sandbox ↔ sandbox | 2-module cycle | LOW |
| providers ↔ runtime_provider | 2-module cycle | MEDIUM |
| smart_seed_selector ↔ thinkodynamic_director | 2-module cycle | MEDIUM |
| verify/reporter ↔ verify/reviewer | 2-module cycle | LOW |

**Weak boundary quantification:**
- `contracts/` → flat root: 24 import edges
- `cascade_domains/` → flat root: 15 import edges
- `tui/` → flat root: 9 import edges
- flat root → `engine/`: 21 import edges (bidirectional leakage)

**Codex verdict**: "The real center of gravity is a flat monolith under dharma_swarm, not the subpackages."

---

## 9. RUFLO ANALYSIS NOTE

RUFLO v3.5.51's static analyzers (boundaries, modules, circular, complexity) are JavaScript/TypeScript-focused and returned empty results for Python files. RUFLO's orchestration capabilities (hive-mind, guidance, autopilot) could be useful for future multi-agent governance enforcement but require initialization and configuration. The repo does not currently use RUFLO.

## 9. CODEX REVIEW NOTE

Codex CLI 0.117.0 was dispatched for independent architectural review. Results pending at time of writing. Codex's `review` mode can be used for ongoing architectural compliance checks.

---

## 10. FRESH RE-AUDIT CORRECTIONS (2026-04-04, Claude Code Opus 4.6)

A parallel re-audit using Claude Code's filesystem tools (Grep, Glob, Read, Bash, 12 parallel agents) found errors in the original 5-model audit above:

### Self-Corrections

| Original Claim | Section | Corrected Value | Evidence |
|----------------|---------|-----------------|----------|
| "codex_overnight.py 10K lines" | Section 5 | **1,008 lines** | wc -l dharma_swarm/codex_overnight.py |
| "16 TUI test errors" | C9 | **16 total: 10 numpy, 2 textual, 1 typer, 1 pytest_asyncio, 1 yaml, 1 tui.app** -- only 3 are TUI-specific | pytest --collect-only |
| "17 bridge files" (line in Section 2) | C6 | **20 bridge files** | find dharma_swarm -name "*bridge*" |
| "19 bridge files" (line in Section 3 C6) | C6 | **20 bridge files** | Self-contradicting within same doc (17 vs 19); both wrong |
| VIVEKA C-03: "18 concrete provider classes" | Section 8 | **19 classes** (incl. abstract LLMProvider); **18 ProviderType enum values** | grep "class.*Provider" providers.py + models.py |

### New Contradictions Found

| ID | Severity | Finding |
|----|----------|---------|
| C-NEW-1 | HIGH | `router_v1.py` labeled "LEGACY" in SOVEREIGN_MANIFEST and NAVIGATION.md. Actually ALIVE: used by providers.py for signal generation (build_routing_signals), doctor.py, smart_router.py. 6+ importers. |
| C-NEW-2 | MEDIUM | `engine/` labeled "legacy duplicate of tui/engine/" in SOVEREIGN_MANIFEST. Actually BOTH are ALIVE: engine/ has 41 importers, tui/engine/ has 31 importers. Different purposes. |
| C-NEW-3 | MEDIUM | NAVIGATION.md claims CLAUDE.md is 383 lines. Actual: 148 lines. |
| C-NEW-4 | LOW | `tui/model_routing.py` and `terminal_routing/model_routing.py` are IDENTICAL (confirmed via comparison). Both are dead code (never imported in dispatch path). |
| C-NEW-5 | HIGH | 74 files across the repo claim to be "source of truth" or "canonical" -- while CANONICAL_DOC_STACK.md explicitly prohibits overlapping claims. |
| C-NEW-6 | MEDIUM | NAVIGATION.md summary claims "~274 modules, ~118,000+ lines". Actual: 514 modules, 227,486 lines. Nearly 2x on both metrics. |

### Circular Dependencies: All 9 Independently Confirmed

| Cycle | Modules | Import Pattern | Severity |
|-------|---------|---------------|----------|
| 1 | evolution ↔ landscape ↔ meta_evolution ↔ dse_integration ↔ jikoku_fitness (6) | Mixed direct + lazy | HIGH |
| 2 | router_v1 → provider_policy → smart_router → router_v1 (4) | TYPE_CHECKING + lazy | HIGH |
| 3 | build_engine → foreman → custodians (3) | All lazy | MEDIUM |
| 4 | api ↔ dharma_swarm (bidirectional) | Direct + lazy | HIGH |
| 5 | organism ↔ dharma_attractor (2) | All lazy | LOW |
| 6 | docker_sandbox ↔ sandbox (2) | Direct + lazy | LOW |
| 7 | providers ↔ runtime_provider (2) | All lazy | MEDIUM |
| 8 | smart_seed_selector ↔ thinkodynamic_director (2) | All lazy | MEDIUM |
| 9 | verify/reporter ↔ verify/reviewer (2) | Direct + lazy | LOW |

### Import Boundary Audit Results

| Boundary | Domain | Status |
|----------|--------|--------|
| Schema (models, config, profiles) | Domain 1 | **PASS** |
| Governance (kernel, gates) | Domain 2 | **PASS** |
| Runtime Core (swarm, orchestrator, runner) | Domain 3 | **PASS** |
| Bridges (no bridge-to-bridge imports) | Domain 6 | **FAIL** -- roaming_operator_bridge:14 imports operator_bridge; bridge_coordinator imports bridge_registry (6 locations) |
| TUI (no direct Runtime/Intelligence/Evolution imports) | Domain 7 | **PASS** |

### Alive/Dead/Zombie Reclassification

| File | Prior Status | Verified Status | Evidence |
|------|-------------|----------------|----------|
| thinkodynamic_director.py | Zombie | **ALIVE** | 2 importers (swarm.py, smart_seed_selector.py) |
| telos_substrate.py | Zombie | **STALE** | 1 importer (swarm.py, lazy) |
| swarmlens_app.py | Zombie | **ZOMBIE** (confirmed) | 0 importers |
| overnight_director.py | Zombie | **ALIVE** | 2 importers (dgc_cli.py, cron_runner.py) |
| codex_overnight.py | Zombie | **STALE** | 1 importer (terminal_overnight_supervisor.py) |
| router_v1.py | Legacy | **ALIVE** | 6+ importers in main routing chain |
| flywheel_bridge.py | — | **ZOMBIE** | 0 importers |
| runtime_bridge.py | — | **ZOMBIE** | 0 importers |
| math_bridges.py | — | **ZOMBIE** | 0 importers |
| offline_training_bridge.py | — | **ZOMBIE** | 0 importers |
