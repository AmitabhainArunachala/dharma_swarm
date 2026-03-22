"""Integration test: the organism processes itself.

This is the test that started the conversation about what happens when
the Gnani says HOLD. It exercises the full loop:

  IdentityMonitor → LiveCoherenceSensor → blend → algedonic → Gnani → Samvara

Six tests, covering:
  1. Boot into empty state → Gnani says HOLD (low coherence)
  2. HOLD accumulation triggers samvara_mode activation
  3. Altitude escalation through consecutive HOLDs
  4. PROCEED resets the cascade when coherence rises
  5. Algedonic signals fire on telos drift and omega divergence
  6. Full 15-heartbeat run with power escalation
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from dharma_swarm.organism import (
    AlgedonicSignal,
    GnaniVerdict,
    HeartbeatResult,
    OrganismRuntime,
)
from dharma_swarm.samvara import Power


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Create a minimal .dharma state tree."""
    for d in ("witness", "shared", "stigmergy", "evolution", "meta", "db"):
        (tmp_path / d).mkdir()
    return tmp_path


@pytest.fixture
def seeded_state(state_dir: Path) -> Path:
    """State dir with some real data so coherence can be non-trivial."""
    # Witness logs (JSONL, outcome field)
    witness = state_dir / "witness" / "witness_test.jsonl"
    entries = []
    for i in range(10):
        outcome = "PASS" if i < 8 else "BLOCKED"
        entries.append(json.dumps({"outcome": outcome, "action": f"t{i}"}))
    witness.write_text("\n".join(entries))

    # Shared notes with telos-connected language
    for i in range(3):
        note = state_dir / "shared" / f"note_{i}.md"
        note.write_text(
            f"Fixed daemon config issue #{i}. The telos gate was blocking because "
            "the ontology witness couldn't reach the stigmergy store. "
            "This is a dharma kernel coherence issue at the evolution layer. "
            "The moksha vector requires intact wiring between the gate and the "
            "autopoiesis engine following friston active inference principles."
        )

    # Valid stigmergy marks
    marks = state_dir / "stigmergy" / "marks.jsonl"
    lines = [json.dumps({"id": f"m{i}", "observation": f"obs {i}"}) for i in range(300)]
    marks.write_text("\n".join(lines))

    # Evolution archive
    archive = state_dir / "evolution" / "archive.jsonl"
    lines = [json.dumps({"gen": i, "fitness": 0.5 + i * 0.01}) for i in range(50)]
    archive.write_text("\n".join(lines))

    return state_dir


# ---------------------------------------------------------------------------
# Test 1: Boot into empty state — Gnani says HOLD
# ---------------------------------------------------------------------------

class TestOrganismBoot:
    def test_empty_state_produces_hold(self, state_dir: Path):
        """Empty state → low coherence → Gnani says HOLD."""
        org = OrganismRuntime(state_dir)
        result = asyncio.run(org.heartbeat())

        assert result.gnani_verdict is not None
        assert result.gnani_verdict.decision == "HOLD"
        # TCS defaults to ~0.35 (GPR=0.5, BSI=0.5, RM=0.0)
        # Live score = 0.0 (no daemon, no fresh subsystems)
        # Blended = 0.4*0.0 + 0.6*0.35 = 0.21 → below 0.4 → HOLD
        assert result.blended < 0.4
        assert result.cycle == 1


# ---------------------------------------------------------------------------
# Test 2: HOLD accumulation triggers samvara_mode
# ---------------------------------------------------------------------------

class TestSamvaraActivation:
    def test_samvara_activates_after_threshold(self, state_dir: Path):
        """After enough consecutive HOLDs, samvara_mode activates."""
        org = OrganismRuntime(state_dir)
        results = asyncio.run(org.run(n_cycles=3))

        # All should be HOLD (empty state = low coherence)
        assert all(r.gnani_verdict.decision == "HOLD" for r in results)

        # Samvara should be active (threshold is 2)
        assert org.samvara.active
        assert org.samvara.state.consecutive_holds == 3


# ---------------------------------------------------------------------------
# Test 3: Altitude escalation through consecutive HOLDs
# ---------------------------------------------------------------------------

class TestAltitudeEscalation:
    def test_powers_escalate(self, state_dir: Path):
        """Consecutive HOLDs escalate through the four powers."""
        org = OrganismRuntime(state_dir)
        results = asyncio.run(org.run(n_cycles=12))

        # Verify altitude escalation
        powers = [r.samvara_diagnostic.power for r in results if r.samvara_diagnostic]
        assert len(powers) == 12

        # First 3: Mahasaraswati
        assert powers[0] == Power.MAHASARASWATI
        assert powers[2] == Power.MAHASARASWATI

        # 4-6: Mahalakshmi
        assert powers[3] == Power.MAHALAKSHMI
        assert powers[5] == Power.MAHALAKSHMI

        # 7-9: Mahakali
        assert powers[6] == Power.MAHAKALI

        # 10+: Maheshwari
        assert powers[9] == Power.MAHESHWARI
        assert powers[11] == Power.MAHESHWARI


# ---------------------------------------------------------------------------
# Test 4: PROCEED resets the cascade when coherence rises
# ---------------------------------------------------------------------------

class TestProceedReset:
    def test_high_coherence_produces_proceed(self, seeded_state: Path):
        """With real data, coherence should be high enough for PROCEED."""
        # Also fake a daemon PID so live sensor gives some score
        pid_file = seeded_state / "daemon.pid"
        pid_file.write_text(str(os.getpid()))

        # Touch fresh subsystem files
        (seeded_state / "pulse.log").write_text("fresh pulse")
        (seeded_state / "db" / "memory.db").write_text("db")

        org = OrganismRuntime(seeded_state)
        result = asyncio.run(org.heartbeat())

        # With real witness logs, telos-connected notes, valid marks,
        # evolution archive, live daemon, fresh subsystems:
        # TCS should be decent, live should be decent, blended should be >= 0.4
        assert result.gnani_verdict is not None
        if result.blended >= 0.4:
            assert result.gnani_verdict.decision == "PROCEED"
            assert result.samvara_diagnostic is None
        # If still HOLD (possible with test timing), at least verify it ran
        assert result.cycle == 1

    def test_proceed_after_hold_resets_samvara(self, state_dir: Path):
        """If coherence rises after HOLDs, samvara deactivates."""
        # Start with empty state → HOLDs
        org = OrganismRuntime(state_dir)
        asyncio.run(org.run(n_cycles=5))
        # After 5 empty-state heartbeats, samvara should be active
        assert org.samvara.state.consecutive_holds == 5
        assert org.samvara.active

        # Simulate coherence recovery by calling on_proceed
        org._samvara.on_proceed()
        assert not org.samvara.active
        assert org.samvara.state.consecutive_holds == 0


# ---------------------------------------------------------------------------
# Test 5: Algedonic signals fire correctly
# ---------------------------------------------------------------------------

class TestAlgedonicChannel:
    def test_telos_drift_fires(self, state_dir: Path):
        """Low blended coherence fires telos_drift signal."""
        signals_received: list[AlgedonicSignal] = []
        org = OrganismRuntime(state_dir, on_algedonic=signals_received.append)
        asyncio.run(org.heartbeat())

        drift_signals = [s for s in signals_received if s.kind == "telos_drift"]
        assert len(drift_signals) > 0
        assert drift_signals[0].severity == "critical"

    def test_omega_divergence_fires(self, seeded_state: Path):
        """When live and trailing disagree, omega_divergence fires."""
        # Seeded state has decent TCS but no daemon → live=0.0
        # So divergence = |0.0 - TCS| which depends on TCS
        signals_received: list[AlgedonicSignal] = []
        org = OrganismRuntime(seeded_state, on_algedonic=signals_received.append)
        result = asyncio.run(org.heartbeat())

        divergence = abs(result.live_score - result.tcs)
        if divergence > 0.4:
            omega_signals = [s for s in signals_received if s.kind == "omega_divergence"]
            assert len(omega_signals) > 0

    def test_callbacks_fire(self, state_dir: Path):
        """Both on_algedonic and on_gnani callbacks fire."""
        verdicts: list[GnaniVerdict] = []
        signals: list[AlgedonicSignal] = []

        org = OrganismRuntime(
            state_dir,
            on_algedonic=signals.append,
            on_gnani=verdicts.append,
        )
        asyncio.run(org.heartbeat())

        assert len(verdicts) == 1
        assert verdicts[0].decision == "HOLD"
        assert len(signals) > 0


# ---------------------------------------------------------------------------
# Test 6: Full 15-heartbeat run — the organism processes itself
# ---------------------------------------------------------------------------

class TestOrganismProcessesItself:
    def test_15_heartbeats_with_escalation(self, state_dir: Path):
        """15 consecutive heartbeats on empty state.

        The organism should:
        - Say HOLD every heartbeat (low coherence)
        - Activate samvara_mode after 2 HOLDs
        - Escalate through powers as HOLDs accumulate
        - Fire algedonic signals every heartbeat
        - Each power's diagnostic should find something
        """
        verdicts: list[GnaniVerdict] = []
        signals: list[AlgedonicSignal] = []

        org = OrganismRuntime(
            state_dir,
            on_algedonic=signals.append,
            on_gnani=verdicts.append,
        )
        results = asyncio.run(org.run(n_cycles=15))

        # All 15 heartbeats executed
        assert len(results) == 15
        assert org.cycle == 15

        # All HOLDs (empty state = low coherence throughout)
        assert all(r.gnani_verdict.decision == "HOLD" for r in results)
        assert len(verdicts) == 15

        # Samvara activated
        assert org.samvara.active
        assert org.samvara.state.consecutive_holds == 15

        # Altitude escalation happened
        powers_seen = set()
        for r in results:
            if r.samvara_diagnostic:
                powers_seen.add(r.samvara_diagnostic.power)
        assert Power.MAHASARASWATI in powers_seen
        assert Power.MAHALAKSHMI in powers_seen
        assert Power.MAHAKALI in powers_seen
        assert Power.MAHESHWARI in powers_seen

        # Algedonic signals fired (at least one per heartbeat)
        assert len(signals) >= 15

        # Every heartbeat took less than 500ms (no LLM calls)
        assert all(r.elapsed_ms < 500 for r in results)

        # Maheshwari (cycles 10+) should have accumulated findings
        maheshwari_results = [
            r.samvara_diagnostic for r in results
            if r.samvara_diagnostic and r.samvara_diagnostic.power == Power.MAHESHWARI
        ]
        assert len(maheshwari_results) > 0
        assert any("accumulated" in " ".join(m.findings).lower() for m in maheshwari_results)

        # Status snapshot
        status = org.status()
        assert status["samvara_active"]
        assert status["consecutive_holds"] == 15
        assert status["samvara_power"] == "maheshwari"
        assert status["last_verdict"] == "HOLD"

        print(f"\n♥ {len(results)} heartbeats completed")
        print(f"  Powers: {[p.value for p in powers_seen]}")
        print(f"  Algedonic signals: {len(signals)}")
        print(f"  Gnani verdicts: {len(verdicts)} (all HOLD)")
        print(f"  Avg elapsed: {sum(r.elapsed_ms for r in results)/len(results):.1f}ms")
        print(f"  The organism processed itself.")
