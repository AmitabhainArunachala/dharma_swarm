# Doctor + Claude Addendum

Date: 2026-03-16
Purpose: capture the overlap and disagreement between deterministic `Doctor` findings and a Claude Code architecture-judge pass.

## What I Added In This Orthogonal Lane

1. Added an API-envelope scanner that detects the typed dashboard fetch path parsing backend `ApiResponse` envelopes as payload `T` instead of unwrapping `data`: [scanner_api_envelope.py](/Users/dhyana/dharma_swarm/dharma_swarm/assurance/scanner_api_envelope.py#L35)
2. Added a context-isolation scanner that detects `build_agent_context(state_dir=...)` still reading shared notes through global `SHARED_DIR` and `STATE_DIR`: [scanner_context_isolation.py](/Users/dhyana/dharma_swarm/dharma_swarm/assurance/scanner_context_isolation.py#L17)
3. Wired both scanners into `Doctor`: [runner.py](/Users/dhyana/dharma_swarm/dharma_swarm/assurance/runner.py#L8)
4. Improved route scanning for dynamic template paths like `/api/tasks/${id}` without breaking query-string template calls: [scanner_routes.py](/Users/dhyana/dharma_swarm/dharma_swarm/assurance/scanner_routes.py#L13)
5. Added regression tests for the new scanners and dynamic-route handling: [test_assurance.py](/Users/dhyana/dharma_swarm/tests/test_assurance.py#L97)

## Current Deterministic Signal

Verification after the patch:
- `pytest -q tests/test_assurance.py tests/test_doctor.py` -> `12 passed`
- `python3 -m dharma_swarm.assurance --json` -> `FAIL`, `high=14`, `medium=6`
- `python3 -m dharma_swarm.dgc_cli doctor --quick` -> `FAIL (pass=9, warn=1, fail=6)`

The high-confidence `Doctor` findings now are:
1. 8 route mismatches in [api.ts](/Users/dhyana/dharma_swarm/dashboard/src/lib/api.ts#L103)
2. 1 typed-fetch response-envelope mismatch in [api.ts](/Users/dhyana/dharma_swarm/dashboard/src/lib/api.ts#L35)
3. 3 CODEX/provider-label mismatches in [conductors.py](/Users/dhyana/dharma_swarm/dharma_swarm/conductors.py#L72) and [persistent_agent.py](/Users/dhyana/dharma_swarm/dharma_swarm/persistent_agent.py#L26)
4. 1 `state_dir` isolation leak in [context.py](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L1084)
5. Lifecycle still missing explicit `ExecutionLease`, `RoutingBias`, and `ProjectionRefresh`

## Claude Judge Summary

Claude’s architecture pass agreed with the main operational picture:
1. Route drift is the top merge risk and likely to produce silent empty dashboard states.
2. The typed-fetch wrapper mismatch is real and becomes live once route paths are corrected.
3. The `state_dir` note leak is real but narrower in blast radius than the web/API defects.

Claude also pushed back on three findings:
1. `ProviderType.CODEX` may be an intentional naming alias for an Anthropic-backed infrastructure lane rather than a runtime bug.
2. Missing lifecycle classes are design debt or aspirational docs drift, not necessarily a regression introduced by this branch.
3. Redis being down looks like local environment noise, not code correctness.

## My Read On The Disagreement

1. Claude is right that route drift is the first thing to fix.
2. Claude is right that the typed-fetch mismatch should be fixed in the same pass as route repair.
3. I only partially agree on the CODEX finding. Even if intentional, the naming remains semantically misleading enough that `Doctor` should keep surfacing it until the code or docs make the alias explicit.
4. I agree that lifecycle gaps are closer to architecture debt than immediate branch regression, but they still matter because `ExecutionLease` is where retry/idempotency identity would normally live.
5. I agree Redis down should not be treated as a merge blocker unless the repo now truly depends on it.

## Practical Priority Order

1. Fix dashboard route mismatches in [api.ts](/Users/dhyana/dharma_swarm/dashboard/src/lib/api.ts#L103)
2. Fix `_fetchWrapped()` envelope handling in [api.ts](/Users/dhyana/dharma_swarm/dashboard/src/lib/api.ts#L35)
3. Thread `state_dir` through note loading in [context.py](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L806)
4. Decide whether `ProviderType.CODEX` is a true provider lane or a role label, then encode that decision honestly in code and docs
5. Treat lifecycle class gaps as a documented backlog unless the main branch starts relying on them semantically
