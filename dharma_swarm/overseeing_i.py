"""The Overseeing I — meta-level wholistic intelligence for dharma_swarm.

Not a scanner. Not a daemon. The module that KNOWS:
- What exists in the system
- What's working and what's stalled
- What the world needs
- What we can uniquely provide
- What to do next

The primordial Shakti — always on-call, holding the whole picture,
guiding the swarm with authority and conviction.

Integration:
    graph_nexus.py           -- queries all 6 graphs for current state
    bridge_coordinator.py    -- cross-graph connections (5,000+ edges)
    concept_blast_radius.py  -- impact analysis for any concept
    telos_graph.py           -- strategic objectives and progress
    stigmergy.py             -- recent agent activity and hot paths
    cost_tracker.py          -- resource usage
    traces.py                -- recent agent decisions

Usage::

    oi = OverseeingI()
    assessment = await oi.assess()
    print(assessment.situation)     # What's happening
    print(assessment.gaps)          # What's missing
    print(assessment.next_move)     # What to do
    print(assessment.conviction)    # How confident (0-1)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Assessment:
    """The Overseeing I's view of the whole system at a moment in time."""

    timestamp: str = ""

    # What exists
    graph_health: dict[str, Any] = field(default_factory=dict)
    concept_count: int = 0
    bridge_count: int = 0
    objective_count: int = 0
    agent_traces: int = 0
    stigmergy_density: int = 0

    # What's working
    alive: list[str] = field(default_factory=list)
    strongest_pillars: list[str] = field(default_factory=list)
    hotspot_files: list[str] = field(default_factory=list)

    # What's stalled
    stalled: list[str] = field(default_factory=list)
    orphan_concepts: int = 0
    broken_bridges: list[str] = field(default_factory=list)

    # What to do
    situation: str = ""     # 2-3 sentence summary
    gaps: list[str] = field(default_factory=list)
    next_move: str = ""     # Single most important action
    conviction: float = 0.0  # 0-1, how confident in the next_move

    # Raw data
    telos_objectives: list[dict] = field(default_factory=list)
    blast_radius_top5: list[dict] = field(default_factory=list)
    recent_stigmergy: list[dict] = field(default_factory=list)
    cross_pillar_bridges: list[dict] = field(default_factory=list)

    duration_seconds: float = 0.0


class OverseeingI:
    """Meta-level wholistic intelligence.

    Probes every subsystem, synthesizes a unified assessment,
    and recommends the next move with conviction.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or Path.home() / ".dharma"

    async def assess(self) -> Assessment:
        """Run a full assessment of the system. Returns Assessment."""
        a = Assessment(timestamp=datetime.now(timezone.utc).isoformat())
        started = time.monotonic()

        # Probe all subsystems in fault-isolation
        await self._probe_graphs(a)
        await self._probe_bridges(a)
        await self._probe_telos(a)
        await self._probe_stigmergy(a)
        await self._probe_traces(a)
        await self._probe_lodestones(a)
        await self._probe_blast_radius(a)

        # Synthesize
        self._synthesize(a)

        a.duration_seconds = round(time.monotonic() - started, 3)
        return a

    # ── Probes ──────────────────────────────────────────────────

    async def _probe_graphs(self, a: Assessment) -> None:
        """Probe GraphNexus for overall health."""
        try:
            from dharma_swarm.graph_nexus import GraphNexus

            nexus = GraphNexus()
            await nexus.init()
            health = await nexus.health()
            a.graph_health = health.model_dump() if hasattr(health, "model_dump") else {"raw": str(health)}
            a.concept_count = a.graph_health.get("total_nodes", 0)

            # Check which graphs are alive
            for graph_name in ["semantic", "temporal", "catalytic", "lineage", "telos", "bridge"]:
                count = a.graph_health.get(f"{graph_name}_nodes", 0)
                if count and count > 0:
                    a.alive.append(f"{graph_name}({count})")
                else:
                    a.stalled.append(f"{graph_name}(empty)")

            await nexus.close()
        except Exception as exc:
            logger.debug("Graph probe failed: %s", exc)
            a.stalled.append(f"GraphNexus(error: {exc})")

    async def _probe_bridges(self, a: Assessment) -> None:
        """Probe BridgeRegistry for edge counts and health."""
        try:
            from dharma_swarm.bridge_coordinator import BridgeCoordinator

            bc = BridgeCoordinator(state_dir=self._state_dir)
            summary = await bc.summary()
            a.bridge_count = summary.get("total_bridges", 0)

            if a.bridge_count == 0:
                a.broken_bridges.append("bridges.db has 0 edges — discovery never ran")
            else:
                by_type = summary.get("by_edge_type", {})
                for etype, count in by_type.items():
                    if count > 0:
                        a.alive.append(f"bridge:{etype}({count})")

            # Cross-pillar bridges from lattice_test.db if available
            try:
                import sqlite3
                lattice_db = self._state_dir / "graphs" / "lattice_test.db"
                if lattice_db.exists():
                    conn = sqlite3.connect(str(lattice_db))
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("""
                        SELECT pillar_a, pillar_b, COUNT(*) as cnt
                        FROM cross_pillar_edges
                        GROUP BY pillar_a, pillar_b
                        ORDER BY cnt DESC LIMIT 10
                    """).fetchall()
                    a.cross_pillar_bridges = [
                        {"a": r["pillar_a"], "b": r["pillar_b"], "count": r["cnt"]}
                        for r in rows
                    ]
                    conn.close()
            except Exception:
                pass

        except Exception as exc:
            logger.debug("Bridge probe failed: %s", exc)

    async def _probe_telos(self, a: Assessment) -> None:
        """Probe TelosGraph for objectives and progress."""
        try:
            from dharma_swarm.telos_graph import TelosGraph

            tg = TelosGraph(telos_dir=self._state_dir / "telos")
            await tg.load()
            objectives = tg.list_objectives()
            a.objective_count = len(objectives)

            for obj in objectives:
                a.telos_objectives.append({
                    "name": obj.name,
                    "status": obj.status,
                    "progress": getattr(obj, "progress", 0),
                    "priority": getattr(obj, "priority", 0),
                })

            blocked = tg.blocked_objectives()
            if blocked:
                for b in blocked:
                    a.gaps.append(f"Blocked objective: {b.name}")

            active = tg.active_objectives()
            a.alive.append(f"telos({len(active)} active, {len(blocked)} blocked)")

        except Exception as exc:
            logger.debug("Telos probe failed: %s", exc)
            a.stalled.append(f"TelosGraph(error: {exc})")

    async def _probe_stigmergy(self, a: Assessment) -> None:
        """Probe stigmergy for recent activity."""
        try:
            from dharma_swarm.stigmergy import StigmergyStore

            store = StigmergyStore(
                marks_file=self._state_dir / "stigmergy" / "marks.jsonl",
            )
            recent = await store.read_marks(limit=10)
            a.stigmergy_density = len(recent)
            a.recent_stigmergy = [
                {
                    "agent": getattr(m, "agent", "unknown"),
                    "action": getattr(m, "action", ""),
                    "salience": getattr(m, "salience", 0),
                    "file": getattr(m, "file_path", ""),
                }
                for m in recent[:5]
            ]

            hot = await store.hot_paths(window_hours=24, min_marks=2)
            a.hotspot_files = [h.get("file_path", "") if isinstance(h, dict) else str(h) for h in hot[:5]]

        except Exception as exc:
            logger.debug("Stigmergy probe failed: %s", exc)

    async def _probe_traces(self, a: Assessment) -> None:
        """Probe traces for recent agent decisions."""
        try:
            from dharma_swarm.traces import TraceStore

            store = TraceStore(trace_dir=self._state_dir / "traces")
            recent = await store.get_recent(limit=20)
            a.agent_traces = len(recent)

        except Exception as exc:
            logger.debug("Traces probe failed: %s", exc)

    async def _probe_lodestones(self, a: Assessment) -> None:
        """Probe the lodestone library for content health."""
        lodestone_dir = Path.home() / "dharma_swarm" / "lodestones"
        if not lodestone_dir.exists():
            a.gaps.append("No lodestone library (~/dharma_swarm/lodestones/)")
            return

        md_files = list(lodestone_dir.rglob("*.md"))
        total_lines = 0
        for f in md_files:
            try:
                total_lines += sum(1 for _ in f.open())
            except Exception:
                pass

        if md_files:
            a.alive.append(f"lodestones({len(md_files)} files, {total_lines} lines)")
        else:
            a.gaps.append("Lodestone library exists but is empty")

        # Check pillar coverage
        pillars_covered = set()
        for f in md_files:
            parts = f.relative_to(lodestone_dir).parts
            if parts:
                pillars_covered.add(parts[0])
        a.strongest_pillars = sorted(pillars_covered)

    async def _probe_blast_radius(self, a: Assessment) -> None:
        """Check blast radius for a few key concepts (not full scan — too slow)."""
        try:
            from dharma_swarm.concept_blast_radius import ConceptBlastRadius

            br = ConceptBlastRadius(state_dir=self._state_dir)
            # Query specific high-value concepts instead of scanning all 4,000+
            key_concepts = ["autopoiesis", "stigmergy", "telos", "witness", "karma"]
            for name in key_concepts:
                try:
                    report = await br.compute_by_name(name)
                    if report.total_impact > 0:
                        a.blast_radius_top5.append({
                            "concept": report.concept_name or name,
                            "impact": report.total_impact,
                            "files": len(report.affected_code_files),
                            "concepts": len(report.affected_concepts),
                            "objectives": len(report.affected_objectives),
                        })
                except Exception:
                    continue
            # Sort by impact
            a.blast_radius_top5.sort(key=lambda x: x["impact"], reverse=True)
        except Exception as exc:
            logger.debug("Blast radius probe failed: %s", exc)

    # ── Synthesis ───────────────────────────────────────────────

    def _synthesize(self, a: Assessment) -> None:
        """Synthesize all probes into situation + gaps + next_move."""

        # Situation
        alive_count = len(a.alive)
        stalled_count = len(a.stalled)
        a.situation = (
            f"System has {alive_count} alive subsystems, {stalled_count} stalled. "
            f"{a.bridge_count} bridge edges connecting graphs. "
            f"{a.objective_count} telos objectives tracked. "
            f"{a.stigmergy_density} recent stigmergy marks."
        )

        # Gaps — what's missing or broken
        if a.bridge_count == 0:
            a.gaps.append("CRITICAL: No bridge edges — cross-graph intelligence is dark")
        if a.objective_count == 0:
            a.gaps.append("No telos objectives — the system has no strategic direction")
        if a.stigmergy_density == 0:
            a.gaps.append("No recent stigmergy — agents aren't communicating")
        if a.agent_traces == 0:
            a.gaps.append("No recent traces — no evidence of agent activity")

        # Check for pillar gaps from lattice data
        if a.cross_pillar_bridges:
            # Which pillars are connected vs isolated
            connected_pillars = set()
            for cpb in a.cross_pillar_bridges:
                connected_pillars.add(cpb["a"])
                connected_pillars.add(cpb["b"])
            # Known pillars that should be there
            expected = {"P07 Hofstadter", "P09 Dada Bhagwan", "P08 Aurobindo",
                       "P02 Kauffman", "P11 Beer", "P05 Deacon", "P06 Friston",
                       "P10 Varela", "P03 Jantsch", "P01 Levin"}
            missing = expected - connected_pillars
            if missing:
                a.gaps.append(f"Unconnected pillars: {', '.join(sorted(missing))}")

        # Next move — highest-leverage action
        if a.bridge_count == 0:
            a.next_move = "Run bridge discovery: BridgeCoordinator.discover_all()"
            a.conviction = 0.95
        elif a.objective_count == 0:
            a.next_move = "Define telos objectives: what is the system trying to achieve?"
            a.conviction = 0.9
        elif len(a.gaps) > 3:
            a.next_move = f"Address top gap: {a.gaps[0]}"
            a.conviction = 0.8
        elif a.blast_radius_top5:
            top = a.blast_radius_top5[0]
            a.next_move = (
                f"Deepen the highest-impact concept: {top['concept']} "
                f"(impact={top['impact']}, touches {top['files']} files)"
            )
            a.conviction = 0.7
        else:
            a.next_move = "System is healthy. Run the director for next vision."
            a.conviction = 0.6

    # ── Display ─────────────────────────────────────────────────

    def print_assessment(self, a: Assessment) -> None:
        """Print a formatted assessment to stdout."""
        print(f"\n╔══════════════════════════════════════════════════════════════╗")
        print(f"║  THE OVERSEEING I — System Assessment                        ║")
        print(f"║  {a.timestamp[:19]:<30}                           ║")
        print(f"╚══════════════════════════════════════════════════════════════╝")

        print(f"\n  SITUATION")
        print(f"  {a.situation}")

        print(f"\n  ALIVE ({len(a.alive)})")
        for item in a.alive:
            print(f"    + {item}")

        if a.stalled:
            print(f"\n  STALLED ({len(a.stalled)})")
            for item in a.stalled:
                print(f"    - {item}")

        if a.gaps:
            print(f"\n  GAPS ({len(a.gaps)})")
            for g in a.gaps:
                print(f"    ! {g}")

        if a.blast_radius_top5:
            print(f"\n  HIGHEST-IMPACT CONCEPTS")
            for b in a.blast_radius_top5:
                print(f"    {b['concept']:<30} impact={b['impact']} files={b['files']}")

        if a.telos_objectives:
            print(f"\n  TELOS OBJECTIVES ({len(a.telos_objectives)})")
            for obj in a.telos_objectives[:8]:
                print(f"    [{obj['status']:<10}] {obj['name']}")

        if a.cross_pillar_bridges:
            print(f"\n  CROSS-PILLAR LATTICE")
            for cpb in a.cross_pillar_bridges[:5]:
                print(f"    {cpb['a']:<25} ←→ {cpb['b']:<25} ({cpb['count']} files)")

        conviction_bar = "█" * int(a.conviction * 10) + "░" * (10 - int(a.conviction * 10))
        print(f"\n  NEXT MOVE (conviction: {conviction_bar} {a.conviction:.0%})")
        print(f"  → {a.next_move}")

        print(f"\n  Duration: {a.duration_seconds:.2f}s")
