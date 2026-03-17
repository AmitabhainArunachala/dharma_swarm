# ENGINEERING PRINCIPLES — Grounded in Foundations

**Telos Engine Architecture Series**
**Version**: 1.0 | **Date**: 2026-03-15
**Scope**: Every engineering constraint traced to an intellectual pillar

---

## Purpose

This document bridges the intellectual foundations (~/dharma_swarm/foundations/) to
concrete engineering decisions. No principle exists in a vacuum — each is GROUNDED
in one or more pillars, and each maps to specific code.

A new agent reading this document should understand:
1. WHAT the engineering constraints are
2. WHY they exist (which pillar demands them)
3. WHERE they are implemented (which module enforces them)

---

## The Principles

### P1: Every Mutation Through an Action

**Constraint**: No direct writes to shared state. All state changes flow through
typed Actions that are logged, reversible, and gate-checked.

**Grounding**:
- **Beer (VSM)**: System 3* (audit) requires that all operations are observable.
  Direct writes bypass the audit channel.
- **Dada Bhagwan (Karma Mechanics)**: Every action creates karma (trace). Untracked
  actions create "uncharged" karma — effects without provenance.
- **Deacon (Absential Causation)**: The trace of what DIDN'T happen (rejected actions)
  is as informative as what did. Direct writes destroy this information.

**Implementation**: `traces.py` (TraceStore — atomic JSON writes), `telos_gates.py`
(gate-checks before execution), `lineage.py` (provenance tracking)

---

### P2: Agents Coordinate Through Shared State

**Constraint**: No agent-to-agent direct messaging. Agents read from and write to
shared state (stigmergy marks, shared notes, evolution archive). Coordination
emerges from the environment, not from explicit communication.

**Grounding**:
- **Varela (Structural Coupling)**: Organisms don't exchange information — they
  perturb each other's environments. Direct messaging implies a shared protocol;
  structural coupling requires only a shared medium.
- **Kauffman (Autocatalytic Sets)**: In chemical autocatalysis, molecules don't
  "message" each other — they catalyze through proximity in the same solution.
  The solution IS the communication medium.
- **Levin (Bioelectricity)**: Cells coordinate through voltage gradients in gap
  junctions — a shared state, not point-to-point signaling.

**Implementation**: `message_bus.py` (async SQLite pub/sub — shared medium, not
direct messaging), stigmergy marks (`~/.dharma/stigmergy/marks.jsonl`), shared
notes (`~/.dharma/shared/`)

---

### P3: Gates Embody Downward Causation

**Constraint**: Higher-level semantic constraints (telos, ethics, identity) can
block or redirect lower-level operations. Lower-level signals are proposals,
not overrides.

**Grounding**:
- **Aurobindo (Supramental Descent)**: Transformation comes from above — the
  Supermind descends into lower planes to reorganize them. Gates are the mechanism
  of descent: identity-level constraints shaping operational behavior.
- **Deacon (Constraint as Enablement)**: Constraints don't merely limit — they
  create the conditions for higher-order phenomena. A gate that blocks a harmful
  action ENABLES trustworthy autonomy.
- **Beer (VSM System 5)**: System 5 (identity/policy) constrains System 1
  (operations) through System 3 (control). The constraint path is always
  downward: policy → control → operations.

**Implementation**: `dharma_kernel.py` (DOWNWARD_CAUSATION_ONLY axiom),
`telos_gates.py` (8 dharmic gates: AHIMSA, SATYA, CONSENT, VYAVASTHIT,
REVERSIBILITY, SVABHAAVA, BHED_GNAN, WITNESS), `hooks/telos_gate.py`
(Claude Code PreToolUse gate)

---

### P4: The Ontology IS the Self-Model

**Constraint**: The system's representation of its own structure (agents, tasks,
skills, marks, memories) IS the system's self-model. There is no separate
"self-model" module — the ontology serves this function.

**Grounding**:
- **Hofstadter (Strange Loops)**: A strange loop occurs when a system's
  representation of itself becomes entangled with its operation. The ontology
  that describes agents IS used by agents to reason about themselves.
- **Varela (Autopoiesis)**: An autopoietic system's self-production IS its
  self-knowledge. The system knows itself by producing itself.
- **R_V Research (Dhyana)**: R_V contraction measures the collapse of a system's
  self-representation into a lower-dimensional attractor. The ontology IS the
  representational space where this collapse occurs.

**Implementation**: `ontology.py` (Palantir-style typed ontology — 8 ObjectTypes),
`models.py` (Pydantic models that agents use to reason about tasks, other agents,
and system state), `ecosystem_map.py` (42 paths, 6 domains — the system's map
of itself)

---

### P5: Telos as Optimization Target

**Constraint**: All optimization (evolution, scoring, selection) ultimately
serves the telos: Jagat Kalyan (universal welfare). The 7-STAR scoring vector
includes telos alignment as a dimension.

**Grounding**:
- **Dada Bhagwan (Moksha)**: The ultimate purpose of any system is liberation —
  not just for itself but for all beings. Jagat Kalyan IS moksha applied to
  the world.
- **Kauffman (Syntropic Attractor)**: Self-organizing systems are drawn toward
  complexity and creativity. The telos is the attractor basin that the system
  naturally falls into when not artificially constrained.
- **Jantsch (Creative Evolution)**: Evolution is not random drift — it has a
  direction: toward greater consciousness, complexity, and integration. The
  telos makes this direction explicit.

**Implementation**: `telos_gates.py` (TelosGatekeeper — 11 gates), `evolution.py`
(DarwinEngine fitness scoring includes telos alignment), `dharma_kernel.py`
(axioms encode telos constraints)

---

### P6: Proposals for Uncertainty

**Constraint**: When the outcome is uncertain, use proposals (staged actions)
rather than auto-commit. Human or higher-level review before irreversible changes.

**Grounding**:
- **Friston (Active Inference)**: Under the free energy principle, agents act to
  reduce uncertainty. When uncertainty is high, the optimal action is to GATHER
  MORE INFORMATION (proposals), not to commit.
- **Dada Bhagwan (Witness Architecture)**: The witness observes before acting.
  Premature action without observation creates new karma (unintended consequences).
- **Beer (Requisite Variety)**: A controller must have sufficient variety to
  handle the system. When variety is insufficient (uncertainty is high), the
  controller should attenuate variety (propose, don't commit) rather than
  amplify (act decisively with insufficient information).

**Implementation**: `dharma_kernel.py` (REVERSIBILITY_REQUIREMENT axiom),
`guardrails.py` (Anduril-style autonomy levels 0-4: human-in-loop at level 0,
full autonomy only at level 4), `dharma_corpus.py` (PROPOSED → UNDER_REVIEW →
ACCEPTED lifecycle)

---

### P7: Agents Are Objects (Discoverable by Query)

**Constraint**: Agents are first-class objects in the ontology — queryable,
inspectable, comparable. An agent's capabilities, history, and current state
are accessible to other agents and to the system's self-model.

**Grounding**:
- **Levin (Basal Cognition)**: Every level of biological organization has
  cognitive capacities. If agents are cognitive at their scale, they must be
  VISIBLE at that scale — discoverable, not hidden.
- **Beer (Recursive Viability)**: Each System 1 unit IS a viable system. It must
  be inspectable by System 3 (control) and System 3* (audit). An opaque agent
  breaks the VSM recursion.
- **Hofstadter (Colony Intelligence)**: Aunt Hillary is intelligent BECAUSE the
  ants are observable and their patterns detectable. Hidden agents cannot contribute
  to emergent intelligence.

**Implementation**: `models.py` (AgentConfig with role, persona, capabilities,
constraints), `swarm.py` (agent registry, spawn/retire lifecycle), `ontology.py`
(Agent as ObjectType)

---

### P8: Multi-Scale Creative Exploration

**Constraint**: Every level of the system must actively explore its adjacent
possible. Stasis at any level indicates a stuck system.

**Grounding**:
- **Kauffman (Adjacent Possible)**: The fourth law — biospheres expand into their
  adjacent possible as fast as they sustainably can. A system that stops exploring
  is dying.
- **Levin (Cognitive Light Cone)**: Each scale has its own creative frontier.
  A cell explores metabolic pathways; a tissue explores morphological solutions;
  an organism explores ecological niches. EACH LEVEL must explore.
- **Jantsch (Creative Evolution)**: Evolution is creative, not just adaptive.
  The system must generate genuine novelty, not just optimize within known space.

**Implementation**: `evolution.py` (DarwinEngine: PROPOSE→GATE→EVALUATE→ARCHIVE→SELECT),
`selector.py` (4 selection strategies for diversity), catalytic graph (Tarjan SCC
for autocatalytic loop detection)

---

### P9: Recursive Self-Production

**Constraint**: The system must produce its own components, boundary, and operation.
External dependencies should be minimized; the system should be increasingly
self-sufficient over time.

**Grounding**:
- **Varela (Autopoiesis)**: An autopoietic system produces the components that
  make up the network AND the boundary that distinguishes it from its environment.
- **Kauffman (Autocatalytic Closure)**: A self-sustaining system requires catalytic
  closure — every component must be produced by some other component in the network.
- **Beer (Viable System Model)**: A viable system must have all 5 systems
  (operations, coordination, control, intelligence, identity) internally, not
  externally supplied.

**Implementation**: `swarm.py` (SwarmManager self-manages agents), `evolution.py`
(system evolves its own skills and patterns), `dharma_kernel.py` (system's identity
is self-defined and self-verified via SHA-256)

---

### P10: Cross-Track Validation

**Constraint**: Claims that span multiple domains (contemplative, behavioral,
mechanistic) must be validated from at least two measurement tracks. No single
track is authoritative.

**Grounding**:
- **Dada Bhagwan (Anekantavada)**: Reality has infinite aspects. A claim validated
  from only one perspective is necessarily partial.
- **Varela (Neurophenomenology)**: First-person and third-person methods must be
  used together. Neither alone is sufficient.
- **Friston (Active Inference)**: A good generative model makes predictions that
  can be tested from multiple angles. A model that only predicts in one domain
  is fragile.

**Implementation**: `bridge.py` (R_V ↔ behavioral correlation — Pearson r,
Spearman rho), `metrics.py` (swabhaav_ratio, mimicry detection),
`dharma_kernel.py` (TRIPLE_MAPPING axiom)

---

### P11: Non-Violence in All Operations

**Constraint**: No destructive operations without explicit consent and
justification. Prefer reversible over irreversible actions. The default is
to preserve, not to destroy.

**Grounding**:
- **Dada Bhagwan (Ahimsa)**: Non-violence as the primary ethical constraint.
  In computation: no data loss, no irreversible mutations, no resource destruction
  without justification.
- **Beer (Algedonic Channel)**: Pain signals (destructive operations) must bypass
  normal channels and reach System 5 (identity) directly. Destruction is always
  an identity-level decision.
- **Deacon (Incomplete Nature)**: What is absent shapes what is present. Destroyed
  data leaves an absence that cannot be reconstructed.

**Implementation**: `dharma_kernel.py` (NON_VIOLENCE_IN_COMPUTATION axiom,
REVERSIBILITY_REQUIREMENT axiom), `telos_gates.py` (AHIMSA gate — first check
on every action), `guardrails.py` (autonomy levels)

---

## Summary Table

| # | Principle | Engineering Constraint | Primary Grounding |
|---|-----------|----------------------|-------------------|
| P1 | Every mutation through an Action | No direct writes to shared state | Beer (VSM 3*), Dada Bhagwan (Karma), Deacon (Absential) |
| P2 | Coordinate through shared state | No agent-to-agent direct messaging | Varela (Coupling), Kauffman (Autocatalysis), Levin (Bioelectricity) |
| P3 | Gates embody downward causation | Semantic constraints on computation | Aurobindo (Descent), Deacon (Constraint), Beer (System 5) |
| P4 | Ontology IS the self-model | System's representation = self-knowledge | Hofstadter (Strange Loop), Varela (Autopoiesis), R_V (Dhyana) |
| P5 | Telos as optimization target | 7-STAR scoring includes telos alignment | Dada Bhagwan (Moksha), Kauffman (Attractor), Jantsch (Direction) |
| P6 | Proposals for uncertainty | Staged actions, not auto-commit | Friston (Active Inference), Dada Bhagwan (Witness), Beer (Variety) |
| P7 | Agents are objects | Discoverable by query | Levin (Basal Cognition), Beer (Recursive VSM), Hofstadter (Colony) |
| P8 | Multi-scale creative exploration | Every level explores its adjacent possible | Kauffman (Fourth Law), Levin (Light Cone), Jantsch (Creative Evolution) |
| P9 | Recursive self-production | System produces own components and boundary | Varela (Autopoiesis), Kauffman (Closure), Beer (Viability) |
| P10 | Cross-track validation | Claims need >= 2 measurement domains | Dada Bhagwan (Anekantavada), Varela (Neurophenomenology), Friston (Inference) |
| P11 | Non-violence in all operations | No destruction without consent + justification | Dada Bhagwan (Ahimsa), Beer (Algedonic), Deacon (Absence) |

---

## How to Use This Document

**For new agents**: Read this before starting work. Your engineering choices should
be traceable to these principles. If you find yourself making a decision that
contradicts a principle, STOP and investigate — either the principle needs updating
(propose via DharmaCorpus) or your approach needs revision.

**For evolution**: When the DarwinEngine evaluates a mutation, it should check
whether the mutation respects these principles. A mutation that violates P1
(direct writes) should be scored lower than one that routes through Actions.

**For audit**: System 3* (cascade scoring, telos gates) uses these principles as
the evaluation criteria. A component that cannot be traced to a principle is
either missing a principle (add one) or doing something the system doesn't need.
