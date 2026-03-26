from __future__ import annotations

import importlib

import pytest


def _load_module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in red phase
        pytest.fail(f"expected module {name!r} to exist: {exc}")


class _StubSearchBackend:
    def search(self, brief, queries):
        assert brief.task_id == "task-research"
        assert [query.intent for query in queries] == [
            "discovery",
            "validation",
            "contradiction",
        ]
        return [
            {
                "source_id": "src-1",
                "url": "https://research.example.com/benchmarks",
                "title": "  Benchmark Notes  ",
                "content": "  Benchmark accuracy improved by 12 percent.  ",
                "metadata": {
                    "claims": ["Benchmark accuracy improved by 12 percent."],
                },
            },
            {
                "source_id": "src-2",
                "url": "https://reviews.example.org/analysis",
                "title": "Skeptical Review",
                "content": "Some tasks showed smaller gains.",
                "metadata": {
                    "claims": ["Some tasks showed smaller gains."],
                },
            },
        ]


def test_auto_research_engine_plans_query_stages() -> None:
    engine_module = _load_module("dharma_swarm.auto_research.engine")
    models = _load_module("dharma_swarm.auto_research.models")

    brief = models.ResearchBrief(
        task_id="task-latest",
        topic="Model releases",
        question="What changed in March 2026?",
        requires_recency=True,
    )

    engine = engine_module.AutoResearchEngine()
    queries = engine.plan(brief)

    assert [query.intent for query in queries] == [
        "discovery",
        "validation",
        "contradiction",
        "update",
    ]
    assert queries[0].query_id == "task-latest:discovery:1"
    assert "Model releases" in queries[-1].text
    assert "March 2026" in queries[-1].text


def test_auto_research_engine_normalizes_sources_and_emits_report() -> None:
    engine_module = _load_module("dharma_swarm.auto_research.engine")
    models = _load_module("dharma_swarm.auto_research.models")

    brief = models.ResearchBrief(
        task_id="task-research",
        topic="Benchmark reliability",
        question="What do the sources agree on?",
    )

    engine = engine_module.AutoResearchEngine(search_backend=_StubSearchBackend())
    report = engine.run(brief)

    assert report.report_id == "report-task-research"
    assert report.task_id == "task-research"
    assert report.brief.task_id == "task-research"
    assert report.source_ids == ["src-1", "src-2"]
    assert [claim.text for claim in report.claims] == [
        "Benchmark accuracy improved by 12 percent.",
        "Some tasks showed smaller gains.",
    ]
    assert report.claims[0].supporting_source_ids == ["src-1"]
    assert report.claims[0].citations == ["[src-1]"]
    assert report.body.count("[src-") == 2
    assert report.metadata["query_intents"] == [
        "discovery",
        "validation",
        "contradiction",
    ]
