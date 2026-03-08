# AllOut 6-Hour Mode

Purpose: run an autonomous 6-hour loop that:
1. Runs core DGC checks/tests.
2. Reads 10 local files per cycle.
3. Generates a fresh 3-5 step action plan.
4. Repeats until time window ends.

## Start

```bash
cd ~/dharma_swarm && POLL_SECONDS=300 USE_CAFFEINATE=1 scripts/start_allout_tmux.sh 6
```

## Status

```bash
cd ~/dharma_swarm && scripts/status_allout_tmux.sh
```

## Stop

```bash
cd ~/dharma_swarm && scripts/stop_allout_tmux.sh
```

## Artifacts

- Heartbeat: `~/.dharma/allout_heartbeat.json`
- Logs: `~/.dharma/logs/allout/<run_id>/allout.log`
- Snapshots: `~/.dharma/logs/allout/<run_id>/snapshots.jsonl`
- Cycle action plans: `~/.dharma/shared/allout_todo_cycle_*.md`
- Morning summary: `~/.dharma/shared/allout_morning_<run_id>.md`
