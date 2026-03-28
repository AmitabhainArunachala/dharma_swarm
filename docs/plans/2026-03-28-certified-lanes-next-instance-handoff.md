# Certified Lanes Next-Instance Handoff

Date: 2026-03-28

## Current Checkpoint

The canonical certified-lane registry is now in place for three real working lanes:

- `glm5_researcher` -> `GLM-5 Cartographer` -> codename `glm-researcher`
- `kimi_k25_scout` -> `Kimi K2.5 Scout` -> codename `kimi-scout`
- `sonnet46_operator` -> `Claude Sonnet 4.6` -> codename `sonnet-relay`

The registry lives in `dharma_swarm/certified_lanes.py` and is now used by:

- `api/routers/chat.py`
  - certified lanes are advertised through `/api/chat/status`
  - `Claude Code / Sonnet 4.6` now has a subprocess-backed dashboard chat path
  - Kimi and GLM stay on the OpenRouter-compatible API-tool loop
- `dharma_swarm/contracts/intelligence_agents.py`
  - live agent registration and KaizenOps events now carry:
    - `registered_lane_id`
    - `registered_lane_profile_id`
    - `registered_lane_codename`
    - `registered_lane_label`
- `api/routers/_agent_aliases.py`
  - dashboard-facing aliases now resolve:
    - `glm5-cartographer`
    - `kimi-k25-scout`
    - `cyber-kimi25`
    - `sonnet46-operator`
- `dashboard/src/lib/chatProfiles.ts`
  - compact labels now recognize `Sonnet` and `Kimi`

## Broader Emergency Context

This handoff is not just about naming lanes. The higher-order issue is that the
swarm has been over-reporting capability while under-proving real end-to-end
autonomous work.

What is now actually true:

- `Claude Sonnet 4.6` is a real subprocess-backed worker lane through
  `ClaudeCodeProvider`.
- `OpenRouter / Kimi K2.5` and `OpenRouter / GLM-5` have already proven at least
  one real local tool/shell probe on this machine after the API tool-loop fix.
- `openrouter` and `nvidia_nim` can no longer be incorrectly treated as local
  bash/file workers without an attached executor. That false-green path was
  closed in `agent_runner.py`.

What is still not healthy:

- `Claude Haiku` is still broken on the tool-schema path and does not count as a
  certified worker.
- `OpenAI / gpt-5` still loops poorly in the local tool path and is not yet
  robust enough to count as a certified peer lane.
- `NVIDIA NIM / qwen2.5-coder-32b-instruct` does not support tool use on the
  current endpoint path and should remain honestly degraded rather than
  advertised as a full local worker.
- The system still needs a formal certification harness that proves artifact
  creation and command execution on each lane regularly instead of relying on
  one-off manual probes.

There is also a separate truthfulness problem in the strategic loop:

- the live `thinkodynamic` canary already proved that passing unit tests do not
  imply useful autonomous behavior
- observed live failures included:
  - stale review reuse
  - generic workflow generation
  - heuristic-only council fallback
  - test files surfacing as strategic top signals
  - corrupt stigmergy marks in live state

Treat these as the two parallel emergency seams:

1. certified worker lanes must become real and continuously provable
2. strategic autonomy must stop lying about improvement when runs are degraded

## Verification

Passed:

- `pytest -q tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py`
  - result: `17 passed`
- `python3 -m py_compile dharma_swarm/certified_lanes.py api/routers/chat.py dharma_swarm/contracts/intelligence_agents.py api/routers/_agent_aliases.py`
  - result: passed

Did not pass:

- `./node_modules/.bin/tsc --noEmit -p dashboard/tsconfig.json`
  - blocked by pre-existing dashboard TypeScript issues
  - dominant failures are existing `.ts` test-import configuration errors (`TS5097`) and a few unrelated narrow typing issues in dashboard tests
  - this failure is not introduced by the certified-lane diff

## Files Touched In This Slice

- `dharma_swarm/certified_lanes.py`
- `api/routers/chat.py`
- `api/routers/_agent_aliases.py`
- `dharma_swarm/contracts/intelligence_agents.py`
- `dashboard/src/lib/chatProfiles.ts`
- `dashboard/src/lib/chatProfiles.test.ts`
- `tests/test_dashboard_chat_router.py`
- `tests/test_intelligence_agents.py`

## Dirty Worktree Note

Two files already had local changes before this slice and were edited carefully on top:

- `api/routers/chat.py`
- `tests/test_dashboard_chat_router.py`

Do not blindly revert those files.

## What Is True Now

- The dashboard runtime contract can truthfully advertise three certified peer lanes beyond `claude_opus` / `codex_operator`.
- `Sonnet 4.6` is not just a label: the dashboard chat router can now complete through the `ClaudeCodeProvider` subprocess path.
- KaizenOps-facing registration metadata is no longer hand-wavy for these lanes; the certified lane identity now survives into telemetry and ingest payloads.

## What Is Not Done

- There are no dedicated `/dashboard/kimi` or `/dashboard/sonnet` route pages yet.
- There is no live periodic certification harness writing pass/fail back into KaizenOps.
- There is no explicit UI grouping for "certified lanes" versus ordinary advertised profiles.
- Live swarm spawn flows do not yet consistently stamp `profile_id` or `registered_lane_profile_id` into agent metadata at creation time.
- The dashboard TypeScript test/import configuration still needs cleanup before frontend compile/test is a reliable gate.

## Priority Order For Next Instance

1. Run live lane probes against the real backend and record the result.
   - `sonnet46_operator`
   - `kimi_k25_scout`
   - `glm5_researcher`
   - confirm actual chat completion, tool use where applicable, and operator-visible status

2. Build the small lane certification harness.
   - fixed artifact-backed task
   - fixed shell-backed task
   - machine-readable result under `~/.dharma`
   - KaizenOps summary payload

3. Fix the next broken worker lane.
   - first target: `Claude Haiku` tool-schema failure
   - second target: `OpenAI / gpt-5` tool-loop termination after contract satisfaction

4. Stop false strategic autonomy claims.
   - repair stale review reuse in `thinkodynamic_director.py`
   - suppress generic or mismatched workflows from counting as success
   - mark heuristic-only council mode as degraded immediately

5. Clean the operator truth surfaces.
   - dashboard compile/test baseline
   - `system_integration_probe.py` must degrade on real witness problems
   - `doctor.py` and runtime status must not report healthy when the canary is red

6. Only after those are moving, continue with the constitutional hardening plan in:
   - `docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md`

## Recommended Next TODOs

1. Run live dashboard lane probes against the real backend:
   - check `/api/chat/status`
   - send one live chat turn through `sonnet46_operator`
   - send one live chat turn through `kimi_k25_scout`
   - send one live chat turn through `glm5_researcher`

2. Add certified-lane metadata at spawn time:
   - wire `profile_id` or `registered_lane_profile_id` into agent spawn metadata in the swarm/API path
   - make live agent objects show the same identity the dashboard advertises

3. Build a small certification harness:
   - fixed artifact-backed task
   - run across certified lanes only
   - persist results under `~/.dharma`
   - publish summary rows to KaizenOps

4. Decide dashboard product surface:
   - either keep certified lanes as dropdown-only
   - or add dedicated `Kimi` and `Sonnet` pages alongside `qwen35` and `glm5`

5. Fix frontend tooling baseline:
   - clean up existing `TS5097` test-import configuration problems
   - restore a trustworthy dashboard compile gate

6. Fix the next broken worker lanes:
   - `Claude Haiku` tool-schema compatibility
   - `OpenAI / gpt-5` tool-loop termination and artifact-contract satisfaction
   - keep unsupported NIM tool-use paths marked degraded unless capability changes are proven

7. Add operator docs:
   - brief note in `PRODUCT_SURFACE.md`
   - short operator-facing explanation of certified lanes and their expected roles

8. Fold canary truth into the certified-lane work:
   - connect `thinkodynamic_canary` findings to operator status
   - make it impossible for the dashboard to look green while the strategic canary is red

## Suggested Resume Command Set

From `/Users/dhyana/dharma_swarm`:

```bash
pytest -q tests/test_dashboard_chat_router.py tests/test_intelligence_agents.py
python3 -m py_compile dharma_swarm/certified_lanes.py api/routers/chat.py dharma_swarm/contracts/intelligence_agents.py api/routers/_agent_aliases.py
```

Then resume with:

```bash
rg -n "registered_lane|kimi_k25_scout|sonnet46_operator|glm5_researcher" api dharma_swarm dashboard tests
```
