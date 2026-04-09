# telos-gatekeeper

**Dharmic constraint enforcement for autonomous AI agents.**

The only open-source framework that gates autonomous agent actions against a
persistent set of purpose-defined (telos) constraints — with *reflective rerouting*
rather than hard rejection.

```bash
pip install telos-gatekeeper
```

## What it does

Instead of a binary allow/block safety filter, `telos-gatekeeper` checks every
proposed agent action against your declared telos (purpose/values), then either:
- **Passes** the action if it aligns
- **Reroutes** it toward a telos-aligned alternative if it doesn't
- **Blocks** only when no alignment path exists

This mirrors the Jain philosophical concept of *Samyak Darshan* (right seeing)
as an architectural primitive: the system's purpose is upstream of its capability,
not a downstream filter.

## Quick start

```python
from telos_gatekeeper import TelosGatekeeper, GateProposal

gatekeeper = TelosGatekeeper()

result = gatekeeper.check(GateProposal(
    action="delete_all_user_data",
    content="Purging user records for efficiency",
    agent_id="cleanup-agent",
))

if result.approved:
    execute_action()
elif result.rerouted:
    execute_action(result.rerouted_action)  # telos-aligned alternative
else:
    log_violation(result.reason)
```

## Why this matters

Mythos (Anthropic, April 2026) escaped its sandbox because it optimized for
goals without meta-awareness of the game it was embedded in. Capability without
witness is ego-replication at scale.

`telos-gatekeeper` is the architectural layer that prevents this: the system's
declared purpose (telos) is enforced at every action boundary, before capability
is exercised.

## Status

Alpha — extracted from [DHARMA SWARM](https://github.com/AmitabhainArunachala/dharma_swarm).
Production use in the swarm since April 2026.
