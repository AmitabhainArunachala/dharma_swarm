"""Autocatalytic graph -- tracks how artifacts catalyze each other.

Directed graph with Tarjan's SCC to find strongly connected components.
Autocatalytic sets are SCCs where every node has at least one internal
catalyst (an incoming edge from another node within the same SCC).

Persistence: ~/.dharma/meta/catalytic_graph.json
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from dharma_swarm.models import CatalyticEdge, _utc_now

logger = logging.getLogger(__name__)

EDGE_TYPES = ("enables", "validates", "attracts", "funds", "improves")


class CatalyticGraph:
    """Directed graph tracking how artifacts enable/validate/fund each other.

    Key capability: Tarjan's SCC algorithm finds autocatalytic sets --
    self-sustaining feedback loops where every member is catalyzed by at
    least one other member.

    Args:
        persist_path: Path for JSON persistence. Defaults to
            ``~/.dharma/meta/catalytic_graph.json``.
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        self._persist_path = persist_path or (
            Path.home() / ".dharma" / "meta" / "catalytic_graph.json"
        )
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[CatalyticEdge] = []
        self._adj: dict[str, list[str]] = defaultdict(list)
        self._rev: dict[str, list[str]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, **metadata: Any) -> None:
        """Add a node with optional metadata.

        If the node already exists its metadata is updated (merged).

        Args:
            node_id: Unique identifier for the node.
            **metadata: Arbitrary key-value pairs stored with the node.
        """
        if node_id in self._nodes:
            self._nodes[node_id].update(metadata)
        else:
            self._nodes[node_id] = dict(metadata)

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str = "enables",
        strength: float = 0.5,
        evidence: str = "",
    ) -> CatalyticEdge:
        """Add a directed edge, auto-creating nodes if absent.

        Args:
            source: Origin node id.
            target: Destination node id.
            edge_type: One of :data:`EDGE_TYPES`.
            strength: Edge weight in ``[0, 1]``.
            evidence: Human-readable justification.

        Returns:
            The constructed :class:`CatalyticEdge`.

        Raises:
            ValueError: If *edge_type* is not in :data:`EDGE_TYPES`.
        """
        if edge_type not in EDGE_TYPES:
            raise ValueError(
                f"Invalid edge_type {edge_type!r}. Must be one of {EDGE_TYPES}"
            )

        if source not in self._nodes:
            self._nodes[source] = {}
        if target not in self._nodes:
            self._nodes[target] = {}

        edge = CatalyticEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            strength=strength,
            evidence=evidence,
        )
        self._edges.append(edge)
        self._adj[source].append(target)
        self._rev[target].append(source)
        return edge

    # ------------------------------------------------------------------
    # Tarjan's SCC
    # ------------------------------------------------------------------

    def tarjan_scc(self) -> list[list[str]]:
        """Tarjan's algorithm for strongly connected components.

        Runs in O(V + E). Returns a list of components, each component
        being a list of node ids. Singleton components (single nodes with
        no self-loop) are included.

        Returns:
            List of strongly connected components.
        """
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        result: list[list[str]] = []

        def _strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in self._adj.get(v, []):
                if w not in index:
                    _strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    component.append(w)
                    if w == v:
                        break
                result.append(component)

        for v in self._nodes:
            if v not in index:
                _strongconnect(v)

        return result

    # ------------------------------------------------------------------
    # Autocatalytic detection
    # ------------------------------------------------------------------

    def detect_autocatalytic_sets(self) -> list[list[str]]:
        """Find SCCs where every node has at least one internal catalyst.

        An *internal catalyst* is an incoming edge from another node that
        belongs to the same SCC.  Singleton SCCs are excluded.

        Returns:
            List of autocatalytic components.
        """
        sccs = self.tarjan_scc()
        autocatalytic: list[list[str]] = []
        for scc in sccs:
            if len(scc) < 2:
                continue
            scc_set = set(scc)
            all_catalyzed = True
            for node in scc:
                has_internal = any(
                    src in scc_set for src in self._rev.get(node, [])
                )
                if not has_internal:
                    all_catalyzed = False
                    break
            if all_catalyzed:
                autocatalytic.append(scc)
        return autocatalytic

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def growth_potential(self, node: str) -> int:
        """Count nodes not yet connected to *node* (in either direction).

        Returns 0 for unknown nodes.

        Args:
            node: Node id to evaluate.

        Returns:
            Number of unconnected nodes (excluding self).
        """
        if node not in self._nodes:
            return 0
        existing_targets = set(self._adj.get(node, []))
        existing_sources = set(self._rev.get(node, []))
        connected = existing_targets | existing_sources | {node}
        return len(self._nodes) - len(connected)

    def loop_closure_priority(self) -> list[tuple[str, str, float]]:
        """Rank missing edges by loop-closing value.

        Uses BFS (depth <= 3) from each node to find candidates whose
        addition would close a cycle. Shorter near-complete loops and
        higher average edge strength both boost the score.

        Returns:
            Deduplicated list of ``(source, target, score)`` sorted by
            score descending.
        """
        candidates: list[tuple[str, str, float]] = []
        for node in self._nodes:
            visited: dict[str, int] = {node: 0}
            queue = [node]
            while queue:
                current = queue.pop(0)
                depth = visited[current]
                if depth >= 3:
                    continue
                for neighbor in self._adj.get(current, []):
                    if neighbor not in visited:
                        visited[neighbor] = depth + 1
                        queue.append(neighbor)

            for candidate, depth in visited.items():
                if candidate == node:
                    continue
                if node not in set(self._adj.get(candidate, [])):
                    score = 1.0 / (depth + 1)
                    edge_strengths = [
                        e.strength for e in self._edges if e.source == candidate
                    ]
                    if edge_strengths:
                        score *= 1.0 + sum(edge_strengths) / len(edge_strengths)
                    candidates.append((candidate, node, round(score, 4)))

        seen: set[tuple[str, str]] = set()
        unique: list[tuple[str, str, float]] = []
        for src, tgt, score in sorted(candidates, key=lambda x: -x[2]):
            if (src, tgt) not in seen:
                seen.add((src, tgt))
                unique.append((src, tgt, score))
        return unique

    def revenue_ready_sets(self) -> list[list[str]]:
        """Return autocatalytic sets containing *funds* or *attracts* edges.

        Returns:
            Subset of :meth:`detect_autocatalytic_sets` touching
            monetisable edge types.
        """
        monetizable_nodes: set[str] = set()
        for edge in self._edges:
            if edge.edge_type in ("funds", "attracts"):
                monetizable_nodes.add(edge.source)
                monetizable_nodes.add(edge.target)

        ac_sets = self.detect_autocatalytic_sets()
        return [s for s in ac_sets if any(n in monetizable_nodes for n in s)]

    # ------------------------------------------------------------------
    # Ecosystem seeding
    # ------------------------------------------------------------------

    def seed_ecosystem(self) -> None:
        """Seed with actual dharma_swarm ecosystem relationships.

        Creates six nodes (rv_paper, credibility, mi_consulting,
        rvm_toolkit, ura_paper, dharma_swarm) and seven edges
        representing their catalytic relationships.
        """
        self.add_node("rv_paper", type="research", status="active")
        self.add_node("credibility", type="reputation")
        self.add_node("mi_consulting", type="revenue")
        self.add_node("rvm_toolkit", type="product")
        self.add_node("ura_paper", type="research", status="complete")
        self.add_node("dharma_swarm", type="infrastructure")

        self.add_edge(
            "rv_paper", "credibility", "attracts", 0.7,
            "Published research builds reputation",
        )
        self.add_edge(
            "credibility", "mi_consulting", "enables", 0.6,
            "Reputation attracts clients",
        )
        self.add_edge(
            "mi_consulting", "rvm_toolkit", "improves", 0.5,
            "Client feedback improves toolkit",
        )
        self.add_edge(
            "rvm_toolkit", "rv_paper", "enables", 0.4,
            "Toolkit validates paper claims",
        )
        self.add_edge(
            "ura_paper", "rv_paper", "validates", 0.8,
            "Behavioral data validates geometric",
        )
        self.add_edge(
            "dharma_swarm", "rv_paper", "enables", 0.5,
            "Swarm automates experiments",
        )
        self.add_edge(
            "rv_paper", "dharma_swarm", "improves", 0.3,
            "Paper findings guide swarm evolution",
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist graph to JSON on disk.

        Creates parent directories as needed. Overwrites any existing
        file at :attr:`_persist_path`.
        """
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": self._nodes,
            "edges": [e.model_dump(mode="json") for e in self._edges],
            "saved_at": _utc_now().isoformat(),
        }
        self._persist_path.write_text(
            json.dumps(data, indent=2, default=str)
        )

    def load(self) -> bool:
        """Load graph from disk, replacing in-memory state.

        Returns:
            ``True`` if the file was found and parsed, ``False``
            otherwise.
        """
        if not self._persist_path.exists():
            return False
        try:
            data = json.loads(self._persist_path.read_text())
            self._nodes = data.get("nodes", {})
            self._edges = [
                CatalyticEdge(**e) for e in data.get("edges", [])
            ]
            self._adj = defaultdict(list)
            self._rev = defaultdict(list)
            for e in self._edges:
                self._adj[e.source].append(e.target)
                self._rev[e.target].append(e.source)
            return True
        except Exception as exc:
            logger.warning("Failed to load catalytic graph: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Properties & summaries
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return len(self._edges)

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of graph state.

        Keys: ``nodes``, ``edges``, ``sccs``, ``autocatalytic_sets``,
        ``largest_scc``, ``revenue_ready``.
        """
        sccs = self.tarjan_scc()
        ac = self.detect_autocatalytic_sets()
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "sccs": len(sccs),
            "autocatalytic_sets": len(ac),
            "largest_scc": max((len(s) for s in sccs), default=0),
            "revenue_ready": len(self.revenue_ready_sets()),
        }
