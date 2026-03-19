"""Graph Query API for the Ontology Hub.

Provides traversal, search, and analysis queries over the unified
ontology graph. Works on the in-memory OntologyRegistry.

Usage::

    from dharma_swarm.ontology import OntologyRegistry
    from dharma_swarm.ontology_query import OntologyGraph

    registry = OntologyRegistry.create_dharma_registry()
    graph = OntologyGraph(registry)

    # Traverse from a node
    result = graph.traverse("obj_123", depth=2)

    # Search by type and text
    marks = graph.find("StigmergyMark", text_query="evolution")

    # Shortest path between two objects
    path = graph.shortest_path("obj_a", "obj_b")
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from dharma_swarm.ontology import Link, OntologyObj, OntologyRegistry

logger = logging.getLogger(__name__)


class OntologyGraph:
    """Query interface for the ontology object graph.

    Wraps an OntologyRegistry and provides graph traversal, search,
    and analysis operations over its in-memory object and link stores.

    Args:
        registry: The OntologyRegistry to query against.
    """

    def __init__(self, registry: OntologyRegistry) -> None:
        self._reg = registry

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def traverse(
        self,
        start_id: str,
        link_names: list[str] | None = None,
        depth: int = 3,
    ) -> dict[str, Any]:
        """BFS traversal from start_id, following specified link types.

        At each node, outgoing AND incoming links are followed. If
        ``link_names`` is provided, only links with matching names are
        traversed.

        Args:
            start_id: ID of the starting OntologyObj.
            link_names: Optional filter -- only follow these link names.
            depth: Maximum traversal depth (default 3).

        Returns:
            Dict with keys:
            - ``root``: The starting OntologyObj (or None if not found).
            - ``nodes``: List of all discovered OntologyObj instances.
            - ``edges``: List of all traversed Link instances.
            - ``depth_reached``: Maximum depth actually reached.
        """
        root = self._reg.get_object(start_id)
        if root is None:
            return {
                "root": None,
                "nodes": [],
                "edges": [],
                "depth_reached": 0,
            }

        visited: set[str] = {start_id}
        nodes: list[OntologyObj] = [root]
        edges: list[Link] = []
        depth_reached = 0

        # BFS queue: (obj_id, current_depth)
        queue: deque[tuple[str, int]] = deque([(start_id, 0)])

        while queue:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue

            # Find all links involving this node
            for link in self._reg._link_instances.values():
                # Determine the "other end" of the link
                neighbor_id: str | None = None
                if link.source_id == current_id:
                    neighbor_id = link.target_id
                elif link.target_id == current_id:
                    neighbor_id = link.source_id
                else:
                    continue

                # Filter by link name if specified
                if link_names is not None and link.link_name not in link_names:
                    continue

                # Record edge (even if neighbor already visited, to get
                # a complete edge set)
                if link not in edges:
                    edges.append(link)

                if neighbor_id in visited:
                    continue

                neighbor = self._reg.get_object(neighbor_id)
                if neighbor is None:
                    continue

                visited.add(neighbor_id)
                nodes.append(neighbor)
                next_depth = current_depth + 1
                if next_depth > depth_reached:
                    depth_reached = next_depth
                queue.append((neighbor_id, next_depth))

        return {
            "root": root,
            "nodes": nodes,
            "edges": edges,
            "depth_reached": depth_reached,
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def find(
        self,
        type_name: str,
        filters: dict[str, Any] | None = None,
        text_query: str = "",
        limit: int = 50,
    ) -> list[OntologyObj]:
        """Find objects by type with optional property filters and text search.

        Applies filters in order: type_name -> property exact match ->
        text substring match across all string/text properties.

        Args:
            type_name: ObjectType name to filter by.
            filters: Dict of ``{property_name: expected_value}`` for
                exact-match filtering.
            text_query: Substring to match against all string and text
                properties (case-insensitive).
            limit: Maximum number of results to return.

        Returns:
            List of matching OntologyObj instances, up to ``limit``.
        """
        candidates = self._reg.get_objects_by_type(type_name)

        # Property filters
        if filters:
            filtered: list[OntologyObj] = []
            for obj in candidates:
                match = True
                for key, expected in filters.items():
                    actual = obj.properties.get(key)
                    if actual != expected:
                        match = False
                        break
                if match:
                    filtered.append(obj)
            candidates = filtered

        # Text query (case-insensitive substring across all text props)
        if text_query:
            query_lower = text_query.lower()
            text_matched: list[OntologyObj] = []
            for obj in candidates:
                for value in obj.properties.values():
                    if isinstance(value, str) and query_lower in value.lower():
                        text_matched.append(obj)
                        break
            candidates = text_matched

        return candidates[:limit]

    # ------------------------------------------------------------------
    # Neighbors
    # ------------------------------------------------------------------

    def neighbors(self, obj_id: str) -> list[tuple[str, OntologyObj]]:
        """All directly linked objects regardless of link type.

        Returns both outgoing and incoming links, yielding the "other
        end" of each link.

        Args:
            obj_id: ID of the object to find neighbors for.

        Returns:
            List of ``(link_name, OntologyObj)`` tuples. The same
            neighbor may appear multiple times if connected via
            different link types.
        """
        result: list[tuple[str, OntologyObj]] = []
        for link in self._reg._link_instances.values():
            other_id: str | None = None
            if link.source_id == obj_id:
                other_id = link.target_id
            elif link.target_id == obj_id:
                other_id = link.source_id
            else:
                continue

            other = self._reg.get_object(other_id)
            if other is not None:
                result.append((link.link_name, other))
        return result

    # ------------------------------------------------------------------
    # Shortest Path
    # ------------------------------------------------------------------

    def shortest_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 6,
    ) -> list[tuple[str, str]]:
        """BFS shortest path through the link graph.

        Follows both outgoing and incoming links at each node.

        Args:
            from_id: Starting object ID.
            to_id: Target object ID.
            max_depth: Maximum path length to search.

        Returns:
            List of ``(link_name, obj_id)`` tuples representing the
            path from ``from_id`` to ``to_id``. Empty list if no path
            found or either endpoint doesn't exist.
        """
        if from_id == to_id:
            return []

        if self._reg.get_object(from_id) is None:
            return []
        if self._reg.get_object(to_id) is None:
            return []

        # BFS with parent tracking
        # parent[node_id] = (link_name, prev_node_id)
        parent: dict[str, tuple[str, str]] = {}
        visited: set[str] = {from_id}
        queue: deque[tuple[str, int]] = deque([(from_id, 0)])

        found = False
        while queue and not found:
            current_id, current_depth = queue.popleft()
            if current_depth >= max_depth:
                continue

            for link in self._reg._link_instances.values():
                neighbor_id: str | None = None
                if link.source_id == current_id:
                    neighbor_id = link.target_id
                elif link.target_id == current_id:
                    neighbor_id = link.source_id
                else:
                    continue

                if neighbor_id in visited:
                    continue

                # Only traverse to existing objects
                if self._reg.get_object(neighbor_id) is None:
                    continue

                visited.add(neighbor_id)
                parent[neighbor_id] = (link.link_name, current_id)

                if neighbor_id == to_id:
                    found = True
                    break

                queue.append((neighbor_id, current_depth + 1))

        if not found:
            return []

        # Reconstruct path
        path: list[tuple[str, str]] = []
        current = to_id
        while current in parent:
            link_name, prev = parent[current]
            path.append((link_name, current))
            current = prev
        path.reverse()
        return path

    # ------------------------------------------------------------------
    # Subgraph
    # ------------------------------------------------------------------

    def subgraph(
        self,
        type_names: list[str] | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Extract a subgraph of recent activity.

        Filters objects by type and/or creation time, then collects
        all links between the matched objects.

        Args:
            type_names: If provided, only include objects of these types.
            since: If provided, only include objects created at or after
                this timestamp.

        Returns:
            Dict with keys:
            - ``objects``: List of matching OntologyObj instances.
            - ``links``: List of Link instances connecting matched objects.
            - ``stats``: Summary counts.
        """
        # Filter objects
        objs: list[OntologyObj] = []
        obj_ids: set[str] = set()
        for obj in self._reg._objects.values():
            if type_names is not None and obj.type_name not in type_names:
                continue
            if since is not None and obj.created_at < since:
                continue
            objs.append(obj)
            obj_ids.add(obj.id)

        # Collect links between matched objects
        links: list[Link] = [
            link
            for link in self._reg._link_instances.values()
            if link.source_id in obj_ids and link.target_id in obj_ids
        ]

        # Type distribution
        type_dist: dict[str, int] = {}
        for obj in objs:
            type_dist[obj.type_name] = type_dist.get(obj.type_name, 0) + 1

        return {
            "objects": objs,
            "links": links,
            "stats": {
                "object_count": len(objs),
                "link_count": len(links),
                "type_distribution": type_dist,
            },
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Object counts by type, link counts by name, freshness metrics.

        Returns:
            Dict with keys:
            - ``object_counts``: Dict mapping type name to object count.
            - ``link_counts``: Dict mapping link name to link count.
            - ``total_objects``: Total number of objects.
            - ``total_links``: Total number of links.
            - ``newest_object``: Datetime of the most recently created
              object, or None if empty.
            - ``oldest_object``: Datetime of the oldest object, or None
              if empty.
        """
        object_counts: dict[str, int] = {}
        newest: datetime | None = None
        oldest: datetime | None = None

        for obj in self._reg._objects.values():
            object_counts[obj.type_name] = (
                object_counts.get(obj.type_name, 0) + 1
            )
            if newest is None or obj.created_at > newest:
                newest = obj.created_at
            if oldest is None or obj.created_at < oldest:
                oldest = obj.created_at

        link_counts: dict[str, int] = {}
        for link in self._reg._link_instances.values():
            link_counts[link.link_name] = link_counts.get(link.link_name, 0) + 1

        return {
            "object_counts": object_counts,
            "link_counts": link_counts,
            "total_objects": len(self._reg._objects),
            "total_links": len(self._reg._link_instances),
            "newest_object": newest,
            "oldest_object": oldest,
        }
