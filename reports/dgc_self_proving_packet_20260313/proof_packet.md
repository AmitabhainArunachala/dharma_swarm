# Proof Packet

Date: 2026-03-13
Purpose: separate what DGC can prove now from what remains aspirational

## Summary

The internal `Campaign X-Ray` is real.

The semantic chamber and continuity chamber are strong enough to sell a managed diagnostic.
The unattended execution chamber is not yet strong enough to sell as the main promise.

## Claims and evidence

| Claim | Evidence | What it proves | What it does not prove |
|---|---|---|---|
| DGC can ingest a live repo into a nontrivial semantic graph. | `semantic_graph.json`, `semantic_proof.txt` | Real corpus digestion at repo scale. | Editorial judgment by itself. |
| DGC can ground that graph with research annotations. | `semantic_proof.txt`, `semantic_brief_packet.md` | The graph is not just local string matching. | Perfect citation hygiene or finished research memos. |
| DGC can synthesize ranked semantic and execution briefs. | `semantic_brief_packet.md`, `campaign.json` | The system can turn corpus structure into prioritized campaigns and tasks. | Reliable completion of all resulting tasks. |
| DGC can maintain a campaign continuity object. | `campaign.json`, `campaign-brief` rendering | The output survives beyond one chat turn. | Fully autonomous long-horizon execution. |
| DGC has runtime-health and operator evidence surfaces. | `reports/verification/dgc_full_power_probe_20260313T015447Z.md` | The system exposes toolchain, mission, and health truth instead of hiding it. | A production-grade reliability guarantee. |
| DGC has at least one prior successful provider smoke artifact. | `reports/dual_engine_swarm_20260313_run/provider_smoke.json` | NVIDIA NIM answered `OK` in an earlier run. | Current full multi-provider reachability inside this sandbox. |

## Fresh internal X-Ray evidence

From the packet generated in this turn:

- digest: `2471` concepts, `19800` edges
- research: `4565` annotations, `91.8%` coverage
- synthesize/harden: `4` clusters, `4/4` hardened
- briefs: `3` semantic briefs, `3` execution briefs
- average readiness: `0.591`
- proof run: passed in `8.6s`

## Operational truth from adjacent runtime artifacts

From `reports/verification/dgc_full_power_probe_20260313T015447Z.md`:

- doctor passed
- worker binaries were available
- ecosystem health probe passed
- context search retrieval was weaker than raw filesystem context
- health-check was degraded because previously active agents had no traces in the last hour

That means DGC is observable and instrumented, but not yet stable enough to hide behind vague autonomy claims.

## Current failure boundaries

### Execution reliability

Current packet evidence does not prove:

- that delegated tasks complete reliably unattended
- that every execution brief turns into a successful artifact
- that provider fallback is stable in all runtime environments

### Provider truth

Current packet evidence does not claim full live provider confirmation for all lanes.

Why:

- the historical NIM smoke artifact exists and shows a clean `OK`
- the later smoke artifact in `reports/verification/provider_smoke_20260313T071659Z.json` is blocked by a JIKOKU write-permission issue in this environment

So the honest statement is:

`provider lanes exist and at least one prior NIM lane was verified, but this packet is not the right artifact for claiming all current model lanes are firing live right now.`

### Warm graph

Current packet evidence does not prove:

- a real warm-account list
- a sales-ready relationship graph
- a verified list of `25` design-partner targets

No such source-of-truth file exists in the repo today.

## What can be sold honestly right now

Sell:

- a managed diagnostic
- a continuity and prioritization engine
- a proof-backed campaign packet

Do not sell:

- fully autonomous company operation
- world-class unattended coding swarm
- a warm outbound engine that does not yet exist

## Bottom line

The strongest honest commercial sentence is:

`DGC can already turn a dense technical corpus into ranked campaigns, explicit gaps, and a continuity ledger.`

The strongest sentence that is still false is:

`DGC can already replace the operator.`
