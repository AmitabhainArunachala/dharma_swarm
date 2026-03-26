from __future__ import annotations

import importlib

import pytest


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in red phase
        pytest.fail(f"expected module {name!r} to exist: {exc}")


def test_research_brief_contract_exposes_phase_one_defaults() -> None:
    models = _load_module("dharma_swarm.auto_research.models")

    brief = models.ResearchBrief(
        task_id="task-brief",
        topic="Research grading",
        question="What makes a report trustworthy?",
    )

    assert brief.audience == "internal"
    assert brief.requires_recency is False
    assert brief.citation_style == "inline"
    assert brief.time_budget_seconds == 300
    assert brief.source_budget == 12
    assert brief.metadata == {}


def test_source_document_normalizes_domain_and_trimmed_text_fields() -> None:
    models = _load_module("dharma_swarm.auto_research.models")

    document = models.SourceDocument(
        source_id="src-1",
        url="https://docs.example.org/path/to/report",
        title="  Verified Notes  ",
        content="  Findings with whitespace.  ",
    )

    assert document.domain == "docs.example.org"
    assert document.source_type == "web"
    assert document.title == "Verified Notes"
    assert document.content == "Findings with whitespace."


def test_claim_record_defaults_support_tracking_fields() -> None:
    models = _load_module("dharma_swarm.auto_research.models")

    claim = models.ClaimRecord(
        claim_id="claim-1",
        text="Grounded claims must stay traceable.",
        support_level="supported",
    )

    assert claim.supporting_source_ids == []
    assert claim.contradicting_source_ids == []
    assert claim.citations == []
    assert claim.confidence == 0.0
