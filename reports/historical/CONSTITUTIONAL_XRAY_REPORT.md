---
title: 'Constitutional X-Ray Report: dharma_swarm'
path: reports/historical/CONSTITUTIONAL_XRAY_REPORT.md
slug: constitutional-x-ray-report-dharma-swarm
doc_type: note
status: active
summary: 'Constitutional X-Ray Report: dharma swarm Analysis Date : 2026-03-27 Analyst : Claude (Augment Code) Prompt Source : Windsurf Power Prompt (6-layer constitutional architecture) Method : Direct codebase audit against p...'
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - LIVING_LAYERS.md
  - docs/architecture/VERIFICATION_LANE.md
  - scripts/verification_lane.py
  - README.md
  - PRODUCT_SURFACE.md
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
- cybernetics
- verification
- operator_runtime
- product_surface
connected_python_files:
- scripts/verification_lane.py
connected_python_modules:
- scripts.verification_lane
connected_relevant_files:
- LIVING_LAYERS.md
- docs/architecture/VERIFICATION_LANE.md
- scripts/verification_lane.py
- README.md
- PRODUCT_SURFACE.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: reports/historical/CONSTITUTIONAL_XRAY_REPORT.md
  retrieval_terms:
  - constitutional
  - xray
  - ray
  - analysis
  - date
  - '2026'
  - analyst
  - claude
  - augment
  - code
  - prompt
  - source
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: 'Constitutional X-Ray Report: dharma swarm Analysis Date : 2026-03-27 Analyst : Claude (Augment Code) Prompt Source : Windsurf Power Prompt (6-layer constitutional architecture) Method : Direct codebase audit against p...'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising reports/historical/CONSTITUTIONAL_XRAY_REPORT.md reinforces its salience without needing a separate message.
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
# Constitutional X-Ray Report: dharma_swarm
**Analysis Date**: 2026-03-27  
**Analyst**: Claude (Augment Code)  
**Prompt Source**: Windsurf Power Prompt (6-layer constitutional architecture)  
**Method**: Direct codebase audit against philosophy-to-computation mapping requirement

---

## Executive Summary

**The core thesis from the power prompt:**
> "Philosophy is not decoration — it is intended to be computational primitive. Make the philosophy computable through stratification without sacrifice."

**Finding:** dharma_swarm has **significant philosophical-to-computational mappings already in place**, but they are **partially wired, not fully enforced**. The 6-layer architecture exists in **conceptual form** and **partial implementation**, but lacks the **strict separation and enforcement** the power prompt demands.

**Gap Type**: **Wiring gaps, not architectural gaps.** The components exist. The connections are incomplete.

---

## The 6-Layer Model (Power Prompt Specification)

| Layer | Purpose | Status in dharma_swarm |
|-------|---------|------------------------|
| **Layer 0: Constitutional Kernel** | Immutable law, tiny and sacred | ✅ **EXISTS** — `dharma_kernel.py`, `telos_gates.py` |
| **Layer 1: Action/Event Substrate** | Provenance, all mutations through actions | ⚠️ **PARTIAL** — `traces.py`, `event_log.py` exist, not universally enforced |
| **Layer 2: Operational Services** | Boring infrastructure (memory, cost, registry) | ✅ **EXISTS** — Multiple modules, testable |
| **Layer 3: Living Adaptive Layers** | Stigmergy, shakti, subconscious, evolution, organism | ✅ **EXISTS** — `stigmergy.py`, `shakti.py`, `subconscious.py`, operational |
| **Layer 4: Control Plane** | Dashboard, API, TUI, runtime views | ⚠️ **PARTIAL** — Dashboard exists, TUI exists, not unified |
| **Layer 5: Verification / Witness** | Always-on independent verifier | ⚠️ **PARTIAL** — Verification lane exists, not fully independent |

---

## Philosophy → Computation Mapping Audit

### ✅ **MAPPED AND OPERATIONAL**

| Philosophy Concept | Computational Primitive | Implementation | Evidence |
|-------------------|------------------------|----------------|----------|
| **Telos (Jagat Kalyan)** | Gate constraints + fitness dimension | `telos_gates.py` (11 gates), `dharma_kernel.py` (25 axioms) | 913 lines, tested |
| **Downward Causation** | Higher-layer gates block lower-layer ops | `dharma_kernel.py` DOWNWARD_CAUSATION_ONLY axiom, `telos_gates.py` gate hierarchy | Explicit constraint |
| **Stigmergy (ant colony intelligence)** | Environmental state marks | `stigmergy.py` (220 lines) — marks.jsonl, hot paths, salience | Operational, tested |
| **Shakti (4 creative energies)** | Perception classifier | `shakti.py` (201 lines) — 4 energy types, classify_energy() | Operational, tested |
| **Subconscious / Dream Layer** | Lateral association engine | `subconscious.py` (191 lines) — Jaccard similarity, dream marks | Operational, tested |
| **Identity / Swabhaav** | Self-model via ontology | `ontology.py`, `identity.py`, `organism.py` | Operational |
| **Anekantavada (multi-perspective)** | Cross-track validation requirement | `dharma_kernel.py` ANEKANTAVADA axiom, `anekanta_gate.py` | Enforced |
| **Witness Architecture** | Observer separation | `witness.py`, `dharma_kernel.py` OBSERVER_SEPARATION axiom | Enforced |
| **Gnani vs Prakruti (immutable vs dynamic)** | Layer separation pattern | `LIVING_LAYERS.md` lines 11-26 | Documented, partially enforced |
| **Autocatalytic Closure** | Self-production requirement | `dharma_kernel.py` AUTOCATALYTIC_CLOSURE axiom | Defined |
| **Reversibility** | All mutations logged + replayable | `dharma_kernel.py` REVERSIBILITY_REQUIREMENT, `traces.py`, `event_log.py` | Infrastructure exists |

---

### ⚠️ **PARTIAL MAPPING (Philosophy exists, computation incomplete)**

| Philosophy Concept | Expected Primitive | Current Status | Gap |
|-------------------|-------------------|----------------|-----|
| **"Every mutation through an Action"** (P1) | No direct shared-state writes | `traces.py` exists, but NOT universally enforced | Agents CAN bypass actions — no compiler enforcement |
| **Shakti Hook Injection** | Auto-inject into agent prompts | Hook text defined (`shakti.py` line 196) | NOT injected by `startup_crew.py` or `agent_runner.py` |
| **Stigmergy auto-marks** | Agents leave marks on task completion | `leave_stigmergic_mark()` exists | NOT called by `agent_runner.py` automatically |
| **Shakti → Darwin escalation** | High-impact perceptions route to evolution | `ShaktiLoop` produces escalation dicts | NOT routed to `evolution.py` — logged only |
| **Constitutional enforcement at runtime** | Layer 0 blocks violating operations | Gates exist, kernel exists | NOT wired into ALL mutation paths |
| **Dashboard as canonical control plane** | Single unified view of organism state | Dashboard exists (`dashboard/`) | TUI, CLI, API are parallel surfaces, not subordinate |
| **Verification lane independence** | Read-only verifier with separate context | `docs/architecture/VERIFICATION_LANE.md`, `scripts/verification_lane.py` | Exists, but not "partially independent" yet |

---

### ❌ **MISSING MAPPING (Philosophy documented, no computational primitive)**

| Philosophy Concept | Where Documented | What's Missing |
|-------------------|-----------------|----------------|
| **"Constitution must be smaller than metabolism"** | Power prompt commandment #3 | No size enforcement, no boundary check |
| **"No subsystem gets silent privilege"** | Power prompt commandment #4 | Dream layer, organism layer emit traces, but no enforcement that ALL do |
| **Replay as canonical verification** | Power prompt emphasis | `event_log.py` has replay infra, but no canonical replay test suite |
| **Model-agnostic action substrate** | Power prompt "future models" section | Actions exist, but not yet the PRIMARY abstraction (models are still first-class) |
| **Split-brain guard as enforced runtime check** | `docs/architecture/VERIFICATION_LANE.md` mentions it | Script exists, not enforced at boot |

---

## The 10 Engineering Commandments (Power Prompt) — Audit

| # | Commandment | Status | Evidence |
|---|------------|--------|----------|
| 1 | Every philosophical concept must compile to code | ⚠️ PARTIAL | Most concepts have code, but not all are ENFORCED |
| 2 | Every runtime mutation must be replayable | ⚠️ PARTIAL | Replay infra exists, not canonical |
| 3 | The constitution must be smaller than the metabolism | ❌ NOT ENFORCED | No size check |
| 4 | No subsystem gets silent privilege | ⚠️ PARTIAL | Most emit traces, not enforced |
| 5 | The dashboard shows the truth, not vibes | ⚠️ PARTIAL | Dashboard exists, not canonical yet |
| 6 | Legacy must be wrapped, not smeared | ⚠️ PARTIAL | `organism.py` lines 1-13 admit dual APIs exist |
| 7 | Verification must be partially independent | ⚠️ PARTIAL | Verification lane exists, not isolated |
| 8 | Future models plug into stable contracts | ⚠️ PARTIAL | Provider routing exists, but models are still first-class |
| 9 | Philosophy belongs in selectors, constraints, and scores | ✅ YES | `telos_gates.py`, `quality_forge.py`, `evolution.py` |
| 10 | The moonshot needs cadence | ✅ YES | `orchestrate_live.py` — 5 concurrent loops, defined intervals |

**Score: 2/10 YES, 7/10 PARTIAL, 1/10 NO**

---

## Gap Analysis by Layer

### **Layer 0: Constitutional Kernel** — ✅ STRONG

**What exists:**
- `dharma_kernel.py`: 25 meta-principles (10 safety/ethics + 15 from foundations)
- `telos_gates.py`: 11 gates (AHIMSA, SATYA, CONSENT, VYAVASTHIT, REVERSIBILITY, SVABHAAVA, BHED_GNAN, WITNESS, + 3 more)
- SHA-256 tamper-evident signature over principles
- Gate variety expansion protocol (propose → approve → load approved)

**What's missing:**
- **Size enforcement**: No check that Layer 0 is smaller than Layer 3
- **Universal gate-checking**: Not all code paths check gates before mutation

**Power prompt requirement:**
> "This must be tiny, sacred, and stable. Nothing in the system gets to bypass Layer 0."

**Gap:** Kernel is well-defined, but NOT universally enforced as a blocker.

---

### **Layer 1: Action/Event Substrate** — ⚠️ PARTIAL

**What exists:**
- `traces.py`: TraceStore with atomic JSON writes, history, archive, patterns
- `event_log.py`: Append-only JSONL event log with RuntimeEnvelope schema
- `lineage.py`: Provenance tracking
- Action models exist

**What's missing:**
- **P1 ("Every mutation through an Action") is NOT ENFORCED**
  - Agents CAN write directly to shared state
  - No compile-time or runtime check that mutations go through actions
- **Trace emission is not mandatory**
  - `agent_runner.py` does NOT automatically log to TraceStore on task completion
- **No canonical replay harness**
  - Replay infra exists, but no test that replays full sessions

**Power prompt requirement:**
> "If it matters, it emits: who acted, why, under what policy, on what object, with what gate result, with what outcome, with what cost, with what confidence, with what reversibility status."

**Gap:** Infrastructure exists, but NOT wired as the ONLY path.

---

### **Layer 2: Operational Services** — ✅ STRONG

**What exists:**
- Task board (`task_board.py`)
- Agent registry (`agent_registry.py`, `swarm.py`)
- Memory (`memory.py`, `memory_palace.py`)
- Provider routing (`providers.py`, `model_routing.py`)
- Cost tracking (`cost_tracker.py`)
- Evaluation registry (`evaluation_registry.py`)
- Archive (`archive.py`)
- State persistence (SQLite, JSONL)

**What's missing:**
- **Not isolated from philosophical leakage**
  - Some modules in Layer 2 have telos/dharma concepts mixed in
  - No strict "boring infrastructure only" boundary

**Power prompt requirement:**
> "This layer must be: typed, modular, benchmarked, testable in isolation, free of mystical leakage."

**Gap:** Mostly clean, but boundary is fuzzy.

---

### **Layer 3: Living Adaptive Layers** — ✅ STRONG

**What exists:**
- `stigmergy.py`: 220 lines, marks.jsonl, hot paths, salience, decay
- `shakti.py`: 201 lines, 4 energy classification, perception loop
- `subconscious.py`: 191 lines, dream cycle, Jaccard associations
- `evolution.py`: DarwinEngine, proposal → gate → evaluate → archive → select
- `organism.py`: VSM, AMIROS, memory, routing, lifecycle hooks
- `strange_loop.py`: Self-reference detection

**What's missing (from LIVING_LAYERS.md lines 370-397):**
1. **SHAKTI_HOOK not injected** — Agents don't perceive through Shakti lens automatically
2. **Stigmergy marks not auto-left** — Agents don't leave marks on task completion
3. **Shakti escalations not routed to Darwin** — High-impact perceptions are logged, not evolved
4. **Dream marks not weighted differently** — All marks treated equally in hot path calc

**Power prompt requirement:**
> "Living layers may propose. They do not get to silently rewrite the constitution."

**Gap:** Components work, wiring incomplete. Proposal paths exist, but routing to Layer 0 gates is partial.

---

### **Layer 4: Control Plane** — ⚠️ PARTIAL

**What exists:**
- `dashboard/`: Next.js dashboard (README.md, package.json, src/)
- `api/`: FastAPI backend (`main.py`, routers, GraphQL)
- `tui/`: Textual TUI (multiple modules)
- `dgc_cli.py`: CLI (1700+ lines)

**What's missing:**
- **Dashboard not canonical**
  - Dashboard, TUI, CLI are parallel surfaces
  - No single source of truth
- **Dashboard doesn't show full organism state**
  - `PRODUCT_SURFACE.md` says dashboard is canonical, but implementation is behind

**Power prompt requirement:**
> "This is where philosophy becomes visible agency. Keep the TUI and shells, but subordinate them to one stable control-plane contract."

**Gap:** Multiple surfaces exist, not unified under one contract.

---

### **Layer 5: Verification / Witness** — ⚠️ PARTIAL

**What exists:**
- `docs/architecture/VERIFICATION_LANE.md`: Documentation
- `scripts/verification_lane.py`: Read-only verifier
- `scripts/split_brain_guard.sh`: Legacy process detection
- `witness.py`: Witness pattern implementation
- Health checks, anomaly detection exist

**What's missing:**
- **Not "partially independent"**
  - Verification lane runs in same context as main system
  - No separate process, no separate state
- **No continuous verification**
  - Verification lane is script-based, not always-on daemon
- **No split-brain ENFORCEMENT**
  - Guard script exists, but not run at boot or on cron

**Power prompt requirement:**
> "This must be always-on and partially independent. The organism should not be the only witness of itself."

**Gap:** Verification exists, but not architecturally independent.

---

## Quantitative Summary

### Philosophy → Code Mapping Status

| Mapping Status | Count | % |
|----------------|-------|---|
| ✅ **Mapped & Operational** | 11 concepts | 48% |
| ⚠️ **Partial** (concept exists, wiring incomplete) | 7 concepts | 30% |
| ❌ **Missing** (no computational primitive) | 5 concepts | 22% |

### Total Concepts Audited: 23

---

## The Real Numbers

**What Windsurf likely SAW:**
- 260+ Python modules
- 4300+ tests
- Extensive philosophical documentation (LIVING_LAYERS.md, PRINCIPLES.md, foundations/)
- Sophisticated concepts (stigmergy, shakti, subconscious, telos gates)

**What Windsurf likely MISSED:**
- The wiring gaps documented in LIVING_LAYERS.md lines 370-397
- The dual organism APIs admitted in organism.py lines 1-13
- The fact that P1 ("every mutation through an Action") is NOT enforced
- The fact that dashboard/TUI/CLI are parallel, not unified

**Why the gaps exist:**
- This is a **living, evolving system** actively under development
- The repo is **carrying multiple epochs** (legacy + current + future)
- **Philosophical design is ahead of implementation hardening**
- This is **normal for a research-grade system**, not a failure

---

## Critical Insight from Power Prompt

> **"Do not reduce the vision. Reduce the ambiguity."**

**Translation for dharma_swarm:**
- ✅ The vision is coherent (6 layers, philosophy as primitive, telos as law)
- ✅ The components exist (kernel, gates, traces, stigmergy, shakti, organism)
- ❌ The **enforcement is incomplete** (P1 not universal, hooks not injected, routing partial)
- ❌ The **boundaries are fuzzy** (Layer 2 has philosophical leakage, Layer 4 is not unified)

---

## What This Means

**You do NOT need to:**
- Kill any philosophy
- Reduce the organism metaphor
- Simplify to "just an agent framework"
- Rebuild from scratch

**You DO need to:**
1. **Wire the gaps** — Auto-inject Shakti hooks, auto-leave stigmergy marks, route escalations
2. **Enforce P1 universally** — Make action-based mutations the ONLY path (static analysis or runtime guard)
3. **Unify Layer 4** — Make dashboard canonical, subordinate TUI/CLI
4. **Isolate Layer 5** — Make verification lane a separate daemon with own state
5. **Check Layer 0 size** — Add a gate that kernel + gates < living layers in LOC
6. **Formalize the constitution** — Turn PRINCIPLES.md into runtime-checked contracts

---

## Recommended Next Steps

### If you want the **FULL MOONSHOT** (per power prompt):

1. **Phase 1: Constitutional Hardening** (2 weeks)
   - Enforce P1: All mutations through actions (add runtime guard or static checker)
   - Wire Shakti hooks into `agent_runner.py`
   - Wire stigmergy auto-marks into `agent_runner.py`
   - Wire Shakti escalations → `evolution.py`

2. **Phase 2: Layer Boundary Enforcement** (2 weeks)
   - Add size check: Layer 0 < Layer 3 (gate at boot)
   - Isolate Layer 2: No telos/dharma concepts in operational services
   - Unify Layer 4: Dashboard as canonical, TUI/CLI as views
   - Separate Layer 5: Verification lane as independent daemon

3. **Phase 3: Replay Canonical** (1 week)
   - Build canonical replay harness
   - Add replay tests to CI
   - Make replay the PROOF of correctness

4. **Phase 4: Future-Model Readiness** (1 week)
   - Make actions/contracts the primary abstraction
   - Models become replaceable organs
   - Provider routing is universal

**Total:** 6 weeks to make the philosophy fully computable.

---

## If you want **QUICK WIN** (validation that the vision works):

Pick ONE subsystem and harden it end-to-end:

**Candidate: Stigmergy + Shakti + Subconscious Loop**

- Wire auto-marks
- Wire Shakti hooks
- Wire escalations → Darwin
- Add replay test
- Show: "Philosophy → Runtime → Provenance → Evolution" in one closed loop

**Time:** 3-5 days

**Value:** Proves the architecture works, builds confidence for full hardening.

---

## Conclusion

**dharma_swarm is NOT vaporware.**

It is a **research-grade thinkodynamic system** with:
- ✅ Strong philosophical grounding (11 pillars, 25 axioms, 11 gates)
- ✅ Real computational primitives (stigmergy, shakti, subconscious, gates, kernel)
- ✅ Operational infrastructure (260+ modules, 4300+ tests, daemon, orchestrator)
- ⚠️ **Incomplete wiring** (hooks not injected, P1 not enforced, layers not separated)

**The gap is NOT architectural. The gap is INTEGRATION.**

**The power prompt is RIGHT:**
> "You are not failing because the vision is too large. You are at risk because the philosophy is ahead of the formalization."

**Fix:**
> "Be stranger, but with cleaner contracts."

---

## Appendix: Key Files Referenced

| File | Role | Lines | Status |
|------|------|-------|--------|
| `dharma_kernel.py` | Layer 0 kernel | 428 | Operational |
| `telos_gates.py` | Layer 0 gates | 913 | Operational |
| `traces.py` | Layer 1 trace store | 256 | Operational, not universal |
| `event_log.py` | Layer 1 event log | 155 | Operational |
| `stigmergy.py` | Layer 3 stigmergy | 220 | Operational, auto-marks missing |
| `shakti.py` | Layer 3 shakti | 201 | Operational, hook not injected |
| `subconscious.py` | Layer 3 subconscious | 191 | Operational |
| `organism.py` | Layer 3 organism | 1146 | Operational, dual APIs |
| `orchestrate_live.py` | Layer 3 orchestrator | 356 | Operational |
| `dashboard/` | Layer 4 control plane | — | Exists, not canonical |
| `docs/architecture/VERIFICATION_LANE.md` | Layer 5 verification | 65 | Documented |
| `LIVING_LAYERS.md` | Architecture doc | 403 | ✅ Honest gap assessment (lines 370-397) |
| `PRINCIPLES.md` | Architecture doc | 297 | ✅ Philosophy → code mapping |

---

**Report prepared by:** Claude (Augment Code) via direct codebase audit  
**Date:** 2026-03-27  
**Next action:** Decide: Full moonshot (6 weeks) or quick win (3-5 days)?
