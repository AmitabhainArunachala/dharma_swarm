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

State-only snapshot (no tracked file churn):

```bash
cd ~/dharma_swarm
python3 scripts/merge_snapshot.py --strict-core --require-tracked --state-only
```

## Import Legacy Archive (One-Time Bootstrap)

```bash
cd ~/dharma_swarm
python3 scripts/import_legacy_archive.py
```

Reports land in:

- `docs/merge/imports/LATEST_LEGACY_IMPORT.md`
- `docs/merge/imports/LATEST_LEGACY_IMPORT.json`

## Overnight Loop

```bash
cd ~/dharma_swarm
scripts/start_merge_control_tmux.sh 08:00
scripts/status_merge_control_tmux.sh
scripts/stop_merge_control_tmux.sh
```

By default the loop now writes canonical outputs under `~/.dharma/merge/`
(`MERGE_STATE_ONLY=1`) so the repo working tree stays clean during autonomous runs.
