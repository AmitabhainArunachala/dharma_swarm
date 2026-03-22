"""Tests for dharma_swarm.identity -- S5 computational identity.

Tests the IdentityState model, TCS calculation, regime classification,
threat boost weight shifting, correction directives, and history tracking.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.identity import IdentityMonitor, IdentityState


# -- Model tests -----------------------------------------------------------


class TestIdentityStateModel:
    def test_identity_state_has_correct_fields(self) -> None:
        state = IdentityState()
        assert state.id  # non-empty auto-generated
        assert state.tcs == 0.5
        assert state.gpr == 0.5
        assert state.bsi == 0.5
        assert state.rm == 0.5
        assert state.regime == "stable"
        assert state.correction_issued is False
        assert state.timestamp is not None

    def test_identity_state_custom_values(self) -> None:
        state = IdentityState(tcs=0.9, gpr=0.95, bsi=0.85, rm=0.9, regime="stable")
        assert state.tcs == 0.9
        assert state.regime == "stable"

    def test_identity_state_serialization(self) -> None:
        state = IdentityState(tcs=0.42, regime="drifting", correction_issued=True)
        raw = state.model_dump_json()
        restored = IdentityState.model_validate_json(raw)
        assert restored.tcs == state.tcs
        assert restored.regime == state.regime
        assert restored.correction_issued is True


# -- Measurement defaults --------------------------------------------------


class TestMeasureDefaults:
    @pytest.mark.asyncio
    async def test_measure_defaults_no_data(self, tmp_path: Path) -> None:
        """With an empty state dir, all sub-metrics default to 0.5."""
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)
        state = await monitor.measure()

        # 0.35*0.5 + 0.35*0.5 + 0.30*0.5 = 0.5
        assert state.tcs == pytest.approx(0.5, abs=0.01)
        assert state.regime == "stable"


# -- Regime classification -------------------------------------------------


class TestRegimeClassification:
    @pytest.mark.asyncio
    async def test_regime_stable(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)
        state = await monitor.measure()
        assert state.tcs >= monitor.DRIFT_THRESHOLD
        assert state.regime == "stable"

    @pytest.mark.asyncio
    async def test_regime_drifting(self, tmp_path: Path) -> None:
        """Force low sub-metrics by creating witness logs that all fail."""
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        # Create witness JSONL logs that all fail (decision = "block")
        for i in range(10):
            (witness_dir / f"gate_{i}.jsonl").write_text(
                json.dumps({"decision": "block"}) + "\n"
            )

        monitor = IdentityMonitor(state_dir=state_dir)
        # GPR = 0/10 = 0.0, BSI = 0.5 (no shared), RM = 0.5 (no archive)
        # TCS = 0.35*0.0 + 0.35*0.5 + 0.30*0.5 = 0.175 + 0.15 = 0.325
        state = await monitor.measure()
        assert state.tcs < monitor.DRIFT_THRESHOLD
        assert state.regime in ("drifting", "critical")

    @pytest.mark.asyncio
    async def test_regime_critical(self, tmp_path: Path) -> None:
        """Force all metrics near zero."""
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        # All gates fail
        for i in range(10):
            (witness_dir / f"gate_{i}.jsonl").write_text(
                json.dumps({"decision": "block"}) + "\n"
            )

        # Empty shared dir (BSI will try to read but find nothing -> 0.5)
        shared_dir = state_dir / "shared"
        shared_dir.mkdir(parents=True)

        # Empty evolution archive
        evo_dir = state_dir / "evolution"
        evo_dir.mkdir(parents=True)
        (evo_dir / "archive.jsonl").write_text("")

        monitor = IdentityMonitor(state_dir=state_dir)
        state = await monitor.measure()
        # GPR = 0.0, BSI = 0.5 (no notes), RM depends on empty dirs
        # This tests that regime is at least drifting
        assert state.tcs < monitor.DRIFT_THRESHOLD


# -- Threat boost ----------------------------------------------------------


class TestThreatBoost:
    @pytest.mark.asyncio
    async def test_threat_boost_shifts_weights(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)

        # Measure without boost
        normal = await monitor.measure(threat_boost=False)

        # Measure with boost -- same sub-metrics (all default 0.5)
        # but weights shift, so TCS should still be ~0.5 since all = 0.5
        boosted = await monitor.measure(threat_boost=True)

        # With all sub-metrics equal at 0.5, weight shift doesn't change TCS
        assert normal.tcs == pytest.approx(boosted.tcs, abs=0.01)

    @pytest.mark.asyncio
    async def test_threat_boost_favors_rm(self, tmp_path: Path) -> None:
        """When RM is high and others are low, threat boost should raise TCS."""
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        # All gates fail -> GPR = 0
        for i in range(5):
            (witness_dir / f"gate_{i}.jsonl").write_text(
                json.dumps({"decision": "block"}) + "\n"
            )

        # High RM: many archive entries
        evo_dir = state_dir / "evolution"
        evo_dir.mkdir(parents=True)
        lines = [json.dumps({"entry": i}) for i in range(200)]
        (evo_dir / "archive.jsonl").write_text("\n".join(lines))

        # Many shared notes for RM
        shared_dir = state_dir / "shared"
        shared_dir.mkdir(parents=True)
        for i in range(60):
            (shared_dir / f"note_{i}.md").write_text(f"Note {i}")

        monitor = IdentityMonitor(state_dir=state_dir)

        normal = await monitor.measure(threat_boost=False)
        # Reset history for clean comparison
        monitor._history.clear()
        boosted = await monitor.measure(threat_boost=True)

        # With GPR=0, high RM, threat boost gives more weight to RM
        assert boosted.tcs >= normal.tcs


# -- Correction directive --------------------------------------------------


class TestCorrectionDirective:
    @pytest.mark.asyncio
    async def test_correction_issued_on_drift(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        # All gates blocked -> GPR = 0 -> drifting
        for i in range(10):
            (witness_dir / f"gate_{i}.jsonl").write_text(
                json.dumps({"decision": "block"}) + "\n"
            )

        monitor = IdentityMonitor(state_dir=state_dir)
        state = await monitor.measure()

        assert state.correction_issued is True
        focus_path = state_dir / ".FOCUS"
        assert focus_path.exists()

        content = focus_path.read_text()
        assert "FOCUS CORRECTION" in content
        assert "Weakest dimension" in content

    def test_issue_correction_directly(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)

        result = monitor._issue_correction(tcs=0.3, gpr=0.1, bsi=0.5, rm=0.4)
        assert result is True

        focus = (state_dir / ".FOCUS").read_text()
        assert "GPR" in focus  # GPR is weakest
        assert "gate failures" in focus.lower()


# -- History tracking ------------------------------------------------------


class TestHistoryTracking:
    @pytest.mark.asyncio
    async def test_history_accumulates(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)

        await monitor.measure()
        await monitor.measure()
        await monitor.measure()

        assert len(monitor.history) == 3

    @pytest.mark.asyncio
    async def test_current_tcs_returns_latest(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)

        # Before any measurement
        assert monitor.current_tcs == 0.5

        state = await monitor.measure()
        assert monitor.current_tcs == state.tcs

    @pytest.mark.asyncio
    async def test_history_is_copy(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        monitor = IdentityMonitor(state_dir=state_dir)

        await monitor.measure()
        h1 = monitor.history
        h1.append(IdentityState())  # mutate the copy
        assert len(monitor.history) == 1  # original unchanged


# -- GPR edge cases --------------------------------------------------------


class TestGprEdgeCases:
    @pytest.mark.asyncio
    async def test_gpr_no_witness_dir(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        # No witness dir at all
        monitor = IdentityMonitor(state_dir=state_dir)
        gpr = await monitor._measure_gpr()
        assert gpr == 0.5

    @pytest.mark.asyncio
    async def test_gpr_all_pass(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        for i in range(5):
            (witness_dir / f"gate_{i}.jsonl").write_text(
                json.dumps({"decision": "allow"}) + "\n"
            )

        monitor = IdentityMonitor(state_dir=state_dir)
        gpr = await monitor._measure_gpr()
        assert gpr == 1.0

    @pytest.mark.asyncio
    async def test_gpr_mixed(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        witness_dir = state_dir / "witness"
        witness_dir.mkdir(parents=True)

        (witness_dir / "gate_0.jsonl").write_text(json.dumps({"decision": "allow"}) + "\n")
        (witness_dir / "gate_1.jsonl").write_text(json.dumps({"decision": "block"}) + "\n")
        (witness_dir / "gate_2.jsonl").write_text(json.dumps({"decision": "PASS"}) + "\n")
        (witness_dir / "gate_3.jsonl").write_text(json.dumps({"decision": "block"}) + "\n")

        monitor = IdentityMonitor(state_dir=state_dir)
        gpr = await monitor._measure_gpr()
        assert gpr == pytest.approx(0.5, abs=0.01)
