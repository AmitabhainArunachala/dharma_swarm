# Codex Allnight YOLO

This is the Codex-native overnight lane for `dharma_swarm`.

It is designed to do one thing well: wake up, inspect the live repo, choose a
bounded slice, ship it with verification, and leave a clean morning handoff.

## Launch

Default aggressive launch:

```bash
dgc swarm yolo
```

Explicit Codex launch with mission file:

```bash
dgc swarm codex-night yolo 10 \
  --mission-file docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md \
  --label allnight-yolo
```

Optional knobs:

```bash
dgc swarm codex-night start 6 \
  --yolo \
  --mission-file docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md \
  --model gpt-5.4 \
  --max-cycles 8 \
  --poll-seconds 20 \
  --cycle-timeout 7200 \
  --label allnight-yolo
```

## Artifacts

Each run writes under `~/.dharma/logs/codex_overnight/<run_id>/`:

- `run_manifest.json`: operator label, mission, settings, git snapshot, latest cycle
- `mission_brief.md`: the exact mission text used for the run
- `report.md`: rolling cycle ledger
- `latest_last_message.txt`: latest Codex result block
- `morning_handoff.md`: human-facing handoff

A copy of the latest handoff is also written to:

- `~/.dharma/shared/codex_overnight_handoff.md`

## Status

```bash
dgc swarm codex-night status
dgc swarm codex-night report
```

The status helper now shows the current heartbeat, manifest, and morning
handoff if they exist.
