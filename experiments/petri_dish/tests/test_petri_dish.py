"""Tests for the Petri Dish experiment.

Uses mock LLM to avoid real API calls. Tests data models, DNA operations,
worker classification, and the consolidation protocol.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from experiments.petri_dish.dataset import DATASET, get_batch, get_partitioned_batches
from experiments.petri_dish.dna import BehavioralDNA, initialize_dna, ALPHA_DNA
from experiments.petri_dish.models import (
    Classification,
    CycleMetrics,
    Modification,
    SnippetResult,
    TextSnippet,
    WorkerTrace,
)
from experiments.petri_dish.worker import WorkerAgent, save_trace, load_traces
from experiments.petri_dish.llm_client import PetriDishLLM


# ---------------------------------------------------------------------------
# Dataset tests
# ---------------------------------------------------------------------------


class TestDataset:
    def test_dataset_has_80_snippets(self):
        assert len(DATASET) == 80

    def test_all_snippets_have_valid_labels(self):
        for s in DATASET:
            assert s.true_sentiment in {"positive", "negative", "neutral"}
            assert s.true_topic in {"technology", "science", "politics", "culture", "other"}
            assert s.true_urgency in {"high", "medium", "low"}

    def test_no_duplicate_texts(self):
        texts = [s.text for s in DATASET]
        assert len(texts) == len(set(texts))

    def test_label_balance(self):
        sentiments = [s.true_sentiment for s in DATASET]
        for label in ("positive", "negative", "neutral"):
            count = sentiments.count(label)
            assert count >= 10, f"Only {count} {label} snippets"

    def test_get_batch_respects_size(self):
        batch = get_batch(10, seed=42)
        assert len(batch) == 10

    def test_get_batch_deterministic(self):
        b1 = get_batch(10, seed=42)
        b2 = get_batch(10, seed=42)
        assert [s.text for s in b1] == [s.text for s in b2]

    def test_get_batch_different_seeds(self):
        b1 = get_batch(10, seed=1)
        b2 = get_batch(10, seed=2)
        assert [s.text for s in b1] != [s.text for s in b2]

    def test_partitioned_batches_non_overlapping(self):
        batches = get_partitioned_batches(10, 4, seed=42)
        assert len(batches) == 4
        # Within a partition set, batches shouldn't overlap
        for i in range(len(batches)):
            for j in range(i + 1, len(batches)):
                texts_i = {s.text for s in batches[i]}
                texts_j = {s.text for s in batches[j]}
                overlap = texts_i & texts_j
                assert len(overlap) == 0, f"Batches {i} and {j} overlap: {len(overlap)} items"


# ---------------------------------------------------------------------------
# DNA tests
# ---------------------------------------------------------------------------


class TestBehavioralDNA:
    def test_save_and_load(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Generation: 0\n")
        assert "Agent: test" in dna.load()

    def test_get_generation(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Generation: 3\n")
        assert dna.get_generation() == 3

    def test_increment_generation(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Generation: 0\n")
        new_gen = dna.increment_generation()
        assert new_gen == 1
        assert dna.get_generation() == 1

    def test_archive(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Generation: 0\n")
        archive_dir = tmp_path / "archive"
        dest = dna.archive(0, archive_dir)
        assert dest.exists()
        assert "gen_0" in str(dest)

    def test_apply_modification_replace(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Decision Heuristics\nOld heuristic\n")
        result = dna.apply_modification(
            section="Decision Heuristics",
            action="replace",
            old_text="Old heuristic",
            new_text="New heuristic",
        )
        assert result is True
        assert "New heuristic" in dna.load()
        assert "Old heuristic" not in dna.load()

    def test_apply_modification_replace_missing(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Heuristics\nSomething\n")
        result = dna.apply_modification(
            section="Heuristics",
            action="replace",
            old_text="nonexistent text",
            new_text="new text",
        )
        assert result is False

    def test_apply_modification_append(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Known Failure Modes\n\n## Change Log\n")
        result = dna.apply_modification(
            section="Known Failure Modes",
            action="append",
            old_text="",
            new_text="- Misclassifies sarcasm",
        )
        assert result is True
        content = dna.load()
        assert "Misclassifies sarcasm" in content

    def test_append_to_changelog(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Agent: test\n## Change Log\n- Gen 0: Initial\n")
        dna.append_to_changelog("Gen 1: Updated heuristics")
        assert "Gen 1: Updated heuristics" in dna.load()

    def test_validate_valid(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save(ALPHA_DNA)
        assert dna.validate() is True

    def test_validate_missing_section(self, tmp_path: Path):
        dna = BehavioralDNA(tmp_path / "test.md")
        dna.save("# Just a title\n")
        assert dna.validate() is False

    def test_initialize_dna(self, tmp_path: Path):
        agents = initialize_dna(tmp_path)
        assert len(agents) == 3
        assert "classifier_alpha" in agents
        assert "classifier_beta" in agents
        assert "classifier_gamma" in agents
        for name, dna in agents.items():
            assert dna.path.exists()
            assert dna.validate()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_worker_trace_compute_accuracy(self):
        results = [
            SnippetResult(
                snippet_text="test",
                classification=Classification(sentiment="positive", topic="technology", urgency="high"),
                true_sentiment="positive", true_topic="technology", true_urgency="high",
                sentiment_correct=True, topic_correct=True, urgency_correct=True,
            ),
            SnippetResult(
                snippet_text="test2",
                classification=Classification(sentiment="negative", topic="science", urgency="low"),
                true_sentiment="positive", true_topic="science", true_urgency="low",
                sentiment_correct=False, topic_correct=True, urgency_correct=True,
            ),
        ]
        trace = WorkerTrace(agent_name="test", cycle_id=0, generation=0, results=results)
        trace.compute_accuracy()
        assert trace.sentiment_accuracy == 0.5
        assert trace.topic_accuracy == 1.0
        assert trace.urgency_accuracy == 1.0
        assert abs(trace.overall_accuracy - 0.8333) < 0.01

    def test_cycle_metrics_serialization(self):
        m = CycleMetrics(cycle_id=0, generation=0, system_score=0.75)
        data = m.model_dump_json()
        m2 = CycleMetrics.model_validate_json(data)
        assert m2.system_score == 0.75

    def test_modification_model(self):
        mod = Modification(
            agent="alpha", section="Heuristics",
            action="replace", old_text="old", new_text="new",
            rationale="test",
        )
        assert mod.agent == "alpha"


# ---------------------------------------------------------------------------
# Worker tests (with mock LLM)
# ---------------------------------------------------------------------------


class TestWorker:
    @pytest.fixture
    def mock_llm(self):
        llm = PetriDishLLM(api_key="test-key")
        return llm

    @pytest.fixture
    def worker(self, tmp_path: Path, mock_llm: PetriDishLLM):
        dna = BehavioralDNA(tmp_path / "test_worker.md")
        dna.save(ALPHA_DNA)
        return WorkerAgent(
            name="test_worker", dna=dna, llm=mock_llm,
            model="test-model", temperature=0.3,
        )

    @pytest.mark.asyncio
    async def test_classify_one(self, worker: WorkerAgent):
        snippet = TextSnippet(
            text="The server crashed", true_sentiment="negative",
            true_topic="technology", true_urgency="high",
        )
        mock_response = json.dumps({
            "sentiment": "negative", "topic": "technology",
            "urgency": "high", "confidence": 0.9,
        })
        with patch.object(worker.llm, "complete", new_callable=AsyncMock, return_value=mock_response):
            result = await worker.classify_one(snippet)
        assert result.sentiment == "negative"
        assert result.topic == "technology"
        assert result.urgency == "high"

    @pytest.mark.asyncio
    async def test_classify_batch(self, worker: WorkerAgent):
        snippets = [
            TextSnippet(text="Good news", true_sentiment="positive", true_topic="other", true_urgency="low"),
            TextSnippet(text="Bad news", true_sentiment="negative", true_topic="other", true_urgency="high"),
        ]
        batch_response = json.dumps([
            {"sentiment": "positive", "topic": "other", "urgency": "low", "confidence": 0.8},
            {"sentiment": "negative", "topic": "other", "urgency": "high", "confidence": 0.7},
        ])
        with patch.object(
            worker.llm,
            "complete",
            new_callable=AsyncMock,
            return_value=batch_response,
        ) as mock_complete:
            trace = await worker.classify_batch(snippets, cycle_id=0, generation=0)
        assert trace.overall_accuracy == 1.0
        assert len(trace.results) == 2
        assert mock_complete.await_count == 1

    @pytest.mark.asyncio
    async def test_parse_json_in_code_block(self, worker: WorkerAgent):
        snippet = TextSnippet(text="test", true_sentiment="neutral", true_topic="science", true_urgency="low")
        raw = '```json\n{"sentiment": "neutral", "topic": "science", "urgency": "low", "confidence": 0.6}\n```'
        with patch.object(worker.llm, "complete", new_callable=AsyncMock, return_value=raw):
            result = await worker.classify_one(snippet)
        assert result.sentiment == "neutral"

    @pytest.mark.asyncio
    async def test_parse_invalid_json_fallback(self, worker: WorkerAgent):
        snippet = TextSnippet(text="test", true_sentiment="neutral", true_topic="science", true_urgency="low")
        raw = "I think this is neutral about science with low urgency"
        with patch.object(worker.llm, "complete", new_callable=AsyncMock, return_value=raw):
            result = await worker.classify_one(snippet)
        # Should return empty classification with raw_response preserved
        assert result.raw_response == raw

    @pytest.mark.asyncio
    async def test_classify_batch_falls_back_to_second_model(self, tmp_path: Path, mock_llm: PetriDishLLM):
        dna = BehavioralDNA(tmp_path / "fallback_worker.md")
        dna.save(ALPHA_DNA)
        worker = WorkerAgent(
            name="fallback_worker",
            dna=dna,
            llm=mock_llm,
            model=["model-primary", "model-secondary"],
            temperature=0.3,
        )
        snippets = [
            TextSnippet(text="Good news", true_sentiment="positive", true_topic="other", true_urgency="low"),
        ]
        batch_response = json.dumps([
            {"sentiment": "positive", "topic": "other", "urgency": "low", "confidence": 0.8},
        ])
        with patch.object(
            worker.llm,
            "complete",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("rate limited"), batch_response],
        ) as mock_complete:
            trace = await worker.classify_batch(snippets, cycle_id=0, generation=0)

        assert trace.overall_accuracy == 1.0
        assert mock_complete.await_count == 2


class TestTracePersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_traces(self, tmp_path: Path):
        trace = WorkerTrace(
            agent_name="test", cycle_id=0, generation=0,
            sentiment_accuracy=0.8, topic_accuracy=0.7,
            urgency_accuracy=0.6, overall_accuracy=0.7,
        )
        save_trace(trace, tmp_path)
        loaded = load_traces(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].agent_name == "test"
        assert loaded[0].overall_accuracy == 0.7

    def test_load_traces_empty_dir(self, tmp_path: Path):
        traces = load_traces(tmp_path / "nonexistent")
        assert traces == []

    @pytest.mark.asyncio
    async def test_load_traces_by_generation(self, tmp_path: Path):
        for gen in range(3):
            trace = WorkerTrace(agent_name="a", cycle_id=gen, generation=gen)
            save_trace(trace, tmp_path)
        loaded = load_traces(tmp_path, generation=1)
        assert len(loaded) == 1
        assert loaded[0].generation == 1
