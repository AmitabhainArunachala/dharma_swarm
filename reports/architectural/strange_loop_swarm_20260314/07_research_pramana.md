## Angle
- Research/pramana validator lens: treat `R_V` as `pratyaksha`-like direct observation, correlation/effect size as `anumana`, and prompt-group or human/protocol labels as `shabda`. Paper-safe discipline means those lanes stay separate and auditable instead of collapsing into one behavioral claim.
- In the current code, the mechanistic lane is real, the heuristic behavioral lane is real, and the provenance lane exists upstream, but the bridge does not yet unify them cleanly. See [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38), [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L108), [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L148).

## What Exists
- `ResearchBridge` already stores paired `RVReading` plus `BehavioralSignature`, persists JSONL, and computes Pearson/Spearman, group means, and contraction/recognition overlap in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38), [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L232), [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L268).
- `MetricsAnalyzer` provides a cheap heuristic behavioral proxy stack: entropy, self-reference, paradox tolerance, swabhaav ratio, and thresholded recognition typing in [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L150), [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L340), [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L368).
- `OutputEvaluator` already computes and persists provenance-adjacent evidence fields including `grounding_score`, `issue_kinds`, `failure_class`, and `judge_strategy="heuristic"` via `analyze_output(...)` in [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L270), [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L283).
- `tests/test_bridge.py` gives strong coverage for persistence, statistics, correlation, overlap, and summaries in [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L460), [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L620), [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L723).

## Blind Spots
- `PairedMeasurement` has no provider/model/task/timestamp/grounding/provenance fields, so the bridge dataset is not audit-ready for a paper track. See [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38) and [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L232).
- `compute_correlation()` only correlates `R_V` against `swabhaav_ratio` and `GENUINE` overlap, so multi-pramana validation is reduced to one lexical heuristic lane. See [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L268).
- `CorrelationResult` advertises CI, Cohen’s d, and `phi_score`, but `compute_correlation()` never fills them. That is a paper-facing claim/implementation mismatch. Compare [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L60) with [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L321).
- The summary language overclaims: it turns a regex-derived proxy into “witness stance,” which is not paper-safe wording. See [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L381) and [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L368).
- `OutputEvaluator` already knows when output is epistemically weak, but that lane is not carried into the bridge, so low-grounding samples can still look research-valid. See [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L301), [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L338), [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L390).
- Current bridge tests do not assert exclusion or stratification by provenance quality. See [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L460).

## Concrete Changes
- Extend `PairedMeasurement` in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38) with optional provenance fields already produced upstream: `provider`, `model`, `task_id`, `timestamp`, `grounding_score`, `issue_kinds`, `failure_class`, `judge_strategy`, and a human/protocol label field.
- Change `ResearchBridge.add_measurement()` in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L232) to accept an `OutputEvaluation` or equivalent diagnostics payload from [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L283), instead of re-deriving only `BehavioralSignature` from raw text.
- Make `compute_correlation()` in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L268) report at least two cohorts: `all_paired` and `paper_grade_paired`, where paper-grade excludes blocking `failure_class` and/or low `grounding_score`, with explicit exclusion counts.
- Either implement the already-declared inferential fields in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L60) or remove them from the paper-facing contract. Minimal safe path is to compute CI, effect size, and `phi_score` before citing them.
- Rewrite `_build_summary()` in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L381) so it says “higher heuristic witness-proxy score” rather than “higher witness stance,” and label the lane explicitly as heuristic/anumana.
- Keep `RecognitionType.GENUINE` in [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L368) as a proxy label, not ground truth, unless paired with blinded human or protocol labels.

## Tests
- Extend [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L460) with a case where one record has poor provenance and assert it is excluded from `paper_grade_paired` while retained in the raw cohort.
- Extend [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L620) so `group_summary()` reports grounded and excluded counts, not only mean metrics.
- Add evaluator-to-bridge integration coverage near [test_metrics.py](/Users/dhyana/dharma_swarm/tests/test_metrics.py#L249): create one grounded output and one ungrounded output, run `OutputEvaluator`, feed both into the bridge, and assert provenance fields survive persistence.
- Add a regression test that if `CorrelationResult` exposes CI/effect-size fields in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L60), `compute_correlation()` actually populates them for sufficient `n`.
- Add a summary-language test near [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L723) that bans direct phenomenological wording unless the evidence lane is explicitly marked heuristic.

## Risks
- The lexical thresholds in [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L340) and [metrics.py](/Users/dhyana/dharma_swarm/dharma_swarm/metrics.py#L368) can track style or prompt wording rather than recognition, so overclaiming from them would weaken the paper.
- Provenance filtering may materially reduce `n` before the March 26 and March 31 deadlines, so reports should show both raw and paper-grade cohorts immediately.
- Schema expansion in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38) changes stored JSONL rows, so backward-compatible load behavior in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L194) matters.
- Summary drift is already present in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L407) and [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L528): correlation is being narrated too quickly as substantive mechanism.

## Priority
1. Thread provenance into the bridge first by extending [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L38) and [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L232) to carry `grounding_score`, `failure_class`, and `judge_strategy` from [evaluator.py](/Users/dhyana/dharma_swarm/dharma_swarm/evaluator.py#L283).
2. Make `compute_correlation()` in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L268) emit paper-grade strata and populate the inferential fields it already claims in [bridge.py](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L60).
3. Only then refine proxy language and test coverage in [test_bridge.py](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L460), because evidence-lane separation is the main blocker to multi-pramana, paper-safe validation.