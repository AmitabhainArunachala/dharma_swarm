"""Tests for signal_bus.py — inter-loop temporal coherence."""
import time
import pytest
from dharma_swarm.signal_bus import SignalBus


class TestSignalBus:
    def test_emit_and_drain_all(self):
        bus = SignalBus()
        bus.emit({"type": "A", "val": 1})
        bus.emit({"type": "B", "val": 2})
        events = bus.drain()
        assert len(events) == 2
        assert events[0]["type"] == "A"
        assert events[1]["type"] == "B"
        # drained — second call returns empty
        assert bus.drain() == []

    def test_drain_by_type(self):
        bus = SignalBus()
        bus.emit({"type": "ANOMALY_DETECTED"})
        bus.emit({"type": "CASCADE_EIGENFORM_DISTANCE"})
        bus.emit({"type": "ANOMALY_DETECTED"})
        anomalies = bus.drain(["ANOMALY_DETECTED"])
        assert len(anomalies) == 2
        # CASCADE should still be there
        remaining = bus.drain()
        assert len(remaining) == 1
        assert remaining[0]["type"] == "CASCADE_EIGENFORM_DISTANCE"

    def test_ttl_expiry(self):
        bus = SignalBus(ttl_seconds=0.1)
        bus.emit({"type": "OLD"})
        time.sleep(0.15)
        events = bus.drain()
        assert len(events) == 0

    def test_peek_non_destructive(self):
        bus = SignalBus()
        bus.emit({"type": "X"})
        peeked = bus.peek()
        assert len(peeked) == 1
        # still there after peek
        drained = bus.drain()
        assert len(drained) == 1

    def test_pending_count(self):
        bus = SignalBus()
        assert bus.pending_count == 0
        bus.emit({"type": "A"})
        bus.emit({"type": "B"})
        assert bus.pending_count == 2

    def test_clear(self):
        bus = SignalBus()
        bus.emit({"type": "A"})
        bus.clear()
        assert bus.pending_count == 0
        assert bus.drain() == []

    def test_drain_mixed_types(self):
        bus = SignalBus()
        bus.emit({"type": "FITNESS_IMPROVED"})
        bus.emit({"type": "FITNESS_DEGRADED"})
        bus.emit({"type": "RECOGNITION_UPDATED"})
        improved = bus.drain(["FITNESS_IMPROVED", "FITNESS_DEGRADED"])
        assert len(improved) == 2
        rest = bus.drain()
        assert len(rest) == 1

    def test_empty_drain(self):
        bus = SignalBus()
        assert bus.drain() == []
        assert bus.drain(["ANYTHING"]) == []
