# DGC Working System Spec

Date: 2026-03-13
Purpose: define the exact internal loop DGC must run on itself before wider sales claims
Status: partially working

## Canonical object

The working system is not "a lot of agents."

It is one bounded operating loop:

`corpus -> graph -> briefs -> campaign -> artifact -> verification -> memory update -> next-day continuity`

## Canonical inputs

- codebase: `dharma_swarm/`
- docs and reports: `docs/`, `reports/`
- active continuity state:
  - `reports/dual_engine_swarm_20260313_run/state/mission.json`
  - `reports/dual_engine_swarm_20260313_run/state/campaign.json`
- health and runtime evidence:
  - `reports/verification/dgc_full_power_probe_20260313T015447Z.md`
  - `reports/dual_engine_swarm_20260313_run/state/shared/thinkodynamic_director_latest.md`

## Canonical outputs

- semantic graph
- semantic brief packet
- active campaign object
- buyer-facing packet
- one verified artifact
- updated continuity ledger for the next cycle

## Current operating loop

| Step | Command or surface | Output | Current truth | Human required |
|---|---|---|---|---|
| 1. Digest | `dgc semantic digest` | `semantic_graph.json` | Working | choose corpus root |
| 2. Ground | `dgc semantic research` | annotated graph | Working | none if corpus chosen |
| 3. Compile briefs | `dgc semantic brief` | `semantic_brief_packet.{json,md}` | Working | choose max briefs and campaign target |
| 4. Select campaign | `dgc campaign-brief` | ranked active campaign | Working | confirm which brief becomes commercial story |
| 5. Package for buyer | this packet | demo, proof, pricing, outreach assets | Working | yes |
| 6. Delegate execution | thinkodynamic director | task wave, artifacts | Partial | yes |
| 7. Verify | tests, probe, artifact review | acceptance evidence | Partial | yes |
| 8. Resume coherently | campaign ledger + memory | next-day continuity | Working | yes |

## What the fresh run proved

- Fresh digest built a graph with `2471` concepts and `19800` edges.
- Fresh research annotation added `4565` annotations with `91.8%` coverage.
- Fresh brief compilation yielded `3` semantic briefs and `3` execution briefs.
- Fresh end-to-end proof passed with all `4` synthesized clusters surviving hardening.
- The generated campaign object remained continuity-compatible with the active director mission state.

## What is working

### Semantic chamber

- DGC can read its own repo and docs at nontrivial scale.
- DGC can produce clusters that are not random file groupings.
- DGC can attach research spine and gap lists.
- DGC can turn those clusters into execution briefs.

### Continuity chamber

- DGC has a campaign object with semantic briefs, execution briefs, artifacts, and metrics.
- DGC can render an operator-readable campaign summary without manual rewriting.
- DGC has a full-power probe that surfaces health, mission, toolchain, and stress evidence.

## What is only partial

### Execution chamber

- The director can delegate work.
- The worker layer is still brittle under real unattended runs.
- Current truth from earlier run state shows semantic output is stronger than execution completion reliability.

### Retrieval and context

- Full power probe notes that context search did not retrieve the mechanistic/work-summary query even though filesystem context existed.
- This means raw corpus access is stronger than retrieval precision.

## What is blocked

### External reachability graph

- There is no verified in-repo CRM, contact ledger, or public-signal target file.
- Under the anti-delusion rule, DGC cannot honestly claim a warm `25`-account target list.
- For a zero-network start, DGC must bootstrap from a `reachability graph`, not a warm graph fantasy.
- Valid cold-start source types are:
  - public repos and issue trackers
  - launch pages and product changelogs
  - hiring pages and role descriptions
  - founder posts or engineering notes that expose a current bottleneck

## Human boundary conditions

Humans still need to:

- choose the commercial campaign to emphasize
- approve public claims
- approve the reachability graph and outbound list
- decide which deliverables are buyer-safe
- supervise send policy, replies, and close conversations

## Minimum working threshold

The system counts as commercially usable for managed diagnostics when all of these are true:

- `corpus -> first brief` in under `24h`
- `brief -> buyer packet` in under `48h`
- demo can be run in under `15m`
- proof boundaries are explicit
- no public claim depends on unattended autonomy

The fresh packet satisfies the first four.
It does not yet satisfy unattended execution reliability.

## Stop conditions

Do not scale outreach if any of these remain true:

- the demo requires hidden manual rescue
- the proof packet overclaims provider or execution reliability
- target-account list lacks source evidence or a concrete public trigger
- outbound domain/authentication and opt-out handling are not set up
- top-of-funnel depends on scaled low-value AI content
- buyer deliverables need more than one extra day of operator interpretation

## Next hardening priorities

1. Build a `reachability_graph.csv` from public signals and score it with the rubric in `target_account_rubric.md`.
2. Add a lightweight `Signal Brief` top-of-funnel asset ahead of the paid `Campaign X-Ray`.
3. Run the same `Campaign X-Ray` packet on one adjacent internal corpus: PSMV, mech-interp, or AGNI workspace.
4. Close the gap between execution briefs and actual worker completion.
5. Capture one clean before/after case study skeleton from an internal proving ground.
