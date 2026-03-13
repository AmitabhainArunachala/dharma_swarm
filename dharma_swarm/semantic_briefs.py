"""Compile semantic clusters into campaign-grade briefs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.mission_contract import (
    CampaignArtifact,
    ExecutionBrief,
    SemanticBrief,
)
from dharma_swarm.semantic_gravity import ConceptGraph, FileClusterSpec, HardeningReport


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _readiness(cluster: FileClusterSpec, report: HardeningReport) -> float:
    score = (cluster.hardening_score or 0.0) * 0.35 + report.overall_score * 0.65
    if report.passed:
        score += 0.05
    return round(max(0.0, min(score, 1.0)), 3)


def _concept_names(graph: ConceptGraph, cluster: FileClusterSpec) -> list[str]:
    names: list[str] = []
    for concept_id in cluster.core_concepts:
        node = graph.get_node(concept_id)
        if node is not None and node.name:
            names.append(node.name)
    return _dedupe(names)


def _cluster_evidence(graph: ConceptGraph, cluster: FileClusterSpec) -> list[str]:
    evidence: list[str] = []
    for concept_id in cluster.core_concepts:
        node = graph.get_node(concept_id)
        if node is not None and node.source_file:
            evidence.append(node.source_file)
    for file_spec in cluster.files:
        if file_spec.path:
            evidence.append(file_spec.path)
        evidence.extend(file_spec.imports_from)
    return _dedupe(evidence)


def _cluster_citations(graph: ConceptGraph, cluster: FileClusterSpec) -> list[str]:
    citations: list[str] = []
    for ann_id in cluster.research_annotations:
        ann = graph.get_annotation(ann_id)
        if ann is None:
            continue
        if ann.citation:
            citations.append(ann.citation)
        elif ann.external_source:
            citations.append(ann.external_source)
    return _dedupe(citations)


def compile_semantic_briefs(
    graph: ConceptGraph,
    clusters: list[FileClusterSpec],
    reports: list[HardeningReport],
    *,
    max_briefs: int = 3,
) -> list[SemanticBrief]:
    """Promote hardened clusters into decision-grade semantic briefs."""
    report_by_cluster = {report.cluster_id: report for report in reports}
    ranked = sorted(
        (
            cluster for cluster in clusters
            if cluster.id in report_by_cluster
        ),
        key=lambda cluster: (
            report_by_cluster[cluster.id].passed,
            report_by_cluster[cluster.id].overall_score,
            cluster.gravitational_mass,
        ),
        reverse=True,
    )

    briefs: list[SemanticBrief] = []
    for cluster in ranked[:max_briefs]:
        report = report_by_cluster[cluster.id]
        concept_names = _concept_names(graph, cluster)
        citations = _cluster_citations(graph, cluster)
        next_actions = report.suggested_refinements[:3] or [
            f"Implement the cluster scaffold for {cluster.name}.",
            f"Write the grounding spec for {cluster.name}.",
            f"Verify the cluster with targeted tests.",
        ]
        thesis_parts = [cluster.description.strip()]
        if concept_names:
            thesis_parts.append(f"Core concepts: {', '.join(concept_names)}.")
        if citations:
            thesis_parts.append(f"Research spine: {citations[0]}.")
        briefs.append(
            SemanticBrief(
                brief_id=f"semantic-{cluster.id}",
                title=cluster.name,
                cluster_name=cluster.name,
                thesis=" ".join(part for part in thesis_parts if part).strip(),
                readiness_score=_readiness(cluster, report),
                concept_names=concept_names,
                evidence_paths=_cluster_evidence(graph, cluster),
                citations=citations,
                gaps=report.gaps_identified[:6],
                next_actions=next_actions,
                metadata={
                    "cluster_id": cluster.id,
                    "intersection_type": cluster.intersection_type,
                    "passed": report.passed,
                    "overall_score": report.overall_score,
                },
            )
        )
    return briefs


def compile_execution_briefs(
    semantic_briefs: list[SemanticBrief],
    clusters: list[FileClusterSpec],
) -> list[ExecutionBrief]:
    """Convert semantic briefs into bounded execution briefs."""
    cluster_by_id = {cluster.id: cluster for cluster in clusters}
    out: list[ExecutionBrief] = []
    for brief in semantic_briefs:
        cluster_id = str(brief.metadata.get("cluster_id", "")).strip()
        cluster = cluster_by_id.get(cluster_id)
        task_titles: list[str] = []
        acceptance: list[str] = [
            "Produce at least one artifact tied to the cluster thesis.",
            "Verify touched code or docs with concrete evidence.",
            "Archive the resulting artifact back into campaign memory.",
        ]
        if cluster is not None:
            for file_spec in cluster.files:
                if file_spec.file_type == "python":
                    task_titles.append(f"Implement or revise {file_spec.path}.")
                elif file_spec.file_type == "test":
                    task_titles.append(f"Add or update verification in {file_spec.path}.")
                else:
                    task_titles.append(f"Write or refresh {file_spec.path}.")
            if brief.gaps:
                acceptance.append(f"Address the top hardening gap: {brief.gaps[0]}")
        else:
            task_titles.extend(brief.next_actions[:3])

        out.append(
            ExecutionBrief(
                brief_id=f"execution-{brief.brief_id}",
                title=f"{brief.title} build brief",
                goal=brief.thesis,
                readiness_score=brief.readiness_score,
                task_titles=_dedupe(task_titles),
                acceptance=_dedupe(acceptance),
                evidence_paths=list(brief.evidence_paths),
                depends_on_briefs=[brief.brief_id],
                metadata={"semantic_brief_id": brief.brief_id, "cluster_id": cluster_id},
            )
        )
    return out


class SemanticBriefPacket(BaseModel):
    generated_at: str
    graph_path: str = ""
    project_root: str = ""
    semantic_briefs: list[SemanticBrief] = Field(default_factory=list)
    execution_briefs: list[ExecutionBrief] = Field(default_factory=list)
    artifacts: list[CampaignArtifact] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


def build_brief_packet(
    *,
    graph: ConceptGraph,
    clusters: list[FileClusterSpec],
    reports: list[HardeningReport],
    graph_path: str = "",
    project_root: str = "",
    max_briefs: int = 3,
) -> SemanticBriefPacket:
    semantic_briefs = compile_semantic_briefs(
        graph,
        clusters,
        reports,
        max_briefs=max_briefs,
    )
    execution_briefs = compile_execution_briefs(semantic_briefs, clusters)
    artifacts = [
        CampaignArtifact(
            artifact_kind="semantic_brief_packet",
            title="semantic brief packet",
            path=str(graph_path).strip(),
            summary=f"{len(semantic_briefs)} semantic briefs, {len(execution_briefs)} execution briefs",
            source="semantic_briefs",
            citations=_dedupe(
                [citation for brief in semantic_briefs for citation in brief.citations]
            ),
        )
    ]
    avg_readiness = (
        round(
            sum(brief.readiness_score for brief in semantic_briefs) / len(semantic_briefs),
            3,
        )
        if semantic_briefs
        else 0.0
    )
    return SemanticBriefPacket(
        generated_at=datetime.now(timezone.utc).isoformat(),
        graph_path=graph_path,
        project_root=project_root,
        semantic_briefs=semantic_briefs,
        execution_briefs=execution_briefs,
        artifacts=artifacts,
        metrics={
            "clusters_considered": len(clusters),
            "reports_considered": len(reports),
            "semantic_briefs": len(semantic_briefs),
            "execution_briefs": len(execution_briefs),
            "avg_readiness": avg_readiness,
        },
    )


def render_brief_packet_markdown(packet: SemanticBriefPacket) -> str:
    """Render the packet in a compact operator-facing markdown form."""
    lines = [
        "# Semantic Brief Packet",
        f"- Graph: `{packet.graph_path or '(unspecified)'}`",
        f"- Project root: `{packet.project_root or '(unspecified)'}`",
        f"- Semantic briefs: `{len(packet.semantic_briefs)}`",
        f"- Execution briefs: `{len(packet.execution_briefs)}`",
        f"- Avg readiness: `{packet.metrics.get('avg_readiness', 0.0)}`",
        "",
        "## Semantic Briefs",
    ]
    if not packet.semantic_briefs:
        lines.append("- None")
    for brief in packet.semantic_briefs:
        lines.append(f"### {brief.title}")
        lines.append(f"- Readiness: `{brief.readiness_score}`")
        lines.append(f"- Thesis: {brief.thesis}")
        if brief.concept_names:
            lines.append(f"- Concepts: {', '.join(brief.concept_names)}")
        if brief.citations:
            lines.append(f"- Citations: {', '.join(brief.citations[:4])}")
        if brief.gaps:
            lines.append(f"- Gaps: {', '.join(brief.gaps[:4])}")
        if brief.next_actions:
            lines.append(f"- Next actions: {', '.join(brief.next_actions[:4])}")
        if brief.evidence_paths:
            lines.append(f"- Evidence: {', '.join(brief.evidence_paths[:6])}")
        lines.append("")

    lines.append("## Execution Briefs")
    if not packet.execution_briefs:
        lines.append("- None")
    for brief in packet.execution_briefs:
        lines.append(f"### {brief.title}")
        lines.append(f"- Readiness: `{brief.readiness_score}`")
        lines.append(f"- Goal: {brief.goal}")
        if brief.task_titles:
            lines.append(f"- Tasks: {', '.join(brief.task_titles[:6])}")
        if brief.acceptance:
            lines.append(f"- Acceptance: {', '.join(brief.acceptance[:4])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_brief_packet(
    packet: SemanticBriefPacket,
    *,
    json_path: str | Path,
    markdown_path: str | Path | None = None,
) -> tuple[Path, Path | None]:
    """Persist the brief packet to JSON and optional markdown."""
    payload = packet.model_dump(mode="json")
    payload["generated_at"] = payload.get("generated_at") or ""
    json_target = Path(json_path).expanduser()
    json_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    markdown_target: Path | None = None
    if markdown_path is not None:
        markdown_target = Path(markdown_path).expanduser()
        markdown_target.parent.mkdir(parents=True, exist_ok=True)
        markdown_target.write_text(
            render_brief_packet_markdown(packet),
            encoding="utf-8",
        )
    return json_target, markdown_target


__all__ = [
    "SemanticBriefPacket",
    "build_brief_packet",
    "compile_execution_briefs",
    "compile_semantic_briefs",
    "render_brief_packet_markdown",
    "write_brief_packet",
]
