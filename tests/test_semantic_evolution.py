"""Tests for the Semantic Evolution Engine (5-module pipeline).

Covers:
  - semantic_gravity: ConceptGraph, ConceptNode, edges, serialization
  - semantic_digester: file parsing, concept extraction
  - semantic_researcher: annotation, coverage
  - semantic_synthesizer: intersection detection, cluster generation
  - semantic_hardener: 6-angle hardening, reports
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.models import GateResult
from dharma_swarm.semantic_gravity import (
    AngleVerdict,
    ClusterFileSpec,
    ConceptEdge,
    ConceptGraph,
    ConceptNode,
    EdgeType,
    FileClusterSpec,
    HardeningAngle,
    HardeningReport,
    ResearchAnnotation,
    ResearchConnectionType,
    SemanticGravity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    name: str,
    *,
    category: str = "mathematical",
    salience: float = 0.8,
    formal_structures: list[str] | None = None,
    source_file: str = "dharma_swarm/monad.py",
    definition: str = "A test concept definition",
) -> ConceptNode:
    return ConceptNode(
        name=name,
        category=category,
        salience=salience,
        formal_structures=formal_structures or [],
        source_file=source_file,
        definition=definition,
    )


def _make_graph() -> ConceptGraph:
    """Build a small but connected graph for testing."""
    g = ConceptGraph()

    n1 = _make_node("monad", formal_structures=["monad", "functor"])
    n2 = _make_node(
        "coalgebra",
        formal_structures=["coalgebra", "functor"],
        source_file="dharma_swarm/coalgebra.py",
    )
    n3 = _make_node(
        "sheaf",
        formal_structures=["sheaf", "cohomology"],
        source_file="dharma_swarm/sheaf.py",
    )
    n4 = _make_node(
        "entropy",
        category="measurement",
        formal_structures=["shannon_entropy"],
        source_file="dharma_swarm/metrics.py",
    )

    g.add_node(n1)
    g.add_node(n2)
    g.add_node(n3)
    g.add_node(n4)

    g.add_edge(ConceptEdge(
        source_id=n1.id, target_id=n2.id,
        edge_type=EdgeType.EXTENDS, weight=0.9,
    ))
    g.add_edge(ConceptEdge(
        source_id=n2.id, target_id=n3.id,
        edge_type=EdgeType.REFERENCES, weight=0.7,
    ))
    g.add_edge(ConceptEdge(
        source_id=n3.id, target_id=n4.id,
        edge_type=EdgeType.IMPORTS, weight=0.5,
    ))

    return g


# ===========================================================================
# semantic_gravity tests
# ===========================================================================


class TestConceptGraph:
    def test_add_and_get_node(self):
        g = ConceptGraph()
        n = _make_node("test")
        nid = g.add_node(n)
        assert g.get_node(nid) is n
        assert g.node_count == 1

    def test_find_by_name_case_insensitive(self):
        g = ConceptGraph()
        g.add_node(_make_node("Monad"))
        assert len(g.find_by_name("monad")) == 1
        assert len(g.find_by_name("MONAD")) == 1

    def test_find_by_file(self):
        g = ConceptGraph()
        g.add_node(_make_node("x", source_file="a.py"))
        g.add_node(_make_node("y", source_file="b.py"))
        assert len(g.find_by_file("a.py")) == 1

    def test_find_by_category(self):
        g = ConceptGraph()
        g.add_node(_make_node("x", category="mathematical"))
        g.add_node(_make_node("y", category="engineering"))
        assert len(g.find_by_category("mathematical")) == 1

    def test_edges_and_neighbors(self):
        g = _make_graph()
        nodes = g.all_nodes()
        monad = g.find_by_name("monad")[0]
        neighbors = g.neighbors(monad.id)
        assert len(neighbors) >= 1

    def test_high_salience_nodes(self):
        g = _make_graph()
        high = g.high_salience_nodes(threshold=0.7)
        assert len(high) >= 2

    def test_connected_components(self):
        g = _make_graph()
        components = g.connected_components()
        assert len(components) == 1  # All connected

    def test_density(self):
        g = _make_graph()
        d = g.density()
        assert 0.0 < d < 1.0

    def test_degree(self):
        g = _make_graph()
        monad = g.find_by_name("monad")[0]
        assert g.degree(monad.id) >= 1

    def test_annotations(self):
        g = _make_graph()
        monad = g.find_by_name("monad")[0]
        ann = ResearchAnnotation(
            concept_id=monad.id,
            connection_type=ResearchConnectionType.VALIDATION,
            external_source="Moggi 1991",
            field="category_theory",
        )
        g.add_annotation(ann)
        assert g.annotation_count == 1
        assert len(g.annotations_for(monad.id)) == 1

    def test_serialization_roundtrip(self):
        g = _make_graph()
        data = g.to_dict()
        g2 = ConceptGraph.from_dict(data)
        assert g2.node_count == g.node_count
        assert g2.edge_count == g.edge_count

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        g = _make_graph()
        path = tmp_path / "graph.json"
        await g.save(path)
        assert path.exists()
        g2 = await ConceptGraph.load(path)
        assert g2.node_count == g.node_count

    def test_shared_concepts(self):
        g = _make_graph()
        shared = g.shared_concepts("dharma_swarm/monad.py", "dharma_swarm/coalgebra.py")
        assert len(shared) >= 1


class TestSemanticGravity:
    def test_gravitational_mass(self):
        g = _make_graph()
        sg = SemanticGravity(g)
        cluster = FileClusterSpec(
            name="test",
            core_concepts=[n.id for n in g.all_nodes()[:2]],
            files=[
                ClusterFileSpec(path="a.py", cross_references=["monad"]),
            ],
        )
        sg.register_cluster(cluster)
        mass = sg.gravitational_mass(cluster)
        assert mass > 0.0

    def test_bridge_candidates(self):
        g = _make_graph()
        sg = SemanticGravity(g)
        bridges = sg.bridge_candidates()
        assert isinstance(bridges, list)

    def test_snapshot(self):
        g = _make_graph()
        sg = SemanticGravity(g)
        snap = sg.snapshot()
        assert snap.total_nodes == g.node_count
        assert snap.total_edges == g.edge_count


# ===========================================================================
# semantic_digester tests
# ===========================================================================


class TestSemanticDigester:
    def test_digest_python_file(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        py_file = tmp_path / "sample.py"
        py_file.write_text(
            '"""Module for testing monad operations."""\n'
            "\n"
            "class MonadTest:\n"
            '    """A test monad class implementing functor pattern."""\n'
            "    def bind(self, f):\n"
            '        """Monadic bind operation."""\n'
            "        return f(self.value)\n"
        )

        digester = SemanticDigester()
        nodes = digester.digest_file(
            py_file.read_text(), str(py_file), suffix=".py",
        )
        assert len(nodes) >= 1

    def test_digest_markdown_file(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        md_file = tmp_path / "spec.md"
        md_file.write_text(
            "# Monad Specification\n"
            "\n"
            "The **monad** pattern provides compositional structure.\n"
            "\n"
            "## Functor Laws\n"
            "\n"
            "Every monad must satisfy the functor identity law.\n"
        )

        digester = SemanticDigester()
        nodes = digester.digest_file(
            md_file.read_text(), str(md_file), suffix=".md",
        )
        assert len(nodes) >= 1

    def test_digest_directory(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        src = tmp_path / "dharma_swarm"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "monad.py").write_text(
            '"""Monad module."""\nclass Monad:\n    """A monad."""\n    pass\n'
        )

        digester = SemanticDigester()
        graph = digester.digest_directory(src)
        assert graph.node_count >= 1

    def test_digest_directory_builds_note_link_edges(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        vault = tmp_path / "vault"
        ideas = vault / "ideas"
        ideas.mkdir(parents=True)

        (ideas / "alpha.md").write_text(
            "---\n"
            "title: Alpha Field\n"
            "aliases: [alpha-field]\n"
            "related: [Beta Note]\n"
            "---\n"
            "# Alpha\n\n"
            "See [[Beta Note]] and [gamma](../gamma.txt).\n",
            encoding="utf-8",
        )
        (ideas / "beta.md").write_text(
            "# Beta Note\n\n"
            "A linked companion note.\n",
            encoding="utf-8",
        )
        (vault / "gamma.txt").write_text(
            "Gamma plain-text note referencing [[Alpha Field]].\n",
            encoding="utf-8",
        )

        digester = SemanticDigester()
        graph = digester.digest_directory(vault, max_files=10)

        alpha_nodes = graph.find_by_name("Alpha Field")
        beta_nodes = graph.find_by_name("Beta Note")
        gamma_nodes = graph.find_by_name("gamma")
        assert alpha_nodes
        assert beta_nodes
        assert gamma_nodes
        neighbors = {node.name for node in graph.neighbors(alpha_nodes[0].id)}
        assert "Beta Note" in neighbors
        assert "gamma" in neighbors

    def test_digest_text_file(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        txt_file = tmp_path / "insight.txt"
        txt_file.write_text(
            "Semantic fields and stigmergy can guide agent coordination.\n",
            encoding="utf-8",
        )

        digester = SemanticDigester()
        nodes = digester.digest_file(
            txt_file.read_text(),
            str(txt_file),
            suffix=".txt",
        )
        assert len(nodes) == 1
        assert nodes[0].recognition_type == "text_note"

    def test_empty_file(self, tmp_path):
        from dharma_swarm.semantic_digester import SemanticDigester

        empty = tmp_path / "empty.py"
        empty.write_text("")

        digester = SemanticDigester()
        nodes = digester.digest_file("", str(empty), suffix=".py")
        # Should not crash, may produce 0 nodes
        assert len(nodes) >= 0


# ===========================================================================
# semantic_researcher tests
# ===========================================================================


class TestSemanticResearcher:
    def test_annotate_adds_annotations(self):
        from dharma_swarm.semantic_researcher import SemanticResearcher

        g = _make_graph()
        researcher = SemanticResearcher()
        annotations = researcher.annotate_graph(g)

        # Concepts with formal structures like "monad", "coalgebra" should match
        assert len(annotations) >= 1
        # Add them to graph so coverage_report works
        for ann in annotations:
            g.add_annotation(ann)
        assert g.annotation_count >= 1

    def test_coverage_report(self):
        from dharma_swarm.semantic_researcher import SemanticResearcher

        g = _make_graph()
        researcher = SemanticResearcher()
        for ann in researcher.annotate_graph(g):
            g.add_annotation(ann)
        report = researcher.coverage_report(g)

        assert "total_concepts" in report
        assert "annotated_concepts" in report
        assert "coverage_pct" in report

    def test_gap_analysis(self):
        from dharma_swarm.semantic_researcher import SemanticResearcher

        g = _make_graph()
        researcher = SemanticResearcher()
        gaps = researcher.research_gaps(g)
        assert isinstance(gaps, list)


# ===========================================================================
# semantic_synthesizer tests
# ===========================================================================


class TestSemanticSynthesizer:
    def test_find_intersections(self):
        from dharma_swarm.semantic_synthesizer import find_intersections

        g = _make_graph()
        intersections = find_intersections(g, min_shared=1)

        # monad and coalgebra share "functor"
        assert len(intersections) >= 1
        names = [i.name for i in intersections]
        # At least one intersection should exist
        assert any("monad" in n.lower() or "coalgebra" in n.lower() for n in names)

    def test_synthesize_produces_clusters(self):
        from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

        g = _make_graph()
        synth = SemanticSynthesizer(min_intersection_score=0.0)
        clusters = synth.synthesize(g, max_clusters=5)

        assert len(clusters) >= 1
        for c in clusters:
            assert len(c.files) >= 3  # core + spec + test
            assert c.name
            assert c.description

    def test_cluster_has_test_file(self):
        from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

        g = _make_graph()
        synth = SemanticSynthesizer(min_intersection_score=0.0)
        clusters = synth.synthesize(g)

        for c in clusters:
            file_types = [f.file_type for f in c.files]
            assert "test" in file_types

    def test_gap_analysis(self):
        from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

        g = _make_graph()
        synth = SemanticSynthesizer()
        gaps = synth.gap_analysis(g)
        assert "total_intersections" in gaps
        assert "structures_covered" in gaps


# ===========================================================================
# semantic_hardener tests
# ===========================================================================


class TestSemanticHardener:
    def _make_cluster(self, graph: ConceptGraph) -> FileClusterSpec:
        """Create a cluster spec tied to the test graph."""
        nodes = graph.all_nodes()
        return FileClusterSpec(
            name="Test Cluster",
            description="A test cluster for hardening",
            core_concepts=[n.id for n in nodes[:2]],
            files=[
                ClusterFileSpec(
                    path="dharma_swarm/test_cluster.py",
                    file_type="python",
                    purpose="Core implementation",
                    cross_references=[nodes[0].name, nodes[1].name],
                ),
                ClusterFileSpec(
                    path="tests/test_test_cluster.py",
                    file_type="test",
                    purpose="Tests",
                ),
                ClusterFileSpec(
                    path="docs/clusters/test_cluster_spec.md",
                    file_type="markdown",
                    purpose="Spec",
                ),
            ],
        )

    def test_harden_produces_report(self):
        from dharma_swarm.semantic_hardener import SemanticHardener

        g = _make_graph()
        cluster = self._make_cluster(g)
        hardener = SemanticHardener(project_root=Path("/tmp"))
        report = hardener.harden(cluster, g)

        assert isinstance(report, HardeningReport)
        assert len(report.verdicts) == 6
        assert report.overall_score >= 0.0

    def test_all_six_angles_present(self):
        from dharma_swarm.semantic_hardener import SemanticHardener

        g = _make_graph()
        cluster = self._make_cluster(g)
        hardener = SemanticHardener(project_root=Path("/tmp"))
        report = hardener.harden(cluster, g)

        angles = {v.angle for v in report.verdicts}
        assert angles == {
            HardeningAngle.MATHEMATICAL,
            HardeningAngle.COMPUTATIONAL,
            HardeningAngle.ENGINEERING,
            HardeningAngle.CONTEXT_ENGINEERING,
            HardeningAngle.SWARM_DYNAMICS,
            HardeningAngle.BEHAVIORAL_HEALTH,
        }

    def test_harden_batch(self):
        from dharma_swarm.semantic_hardener import SemanticHardener

        g = _make_graph()
        c1 = self._make_cluster(g)
        c2 = FileClusterSpec(
            name="Empty Cluster",
            description="Empty",
            core_concepts=[],
            files=[],
        )
        hardener = SemanticHardener(project_root=Path("/tmp"))
        reports = hardener.harden_batch([c1, c2], g)
        assert len(reports) == 2

    def test_summary(self):
        from dharma_swarm.semantic_hardener import SemanticHardener

        g = _make_graph()
        cluster = self._make_cluster(g)
        hardener = SemanticHardener(project_root=Path("/tmp"))
        reports = [hardener.harden(cluster, g)]
        summary = hardener.summary(reports)

        assert "total" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "angle_stats" in summary

    def test_report_properties(self):
        report = HardeningReport(
            cluster_id="test",
            verdicts=[
                AngleVerdict(
                    angle=HardeningAngle.MATHEMATICAL,
                    result=GateResult.PASS,
                    score=0.8,
                ),
                AngleVerdict(
                    angle=HardeningAngle.COMPUTATIONAL,
                    result=GateResult.FAIL,
                    score=0.2,
                ),
                AngleVerdict(
                    angle=HardeningAngle.ENGINEERING,
                    result=GateResult.WARN,
                    score=0.5,
                ),
            ],
        )
        assert report.pass_count == 1
        assert report.fail_count == 1
        assert report.warn_count == 1


# ===========================================================================
# Integration: full pipeline
# ===========================================================================


class TestFullPipeline:
    def test_digest_research_synthesize_harden(self, tmp_path):
        """End-to-end: digest a small file, research, synthesize, harden."""
        from dharma_swarm.semantic_digester import SemanticDigester
        from dharma_swarm.semantic_hardener import SemanticHardener
        from dharma_swarm.semantic_researcher import SemanticResearcher
        from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

        # Create a small Python file
        py_file = tmp_path / "dharma_swarm" / "sample_monad.py"
        py_file.parent.mkdir(parents=True, exist_ok=True)
        py_file.write_text(
            '"""Monad implementation with coalgebra bridge."""\n'
            "\n"
            "from dharma_swarm.coalgebra import Coalgebra\n"
            "\n"
            "class Monad:\n"
            '    """A monad implementing functor and coalgebra patterns."""\n'
            "    def bind(self, f):\n"
            '        """Monadic bind (flatMap)."""\n'
            "        return f(self.value)\n"
            "\n"
            "    def unfold(self):\n"
            '        """Coalgebraic unfold operation."""\n'
            "        return self.value\n"
        )

        py_file2 = tmp_path / "dharma_swarm" / "sample_coalgebra.py"
        py_file2.write_text(
            '"""Coalgebra with sheaf connections."""\n'
            "\n"
            "class Coalgebra:\n"
            '    """A coalgebra implementing functor pattern."""\n'
            "    def unfold(self):\n"
            '        """Coalgebraic unfold."""\n'
            "        return self.state\n"
        )

        # Phase 1: Digest
        digester = SemanticDigester()
        graph = digester.digest_directory(tmp_path / "dharma_swarm")
        assert graph.node_count >= 2

        # Phase 2: Research
        researcher = SemanticResearcher()
        annotations = researcher.annotate_graph(graph)
        for ann in annotations:
            graph.add_annotation(ann)

        # Phase 3: Synthesize
        synth = SemanticSynthesizer(min_intersection_score=0.0)
        clusters = synth.synthesize(graph, max_clusters=5)
        # Clusters may be empty if concepts don't intersect enough

        # Phase 4: Harden (even if no clusters, test the path)
        hardener = SemanticHardener(project_root=tmp_path)
        if clusters:
            reports = hardener.harden_batch(clusters, graph)
            assert len(reports) == len(clusters)
            for r in reports:
                assert len(r.verdicts) == 6
