# Merge Control

This folder is the control plane for converging DGC into one clean canonical runtime.

## Files

- `MERGE_LEDGER.md`: authoritative keep/port/drop ledger.
- `CANONICAL_STATE.md`: latest generated state snapshot in plain language.
- `FACTS.json`: latest generated machine-readable facts.
- `snapshots/YYYY-MM-DD/<stamp>/`: immutable point-in-time evidence bundles.

## Generate Snapshot

```bash
cd ~/dharma_swarm
python3 scripts/merge_snapshot.py --strict-core --require-tracked
```

## Overnight Loop

```bash
cd ~/dharma_swarm
scripts/start_merge_control_tmux.sh 08:00
scripts/status_merge_control_tmux.sh
scripts/stop_merge_control_tmux.sh
```
