from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dharma_swarm.citation_index import CitationIndex
from dharma_swarm.contradiction_registry import ContradictionRegistry
from dharma_swarm.semantic_gravity import ConceptGraph, ConceptNode
from dharma_swarm.semantic_ingestion import IngestionSourceSpec, SemanticIngestionSpine


def _make_source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "geb.md").write_text(
        "# Strange Loops\n\n"
        "Hofstadter writes about self-reference, recursive structure, and strange loops.\n\n"
        "This note grounds semantic lineage and reflective systems.\n",
        encoding="utf-8",
    )
    (root / "cybernetics.py").write_text(
        '"""Cybernetic feedback controllers."""\n\n'
        "class FeedbackController:\n"
        '    """Coordinates adaptive regulation."""\n'
        "    pass\n",
        encoding="utf-8",
    )
    return root


def _write_concept_graph(state_dir: Path) -> tuple[Path, ConceptNode]:
    graph = ConceptGraph()
    node = ConceptNode(
        name="Autopoiesis",
        definition="Self-producing organization with recursive closure.",
        source_file="dharma_swarm/organism.py",
        category="philosophical",
        salience=0.91,
        formal_structures=["recursive_closure", "self_reference"],
        recognition_type="concept",
    )
    graph.add_node(node)

    graph_path = state_dir / "semantic" / "concept_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return graph_path, node


def test_semantic_ingestion_source_registry_round_trip(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    spine = SemanticIngestionSpine(state_dir=state_dir)

    added = spine.add_source(
        IngestionSourceSpec(
            name="geb",
            roots=[str(tmp_path / "canon")],
            tags=["hofstadter", "strange-loop"],
        )
    )

    assert added.name == "geb"
    listed = spine.list_sources(enabled_only=False)
    assert len(listed) == 1
    assert listed[0].name == "geb"
    assert listed[0].tags == ["hofstadter", "strange-loop"]

    payload = json.loads((state_dir / "semantic" / "ingestion_sources.json").read_text(encoding="utf-8"))
    assert payload["sources"][0]["name"] == "geb"


def test_semantic_ingestion_run_indexes_documents_and_graph(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = _make_source_tree(tmp_path)
    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(
        IngestionSourceSpec(
            name="core",
            roots=[str(source_root)],
            tags=["cybernetics", "hofstadter"],
        )
    )

    report = spine.run(max_files=20)

    assert report.files_scanned == 2
    assert report.files_ingested == 2
    assert report.concept_nodes > 0
    assert Path(report.graph_path).exists()

    status = spine.status()
    assert status["documents"] == 2
    assert status["vector_store"]["total_documents"] >= 2
    assert status["index"]["source_documents"] >= 2


def test_semantic_ingestion_search_returns_ingested_hits(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = _make_source_tree(tmp_path)
    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(
        IngestionSourceSpec(
            name="core",
            roots=[str(source_root)],
            tags=["cybernetics", "hofstadter"],
        )
    )
    spine.run(max_files=20)

    hits = spine.search("strange loops self-reference", limit=5)

    assert hits
    assert hits[0]["source_name"] == "core"
    assert "geb.md" in hits[0]["source_path"]


def test_semantic_ingestion_run_skips_unchanged_files(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = _make_source_tree(tmp_path)
    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(IngestionSourceSpec(name="core", roots=[str(source_root)]))

    first = spine.run(max_files=20)
    second = spine.run(max_files=20)

    assert first.files_ingested == 2
    assert second.files_ingested == 0
    assert second.files_skipped == 2


def test_semantic_ingestion_creates_deterministic_source_to_artifact_citations(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = _make_source_tree(tmp_path)
    source_path = (source_root / "geb.md").resolve()
    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(
        IngestionSourceSpec(
            name="core",
            roots=[str(source_root)],
            tags=["cybernetics", "hofstadter"],
        )
    )

    first = spine.run(max_files=20)

    assert first.files_ingested == 2

    document = spine._document_for_path(str(source_path), source_name="core")
    assert document is not None

    citations_path = state_dir / "citations" / "citations.jsonl"
    citations = CitationIndex(path=citations_path)
    asyncio.run(citations.load())
    first_citations = asyncio.run(citations.list_all())

    assert len(first_citations) == 2

    target_citations = asyncio.run(citations.query_by_target(document["archive_path"]))

    assert len(target_citations) == 1
    citation = target_citations[0]
    assert citation.source_work == "core"
    assert citation.source_location == str(source_path)
    assert citation.target_type == "artifact"
    assert citation.relationship == "grounds"
    assert citation.created_by == "semantic_ingestion"
    assert "strange loops" in citation.passage_text.lower()
    assert document["metadata"]["citation_ids"] == [citation.id]

    second = spine.run(max_files=20)

    assert second.files_ingested == 0

    reloaded = CitationIndex(path=citations_path)
    asyncio.run(reloaded.load())
    second_citations = asyncio.run(reloaded.list_all())

    assert len(second_citations) == 2
    assert sorted(item.id for item in second_citations) == sorted(item.id for item in first_citations)


def test_semantic_ingestion_concept_graph_bootstrap_indexes_and_is_idempotent(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / ".dharma"
    graph_path, node = _write_concept_graph(state_dir)
    spine = SemanticIngestionSpine(state_dir=state_dir)

    first = spine.bootstrap_from_concept_graph()

    assert first.graph_path == str(graph_path)
    assert first.concept_nodes == 1
    assert first.indexed_concepts == 1
    assert first.files_ingested == 1
    assert first.files_skipped == 0

    status = spine.status()
    assert status["documents"] == 1
    assert status["vector_store"]["total_documents"] == 1

    hits = spine.search("autopoiesis recursive closure", limit=5)
    assert hits
    assert hits[0]["title"] == "Autopoiesis"
    assert hits[0]["source_name"] == "concept_graph"
    assert hits[0]["source_path"] == f"concept://{node.id}"

    second = spine.bootstrap_from_concept_graph()

    assert second.concept_nodes == 1
    assert second.indexed_concepts == 0
    assert second.files_ingested == 0
    assert second.files_skipped == 1


def test_semantic_ingest_bootstrap_status_includes_last_run_counts(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    _write_concept_graph(state_dir)
    spine = SemanticIngestionSpine(state_dir=state_dir)

    report = spine.bootstrap_from_concept_graph()
    status = spine.status()
    last_run = status["last_run"]

    assert last_run is not None
    assert last_run["run_id"] == report.run_id
    assert last_run["status"] == "completed"
    assert last_run["stats"]["source_names"] == ["concept_graph"]
    assert last_run["stats"]["concept_nodes"] == 1
    assert last_run["stats"]["concept_edges"] == 0
    assert last_run["stats"]["indexed_concepts"] == 1


def test_semantic_ingestion_surfaces_obvious_claim_contradictions(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = tmp_path / "sources"
    source_root.mkdir()
    first = source_root / "provenance_positive.md"
    second = source_root / "provenance_negative.md"
    first.write_text(
        "# Provenance Positive\n\n"
        "The ingestion spine must always preserve provenance across documents.\n",
        encoding="utf-8",
    )
    second.write_text(
        "# Provenance Negative\n\n"
        "The ingestion spine must never preserve provenance across documents.\n",
        encoding="utf-8",
    )

    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(IngestionSourceSpec(name="core", roots=[str(source_root)]))

    report = spine.run(max_files=20)

    assert report.files_ingested == 2

    registry = ContradictionRegistry(path=state_dir / "contradictions" / "registry.jsonl")

    asyncio.run(registry.load())
    contradictions = asyncio.run(registry.list_all())

    assert len(contradictions) == 1
    contradiction = contradictions[0]
    assert contradiction.created_by == "semantic_ingestion"
    assert contradiction.claim_a in {
        "The ingestion spine must always preserve provenance across documents.",
        "The ingestion spine must never preserve provenance across documents.",
    }
    assert contradiction.claim_b in {
        "The ingestion spine must always preserve provenance across documents.",
        "The ingestion spine must never preserve provenance across documents.",
    }
    assert contradiction.claim_a != contradiction.claim_b
    assert f"source_path:{first.resolve()}" in contradiction.tags
    assert f"source_path:{second.resolve()}" in contradiction.tags


def test_semantic_ingestion_does_not_create_contradictions_for_benign_claims(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "grounding.md").write_text(
        "# Grounding\n\n"
        "The ingestion spine must preserve provenance across documents.\n",
        encoding="utf-8",
    )
    (source_root / "indexing.md").write_text(
        "# Indexing\n\n"
        "The ingestion spine must preserve lexical retrieval quality across documents.\n",
        encoding="utf-8",
    )

    spine = SemanticIngestionSpine(state_dir=state_dir)
    spine.add_source(IngestionSourceSpec(name="core", roots=[str(source_root)]))

    report = spine.run(max_files=20)

    assert report.files_ingested == 2

    registry = ContradictionRegistry(path=state_dir / "contradictions" / "registry.jsonl")

    asyncio.run(registry.load())
    assert asyncio.run(registry.list_all()) == []
