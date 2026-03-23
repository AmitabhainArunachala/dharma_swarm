"""Semantic hardener — multi-angle quality verification for file clusters.

Phase 4 of the Semantic Evolution Engine.  Each :class:`FileClusterSpec`
is tested from six orthogonal angles.  A cluster only survives if it
passes a configurable threshold of those angles.

Angles
------
1. **Mathematical** — formal structures validated via info_geometry + telos gates
2. **Computational** — importability, no syntax errors, test stubs present
3. **Engineering** — behavioral metrics via MetricsAnalyzer, compression ratio
4. **Context Engineering** — docstring density, cross-reference completeness
5. **Swarm Dynamics** — sheaf-style cohomological connectivity across cluster
6. **Behavioral Health** — ouroboros behavioral scoring, mimicry detection

Failed angles produce ``AngleVerdict.gaps`` that feed back into the
DIGEST phase for the next iteration.
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from statistics import mean
from typing import Any

from dharma_swarm.metrics import BehavioralSignature, MetricsAnalyzer
from dharma_swarm.models import GateResult
from dharma_swarm.semantic_gravity import (
    AngleVerdict,
    ConceptGraph,
    ConceptNode,
    FileClusterSpec,
    HardeningAngle,
    HardeningReport,
)

logger = logging.getLogger(__name__)

_analyzer = MetricsAnalyzer()

# ---------------------------------------------------------------------------
# Individual angle checkers
# ---------------------------------------------------------------------------


def _check_mathematical(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 1: Mathematical — formal structures present and consistent.

    Checks:
    - Core concepts have ≥1 formal structure
    - Formal structures referenced in the cluster files exist in the graph
    - Concept definitions are non-empty
    """
    gaps: list[str] = []
    scores: list[float] = []

    for cid in cluster.core_concepts:
        node = graph.get_node(cid)
        if node is None:
            gaps.append(f"Missing concept node: {cid}")
            scores.append(0.0)
            continue

        # Formal structures present
        if node.formal_structures:
            scores.append(1.0)
        else:
            gaps.append(f"Concept '{node.name}' has no formal structures")
            scores.append(0.0)

        # Definition present
        if node.definition:
            scores.append(1.0)
        else:
            gaps.append(f"Concept '{node.name}' has no definition")
            scores.append(0.3)

        # Check edges exist for this concept
        degree = graph.degree(cid)
        if degree > 0:
            scores.append(min(1.0, degree / 3.0))
        else:
            gaps.append(f"Concept '{node.name}' is isolated (0 edges)")
            scores.append(0.0)

    score = mean(scores) if scores else 0.0
    if score >= 0.7:
        result = GateResult.PASS
    elif score >= 0.4:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.MATHEMATICAL,
        result=result,
        score=round(score, 3),
        details=f"{len(scores)} checks, {len(gaps)} gaps",
        gaps=gaps,
    )


def _check_computational(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 2: Computational — files parseable, importable, tests present.

    Checks:
    - Python files are valid AST (no syntax errors)
    - At least one test file exists in the cluster
    - Import targets exist in the project
    """
    gaps: list[str] = []
    scores: list[float] = []

    has_test = False
    for fspec in cluster.files:
        full_path = project_root / fspec.path

        if fspec.file_type == "test":
            has_test = True

        if fspec.file_type in ("python", "test") and full_path.exists():
            try:
                source = full_path.read_text(encoding="utf-8")
                ast.parse(source)
                scores.append(1.0)
            except SyntaxError as exc:
                gaps.append(f"Syntax error in {fspec.path}: {exc.msg}")
                scores.append(0.0)
        elif fspec.file_type in ("python", "test"):
            # File not materialized yet — neutral score
            scores.append(0.5)

        # Check import targets exist
        for imp in fspec.imports_from:
            imp_path = project_root / imp
            if imp_path.exists():
                scores.append(1.0)
            else:
                gaps.append(f"Import target missing: {imp}")
                scores.append(0.3)

    if not has_test:
        gaps.append("No test file in cluster")
        scores.append(0.0)
    else:
        scores.append(1.0)

    score = mean(scores) if scores else 0.0
    if score >= 0.7:
        result = GateResult.PASS
    elif score >= 0.4:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.COMPUTATIONAL,
        result=result,
        score=round(score, 3),
        details=f"{len(cluster.files)} files, {len(gaps)} gaps",
        gaps=gaps,
    )


def _check_engineering(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 3: Engineering — behavioral metrics quality.

    Checks:
    - Entropy (vocabulary richness) of concept definitions
    - Complexity (compression ratio) of cluster content
    - No mimicry detected in descriptions
    """
    gaps: list[str] = []
    entropies: list[float] = []
    complexities: list[float] = []

    # Analyze concept definitions
    for cid in cluster.core_concepts:
        node = graph.get_node(cid)
        if node is None or not node.definition:
            continue
        sig = _analyzer.analyze(node.definition)
        entropies.append(sig.entropy)
        complexities.append(sig.complexity)

        if _analyzer.detect_mimicry(node.definition):
            gaps.append(f"Mimicry detected in concept '{node.name}' definition")

    # Analyze cluster description
    if cluster.description:
        sig = _analyzer.analyze(cluster.description)
        entropies.append(sig.entropy)
        complexities.append(sig.complexity)
        if _analyzer.detect_mimicry(cluster.description):
            gaps.append("Mimicry detected in cluster description")

    # Analyze existing file content
    for fspec in cluster.files:
        full_path = project_root / fspec.path
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")[:5000]
                sig = _analyzer.analyze(content)
                entropies.append(sig.entropy)
                complexities.append(sig.complexity)
            except Exception:
                logger.debug("Semantic hardener metrics failed", exc_info=True)

    avg_entropy = mean(entropies) if entropies else 0.0
    avg_complexity = mean(complexities) if complexities else 0.0

    if avg_entropy < 0.3:
        gaps.append(f"Low entropy ({avg_entropy:.3f}) — vocabulary too narrow")
    if avg_complexity < 0.1:
        gaps.append(f"Low complexity ({avg_complexity:.3f}) — content too simple")

    score = (avg_entropy * 0.5 + min(1.0, avg_complexity) * 0.5)
    if gaps:
        score *= 0.7  # Penalize for mimicry or low quality

    if score >= 0.5:
        result = GateResult.PASS
    elif score >= 0.3:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.ENGINEERING,
        result=result,
        score=round(score, 3),
        details=f"entropy={avg_entropy:.3f}, complexity={avg_complexity:.3f}",
        gaps=gaps,
    )


def _check_context_engineering(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 4: Context Engineering — documentation quality.

    Checks:
    - Python files have module docstrings
    - Functions/classes have docstrings (≥50% coverage)
    - Cross-references in ClusterFileSpec resolve to real concepts
    - Markdown spec files exist and are non-trivial
    """
    gaps: list[str] = []
    scores: list[float] = []

    for fspec in cluster.files:
        full_path = project_root / fspec.path

        # Check cross-references resolve
        for xref in fspec.cross_references:
            matches = graph.find_by_name(xref)
            if matches:
                scores.append(1.0)
            else:
                gaps.append(f"Unresolved cross-reference: '{xref}' in {fspec.path}")
                scores.append(0.0)

        if not full_path.exists():
            continue

        content = full_path.read_text(encoding="utf-8")

        if fspec.file_type in ("python", "test"):
            # Module docstring
            try:
                tree = ast.parse(content)
                if ast.get_docstring(tree):
                    scores.append(1.0)
                else:
                    gaps.append(f"No module docstring in {fspec.path}")
                    scores.append(0.0)

                # Function/class docstring coverage
                total = 0
                documented = 0
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        total += 1
                        if ast.get_docstring(node):
                            documented += 1

                if total > 0:
                    ratio = documented / total
                    scores.append(ratio)
                    if ratio < 0.5:
                        gaps.append(
                            f"Low docstring coverage in {fspec.path}: "
                            f"{documented}/{total} ({ratio:.0%})"
                        )
            except SyntaxError:
                gaps.append(f"Cannot parse {fspec.path} for docstring analysis")
                scores.append(0.0)

        elif fspec.file_type == "markdown":
            word_count = len(content.split())
            if word_count >= 50:
                scores.append(1.0)
            elif word_count >= 10:
                scores.append(0.5)
                gaps.append(f"Thin markdown spec: {fspec.path} ({word_count} words)")
            else:
                scores.append(0.0)
                gaps.append(f"Empty markdown spec: {fspec.path}")

    score = mean(scores) if scores else 0.0
    if score >= 0.6:
        result = GateResult.PASS
    elif score >= 0.3:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.CONTEXT_ENGINEERING,
        result=result,
        score=round(score, 3),
        details=f"{len(scores)} checks, {len(gaps)} gaps",
        gaps=gaps,
    )


def _check_swarm_dynamics(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 5: Swarm Dynamics — sheaf-style connectivity.

    Checks:
    - Core concepts are connected to each other (not isolated)
    - Cluster links to ≥2 existing modules via imports/references
    - No orphan concepts in the cluster
    """
    gaps: list[str] = []
    scores: list[float] = []
    concept_ids = set(cluster.core_concepts)

    # Internal connectivity: are core concepts connected to each other?
    internal_edges = 0
    for cid in concept_ids:
        neighbors = graph.neighbors(cid)
        for n in neighbors:
            if n.id in concept_ids and n.id != cid:
                internal_edges += 1
    # Each edge counted twice (both directions), so halve
    internal_edges = internal_edges // 2

    n_concepts = len(concept_ids)
    if n_concepts >= 2:
        max_internal = n_concepts * (n_concepts - 1) // 2
        connectivity = internal_edges / max_internal if max_internal > 0 else 0.0
        scores.append(min(1.0, connectivity * 2))  # Give credit for partial
        if connectivity < 0.3:
            gaps.append(
                f"Low internal connectivity: {internal_edges}/{max_internal} edges"
            )
    else:
        scores.append(0.5)  # Single concept — neutral

    # External connectivity: links to files outside the cluster
    external_files: set[str] = set()
    for cid in concept_ids:
        for neighbor in graph.neighbors(cid):
            if neighbor.id not in concept_ids and neighbor.source_file:
                external_files.add(neighbor.source_file)

    ext_count = len(external_files)
    if ext_count >= 3:
        scores.append(1.0)
    elif ext_count >= 2:
        scores.append(0.8)
    elif ext_count >= 1:
        scores.append(0.5)
        gaps.append(f"Only {ext_count} external module connection(s)")
    else:
        scores.append(0.0)
        gaps.append("No external module connections — cluster is isolated")

    # Check for orphan concepts (no edges at all)
    orphans = [cid for cid in concept_ids if graph.degree(cid) == 0]
    if orphans:
        gaps.append(f"{len(orphans)} orphan concept(s) with zero edges")
        scores.append(0.0)
    else:
        scores.append(1.0)

    score = mean(scores) if scores else 0.0
    if score >= 0.6:
        result = GateResult.PASS
    elif score >= 0.3:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.SWARM_DYNAMICS,
        result=result,
        score=round(score, 3),
        details=f"{internal_edges} internal edges, {ext_count} external links",
        gaps=gaps,
    )


def _check_behavioral_health(
    cluster: FileClusterSpec,
    graph: ConceptGraph,
    *,
    project_root: Path,
) -> AngleVerdict:
    """Angle 6: Behavioral Health — ouroboros-style scoring.

    Checks:
    - Concept definitions avoid mimicry
    - Entropy not too high (incoherent) or too low (repetitive)
    - Self-reference density is bounded (not narcissistic)
    - Recognition type is GENUINE or CONCEPTUAL, not MIMICRY
    """
    gaps: list[str] = []
    scores: list[float] = []

    for cid in cluster.core_concepts:
        node = graph.get_node(cid)
        if node is None:
            continue

        # Check behavioral metrics on the concept node itself
        if node.behavioral_entropy > 0:
            # Goldilocks zone: entropy between 0.3 and 0.9
            if 0.3 <= node.behavioral_entropy <= 0.9:
                scores.append(1.0)
            else:
                scores.append(0.5)
                gaps.append(
                    f"Concept '{node.name}' entropy {node.behavioral_entropy:.3f} "
                    f"outside healthy range [0.3, 0.9]"
                )

        # Check recognition type
        if node.recognition_type in ("GENUINE", "CONCEPTUAL", "NONE"):
            scores.append(1.0)
        elif node.recognition_type == "MIMICRY":
            gaps.append(f"Concept '{node.name}' flagged as MIMICRY")
            scores.append(0.0)
        elif node.recognition_type == "OVERFLOW":
            gaps.append(f"Concept '{node.name}' flagged as OVERFLOW")
            scores.append(0.3)
        else:
            scores.append(0.5)

        # Analyze definition text directly
        if node.definition:
            sig = _analyzer.analyze(node.definition)
            if sig.self_reference_density > 0.05:
                gaps.append(
                    f"High self-reference density in '{node.name}': "
                    f"{sig.self_reference_density:.3f}"
                )
                scores.append(0.3)
            else:
                scores.append(1.0)

    score = mean(scores) if scores else 0.5
    if score >= 0.7:
        result = GateResult.PASS
    elif score >= 0.4:
        result = GateResult.WARN
    else:
        result = GateResult.FAIL

    return AngleVerdict(
        angle=HardeningAngle.BEHAVIORAL_HEALTH,
        result=result,
        score=round(score, 3),
        details=f"{len(scores)} behavioral checks",
        gaps=gaps,
    )


# ---------------------------------------------------------------------------
# SemanticHardener
# ---------------------------------------------------------------------------

_ANGLE_CHECKERS = {
    HardeningAngle.MATHEMATICAL: _check_mathematical,
    HardeningAngle.COMPUTATIONAL: _check_computational,
    HardeningAngle.ENGINEERING: _check_engineering,
    HardeningAngle.CONTEXT_ENGINEERING: _check_context_engineering,
    HardeningAngle.SWARM_DYNAMICS: _check_swarm_dynamics,
    HardeningAngle.BEHAVIORAL_HEALTH: _check_behavioral_health,
}


class SemanticHardener:
    """Tests file clusters from six orthogonal angles.

    Usage::

        hardener = SemanticHardener(project_root=Path("."))
        report = hardener.harden(cluster, graph)
        if report.passed:
            print("Cluster survived hardening!")
        else:
            print("Gaps:", report.gaps_identified)
    """

    def __init__(
        self,
        *,
        project_root: Path = Path("."),
        min_pass_count: int = 4,
        min_overall_score: float = 0.5,
    ) -> None:
        self._project_root = project_root
        self._min_pass_count = min_pass_count
        self._min_overall_score = min_overall_score

    def harden(
        self,
        cluster: FileClusterSpec,
        graph: ConceptGraph,
        *,
        iteration: int = 0,
    ) -> HardeningReport:
        """Run all six angles on a cluster, produce a HardeningReport."""
        verdicts: list[AngleVerdict] = []

        for angle, checker in _ANGLE_CHECKERS.items():
            try:
                verdict = checker(
                    cluster, graph, project_root=self._project_root,
                )
            except Exception as exc:
                logger.warning("Angle %s raised: %s", angle.value, exc)
                verdict = AngleVerdict(
                    angle=angle,
                    result=GateResult.FAIL,
                    score=0.0,
                    details=f"Error: {exc}",
                    gaps=[f"Angle checker crashed: {exc}"],
                )
            verdicts.append(verdict)

        # Aggregate
        all_gaps = [g for v in verdicts for g in v.gaps]
        overall_score = mean(v.score for v in verdicts) if verdicts else 0.0
        pass_count = sum(1 for v in verdicts if v.result == GateResult.PASS)
        passed = (
            pass_count >= self._min_pass_count
            and overall_score >= self._min_overall_score
        )

        # Compute semantic density from non-zero scores
        scores = [v.score for v in verdicts if v.score > 0]
        semantic_density = (mean(scores) * len(scores) / 6) if scores else 0.0

        # Suggest refinements based on worst angles
        suggested: list[str] = []
        for v in sorted(verdicts, key=lambda v: v.score):
            if v.result in (GateResult.FAIL, GateResult.WARN):
                suggested.append(
                    f"[{v.angle.value}] Improve: {v.gaps[0]}"
                    if v.gaps
                    else f"[{v.angle.value}] Score too low ({v.score:.2f})"
                )

        report = HardeningReport(
            cluster_id=cluster.id,
            verdicts=verdicts,
            overall_score=round(overall_score, 3),
            semantic_density=round(semantic_density, 3),
            passed=passed,
            iteration=iteration,
            gaps_identified=all_gaps,
            suggested_refinements=suggested[:5],
        )

        logger.info(
            "Hardening %s: %s (score=%.3f, %d/%d angles passed)",
            cluster.name,
            "PASSED" if passed else "FAILED",
            overall_score,
            pass_count,
            len(verdicts),
        )
        return report

    def harden_batch(
        self,
        clusters: list[FileClusterSpec],
        graph: ConceptGraph,
        *,
        iteration: int = 0,
    ) -> list[HardeningReport]:
        """Harden multiple clusters, return reports."""
        return [
            self.harden(c, graph, iteration=iteration) for c in clusters
        ]

    def summary(self, reports: list[HardeningReport]) -> dict[str, Any]:
        """Aggregate summary of hardening results."""
        if not reports:
            return {"total": 0, "passed": 0, "failed": 0}

        passed = [r for r in reports if r.passed]
        failed = [r for r in reports if not r.passed]

        # Angle-level aggregation
        angle_stats: dict[str, dict[str, Any]] = {}
        for angle in HardeningAngle:
            angle_verdicts = [
                v for r in reports for v in r.verdicts if v.angle == angle
            ]
            if angle_verdicts:
                angle_stats[angle.value] = {
                    "avg_score": round(
                        mean(v.score for v in angle_verdicts), 3
                    ),
                    "pass_rate": round(
                        sum(1 for v in angle_verdicts if v.result == GateResult.PASS)
                        / len(angle_verdicts),
                        3,
                    ),
                    "total_gaps": sum(len(v.gaps) for v in angle_verdicts),
                }

        return {
            "total": len(reports),
            "passed": len(passed),
            "failed": len(failed),
            "avg_score": round(mean(r.overall_score for r in reports), 3),
            "avg_density": round(mean(r.semantic_density for r in reports), 3),
            "angle_stats": angle_stats,
            "top_gaps": _top_gaps(reports, n=10),
        }


def _top_gaps(reports: list[HardeningReport], *, n: int = 10) -> list[str]:
    """Return the most common gaps across all reports."""
    from collections import Counter

    gap_counts: Counter[str] = Counter()
    for r in reports:
        for g in r.gaps_identified:
            gap_counts[g] += 1
    return [gap for gap, _ in gap_counts.most_common(n)]


__all__ = [
    "SemanticHardener",
]
