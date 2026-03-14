"""Tests for checkpoint / resume / interrupt primitives.

Covers:
  - LoopCheckpoint serialization round-trip
  - CheckpointStore save/load/delete/list (atomic writes)
  - InterruptGate auto-approve, manual resolve, timeout
  - Filesystem interrupt transport (request/response files)
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dharma_swarm.checkpoint import (
    CheckpointStore,
    InterruptDecision,
    InterruptGate,
    InterruptRequest,
    InterruptResponse,
    LoopCheckpoint,
    cleanup_interrupt,
    read_pending_interrupts,
    write_interrupt_response,
)


# ---------------------------------------------------------------------------
# LoopCheckpoint
# ---------------------------------------------------------------------------


class TestLoopCheckpoint:
    def test_round_trip_json(self):
        cp = LoopCheckpoint(
            domain="code",
            cycle_id="abc123",
            iteration=5,
            current={"code": "print('hello')"},
            previous={"code": "print('hi')"},
            candidates=[{"code": "a"}, {"code": "b"}],
            best_score=0.87,
            fitness_trajectory=[0.5, 0.7, 0.87],
            eigenform_trajectory=[1.0, 0.3, 0.05],
            elapsed_seconds=12.5,
        )
        raw = cp.model_dump_json()
        restored = LoopCheckpoint(**json.loads(raw))
        assert restored.domain == "code"
        assert restored.iteration == 5
        assert restored.best_score == 0.87
        assert len(restored.candidates) == 2
        assert restored.fitness_trajectory == [0.5, 0.7, 0.87]

    def test_defaults(self):
        cp = LoopCheckpoint(domain="test", cycle_id="x")
        assert cp.iteration == 0
        assert cp.converged is False
        assert cp.interrupted is False
        assert cp.current is None
        assert cp.candidates == []


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------


class TestCheckpointStore:
    def test_save_load_delete(self, tmp_path):
        store = CheckpointStore(base_dir=tmp_path)
        cp = LoopCheckpoint(
            domain="code",
            cycle_id="cycle001",
            iteration=3,
            best_score=0.75,
        )

        # Save
        path = store.save(cp)
        assert path.exists()
        assert "code" in str(path)

        # Load
        loaded = store.load("code", "cycle001")
        assert loaded is not None
        assert loaded.iteration == 3
        assert loaded.best_score == 0.75

        # Delete
        assert store.delete("code", "cycle001") is True
        assert store.load("code", "cycle001") is None

    def test_list_checkpoints(self, tmp_path):
        store = CheckpointStore(base_dir=tmp_path)
        for i in range(3):
            cp = LoopCheckpoint(
                domain="code",
                cycle_id=f"cycle{i:03d}",
                iteration=i,
                best_score=i * 0.1,
            )
            store.save(cp)

        all_cps = store.list_checkpoints()
        assert len(all_cps) == 3

        code_cps = store.list_checkpoints("code")
        assert len(code_cps) == 3

        empty = store.list_checkpoints("nonexistent")
        assert len(empty) == 0

    def test_atomic_overwrite(self, tmp_path):
        store = CheckpointStore(base_dir=tmp_path)
        cp1 = LoopCheckpoint(domain="code", cycle_id="c1", iteration=1)
        cp2 = LoopCheckpoint(domain="code", cycle_id="c1", iteration=5)

        store.save(cp1)
        store.save(cp2)

        loaded = store.load("code", "c1")
        assert loaded is not None
        assert loaded.iteration == 5  # Overwritten

    def test_load_missing_returns_none(self, tmp_path):
        store = CheckpointStore(base_dir=tmp_path)
        assert store.load("nope", "nope") is None

    def test_delete_missing_returns_true(self, tmp_path):
        store = CheckpointStore(base_dir=tmp_path)
        assert store.delete("nope", "nope") is True  # missing_ok


# ---------------------------------------------------------------------------
# InterruptGate
# ---------------------------------------------------------------------------


class TestInterruptGate:
    @pytest.mark.asyncio
    async def test_auto_approve_no_callback(self):
        gate = InterruptGate(auto_approve=True)
        req = InterruptRequest(
            domain="code",
            phase="gate",
            reason="test",
        )
        resp = await gate.interrupt(req)
        assert resp.decision == InterruptDecision.APPROVE
        assert "auto-approved" in resp.reason

    @pytest.mark.asyncio
    async def test_manual_resolve(self):
        callback_called = []

        def on_interrupt(req: InterruptRequest):
            callback_called.append(req.id)

        gate = InterruptGate(callback=on_interrupt, auto_approve=False, timeout_seconds=5.0)
        req = InterruptRequest(domain="code", phase="gate", reason="needs review")

        async def resolve_after_delay():
            await asyncio.sleep(0.1)
            resp = InterruptResponse(
                request_id=req.id,
                decision=InterruptDecision.REJECT,
                reason="bad code",
            )
            assert gate.resolve(resp) is True

        task = asyncio.create_task(resolve_after_delay())
        response = await gate.interrupt(req)
        await task

        assert response.decision == InterruptDecision.REJECT
        assert response.reason == "bad code"
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_timeout_auto_approve(self):
        gate = InterruptGate(
            callback=lambda r: None,
            auto_approve=True,
            timeout_seconds=0.1,
        )
        req = InterruptRequest(domain="code", phase="gate", reason="test")
        resp = await gate.interrupt(req)
        assert resp.decision == InterruptDecision.APPROVE
        assert "timeout" in resp.reason

    @pytest.mark.asyncio
    async def test_timeout_auto_reject(self):
        gate = InterruptGate(
            callback=lambda r: None,
            auto_approve=False,
            timeout_seconds=0.1,
        )
        req = InterruptRequest(domain="code", phase="gate", reason="test")
        resp = await gate.interrupt(req)
        assert resp.decision == InterruptDecision.REJECT

    def test_pending_tracking(self):
        gate = InterruptGate()
        assert gate.pending_count == 0
        assert gate.pending_ids == []


# ---------------------------------------------------------------------------
# Filesystem interrupt transport
# ---------------------------------------------------------------------------


class TestInterruptFilesystem:
    def test_write_read_cleanup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.checkpoint.INTERRUPT_DIR", tmp_path
        )

        req = InterruptRequest(
            id="test123",
            domain="code",
            phase="gate",
            reason="needs review",
        )

        # Write request
        from dharma_swarm.checkpoint import _write_interrupt_request
        _write_interrupt_request(req)

        # Read pending
        pending = read_pending_interrupts()
        assert len(pending) == 1
        assert pending[0].id == "test123"

        # Write response
        resp = InterruptResponse(
            request_id="test123",
            decision=InterruptDecision.APPROVE,
        )
        write_interrupt_response(resp)

        # Now pending should be empty (response exists)
        pending = read_pending_interrupts()
        assert len(pending) == 0

        # Cleanup
        cleanup_interrupt("test123")
        assert not (tmp_path / "test123.request.json").exists()
        assert not (tmp_path / "test123.response.json").exists()
