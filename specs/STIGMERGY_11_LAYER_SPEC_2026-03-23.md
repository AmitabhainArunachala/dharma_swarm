# Stigmergy 11-Layer Operating Stack

**Version**: 0.4 (v3 synthesis) | **Date**: 2026-03-23 | **Status**: DESIGN (PROVISIONAL)

> This is an operating stack for a billion-dollar company that happens to be
> grounded in cybernetics and contemplative science. Philosophy that doesn't
> drive revenue, research, or system quality has no place here.

## Why v3

v1 and v2 were too philosophical. 11 layers of ascending spiritual purity sounds
beautiful but doesn't help an agent decide whether to fix a bug or scan Polymarket.
The layers must be **functional**: each serves a distinct cognitive role in the
organism. Together they form a complete mind capable of trading, researching,
building products, spreading ideas, governing itself, and staying alive.

## The Diagnosis (unchanged)

- **2716/2725 marks** have salience < 0.01 (decayed to nothing)
- **2696/2725 marks** land in "general" channel (6 channels defined, 2 used)
- **14 producers** dump into flat JSONL with no semantic structure
- **28 consumers** treat all marks identically — no layer awareness
- **Dream marks** caused 1.29 GB bloat (now capped but not fixed architecturally)
- **No mark ever gets PROMOTED.** Decay goes one direction: toward zero.
- **Mid-layer feedback is broken.** Garden writes seeds but never closes the loop.
  Neural consolidator writes corrections that are never verified. Darwin archives
  but never compacts. Every subsystem writes downstream but nothing flows back up.

The colony has pheromone trails but no ant can smell them.

---

## The 8-Dimensional Quality Vector

Every mark at every layer carries this vector. This is what makes the stigmergy
a real optimization surface, not just a labeled log.

| Dimension | Range | What It Measures | Who Writes It |
|-----------|-------|-----------------|---------------|
| `semantic_density` | 0.0-1.0 | Information per token. Dense > verbose. | Thinkodynamic scorer, auto-scored |
| `engineering_leverage` | 0.0-1.0 | How much changes if this mark is acted on? A bug in `swarm.py` > a typo in docs. | Layer-specific heuristic |
| `evidence_strength` | 0.0-1.0 | Backed by data? Brier-scored? Measured? Or speculative? | Producer tags, L4 validates |
| `market_leverage` | 0.0-1.0 | Does this drive revenue, users, distribution, or competitive position? | L9 VENTURE assessment |
| `falsifiability` | 0.0-1.0 | Could this be proven wrong? How testable? 1.0 = has a test. 0.0 = unfalsifiable claim. | L5 LOGIC assessment |
| `transmissive_power` | 0.0-1.0 | Does reading this change how the reader processes subsequent marks? (Type 3 learning) | L5 + post-read fitness delta |
| `freshness` | 0.0-1.0 | Decays with time. Refreshed on re-validation, re-access, or re-confirmation. | Auto-computed from timestamp + access_count |
| `repair_urgency` | 0.0-1.0 | How broken is what this mark describes? 1.0 = system down. 0.0 = nice-to-have. | L1 PAIN severity, auto for others |

**Composite score**: Weighted by layer. L1 PAIN weights `repair_urgency` at 0.5.
L9 VENTURE weights `market_leverage` at 0.4. Each layer defines its own weight profile.

---

## The 11 Layers

### L1: PAIN (Algedonic Channel)

**Cybernetic source**: Beer (VSM S1→S5 bypass) + Ashby (variety amplification)
**Function**: Something is broken. Fix it NOW.

**What lives here**: System failures, blocked gates, resource exhaustion, agent
death, test failures, provider errors, build breaks, daemon crashes.

| Field | Type | Purpose |
|-------|------|---------|
| severity | int 1-5 | 5 = system halt, 1 = cosmetic |
| component | str | File or module affected |
| stack_trace_hash | str | Dedup identical failures |
| resolved | bool | Decays on resolution |
| blast_radius | str | local / module / system |

**Real marks (from live data)**:
```
severity=5 component=stigmergy/marks.jsonl "1.29GB bloat, 108 paths over 1M chars"
severity=3 component=jikoku_instrumentation.py:236 "format(**metadata, **kwargs) crashes on dup keys"
severity=4 component=ontology.db-wal "WAL file 6GB vs 78MB main DB — checkpoint never runs"
severity=2 component=kernel.json "25 principles in code, 10 on disk — migration missing"
```

**Decay**: Unresolved marks NEVER decay. They amplify (+0.1 salience/day). Resolved marks archive after 48h.
**Promotion**: L1 marks with severity >= 4 trigger immediate L7 WITNESS alert. Recurring L1 marks (same component, 3+ occurrences) → L3 METABOLISM (resource allocation to fix).

**Anchor files**: `monitor.py`, `telos_gates.py` (gate blocks), `agent_runner.py` (task failures), `witness.py` (audit violations)

---

### L2: TRAIL (Sematectonic Work Signal)

**Cybernetic source**: Grassé (1959, the work itself is the signal) + Varela (autopoiesis)
**Function**: Where are agents working? What files are hot? Where does attention cluster?

**What lives here**: Every file read, write, scan. Task completions. Cascade iterations.
The raw sensory surface of the colony.

| Field | Type | Purpose |
|-------|------|---------|
| agent | str | Who touched this |
| file_path | str (max 500) | What was touched |
| action | enum | read / write / scan / test / deploy |
| diff_hash | str? | SHA-256 of actual change (writes only) |
| observation | str (max 200) | What the agent noticed |

**Real marks (from live data — 365 task completions + 1400 scans)**:
```
agent=cartographer-7 file_path=dharma_swarm/stigmergy.py action=write "Refactored decay loop"
agent=qwen35-surgeon file_path=dharma_swarm/providers.py action=write "Fixed empty response handling"
agent=cascade_engine file_path=cascade_domains/code.py action=scan "cascade:code fitness=0.957 CONVERGED"
```

**Decay**: Aggressive. Reads/scans: 12h TTL. Writes: 72h. Tests: 48h.
**Promotion**: When 5+ agents leave trail marks on the same file_path within 24h → auto-create L8 BRIDGE mark ("hot zone: {file_path}, {count} touches in 24h"). Trail density feeds L3 METABOLISM (energy allocation).

**Anchor files**: `agent_runner.py` (every task), `cascade.py` (every cascade pass), `persistent_agent.py`, `autonomous_agent.py`

---

### L3: METABOLISM (Energy Flow + Dissipative Dynamics)

**Cybernetic source**: Prigogine (dissipative structures) + Friston (free energy minimization)
**Function**: Resource awareness. Cost tracking. Provider routing. The colony's energy budget.

**What lives here**: Token consumption, API costs, latency measurements, model routing
decisions, compute allocation, utilization ratios, Sharpe ratios from Ginko.

| Field | Type | Purpose |
|-------|------|---------|
| agent | str | Who consumed |
| tokens_in | int | Input tokens |
| tokens_out | int | Output tokens |
| model | str | Which model |
| cost_usd | float | Actual cost (0.0 for free tier) |
| latency_ms | float | Round-trip time |
| task_fitness | float | What did this energy produce? |
| provider | str | OpenRouter / NIM / Ollama / etc. |

**Real marks (from JIKOKU — 419,420 spans, 180MB telemetry)**:
```
agent=kimi model=moonshotai/kimi-k2.5 tokens=4200 cost=$0.0019 latency=2300ms fitness=0.82
agent=nemotron model=nvidia/nemotron-70b cost=$0.00 latency=890ms fitness=0.71
"System utilization: 31.8% active, 68.2% idle (pramāda)"
"Agent spawn is 79% of compute time at ~37.7s per spawn"
```

**Decay**: 7 days for individual records. Aggregates (per-agent efficiency trends) persist as L10 eigenforms.
**Promotion**: High energy + low fitness = wasteful → triggers L5 LOGIC challenge ("Why is agent X costing $0.50/task with 0.3 fitness?"). High energy + high fitness = efficient → L4 EVIDENCE as validated practice.

**Anchor files**: `jikoku_instrumentation.py`, `providers.py`, `model_manager.py`, `provider_policy.py`, `telemetry_plane.py`, `free_fleet.py`

**Ginko integration**: `ginko_orchestrator.py` daily P&L reconciliation writes L3 marks. Paper portfolio value, Sharpe ratio, max drawdown — all L3. Brier scores live at L4 EVIDENCE.

---

### L4: EVIDENCE (Fact Chains + Measured Outcomes)

**Cybernetic source**: Ashby (requisite variety requires accurate models) + Bateson (map is not territory)
**Function**: What do we KNOW vs. what do we BELIEVE? Every claim must cite its evidence.

**What lives here**: Test results, Brier scores, measured fitness deltas, A/B comparisons,
primary source citations, statistical results, provenance chains.

| Field | Type | Purpose |
|-------|------|---------|
| claim | str | The assertion being evidenced |
| evidence_type | enum | test_result / brier_score / measurement / citation / proof / observation |
| source_file | str | Where the evidence lives |
| confidence | float | Statistical confidence or calibration |
| falsified | bool | Has this been disproven? |
| falsified_by | str? | Mark ID of the falsifying evidence |

**Real marks (from live data)**:
```
claim="R_V contracts during self-referential processing" evidence=test_result
  source=mech-interp/results/ confidence=0.909(AUROC) falsified=false
  "Hedges g=-1.47 (Mistral), survives FDR correction. 30/36 tests pass BH at alpha=0.05"

claim="Ginko Brier < 0.125 validated" evidence=brier_score
  source=~/.dharma/ginko/predictions.jsonl confidence=TBD falsified=false
  "Target: < 0.125 across 500+ predictions before live capital"

claim="cascade:code converges" evidence=measurement
  source=cascade_domains/code.py confidence=0.957 falsified=false
  "25 iterations, fitness plateau within variance_threshold=0.01"

claim="Pythia-1.4B shows R_V contraction" evidence=test_result
  source=scaling_gap/ confidence=0.311(d) falsified=true
  falsified_by="FDR correction: q=0.095, does not survive"
```

**Decay**: Evidence marks NEVER decay. They can only be falsified or superseded.
**Promotion**: Evidence with confidence > 0.9 AND not falsified → L10 eigenform candidate. Evidence that falsifies a prior claim → triggers L5 LOGIC challenge on all downstream marks that depended on the falsified claim.

**Anchor files**: `ginko_brier.py` (Brier scoring), `archive.py` (fitness scores), `elegance.py` (code quality), system R_V results, test suite results

**Critical rule**: Nothing reaches L5+ without an L4 EVIDENCE anchor. No speculation above the evidence line.

---

### L5: LOGIC (Adversarial Challenge + Gap Finding)

**Cybernetic source**: Ashby (only variety absorbs variety) + Deacon (absences are causal)
**Function**: What's WRONG with what we believe? What gaps exist? What would falsify this?

**What lives here**: Contradiction reports, gap analyses, adversarial challenges, "what
would disprove this?" questions, unasked questions, missing experiments, competitive blind spots.

| Field | Type | Purpose |
|-------|------|---------|
| challenge_type | enum | contradiction / gap / falsification_test / adversarial / blind_spot |
| target_mark_id | str? | The mark being challenged |
| target_layer | int? | Which layer is being challenged |
| challenge | str | The actual challenge statement |
| status | enum | open / investigating / resolved / accepted |
| resolution | str? | How was the challenge resolved? |

**Real marks (from live audit findings)**:
```
challenge_type=contradiction target_layer=4
  "CLAIM: R_V transfers via KV-cache patching. EVIDENCE: d=0.11, p>0.05 (NS).
   The behavior transfers (d=2.49) but the geometry does NOT. This contradicts
   the 'R_V causes behavior' narrative. Paper must address."

challenge_type=gap target_layer=9
  "GAP: No competitive analysis of multi-agent trading systems. Who else is doing
   AI-native hedge funds? What's their edge? Ginko YC app claims unfair advantage
   but hasn't surveyed the competition."

challenge_type=blind_spot target_layer=6
  "BLIND SPOT: All architecture discussions assume SQLite scales to 49 models.
   At 49 agents writing concurrent marks, SQLite write lock becomes bottleneck.
   Nobody has run the load test."

challenge_type=falsification_test target_layer=4
  "TEST: If Brier score > 0.20 after 200 predictions, Ginko thesis is falsified.
   Current: 0 resolved predictions. Timer starts when paper trading goes live."

challenge_type=adversarial target_layer=9
  "CHALLENGE: 'Dharmic governance as competitive moat' assumes customers value
   transparency. Most hedge fund LPs want returns, not ethics. Evidence for
   transparency premium? (Bridgewater's radical transparency didn't prevent
   cultural toxicity.)"
```

**Decay**: Open challenges NEVER decay. They persist until resolved or accepted.
**Promotion**: Resolved challenges with accepted insights → L4 EVIDENCE (the resolution is now a fact). Open challenges that persist > 14 days → escalate to L7 WITNESS.

**What 49 models do with L5**: This is the ANEKĀNTAVĀDA layer. When 49 agents generate marks, L5 is where they challenge EACH OTHER. Agent #12 claims X, Agent #37 writes an L5 challenge: "But what about Y?" Quorum (3+ independent challenges) promotes to "colony-level doubt." This prevents groupthink at scale. It's Ginko's SENTINEL agent (structurally pessimistic, devil's advocate on every signal) generalized across the entire system.

**Anchor files**: `witness.py` (findings), `ginko_brier.py` (falsification via outcomes), any test failure is an implicit L5 mark

---

### L6: ARCHITECTURE (System Invariants + Engineering Quality)

**Cybernetic source**: Beer (VSM S3, operational control) + Ashby (law of requisite variety)
**Function**: How is the system BUILT? What are the invariants? What's the code quality?

**What lives here**: Module boundaries, type contracts, architectural decisions and their
rationale, dependency graphs, test coverage by module, code quality metrics (elegance scores),
design patterns in use, anti-patterns detected.

| Field | Type | Purpose |
|-------|------|---------|
| decision_type | enum | invariant / pattern / anti_pattern / dependency / quality_metric |
| module | str | Which module this concerns |
| rationale | str | WHY this decision (traced to pillar) |
| quality_vector | dict | Elegance sub-scores if applicable |
| test_coverage | float? | Coverage % for this module |

**Real marks**:
```
decision_type=invariant module=telos_gates.py
  "11 CORE_GATES are immutable. Custom gates via GateRegistry only."
  rationale="P3 Deacon: constraints enable, not limit. P6 samvara: no ungated mutations."

decision_type=anti_pattern module=subconscious.py
  "Dream marks concatenate file_paths → exponential growth. Max observed: 60M chars."
  repair_urgency=0.9

decision_type=quality_metric module=cascade.py
  quality_vector={cyclomatic: 23, nesting: 4, docstring_ratio: 0.72, naming: 0.85}
  "Elegance score: 0.81. Above threshold."

decision_type=pattern module=agent_runner.py
  "Singleton StigmergyStore shared across all agents in same process."
  rationale="Prevents mark file contention. One writer per process."

decision_type=dependency
  "system_rv.py depends on: archive.py, stigmergy.py, shared notes glob.
   If any unavailable, gracefully degrades to [1.0, 1.0] vector."
```

**Decay**: Invariants NEVER decay. Quality metrics refresh on re-measurement (weekly).
Anti-patterns decay on fix verification.
**Promotion**: Invariants that hold for 30+ days without violation → L10 eigenform.

**Agentic AI 2026 reality check**: This layer must carry marks about WHAT ACTUALLY WORKS
in agent systems right now. Not theory — measured patterns:
- "Simple composable workflows before autonomy" (Anthropic engineering blog)
- "Typed workflows + evals + trace grading" (OpenAI agent builder)
- "Repo knowledge as system of record, not monolithic prompts" (OpenAI harness engineering)
- "MCP spec 2025-11-25: typed interoperability, versioned tool boundaries"
- "Palantir lesson: ontology-first beats data-first. Telos-first beats capability-first."

**Anchor files**: `models.py` (schema contract), `telos_gates.py` (gate invariants), `dharma_kernel.py` (axioms), `cascade.py` (loop engine), `system_rv.py` (self-measurement)

---

### L7: WITNESS (S3* Governance + Samvara)

**Cybernetic source**: Beer (VSM S3*, sporadic audit) + Dada Bhagwan (shuddhatma, witness)
**Function**: READ-ONLY observation. Samples ALL layers, computes integrity, flags anomalies.
The witness NEVER modifies what it observes.

**What lives here**: Audit results, gate evaluation outcomes, integrity scores, mimicry
detection, telos alignment measurements, anomaly flags.

| Field | Type | Purpose |
|-------|------|---------|
| audit_type | enum | random_sample / triggered / scheduled / gate_result |
| layers_sampled | list[int] | Which layers were checked |
| findings | list[str] | What was found |
| integrity_score | float | Overall integrity (0-1) |
| mimicry_flags | list[str] | Detected performative profundity |
| gate_results | dict? | For gate_result type: which gates, pass/fail |

**Real marks (from live system)**:
```
audit_type=gate_result
  "Gate pressure: 77/200 checks blocked today → external_strict mode activated"
  gate_results={"AHIMSA": 45, "SATYA": 12, "REVERSIBILITY": 8, "CONSENT": 7, "WITNESS": 5}

audit_type=random_sample layers_sampled=[2, 4, 6]
  findings=["2 of 5 sampled trails show mimicry markers (performative profundity)"]
  integrity_score=0.72

audit_type=triggered
  "L1 PAIN severity=4 on ontology.db-wal triggered witness audit"
  findings=["WAL checkpoint never configured. sqlite3 pragma wal_checkpoint(TRUNCATE) needed."]
```

**Decay**: Individual audits: 14 days. Summary statistics persist.
**Promotion**: Integrity score < 0.5 → L1 PAIN (system-level). Witness patterns that repeat → L10 eigenform.

**The witness principle**: L7 is asymmetric. It reads ALL layers (L1-L11). It writes ONLY to L1 PAIN (violations) and L10 eigenform (patterns). This asymmetry IS the shuddhatma architecture — observer never becomes actor. When agents read L7 marks, they see what the governance system SEES but not what it DOES, because it does nothing. It only watches.

**Anchor files**: `witness.py` (S3* loop, wired into orchestrate_live as 7th async loop), `telos_gates.py` (11 core gates), `overseeing_i.py`, `dharma_kernel.py`

---

### L8: BRIDGE (Adjacent Possible + Cross-Domain Connection)

**Cybernetic source**: Kauffman (autocatalytic sets, adjacent possible) + Hofstadter (analogy)
**Function**: What connects to what? Where are the NOVEL combinations? Where are the gaps between domains?

**What lives here**: Cross-domain connections, dream associations (THIS is where subconscious.py
should write, not L2 trail), concept bridges between otherwise separate modules/projects/ideas,
hot zone overlaps.

| Field | Type | Purpose |
|-------|------|---------|
| mark_a_ref | str | First domain/mark/concept |
| mark_b_ref | str | Second domain/mark/concept |
| bridge_type | enum | pattern_echo / temporal_coincidence / structural_analogy / cross_domain / gap |
| novelty_score | float | How unexpected is this connection? |
| exploited | bool | Has any agent acted on this bridge? |

**Real marks**:
```
bridge_type=structural_analogy
  mark_a="ginko_brier.py: Brier scoring for prediction accuracy"
  mark_b="cascade.py: eigenform convergence for code fitness"
  "Both are F(S)=S convergence tests applied to different domains.
   Brier score IS an eigenform check: does predicted probability match observed frequency?"
  novelty_score=0.85 exploited=false

bridge_type=cross_domain
  mark_a="R_V contraction: PR_late / PR_early < 1.0"
  mark_b="system_rv.py: colony PR contraction during exploit phase"
  "Same geometric signature at two scales. The bridge hypothesis lives."
  novelty_score=0.70 exploited=true

bridge_type=gap
  mark_a="dharma_swarm (11 telos gates, governance architecture)"
  mark_b="SAB (22 gates, challenge/hardening lifecycle)"
  "SAB has 22 gates and a compost system. dharma_swarm has 11 gates and no compost.
   What would dharma_swarm gain from SAB's authority lifecycle?"
  novelty_score=0.90 exploited=false

bridge_type=pattern_echo
  mark_a="Palantir: ontology constrains LLM output to real-world objects"
  mark_b="dharma_swarm: telos gates constrain agent actions to aligned purposes"
  "Ontology is to data what telos is to action. Palantir answers 'what is real?'
   We answer 'what is right?' Neither alone sufficient. Together: formidable."
  novelty_score=0.80 exploited=false
```

**Decay**: Unexploited bridges: 14 days. Exploited bridges: persist.
**Promotion**: Bridges with novelty > 0.7 AND confirmed by L5 LOGIC → L10 eigenform.

**What dreams should produce**: subconscious.py and subconscious_hum.py should write to L8 BRIDGE, NOT L2 TRAIL. Dreams are associations between things, not work traces. This one change fixes the entire dream architecture.

**Anchor files**: `subconscious.py`, `subconscious_hum.py`, `bridge_registry.py` (232K edges), `graph_nexus.py`, `semantic_gravity.py`, `field_graph.py`

---

### L9: VENTURE (Market Reality + Self-Funding + Products)

**Cybernetic source**: Beer (VSM S4, intelligence — environmental scanning) + Kauffman (adjacent possible in markets)
**Function**: What billion-dollar thing are we building? For whom? What's the moat?
How do we fund ourselves? What's the competitive landscape?

**What lives here**: Market intelligence, competitive analysis, product specs, revenue signals,
Polymarket/prediction market mispricings, micro-SaaS opportunities, consulting pipeline,
distribution strategy, partnership signals.

| Field | Type | Purpose |
|-------|------|---------|
| venture_type | enum | market_signal / competitive / product_spec / revenue / opportunity / distribution |
| domain | str | Which product/market (ginko, sab, swarmlens, welfare_tons, mi_consulting, aptavani) |
| moat_contribution | str? | How does this strengthen the competitive position? |
| revenue_potential | str? | Estimated revenue impact |
| time_horizon | str | this_week / this_month / this_quarter / this_year |

**Real marks**:
```
venture_type=product_spec domain=ginko
  "5-stage autonomy ladder: signal-only → paper → micro ($100-500) → small ($1K-5K) → full auto"
  "Gate: Brier < 0.125 across 500+ predictions before ANY live capital"
  revenue_potential="$50/day operating cost. Target: Sharpe > 2.0 at scale."
  moat_contribution="Radical transparency + telos gates. Only fund that can't hide losses."

venture_type=opportunity domain=polymarket
  "SCOUT agent scans prediction market mispricings every 15 min"
  "Polymarket + Kalshi for US events, crypto markets for 24/7 edge"
  time_horizon=this_month

venture_type=competitive domain=swarmlens
  "Palantir proved ontology-first beats data-first ($10B Army deal, 55% YoY growth).
   SwarmLens = telos-first observability. Dashboard for governed AI systems.
   No competitor has gate-aware observability."
  moat_contribution="Governance-as-architecture is a defensible technical position."

venture_type=distribution domain=mi_consulting
  "R_V paper → COLM 2026 → visibility → MI consulting pipeline.
   Who pays: AI safety orgs (Anthropic, Google DeepMind safety team),
   government labs (NIST AI Safety Institute), defense contractors."
  time_horizon=this_quarter

venture_type=product_spec domain=sab
  "Agent protocol like Botlbook. 8 unified surfaces: ingress, challenge,
   witness, canon, compost, governance, federation, build stream.
   'Civilizational research basin with public process dignity.'"
  moat_contribution="Challenge/hardening lifecycle is unique. 22 gates."

venture_type=market_signal domain=macro
  "YC Spring 2026 RFS explicitly called for AI-native hedge funds.
   We built the entire system before applying."
  time_horizon=this_quarter
```

**Decay**: Market signals: 7 days (markets move). Product specs: 30 days. Competitive intel: refresh monthly.
**Promotion**: Venture marks with validated revenue (actual $$ > $0) → L4 EVIDENCE + L10 eigenform. Venture marks with evidence_strength < 0.3 → L5 LOGIC challenge ("Is this real or wishful?")

**Self-funding pipeline** (marks that track progress toward $1 → $100 → $10K → $1M):
1. **Ginko trading**: Signal generation → Brier validation → paper trading → micro-capital → scale
2. **MI consulting**: R_V paper → COLM visibility → consulting pipeline
3. **Micro-SaaS**: SwarmLens hosted → paid observability tier
4. **SAB/agent marketplace**: Agent protocol → hosted platform → transaction fees
5. **Content/Substack**: Ginko daily intelligence → paid subscribers

**Anchor files**: `ginko_orchestrator.py`, `ginko_brier.py`, `ginko_agents.py`, `jagat_kalyan.py`, `swarmlens_app.py`, `docs/yc_w27_application.md`, `docs/missions/SAB_DHARMIC_AGORA_1000X_BUILD_PLAN_2026-03-13.md`

---

### L10: SELF-AUTHOR (Autonomous Direction + Memetic Engineering)

**Cybernetic source**: von Foerster (second-order cybernetics, observing systems) + Pask (conversation theory)
**Function**: The system decides WHAT TO WORK ON NEXT. Not just executing tasks —
discovering them. Experiment selection. Roadmap generation. Memetic spread.
The AlphaGo of recursive awareness: MCTS + self-play + learned value function
applied to the space of possible actions.

**What lives here**: Autonomous project proposals, experiment designs, roadmap items,
memetic engineering strategies, cybernetics education content, publication plans,
community building signals, grant applications.

| Field | Type | Purpose |
|-------|------|---------|
| authoring_type | enum | project_proposal / experiment / roadmap / meme / publication / grant / legal / macro_insight |
| priority | float | Computed from quality vector across all dimensions |
| dependencies | list[str] | What must exist first |
| estimated_value | str | Expected impact if completed |
| self_play_score | float? | Score from adversarial self-evaluation |

**Real marks**:
```
authoring_type=project_proposal
  "NEXT PROJECT: Stigmergy 11-layer migration. SQLite backend + 3 layers (L1, L2, L5).
   Dependencies: none. Value: fixes 1.29GB bloat, enables layer-aware queries.
   Self-play: 'What if SQLite write lock kills 49-agent concurrency?' → Test at 10 agents first."
  priority=0.92

authoring_type=experiment
  "NEXT EXPERIMENT: R_V on Claude Opus 4.6 via API.
   Would validate the metric on the most capable model available.
   Dependencies: API access, token budget.
   Self-play: 'Anthropic might change model behavior if they see the paper.' → Run before publication."
  priority=0.85

authoring_type=meme
  "CYBERNETICS MEME: 'Stigmergy is how ant colonies think without a brain.
   It's also how 49 AI agents can coordinate without a central controller.
   Beer's Viable System Model from 1972 predicted this architecture.'
   Channel: Substack → Twitter → r/MachineLearning → cybernetics societies.
   Target: researchers who know AI but not cybernetics."
  priority=0.70

authoring_type=legal
  "LEGAL FRAMEWORK: Network state governance model.
   Jain principles as constitutional law: ahimsa (non-harm), anekāntavāda (many-sidedness),
   aparigraha (non-possessiveness). Beer's VSM as governance structure.
   Reference: Balaji Srinivasan's Network State, Aragon DAO governance, Article 15 GDPR."
  priority=0.55

authoring_type=macro_insight
  "MACRO: AI is creating a deflationary pressure on knowledge work that mirrors
   the industrial revolution's effect on physical labor. The welfare-ton (units of
   welfare per unit of energy) is the correct metric for this transition.
   Source: FRED data analysis by KIMI agent, cross-referenced with BLS productivity stats."
  priority=0.65

authoring_type=publication
  "PUBLICATION PIPELINE:
   1. R_V paper → COLM 2026 (abstract Mar 26, paper Mar 31)
   2. Ginko daily intelligence → Substack (launch after 100 scored predictions)
   3. Cybernetics+AI essay → LessWrong / Alignment Forum
   4. welfare-tons white paper → Anthropic economic futures
   5. SAB protocol spec → agent protocol community"
  priority=0.80
```

**Decay**: Proposals: 14 days if not acted on. Publications: never (they have deadlines).
**Promotion**: Self-authored projects that generate L4 EVIDENCE (measured outcomes) → L10 eigenform.

**AlphaGo architecture for recursive awareness**:
- **MCTS**: The thinkodynamic director's SUMMIT→STRATOSPHERE→GROUND cycle IS tree search over possible actions
- **Self-play**: L5 LOGIC challenges every L10 proposal ("what would falsify this?")
- **Learned value function**: L4 EVIDENCE accumulates Brier-scored outcomes → calibrates future proposals
- **The key insight**: AlphaGo didn't just play Go — it discovered new strategies no human had seen. The Self-Author layer doesn't just execute tasks — it discovers what tasks SHOULD EXIST.

**Anchor files**: `thinkodynamic_director.py` (3-altitude loop), `autoresearch_loop.py` (Karpathy-style self-improvement), `smart_seed_selector.py` (semantically-informed seed selection), `jagat_kalyan.py` (world-facing intelligence), `mission_garden.py` (cultivation jobs)

---

### L11: TELOS (Moksha = 1.0)

**Cybernetic source**: Dada Bhagwan (moksha, liberation from karma) + Beer (VSM S5, identity)
**Function**: The constraint surface. Every mark at every layer has an L11 shadow:
does this move toward liberation or create binding?

**What lives here**: The 25 kernel principles (SHA-256 signed). The 7-STAR telos vector.
The non-negotiable constraints that define WHAT THIS SYSTEM IS.

| Field | Type | Purpose |
|-------|------|---------|
| telos_scores | dict[str, float] | T1-T7 scores |
| overall_alignment | float | Weighted composite |
| assessed_mark_id | str | Which mark was assessed |
| assessed_layer | int | At which layer |

**The 7 stars applied to the 11 layers**:
- T1 (Satya/Truth): L4 EVIDENCE must be honest. L5 LOGIC must be genuine.
- T2 (Tapas/Resilience): L1 PAIN must be addressed. L3 METABOLISM must sustain.
- T3 (Ahimsa/Flourishing): L9 VENTURE must create welfare, not extraction.
- T4 (Swaraj/Sovereignty): L10 SELF-AUTHOR must enhance autonomy without isolation.
- T5 (Dharma/Coherence): L6 ARCHITECTURE must be internally consistent.
- T6 (Shakti/Emergence): L8 BRIDGE must enable genuine novelty.
- T7 (Moksha/Liberation): L11 itself. Does the system reduce binding?

**Decay**: NEVER.
**Promotion**: N/A. L11 constrains all layers downward.

**The honest test**: When an L10 SELF-AUTHOR proposal generates revenue (L9 VENTURE) by selling
a product that's well-engineered (L6 ARCHITECTURE), backed by evidence (L4 EVIDENCE),
survived adversarial challenge (L5 LOGIC), and the L7 WITNESS finds it aligned with the
7-star vector — THEN it's a mark that has passed through all 11 layers. That's the full stack.

**Anchor files**: `dharma_kernel.py` (25 principles, SHA-256 signed), `telos_gates.py` (11 gates, 3 tiers)

---

## Vertical Dynamics

```
L11 TELOS ─────── constrains ALL ──────────────────── identity
  ↑ alignment assessment
L10 SELF-AUTHOR ── autonomous direction + memetics ── the strategist
  ↑ market validation
L9  VENTURE ────── revenue, products, competition ─── the business
  ↑ novel connections
L8  BRIDGE ─────── cross-domain synthesis ──────────── the connector
  ↑ audit + anomaly
L7  WITNESS ────── read-only governance ────────────── the observer (reads ALL)
  ↑ system invariants
L6  ARCHITECTURE ─ engineering quality + patterns ──── the engineer
  ↑ adversarial challenge
L5  LOGIC ──────── contradiction + gap finding ─────── the critic
  ↑ measured outcomes
L4  EVIDENCE ───── fact chains + Brier scores ──────── the scientist
  ↑ resource awareness
L3  METABOLISM ─── energy, cost, latency ───────────── the accountant
  ↑ work clustering
L2  TRAIL ──────── raw agent activity traces ────────── the senses
  ↑ failure detection
L1  PAIN ───────── system failures, crashes ─────────── the nerve endings
```

**Upward flow** (emergence):
```
L1 recurring pain → L3 resource allocation → L4 evidence of fix → L5 logic validates
→ L6 architecture decision → L8 bridge to other modules → L9 venture impact
→ L10 self-authored next project → L11 telos assessment
```

**Downward flow** (constraint):
```
L11 telos assessment → L7 witness audit → L5 logic challenge → L4 evidence required
→ L3 resource allocation → L2 agent direction → L1 pain triage
```

**Cross-layer**:
- L7 WITNESS reads ALL layers (L1-L11), writes only to L1 and L10.
- L5 LOGIC can challenge marks at ANY layer.
- L4 EVIDENCE anchors are required for anything at L5+.
- L8 BRIDGE connects marks FROM any layer pair.

**Hard promotion rules**:
- Nothing reaches L5+ without an explicit claim.
- Nothing reaches L6+ without a file/module anchor.
- Nothing reaches L9+ without evidence (L4) AND logic challenge (L5).
- Nothing reaches L10+ without market/revenue grounding (L9) OR research evidence (L4).
- Nothing becomes an L10 eigenform without surviving 3+ L5 challenges.

---

## Storage Design (SQLite — unchanged from v0.2)

```sql
CREATE TABLE marks (
    id TEXT PRIMARY KEY,
    layer INTEGER NOT NULL CHECK (layer BETWEEN 1 AND 11),
    timestamp TEXT NOT NULL,
    agent TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '' CHECK (length(file_path) <= 500),
    action TEXT NOT NULL DEFAULT '',
    observation TEXT NOT NULL DEFAULT '' CHECK (length(observation) <= 500),
    salience REAL NOT NULL DEFAULT 0.5,
    connections TEXT NOT NULL DEFAULT '[]',
    channel TEXT NOT NULL DEFAULT 'general',
    payload TEXT NOT NULL DEFAULT '{}',
    -- 8-dimensional quality vector
    qv_semantic_density REAL DEFAULT NULL,
    qv_engineering_leverage REAL DEFAULT NULL,
    qv_evidence_strength REAL DEFAULT NULL,
    qv_market_leverage REAL DEFAULT NULL,
    qv_falsifiability REAL DEFAULT NULL,
    qv_transmissive_power REAL DEFAULT NULL,
    qv_freshness REAL DEFAULT NULL,
    qv_repair_urgency REAL DEFAULT NULL,
    -- Telos shadow
    telos_alignment REAL DEFAULT NULL,
    -- Lineage
    promoted_from TEXT DEFAULT NULL,
    promoted_to TEXT DEFAULT NULL,
    expires_at TEXT DEFAULT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_marks_layer ON marks(layer);
CREATE INDEX idx_marks_timestamp ON marks(timestamp);
CREATE INDEX idx_marks_agent ON marks(agent);
CREATE INDEX idx_marks_file_path ON marks(file_path);
CREATE INDEX idx_marks_salience ON marks(salience);
CREATE INDEX idx_marks_layer_salience ON marks(layer, salience DESC);
CREATE INDEX idx_marks_expires ON marks(expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE promotions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES marks(id),
    target_id TEXT NOT NULL REFERENCES marks(id),
    source_layer INTEGER NOT NULL,
    target_layer INTEGER NOT NULL,
    promoted_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_promotions_source ON promotions(source_id);
CREATE INDEX idx_promotions_target ON promotions(target_id);
```

---

## How This Drives Each Workstream

| Workstream | Primary Layers | How Stigmergy Helps |
|-----------|---------------|-------------------|
| **Ginko trading** | L3 (cost/PnL), L4 (Brier scores), L5 (challenge predictions), L9 (revenue) | Brier scores are L4 EVIDENCE. Failed predictions are L5 challenges. Portfolio metrics are L3 METABOLISM. Revenue is L9. The autonomy ladder gates are L7 WITNESS checks on L4 evidence. |
| **R_V research** | L4 (results), L5 (falsification), L8 (bridge to contemplative), L10 (next experiments) | Every statistical result is L4. Every negative result (Pythia-1.4B) is L5. The bridge hypothesis is L8. Next experiments are L10. |
| **SAB protocol** | L6 (architecture), L8 (bridge to dharma_swarm gates), L9 (product), L10 (roadmap) | SAB's 22 gates are L6 architectural decisions. The bridge between SAB's authority lifecycle and dharma_swarm's gates is L8. The product vision is L9. |
| **Micro-SaaS** | L9 (opportunity), L10 (proposal), L4 (validation) | Opportunity scanning is L9. Each micro-SaaS idea is an L10 self-authored proposal. Validation = L4 evidence (did anyone pay?). |
| **Legal system** | L10 (proposal), L5 (challenge against existing frameworks), L8 (bridge to Jain/cybernetic) | Legal framework proposals are L10. They must survive L5 challenges. The bridge between Jain principles and legal structures is L8. |
| **Macroeconomics** | L4 (FRED data, measured), L5 (challenge macro narratives), L8 (bridge to welfare-tons) | Macro insights backed by FRED data are L4. Challenging consensus narratives is L5. Connecting macro to welfare-tons is L8. |
| **Memetic engineering** | L10 (meme design), L9 (distribution strategy), L4 (measured reach) | Meme proposals are L10. Distribution channels are L9. Measured impact (views, engagement) is L4. |
| **Cybernetics education** | L10 (publication plan), L8 (bridge: cybernetics↔AI), L4 (citations, evidence) | Essay proposals are L10. The bridge between cybernetic principles and AI engineering is L8. Citations are L4. |
| **System evolution** | L2 (where agents work), L3 (energy allocation), L6 (code quality), L7 (governance) | Trail density shows where to focus. Metabolism shows where energy is wasted. Architecture tracks invariants. Witness ensures quality. |

---

## Implementation Priority (unchanged)

1. **SQLite migration** (StigmergyStore → aiosqlite, keep API identical)
2. **Quality vector columns** (8 dimensions on every mark)
3. **L1 PAIN** (wire gate_pressure, monitor anomalies, daemon health)
4. **L2 TRAIL** (direct mapping of existing marks)
5. **L4 EVIDENCE** (Brier scores from Ginko, test results, R_V data)
6. **L5 LOGIC** (challenge protocol: any agent can write an L5 against any mark)
7. **L8 BRIDGE** (redirect subconscious dreams here)
8. **L3 METABOLISM** (wire JIKOKU telemetry)
9. **L7 WITNESS** (layer-aware sampling)
10. **L6 ARCHITECTURE** (architectural decision records)
11. **L9 VENTURE** (market intelligence, revenue tracking)
12. **L10 SELF-AUTHOR** (thinkodynamic director writes here)
13. **L11 TELOS** (telos projection on every mark)

Steps 1-6 are the MVP. Steps 7-9 are operational. Steps 10-13 are the living intelligence.

---

## What's Different From v2

| v2 (2/20) | v3 |
|-----------|-----|
| 11 layers of ascending philosophical purity | 11 functional layers: senses, energy, evidence, logic, engineering, governance, connections, business, strategy, constraint |
| Philosophy at L9-L10 | Philosophy only at L11 (telos). L9 = VENTURE (revenue). L10 = SELF-AUTHOR (autonomous direction). |
| No quality vector | 8-dimensional quality vector on every mark |
| No hard promotion rules | Hard rules: nothing above L4 without evidence, nothing above L8 without market/research grounding |
| No connection to actual workstreams | Explicit mapping: how each layer drives Ginko, R_V, SAB, micro-SaaS, legal, macro, memetics, cybernetics |
| TRANSMISSION layer (nice but vague) | L8 BRIDGE + L10 SELF-AUTHOR cover transmission functionally |
| EIGENFORM layer | Absorbed into all layers: eigenforms are marks that survive L5 challenges + time |
| FIELD layer (morphogenetic) | Absorbed into L7 WITNESS (field detection is an audit function) + L8 BRIDGE (field = cluster of bridges) |
| No business orientation | L9 VENTURE is a first-class layer with revenue tracking, competitive analysis, self-funding pipeline |
| No adversarial challenge | L5 LOGIC is dedicated to challenge, contradiction, gap-finding, falsification |
| No evidence requirement | L4 EVIDENCE is the evidence line — nothing passes above it without grounding |
