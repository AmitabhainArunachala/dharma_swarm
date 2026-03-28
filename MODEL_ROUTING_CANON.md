# Model Routing Canon

This is the single story for model and provider selection in `dharma_swarm`.

## Source Of Truth

- Provider lanes, default models, and paid/free ordering live in [model_hierarchy.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_hierarchy.py).
- Live free-tier OpenRouter rosters live in [free_fleet.py](/Users/dhyana/dharma_swarm/dharma_swarm/free_fleet.py).
- Human-friendly selectors such as `top open models` and `tier one models` live in [model_catalog.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_catalog.py).
- Routing execution still lives in [provider_policy.py](/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py) and [providers.py](/Users/dhyana/dharma_swarm/dharma_swarm/providers.py).

## Canonical Selectors

- `top_open_models`
  Open-model lanes across the shared router.
- `driver_models`
  Primary driver lanes for sovereign execution and escalation.
- `free_models`
  All currently discovered free OpenRouter models.
- `tier1_models`
  Heavy free reasoning models.
- `tier2_models`
  General-purpose free models.
- `tier3_models`
  Fast/light free models.

Natural aliases are supported:

- `top open models`
- `free models`
- `tier one models`
- `tier1`

## Runtime Contract

Use the selector metadata instead of hand-rolled provider allowlists:

```python
metadata = {
    "model_catalog_selector": "top open models",
}
```

That expands into the routing keys the runtime already understands:

- `allow_provider_routing`
- `available_provider_types`
- `preferred_provider`
- `preferred_model`

This expansion is now honored in:

- [swarm.py](/Users/dhyana/dharma_swarm/dharma_swarm/swarm.py)
- [agent_runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/agent_runner.py)
- [worker_spawn.py](/Users/dhyana/dharma_swarm/dharma_swarm/worker_spawn.py)

## Inspection

```bash
dgc model-catalog
dgc model-catalog "top open models"
dgc model-catalog "tier one models" --json
```

## Mental Model

1. Human or spec chooses a canonical selector.
2. [model_catalog.py](/Users/dhyana/dharma_swarm/dharma_swarm/model_catalog.py) resolves it into routing metadata.
3. Agent and worker execution honor that metadata through the shared router.
4. [provider_policy.py](/Users/dhyana/dharma_swarm/dharma_swarm/provider_policy.py) and [providers.py](/Users/dhyana/dharma_swarm/dharma_swarm/providers.py) still make the final path decision, but they now start from one shared vocabulary instead of ad hoc lists.
