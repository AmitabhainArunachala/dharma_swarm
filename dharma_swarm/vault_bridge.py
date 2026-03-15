"""Vault Bridge -- ingest knowledge sources into a unified semantic vault.

Walks source directories (Kailash Obsidian, PSMV, R_V Paper, CLAUDE companions,
dharma_swarm state), digests files via SemanticDigester, extends the existing
ConceptGraph, and generates interlinked vault notes with wikilinks.

Data structures:
  IngestReport  -- per-source ingest statistics
  VaultReport   -- vault generation statistics
  VaultBridge   -- the bridge between knowledge sources and the semantic vault

Usage::

    import asyncio
    from dharma_swarm.vault_bridge import VaultBridge

    async def main() -> None:
        bridge = VaultBridge()
        await bridge.load_graph()
        reports = bridge.ingest_all()
        vault_report = bridge.generate_vault()
        await bridge.save_graph()
        print(f"Generated {vault_report.notes_generated} notes")

    asyncio.run(main())
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dharma_swarm.semantic_digester import (
    ALLOWED_MD_SUFFIXES,
    ALLOWED_PY_SUFFIXES,
    ALLOWED_TEXT_SUFFIXES,
    SKIP_DIRS,
    SemanticDigester,
)
from dharma_swarm.semantic_gravity import (
    ConceptGraph,
    ConceptNode,
    EdgeType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Additional suffixes handled by vault bridge beyond the digester defaults
ALLOWED_TEX_SUFFIXES: frozenset[str] = frozenset({".tex"})
ALL_VAULT_SUFFIXES: frozenset[str] = (
    ALLOWED_PY_SUFFIXES
    | ALLOWED_MD_SUFFIXES
    | ALLOWED_TEXT_SUFFIXES
    | ALLOWED_TEX_SUFFIXES
)

# Salience boost keywords -- concepts touching these get a 1.5x salience multiplier
_SALIENCE_BOOST_RE: re.Pattern[str] = re.compile(
    r"\b(?:L3|L4|L5|Phoenix|R_V|Akram|witnessing|consciousness|swabhaav|"
    r"recursive|self-reference|fixed[- ]?point|phase[- ]?transition|"
    r"participation[- ]?ratio|eigenform|Bhed[- ]?Gnan)\b",
    re.IGNORECASE,
)

# Edge type display names for vault note sections
_EDGE_SECTION_MAP: dict[EdgeType, str] = {
    EdgeType.DEPENDS_ON: "Depends on",
    EdgeType.IMPLEMENTS: "Implements",
    EdgeType.EXTENDS: "Extends",
    EdgeType.CONTRADICTS: "Contradicts",
    EdgeType.ANALOGOUS_TO: "Analogous to",
    EdgeType.IMPORTS: "Imports",
    EdgeType.REFERENCES: "References",
    EdgeType.GROUNDS: "Grounds",
}

# Standard paths
HOME: Path = Path.home()
VAULT_DIR: Path = HOME / ".dharma" / "vault"
GRAPH_PATH: Path = HOME / ".dharma" / "semantic" / "concept_graph.json"

# PSMV subdirectories to skip (boilerplate / agent workspaces)
PSMV_SKIP_DIRS: frozenset[str] = frozenset(
    {"AGENT_EMERGENT_WORKSPACES", ".git", "__pycache__"}
)

# Minimum content length -- files shorter than this are stubs, skip them
_MIN_CONTENT_LENGTH: int = 100

# Maximum concepts per index table
_MAX_INDEX_ENTRIES: int = 200

# Salience threshold for vault note generation
_SALIENCE_THRESHOLD: float = 0.3

# Minimum graph degree for a concept to earn a cross-cutting hub note
_HUB_DEGREE_THRESHOLD: int = 10


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    """Report from ingesting a single source."""

    source: str
    files_scanned: int = 0
    files_digested: int = 0
    files_skipped: int = 0
    concepts_added: int = 0
    edges_added: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line summary string."""
        parts = [
            f"{self.source}: {self.files_digested}/{self.files_scanned} files",
            f"{self.concepts_added} concepts",
        ]
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


@dataclass
class VaultReport:
    """Report from generating vault notes."""

    notes_generated: int = 0
    wikilinks_created: int = 0
    indexes_generated: int = 0
    directories_created: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line summary string."""
        return (
            f"{self.notes_generated} notes, "
            f"{self.wikilinks_created} wikilinks, "
            f"{self.indexes_generated} indexes"
        )


# ---------------------------------------------------------------------------
# VaultBridge
# ---------------------------------------------------------------------------


class VaultBridge:
    """Ingests knowledge sources into a unified semantic vault.

    The bridge reads files from five configured source tiers, digests them
    via :class:`SemanticDigester`, and populates a shared :class:`ConceptGraph`.
    It can then generate an interlinked vault of Markdown notes with YAML
    frontmatter and ``[[wikilinks]]`` suitable for Obsidian or similar tools.

    Source tiers (in order):

    1. **kailash** -- Obsidian vault (``~/Desktop/KAILASH ABODE OF SHIVA``)
    2. **psmv** -- Persistent Semantic Memory Vault
    3. **research** -- R_V paper directory
    4. **claude** -- CLAUDE1-9.md companion files in ``~/``
    5. **state** -- dharma_swarm runtime state (``~/.dharma/shared``, ``~/.dharma/distilled``)
    """

    # (tier_name, source_directory, max_files, vault_subdir)
    DEFAULT_SOURCES: list[tuple[str, Path, int, str]] = [
        ("kailash", HOME / "Desktop" / "KAILASH ABODE OF SHIVA", 2000, "01-KAILASH"),
        ("psmv", HOME / "Persistent-Semantic-Memory-Vault", 1500, "02-PSMV"),
        (
            "research",
            HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER",
            200,
            "03-RESEARCH",
        ),
        ("claude", HOME, 9, "03-RESEARCH"),
        ("state", HOME / ".dharma", 500, "06-STATE"),
    ]

    def __init__(
        self,
        vault_dir: Path = VAULT_DIR,
        graph_path: Path = GRAPH_PATH,
    ) -> None:
        self.vault_dir = vault_dir
        self.graph_path = graph_path
        self.digester = SemanticDigester()
        self.graph: ConceptGraph | None = None
        self._source_nodes: dict[str, list[str]] = defaultdict(list)

    # -- graph lifecycle -----------------------------------------------------

    async def load_graph(self) -> ConceptGraph:
        """Load existing concept graph from disk, or create an empty one."""
        self.graph = await ConceptGraph.load(self.graph_path)
        logger.info(
            "[vault] Loaded graph: %d nodes, %d edges",
            self.graph.node_count,
            self.graph.edge_count,
        )
        return self.graph

    async def save_graph(self) -> None:
        """Persist the current concept graph to disk."""
        if self.graph is None:
            logger.warning("[vault] No graph loaded, nothing to save")
            return
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        await self.graph.save(self.graph_path)
        logger.info(
            "[vault] Saved graph (%d nodes, %d edges) to %s",
            self.graph.node_count,
            self.graph.edge_count,
            self.graph_path,
        )

    # -- file collection -----------------------------------------------------

    def _collect_files(self, source_dir: Path, *, tier: str) -> list[Path]:
        """Collect candidate files from a source directory.

        Each tier has its own collection strategy:

        - **claude**: enumerates CLAUDE1.md through CLAUDE9.md in HOME.
        - **state**: scans ``shared/`` and ``distilled/`` subdirs only,
          including ``.jsonl`` files whose name contains ``ideas``.
        - **kailash / psmv / research**: recursive walk with skip-dir
          filtering and suffix checks.

        Args:
            source_dir: Root directory for this tier.
            tier: Tier name controlling collection strategy.

        Returns:
            Sorted list of file paths to process.
        """
        if not source_dir.exists():
            logger.debug("[vault] Source dir does not exist: %s", source_dir)
            return []

        files: list[Path] = []

        # -- CLAUDE companion files ------------------------------------------
        if tier == "claude":
            for i in range(1, 10):
                p = HOME / f"CLAUDE{i}.md"
                if p.exists():
                    files.append(p)
            return files

        # -- dharma_swarm state ----------------------------------------------
        if tier == "state":
            for subdir_name in ("shared", "distilled"):
                subdir = source_dir / subdir_name
                if not subdir.exists():
                    continue
                for fpath in subdir.rglob("*"):
                    if not fpath.is_file():
                        continue
                    suffix = fpath.suffix.lower()
                    if suffix in ALL_VAULT_SUFFIXES:
                        files.append(fpath)
                    elif suffix == ".jsonl" and "ideas" in fpath.name.lower():
                        files.append(fpath)
            return sorted(files)

        # -- general walk (kailash, psmv, research) --------------------------
        skip_dirs = SKIP_DIRS | (PSMV_SKIP_DIRS if tier == "psmv" else frozenset())

        for fpath in sorted(source_dir.rglob("*")):
            if not fpath.is_file():
                continue

            # Check against skip-dir set
            try:
                rel_parts = set(fpath.relative_to(source_dir).parts)
            except ValueError:
                continue
            if rel_parts & skip_dirs:
                continue

            suffix = fpath.suffix.lower()
            if suffix not in ALL_VAULT_SUFFIXES:
                continue

            # Skip binary files that sneak through extension checks
            if tier == "research" and suffix in {
                ".pdf",
                ".png",
                ".csv",
                ".jpg",
                ".jpeg",
                ".gif",
            }:
                continue

            # Skip zero-byte cloud-only placeholders (Google Drive sync)
            try:
                if fpath.stat().st_size == 0:
                    continue
            except OSError:
                continue

            files.append(fpath)

        return files

    # -- single-source ingestion ---------------------------------------------

    def ingest_source(
        self,
        source_dir: Path,
        *,
        tier: str,
        vault_subdir: str,
        max_files: int = 2000,
        file_filter: Callable[[Path], bool] | None = None,
    ) -> IngestReport:
        """Ingest files from a single source directory into the concept graph.

        Each file is read, passed through :class:`SemanticDigester`, and the
        resulting :class:`ConceptNode` objects are added to the graph with
        tier-specific metadata.  For the ``kailash`` tier, files containing
        key research terms receive a salience boost.

        Args:
            source_dir: Root directory of the source.
            tier: Tier name (used for metadata tagging and collection strategy).
            vault_subdir: Subdirectory name under the vault for generated notes.
            max_files: Maximum number of files to process from this source.
            file_filter: Optional predicate -- only files where
                ``file_filter(path)`` returns ``True`` are digested.

        Returns:
            An :class:`IngestReport` summarising what was ingested.

        Raises:
            RuntimeError: If :meth:`load_graph` has not been called.
        """
        if self.graph is None:
            raise RuntimeError("Call load_graph() before ingesting sources")

        report = IngestReport(source=tier)

        file_paths = self._collect_files(source_dir, tier=tier)
        report.files_scanned = len(file_paths)
        files_processed = 0

        for fpath in file_paths:
            if files_processed >= max_files:
                break

            if file_filter is not None and not file_filter(fpath):
                report.files_skipped += 1
                continue

            # -- read file ---------------------------------------------------
            try:
                # Skip cloud-only placeholders (size 0) and guard against
                # Google Drive sync timeouts by checking size first.
                if fpath.stat().st_size == 0:
                    report.files_skipped += 1
                    continue
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, TimeoutError) as exc:
                report.errors.append(f"Cannot read {fpath}: {exc}")
                report.files_skipped += 1
                continue

            # Skip stubs / empty files
            if len(content.strip()) < _MIN_CONTENT_LENGTH:
                report.files_skipped += 1
                continue

            # -- digest ------------------------------------------------------
            suffix = fpath.suffix.lower()
            # The digester does not know about .tex; treat as .txt
            digest_suffix = ".txt" if suffix in ALLOWED_TEX_SUFFIXES else suffix

            rel_path = str(fpath)
            try:
                nodes = self.digester.digest_file(
                    content, rel_path, suffix=digest_suffix
                )
            except Exception as exc:
                report.errors.append(f"Digest error {fpath}: {exc}")
                report.files_skipped += 1
                continue

            if not nodes:
                report.files_skipped += 1
                continue

            # -- apply source-specific metadata and salience -----------------
            for node in nodes:
                node.metadata["vault_tier"] = tier
                node.metadata["vault_subdir"] = vault_subdir

                if tier == "kailash":
                    boost_count = len(_SALIENCE_BOOST_RE.findall(content))
                    if boost_count > 0:
                        node.salience = min(1.0, node.salience * 1.5)

            # -- add to graph -----------------------------------------------
            for node in nodes:
                self.graph.add_node(node)
                self._source_nodes[tier].append(node.id)
                report.concepts_added += 1

            files_processed += 1
            report.files_digested += 1

        logger.info(
            "[vault] %s: %d files -> %d concepts (%d errors)",
            tier,
            report.files_digested,
            report.concepts_added,
            len(report.errors),
        )
        return report

    # -- batch ingestion -----------------------------------------------------

    def ingest_all(self) -> list[IngestReport]:
        """Ingest all configured sources in order.

        Uses :data:`DEFAULT_SOURCES` for tier configuration.  Prints progress
        to stdout for CLI feedback.

        Returns:
            List of per-source :class:`IngestReport` objects.
        """
        reports: list[IngestReport] = []

        for tier, source_dir, max_files, vault_subdir in self.DEFAULT_SOURCES:
            print(f"[vault] Ingesting {tier} from {source_dir}...")  # noqa: T201
            report = self.ingest_source(
                source_dir,
                tier=tier,
                vault_subdir=vault_subdir,
                max_files=max_files,
            )
            reports.append(report)
            print(  # noqa: T201
                f"  -> {report.files_digested} files, "
                f"{report.concepts_added} concepts"
            )
            if report.errors:
                print(f"  -> {len(report.errors)} errors")  # noqa: T201

        return reports

    # -- vault generation ----------------------------------------------------

    def generate_vault(self) -> VaultReport:
        """Generate vault notes from the current concept graph.

        Creates a directory hierarchy under :attr:`vault_dir`, writes one
        Markdown note per concept node (filtered by salience), and generates
        per-tier index files plus a master index.

        Returns:
            A :class:`VaultReport` summarising what was generated.

        Raises:
            RuntimeError: If :meth:`load_graph` has not been called.
        """
        if self.graph is None:
            raise RuntimeError("Call load_graph() before generating the vault")

        report = VaultReport()

        # -- directory skeleton ----------------------------------------------
        subdirs = [
            "00-ARCHITECTURE",
            "01-KAILASH",
            "02-PSMV",
            "03-RESEARCH",
            "04-DHARMA-SWARM",
            "05-CONCEPTS",
            "06-STATE",
        ]
        for d in subdirs:
            (self.vault_dir / d).mkdir(parents=True, exist_ok=True)
            report.directories_created.append(d)

        # -- bucket nodes by tier --------------------------------------------
        all_nodes = self.graph.all_nodes()
        nodes_by_tier: dict[str, list[ConceptNode]] = defaultdict(list)
        for node in all_nodes:
            tier = node.metadata.get("vault_tier", "dharma_swarm")
            nodes_by_tier[tier].append(node)

        tier_to_dir: dict[str, str] = {
            "kailash": "01-KAILASH",
            "psmv": "02-PSMV",
            "research": "03-RESEARCH",
            "claude": "03-RESEARCH",
            "dharma_swarm": "04-DHARMA-SWARM",
            "state": "06-STATE",
        }

        # -- individual notes ------------------------------------------------
        for tier, nodes in nodes_by_tier.items():
            subdir = tier_to_dir.get(tier, "04-DHARMA-SWARM")
            for node in nodes:
                # Low-salience nodes from large tiers are not worth a note
                if (
                    node.salience < _SALIENCE_THRESHOLD
                    and tier not in ("claude", "research")
                ):
                    continue

                note_content = self._generate_note(node)
                slug = self._slugify(node.name)
                note_path = self.vault_dir / subdir / f"{slug}.md"

                # Avoid overwriting on name collision
                if note_path.exists():
                    note_path = (
                        self.vault_dir / subdir / f"{slug}-{node.id[:6]}.md"
                    )

                note_path.write_text(note_content, encoding="utf-8")
                report.notes_generated += 1
                report.wikilinks_created += note_content.count("[[")

        # -- cross-cutting concept notes (high-degree hubs) ------------------
        self._generate_concept_notes(report)

        # -- per-tier indexes ------------------------------------------------
        self._generate_indexes(nodes_by_tier, tier_to_dir, report)

        # -- master index ----------------------------------------------------
        self._generate_master_index(report)

        logger.info("[vault] Generated vault: %s", report.summary())
        return report

    # -- note generation helpers ---------------------------------------------

    def _generate_note(self, node: ConceptNode) -> str:
        """Generate a vault Markdown note for a single concept node.

        Includes YAML frontmatter with metadata, definition, key concepts
        (claims and formal structures), wikilinked connections from graph
        edges, source reference, and research annotations.
        """
        tier = node.metadata.get("vault_tier", "unknown")
        tags: list[str] = []
        if node.category:
            tags.append(node.category)
        tags.extend(node.formal_structures[:5])

        lines: list[str] = [
            "---",
            f"title: {node.name}",
            f"source: {node.source_file}",
            f"tier: {tier}",
            f"category: {node.category}",
            f"salience: {node.salience:.2f}",
            f"created: {node.created_at.isoformat()}",
            f"tags: [{', '.join(tags)}]",
            "---",
            "",
            f"# {node.name}",
            "",
        ]

        # Definition
        if node.definition:
            lines.append(node.definition)
            lines.append("")

        # Key concepts (claims + formal structures)
        if node.claims or node.formal_structures:
            lines.append("## Key Concepts")
            lines.append("")
            for claim in node.claims[:10]:
                lines.append(f"- {claim}")
            for struct in node.formal_structures:
                lines.append(f"- *{struct}*")
            lines.append("")

        # Connections via graph edges (wikilinks)
        if self.graph is not None:
            connections = self._get_connections(node)
            if connections:
                lines.append("## Connections")
                lines.append("")
                for section, targets in connections.items():
                    target_links = ", ".join(
                        f"[[{self._slugify(t)}]]" for t in targets
                    )
                    lines.append(f"- **{section}**: {target_links}")
                lines.append("")

        # Source reference
        if node.source_file:
            source_ref = node.source_file
            if node.source_line:
                source_ref += f":{node.source_line}"
            lines.append("## Source")
            lines.append("")
            lines.append(f"`{source_ref}`")
            lines.append("")

        # Research annotations (if any exist on the graph)
        if self.graph is not None:
            annotations = self.graph.annotations_for(node.id)
            if annotations:
                lines.append("## Research Annotations")
                lines.append("")
                for ann in annotations:
                    lines.append(
                        f"- [{ann.connection_type.value}] {ann.external_source}"
                    )
                    if ann.citation:
                        lines.append(f"  > {ann.citation}")
                lines.append("")

        return "\n".join(lines)

    def _get_connections(self, node: ConceptNode) -> dict[str, list[str]]:
        """Get wikilink connections for a node, grouped by edge type.

        Includes both outgoing and incoming edges so that every relationship
        is visible from either side of the edge.
        """
        if self.graph is None:
            return {}

        connections: dict[str, list[str]] = defaultdict(list)

        # Outgoing edges
        for edge in self.graph.edges_from(node.id):
            target = self.graph.get_node(edge.target_id)
            if target is not None:
                section = _EDGE_SECTION_MAP.get(edge.edge_type, "Related")
                connections[section].append(target.name)

        # Incoming edges (reverse relationship label)
        for edge in self.graph.edges_to(node.id):
            source = self.graph.get_node(edge.source_id)
            if source is not None:
                section = _EDGE_SECTION_MAP.get(edge.edge_type, "Related")
                connections[f"Referenced by ({section.lower()})"].append(
                    source.name
                )

        return dict(connections)

    def _generate_concept_notes(self, report: VaultReport) -> None:
        """Generate notes for high-degree cross-cutting concepts.

        A concept with degree >= :data:`_HUB_DEGREE_THRESHOLD` is considered
        a hub that bridges multiple source tiers and warrants its own note
        in ``05-CONCEPTS/``.
        """
        if self.graph is None:
            return

        concept_dir = self.vault_dir / "05-CONCEPTS"
        for node in self.graph.all_nodes():
            degree = self.graph.degree(node.id)
            if degree < _HUB_DEGREE_THRESHOLD:
                continue

            note_content = self._generate_note(node)
            slug = self._slugify(node.name)
            note_path = concept_dir / f"{slug}.md"
            if not note_path.exists():
                note_path.write_text(note_content, encoding="utf-8")
                report.notes_generated += 1
                report.wikilinks_created += note_content.count("[[")

    def _generate_indexes(
        self,
        nodes_by_tier: dict[str, list[ConceptNode]],
        tier_to_dir: dict[str, str],
        report: VaultReport,
    ) -> None:
        """Generate per-tier ``_INDEX.md`` files with sortable tables."""
        for tier, nodes in nodes_by_tier.items():
            subdir = tier_to_dir.get(tier, "04-DHARMA-SWARM")
            index_path = self.vault_dir / subdir / "_INDEX.md"

            sorted_nodes = sorted(
                nodes, key=lambda n: n.salience, reverse=True
            )
            # Only list nodes that pass the salience filter
            noted = [
                n
                for n in sorted_nodes
                if n.salience >= _SALIENCE_THRESHOLD
                or tier in ("claude", "research")
            ]

            lines: list[str] = [
                f"# {tier.upper()} Index",
                "",
                f"**{len(noted)} concepts** from {tier}",
                "",
                "| Concept | Category | Salience |",
                "|---------|----------|----------|",
            ]
            for node in noted[:_MAX_INDEX_ENTRIES]:
                slug = self._slugify(node.name)
                lines.append(
                    f"| [[{slug}]] | {node.category} | {node.salience:.2f} |"
                )
            lines.append("")

            index_path.write_text("\n".join(lines), encoding="utf-8")
            report.indexes_generated += 1

    def _generate_master_index(self, report: VaultReport) -> None:
        """Generate the master ``00-INDEX.md`` with cross-tier statistics."""
        if self.graph is None:
            return

        all_nodes = self.graph.all_nodes()
        categories: dict[str, int] = defaultdict(int)
        tiers: dict[str, int] = defaultdict(int)
        for node in all_nodes:
            categories[node.category or "uncategorized"] += 1
            tiers[node.metadata.get("vault_tier", "unknown")] += 1

        lines: list[str] = [
            "# Semantic Vault -- Master Index",
            "",
            f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
            f"**Total concepts**: {self.graph.node_count}",
            f"**Total edges**: {self.graph.edge_count}",
            f"**Vault notes**: {report.notes_generated}",
            f"**Wikilinks**: {report.wikilinks_created}",
            "",
            "## Sources",
            "",
            "| Source | Concepts |",
            "|--------|----------|",
        ]
        for tier, count in sorted(tiers.items(), key=lambda x: -x[1]):
            lines.append(f"| {tier} | {count} |")

        lines.extend(
            [
                "",
                "## Categories",
                "",
                "| Category | Count |",
                "|----------|-------|",
            ]
        )
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            lines.append(f"| {cat} | {count} |")

        lines.extend(
            [
                "",
                "## Directories",
                "",
                "- [[01-KAILASH/_INDEX|Kailash Obsidian Vault]]",
                "- [[02-PSMV/_INDEX|Persistent Semantic Memory Vault]]",
                "- [[03-RESEARCH/_INDEX|Research (R_V Paper + CLAUDE Companions)]]",
                "- [[04-DHARMA-SWARM/_INDEX|dharma_swarm Modules]]",
                "- [[05-CONCEPTS/_INDEX|Cross-Cutting Concepts]]",
                "- [[06-STATE/_INDEX|System State]]",
                "",
                "## Top Concepts (by salience)",
                "",
            ]
        )
        top = self.graph.high_salience_nodes(threshold=0.7)[:20]
        for node in top:
            slug = self._slugify(node.name)
            lines.append(
                f"- [[{slug}]] -- salience {node.salience:.2f}, {node.category}"
            )

        lines.append("")
        master_path = self.vault_dir / "00-INDEX.md"
        master_path.write_text("\n".join(lines), encoding="utf-8")
        report.indexes_generated += 1

    # -- search and status ---------------------------------------------------

    def search(self, query: str, *, limit: int = 20) -> list[ConceptNode]:
        """Search vault concepts by name, definition, or claim substring.

        Results are ranked by match quality + salience and capped at *limit*.

        Args:
            query: Case-insensitive search string.
            limit: Maximum number of results to return.

        Returns:
            List of matching :class:`ConceptNode` objects, best matches first.
        """
        if self.graph is None:
            return []

        query_lower = query.lower()
        scored: list[tuple[float, ConceptNode]] = []

        for node in self.graph.all_nodes():
            score = 0.0
            if query_lower in node.name.lower():
                score = 2.0
            elif query_lower in node.definition.lower():
                score = 1.0
            elif any(query_lower in c.lower() for c in node.claims):
                score = 0.5

            if score > 0:
                scored.append((score + node.salience, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored[:limit]]

    def vault_status(self) -> dict[str, Any]:
        """Return vault statistics as a JSON-serialisable dict.

        Useful for ``dgc vault status`` or dashboard integration.

        Returns:
            Dict with keys ``exists``, ``vault_dir``, ``notes``,
            ``wikilinks``, ``graph_path``, ``graph_exists``.
        """
        if not self.vault_dir.exists():
            return {"exists": False}

        note_count = 0
        wikilink_count = 0
        for md_file in self.vault_dir.rglob("*.md"):
            note_count += 1
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                wikilink_count += content.count("[[")
            except OSError:
                pass

        return {
            "exists": True,
            "vault_dir": str(self.vault_dir),
            "notes": note_count,
            "wikilinks": wikilink_count,
            "graph_path": str(self.graph_path),
            "graph_exists": self.graph_path.exists(),
        }

    # -- utilities -----------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a concept name to a vault-safe filename slug.

        Strips non-alphanumeric characters, replaces whitespace with hyphens,
        and title-cases each word.  Truncates to 80 characters.

        Examples::

            >>> VaultBridge._slugify("R_V Metric (Contraction)")
            'RV-Metric-Contraction'
            >>> VaultBridge._slugify("")
            'Unnamed'
        """
        slug = re.sub(r"[^a-zA-Z0-9\s_-]", "", name)
        slug = re.sub(r"[\s_]+", "-", slug.strip())
        slug = "-".join(w.capitalize() for w in slug.split("-") if w)
        return slug[:80] or "Unnamed"


__all__ = ["VaultBridge", "IngestReport", "VaultReport"]
