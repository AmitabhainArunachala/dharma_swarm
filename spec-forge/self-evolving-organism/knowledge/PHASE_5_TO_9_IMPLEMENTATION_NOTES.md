# PHASE 5 TO 9 IMPLEMENTATION NOTES

## Phase 5 Notes

- Favor optional import guards for `nevergrad` and `textgrad`.
- The bridge should operate on runtime-field names and values, not raw code patches.
- `research_reward_to_fitness(...)` already exists. Reuse it.
- `EvolutionArchive` already knows how to store fitness-bearing entries.
- `DarwinEngine` is large. Add a narrow entrypoint instead of threading optimizer logic everywhere at once.

## Phase 6 Notes

- `workflow.py` already has a successful pattern: `execute_auto_research_workflow(...)`.
- `TopologyGenome` should compile into that style of workflow execution, not invent a new executor.
- `orchestrator.py` still expects `TopologyType`. Preserve that path.

## Phase 7 Notes

- Curriculum objects should feel like proposals or seeds, not a shadow task board.
- `agent_registry.py` is a safe persistence seam for new JSONL-style frontier artifacts if needed.
- Use `RewardSignal`, contradictions, and stale capability evidence as inputs.

## Phase 8 Notes

- `agent_export.py` is intentionally pure today. Keep it that way.
- `agent_install.py` may perform side effects, but it should support dry-run planning first.

## Phase 9 Notes

- The offline bridge should export manifests and bundle paths.
- It must not import or invoke live training frameworks on the main execution path.

## Same-Instance Advice

Even though this handoff goes to the same instance lineage:

- reload the canonical spec before each phase
- inspect the currently implemented files before adding new ones
- prefer small red/green loops over giant mixed patches
