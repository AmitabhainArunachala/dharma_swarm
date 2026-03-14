## Angle
System R_V should be an always-on vital: cheap behavioral contraction online, sparse geometric calibration offline, and explicit provenance so the daemon never mistakes a proxy for paper-grade R_V.

## What Exists
- [`RVReading` and thresholds](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L65) already give a clean mechanistic contract, and [`RVMeasurer`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L155) already isolates the expensive torch/HF path.
- [`EvolutionRVTracker.measure_cycle()`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L306) already persists per-cycle contraction plus fitness, so the repo already has a place to store system-level readings.
- [`ResearchBridge.compute_correlation()`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L268) and [`EvolutionBridge.correlate()`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L495) already cover the two validation modes: prompt-level research and cycle-level system tracking.
- [`SystemMonitor.check_health()`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L130) already computes the surrounding vitals, and [`SystemMonitor._detect_anomalies_from()`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L308) already calls [`SwarmRV.measure()`](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py#L276), which is the cheap colony-contraction substrate.
- [`tests/test_bridge.py`](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L321) gives strong `ResearchBridge` coverage, and [`tests/test_swarm_rv.py`](/Users/dhyana/dharma_swarm/tests/test_swarm_rv.py#L168) already validates the low-cost behavioral measurement path.

## Blind Spots
- [`HealthReport`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L66) has no first-class contraction fields, so system contraction is only visible if it trips an anomaly.
- The fallback in [`EvolutionRVTracker.measure_cycle()`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L354) uses `proposals_archived` alone; that is too coarse to distinguish productive closure from noisy convergence.
- [`bridge_summary()`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L649) knows how to summarize `ResearchBridge`, but not [`EvolutionBridge`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L455), so the live monitor cannot surface the cycle-level R_V story.
- I do not see `EvolutionBridge` coverage in [`tests/test_bridge.py`](/Users/dhyana/dharma_swarm/tests/test_bridge.py#L16), and I do not see a test for the `swarm_contraction_*` anomaly path in [`tests/test_monitor.py`](/Users/dhyana/dharma_swarm/tests/test_monitor.py#L309).

## Concrete Changes
- Prefer extending [`HealthReport`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L66) over creating `system_rv.py`: add `system_contraction: SwarmRVReading | None`, `system_contraction_source`, and `system_contraction_confidence`.
- Add `def __init__(self, trace_store: TraceStore, swarm_rv: SwarmRV | None = None) -> None` to [`SystemMonitor`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L106) and a single `async def measure_system_contraction(...)` helper so `check_health()` measures once and reuses that reading for both report and anomalies.
- Extend [`EvolutionRVTracker.measure_cycle()`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L306) to accept `swarm_reading: SwarmRVReading | None` and `health_report: HealthReport | None`; if no mechanistic read exists, persist a behavioral proxy bundle with `rv_source`, `confidence`, and the cheap features that produced it.
- Extend [`EvolutionBridge.add_record()`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L470) and [`EvolutionBridge.correlate()`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L495) so proxy, behavioral, and geometric signals are analyzed separately by default.
- Keep [`RVMeasurer.measure()`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L231) off the daemon hot path; run it only on schedule or after strong productive behavioral contraction.

## Tests
- I did not run the suite; these are the highest-value additions.
- In [`tests/test_bridge.py`](/Users/dhyana/dharma_swarm/tests/test_bridge.py), add `EvolutionBridge` coverage for proxy-only correlation, geometric-only correlation, mixed-source separation, and `format_for_archive()`.
- In [`tests/test_monitor.py`](/Users/dhyana/dharma_swarm/tests/test_monitor.py), add `test_check_health_includes_system_contraction`, `test_swarm_contraction_stuck_from_injected_reading`, and `test_missing_shared_notes_is_nonfatal`.
- In [`tests/test_rv.py`](/Users/dhyana/dharma_swarm/tests/test_rv.py), add `EvolutionRVTracker` tests for behavioral proxy recording, confidence/source persistence, and mocked geometric calibration.

## Risks
- Reusing the same `rv` field for mechanistic and behavioral quantities will create false certainty; provenance has to be explicit in storage and summaries.
- Putting [`RVMeasurer`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L155) inside frequent health checks is too expensive for the stated M3 Pro/18 GB target.
- [`SwarmRV`](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py#L109) only sees shared notes, not all useful work; contraction should be interpreted alongside failure, quality, and fitness.
- The current proxy in [`rv.py`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L354) can reward archived-proposal volume instead of real colony-level closure.

## Priority
- 1. Promote the existing [`SwarmRV`](/Users/dhyana/dharma_swarm/dharma_swarm/swarm_rv.py#L109) path into [`HealthReport`](/Users/dhyana/dharma_swarm/dharma_swarm/monitor.py#L66) so contraction becomes a cheap first-class vital.
- 2. Separate proxy, behavioral, and geometric provenance in [`EvolutionRVTracker`](/Users/dhyana/dharma_swarm/dharma_swarm/rv.py#L285) and [`EvolutionBridge`](/Users/dhyana/dharma_swarm/dharma_swarm/bridge.py#L455).
- 3. Add the missing `EvolutionBridge` and monitor-contraction tests.
- 4. Only then schedule sparse mechanistic calibration jobs for paper-grade validation.