"""Visualization data plane — projection from live state to renderable contracts.

One data plane, multiple lenses. This module normalizes data from the
telemetry substrate, stigmergy store, trajectory collector, and economic
engine into a single set of models that any visualization lens can consume.

Models:
    GraphNode, GraphEdge, GraphEvent, GraphSnapshot, TimelineSlice

The VizProjector reads from:
    - TelemetryPlaneStore (agent_identity, reward_ledger, reputation)
    - StigmergyStore (marks, hot paths)
    - TrajectoryCollector (active/completed trajectories)
    - EconomicEngine (revenue, expenses, budget)
    - Selected graph enrichments via GraphNexus (concept frequency, not full topology)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Renderable contracts
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A node in the visualization graph."""
    id: str
    label: str = ""
    node_type: str = "unknown"  # agent | task | subsystem | file | graph
    status: str = "unknown"     # alive | idle | stuck | dead | pending
    metrics: dict[str, float] = Field(default_factory=dict)
    position: Optional[dict[str, float]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """An edge in the visualization graph."""
    id: str
    source: str
    target: str
    edge_type: str = "default"  # data_flow | dependency | pheromone | trajectory
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEvent(BaseModel):
    """A discrete event for timeline/streaming."""
    timestamp: float = Field(default_factory=time.time)
    event_type: str = ""  # mark_added | trajectory_completed | agent_status | expense | revenue
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class GraphSnapshot(BaseModel):
    """Point-in-time visualization state."""
    timestamp: float = Field(default_factory=time.time)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class TimelineSlice(BaseModel):
    """A time range with events and bounding snapshots."""
    start: float = 0.0
    end: float = 0.0
    events: list[GraphEvent] = Field(default_factory=list)
    snapshot_before: Optional[GraphSnapshot] = None
    snapshot_after: Optional[GraphSnapshot] = None


# ---------------------------------------------------------------------------
# Projector
# ---------------------------------------------------------------------------


class VizProjector:
    """Projects live system state into renderable GraphSnapshots.

    Reads from multiple data sources via lazy imports to avoid
    coupling. Each source is optional — if unavailable, that
    section of the snapshot is simply empty.

    Usage:
        projector = VizProjector()
        snapshot = projector.build_snapshot()
        events = projector.recent_events(since=time.time() - 3600)
        timeline = projector.build_timeline(start, end)
    """

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")

    def build_snapshot(self, max_nodes: int = 200) -> GraphSnapshot:
        """Build a current-state snapshot from all available sources."""
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        summary: dict[str, Any] = {}

        # 1. Agents from telemetry plane
        agent_nodes, agent_summary = self._project_agents()
        nodes.extend(agent_nodes[:max_nodes // 3])
        summary.update(agent_summary)

        # 2. Subsystems (fixed topology)
        subsystem_nodes, subsystem_edges = self._project_subsystems()
        nodes.extend(subsystem_nodes)
        edges.extend(subsystem_edges)

        # 3. Stigmergy marks as edges
        stig_edges, stig_summary = self._project_stigmergy()
        edges.extend(stig_edges[:max_nodes])
        summary.update(stig_summary)

        # 4. Trajectories
        traj_summary = self._project_trajectories()
        summary.update(traj_summary)

        # 5. Economics
        econ_summary = self._project_economics()
        summary.update(econ_summary)

        # Compute aggregate summary
        alive = sum(1 for n in nodes if n.status == "alive")
        stuck = sum(1 for n in nodes if n.status == "stuck")
        idle = sum(1 for n in nodes if n.status == "idle")
        summary["alive_count"] = alive
        summary["stuck_count"] = stuck
        summary["idle_count"] = idle
        summary["total_nodes"] = len(nodes)
        summary["total_edges"] = len(edges)

        return GraphSnapshot(
            nodes=nodes,
            edges=edges,
            summary=summary,
        )

    def recent_events(self, since: float = 0.0, limit: int = 100) -> list[GraphEvent]:
        """Collect recent events from all sources since a timestamp."""
        events: list[GraphEvent] = []

        # Stigmergy marks as events
        events.extend(self._stigmergy_events(since, limit))

        # Trajectory completions as events
        events.extend(self._trajectory_events(since, limit))

        # Economic transactions as events
        events.extend(self._economic_events(since, limit))

        # Sort by timestamp, limit
        events.sort(key=lambda e: e.timestamp)
        return events[-limit:]

    def build_timeline(self, start: float, end: float, max_events: int = 200) -> TimelineSlice:
        """Build a timeline slice for playback."""
        all_events = self.recent_events(since=start, limit=max_events * 2)
        in_range = [e for e in all_events if start <= e.timestamp <= end][:max_events]

        return TimelineSlice(
            start=start,
            end=end,
            events=in_range,
            snapshot_after=self.build_snapshot(max_nodes=100),
        )

    def node_detail(self, node_id: str) -> Optional[GraphNode]:
        """Get detailed info for a single node."""
        snapshot = self.build_snapshot(max_nodes=500)
        for node in snapshot.nodes:
            if node.id == node_id:
                return node
        return None

    # -- Source projectors -------------------------------------------------

    def _project_agents(self) -> tuple[list[GraphNode], dict[str, Any]]:
        """Project agent state from telemetry or agent registry."""
        nodes = []
        summary: dict[str, Any] = {}
        try:
            agents_dir = self._state_dir / "agents"
            if agents_dir.exists():
                import json
                for agent_dir in agents_dir.iterdir():
                    if not agent_dir.is_dir():
                        continue
                    identity_file = agent_dir / "identity.json"
                    if identity_file.exists():
                        try:
                            identity = json.loads(identity_file.read_text())
                            status = identity.get("status", "idle")
                            nodes.append(GraphNode(
                                id=f"agent:{identity.get('name', agent_dir.name)}",
                                label=identity.get("name", agent_dir.name),
                                node_type="agent",
                                status=status if status in ("alive", "idle", "stuck", "dead") else "idle",
                                metrics={
                                    "level": float(identity.get("level", 1)),
                                    "xp": float(identity.get("xp", 0)),
                                },
                                metadata={k: v for k, v in identity.items()
                                          if k in ("model", "provider", "role", "specialization")},
                            ))
                        except (json.JSONDecodeError, OSError):
                            continue
            summary["agent_count"] = len(nodes)
        except Exception:
            logger.debug("Agent projection failed", exc_info=True)
        return nodes, summary

    def _project_subsystems(self) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Project fixed subsystem topology."""
        subsystems = [
            ("sub:stigmergy", "Stigmergy Store", "subsystem"),
            ("sub:evolution", "DarwinEngine", "subsystem"),
            ("sub:trajectories", "Trajectory Collector", "subsystem"),
            ("sub:economics", "Economic Engine", "subsystem"),
            ("sub:sandbox", "Docker Sandbox", "subsystem"),
            ("sub:kernel", "Dharma Kernel", "subsystem"),
            ("sub:corpus", "Dharma Corpus", "subsystem"),
            ("sub:gates", "Telos Gates", "subsystem"),
        ]
        nodes = [
            GraphNode(id=sid, label=label, node_type=ntype, status="alive")
            for sid, label, ntype in subsystems
        ]
        # Data flow edges between subsystems
        flows = [
            ("sub:trajectories", "sub:evolution", "data_flow"),
            ("sub:evolution", "sub:stigmergy", "data_flow"),
            ("sub:economics", "sub:sandbox", "data_flow"),
            ("sub:gates", "sub:kernel", "dependency"),
            ("sub:sandbox", "sub:trajectories", "data_flow"),
        ]
        edges = [
            GraphEdge(id=f"flow:{s}->{t}", source=s, target=t, edge_type=et)
            for s, t, et in flows
        ]
        return nodes, edges

    def _project_stigmergy(self) -> tuple[list[GraphEdge], dict[str, Any]]:
        """Project recent stigmergy marks as graph edges."""
        edges = []
        summary: dict[str, Any] = {"stigmergy_marks": 0}
        try:
            marks_file = self._state_dir / "stigmergy" / "marks.jsonl"
            if marks_file.exists():
                import json
                count = 0
                # Read last 100 marks (tail of file)
                lines = marks_file.read_text().strip().split("\n")
                for line in lines[-100:]:
                    if not line.strip():
                        continue
                    try:
                        mark = json.loads(line)
                        agent = mark.get("agent", "unknown")
                        file_path = mark.get("file_path", "")
                        if agent and file_path:
                            edges.append(GraphEdge(
                                id=f"mark:{mark.get('id', count)}",
                                source=f"agent:{agent}",
                                target=f"file:{file_path[:80]}",
                                edge_type="pheromone",
                                weight=float(mark.get("salience", 0.5)),
                                metadata={
                                    "observation": mark.get("observation", "")[:200],
                                    "action": mark.get("action", ""),
                                },
                            ))
                        count += 1
                    except (json.JSONDecodeError, ValueError):
                        continue
                summary["stigmergy_marks"] = count
        except Exception:
            logger.debug("Stigmergy projection failed", exc_info=True)
        return edges, summary

    def _project_trajectories(self) -> dict[str, Any]:
        """Project trajectory statistics."""
        summary: dict[str, Any] = {}
        try:
            from dharma_swarm.trajectory_collector import get_collector
            collector = get_collector()
            stats = collector.stats()
            summary["trajectories_active"] = stats.get("active_trajectories", 0)
            summary["trajectories_completed"] = stats.get("completed_trajectories", 0)
        except Exception:
            logger.debug("Trajectory projection failed", exc_info=True)
        return summary

    def _project_economics(self) -> dict[str, Any]:
        """Project economic state."""
        summary: dict[str, Any] = {}
        try:
            from dharma_swarm.economic_engine import EconomicEngine
            engine = EconomicEngine()
            snap = engine.snapshot()
            summary["revenue_total"] = snap.total_revenue
            summary["expense_total"] = snap.total_expenses
            summary["net_balance"] = snap.net_balance
            summary["training_budget"] = snap.budget.training
        except Exception:
            logger.debug("Economics projection failed", exc_info=True)
        return summary

    # -- Event projectors --------------------------------------------------

    def _stigmergy_events(self, since: float, limit: int) -> list[GraphEvent]:
        """Convert stigmergy marks to events."""
        events = []
        try:
            import json
            marks_file = self._state_dir / "stigmergy" / "marks.jsonl"
            if not marks_file.exists():
                return events
            lines = marks_file.read_text().strip().split("\n")
            for line in lines[-limit * 2:]:
                if not line.strip():
                    continue
                try:
                    mark = json.loads(line)
                    ts = _parse_timestamp(mark.get("timestamp", ""))
                    if ts and ts > since:
                        events.append(GraphEvent(
                            timestamp=ts,
                            event_type="mark_added",
                            node_id=f"agent:{mark.get('agent', '')}",
                            data={
                                "observation": mark.get("observation", "")[:200],
                                "salience": mark.get("salience", 0),
                                "file_path": mark.get("file_path", ""),
                            },
                        ))
                except (json.JSONDecodeError, ValueError):
                    continue
        except Exception:
            logger.debug("Stigmergy events failed", exc_info=True)
        return events[:limit]

    def _trajectory_events(self, since: float, limit: int) -> list[GraphEvent]:
        """Convert completed trajectories to events."""
        events = []
        try:
            from dharma_swarm.trajectory_collector import get_collector
            trajectories = get_collector().load_trajectories(limit=limit)
            for traj in trajectories:
                if traj.completed_at and traj.completed_at > since:
                    events.append(GraphEvent(
                        timestamp=traj.completed_at,
                        event_type="trajectory_completed",
                        node_id=f"agent:{traj.agent_id}",
                        data={
                            "task": traj.task_title[:100],
                            "success": traj.outcome.success,
                            "chunks": traj.chunk_count,
                            "tokens": traj.total_tokens,
                        },
                    ))
        except Exception:
            logger.debug("Trajectory events failed", exc_info=True)
        return events[:limit]

    def _economic_events(self, since: float, limit: int) -> list[GraphEvent]:
        """Convert economic transactions to events."""
        events = []
        try:
            from dharma_swarm.economic_engine import EconomicEngine
            engine = EconomicEngine()
            for tx in engine._transactions:
                if tx.timestamp > since:
                    events.append(GraphEvent(
                        timestamp=tx.timestamp,
                        event_type="revenue" if tx.type.value == "revenue" else "expense",
                        data={
                            "amount": tx.amount_usd,
                            "source": tx.source,
                            "description": tx.description[:200],
                        },
                    ))
        except Exception:
            logger.debug("Economic events failed", exc_info=True)
        return events[:limit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(value: Any) -> Optional[float]:
    """Parse various timestamp formats to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            from datetime import datetime, timezone
            # Try ISO format
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, AttributeError):
            pass
    return None
