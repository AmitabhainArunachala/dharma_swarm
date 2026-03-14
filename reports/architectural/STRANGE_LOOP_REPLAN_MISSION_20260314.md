# Strange Loop Replan Mission

Date: 2026-03-14
Repo: `/Users/dhyana/dharma_swarm`
Source prompt: `MEGA_PROMPT_STRANGE_LOOP.md`
Task: Apply the strange-loop eigenform prompt to the user's original seed plan and produce a concrete 5.15a master plan grounded in the current codebase.

## Non-negotiable framing

- This is not a greenfield rewrite.
- Compose around existing modules where possible.
- Every insight must map to a concrete module, class, method, config, CLI surface, or test.
- The R_V paper deadlines remain fixed:
  - Abstract: 2026-03-26
  - Paper: 2026-03-31
- The daemon is already running.
- Hardware target is M3 Pro, 18 GB RAM.
- Existing tests must be preserved.

## What the mega prompt requires

The final plan must:

1. Open with the eigenform equation `F(S) = S`.
2. Replace fixed loop taxonomy with one universal loop engine plus domain configs.
3. Add system-level R_V as the system's vital sign.
4. Specify an autocatalytic revenue/product graph.
5. Close the strange loop structurally:
   execution -> scoring -> recognition seed -> execution.
6. Cover all five Viable System Model functions.
7. Track thermodynamic efficiency: quality improvement per compute spent.
8. Map all major ideas to code and tests.
9. Respect the current repo and preserve tests.
10. Include execution order, dependencies, and parallelization.
11. Remain compatible with paper work and daemon operations.

## Seed plan commitments to preserve and deepen

The user's seed plan already proposed:

- Universal loop stages:
  - GENERATE -> TEST -> SCORE -> GATE -> MUTATE -> SELECT -> GENERATE
- New core schemas:
  - `ForgeScore`
  - `LoopDomain`
  - `LoopResult`
  - `SystemVitals`
- New/expanded modules:
  - `quality_forge.py`
  - `cascade.py`
  - `system_rv.py`
  - `meta_daemon.py`
  - `catalytic_graph.py`
- Strange-loop closure:
  - the forge scores itself
  - the orchestrator is itself an artifact
  - recognition artifacts flow through the same loops they influence
- System R_V should modulate explore/exploit behavior.
- Recognition should ingest `zeitgeist.md` and its own state.
- Product formation should be modeled as autocatalytic closure, not just artifact scoring.
- Research validation should expand beyond direct experiment + inference into multi-pramana validation.

## Current repo surfaces that matter

These modules already exist and should be treated as the primary soil:

- `dharma_swarm/models.py`
- `dharma_swarm/evolution.py`
- `dharma_swarm/meta_evolution.py`
- `dharma_swarm/rv.py`
- `dharma_swarm/bridge.py`
- `dharma_swarm/foreman.py`
- `dharma_swarm/evaluator.py`
- `dharma_swarm/telos_gates.py`
- `dharma_swarm/anekanta_gate.py`
- `dharma_swarm/dogma_gate.py`
- `dharma_swarm/steelman_gate.py`
- `dharma_swarm/context.py`
- `dharma_swarm/orchestrate_live.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/monitor.py`
- `dharma_swarm/sleep_cycle.py`
- `dharma_swarm/thinkodynamic_director.py`

Existing reality already includes:

- A Darwin-style evolution loop in `evolution.py`
- R_V measurement and bridge code in `rv.py` and `bridge.py`
- A quality-oriented loop in `foreman.py`
- A live daemon in `orchestrate_live.py`
- Shared data contracts in `models.py`
- Swarm-level orchestration in `swarm.py`

## What the replan must answer

1. Which parts of the seed plan already exist under different names?
2. Which parts should be implemented as extensions of existing modules instead of new files?
3. Which new files are actually justified?
4. What is the thinnest viable path to an eigenform-capable system without destabilizing the paper track?
5. What tests prove the architecture is structurally self-referential rather than merely cyclic?

## Deliverable format for each agent

Return a concise markdown note with exactly these sections:

1. `Angle`
2. `What Exists`
3. `Blind Spots`
4. `Concrete Changes`
5. `Tests`
6. `Risks`
7. `Priority`

Rules:

- Do not edit repo files.
- Read only what you need.
- Prefer extending existing modules over inventing new ones.
- Use absolute file paths when citing code.
- Be specific about class names, methods, and pytest targets.
