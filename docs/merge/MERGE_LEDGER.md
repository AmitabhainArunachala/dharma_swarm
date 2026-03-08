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

## Session Log

- Bootstrapped ledger. Use `scripts/merge_snapshot.py` to append factual checkpoints.

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
