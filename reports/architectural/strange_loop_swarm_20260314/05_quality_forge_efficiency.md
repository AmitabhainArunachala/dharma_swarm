## Angle
- Treat the current forge as a heat engine: optimize `marginal_quality_gain / marginal_cost`, not raw cycle count. The useful signals already exist in [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L290), [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L147), [elegance.py](/Users/dhyana/dharma_swarm/dharma_swarm/elegance.py#L323), and [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L69).
- The missing move is closure: the system can score artifacts, but the forge does not yet score its own interventions or decide when more work is thermodynamically wasteful.

## What Exists
- [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L441) already runs a weakest-link loop: scan, pick lowest dimension, generate one task, persist cycle state.
- [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L175) already computes `quality_score`, and [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L185) already computes a cost-normalized `efficiency`.
- [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L427) and [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L446) already aggregate by agent and model, so self-scoring infrastructure exists.
- [elegance.py](/Users/dhyana/dharma_swarm/dharma_swarm/elegance.py#L270) and [elegance.py](/Users/dhyana/dharma_swarm/dharma_swarm/elegance.py#L323) already expose structural before/after scoring for code changes.
- [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L69) already logs spend by `task_id`, `agent_name`, model, and tokens.
- Nearby stop thresholds already exist in [iteration_depth.py](/Users/dhyana/dharma_swarm/dharma_swarm/iteration_depth.py#L33), [iteration_depth.py](/Users/dhyana/dharma_swarm/dharma_swarm/iteration_depth.py#L118), and [iteration_depth.py](/Users/dhyana/dharma_swarm/dharma_swarm/iteration_depth.py#L125), but Foreman does not consult them.

## Blind Spots
- No self-scoring loop: [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L484) generates tasks and [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L560) records build results, but neither is passed through [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L283).
- No unified efficiency ledger: [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L292) accepts caller-supplied `estimated_cost_usd`, while [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L69) logs spend separately.
- Efficiency is biased for zero or unknown cost: [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L22) marks several models as `0.0`, while [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L185) divides by `max(cost, 0.001)`, so missing accounting can look artificially efficient.
- No stop condition in the forge: [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L462) always scans and [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L495) keeps queue/build behavior active even if quality is already high, the same weakness repeats, or gains flatten.
- Model ranking is quality-first, not efficiency-first, in [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L444) and [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L465).

## Concrete Changes
- Extend [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L430) instead of adding a new runtime file: add `quality_delta`, `cycle_cost_usd`, `cycle_tokens`, `thermo_efficiency`, and `stop_reason` to `CycleReport` and `project_result`.
- Add `def _compute_cycle_thermo(previous: ProjectEntry | None, dims: dict[str, float], *, cost_entries: list[CostEntry]) -> dict[str, float]:` in [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L441) to compute `avg_quality_delta`, `weakest_delta`, and `quality_gain_per_dollar`.
- Add `def _should_stop_project(project: ProjectEntry, initiative: Initiative | None, thermo: dict[str, float], weakest: str) -> tuple[bool, str]:` in [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L441). Stop reasons should include `already_shippable`, `plateaued`, `cost_ceiling_exceeded`, and `same_weakest_dimension_stalled`.
- Wire Foreman into its own judge: after task generation and after build, create a synthetic `Task` and run [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L283) on the generated task/report text.
- Use [elegance.py](/Users/dhyana/dharma_swarm/dharma_swarm/elegance.py#L323) as the structural gain term in build mode so quality improvement is not reduced to test/doc coverage alone.
- Make [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L147) cost-aware instead of cost-tolerant: add `cost_source`, and exclude `efficiency` from rankings when cost is unknown or zero-estimated.
- Extend [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L100) with `def summarize_costs(*, task_id: str | None = None, agent_name: str | None = None, since_hours: float = 24.0) -> dict[str, float]:` so Foreman can consume per-cycle spend directly.
- No new production module is justified before these extensions.

## Tests
- Extend [tests/test_foreman.py](/Users/dhyana/dharma_swarm/tests/test_foreman.py#L351) with `test_run_cycle_records_quality_delta_and_thermo_efficiency`, `test_run_cycle_stops_when_initiative_is_shippable`, and `test_run_cycle_stops_after_plateau_on_same_weakest_dimension`.
- Add [tests/test_evaluator.py](/Users/dhyana/dharma_swarm/tests/test_evaluator.py) with `test_efficiency_is_none_when_cost_basis_unknown`, `test_zero_cost_models_do_not_dominate_efficiency`, and `test_leaderboard_can_rank_by_efficiency_when_present`.
- Add [tests/test_cost_tracker.py](/Users/dhyana/dharma_swarm/tests/test_cost_tracker.py) with `test_summarize_costs_filters_by_task_id`, `test_summarize_costs_aggregates_tokens_and_usd`, and `test_estimate_cost_unknown_model_does_not_break_accounting`.
- Keep [tests/test_elegance.py](/Users/dhyana/dharma_swarm/tests/test_elegance.py#L252) as the unit anchor for before/after delta, and add one Foreman integration assertion that `elegance_delta` affects stop or continue decisions.
- Current evaluator coverage is indirect through [tests/test_monitor.py](/Users/dhyana/dharma_swarm/tests/test_monitor.py#L277) and [tests/test_cli.py](/Users/dhyana/dharma_swarm/tests/test_cli.py#L323), which is not enough for stop-logic changes.

## Risks
- Plateau detection can stop too early because the five current Foreman dimensions under-measure some real improvements.
- Self-scoring can become theater if it grades prose without binding that score to repo deltas and test outcomes.
- Cost accounting remains noisy while model-rate tables are heuristic and some providers are marked `0.0`.
- Extra judge passes can themselves waste budget; self-scoring should run on meaningful state changes, not every observe tick.

## Priority
- 1. Extend [foreman.py](/Users/dhyana/dharma_swarm/dharma_swarm/foreman.py#L441) to compute `quality_delta`, consult [iteration_depth.py](/Users/dhyana/dharma_swarm/dharma_swarm/iteration_depth.py#L118), and emit `stop_reason`.
- 2. Unify [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L147) and [cost_tracker.py](/Users/dhyana/dharma_swarm/dharma_swarm/cost_tracker.py#L69) so efficiency has a single cost ledger.
- 3. Add self-scoring of generated tasks and build summaries, then feed [elegance.py](/Users/dhyana/dharma_swarm/dharma_swarm/elegance.py#L323) into marginal-gain calculations.
- 4. Only after those three are in place, consider new loop abstractions.