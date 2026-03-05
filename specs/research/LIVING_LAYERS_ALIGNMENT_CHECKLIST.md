# Living Layers Alignment Checklist

Use this checklist to keep implementation aligned with the research corpus in `specs/research/`.

## Canonical references
- `research_subconscious_ai.md`
- `research_stigmergy_agents.md`
- `research_shakti_creative_autonomy.md`

## v1.1 alignment targets
- **Stigmergy substrate exists**
  - `dharma_swarm/stigmergy.py` provides append/read/hot-path/decay behavior.
  - Tests: `tests/test_stigmergy.py`.
- **Subconscious association loop exists**
  - `dharma_swarm/subconscious.py` provides dream trigger, association scoring, and recent dream retrieval.
  - Tests: `tests/test_subconscious.py`.
- **Shakti proactive perception exists**
  - `dharma_swarm/shakti.py` provides perception classification and propose/escalate flow.
  - Tests: `tests/test_shakti.py`.

## Known v2 gaps (from build report)
- Inject SHAKTI perception hook into `context.py` for all worker prompts.
- Wire startup crew with dedicated Shakti agents in `startup_crew.py`.
- Add daemon-triggered subconscious wake cycle based on stigmergy density.
- Auto-create stigmergic marks for all file reads/writes.
- Improve policy specificity and conflict-resolution heuristics.

## Regression checks after each wave
1. Run: `python3 -m pytest tests/test_stigmergy.py tests/test_shakti.py tests/test_subconscious.py -q`
2. Run: `python3 test_full_loop.py`
3. Confirm no split-brain:
   - `python3 -m dharma_swarm.dgc_cli runtime`
   - `python3 -m dharma_swarm.dgc_cli truth`

## Review cadence
- On each major merge, update this checklist with:
  - what was implemented,
  - what remains,
  - and which research claims were concretely operationalized.
