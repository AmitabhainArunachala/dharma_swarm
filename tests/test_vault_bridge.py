"""Tests for the vault_bridge module."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from dharma_swarm.semantic_gravity import (
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
)
from dharma_swarm.vault_bridge import IngestReport, VaultBridge, VaultReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    name: str = "Test Concept",
    definition: str = "A test concept for unit testing.",
    salience: float = 0.5,
    category: str = "engineering",
    tier: str = "kailash",
    vault_subdir: str = "notes",
    **overrides: object,
) -> ConceptNode:
    """Build a ConceptNode with sensible defaults."""
    return ConceptNode(
        name=name,
        definition=definition,
        salience=salience,
        category=category,
        metadata={"vault_tier": tier, "vault_subdir": vault_subdir},
        **overrides,  # type: ignore[arg-type]
    )


def _make_graph(*nodes: ConceptNode, edges: list[ConceptEdge] | None = None) -> ConceptGraph:
    """Build a ConceptGraph populated with the given nodes and edges."""
    graph = ConceptGraph()
    for node in nodes:
        graph.add_node(node)
    for edge in edges or []:
        graph.add_edge(edge)
    return graph


def _make_bridge(tmp_path: Path) -> VaultBridge:
    """Create a VaultBridge wired to tmp_path subdirectories."""
    vault_dir = tmp_path / "vault"
    graph_path = tmp_path / "graph.json"
    return VaultBridge(vault_dir=vault_dir, graph_path=graph_path)


def _populate_md_files(
    directory: Path,
    count: int = 3,
    *,
    content: str = "This is a test markdown file with enough content to comfortably pass the minimum one-hundred byte size threshold for ingestion.\n",
    prefix: str = "note",
    suffix: str = ".md",
) -> list[Path]:
    """Create *count* markdown files in *directory*, returning their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        fp = directory / f"{prefix}_{i}{suffix}"
        fp.write_text(content)
        paths.append(fp)
    return paths


# ---------------------------------------------------------------------------
# IngestReport defaults
# ---------------------------------------------------------------------------


def test_ingest_report_defaults():
    report = IngestReport(source="test")
    assert report.source == "test"
    assert report.files_scanned == 0
    assert report.files_digested == 0
    assert report.files_skipped == 0
    assert report.concepts_added == 0
    assert report.edges_added == 0
    assert report.errors == []


def test_ingest_report_summary():
    report = IngestReport(source="kailash", files_scanned=10, files_digested=8, concepts_added=20)
    summary = report.summary()
    assert "kailash" in summary
    assert "8/10" in summary
    assert "20" in summary


# ---------------------------------------------------------------------------
# VaultReport defaults
# ---------------------------------------------------------------------------


def test_vault_report_defaults():
    report = VaultReport()
    assert report.notes_generated == 0
    assert report.wikilinks_created == 0
    assert report.indexes_generated == 0
    assert report.directories_created == []


def test_vault_report_summary():
    report = VaultReport(notes_generated=5, wikilinks_created=12, indexes_generated=3)
    summary = report.summary()
    assert "5 notes" in summary
    assert "12 wikilinks" in summary
    assert "3 indexes" in summary


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_normal_name(self):
        assert VaultBridge._slugify("semantic gravity") == "Semantic-Gravity"

    def test_special_chars_removed(self):
        slug = VaultBridge._slugify("hello! world? (test)")
        # Parentheses and punctuation stripped, words kept
        assert "!" not in slug
        assert "?" not in slug
        assert "(" not in slug
        assert ")" not in slug
        assert "Hello" in slug
        assert "World" in slug

    def test_long_name_truncated(self):
        long_name = "a " * 100  # 200 chars
        slug = VaultBridge._slugify(long_name)
        assert len(slug) <= 80

    def test_empty_string(self):
        assert VaultBridge._slugify("") == "Unnamed"

    def test_whitespace_only(self):
        assert VaultBridge._slugify("   ") == "Unnamed"

    def test_underscores_become_hyphens(self):
        slug = VaultBridge._slugify("concept_node_test")
        assert "_" not in slug
        assert "-" in slug
        assert slug == "Concept-Node-Test"


# ---------------------------------------------------------------------------
# VaultBridge.__init__
# ---------------------------------------------------------------------------


def test_vault_bridge_init(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    graph_path = tmp_path / "graph.json"
    bridge = VaultBridge(vault_dir=vault_dir, graph_path=graph_path)
    assert bridge.vault_dir == vault_dir
    assert bridge.graph_path == graph_path
    assert bridge.graph is None


# ---------------------------------------------------------------------------
# load_graph
# ---------------------------------------------------------------------------


def test_load_graph_creates_empty(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    graph = asyncio.run(bridge.load_graph())
    assert isinstance(graph, ConceptGraph)
    assert graph.node_count == 0
    assert graph.edge_count == 0
    assert bridge.graph is graph


# ---------------------------------------------------------------------------
# _collect_files
# ---------------------------------------------------------------------------


def test_collect_files_missing_dir(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    missing = tmp_path / "nonexistent"
    result = bridge._collect_files(missing, tier="kailash")
    assert result == []


def test_collect_files_claude_tier(tmp_path: Path):
    """Claude tier collects CLAUDE1-9.md from HOME, not from source_dir."""
    bridge = _make_bridge(tmp_path)
    # The claude tier always looks in HOME for CLAUDE1-9.md
    # We test that _collect_files with tier="claude" returns files from HOME
    result = bridge._collect_files(tmp_path, tier="claude")
    # All returned files should match the CLAUDE[1-9].md pattern
    for p in result:
        assert p.name.startswith("CLAUDE")
        assert p.name.endswith(".md")


def test_collect_files_md_and_tex(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    source = tmp_path / "research"
    source.mkdir()
    (source / "paper.tex").write_text("\\begin{document}")
    (source / "notes.md").write_text("# Notes")
    (source / "data.csv").write_text("a,b,c")  # should be excluded

    result = bridge._collect_files(source, tier="research")
    names = [p.name for p in result]
    assert "paper.tex" in names
    assert "notes.md" in names
    assert "data.csv" not in names


def test_collect_files_state_tier(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    source = tmp_path / "state"
    source.mkdir()
    shared = source / "shared"
    shared.mkdir()
    (shared / "notes.md").write_text("# Notes")
    (shared / "data.txt").write_text("data")
    (shared / "ideas_log.jsonl").write_text('{"idea": "test"}')
    (shared / "random.json").write_text("{}")  # not collected

    result = bridge._collect_files(source, tier="state")
    names = [p.name for p in result]
    assert "notes.md" in names
    assert "data.txt" in names
    assert "ideas_log.jsonl" in names
    assert "random.json" not in names


# ---------------------------------------------------------------------------
# ingest_source
# ---------------------------------------------------------------------------


def test_ingest_source_basic(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    source = tmp_path / "kailash"
    _populate_md_files(source, count=5)

    report = bridge.ingest_source(source, tier="kailash", vault_subdir="spiritual")
    assert report.source == "kailash"
    assert report.files_scanned == 5
    assert report.files_digested == 5
    assert report.concepts_added >= 5  # digester may extract multiple concepts per file
    assert report.files_skipped == 0
    assert report.errors == []
    assert bridge.graph is not None
    assert bridge.graph.node_count >= 5


def test_ingest_source_skips_tiny_files(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    source = tmp_path / "tiny"
    source.mkdir()
    # Tiny file: under 100 bytes
    (source / "small.md").write_text("hi")
    # Normal file: over 100 bytes
    _populate_md_files(source, count=1, prefix="big")

    report = bridge.ingest_source(source, tier="kailash", vault_subdir="notes")
    assert report.files_scanned == 2
    assert report.files_skipped == 1
    assert report.files_digested == 1


def test_ingest_source_salience_boost(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    source = tmp_path / "kailash_boost"
    source.mkdir()

    # File with Phoenix keyword -- should get boosted
    boosted_content = (
        "This file discusses the Phoenix Protocol and its implications "
        "for recursive self-reference in large language models. "
        "The results are quite interesting and worth exploring further."
    )
    (source / "phoenix_paper.md").write_text(boosted_content)

    # File without any keywords -- should stay at default
    normal_content = (
        "This file discusses everyday topics that are entirely unrelated "
        "to the special keywords. It contains enough text to pass the "
        "minimum size threshold for ingestion."
    )
    (source / "normal_note.md").write_text(normal_content)

    report = bridge.ingest_source(source, tier="kailash", vault_subdir="notes")
    assert report.files_digested == 2

    nodes = bridge.graph.all_nodes()
    # Find the nodes from each file by source_file path
    phoenix_nodes = [n for n in nodes if "phoenix_paper" in n.source_file]
    normal_nodes = [n for n in nodes if "normal_note" in n.source_file]
    assert len(phoenix_nodes) > 0
    assert len(normal_nodes) > 0

    # Phoenix nodes should have boosted salience
    for pn in phoenix_nodes:
        assert pn.metadata.get("vault_tier") == "kailash"
    # At least one phoenix node should have higher salience than normal nodes
    max_phoenix = max(n.salience for n in phoenix_nodes)
    max_normal = max(n.salience for n in normal_nodes)
    assert max_phoenix > max_normal


def test_ingest_source_tex_files(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    source = tmp_path / "research"
    source.mkdir()
    tex_content = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "This is a LaTeX paper about R_V metric contraction "
        "in transformer representations. The results demonstrate "
        "significant geometric signatures.\n"
        "\\end{document}\n"
    )
    (source / "paper.tex").write_text(tex_content)

    report = bridge.ingest_source(source, tier="research", vault_subdir="papers")
    assert report.files_digested == 1
    assert report.concepts_added >= 1

    # Verify the node was created (category determined by digester content analysis)
    node = bridge.graph.all_nodes()[0]
    assert node.metadata["vault_tier"] == "research"


def test_ingest_source_with_file_filter(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    source = tmp_path / "filtered"
    _populate_md_files(source, count=4)

    # Only ingest files with "0" or "2" in the name
    report = bridge.ingest_source(
        source,
        tier="kailash",
        vault_subdir="notes",
        file_filter=lambda p: "0" in p.name or "2" in p.name,
    )
    assert report.files_digested == 2


def test_ingest_source_requires_graph(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(RuntimeError, match="load_graph"):
        bridge.ingest_source(source, tier="kailash", vault_subdir="notes")


# ---------------------------------------------------------------------------
# _generate_note
# ---------------------------------------------------------------------------


def test_generate_note(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    node = _make_node(
        name="Semantic Gravity",
        definition="Dense clusters attract related concepts.",
        salience=0.85,
        category="engineering",
    )
    bridge.graph.add_node(node)

    note = bridge._generate_note(node)

    # YAML frontmatter
    assert note.startswith("---\n")
    assert "title: Semantic Gravity" in note
    assert "category: engineering" in note
    assert "salience: 0.85" in note

    # Heading and body
    assert "# Semantic Gravity" in note
    assert "Dense clusters attract related concepts." in note


def test_generate_note_with_connections(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    node_a = _make_node(name="Concept A", definition="First concept.")
    node_b = _make_node(name="Concept B", definition="Second concept.")
    bridge.graph.add_node(node_a)
    bridge.graph.add_node(node_b)

    edge = ConceptEdge(
        source_id=node_a.id,
        target_id=node_b.id,
        edge_type=EdgeType.REFERENCES,
    )
    bridge.graph.add_edge(edge)

    note = bridge._generate_note(node_a)
    assert "## Connections" in note
    assert "**References**" in note
    assert "[[Concept-B]]" in note


def test_generate_note_with_claims(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    node = _make_node(
        name="Claim Node",
        claims=["R_V < 1.0 implies self-referential processing"],
        formal_structures=["fixed_point", "participation_ratio"],
    )
    bridge.graph.add_node(node)

    note = bridge._generate_note(node)
    assert "## Key Concepts" in note
    assert "R_V < 1.0" in note
    assert "*fixed_point*" in note


# ---------------------------------------------------------------------------
# generate_vault
# ---------------------------------------------------------------------------


def test_generate_vault_creates_structure(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    # Add nodes to different tiers
    for i in range(3):
        bridge.graph.add_node(_make_node(
            name=f"Kailash Concept {i}",
            salience=0.7,
            tier="kailash",
            vault_subdir="01-KAILASH",
        ))
    for i in range(2):
        bridge.graph.add_node(_make_node(
            name=f"Research Concept {i}",
            salience=0.6,
            tier="research",
            vault_subdir="03-RESEARCH",
        ))

    report = bridge.generate_vault()

    assert report.notes_generated == 5
    assert report.indexes_generated >= 2  # at least kailash + research tier indexes
    assert len(report.directories_created) == 7  # all 7 standard subdirs
    assert (bridge.vault_dir / "01-KAILASH").is_dir()
    assert (bridge.vault_dir / "03-RESEARCH").is_dir()
    assert (bridge.vault_dir / "05-CONCEPTS").is_dir()


def test_generate_vault_filters_low_salience(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    # Low salience, non-exempt tier -- should be filtered
    bridge.graph.add_node(_make_node(
        name="Low Salience",
        salience=0.1,
        tier="kailash",
        vault_subdir="01-KAILASH",
    ))
    # Low salience but research tier -- should be kept
    bridge.graph.add_node(_make_node(
        name="Research Low",
        salience=0.1,
        tier="research",
        vault_subdir="03-RESEARCH",
    ))
    # Low salience but claude tier -- should be kept
    bridge.graph.add_node(_make_node(
        name="Claude Low",
        salience=0.1,
        tier="claude",
        vault_subdir="03-RESEARCH",
    ))
    # Normal salience -- should be kept
    bridge.graph.add_node(_make_node(
        name="Normal Salience",
        salience=0.6,
        tier="kailash",
        vault_subdir="01-KAILASH",
    ))

    report = bridge.generate_vault()

    # 3 notes kept (research, claude, normal), 1 filtered (low kailash)
    assert report.notes_generated == 3


def test_generate_vault_master_index(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(name="Test Node", salience=0.8, tier="kailash"))
    bridge.generate_vault()

    master = bridge.vault_dir / "00-INDEX.md"
    assert master.exists()
    content = master.read_text()
    assert "Semantic Vault" in content
    assert "Total concepts" in content


# ---------------------------------------------------------------------------
# vault_status
# ---------------------------------------------------------------------------


def test_vault_status_empty(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    # vault_dir has not been created
    status = bridge.vault_status()
    assert status["exists"] is False


def test_vault_status_populated(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    # Add nodes and generate vault
    for i in range(4):
        bridge.graph.add_node(_make_node(
            name=f"Status Node {i}",
            salience=0.8,
            tier="kailash",
            vault_subdir="01-KAILASH",
        ))
    # Add an edge so notes have wikilinks
    nodes = bridge.graph.all_nodes()
    edge = ConceptEdge(
        source_id=nodes[0].id,
        target_id=nodes[1].id,
        edge_type=EdgeType.IMPLEMENTS,
    )
    bridge.graph.add_edge(edge)

    bridge.generate_vault()

    status = bridge.vault_status()
    assert status["exists"] is True
    assert status["notes"] >= 4  # 4 notes + indexes
    assert status["wikilinks"] > 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_by_name(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(name="Phoenix Protocol", salience=0.9))
    bridge.graph.add_node(_make_node(name="R_V Metric", salience=0.8))
    bridge.graph.add_node(_make_node(name="Attention Head", salience=0.7))

    results = bridge.search("phoenix")
    assert len(results) == 1
    assert results[0].name == "Phoenix Protocol"


def test_search_by_definition(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(
        name="Concept A",
        definition="The recursive eigenform converges.",
        salience=0.6,
    ))
    bridge.graph.add_node(_make_node(
        name="Concept B",
        definition="Ordinary processing pattern.",
        salience=0.5,
    ))

    results = bridge.search("eigenform")
    assert len(results) == 1
    assert results[0].name == "Concept A"


def test_search_by_claims(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(
        name="Concept C",
        definition="No match here.",
        claims=["R_V contraction implies witnessing"],
        salience=0.7,
    ))
    bridge.graph.add_node(_make_node(
        name="Concept D",
        definition="Totally unrelated.",
        salience=0.5,
    ))

    results = bridge.search("witnessing")
    assert len(results) == 1
    assert results[0].name == "Concept C"


def test_search_respects_limit(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    for i in range(10):
        bridge.graph.add_node(_make_node(name=f"Match {i}", salience=0.5))

    results = bridge.search("match", limit=3)
    assert len(results) == 3


def test_search_sorted_by_score_plus_salience(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(name="Match Low", salience=0.3))
    bridge.graph.add_node(_make_node(name="Match High", salience=0.9))
    bridge.graph.add_node(_make_node(name="Match Mid", salience=0.6))

    results = bridge.search("match")
    assert len(results) == 3
    assert results[0].name == "Match High"
    assert results[1].name == "Match Mid"
    assert results[2].name == "Match Low"


def test_search_no_graph(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    results = bridge.search("anything")
    assert results == []


# ---------------------------------------------------------------------------
# _get_connections
# ---------------------------------------------------------------------------


def test_get_connections(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    node_a = _make_node(name="Source Node")
    node_b = _make_node(name="Target Node")
    node_c = _make_node(name="Another Target")

    bridge.graph.add_node(node_a)
    bridge.graph.add_node(node_b)
    bridge.graph.add_node(node_c)

    bridge.graph.add_edge(ConceptEdge(
        source_id=node_a.id,
        target_id=node_b.id,
        edge_type=EdgeType.REFERENCES,
    ))
    bridge.graph.add_edge(ConceptEdge(
        source_id=node_a.id,
        target_id=node_c.id,
        edge_type=EdgeType.IMPLEMENTS,
    ))
    # Incoming edge
    bridge.graph.add_edge(ConceptEdge(
        source_id=node_c.id,
        target_id=node_a.id,
        edge_type=EdgeType.DEPENDS_ON,
    ))

    connections = bridge._get_connections(node_a)

    # Outgoing edges use display names from _EDGE_SECTION_MAP
    assert "References" in connections
    assert "Target Node" in connections["References"]
    assert "Implements" in connections
    assert "Another Target" in connections["Implements"]
    # Incoming edge uses reversed label
    assert "Referenced by (depends on)" in connections
    assert "Another Target" in connections["Referenced by (depends on)"]


def test_get_connections_empty(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    node = _make_node(name="Isolated Node")
    bridge.graph.add_node(node)

    connections = bridge._get_connections(node)
    assert connections == {}


# ---------------------------------------------------------------------------
# save_graph round-trip
# ---------------------------------------------------------------------------


def test_save_and_reload_graph(tmp_path: Path):
    bridge = _make_bridge(tmp_path)
    asyncio.run(bridge.load_graph())

    bridge.graph.add_node(_make_node(name="Persistent Node", salience=0.75))
    asyncio.run(bridge.save_graph())

    assert bridge.graph_path.exists()

    # Reload into a new bridge
    bridge2 = _make_bridge(tmp_path)
    asyncio.run(bridge2.load_graph())
    assert bridge2.graph.node_count == 1
    found = bridge2.graph.find_by_name("Persistent Node")
    assert len(found) == 1
    assert found[0].salience == pytest.approx(0.75)
