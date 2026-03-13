# Repo X-Ray Sprint Brief: dharma_swarm
*Generated 2026-03-13T15:07:21 UTC*

## Executive Summary
dharma_swarm is a viable fixed-scope Repo X-Ray Sprint candidate for AI-native founder or CTO buying a fixed-scope repo hardening sprint. The repo currently grades C and shows 15 visible risk signals, which is enough to justify a paid hardening sprint instead of a generic advisory call.

## Buyer
- AI-native founder or CTO buying a fixed-scope repo hardening sprint

## Diagnosis
- Change velocity is being taxed by concentrated complexity in a few functions or modules.
- Context is trapped in oversized files, which slows onboarding, review, and safe edits.
- Internal coupling suggests small changes may ripple across the codebase.

## Proof Points
- Analyzed 446 files and 128,909 non-blank lines.
- Test surface: 199 test files for roughly 247 non-test files (81% ratio).
- Quality grade C with score 0.529; average complexity 48.1.
- Top hotspot: execute_single_step in scripts/strange_loop.py:1007 (complexity 95).
- Largest file: dharma_swarm/dgc_cli.py at 4,591 non-blank lines.

## Fixed-Scope Offer
- Name: Repo X-Ray Sprint
- Duration: 5 business days
- Outcome: Deliver a source-grounded risk map, a prioritized remediation brief, one verified implementation slice, and a buyer-ready next-step recommendation.
- Price floor: $17,000
- Target price: $23,000

## Deliverables
- repo_xray_report.md
- service_brief.md
- mission_brief.md
- risk_register.json
- verified_change_slice.md
- hotspot_refactor_plan.md

## Swarm Plan
- codex-primus: lead builder, patch closer, and implementation owner
- opus-primus: diagnosis, contradiction hunting, and scope control
- glm-researcher: dependency and evidence synthesis
- kimi-cartographer: file graph and artifact mapping
- qwen-builder: broad low-cost implementation support
- nim-validator: verification, regression checks, and result gating

## Top Risks
- size: Large file (596 lines). Consider splitting. (tests/test_monitor.py)
- size: Large file (523 lines). Consider splitting. (tests/test_semantic_evolution.py)
- size: Large file (1056 lines). Consider splitting. (tests/test_thinkodynamic_director.py)
- size: Large file (893 lines). Consider splitting. (tests/test_gaia.py)
- size: Large file (750 lines). Consider splitting. (tests/test_orchestrator.py)

## Next Step
Run the paid Repo X-Ray Sprint on the live repository, then convert the first verified fix into a case study and recurring maintenance offer.
