# DGC Stress Harness

This harness is wired into the CLI as:

```bash
dgc stress [options]
```

Implementation entrypoints:

- `scripts/dgc_max_stress.py`
- `dharma_swarm/dgc_cli.py` (`cmd_stress`)

## What It Tests

The run executes these phases end-to-end:

1. `preflight`
- Verifies binaries, keys, and baseline DGC status/health commands.

2. `research agents`
- Spawns two dedicated stress-research agents and tasks.
- Focuses on stress vectors and adversarial breakpoints.

3. `orchestrator load`
- Spawns N agents, creates M tasks, dispatches until completion/timeout.
- Measures completion, failures, and throughput.

4. `evolution stress`
- Submits safe + intentionally harmful proposals.
- Validates gate rejections, archive behavior, canary promote/rollback, policy compile.

5. `CLI flood`
- Parallel command pressure across status, dharma, gates, route, compose, autonomy,
  context-search, stigmergy, and hum.

6. `external research` (optional)
- Runs direct `claude -p` and `codex exec` probes with bounded timeout.

## Artifacts

Each run writes:

- `~/.dharma/shared/dgc_max_stress_<RUN_ID>.json`
- `~/.dharma/shared/dgc_max_stress_<RUN_ID>.md`

## Recommended Profiles

Fast synthetic reliability check:

```bash
dgc stress --profile quick --provider-mode mock
```

Maximum synthetic load:

```bash
dgc stress --profile max --provider-mode mock
```

Live-provider integration smoke:

```bash
dgc stress \
  --profile quick \
  --provider-mode claude \
  --orchestration-timeout-sec 30 \
  --external-research \
  --external-timeout-sec 45
```

## Reading Results

Prioritize these fields in the report:

- `phase_research_agents.wait.complete`
- `phase_orchestrator_load.counts` (`completed`, `failed`, `other`)
- `phase_evolution` (`rejected`, `canary_promote`, `canary_rollback`)
- `phase_cli_flood.pass_rate`
- `phase_external_research` (`rc`, `elapsed_sec`, `stderr_tail`)

`counts.other > 0` or `research complete=false` indicates timeout/starvation under the selected provider/timeout settings.
