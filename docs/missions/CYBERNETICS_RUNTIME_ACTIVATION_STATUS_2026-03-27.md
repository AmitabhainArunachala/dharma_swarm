# Cybernetics Runtime Activation Status

Date: 2026-03-27
Status: live but early

## What is now real

- A persistent four-seat cybernetics roster exists in the live swarm:
  - `cyber-glm5` -> `glm-5:cloud`
  - `cyber-kimi25` -> `kimi-k2.5:cloud`
  - `cyber-codex` -> `qwen3-coder:480b-cloud`
  - `cyber-opus` -> `deepseek-v3.2:cloud`
- Cybernetics workflows now prefer `provider-fallback` with `available_provider_types=["ollama"]`.
- The startup path spawns the cybernetics seats as part of the live swarm.
- The directive task board has been rebound so new cyber work prefers the cyber seats.

## What changed in code

- `dharma_swarm/startup_crew.py`
  - switched the cybernetics crew to Ollama Cloud models
- `dharma_swarm/thinkodynamic_director.py`
  - added cybernetics-specific backend and provider routing
- `scripts/onboard_cybernetics_stewards.py`
  - re-onboards the cyber seats onto Ollama Cloud
- `scripts/rebind_cybernetics_directive.py`
  - rebinds active directive tasks to the new routing

## Runtime evidence

- `~/.dharma/shared/cybernetics_stewards_latest.json`
- `~/.dharma/shared/cybernetics_directive_rebind_latest.json`
- `~/.dharma/logs/daemon.log`

The daemon log shows the seats being spawned on Ollama:

- `Spawned cybernetics seat cyber-glm5 (researcher) on ollama [cybernetics]`
- `Spawned cybernetics seat cyber-kimi25 (cartographer) on ollama [cybernetics]`
- `Spawned cybernetics seat cyber-codex (surgeon) on ollama [cybernetics]`
- `Spawned cybernetics seat cyber-opus (architect) on ollama [cybernetics]`

## Honest status

This is not a fully mature subsystem yet.

- The seat identity layer is live.
- The routing layer is live.
- The harness layer is live.
- The runtime layer has dispatched real cyber work.
- The completion closeout path is still fragile; one dispatched task stalled in `running` after dispatch and had to be closed manually.

## Next bounded move

Seed the first population cycle so cybernetics stops being only a routing story and starts becoming a living knowledge-to-runtime loop:

1. build the canon packet
2. produce a stratified extraction
3. ingest claims, citations, and contradictions
4. force one transmission vector into code
5. audit metabolism and reroute

This keeps the next cycle bounded, auditable, and attached to runtime rather than theory accumulation.
