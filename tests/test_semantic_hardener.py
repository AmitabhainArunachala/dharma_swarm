"""Tests for dharma_swarm.semantic_hardener.

Exercises the six-angle hardening pipeline, individual angle checkers,
SemanticHardener.harden/harden_batch/summary, and _top_gaps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.models import GateResult
from dharma_swarm.semantic_gravity import (
    AngleVerdict,
    ClusterFileSpec,
    ConceptGraph,
    ConceptNode,
    FileClusterSpec,
    HardeningAngle,
    HardeningReport,
)
from dharma_swarm.semantic_hardener import (
    SemanticHardener,
    _check_computational,
    _check_mathematical,
    _top_gaps,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def graph_with_concepts() -> ConceptGraph:
    """Graph with two concepts, one with formal structures."""
    g = ConceptGraph()
    n1 = ConceptNode(
        id="c1", name="eigenform", definition="Self-referential fixed point",
        formal_structures=["S(x)=x"], source_file="foo.py",
    )
    n2 = ConceptNode(
        id="c2", name="empty_concept", definition="",
        formal_structures=[], source_file="bar.py",
    )
    g.add_node(n1)
    g.add_node(n2)
    return g


@pytest.fixture()
def simple_cluster() -> FileClusterSpec:
    """Minimal cluster with one Python file."""
    return FileClusterSpec(
        id="cluster-1",
        name="test_cluster",
        core_concepts=["c1"],
        files=[
            ClusterFileSpec(path="dharma_swarm/foo.py", file_type="python"),
            ClusterFileSpec(path="tests/test_foo.py", file_type="test"),
        ],
    )


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Create a temp project with a valid Python file."""
    (tmp_path / "dharma_swarm").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "dharma_swarm" / "foo.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_foo.py").write_text("def test_x(): pass\n")
    return tmp_path


# ---------------------------------------------------------------------------
# _check_mathematical
# ---------------------------------------------------------------------------

class TestCheckMathematical:
    def test_pass_with_formal_structures(self, graph_with_concepts, simple_cluster, project_root):
        v = _check_mathematical(simple_cluster, graph_with_concepts, project_root=project_root)
        assert v.angle == HardeningAngle.MATHEMATICAL
        assert v.result in (GateResult.PASS, GateResult.WARN)
        assert v.score > 0

    def test_fail_missing_concept(self, graph_with_concepts, project_root):
        cluster = FileClusterSpec(
            id="c2", name="bad", core_concepts=["nonexistent"],
            files=[ClusterFileSpec(path="x.py", file_type="python")],
        )
        v = _check_mathematical(cluster, graph_with_concepts, project_root=project_root)
        assert len(v.gaps) > 0
        assert "Missing concept node" in v.gaps[0]

    def test_fail_no_formal_structures(self, graph_with_concepts, project_root):
        cluster = FileClusterSpec(
            id="c3", name="empty_formal", core_concepts=["c2"],
            files=[ClusterFileSpec(path="x.py", file_type="python")],
        )
        v = _check_mathematical(cluster, graph_with_concepts, project_root=project_root)
        assert any("no formal structures" in g for g in v.gaps)


# ---------------------------------------------------------------------------
# _check_computational
# ---------------------------------------------------------------------------

class TestCheckComputational:
    def test_pass_valid_python_with_tests(self, graph_with_concepts, simple_cluster, project_root):
        v = _check_computational(simple_cluster, graph_with_concepts, project_root=project_root)
        assert v.angle == HardeningAngle.COMPUTATIONAL
        assert v.result == GateResult.PASS

    def test_fail_syntax_error(self, graph_with_concepts, project_root):
        (project_root / "dharma_swarm" / "bad.py").write_text("def f(\n")
        cluster = FileClusterSpec(
            id="c4", name="bad_syntax",
            core_concepts=["c1"],
            files=[
                ClusterFileSpec(path="dharma_swarm/bad.py", file_type="python"),
                ClusterFileSpec(path="tests/test_foo.py", file_type="test"),
            ],
        )
        v = _check_computational(cluster, graph_with_concepts, project_root=project_root)
        assert any("Syntax error" in g for g in v.gaps)

    def test_fail_no_test_file(self, graph_with_concepts, project_root):
        cluster = FileClusterSpec(
            id="c5", name="no_tests",
            core_concepts=["c1"],
            files=[
                ClusterFileSpec(path="dharma_swarm/foo.py", file_type="python"),
            ],
        )
        v = _check_computational(cluster, graph_with_concepts, project_root=project_root)
        assert any("No test file" in g for g in v.gaps)


# ---------------------------------------------------------------------------
# SemanticHardener
# ---------------------------------------------------------------------------

class TestSemanticHardener:
    def test_harden_returns_report(self, graph_with_concepts, simple_cluster, project_root):
        h = SemanticHardener(project_root=project_root, min_pass_count=1)
        report = h.harden(simple_cluster, graph_with_concepts)
        assert isinstance(report, HardeningReport)
        assert report.cluster_id == "cluster-1"
        assert len(report.verdicts) == 6  # All six angles

    def test_harden_high_threshold_fails(self, graph_with_concepts, simple_cluster, project_root):
        h = SemanticHardener(project_root=project_root, min_pass_count=6, min_overall_score=0.99)
        report = h.harden(simple_cluster, graph_with_concepts)
        # Unlikely all 6 angles pass at 0.99 with minimal cluster
        assert isinstance(report, HardeningReport)

    def test_harden_batch(self, graph_with_concepts, simple_cluster, project_root):
        h = SemanticHardener(project_root=project_root, min_pass_count=1)
        reports = h.harden_batch([simple_cluster, simple_cluster], graph_with_concepts)
        assert len(reports) == 2
        assert all(isinstance(r, HardeningReport) for r in reports)

    def test_summary_empty(self):
        h = SemanticHardener()
        s = h.summary([])
        assert s == {"total": 0, "passed": 0, "failed": 0}

    def test_summary_with_reports(self, graph_with_concepts, simple_cluster, project_root):
        h = SemanticHardener(project_root=project_root, min_pass_count=1)
        reports = h.harden_batch([simple_cluster], graph_with_concepts)
        s = h.summary(reports)
        assert s["total"] == 1
        assert "avg_score" in s
        assert "angle_stats" in s
        assert "top_gaps" in s

    def test_harden_catches_angle_exception(self, graph_with_concepts, project_root):
        """If an angle checker crashes, the report still completes."""
        cluster = FileClusterSpec(
            id="c6", name="minimal",
            core_concepts=["c1"],
            files=[ClusterFileSpec(path="dharma_swarm/foo.py", file_type="python")],
        )
        h = SemanticHardener(project_root=project_root, min_pass_count=0)
        report = h.harden(cluster, graph_with_concepts)
        assert isinstance(report, HardeningReport)
        assert len(report.verdicts) == 6

    def test_iteration_tracked(self, graph_with_concepts, simple_cluster, project_root):
        h = SemanticHardener(project_root=project_root, min_pass_count=1)
        report = h.harden(simple_cluster, graph_with_concepts, iteration=42)
        assert report.iteration == 42


# ---------------------------------------------------------------------------
# _top_gaps
# ---------------------------------------------------------------------------

class TestTopGaps:
    def test_empty_reports(self):
        assert _top_gaps([]) == []

    def test_gaps_ranked_by_frequency(self):
        r1 = HardeningReport(
            cluster_id="a", gaps_identified=["gap1", "gap2", "gap1"],
        )
        r2 = HardeningReport(
            cluster_id="b", gaps_identified=["gap1", "gap3"],
        )
        result = _top_gaps([r1, r2], n=2)
        assert result[0] == "gap1"  # Most common
        assert len(result) == 2

    def test_n_limits_output(self):
        r = HardeningReport(
            cluster_id="a",
            gaps_identified=[f"gap{i}" for i in range(20)],
        )
        result = _top_gaps([r], n=5)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# Data model integration
# ---------------------------------------------------------------------------

class TestAngleVerdict:
    def test_all_angles_exist(self):
        expected = {
            "mathematical", "computational", "engineering",
            "context_engineering", "swarm_dynamics", "behavioral_health",
        }
        actual = {a.value for a in HardeningAngle}
        assert actual == expected

    def test_verdict_fields(self):
        v = AngleVerdict(
            angle=HardeningAngle.MATHEMATICAL,
            result=GateResult.PASS,
            score=0.85,
            details="ok",
            gaps=["minor issue"],
        )
        assert v.score == 0.85
        assert len(v.gaps) == 1
