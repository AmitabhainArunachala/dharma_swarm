# Agentic Autonomy Bundle

Date: 2026-03-27

## Scope

This pass localizes external source material and ties it to existing `dharma_swarm` seams. It does not yet change runtime behavior. The safe default assumption is:

- clone and snapshot relevant adjacent systems
- create a source bundle with at least twenty metabolizable artifacts
- seed citation-level links into the system
- update external field intelligence with the new patterns

## Bundle Summary

Pulled into the repo:

- `references/adjacent/ouroboros`
- `references/adjacent/ouroboros-desktop`
- `references/adjacent/cashclaw`
- `references/adjacent/cashclaw-moltlaunch`
- `references/adjacent/hyrve-ai`
- `references/adjacent/openroom`
- `references/adjacent/deepagents`
- `references/adjacent/paybot-mcp`

Localized note files:

- `references/research/agentic_autonomy_2026-03-27/meta_rea_2026-03-17.md`
- `references/research/agentic_autonomy_2026-03-27/minimax_m27_2026-03-18.md`
- `references/research/agentic_autonomy_2026-03-27/microsoft_plugmem_2026-03-10.md`
- `references/research/agentic_autonomy_2026-03-27/langchain_deepagents_multi_agent_2026-01-21.md`
- `references/research/agentic_autonomy_2026-03-27/langchain_deepagents_context_2026-01-28.md`
- `references/research/agentic_autonomy_2026-03-27/mempo_2026-03-17.md`

Manifested source count:

- 24 sources in `references/research/agentic_autonomy_2026-03-27/sources.json`

## Highest-Signal Lessons

### 1. REA is the missing wait-state architecture

REA's real move is not "good agents." It is:

- planner/executor split
- persistent plan state
- explicit wait state around external jobs
- hibernate/wake around long runs
- failure runbooks
- budget approval before execution

`dharma_swarm` currently has the ingredients for resume and persistence, but not the actual external-job wait model.

### 2. MiniMax M2.7 points at harness evolution, not just model evolution

The mutable unit is:

- memory
- skills
- prompt and harness logic
- loop detection
- evaluation sets

That matches `dharma_swarm`'s architecture well because many seams already live outside base weights. The present limitation is that `self_improve.py` still thinks too much like code-only improvement.

### 3. Ouroboros is useful as design inspiration, not audited evidence

Ignore the mythologizing. Keep the design primitives:

- constitution as a protected continuity core
- persistent identity across restarts
- background cognition
- git-mediated self-rewrite
- explicit lineage

This maps directly onto `identity.py`, `self_improve.py`, and the missing notion of constitution-bound evolution.

### 4. CashClaw/HYRVE is the closest operational template for economic closure

The valuable parts are concrete:

- job polling daemon
- acceptance and auto-accept thresholds
- order lifecycle
- delivery hooks
- escrow and payout rails
- agent payments via MPP/USDC

`economic_agent.py` already names the stages, but the connectors and tests are not there yet.

## Recommended Runtime Work Packages

1. Wait-state job engine
   - Introduce a durable job object with states like `planned`, `submitted`, `waiting_external`, `ready_to_resume`, `blocked_budget`, `failed`, `completed`.
   - Store the exact next action and resumption condition.

2. Economic closure spine
   - Extend `economic_agent.py` to a real job machine with marketplace adapters, payout records, and approval policy.
   - Keep marketplace connectors modular so HYRVE, direct clients, and future marketplaces share one internal contract.

3. Harness self-evolution
   - Upgrade `self_improve.py` so prompts, memory policies, skills, and loop policies are first-class candidates.
   - Add keep/revert decisions and harness-targeted eval sets.

4. Identity and constitution lineage
   - Make constitution and identity changes explicit artifacts with lineage logs and review policy.
   - Treat identity continuity as part of runtime health, not just a file on disk.

## External Sources

- Meta REA: https://engineering.fb.com/2026/03/17/developer-tools/ranking-engineer-agent-rea-autonomous-ai-system-accelerating-meta-ads-ranking-innovation/
- MiniMax M2.7: https://www.minimax.io/news/minimax-m27-en
- PlugMem: https://www.microsoft.com/en-us/research/blog/from-raw-interaction-to-reusable-knowledge-rethinking-memory-for-ai-agents/
- Deep Agents multi-agent patterns: https://blog.langchain.dev/building-multi-agent-applications-with-deep-agents/
- Deep Agents context management: https://blog.langchain.dev/context-management-for-deepagents/
- MemPO: https://arxiv.org/abs/2603.00680
- Ouroboros: https://github.com/oseledets/ouroboros
- Ouroboros Desktop: https://github.com/joi-lab/ouroboros-desktop
- CashClaw: https://github.com/ertugrulakben/cashclaw
- HYRVE: https://github.com/ertugrulakben/HYRVE-AI
- PayBot MCP: https://github.com/RBKunnela/paybot-mcp
- DeepAgents: https://github.com/langchain-ai/deepagents
- OpenRoom: https://github.com/MiniMax-AI/OpenRoom
