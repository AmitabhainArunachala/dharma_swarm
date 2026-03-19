"""Curiosity Engine — intelligent exploration driver for dharma_swarm.

Phase 4 of the 1000x Stigmergy plan.  Three drivers identify where the
system should look next:

  1. Semantic Gaps — structurally important files with low understanding
  2. Salience Gradients — follow stigmergy heat toward high-signal regions
  3. Mission Frontiers — explore near active goals (R_V, swarm, Jagat Kalyan)

Reads directly from:
  - file_profiles.db  (ProfileEngine's SQLite store)
  - knowledge_graph.db (KnowledgeGraph's SQLite store)
  - marks.jsonl        (stigmergy mark stream)

All reads synchronous — this is a batch analysis tool, not real-time.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ExplorationTarget(BaseModel):
    """A file or concept identified as worth exploring."""

    path: str                           # File path to explore
    reason: str                         # "semantic_gap" | "salience_gradient" | "mission_frontier"
    curiosity_score: float              # 0.0-1.0 composite score
    gap_score: float = 0.0             # Semantic gap component
    gradient_score: float = 0.0        # Salience gradient component
    mission_score: float = 0.0         # Mission alignment component
    suggested_agent: str = ""          # Which agent type should explore this
    expected_yield: str = ""           # What new information might emerge


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MISSION GOALS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACTIVE_GOALS: dict[str, set[str]] = {
    "rv_paper": {
        "r_v", "metric", "mistral", "colm", "mech-interp", "geometric",
        "contraction", "participation", "ratio", "transformer", "probe",
    },
    "dharma_swarm": {
        "swarm", "agent", "evolution", "stigmergy", "telos", "gate",
        "kernel", "darwin", "cascade", "ontology", "orchestrat",
    },
    "jagat_kalyan": {
        "welfare", "carbon", "ecological", "restoration", "matching",
        "kalyan", "offset", "reforestation", "eden", "climate",
    },
}

# Flat set for fast membership checking
_ALL_GOAL_KEYWORDS: set[str] = set()
for _kws in ACTIVE_GOALS.values():
    _ALL_GOAL_KEYWORDS |= _kws


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CuriosityEngine:
    """Identifies the most valuable files and concepts to explore next.

    Composite curiosity score per file:

        curiosity(f) = 0.4 * gap(f) + 0.3 * gradient(f) + 0.3 * mission(f)

    Usage::

        engine = CuriosityEngine()
        targets = engine.explore(top_n=10)
        for t in targets:
            print(f"{t.curiosity_score:.3f}  {t.path}  [{t.reason}]")
    """

    def __init__(
        self,
        db_path: Path | str | None = None,
        graph_db_path: Path | str | None = None,
        marks_path: Path | str | None = None,
    ) -> None:
        if db_path is None:
            db_path = Path.home() / ".dharma" / "file_profiles.db"
        self._db_path = Path(db_path)

        if graph_db_path is None:
            graph_db_path = Path.home() / ".dharma" / "knowledge_graph.db"
        self._graph_db_path = Path(graph_db_path)

        if marks_path is None:
            marks_path = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
        self._marks_path = Path(marks_path)

        # Lazily loaded caches
        self._marks_cache: list[dict[str, Any]] | None = None

    # ── DB helpers ────────────────────────────────────────────────────

    @contextmanager
    def _profiles_conn(self):
        """Connect to file_profiles.db (read-only)."""
        if not self._db_path.exists():
            yield None
            return
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _graph_conn(self):
        """Connect to knowledge_graph.db (read-only)."""
        if not self._graph_db_path.exists():
            yield None
            return
        conn = sqlite3.connect(str(self._graph_db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _load_marks(self) -> list[dict[str, Any]]:
        """Load stigmergy marks from JSONL, with caching."""
        if self._marks_cache is not None:
            return self._marks_cache
        marks: list[dict[str, Any]] = []
        if not self._marks_path.exists():
            self._marks_cache = marks
            return marks
        try:
            with open(self._marks_path, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        marks.append(json.loads(stripped))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError:
            pass
        self._marks_cache = marks
        return marks

    # ── Main entry point ──────────────────────────────────────────────

    def explore(self, top_n: int = 5) -> list[ExplorationTarget]:
        """Return ranked list of files/concepts worth exploring.

        Merges results from all three drivers, computes composite scores,
        deduplicates by path, and returns the top_n.
        """
        # Gather candidates from each driver
        gap_targets = self._semantic_gaps(limit=20)
        gradient_targets = self._salience_gradients(limit=20)
        mission_targets = self._mission_frontiers(limit=20)

        # Merge by path — combine scores where a file appears in multiple drivers
        by_path: dict[str, ExplorationTarget] = {}

        for t in gap_targets:
            by_path[t.path] = t

        for t in gradient_targets:
            if t.path in by_path:
                existing = by_path[t.path]
                existing.gradient_score = t.gradient_score
            else:
                by_path[t.path] = t

        for t in mission_targets:
            if t.path in by_path:
                existing = by_path[t.path]
                existing.mission_score = t.mission_score
            else:
                by_path[t.path] = t

        # Recompute composite scores and pick primary reason
        for target in by_path.values():
            target.curiosity_score = round(
                0.4 * target.gap_score
                + 0.3 * target.gradient_score
                + 0.3 * target.mission_score,
                4,
            )
            # Primary reason = highest-scoring driver
            scores = {
                "semantic_gap": target.gap_score,
                "salience_gradient": target.gradient_score,
                "mission_frontier": target.mission_score,
            }
            target.reason = max(scores, key=scores.get)  # type: ignore[arg-type]

            # Enrich with agent suggestion and expected yield
            target.suggested_agent = self._suggest_agent(target)
            target.expected_yield = self._expected_yield(target)

        # Sort by composite score descending
        ranked = sorted(by_path.values(), key=lambda t: t.curiosity_score, reverse=True)
        return ranked[:top_n]

    # ── Driver 1: Semantic Gaps ───────────────────────────────────────

    def _semantic_gaps(self, limit: int = 20) -> list[ExplorationTarget]:
        """Files with structural importance but low understanding.

        Three sub-signals:
          - High connectivity_degree but low semantic_density
            -> "known but not understood"
          - High impact_score but low mark_count
            -> "important but unexamined"
          - High lines but low concept_count
            -> "big but opaque"
        """
        targets: list[ExplorationTarget] = []

        with self._profiles_conn() as conn:
            if conn is None:
                return targets

            # Fetch files with enough data to score
            rows = conn.execute(
                """SELECT path, semantic_density, connectivity_degree,
                          impact_score, mark_count, lines, concept_count
                   FROM file_profiles
                   WHERE lines > 10
                   ORDER BY connectivity_degree DESC
                   LIMIT 200"""
            ).fetchall()

        if not rows:
            return targets

        # Find normalization maxima
        max_connectivity = max((r["connectivity_degree"] or 1) for r in rows)
        max_impact = max((r["impact_score"] or 0.001) for r in rows)
        max_lines = max((r["lines"] or 1) for r in rows)

        for row in rows:
            path = row["path"]
            density = row["semantic_density"] or 0.0
            connectivity = row["connectivity_degree"] or 0
            impact = row["impact_score"] or 0.0
            mark_count = row["mark_count"] or 0
            lines = row["lines"] or 0
            concepts = row["concept_count"] or 0

            # Sub-signal 1: connected but not understood
            conn_norm = connectivity / max_connectivity
            signal_1 = (1.0 - density) * conn_norm

            # Sub-signal 2: important but unexamined
            impact_norm = impact / max_impact
            exam_factor = 1.0 / (1.0 + mark_count)  # decays with marks
            signal_2 = impact_norm * exam_factor

            # Sub-signal 3: large but opaque (few concepts per line)
            lines_norm = lines / max_lines
            concept_density = concepts / max(lines, 1)
            opacity = max(0.0, 1.0 - min(1.0, concept_density * 10))
            signal_3 = lines_norm * opacity

            # Composite gap score
            gap = round(0.5 * signal_1 + 0.3 * signal_2 + 0.2 * signal_3, 4)

            if gap > 0.05:  # threshold to avoid noise
                targets.append(ExplorationTarget(
                    path=path,
                    reason="semantic_gap",
                    curiosity_score=0.0,  # recomputed in explore()
                    gap_score=gap,
                ))

        # Sort by gap score, take top
        targets.sort(key=lambda t: t.gap_score, reverse=True)
        return targets[:limit]

    # ── Driver 2: Salience Gradients ──────────────────────────────────

    def _salience_gradients(self, limit: int = 20) -> list[ExplorationTarget]:
        """Follow salience gradients in stigmergy.

        Groups marks by parent directory, computes per-directory average
        salience, then finds files where salience differs sharply from
        their neighborhood.  Includes 20% anti-echo-chamber picks from
        the lowest-salience regions.
        """
        targets: list[ExplorationTarget] = []
        marks = self._load_marks()

        if not marks:
            return targets

        # Group marks by file_path -> collect saliences
        file_saliences: dict[str, list[float]] = defaultdict(list)
        for m in marks:
            fp = m.get("file_path", "")
            if not fp or fp.startswith("task:"):
                continue
            salience = m.get("salience", 0.5)
            file_saliences[fp].append(salience)

        if not file_saliences:
            return targets

        # Per-file average salience
        file_avg: dict[str, float] = {
            fp: sum(sals) / len(sals)
            for fp, sals in file_saliences.items()
        }

        # Per-directory average salience
        dir_saliences: dict[str, list[float]] = defaultdict(list)
        for fp, avg_sal in file_avg.items():
            parent = str(Path(fp).parent)
            dir_saliences[parent].append(avg_sal)

        dir_avg: dict[str, float] = {
            d: sum(sals) / len(sals)
            for d, sals in dir_saliences.items()
        }

        # Compute gradient: how much does this file differ from its directory?
        gradient_scores: list[tuple[str, float]] = []
        for fp, avg_sal in file_avg.items():
            parent = str(Path(fp).parent)
            neighbor_avg = dir_avg.get(parent, avg_sal)
            if neighbor_avg > 0.001:
                gradient = abs(avg_sal - neighbor_avg) / neighbor_avg
            else:
                gradient = abs(avg_sal)
            # Boost files with higher absolute salience (follow uphill)
            boosted = gradient * (0.5 + 0.5 * avg_sal)
            gradient_scores.append((fp, round(min(1.0, boosted), 4)))

        # Sort descending by gradient score
        gradient_scores.sort(key=lambda x: x[1], reverse=True)

        # Main picks: 80% from highest gradients
        main_count = max(1, int(limit * 0.8))
        anti_echo_count = limit - main_count

        main_picks = gradient_scores[:main_count]

        # Anti-echo-chamber: 20% from lowest-salience files
        # (files that nobody is looking at — potential blind spots)
        lowest_salience = sorted(file_avg.items(), key=lambda x: x[1])
        anti_echo_paths = {fp for fp, _ in main_picks}
        anti_echo_picks: list[tuple[str, float]] = []
        for fp, sal in lowest_salience:
            if fp not in anti_echo_paths:
                # Score = inverse salience as curiosity signal
                anti_echo_picks.append((fp, round(max(0.1, 1.0 - sal), 4)))
                if len(anti_echo_picks) >= anti_echo_count:
                    break

        for fp, score in main_picks:
            targets.append(ExplorationTarget(
                path=fp,
                reason="salience_gradient",
                curiosity_score=0.0,
                gradient_score=score,
            ))

        for fp, score in anti_echo_picks:
            targets.append(ExplorationTarget(
                path=fp,
                reason="salience_gradient",
                curiosity_score=0.0,
                gradient_score=score,
            ))

        targets.sort(key=lambda t: t.gradient_score, reverse=True)
        return targets[:limit]

    # ── Driver 3: Mission Frontiers ───────────────────────────────────

    def _mission_frontiers(self, limit: int = 20) -> list[ExplorationTarget]:
        """Files near active goal keywords but not recently profiled.

        Score = (keyword_matches / total_keywords) * recency_bonus.
        Files not profiled in 24h get a 1.5x bonus.
        """
        targets: list[ExplorationTarget] = []

        with self._profiles_conn() as conn:
            if conn is None:
                return targets

            rows = conn.execute(
                """SELECT path, filename, domain, last_profiled,
                          mission_alignment, semantic_density
                   FROM file_profiles
                   ORDER BY mission_alignment DESC
                   LIMIT 500"""
            ).fetchall()

        if not rows:
            return targets

        now = datetime.now(timezone.utc)
        twenty_four_hours = 24 * 3600

        for row in rows:
            path = row["path"]
            filename = (row["filename"] or "").lower()
            domain = (row["domain"] or "").lower()
            last_profiled_str = row["last_profiled"] or ""
            existing_alignment = row["mission_alignment"] or 0.0

            # Compute keyword match score across all goals
            search_text = f"{path} {filename} {domain}".lower()
            total_keywords = len(_ALL_GOAL_KEYWORDS)
            matches = sum(1 for kw in _ALL_GOAL_KEYWORDS if kw in search_text)

            if matches == 0:
                continue

            keyword_score = matches / total_keywords

            # Per-goal breakdown: which goal does this file serve?
            best_goal = ""
            best_goal_score = 0.0
            for goal_name, keywords in ACTIVE_GOALS.items():
                goal_matches = sum(1 for kw in keywords if kw in search_text)
                goal_score = goal_matches / len(keywords) if keywords else 0.0
                if goal_score > best_goal_score:
                    best_goal_score = goal_score
                    best_goal = goal_name

            # Recency bonus: files not profiled recently get boosted
            recency_bonus = 1.0
            if last_profiled_str:
                try:
                    last_dt = datetime.fromisoformat(last_profiled_str)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    age_seconds = (now - last_dt).total_seconds()
                    if age_seconds > twenty_four_hours:
                        recency_bonus = 1.5
                except (ValueError, TypeError):
                    recency_bonus = 1.5
            else:
                recency_bonus = 1.5  # never profiled = high curiosity

            # Combine keyword match with existing alignment and recency
            raw_score = (0.6 * keyword_score + 0.4 * existing_alignment) * recency_bonus
            mission = round(min(1.0, raw_score), 4)

            if mission > 0.05:
                targets.append(ExplorationTarget(
                    path=path,
                    reason="mission_frontier",
                    curiosity_score=0.0,
                    mission_score=mission,
                    expected_yield=f"telos connection ({best_goal})" if best_goal else "",
                ))

        targets.sort(key=lambda t: t.mission_score, reverse=True)
        return targets[:limit]

    # ── Agent suggestion ──────────────────────────────────────────────

    def _suggest_agent(self, target: ExplorationTarget) -> str:
        """Heuristic: which agent type should explore this target?

        Based on file extension, domain, and which driver scored highest.
        """
        path = target.path
        ext = Path(path).suffix.lower() if path else ""

        # Mission-aligned targets -> telos-agent
        if target.mission_score > 0.5:
            return "telos-agent"

        # Low semantic density -> analyst (needs deep reading)
        if target.gap_score > 0.6:
            if ext == ".py":
                return "analyst"
            if ext in {".md", ".rst", ".txt"}:
                return "archeologist"
            return "analyst"

        # File-type heuristics
        if ext == ".py":
            if target.gradient_score > target.gap_score:
                return "researcher"
            return "architect"
        if ext in {".md", ".rst", ".txt"}:
            if target.gradient_score > 0.3:
                return "writer"
            return "archeologist"
        if ext in {".json", ".yaml", ".yml", ".toml"}:
            return "analyst"

        # Default
        return "researcher"

    # ── Expected yield ────────────────────────────────────────────────

    def _expected_yield(self, target: ExplorationTarget) -> str:
        """Estimate what exploring this target will produce."""
        # If already set (e.g., by mission_frontiers), keep it
        if target.expected_yield:
            return target.expected_yield

        yields: list[str] = []

        if target.gap_score > 0.3:
            yields.append("structural understanding, concept extraction")
        if target.gradient_score > 0.3:
            yields.append("salience resolution, mark enrichment")
        if target.mission_score > 0.3:
            yields.append("telos connection, goal proximity")

        if not yields:
            # Fallback based on primary reason
            fallbacks = {
                "semantic_gap": "concept extraction, density increase",
                "salience_gradient": "neighborhood mapping, salience calibration",
                "mission_frontier": "mission alignment verification",
            }
            return fallbacks.get(target.reason, "general exploration")

        return "; ".join(yields)

    # ── Graph-enhanced gap detection ──────────────────────────────────

    def _graph_connectivity(self, path: str) -> int:
        """Get edge count for a file node in the knowledge graph.

        Falls back to 0 if graph DB doesn't exist or node not found.
        """
        from hashlib import sha256
        node_id = sha256(path.encode()).hexdigest()[:16]

        with self._graph_conn() as conn:
            if conn is None:
                return 0
            try:
                row = conn.execute(
                    """SELECT COUNT(*) FROM edges
                       WHERE source_id = ? OR target_id = ?""",
                    (node_id, node_id),
                ).fetchone()
                return row[0] if row else 0
            except sqlite3.OperationalError:
                return 0

    # ── Summary ───────────────────────────────────────────────────────

    def summary(self, top_n: int = 5) -> str:
        """Human-readable exploration summary."""
        targets = self.explore(top_n=top_n)
        if not targets:
            return "Curiosity Engine: no exploration targets (profile DB may be empty)"

        lines = [f"Curiosity Engine: top {len(targets)} exploration targets\n"]
        for i, t in enumerate(targets, 1):
            lines.append(
                f"  {i}. [{t.curiosity_score:.3f}] {t.path}\n"
                f"     reason={t.reason}  agent={t.suggested_agent}\n"
                f"     gap={t.gap_score:.3f} gradient={t.gradient_score:.3f} "
                f"mission={t.mission_score:.3f}\n"
                f"     yield: {t.expected_yield}"
            )
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        """Diagnostic stats about data sources."""
        profile_count = 0
        graph_node_count = 0
        graph_edge_count = 0
        mark_count = len(self._load_marks())

        with self._profiles_conn() as conn:
            if conn is not None:
                try:
                    row = conn.execute("SELECT COUNT(*) FROM file_profiles").fetchone()
                    profile_count = row[0] if row else 0
                except sqlite3.OperationalError:
                    pass

        with self._graph_conn() as conn:
            if conn is not None:
                try:
                    row = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
                    graph_node_count = row[0] if row else 0
                    row = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
                    graph_edge_count = row[0] if row else 0
                except sqlite3.OperationalError:
                    pass

        return {
            "profile_count": profile_count,
            "graph_nodes": graph_node_count,
            "graph_edges": graph_edge_count,
            "mark_count": mark_count,
            "goals": list(ACTIVE_GOALS.keys()),
            "goal_keywords": len(_ALL_GOAL_KEYWORDS),
        }
