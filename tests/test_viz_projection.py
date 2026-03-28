"""Tests for visualization projection layer."""

from __future__ import annotations

import time
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.viz_projection import (
    GraphEdge,
    GraphEvent,
    GraphNode,
    GraphSnapshot,
    TimelineSlice,
    VizProjector,
)


class TestModels:

    def test_graph_node_defaults(self):
        node = GraphNode(id="test", label="Test")
        assert node.node_type == "unknown"
        assert node.status == "unknown"
        assert node.metrics == {}

    def test_graph_edge(self):
        edge = GraphEdge(id="e1", source="a", target="b", edge_type="data_flow")
        assert edge.weight == 1.0

    def test_graph_event(self):
        event = GraphEvent(event_type="mark_added", node_id="agent:test")
        assert event.timestamp > 0
        assert event.data == {}

    def test_graph_snapshot(self):
        snap = GraphSnapshot(
            nodes=[GraphNode(id="n1", label="N1")],
            edges=[GraphEdge(id="e1", source="n1", target="n2")],
            summary={"alive_count": 1},
        )
        assert len(snap.nodes) == 1
        assert snap.summary["alive_count"] == 1

    def test_timeline_slice(self):
        ts = TimelineSlice(
            start=1.0, end=2.0,
            events=[GraphEvent(event_type="test")],
        )
        assert len(ts.events) == 1
        assert ts.snapshot_before is None

    def test_serialization_roundtrip(self):
        node = GraphNode(
            id="agent:test", label="Test Agent",
            node_type="agent", status="alive",
            metrics={"fitness": 0.8},
        )
        data = node.model_dump()
        restored = GraphNode.model_validate(data)
        assert restored.id == "agent:test"
        assert restored.metrics["fitness"] == 0.8


class TestVizProjector:

    def test_build_snapshot_empty_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot()
            assert isinstance(snapshot, GraphSnapshot)
            assert snapshot.summary.get("total_nodes", 0) >= 0
            # Should always have subsystem nodes
            subsystem_nodes = [n for n in snapshot.nodes if n.node_type == "subsystem"]
            assert len(subsystem_nodes) == 8  # Fixed topology

    def test_subsystem_edges(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot()
            flow_edges = [e for e in snapshot.edges if e.edge_type in ("data_flow", "dependency")]
            assert len(flow_edges) == 5  # Fixed topology edges

    def test_build_snapshot_with_agents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock agent identity
            agents_dir = Path(tmpdir) / "agents" / "test-agent"
            agents_dir.mkdir(parents=True)
            import json
            (agents_dir / "identity.json").write_text(json.dumps({
                "name": "test-agent",
                "status": "alive",
                "level": 3,
                "xp": 150.0,
                "model": "opus",
                "role": "researcher",
            }))

            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot()
            agent_nodes = [n for n in snapshot.nodes if n.node_type == "agent"]
            assert len(agent_nodes) == 1
            assert agent_nodes[0].label == "test-agent"
            assert agent_nodes[0].status == "alive"
            assert agent_nodes[0].metrics["level"] == 3.0

    def test_build_snapshot_with_stigmergy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock stigmergy marks
            stig_dir = Path(tmpdir) / "stigmergy"
            stig_dir.mkdir(parents=True)
            import json
            marks = [
                {"id": "m1", "agent": "agent-1", "file_path": "foo.py",
                 "observation": "Found a bug", "salience": 0.8, "action": "scan"},
            ]
            with open(stig_dir / "marks.jsonl", "w") as f:
                for m in marks:
                    f.write(json.dumps(m) + "\n")

            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot()
            pheromone_edges = [e for e in snapshot.edges if e.edge_type == "pheromone"]
            assert len(pheromone_edges) == 1
            assert pheromone_edges[0].weight == 0.8

    def test_recent_events_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            events = projector.recent_events(since=0.0)
            assert isinstance(events, list)

    def test_recent_events_with_stigmergy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stig_dir = Path(tmpdir) / "stigmergy"
            stig_dir.mkdir(parents=True)
            import json
            now = time.time()
            marks = [
                {"id": "m1", "agent": "a1", "file_path": "f.py",
                 "observation": "test", "salience": 0.5,
                 "timestamp": now - 100},
                {"id": "m2", "agent": "a2", "file_path": "g.py",
                 "observation": "test2", "salience": 0.9,
                 "timestamp": now - 50},
            ]
            with open(stig_dir / "marks.jsonl", "w") as f:
                for m in marks:
                    f.write(json.dumps(m) + "\n")

            projector = VizProjector(state_dir=Path(tmpdir))
            events = projector.recent_events(since=now - 200)
            assert len(events) == 2
            assert events[0].event_type == "mark_added"

    def test_build_timeline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            now = time.time()
            timeline = projector.build_timeline(start=now - 3600, end=now)
            assert isinstance(timeline, TimelineSlice)
            assert timeline.start == now - 3600
            assert timeline.snapshot_after is not None

    def test_node_detail_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            # Subsystem nodes should always be findable
            node = projector.node_detail("sub:kernel")
            assert node is not None
            assert node.label == "Dharma Kernel"

    def test_node_detail_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            node = projector.node_detail("nonexistent:node")
            assert node is None

    def test_max_nodes_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot(max_nodes=5)
            # Should still have subsystem nodes (they don't count against agent cap)
            assert len(snapshot.nodes) <= 20  # subsystems + limited agents

    def test_summary_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projector = VizProjector(state_dir=Path(tmpdir))
            snapshot = projector.build_snapshot()
            assert "alive_count" in snapshot.summary
            assert "stuck_count" in snapshot.summary
            assert "total_nodes" in snapshot.summary
            assert "total_edges" in snapshot.summary
