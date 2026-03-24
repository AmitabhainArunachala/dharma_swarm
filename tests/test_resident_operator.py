"""Tests for dharma_swarm.resident_operator."""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.resident_operator import OPERATOR_PORT, ResidentOperator


def test_operator_port():
    assert OPERATOR_PORT == 8420


class TestResidentOperator:
    def test_init_defaults(self):
        op = ResidentOperator()
        assert op.state_dir == Path.home() / ".dharma"
        assert op.session_id == "resident_operator"
        assert op.bridge_agent_id == "operator_bridge"
        assert op._running is False

    def test_init_custom_state_dir(self, tmp_path: Path):
        op = ResidentOperator(state_dir=tmp_path / "custom")
        assert op.state_dir == tmp_path / "custom"

    def test_runtime_contracts_before_start_raises(self):
        op = ResidentOperator()
        with pytest.raises(RuntimeError, match="not been started"):
            op.runtime_contracts()

    @pytest.mark.asyncio
    async def test_start_and_stop(self, tmp_path: Path):
        op = ResidentOperator(state_dir=tmp_path / "operator_state")
        await op.start()
        assert op._running is True
        # Runtime contracts available after start
        contracts = op.runtime_contracts()
        assert contracts is not None
        await op.stop()
        assert op._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self, tmp_path: Path):
        op = ResidentOperator(state_dir=tmp_path / "op")
        await op.start()
        await op.start()  # Should not raise
        assert op._running is True
        await op.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_idempotent(self, tmp_path: Path):
        op = ResidentOperator(state_dir=tmp_path / "op")
        await op.start()
        await op.stop()
        await op.stop()  # Should not raise
        assert op._running is False

    def test_exports(self):
        from dharma_swarm import resident_operator
        assert "OPERATOR_PORT" in resident_operator.__all__
        assert "ResidentOperator" in resident_operator.__all__
