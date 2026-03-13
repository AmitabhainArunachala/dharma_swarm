#!/usr/bin/env python3
"""Bootstrap a staged PSMV hyperfile sprint inside the writable workspace.

This script does not write back into the PSMV vault. Instead it:

1. Runs semantic digestion/research/synthesis on the repo and the selected vault root
2. Builds a ranked set of hyperfile targets from the vault graph
3. Emits staged markdown packets with dense internal/external link spines
4. Writes manifests the thinkodynamic director can keep expanding
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.semantic_digester import SemanticDigester
from dharma_swarm.semantic_gravity import ConceptGraph, ConceptNode
from dharma_swarm.semantic_researcher import SemanticResearcher
from dharma_swarm.semantic_synthesizer import FileClusterSpec, SemanticSynthesizer


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "hyperfile"


def _load_source_pack(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    return [entry for entry in data if isinstance(entry, dict)]


@dataclass
class HyperfileTarget:
    node: ConceptNode
    slug: str
    score: float


def _degree(graph: ConceptGraph, node: ConceptNode) -> int:
    try:
        return graph.degree(node.id)
    except Exception:
        return len(graph.neighbors(node.id))


def _file_level_nodes(graph: ConceptGraph) -> list[ConceptNode]:
    nodes: list[ConceptNode] = []
    seen_files: set[str] = set()
    for node in sorted(
        graph.all_nodes(),
        key=lambda item: (
            item.salience,
            item.semantic_density,
            item.source_file,
            item.name,
        ),
        reverse=True,
    ):
        if node.recognition_type not in {"note", "text_note"}:
            continue
        if not node.source_file or node.source_file in seen_files:
            continue
        seen_files.add(node.source_file)
        nodes.append(node)
    return nodes


def _rank_targets(
    graph: ConceptGraph,
    *,
    limit: int,
) -> list[HyperfileTarget]:
    ranked: list[HyperfileTarget] = []
    for node in _file_level_nodes(graph):
        degree = _degree(graph, node)
        score = (
            node.salience * 100.0
            + node.semantic_density * 4.0
            + degree * 2.5
            + len(node.formal_structures) * 3.0
        )
        ranked.append(HyperfileTarget(
            node=node,
            slug=_safe_slug(node.name),
            score=round(score, 3),
        ))
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def _source_tokens(node: ConceptNode) -> set[str]:
    metadata = node.metadata if isinstance(node.metadata, dict) else {}
    tags = metadata.get("tags", [])
    aliases = metadata.get("aliases", [])
    raw = " ".join(
        [
            node.name,
            node.definition,
            node.category,
            " ".join(node.formal_structures),
            " ".join(str(tag) for tag in tags),
            " ".join(str(alias) for alias in aliases),
        ],
    ).lower()
    return {token for token in re.findall(r"[a-z0-9_]{3,}", raw)}


def _pick_internal_targets(
    graph: ConceptGraph,
    items: list[HyperfileTarget],
    current: HyperfileTarget,
    *,
    link_count: int,
) -> list[HyperfileTarget]:
    neighbors = {node.id for node in graph.neighbors(current.node.id)}
    current_structures = set(current.node.formal_structures)
    current_tokens = _source_tokens(current.node)
    ranked: list[tuple[float, HyperfileTarget]] = []

    for candidate in items:
        if candidate.node.id == current.node.id:
            continue
        score = candidate.score * 0.01
        if candidate.node.id in neighbors:
            score += 8.0
        if candidate.node.category and candidate.node.category == current.node.category:
            score += 3.0
        score += len(current_structures & set(candidate.node.formal_structures)) * 2.5
        overlap = len(current_tokens & _source_tokens(candidate.node))
        score += min(overlap, 6) * 0.4
        ranked.append((score, candidate))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in ranked[:link_count]]


def _pick_external_sources(
    node: ConceptNode,
    sources: list[dict[str, Any]],
    *,
    link_count: int,
) -> list[dict[str, Any]]:
    tokens = _source_tokens(node)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for source in sources:
        themes = {str(theme).lower() for theme in source.get("themes", [])}
        text = " ".join(
            [
                str(source.get("title", "")),
                str(source.get("publisher", "")),
                " ".join(themes),
            ],
        ).lower()
        score = len(tokens & set(re.findall(r"[a-z0-9_]{3,}", text)))
        if node.category and node.category.lower() in text:
            score += 2
        if any(struct in text for struct in node.formal_structures):
            score += 3
        if source.get("kind") == "official_docs":
            score += 1
        ranked.append((float(score), source))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for _, source in ranked:
        source_id = str(source.get("id", source.get("url", "")))
        if source_id in seen_ids:
            continue
        selected.append(source)
        seen_ids.add(source_id)
        if len(selected) >= link_count:
            return selected

    for source in sources:
        source_id = str(source.get("id", source.get("url", "")))
        if source_id in seen_ids:
            continue
        selected.append(source)
        seen_ids.add(source_id)
        if len(selected) >= link_count:
            break
    return selected


def _summarize_related_names(graph: ConceptGraph, node: ConceptNode, *, limit: int = 6) -> list[str]:
    names: list[str] = []
    for other in graph.neighbors(node.id):
        if other.source_file == node.source_file:
            continue
        if other.name not in names:
            names.append(other.name)
        if len(names) >= limit:
            break
    return names


def _build_condensation(graph: ConceptGraph, node: ConceptNode) -> list[str]:
    formal = ", ".join(node.formal_structures[:6]) or "no explicit formal structure markers"
    claims = "; ".join(node.claims[:3]) or "no explicit invariant claims extracted"
    related = ", ".join(_summarize_related_names(graph, node)) or "no strong adjacent note nodes yet"
    return [
        (
            f"This staged packet condenses `{node.source_file}` into a build-grade brief. "
            f"The source is currently classified as `{node.category or 'uncategorized'}` "
            f"with formal signals around {formal}. Salience is {node.salience:.2f} and "
            f"semantic density is {node.semantic_density:.2f}."
        ),
        (
            f"Primary extracted claims: {claims}. Nearby concepts in the current semantic "
            f"graph include {related}. The intent of this packet is not to freeze the note "
            f"as prose, but to route it toward a research, product, protocol, or institutional "
            f"move that can be executed by an agentic build system."
        ),
    ]


def _write_hyperfile(
    path: Path,
    *,
    target: HyperfileTarget,
    graph: ConceptGraph,
    internal_targets: list[HyperfileTarget],
    external_sources: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    condensation = _build_condensation(graph, target.node)
    lines = [
        "---",
        f"title: {target.node.name}",
        "status: staged_scaffold",
        f"generated_at: {_utc_now()}",
        f"source_file: {target.node.source_file}",
        f"category: {target.node.category or 'uncategorized'}",
        f"salience: {target.node.salience:.3f}",
        f"semantic_density: {target.node.semantic_density:.3f}",
        f"internal_link_count: {len(internal_targets)}",
        f"external_link_count: {len(external_sources)}",
        "---",
        "",
        f"# {target.node.name}",
        "",
        "## Source Condensation",
        "",
    ]
    lines.extend(f"- {paragraph}" for paragraph in condensation)
    lines.extend([
        "",
        "## Agentic Upgrade",
        "",
        (
            "- Translate this note into a mission organism: one research claim, one buildable "
            "product or protocol surface, one measurable verification loop, and one public-facing "
            "narrative that could survive contact with industry and academic scrutiny."
        ),
        (
            "- Hold two scales at once: the corpus-level metaphysics that gave rise to the note, "
            "and the concrete 2026 workflow interfaces required for coding agents, retrieval systems, "
            "memory graphs, evaluation loops, and production deployment."
        ),
        (
            "- Write as if the destination were a publishable essay, a product spec, and a field manual "
            "for multi-agent implementation all at the same time."
        ),
        "",
        "## Internal Link Mesh",
        "",
    ])
    for item in internal_targets:
        lines.append(
            f"- [{item.node.name}](./{item.slug}.md) :: source `{item.node.source_file}` :: "
            f"category `{item.node.category or 'uncategorized'}`"
        )
    lines.extend(["", "## External Research Spine", ""])
    for source in external_sources:
        lines.append(
            f"- [{source['title']}]({source['url']}) :: {source.get('publisher', 'unknown')} "
            f"({source.get('year', 'n/a')}) :: {', '.join(source.get('themes', [])[:5])}"
        )
    lines.extend([
        "",
        "## Build Translation",
        "",
        "- Product lane: derive one operator-facing workflow or tool surface that this note implies.",
        "- Research lane: define the strongest falsifiable claim or comparison this note makes possible.",
        "- Infrastructure lane: identify the memory, retrieval, orchestration, or eval capability required to operationalize it.",
        "",
        "## Verification Questions",
        "",
        "- Which parts of the original note are actually evidentiary, and which are merely suggestive?",
        "- What would make this packet credible to a hard-nosed researcher, operator, or editor outside the original corpus?",
        "- What should be built next if this packet is treated as a live mission rather than archival writing?",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _top_formal_structures(graph: ConceptGraph, *, limit: int = 10) -> list[str]:
    counter: Counter[str] = Counter()
    for node in graph.all_nodes():
        counter.update(node.formal_structures)
    return [name for name, _ in counter.most_common(limit)]


def _write_graph_summary(
    path: Path,
    *,
    label: str,
    root: Path,
    graph: ConceptGraph,
    clusters: list[FileClusterSpec],
) -> None:
    lines = [
        f"# {label} Semantic Summary",
        "",
        f"- Root: `{root}`",
        f"- Generated at: `{_utc_now()}`",
        f"- Nodes: `{graph.node_count}`",
        f"- Edges: `{graph.edge_count}`",
        f"- Annotations: `{graph.annotation_count}`",
        f"- Top formal structures: {', '.join(_top_formal_structures(graph)) or 'none'}",
        "",
        "## Top Clusters",
        "",
    ]
    if clusters:
        for cluster in clusters[:8]:
            lines.append(
                f"- {cluster.name} :: {cluster.intersection_type or 'unspecified'} :: "
                f"{len(cluster.files)} files"
            )
    else:
        lines.append("- No clusters synthesized.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_cross_corpus_summary(
    path: Path,
    *,
    repo_graph: ConceptGraph,
    vault_graph: ConceptGraph,
    targets: list[HyperfileTarget],
) -> None:
    repo_structures = set(_top_formal_structures(repo_graph, limit=20))
    vault_structures = set(_top_formal_structures(vault_graph, limit=20))
    shared = sorted(repo_structures & vault_structures)
    lines = [
        "# Cross-Corpus Bridge Summary",
        "",
        f"- Generated at: `{_utc_now()}`",
        f"- Repo nodes: `{repo_graph.node_count}`",
        f"- Vault nodes: `{vault_graph.node_count}`",
        f"- Shared formal structures: {', '.join(shared) or 'none'}",
        "",
        "## Top Staged Targets",
        "",
    ]
    for target in targets[:12]:
        lines.append(
            f"- {target.node.name} :: {target.node.category or 'uncategorized'} :: "
            f"{target.node.source_file}"
        )
    lines.extend([
        "",
        "## Why This Matters",
        "",
        (
            "- The repo graph describes the current implementation organism. The vault graph "
            "describes the latent intellectual attractors. The staged hyperfiles are the translation "
            "layer between them."
        ),
        (
            "- Shared formal structures are the fastest route to buildable programs: they identify "
            "where the codebase can already metabolize the vault's strongest ideas."
        ),
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _run_semantic_bundle(
    root: Path,
    *,
    max_files: int,
    include_tests: bool,
    graph_path: Path,
    summary_path: Path,
    label: str,
) -> tuple[ConceptGraph, list[FileClusterSpec]]:
    digester = SemanticDigester()
    graph = digester.digest_directory(
        root,
        include_tests=include_tests,
        max_files=max_files,
    )
    researcher = SemanticResearcher()
    for annotation in researcher.annotate_graph(graph):
        graph.add_annotation(annotation)
    synth = SemanticSynthesizer(max_clusters=12)
    clusters = synth.synthesize(graph)
    asyncio.run(graph.save(graph_path))
    _write_graph_summary(
        summary_path,
        label=label,
        root=root,
        graph=graph,
        clusters=clusters,
    )
    return graph, clusters


def build_stage(
    *,
    repo_root: Path,
    vault_root: Path,
    stage_dir: Path,
    source_pack_path: Path,
    target_count: int,
    internal_link_count: int,
    external_link_count: int,
    vault_max_files: int,
    repo_max_files: int,
) -> dict[str, Any]:
    stage_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = stage_dir / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    repo_graph, _repo_clusters = _run_semantic_bundle(
        repo_root,
        max_files=repo_max_files,
        include_tests=False,
        graph_path=graphs_dir / "repo_graph.json",
        summary_path=stage_dir / "repo_semantic_summary.md",
        label="Repo",
    )
    vault_graph, _vault_clusters = _run_semantic_bundle(
        vault_root,
        max_files=vault_max_files,
        include_tests=False,
        graph_path=graphs_dir / "vault_graph.json",
        summary_path=stage_dir / "vault_semantic_summary.md",
        label="Vault",
    )

    source_pack = _load_source_pack(source_pack_path)
    targets = _rank_targets(vault_graph, limit=target_count)
    hyperfiles_dir = stage_dir / "hyperfiles"
    hyperfiles_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for target in targets:
        internal_targets = _pick_internal_targets(
            vault_graph,
            targets,
            target,
            link_count=min(internal_link_count, max(0, len(targets) - 1)),
        )
        external_sources = _pick_external_sources(
            target.node,
            source_pack,
            link_count=external_link_count,
        )
        out_path = hyperfiles_dir / f"{target.slug}.md"
        _write_hyperfile(
            out_path,
            target=target,
            graph=vault_graph,
            internal_targets=internal_targets,
            external_sources=external_sources,
        )
        manifest_entries.append({
            "title": target.node.name,
            "slug": target.slug,
            "source_file": target.node.source_file,
            "category": target.node.category,
            "salience": target.node.salience,
            "semantic_density": target.node.semantic_density,
            "score": target.score,
            "internal_links": [item.slug for item in internal_targets],
            "external_source_ids": [source["id"] for source in external_sources],
            "output_path": str(out_path),
        })

    index_lines = [
        "# PSMV Hyperfile Staging Index",
        "",
        f"- Generated at: `{_utc_now()}`",
        f"- Vault root: `{vault_root}`",
        f"- Repo root: `{repo_root}`",
        f"- Target count: `{len(manifest_entries)}`",
        f"- Source pack: `{source_pack_path}`",
        "",
        "## Hyperfiles",
        "",
    ]
    for entry in manifest_entries:
        index_lines.append(
            f"- [{entry['title']}](./hyperfiles/{entry['slug']}.md) :: "
            f"`{entry['source_file']}` :: score `{entry['score']}`"
        )
    (stage_dir / "README.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    _write_cross_corpus_summary(
        stage_dir / "cross_corpus_bridge.md",
        repo_graph=repo_graph,
        vault_graph=vault_graph,
        targets=targets,
    )

    manifest = {
        "generated_at": _utc_now(),
        "repo_root": str(repo_root),
        "vault_root": str(vault_root),
        "target_count": len(manifest_entries),
        "internal_link_count": internal_link_count,
        "external_link_count": external_link_count,
        "entries": manifest_entries,
    }
    (stage_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path.cwd()))
    parser.add_argument("--vault-root", required=True)
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--source-pack", required=True)
    parser.add_argument("--target-count", type=int, default=24)
    parser.add_argument("--internal-links", type=int, default=20)
    parser.add_argument("--external-links", type=int, default=20)
    parser.add_argument("--vault-max-files", type=int, default=2500)
    parser.add_argument("--repo-max-files", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = build_stage(
        repo_root=Path(args.repo_root).expanduser().resolve(),
        vault_root=Path(args.vault_root).expanduser().resolve(),
        stage_dir=Path(args.stage_dir).expanduser().resolve(),
        source_pack_path=Path(args.source_pack).expanduser().resolve(),
        target_count=args.target_count,
        internal_link_count=args.internal_links,
        external_link_count=args.external_links,
        vault_max_files=args.vault_max_files,
        repo_max_files=args.repo_max_files,
    )
    print(
        f"psmv_hyperfile_bootstrap targets={manifest['target_count']} "
        f"stage_dir={args.stage_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
