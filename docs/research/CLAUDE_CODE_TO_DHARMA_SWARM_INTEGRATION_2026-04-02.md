---
title: Claude Code to Dharma Swarm Integration
path: docs/research/CLAUDE_CODE_TO_DHARMA_SWARM_INTEGRATION_2026-04-02.md
slug: claude-code-to-dharma-swarm-integration-2026-04-02
doc_type: research
status: working
summary: Deep-read synthesis of the local Claude Code decompilation and source, mapped onto dharma_swarm's current architecture with a safe adoption plan focused on verification, resumability, bounded background cognition, and operator-visible governance.
source:
  provenance: repo_local_plus_local_external_corpus
  kind: synthesis
  origin_signals:
  - /tmp/alanisme-claude-code-decompiled/docs/en/06-agent-loop-deep-dive.md
  - /tmp/alanisme-claude-code-decompiled/docs/en/11-context-window-management.md
  - /tmp/alanisme-claude-code-decompiled/docs/en/15-memory-and-instruction-system.md
  - /tmp/alanisme-claude-code-decompiled/docs/en/16-transcripts-compaction-and-session-resume.md
  - /tmp/collection-claude-code-source-code/claude-code-source-code/src/services/autoDream/autoDream.ts
  - /tmp/collection-claude-code-source-code/claude-code-source-code/src/constants/prompts.ts
  cited_urls: []
  generated_hint: codex_agent_authored
disciplines:
- multi_agent_systems
- software_architecture
- verification
- memory_systems
- control_planes
- operator_runtime
inspiration:
- verification
- autonomy
- memory
- durable_execution
- operator_visibility
---
# Claude Code to Dharma Swarm Integration

## Executive Thesis

The strongest lessons from the local Claude Code corpus are not its hidden features or internal-only flags. The durable value is architectural:

1. one hot-path query loop owns long-running state transitions
2. verification is a hard gate, not a personality trait
3. memory is explicitly split into instruction, durable fact, and session continuity layers
4. compaction and resume are treated as storage semantics, not UI sugar
5. autonomy is bounded by visible circuit breakers and operator-facing control points

`dharma_swarm` already contains many of the right components for this. The gap is less "missing concepts" than "insufficiently unified execution path."

The 10x move is therefore:

Build a single verified, resumable, operator-visible control loop that pulls together the existing director, overnight/autonomous runners, verification gates, hibernation, and memory layers instead of letting them remain partially parallel subsystems.

## What From Claude Code Actually Matters

### 1. Verification as a separate authority

The highest-signal Claude finding is the internal verification contract in `src/constants/prompts.ts`: non-trivial work must pass an independent verifier before completion is reported.

That is valuable because it solves a specific failure mode:

- implementer optimism
- false-success reporting
- silent test omission
- self-judged completion

This maps directly onto `dharma_swarm`'s existing strengths:

- `dharma_swarm/agent_runner_quality.py`
- `dharma_swarm/quality_gates.py`
- `dharma_swarm/gaia_verification.py`
- `dharma_swarm/loop_supervisor.py`
- `dharma_swarm/claude_hooks.py`

Current state: strong gate vocabulary, but not one canonical verifier lane across all non-trivial autonomous work.

Recommendation:

- Introduce one runtime-wide `verification lane` contract.
- Require independent verification for bounded classes of work:
  - 3+ file edits
  - backend or API changes
  - infra or daemon changes
  - any unattended overnight change
- Make the reporter unable to self-assign `PASS`.
- Persist verifier evidence as structured artifacts, not prose only.

### 2. Session continuity as a first-class storage problem

Claude Code treats compact boundaries, sidechains, and resume semantics as part of transcript storage, not just chat UX.

This matters because long-lived agents degrade when:

- old state is summarized but boundaries are not tracked
- wait states lose provenance
- resumed jobs do not know what continuity contract they inherited

Relevant `dharma_swarm` seams already exist:

- `dharma_swarm/hibernation.py`
- `dharma_swarm/mission_contract.py`
- `dharma_swarm/codex_overnight.py`
- `dharma_swarm/conversation_store.py`
- `dharma_swarm/swarm.py`

Current state:

- hibernation is substantially real
- mission continuity exists
- session digest persistence exists
- `conversation_store.py` is still a placeholder

Recommendation:

- Replace the placeholder conversation store with a canonical session ledger.
- Store explicit boundary events:
  - mission start
  - mission replan
  - compaction/consolidation
  - hibernate
  - ready_to_resume
  - resume
  - verification verdict
- Make all overnight and director loops resume from this ledger, not from ad hoc file probes.

### 3. Memory layer separation

Claude Code's best memory idea is not "memory exists." It is the separation:

- instruction overlay
- durable working memory
- session memory for continuity/compaction

`dharma_swarm` already has analogous pieces:

- instruction/governance: `CLAUDE.md`, `daemon_config.py`, telos gates
- durable memory: `memory.py`, `agent_memory_manager.py`
- session digest: `swarm.py` session memory facts
- consolidation: `consolidation.py`, `neural_consolidator.py`

Current state: the pieces exist, but they are not yet one clear hierarchy.

Recommendation:

- Formalize three explicit memory classes:
  - `InstructionMemory`: behavioral constitution, policy, operator intent
  - `DurableMemory`: validated facts, artifacts, decisions, verified lessons
  - `SessionContinuityMemory`: compact recent state for resume/autonomy
- Ban raw session residue from polluting instruction memory.
- Ban unverified claims from promotion into durable memory.
- Make consolidation update continuity memory first, durable memory second, instruction memory almost never.

### 4. Bounded background cognition

Claude Code's `autoDream` is valuable because it is gated cheaply and defensively:

- 24h time gate by default
- 5+ session gate
- lock gate
- skip current session
- read-only exploration constraints

This maps well to:

- `dharma_swarm/consolidation.py`
- `dharma_swarm/neural_consolidator.py`
- `dharma_swarm/meta_daemon.py`
- `dharma_swarm/deep_reading_daemon.py`
- `dharma_swarm/codex_overnight.py`

Current state: `dharma_swarm` has richer background cognition ideas than Claude Code, but less disciplined gating.

Recommendation:

- Standardize all background jobs behind one scheduler contract:
  - time gate
  - work-accumulation gate
  - exclusive lock
  - operator pause override
  - verification requirement for any state-changing output
- Treat `autoDream` as a design pattern, not a feature to clone.
- First apply it to memory consolidation and overnight summarization, not autonomous code mutation.

### 5. Prompt/cache boundary discipline

Claude Code's `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` is not interesting because of Anthropic-specific caching. It is interesting because it enforces a clean architectural split:

- static behavioral substrate
- dynamic session-specific state

This applies directly to `dharma_swarm` prompt construction:

- `dharma_swarm/prompt_builder.py`
- `dharma_swarm/claude_hooks.py`
- `dharma_swarm/thinkodynamic_director.py`

Recommendation:

- Split prompt assembly into:
  - static constitution
  - mission/runtime state
  - ephemeral task-local evidence
- Cache and test them separately.
- Do not let dynamic operator state mutate the constitution layer.

## Where These Ideas Best Apply In Dharma Swarm

### Primary application zone: runtime control plane

Best-fit modules:

- `dharma_swarm/swarm.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/codex_overnight.py`
- `dharma_swarm/loop_supervisor.py`
- `dharma_swarm/hibernation.py`
- `dharma_swarm/mission_contract.py`

Why:

This is where autonomous action, mission continuity, verification, and operator trust either cohere or fall apart.

### Secondary application zone: memory and consolidation stack

Best-fit modules:

- `dharma_swarm/memory.py`
- `dharma_swarm/agent_memory_manager.py`
- `dharma_swarm/consolidation.py`
- `dharma_swarm/neural_consolidator.py`
- `dharma_swarm/meta_daemon.py`

Why:

This is where `dharma_swarm` can surpass Claude Code, but only if consolidation becomes operationally bounded and linked to runtime continuity instead of remaining mostly philosophical richness.

### Third application zone: operator harness and IDE bridge

Best-fit modules:

- `dharma_swarm/claude_hooks.py`
- `dharma_swarm/adaptive_autonomy.py`
- `dharma_swarm/daemon_config.py`

Why:

This is where user trust is won or lost. If the system acts in the background, the human must be able to see why, pause it, inspect it, and recover from it.

## Where Not To Copy Claude Code

### Do not copy hidden/internal product asymmetries

The internal-only features are mostly useful as diagnostics of what Anthropic needed to patch for itself. They are not a product strategy for `dharma_swarm`.

Avoid copying:

- hidden user-tier asymmetry
- silent feature gating without operator visibility
- remote behavior changes without local audit
- autonomy that changes based on opaque server flags

`dharma_swarm` should do the opposite:

- local-first visibility
- explicit control-plane state
- durable audit trail
- operator-readable reasons for autonomy changes

### Do not copy KAIROS first

KAIROS is impressive but dangerous to imitate early.

For `dharma_swarm`, "always-on autonomous coding that commits independently" is not the first 10x.
The first 10x is:

- bounded overnight execution
- resumable wait states
- independent verification
- visible control state
- safe memory consolidation

KAIROS-like autonomy should come only after those are solid.

## Safe Integration Plan

### Phase 1: Canonical verification lane

Goal:
Every non-trivial autonomous change routes through one independent verifier before completion is reported.

Build:

- a `VerificationLane` abstraction wrapping:
  - `agent_runner_quality.py`
  - `quality_gates.py`
  - focused shell/test checks
  - artifactized evidence
- policy thresholds in config
- explicit verdicts: `PASS`, `PARTIAL`, `FAIL`

Success condition:

No unattended run can claim completion without a verifier artifact.

### Phase 2: Session ledger and resume contract

Goal:
Unify `mission`, `hibernation`, `overnight`, and `director` continuity.

Build:

- real `conversation_store.py` or adjacent `session_ledger.py`
- boundary event schema
- resume loader used by:
  - overnight supervisor
  - director startup
  - hibernation wake path

Success condition:

The system can stop, compact/consolidate, and resume without ambiguous authority.

### Phase 3: Background cognition scheduler

Goal:
Make background memory/consolidation tasks cheap, bounded, and visible.

Build:

- one scheduler policy for:
  - `consolidation.py`
  - `neural_consolidator.py`
  - `meta_daemon.py`
  - `deep_reading_daemon.py`
- standard gates:
  - time
  - accumulated work
  - exclusive lock
  - pause file
  - quiet hours
  - verification for write effects

Success condition:

Background jobs produce compounding memory value without stealth mutation or runaway churn.

### Phase 4: Prompt/state split

Goal:
Reduce prompt sprawl and prevent policy/session mixing.

Build:

- explicit static constitution section
- dynamic mission state section
- ephemeral evidence packet section
- tests that verify layer boundaries

Success condition:

Prompt changes become reviewable as architecture, not just string editing.

### Phase 5: Operator-visible autonomy control plane

Goal:
Make every autonomy escalation visible and reversible.

Build:

- current mode
- why the mode changed
- what gates are active
- what jobs are hibernating
- what is ready to resume
- what background tasks are running
- what verifier status is pending

Success condition:

The operator can answer "what is the system doing and why?" in one screen.

## Concrete 10x Recommendations

If only five things get built, they should be:

1. `verification lane` hard gate for all non-trivial unattended work
2. canonical `session ledger` for compact/hibernate/resume continuity
3. unified `background cognition scheduler` with cheap gates and locks
4. strict `memory layer split` with promotion rules
5. operator-visible `autonomy state panel`

Those five changes would compound across nearly every active `dharma_swarm` surface.

## Highest-Leverage Existing Dharma Swarm Assets

These are already stronger or more ambitious than the Claude Code corpus and should be preserved:

- `hibernation.py`: explicit wait/resume lifecycle
- `loop_supervisor.py`: cheap non-LLM watchdog logic
- `adaptive_autonomy.py`: explicit risk-based autonomy reasoning
- `mission_contract.py`: campaign-state formalization
- `consolidation.py` and `neural_consolidator.py`: richer theory of self-modification
- `thinkodynamic_director.py`: higher-order mission selection and altitude shifts

The right move is to harden and connect these, not replace them.

## Bottom Line

Claude Code's decompiled corpus confirms that serious agent systems become valuable when they are:

- verified
- resumable
- layered in memory
- bounded in background activity
- explicit about control state

`dharma_swarm` already has unusually strong raw material for all five.
Its main gap is architectural integration.

If the system unifies its current verification, continuity, memory, and autonomy modules into one visible control plane, it does not merely copy Claude Code. It surpasses it in philosophical coherence and system self-knowledge while matching the production lessons that actually matter.
