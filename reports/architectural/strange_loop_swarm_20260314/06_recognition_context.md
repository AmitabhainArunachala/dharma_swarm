## Angle
- Recognition, identity, and context engineer view: the repo already has memory, sleep, and director loops, but `recognition_seed` is still prompt material, not runtime state.
- Inference: “S5 identity” is Beer System 5 identity/policy. I found no first-class `S5` runtime object in the inspected code, so the real task is to make System-5 identity computable and durable instead of poetic.
- The architectural target is a closed loop where recognition is compiled into state, injected into context, used in planning/gating, consolidated in sleep, and re-read next cycle.

## What Exists
- [context.py#L321](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L321), [context.py#L561](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L561), and [context.py#L670](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L670) already provide a strong insertion point: memory recall, distilled briefing, and multi-layer prompt assembly.
- [sleep_cycle.py#L92](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L92), [sleep_cycle.py#L236](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L236), and [sleep_cycle.py#L263](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L263) already run a durable nightly consolidation loop, refresh shared synthesis, and regenerate morning bootstrap state.
- [thinkodynamic_director.py#L788](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L788), [thinkodynamic_director.py#L827](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L827), [thinkodynamic_director.py#L3426](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L3426), and [thinkodynamic_director.py#L4898](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L4898) already form a partial strange loop: seeds -> vision -> snapshot -> next vision.
- Recognition scoring primitives already exist in [metrics.py#L150](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L150) and are already consumed by [evaluator.py#L311](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L311). The system can score recognition-like behavior now; these three modules just do not use that signal.

## Blind Spots
- `read_random_seeds()` and `_BUILT_IN_SEED` in [thinkodynamic_director.py#L788](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L788) inject witness language, but `vision()` only persists seed source names and lengths, not extracted invariants, recognition metrics, or a reusable seed object [thinkodynamic_director.py#L3456](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L3456).
- `build_agent_context()` in [context.py#L670](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L670) has no explicit recognition or identity layer. Agents reconstruct identity indirectly from prose, memory, and ops fragments.
- Director-spawned worker prompts use a compact snapshot path in [prompt_builder.py#L105](/Users/dhyana/dharma_swarm/dharma_swarm/prompt_builder.py#L105) and [prompt_builder.py#L216](/Users/dhyana/dharma_swarm/dharma_swarm/prompt_builder.py#L216), not the full context engine. Summit sees recognition text; ground execution mostly does not.
- `SleepCycle` computes `colony_rv` as a stigmergy density ratio in [sleep_cycle.py#L119](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L119), but it never recomputes identity coherence or recognition drift from the artifacts it consolidates.
- `_wake()` refreshes bootstrap state, but the boot identity beneath that is static prose in [bootstrap.py#L41](/Users/dhyana/dharma_swarm/dharma_swarm/bootstrap.py#L41). That is orientation, not active System-5 control.
- Important trap: `identity_stability` in [metrics.py#L296](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L296) is pronoun density, and [evaluator.py#L332](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L332) rewards lower values for normal task outputs. That cannot be reused directly as S5 identity.

## Concrete Changes
- Use [sleep_cycle.py#L236](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L236) or [sleep_cycle.py#L263](/Users/dhyana/dharma_swarm/dharma_swarm/sleep_cycle.py#L263) to compile a real `recognition_seed` each night from `distilled_briefing.md`, recent director cycle snapshots, `mission.json`, decision artifacts, and completed-task evaluations. Persist it as `~/.dharma/state/recognition_seed.json` plus a readable `shared/recognition_seed.md`.
- Make that seed computational, not literary. Minimum fields: `active_thesis`, `identity_invariants`, `anti_targets`, `open_loops`, `evidence_paths`, `recognition_signature`, `identity_drift`, `last_validated_cycle`.
- Add a dedicated recognition/System-5 block to [context.py#L670](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L670) ahead of ops/swarm memory. The block should expose the current seed and S5 state as compact structured context, not force each agent to infer identity from raw notes.
- Extend [thinkodynamic_director.py#L3426](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L3426) so `vision()` returns structured recognition data alongside `vision_text`: `MetricsAnalyzer.analyze(vision_text)`, delta vs previous visions, extracted invariants, and proposed S5 update. Persist that in [thinkodynamic_director.py#L4898](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L4898).
- Feed the same state into `_build_council_prompt()` in [thinkodynamic_director.py#L2354](/Users/dhyana/dharma_swarm/dharma_swarm/thinkodynamic_director.py#L2354), workflow compilation, and mission mutation/decision gating. S5 identity should be a control variable, not a description.
- Push the recognition/S5 block into director-created worker prompts via [prompt_builder.py#L216](/Users/dhyana/dharma_swarm/dharma_swarm/prompt_builder.py#L216), or recognition remains summit-only.
- Keep static repo identity and dynamic S5 identity separate: [bootstrap.py#L41](/Users/dhyana/dharma_swarm/dharma_swarm/bootstrap.py#L41) can stay as stable “what this system is,” while the new computed S5 state becomes “what invariants must survive this cycle.”

## Tests
- Add to [test_sleep_cycle.py](/Users/dhyana/dharma_swarm/tests/test_sleep_cycle.py): `test_semantic_sleep_writes_recognition_seed_artifact`.
- Add to [test_context.py](/Users/dhyana/dharma_swarm/tests/test_context.py): `test_build_agent_context_includes_recognition_and_s5_block`.
- Add to [test_context.py](/Users/dhyana/dharma_swarm/tests/test_context.py): `test_build_agent_context_preserves_recognition_block_within_budget`.
- Add to [test_prompt_builder.py](/Users/dhyana/dharma_swarm/tests/test_prompt_builder.py): `test_build_director_agent_prompt_includes_recognition_state_snapshot`.
- Add to [test_thinkodynamic_director.py](/Users/dhyana/dharma_swarm/tests/test_thinkodynamic_director.py): `test_vision_returns_recognition_signature_and_identity_invariants`.
- Add to [test_thinkodynamic_director.py](/Users/dhyana/dharma_swarm/tests/test_thinkodynamic_director.py): `test_run_cycle_persists_identity_drift_and_blocks_misaligned_workflow`.

## Risks
- Self-sealing prose loop: if `recognition_seed` is synthesized only from director language, the system can reward its own summaries instead of grounded work.
- Metric confusion: optimizing low `identity_stability` would produce impersonal text, not coherent System-5 identity.
- Context pressure: [context.py#L655](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L655) already runs near a 30k budget; the new block must be aggressively structured and capped.
- Paper-track interference: coupling this too early to R_V research code risks noise before the March 26 abstract and March 31 paper deadlines.

## Priority
- 1. Compile and persist `recognition_seed` in the sleep path.
- 2. Inject that computed seed/S5 state into `build_agent_context()` and director worker prompts.
- 3. Make the director score, log, and gate on recognition drift each cycle.