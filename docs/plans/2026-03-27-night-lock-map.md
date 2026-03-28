# Night Lock Map — 2026-03-27

**Purpose**: freeze a truthful picture of the repo field at end-of-night so the system does not dissolve into untraceable branch dirt.

## 1. Repo Scan

Shortlist of relevant repos as of this pass:

| Repo | Branch | HEAD | Dirty files | Last commit |
| --- | --- | --- | ---: | --- |
| `/Users/dhyana/dharma_swarm` | `checkpoint/dashboard-stabilization-2026-03-19` | `50d72e1` | `153` | `2026-03-27 Add agent memory and observability lane` |
| `/Users/dhyana/mech-interp-latent-lab-phase1` | `main` | `02de820` | `40` | `2026-03-24 Sync March paper, automation, and experiment outputs` |
| `/Users/dhyana/saraswati-dharmic-agora` | `main` | `b3d9169` | `25` | `2026-03-10 feat: MCP tool server + canonical spec expansion + /health endpoint` |
| `/Users/dhyana/dharmic-agora` | `execution/sab-proofpack-20260225-2324` | `a6611ee` | `43` | `2026-02-26 hardening: add production CORS/federation guards and launch readiness scorer` |
| `/Users/dhyana/autoresearch` | `dharma-benchmarks-seed` | `c2450ad` | `14` | `2026-03-10 Guard against infinite loop when no training shards exist, fix README typo` |
| `/Users/dhyana/dharma_swarm_autoresearch` | `autoresearch-bootstrap` | `c1bb0fe` | `0` | `2026-03-17 Cached flow-score and token-set work inside conversation_memory.py hot path` |
| `/Users/dhyana/everything-claude-code` | `main` | `b489309` | `6` | `2026-03-16 fix: resolve all CI test failures (19 fixes across 6 files) (#519)` |

## 2. Verdict

### Cleanest emergent repo tonight

`/Users/dhyana/dharma_swarm_autoresearch`

Why:
- `0` dirty files
- recent enough to still be alive
- structurally adjacent to the autonomous-reading / self-improving direction
- not already in branch-war condition

Weakness:
- cleaner than it is mature
- not the strongest production-ish system in the stack

### Cleanest serious product-ish repo tonight

`/Users/dhyana/saraswati-dharmic-agora`

Why:
- only `25` dirty files
- coherent README and system boundary
- concrete protocol, moderation queue, witness chain, and API surface
- a better “sleep here” anchor than `dharma_swarm` if the criterion is stable operational shape

### Dirtiest but still central repo

`/Users/dhyana/dharma_swarm`

Truth:
- this is still the main system
- it is also the current warzone
- do not pretend it is safe for casual overnight free-for-all edits

## 3. What Landed Tonight In `dharma_swarm`

### New spec package

- `spec-forge/conscious-control-plane/README.md`
- `spec-forge/conscious-control-plane/00-raw-requirements.md`
- `spec-forge/conscious-control-plane/01-architecture.md`
- `spec-forge/conscious-control-plane/02-adjacent-systems.md`
- `spec-forge/conscious-control-plane/features.json`
- `spec-forge/conscious-control-plane/05-validation.md`
- `spec-forge/conscious-control-plane/validation_manifest.json`
- `scripts/validate_conscious_control_plane_spec.py`

### New isolated implementation slice

- `dharma_swarm/semantic_governance.py`
- `dharma_swarm/claim_graph.py`
- `dharma_swarm/orientation_packet.py`
- `dharma_swarm/postmortem_reader.py`
- `dharma_swarm/prescription_translator.py`
- `dharma_swarm/runtime_bridge.py`

### One shared-file integration

- `dharma_swarm/context.py`
  Added `build_orientation_packet(...)` as a typed helper without disturbing the legacy text-context path.

### New tests

- `tests/test_semantic_governance.py`
- `tests/test_claim_graph.py`
- `tests/test_orientation_packet.py`
- `tests/test_postmortem_reader.py`
- `tests/test_prescription_translator.py`
- `tests/test_runtime_bridge.py`

### Verification status

Targeted verification passed on the new slice:

```bash
python3 -m py_compile \
  dharma_swarm/semantic_governance.py \
  dharma_swarm/claim_graph.py \
  dharma_swarm/orientation_packet.py \
  dharma_swarm/postmortem_reader.py \
  dharma_swarm/prescription_translator.py \
  dharma_swarm/runtime_bridge.py \
  dharma_swarm/context.py

pytest \
  tests/test_semantic_governance.py \
  tests/test_claim_graph.py \
  tests/test_orientation_packet.py \
  tests/test_postmortem_reader.py \
  tests/test_prescription_translator.py \
  tests/test_runtime_bridge.py -q
```

Result:
- `20 passed`

## 4. Current No-Go Zones In `dharma_swarm`

These surfaces are too hot to touch casually tonight because they are already in active churn:

- `dharma_swarm/orchestrator.py`
- `dharma_swarm/policy_compiler.py`
- `dharma_swarm/thinkodynamic_director.py`
- `dharma_swarm/startup_crew.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/providers.py`
- `dharma_swarm/model_routing.py`
- `dharma_swarm/provider_policy.py`
- `tests/test_orchestrator.py`
- `tests/test_startup_crew.py`
- `tests/test_swarm.py`
- `tests/test_thinkodynamic_director.py`

Interpretation:
- these are not forbidden forever
- they are the wrong place for sleepy, broad, speculative edits

## 5. Safe Next Slice

When work resumes, the safest expansion path is:

1. wire `semantic_governance.py` into `policy_compiler.py` behind a guarded fallback
2. add one integration test proving shared governance verdict reuse
3. only then expand into `orchestrator.py` and `thinkodynamic_director.py`

Do **not** start by pushing the whole conscious-control-plane vision through all hot files at once.

## 6. Recommended Overnight Anchor

If the goal is **cleanest emergent repo**:
- anchor on `/Users/dhyana/dharma_swarm_autoresearch`

If the goal is **cleanest serious operating repo**:
- anchor on `/Users/dhyana/saraswati-dharmic-agora`

If the goal is **continue core-system evolution despite dirt**:
- stay in `/Users/dhyana/dharma_swarm`
- but constrain work to new files and low-conflict helpers only

## 7. One-Line Guidance For Tomorrow

Treat `dharma_swarm` as the strategic core, `saraswati-dharmic-agora` as the cleanest stable serious substrate, and `dharma_swarm_autoresearch` as the cleanest emergent branch of the future. Do not confuse cleanliness with primacy.
