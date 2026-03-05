# Verification Lane

Read-only verifier for the active DGC + dharma_swarm system.

It checks:
- process liveness (`overnight`, `daemon`, `sentinel`)
- command health (`dgc status`, `dgc swarm overnight status`, `dharma_swarm.cli status`)
- task/memory DB state
- log freshness

## Start

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/start_verification_lane.sh 8
```

Optional faster loop:

```bash
VERIFY_INTERVAL=120 bash scripts/start_verification_lane.sh 8
```

## Stop

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/stop_verification_lane.sh
```

## Outputs

Run metadata:

```bash
cat ~/.dharma/verification_lane_run_dir.txt
```

Per-run files:
- `report.md`
- `snapshots.jsonl`
- `verify.log`

