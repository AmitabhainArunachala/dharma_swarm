# Overnight Autopilot

Primary goal: keep `dharma_swarm` active all night with periodic status, task feed, and quality checks.

## Start

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/start_overnight.sh 8
```

## Stop

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/stop_overnight.sh
```

## Live logs

```bash
tail -f ~/.dharma/logs/overnight_supervisor_stdout.log
```

Per-run artifacts are written under:

```text
~/.dharma/logs/overnight/<run_id>/
```

Key files:
- `autopilot.log` (event log)
- `report.md` (human summary)
- `snapshots.jsonl` (machine-readable loop snapshots)
- `context_*.md` (role/thread context captures)
