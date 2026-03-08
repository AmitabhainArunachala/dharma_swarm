# DGC Caffeine Loop — 25 Tasks

1. Verify `dgc status` baseline and capture snapshot.
2. Verify `dgc health-check` and record anomaly deltas.
3. Verify `dgc dharma status` signed kernel and gate counts.
4. Verify `dgc rag health --service rag`.
5. Verify `dgc rag health --service ingest`.
6. Verify `dgc flywheel jobs` service reachability.
7. Run provider core tests (`tests/test_providers.py`).
8. Run provider quality tests (`tests/test_providers_quality_track.py`).
9. Run integration tests (`tests/test_integrations_*.py`).
10. Run engine safety tests (`tests/test_engine_*.py`).
11. Run pulse + living-layer tests (`tests/test_pulse.py`).
12. Run CLI command-dispatch tests (`tests/test_dgc_cli.py`).
13. Run swarm smoke tests (`tests/test_swarm.py`).
14. Scan logs for recurrent provider failures.
15. Scan logs for recurrent gate violations.
16. Export current open tasks and status counts.
17. Refill task board if pending tasks fall below threshold.
18. Generate nightly findings note in `~/.dharma/shared/`.
19. Check RAG retrieval quality on one canonical query.
20. Check flywheel job lifecycle with one dry-run payload.
21. Capture performance deltas from previous loop.
22. Verify no split-brain runtime detected.
23. Verify canary/rollback status unchanged unless intentional.
24. Append nightly summary to `~/.dharma/logs/caffeine/`.
25. Emit final “handoff at 04:00 JST” report.

