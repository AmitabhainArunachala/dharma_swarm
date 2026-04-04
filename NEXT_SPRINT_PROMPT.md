# DHARMA SWARM — Sprint 2: Identity Unification + Loop Closure Verification

## Prerequisites

Sprint 1 (Bootstrap) must be complete:
- All 9 fixes from INTERFACE_MISMATCH_MAP.md applied and marked RESOLVED
- `dgc organism-pulse --dry-run` shows at least one invariant above 0.0000
- At least one task has completed end-to-end (check: `dgc status` → Tasks Completed > 0)

If Sprint 1 is NOT complete, stop. Go back to the bootstrap prompt and finish it first.

## Required Reading (in this order)

1. `CLAUDE.md` — system genome + links to all maps
2. `INTERFACE_MISMATCH_MAP.md` — verify all 9 entries are marked RESOLVED
3. `MODEL_ROUTING_MAP.md` — understand the 5 inconsistencies between calling surfaces
4. `AGENT_IDENTITY_UNIFICATION.md` — **this is your work order for this sprint**
5. `CYBERNETIC_LOOP_MAP.md` — understand which loops should close after your changes
6. `tests/test_bootstrap_loops.py` — the verification harness for loop closure

## Mission 1: Unify Agent Identity (from AGENT_IDENTITY_UNIFICATION.md)

Follow the Migration Plan exactly:

### Step 1: Add unified AgentIdentity to models.py
Add the Pydantic model from Section 2 of AGENT_IDENTITY_UNIFICATION.md. Include the model_validator for legacy string coercion.

### Step 2: Migrate startup_crew.py
Replace crew dicts with AgentIdentity instances. The crew definition should look like:
```python
AgentIdentity(name="cartographer", role=AgentRole.CARTOGRAPHER, ...)
```
Not:
```python
{"name": "cartographer", "role": AgentRole.CARTOGRAPHER, ...}
```

### Step 3: Migrate persistent_agent.py
Change `__init__` to accept `identity: AgentIdentity` instead of individual fields.

### Step 4: Migrate autonomous_agent.py
Delete the local AgentIdentity dataclass. Import from models.py instead.

### Step 5: Migrate profiles.py
AgentProfile should extend AgentIdentity (or contain it). Remove duplicate fields.

### Step 6: Migrate conductors.py
Replace hardcoded `ProviderType.ANTHROPIC` with provider fallback chain from runtime_provider.py.

### Step 7: Migrate api/routers/agents.py
Construct AgentOut from AgentIdentity instead of parsing properties dicts.

**After each step:** Run `python -m pytest tests/ -q --tb=short -x` to verify nothing broke.

## Mission 2: Verify Loop Closure

After identity unification, run the loop verification tests:

```bash
python -m pytest tests/test_bootstrap_loops.py -v
```

All 14 tests should pass. If any fail, fix the root cause (don't mock around it).

Then run the manual verification from CYBERNETIC_LOOP_MAP.md:

```bash
dgc status           # Tasks Completed > 0?
dgc organism-pulse --dry-run  # criticality > 0? closure > 0?
dgc evolve trend     # fitness entries?
dgc memory           # memory entries > 0?
dgc loops            # signal bus status?
ls ~/.dharma/witness/ # witness logs exist?
```

## Mission 3: Close Loop 5 (Zeitgeist → Telos Gates feedback)

This is the easiest loop to close after bootstrap because it only needs local file access:

1. Verify ZeitgeistScanner._scan_local() can read witness logs from ~/.dharma/witness/
2. Verify that when high gate block rates are detected, gate_pressure.json is written
3. Verify that telos_gates reads gate_pressure.json on next check and adjusts strictness
4. Run `dgc organism-pulse --dry-run` and verify the closure invariant increased

## Rules

1. Read the file before editing it. Always.
2. One migration step at a time. Test after each.
3. Do not create new files except tests.
4. Do not rename, refactor, or "improve" anything not in the migration plan.
5. Update AGENT_IDENTITY_UNIFICATION.md after each step — mark it DONE with commit hash.
6. Update CYBERNETIC_LOOP_MAP.md — change loop status from NO to YES as each loop verifies.

## Commit Convention

```
fix(identity-N): <what was migrated>

Part of Sprint 2: Agent Identity Unification
See AGENT_IDENTITY_UNIFICATION.md Step N
```

## Success Criteria

After this sprint:
1. One canonical AgentIdentity model in models.py
2. All 6 files migrated to use it
3. All 14 bootstrap loop tests pass
4. At least 3 loops show "closed" status in CYBERNETIC_LOOP_MAP.md
5. Conductors can start with free providers (not hardcoded to Anthropic)
