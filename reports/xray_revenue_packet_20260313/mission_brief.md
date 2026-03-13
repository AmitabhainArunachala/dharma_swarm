# Swarm Mission: Repo X-Ray Sprint for dharma_swarm

## Objective
Turn static repo evidence into a buyer-ready diagnostic, a verified implementation slice, and the shortest credible path to a paid follow-on sprint.

## Success Criteria
- Source-grounded X-Ray completed
- Service brief written
- Top risks ranked and scoped
- One verified implementation slice proposed or shipped
- Clear next paid step identified

## Agent Lanes
- codex-primus: lead builder, patch closer, and implementation owner
- opus-primus: diagnosis, contradiction hunting, and scope control
- glm-researcher: dependency and evidence synthesis
- kimi-cartographer: file graph and artifact mapping
- qwen-builder: broad low-cost implementation support
- nim-validator: verification, regression checks, and result gating

## Proof Surfaces
- Analyzed 446 files and 128,909 non-blank lines.
- Test surface: 199 test files for roughly 247 non-test files (81% ratio).
- Quality grade C with score 0.529; average complexity 48.1.
- Top hotspot: execute_single_step in scripts/strange_loop.py:1007 (complexity 95).
- Largest file: dharma_swarm/dgc_cli.py at 4,591 non-blank lines.

## Close Condition
Run the paid Repo X-Ray Sprint on the live repository, then convert the first verified fix into a case study and recurring maintenance offer.
