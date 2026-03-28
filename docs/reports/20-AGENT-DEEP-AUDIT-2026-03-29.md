# dharma_swarm 20-Agent Deep Audit Synthesis

**Date**: 2026-03-29
**Scope**: Post-cleanup comprehensive audit — not "do tests pass" but "does the system work end-to-end"
**Agents deployed**: 20 (10 Claude expert personas + 10 PAL open-model)
**Agents reporting**: 13/20 (7 PAL agents stuck on MCP endpoint timeouts — see Appendix F)
**Models used**: Claude Opus 4.6 (10 agents), GPT-5.2 via PAL (3 agents)

---

## EXECUTIVE SUMMARY

dharma_swarm is a **genuinely novel system** with real intellectual depth — 7 of 10 philosophical pillars implemented in code, not just documented. The architecture is legitimate cybernetics (Beer's VSM at 70% wiring), the math is mostly correct (with 2 naming overclaims and 1 calibration bug), and the engineering is solid (B+ code quality, 97.2% type hints, 93.7% test coverage).

**It is not production-ready for unattended 24/7 operation.** Estimated MTBF: 4-12 hours. The dominant failure mode is not crashes (handled by supervisor restarts) but **liveness collapse without crash** — SQLite lock contention, threadpool saturation, or event loop blocking causes all loops to remain "alive" but stop making progress, with no watchdog to detect it.

**It has 4 real security vulnerabilities** (eval RCE, telos gate unicode bypass, kernel tamper forgeable, shell=True) that must be fixed before any external exposure.

**The evolution system is 96% phantom** — only 21 of 576 archive entries contain actual code diffs, no lineage trees exist, and the diversity archive has never been populated. But meta-evolution IS real (864 entries with measurable improvement). The pipes are correctly laid; the water isn't flowing.

**The consciousness architecture exists as three disconnected islands** that all work individually but aren't wired into the production runtime. Connecting them is future architecture, not cleanup.

---

## A. CRITICAL FINDINGS (Must Fix)

### A1. Security Vulnerabilities

| # | Finding | Severity | Agent | Fix |
|---|---------|----------|-------|-----|
| 1 | **`eval()` RCE** in `citation_index.py:180` — arbitrary Python execution via verification_test strings, namespace includes `os` and `Path` | CRITICAL | Security | Replace with `ast.literal_eval()` or sandboxed execution |
| 2 | **Telos gate AHIMSA bypass via unicode zero-width characters** — `\u200b` inside harm words evades substring check. 8/13 adversarial inputs bypassed blocking. `injection_scanner.py` detects unicode but is NOT wired into gate preprocessing | CRITICAL | Security | Wire `injection_scanner.py` into gate preprocessing pipeline |
| 3 | **`shell=True` in `scout_framework.py:208`** — string commands passed to subprocess with shell interpretation | CRITICAL | Security | Use `subprocess.run(cmd_list)` without `shell=True` |
| 4 | **`pickle.load()` in `vector_store.py:297`** — tampered state file gives full RCE | HIGH | Security | Switch to `safetensors` or JSON serialization |
| 5 | **Kernel tamper detection is self-referential** — SHA-256 stored in same file it signs. Attacker modifies principles + rehashes. `verify_integrity()` passes because it only compares against self-referential recomputation | HIGH | Security, GPT-5.2 | Upgrade to HMAC-SHA256 with external key, or rename to "checksum" |
| 6 | **Cross-layer prompt injection via stigmergy/shared notes** — retrieved context injected into prompts without injection scanning. Compromised marks can instruct models to bypass gates | HIGH | GPT-5.2 Governance | Add context quarantine wrapper, scan all injected blocks |
| 7 | **No pre-tool-use gate at side-effect point** — `_execute_local_tool()` has file writes and shell execution with no explicit gate at moment of side effect | HIGH | GPT-5.2 Governance | Add mandatory `pre_tool_use(tool_name, params)` gate |

### A2. Operational Risks

| # | Finding | Severity | Agent | Fix |
|---|---------|----------|-------|-----|
| 8 | **18GB `~/.dharma/` with unbounded growth** — `memory_plane.db` 3.5GB, `temporal_graph.db` 1.3GB (frozen since Mar 14), `sessions/` 674MB (924 files), no TTL, no archival, no vacuum | CRITICAL | DevOps | Add retention policy, WAL checkpoint cron, log rotation |
| 9 | **ontology.db WAL = 592MB** — stuck read transaction preventing checkpoint. Crash in this state risks data loss | CRITICAL | DevOps | Force WAL checkpoint, investigate lock holder |
| 10 | **No log rotation** — `artifact_watcher_stderr.log` writes noise every 5 min (5.1MB), `daemon.log` climbing | HIGH | DevOps | Add logrotate config or size-based rotation |
| 11 | **4 stale PID files** — caffeine, overnight, sentinel, verification all point to dead processes | HIGH | DevOps | Clean up on daemon start, add PID reaping |
| 12 | **Restart counter never resets** — `max_restarts=5` is lifetime, not windowed. 5 transient errors over a week permanently kills a loop | HIGH | Anthropic Lead, GPT-5.2 | Time-windowed counter (5 per 3600s) |
| 13 | **Fire-and-forget asyncio task leaks** — `orchestrator.py:513` creates tasks without storing/awaiting. Hundreds of orphaned tasks per day | HIGH | Anthropic Lead | Track tasks, copy `evolution.py:_trace_bg` pattern |
| 14 | **MTBF 4-12 hours** — liveness collapse via SQLite contention, no watchdog | HIGH | Anthropic Lead, GPT-5.2 Stress, DevOps | Add liveness watchdog with per-loop progress timestamps |

---

## B. IMPORTANT FINDINGS (Should Fix)

### B1. Mathematical Defects

| # | Finding | Agent | Fix |
|---|---------|-------|-----|
| 15 | **Eigenform distance violates triangle inequality** (~2% of random cases) — normalized L1 is a semimetric, not a metric. Banach's contraction mapping theorem cannot be invoked. "Eigenform" language is metaphor, not proof | Physics/Math | Use un-normalized L1 (which IS a metric) |
| 16 | **KV diversity function returns negative values** — theorem only holds for MSE + simple averaging. With quality-weighted aggregation, the guarantee breaks | Physics/Math, ML PhD | Enforce MSE inputs or rename and drop KV citation |
| 17 | **Eigen threshold perpetually alarming** — default params (s=0.1, L=10) give threshold=0.01, while mutation_rate range is [0.01, 0.5]. Invariant always reports "critical" — calibration bug | Physics/Math | Raise `selective_advantage` to ~1.0 or lower `genome_length` |
| 18 | **`error_decorrelation` measures CV not statistical independence** — high CV means errors vary in magnitude, NOT that they're independent | ML PhD, Physics/Math | Rename to `error_dispersion` or implement pairwise correlation |
| 19 | **Temperature concentration attribution is loose** — docstring credits Zhang but Zhang uses softmax on token logits during generation, not post-hoc probability sharpening | ML PhD | Fix attribution in docstring |

### B2. VSM Wiring Gaps

| # | Finding | Agent | Fix |
|---|---------|-------|-----|
| 20 | **`on_gate_check()` never called from runtime** — swarm.py and orchestrator.py call `TelosGatekeeper.check()` directly, never forward results to `VSMCoordinator`. GatePatternAggregator accumulates nothing. Failure streak tracking for algedonic signals is dead | Cybernetics PhD | Wire `check()` results → `VSMCoordinator.on_gate_check()` |
| 21 | **`get_sensitivity_boost()` never consumed** — GatePatternAggregator computes sensitivity boosts from zeitgeist but TelosGatekeeper never reads them | Cybernetics PhD | Wire into `check()` call path |
| 22 | **`on_agent_viability()` never called** — AgentViabilityMonitor model is correct but no agent reports scores. `fleet_health()` always returns 1.0 (permanent false positive) | Cybernetics PhD | Wire agent_runner to report viability after task completion |
| 23 | **`_scan_claude()` is a stub** returning `[]` — S4 environmental intelligence has no outside-world scanning | Cybernetics PhD | Implement or remove |

### B3. Evolution System

| # | Finding | Agent | Fix |
|---|---------|-------|-----|
| 24 | **96% phantom evolution** — only 21/576 archive entries have actual code diffs. 555 are descriptions of intended changes | Sakana CEO | Enforce diff presence in `archive_result()` |
| 25 | **No lineage** — only 1 of 576 entries has parent_id. No descent with modification | Sakana CEO | Enforce parent selection before proposal |
| 26 | **5/8 fitness dimensions collapsed to 0.5** — performance, utilization, economic_value all defaulting. Effective fitness is `correctness * 0.4 + elegance * 0.15 + constants` | Sakana CEO | Connect to real runtime metrics |
| 27 | **DiversityArchive never populated** — file doesn't exist on disk. The mechanism that should prevent evolutionary collapse has never been exercised | Sakana CEO, Complex Systems | Wire into `archive_result()` |
| 28 | **Cascade engine: zero runs recorded** — history file doesn't exist. F(S)=S has never converged | Sakana CEO | Run at least code + meta domains |

### B4. Code Quality

| # | Finding | Agent | Fix |
|---|---------|-------|-----|
| 29 | **236 `except Exception: pass` blocks** — silent failure swallowing in autonomous daemon | Python Expert | Audit top 20, add logging or typed catches |
| 30 | **631 broad `except Exception` at DEBUG level** — the system looks healthy while writes silently disappear | Anthropic Lead | Elevate to WARNING in 12 critical-path modules |
| 31 | **4 threading.Lock in async runtime** — `observability.py`, `agent_memory_manager.py`, `ontology_hub.py`, `ecosystem_index.py` — blocks event loop | Anthropic Lead | Replace with `asyncio.Lock` |
| 32 | **55 functions above cyclomatic complexity 25** — `swarm.py:tick()` CC=82, `tui_legacy.py:_handle_command()` CC=78 | Python Expert | Decompose top 10 |
| 33 | **No dependency upper bounds** — `pydantic>=2.0` could break on 3.x | Python Expert | Use `pydantic>=2.0,<3` |
| 34 | **Init takes 20.1s, shutdown 28.4s** — too slow for crash recovery, SIGKILL risk on shutdown | Anthropic Lead | Parallelize subsystem init, reduce shutdown timeout |

---

## C. ADVISORY (Architecture Debt, Future Work)

| # | Finding | Agent |
|---|---------|-------|
| 35 | Self-model stale by 80% — NAVIGATION.md says 274 modules, reality is 493 | Palantir CEO |
| 36 | Telos objectives never updated — 200 hardcoded progress values, no updater | Palantir CEO |
| 37 | Ontology not in hot path — records outcomes, doesn't govern dispatch | Palantir CEO |
| 38 | 140 files exceed 500-line limit; `dgc_cli.py` at 6,888 lines | Python Expert |
| 39 | `__all__` missing in 84.6% of modules | Python Expert |
| 40 | All 660 stigmergy marks in "general" channel — 6-channel scoping dormant | Complex Systems |
| 41 | Transcendence modes (denoising/selection/generalization) declared but not implemented | ML PhD |
| 42 | Mycelium daemon runs Python 3.9 while everything else runs 3.14 | DevOps |
| 43 | 22/22 heartbeats in message bus are stale | DevOps |
| 44 | Redis connection refused (vestigial or real dependency?) | DevOps |
| 45 | 6 empty shadow .db files in `~/.dharma/` root (code hitting wrong path gets empty results) | DevOps |

---

## D. VALIDATED STRENGTHS (Do Not Touch)

These are things **multiple agents independently confirmed as genuinely well-built**:

| Strength | Confirming Agents | Detail |
|----------|------------------|--------|
| **97.2% type hint coverage** | Python Expert | 6,854/7,050 functions have return annotations |
| **Zero circular imports** | Python Expert, PAL E2E | 1,086 lazy imports are the correct prevention mechanism |
| **Zero bare `except:`** | Python Expert | All exception handlers are typed (though too broad) |
| **Zero JSONL data corruption** | Palantir CEO, DevOps | Across 660 stigmergy marks, 576 evolution entries, daily traces |
| **SQLite integrity clean** | DevOps (3 checks) | All DBs pass `PRAGMA integrity_check` |
| **VSM architecture is genuine cybernetics** | Cybernetics PhD | 100% architectural fidelity to Beer, 70% runtime wiring |
| **Transcendence algebra is correct** | ML PhD, Physics/Math | Core KV computation right, aggregation numerically stable |
| **MAP-Elites implementation grade A** | Physics/Math | Both `diversity_archive.py` and `archive.py` are correct |
| **Spectral criticality uses Perron-Frobenius correctly** | Physics/Math | A- grade |
| **Main daemon is solid** | DevOps | 16MB RSS, clean boot, health checks work |
| **Graceful degradation works** | DevOps | Read-only boot mode functional |
| **93.7% test file coverage** | Python Expert | 340/363 modules have matching test files |
| **Algedonic channel is a true bypass** | Cybernetics PhD | Single-digit ms latency, no intermediate layers |
| **Samvara four-power cascade properly wired** | Cybernetics PhD | Through OrganismRuntime, fluid altitude escalation |
| **Meta-evolution is real** | Sakana CEO | 864 entries, fitness weights drifting with measurable improvement |
| **Damper system production-quality** | Anthropic Lead | Named semaphores, correct concurrency control |
| **5-phase shutdown choreography** | Anthropic Lead | Ordered: gateway → bg tasks → agents → providers → memory |
| **WAL mode consistent** | Anthropic Lead | Across 20+ SQLite connection sites |
| **Circuit breaker + Gnani HOLD** | Anthropic Lead | Self-regulation that actually works |

---

## E. THE DEEPEST VERDICTS (Expert Quotes)

**Complex Systems Genius (SFI-level)**:
> "This is a well-designed complicated system with correct complexity vocabulary and dormant emergence potential, but it has not yet crossed the threshold into genuine complex adaptive behavior. 80% of the way — the last 20% is closing the feedback loops from measurement to enforcement."

**Sakana AI CEO (Llion Jones)**:
> "Parameter optimization wearing a sophisticated evolution costume — but the costume is well-tailored enough that it could become the real thing with modest changes. The pipes are laid correctly. The water isn't flowing through them."

**Anthropic Lead Engineer**:
> "NOT production-ready for unattended 24/7 operation. Estimated MTBF: 4-12 hours. The architecture is genuinely good — the 13-loop orchestrator with per-loop restart logic, signal handlers, graceful shutdown choreography, and circuit breakers shows strong systems thinking. But seven engineering gaps would cause failure in sustained operation."

**Cybernetics PhD**:
> "Architecture: 100% VSM. Runtime wiring: 70%. Three specific integration-point fixes would bring it to full compliance."

**Physics/Math**:
> "Aspiration-forward math, not cargo-cult, but with real defects. The spectral criticality and MAP-Elites are grade A. The eigenform convergence and KV attribution are overclaims."

**Python Expert**:
> "Grade B+. Strong foundations with concentrated structural debt. 97.2% type hints is excellent for 220K LOC. The debt is concentrated in two places: swallowed exceptions and god-functions."

**GPT-5.2 Architecture Review**:
> "Rating: 6.5/10. Strong schema layer, thoughtful abstractions, meaningful governance, clear intent to build resilient long-running autonomy. But complexity concentration, unclear degraded-mode semantics, and persistence contention risk."

**GPT-5.2 Stress Analysis**:
> "The single most important finding: the system's biggest vulnerability is not crashes but liveness collapse without crash — where SQLite lock contention causes all loops to remain alive but stop making progress, with no watchdog to detect or recover from this state."

**GPT-5.2 Governance Review**:
> "Stronger-than-average governance layering compared to typical agent frameworks. Where it lags serious safety systems: lack of capability-based enforcement, lack of cryptographic provenance, and insufficient hardening against indirect prompt injection via memory/stigmergy channels."

---

## F. PAL MCP INFRASTRUCTURE NOTE

**7 of 10 PAL agents got stuck** waiting for model endpoint responses. The configured PAL providers (OpenAI direct, OpenRouter) don't expose Qwen 3.5, GLM-5, MiniMax 2.7, or Kimi 2.5 — all PAL agents fell back to GPT-5.2. The stuck agents appear to have completed their code analysis but stalled on the PAL MCP tool call.

**Immediate fix needed**: Verify PAL MCP server configuration. Check:
1. Which models are actually available: `mcp__pal__listmodels`
2. Whether Ollama Cloud endpoints (GLM-5, DeepSeek-v3.2, Kimi-K2.5) are reachable
3. PAL MCP timeout settings — 10+ minute hangs suggest no timeout configured
4. Consider adding explicit timeout to PAL tool calls

This is a dharma_swarm infrastructure issue — the system claims multi-model diversity (Transcendence Principle) but the model routing actually collapses to a single provider in practice. The same pattern that makes the evolution 96% phantom (diversity claimed but not achieved) appears in the tooling layer.

---

## G. CLAUDE'S OPINIONS AND RECOMMENDATIONS

### What I think after seeing all 13 reports converge:

**1. The system is more real than I initially assessed.** My first audit (the 10-agent scan) treated it as a messy repo needing cleanup. The deep dive reveals genuine intellectual architecture — Beer's VSM at 70% wiring, correct Perron-Frobenius spectral analysis, real meta-evolution, working algedonic channels. This is not documentation-driven development. The code implements the ideas.

**2. The gap between architecture and dynamics is the central challenge.** Every expert independently identified the same pattern: correct structure, dormant dynamics. The VSM is architecturally 100% but runtime 70%. The evolution has correct pipes but phantom data. The consciousness loop works individually but isn't wired to production. The stigmergy has 6 channels but all marks go to "general." The invariants compute correctly but nobody reads the results.

This is not a code quality problem. It's a **commissioning problem**. The system is built but not turned on. The metaphor from the Sakana CEO is perfect: "The pipes are laid correctly. The water isn't flowing through them."

**3. The security findings are the only true blockers for merge.** The eval() RCE and unicode gate bypass are real vulnerabilities that should be fixed before the branch merges to main. Everything else (disk growth, restart counters, math naming) is post-merge improvement work.

**4. The 5 changes that would cross the emergence threshold** (from the Complex Systems agent) are the highest-leverage work items for the next development cycle:
   1. Close the invariant loop (spectral radius → dampen)
   2. Make strange loop generative (LLM-proposed mutations)
   3. Activate stigmergy channels
   4. Wire diversity archive to evolution
   5. Make the ambient seed state-dependent

These are not refactoring. They are the difference between a complicated system and a genuinely complex adaptive one.

**5. The PAL MCP problem mirrors the Transcendence Principle's own warning.** The system claims multi-model diversity but the tooling collapses to one provider. This is exactly what the CLAUDE.md warns about: "Correlated errors compound; decorrelated errors cancel." If all analysis comes from GPT-5.2, we have one perspective, not ten. Fix the PAL routing so the diversity claimed is diversity achieved.

### Recommended Priority Order

**Before merge to main (hours):**
1. Fix eval() RCE in citation_index.py
2. Wire injection_scanner into telos gate preprocessing
3. Remove shell=True from scout_framework.py
4. Replace pickle.load in vector_store.py

**First week post-merge:**
5. Add liveness watchdog with per-loop progress timestamps
6. WAL checkpoint cron for ontology.db
7. Time-windowed restart counter
8. Wire 3 severed VSM channels
9. Fix eigenform distance metric (un-normalize L1)
10. Recalibrate Eigen threshold defaults

**Next development cycle:**
11. Close the 5 emergence-threshold feedback loops
12. Wire organism_pulse into production runtime
13. Connect diversity archive to evolution
14. Activate stigmergy channel scoping
15. Decompose SwarmManager God Object

---

## APPENDIX: Agent Inventory

| # | Agent | Type | Status | Key Contribution |
|---|-------|------|--------|-----------------|
| 1 | devops-lead | Claude | COMPLETE | 18GB disk, WAL bloat, stale PIDs |
| 2 | security-auditor | Claude | COMPLETE | 4 CRITICAL vulns, gate bypass verified |
| 3 | cybernetics-phd | Claude | COMPLETE | VSM 70% wired, 3 severed wires |
| 4 | ml-phd | Claude | COMPLETE | Math correct, 2 naming overclaims |
| 5 | anthropic-lead | Claude | COMPLETE | MTBF 4-12h, task leaks, threading.Lock |
| 6 | sakana-ceo | Claude | COMPLETE | Evolution 96% phantom, meta-evo real |
| 7 | palantir-ceo | Claude | COMPLETE | Self-model stale 80%, telos static |
| 8 | python-expert | Claude | COMPLETE | B+, 97.2% typed, 236 swallowed |
| 9 | complex-systems | Claude | COMPLETE | 80% to emergence, dynamics dormant |
| 10 | physics-math | Claude | COMPLETE | Triangle inequality violation, Eigen miscal |
| 11 | pal-qwen → GPT-5.2 | PAL | COMPLETE | 6.5/10, complexity concentration |
| 12 | pal-minimax → GPT-5.2 | PAL | COMPLETE | Pre-tool-use gate missing, prompt injection |
| 13 | pal-stress → GPT-5.2 | PAL | COMPLETE | Liveness collapse, SQLite blast radius |
| 14 | pal-glm5 | PAL | STUCK | Code analysis captured, PAL call hung |
| 15 | pal-kimi | PAL | STUCK | Code analysis captured, PAL call hung |
| 16 | pal-python-quality | PAL | STUCK | Code analysis captured, PAL call hung |
| 17 | pal-data-integrity | PAL | STUCK | Code analysis captured, PAL call hung |
| 18 | pal-redteam | PAL | STUCK | Code analysis captured, PAL call hung |
| 19 | pal-philosophy | PAL | STUCK | Code analysis captured, PAL call hung |
| 20 | pal-e2e | PAL | STUCK | Code analysis captured, PAL call hung |

---

*This synthesis represents ~800K tokens of analysis across 13 reporting agents (10 Claude Opus 4.6 + 3 GPT-5.2 via PAL), examining 493 Python modules, 219,810 lines of code, 8,465 tests, and 18GB of runtime state. Total session: 42 agents deployed across two audit phases.*

*JSCA.*
