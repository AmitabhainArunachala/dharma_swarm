# DGC Merge Ledger

Purpose: enforce one canonical runtime (`~/dharma_swarm`) and track every import/merge decision from legacy generations.

## Canonical Runtime

- Runtime repo: `~/dharma_swarm`
- Legacy sources (import-only):
  - `~/DHARMIC_GODEL_CLAW`
  - `~/dgc-core`

## Decision Table

| Date (UTC) | Source | Target | Decision | Reason | Tests | Commit |
|---|---|---|---|---|---|---|
| 2026-03-09 | `~/DHARMIC_GODEL_CLAW/src/core/model_router.py` | `~/dharma_swarm/dharma_swarm/provider_policy.py`, `~/dharma_swarm/dharma_swarm/providers.py` | `PORT NOW` | Folded legacy risk-aware backend routing into the canonical provider router without reviving legacy backend coupling. | `tests/test_provider_policy.py`, `tests/test_providers.py`, `tests/test_providers_quality_track.py` | Uncommitted |
| 2026-03-09 | `~/DHARMIC_GODEL_CLAW/src/core/session_event_bridge.py`, `~/DHARMIC_GODEL_CLAW/src/core/continuity_harness.py` | `~/dharma_swarm/dharma_swarm/session_event_bridge.py`, `~/dharma_swarm/dharma_swarm/continuity_harness.py`, `~/dharma_swarm/dharma_swarm/tui/engine/session_store.py` | `PORT NOW` | Canonical TUI/session flow now emits validated runtime envelopes and replay-safe snapshots through the existing session store seam. | `tests/test_session_event_bridge.py`, `tests/test_continuity_harness.py`, `tests/test_tui_session_store.py` | Uncommitted |
| 2026-03-09 | `~/DHARMIC_GODEL_CLAW/ops/bridge/bridge_queue.py`, `~/DHARMIC_GODEL_CLAW/ops/bridge/bridge_exec.py`, `~/DHARMIC_GODEL_CLAW/ops/bridge/bridge_watcher.py` | `~/dharma_swarm/dharma_swarm/operator_bridge.py` | `REIMPLEMENT CLEANLY` | Canonical operator claim/timeout/respond lifecycle now lives on top of the message-bus SQLite authority plus session-ledger audit, without reviving legacy file-queue transport. | `tests/test_operator_bridge.py` | Uncommitted |
| 2026-03-10 | Canonical runtime doctrine + launcher/env gap | `~/dharma_swarm/dharma_swarm/artifact_manifest.py`, `~/dharma_swarm/scripts/start_allout_tmux.sh`, `~/dharma_swarm/scripts/start_caffeine_tmux.sh`, `~/dharma_swarm/scripts/start_caffeine_nvidia_tmux.sh` | `BUILD NOW` | Added machine-readable artifact manifests on top of existing artifact/runtime-state seams, and made autonomy launchers honor persisted NVIDIA wiring automatically instead of silently defaulting back to localhost. | `tests/test_artifact_manifest.py`, `tests/test_engine_artifacts.py`, `tests/test_runtime_state.py`, `bash -n scripts/start_allout_tmux.sh`, `bash -n scripts/start_caffeine_tmux.sh`, `bash -n scripts/start_caffeine_nvidia_tmux.sh` | Uncommitted |
| 2026-03-10 | Autonomous accelerator dormancy control | `~/dharma_swarm/scripts/strange_loop.py`, `~/dharma_swarm/dharma_swarm/dgc_cli.py`, `~/dharma_swarm/scripts/start_allout_tmux.sh`, `~/dharma_swarm/scripts/start_caffeine_tmux.sh`, `~/dharma_swarm/scripts/start_caffeine_nvidia_tmux.sh`, `~/.dharma/env/nvidia_remote.env` | `BUILD NOW` | Added explicit dormant/enabled accelerator mode so long unattended runs stop burning cycles on dead localhost RAG/Flywheel probes, while `wire_nvidia_remote.sh` remains the one-command path to arm the lane later. | `tests/test_allout_integration.py`, `tests/test_dgc_cli.py`, `bash -n scripts/start_allout_tmux.sh`, `bash -n scripts/start_caffeine_tmux.sh`, `bash -n scripts/start_caffeine_nvidia_tmux.sh`, `bash -n scripts/wire_nvidia_remote.sh` | Uncommitted |
| 2026-03-10 | Canonical flywheel integration blueprint | `~/dharma_swarm/dharma_swarm/flywheel_exporter.py` | `BUILD NOW` | Added a local, provenance-rich flywheel export seam that assembles workload records from canonical runtime state, manifests, replayed events, and conservative promoted facts before any remote job API is involved. | `tests/test_flywheel_exporter.py`, `tests/test_artifact_manifest.py`, `tests/test_runtime_state.py`, `tests/test_event_log.py` | Uncommitted |
| 2026-03-10 | Canonical flywheel operator surface | `~/dharma_swarm/dharma_swarm/dgc_cli.py` | `BUILD NOW` | Exposed the canonical flywheel export seam through `dgc flywheel export` and taught `dgc flywheel start --run-id ...` to create a recorded local export artifact before calling the remote job API. | `tests/test_dgc_cli.py`, `tests/test_flywheel_exporter.py`, `tests/test_integrations_data_flywheel.py` | Uncommitted |
| 2026-03-10 | Canonical external evaluation return path | `~/dharma_swarm/dharma_swarm/evaluation_registry.py`, `~/dharma_swarm/dharma_swarm/dgc_cli.py` | `BUILD NOW` | Added a canonical registry for Flywheel job outputs so remote evaluation results come back as local evaluation artifacts, promoted/candidate facts, provenance entries, and audited receipt events; exposed through `dgc flywheel record`. | `tests/test_evaluation_registry.py`, `tests/test_dgc_cli.py`, `tests/test_flywheel_exporter.py`, `tests/test_integrations_data_flywheel.py` | Uncommitted |

## Session Log

- Bootstrapped ledger. Use `scripts/merge_snapshot.py` to append factual checkpoints.
- 2026-03-09: Ported policy-backed provider routing plus session/runtime continuity seams into canonical `dharma_swarm`; legacy remains import-only authority.
- 2026-03-09: Reimplemented operator bridge queue semantics in canonical `dharma_swarm` using bus-backed live state and ledger-backed audit facts; legacy `ops/bridge` transport remains frozen.
- 2026-03-10: Ratified the lean hybrid runtime doctrine in `docs/reports/DGC_HYBRID_ACCELERATOR_BLUEPRINT_2026-03-10.md`: SQLite/JSONL/filesystem remain canonical truth layers, while NVIDIA RAG/Data Flywheel stay optional accelerator lanes around the sovereign runtime spine.
- 2026-03-10: Added canonical artifact manifests plus launcher-side persisted NVIDIA env loading; remote accelerator wiring can now be persisted once and reused by unattended tmux runs without manual shell sourcing.
- 2026-03-10: Put the NVIDIA lane into explicit dormant/enabled mode; current persisted config is dormant so allout/caffeine runs no longer waste long loops on dead local accelerator endpoints until the lane is deliberately armed.
- 2026-03-10: Added `flywheel_exporter.py` as the first canonical Data Flywheel attach point; exports are now local audited artifacts built from runtime truth, with receipt events in `flywheel_exports`, rather than implicit ad hoc payload assembly.
- 2026-03-10: Added `dgc flywheel export` and optional pre-export behavior on `dgc flywheel start`; operator-triggered flywheel jobs can now be rooted in a canonical local export artifact instead of starting from remote-only job creation.
- 2026-03-10: Added `evaluation_registry.py` and `dgc flywheel record`; Flywheel job outputs can now be bound back to canonical runs/sessions as evaluation artifacts, memory facts, provenance entries, and `flywheel_evaluations` receipt events.

## Rules

1. No architecture/performance claim without command output or file reference.
2. No feature lane is "done" until `mission-status --strict-core --require-tracked` is green.
3. Legacy code is ported by evidence (`keep|port|drop`), never copied wholesale.
4. All overnight/autonomous runs must emit snapshot facts and heartbeat.
- 2026-03-08T14:46:26Z snapshot=20260308T144624Z branch=split/2026-03-08 head=807779213dfc mission_exit=0 tracked=8/8
- 2026-03-08T14:46:58Z snapshot=20260308T144655Z branch=split/2026-03-08 head=807779213dfc mission_exit=0 tracked=8/8
- 2026-03-08T14:54:21Z snapshot=20260308T145419Z branch=split/2026-03-08 head=807779213dfc mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T14:57:00Z snapshot=20260308T145658Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:07:03Z snapshot=20260308T150700Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:17:05Z snapshot=20260308T151703Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:27:08Z snapshot=20260308T152705Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:37:10Z snapshot=20260308T153708Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:47:13Z snapshot=20260308T154710Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T15:57:15Z snapshot=20260308T155713Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:07:18Z snapshot=20260308T160715Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:17:20Z snapshot=20260308T161718Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:27:23Z snapshot=20260308T162720Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:37:25Z snapshot=20260308T163723Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:47:28Z snapshot=20260308T164725Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T16:57:30Z snapshot=20260308T165728Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:07:33Z snapshot=20260308T170730Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:17:35Z snapshot=20260308T171733Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:27:38Z snapshot=20260308T172735Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:37:40Z snapshot=20260308T173738Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:47:43Z snapshot=20260308T174740Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T17:57:46Z snapshot=20260308T175743Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:07:48Z snapshot=20260308T180746Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:17:51Z snapshot=20260308T181748Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:27:53Z snapshot=20260308T182751Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:37:56Z snapshot=20260308T183753Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:47:58Z snapshot=20260308T184756Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T18:58:01Z snapshot=20260308T185758Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:08:03Z snapshot=20260308T190801Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:18:05Z snapshot=20260308T191803Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:28:08Z snapshot=20260308T192806Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:38:11Z snapshot=20260308T193808Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:48:13Z snapshot=20260308T194811Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T19:58:16Z snapshot=20260308T195813Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:08:18Z snapshot=20260308T200816Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:18:21Z snapshot=20260308T201819Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:28:24Z snapshot=20260308T202821Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:38:26Z snapshot=20260308T203824Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:48:28Z snapshot=20260308T204826Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T20:58:31Z snapshot=20260308T205829Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:08:34Z snapshot=20260308T210831Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:18:36Z snapshot=20260308T211834Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:28:39Z snapshot=20260308T212836Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:38:41Z snapshot=20260308T213839Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:48:44Z snapshot=20260308T214841Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T21:58:46Z snapshot=20260308T215844Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:08:49Z snapshot=20260308T220846Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:18:51Z snapshot=20260308T221849Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:28:54Z snapshot=20260308T222851Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:38:56Z snapshot=20260308T223854Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:48:58Z snapshot=20260308T224856Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T22:59:01Z snapshot=20260308T225859Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T23:09:03Z snapshot=20260308T230901Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=778 predictor_rows=801
- 2026-03-08T23:29:42Z snapshot=20260308T232940Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=786 predictor_rows=809
- 2026-03-08T23:34:52Z snapshot=20260308T233449Z branch=split/2026-03-08 head=5a37a32ed2a6 mission_exit=0 tracked=8/8 legacy_imported=786 predictor_rows=809
