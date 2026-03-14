"""Tests for dharma_swarm.zeitgeist -- S4 environmental intelligence.

Tests the ZeitgeistSignal model, keyword relevance scoring,
threat detection, local scanning, and persistence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dharma_swarm.zeitgeist import (
    RESEARCH_KEYWORDS,
    THREAT_KEYWORDS,
    ZeitgeistScanner,
    ZeitgeistSignal,
)


# -- Model tests -----------------------------------------------------------


class TestZeitgeistSignalModel:
    def test_signal_has_correct_fields(self) -> None:
        sig = ZeitgeistSignal(
            source="manual",
            category="methodology",
            title="Test signal",
        )
        assert sig.id  # non-empty auto-generated
        assert sig.source == "manual"
        assert sig.category == "methodology"
        assert sig.title == "Test signal"
        assert sig.relevance_score == 0.0
        assert sig.keywords == []
        assert sig.description == ""
        assert sig.timestamp is not None

    def test_signal_serialization_roundtrip(self) -> None:
        sig = ZeitgeistSignal(
            source="local_scan",
            category="threat",
            title="Preprint detected",
            relevance_score=0.8,
            keywords=["preprint", "recursive"],
        )
        raw = sig.model_dump_json()
        restored = ZeitgeistSignal.model_validate_json(raw)
        assert restored.title == sig.title
        assert restored.relevance_score == sig.relevance_score
        assert restored.keywords == sig.keywords


# -- Keyword relevance tests -----------------------------------------------


class TestKeywordRelevance:
    def test_keyword_relevance_high(self) -> None:
        scanner = ZeitgeistScanner()
        text = (
            "mechanistic interpretability of the participation ratio "
            "shows self-reference in the value matrix with contraction "
            "and phase transition patterns"
        )
        score = scanner.keyword_relevance(text)
        assert score >= 0.8

    def test_keyword_relevance_zero(self) -> None:
        scanner = ZeitgeistScanner()
        text = "The weather is nice today and I had eggs for breakfast."
        score = scanner.keyword_relevance(text)
        assert score == 0.0

    def test_keyword_relevance_partial(self) -> None:
        scanner = ZeitgeistScanner()
        text = "A new SAE paper on superposition was released."
        score = scanner.keyword_relevance(text)
        assert 0.0 < score < 1.0


# -- Threat detection tests ------------------------------------------------


class TestDetectThreats:
    def test_detect_threats_finds_keywords(self) -> None:
        scanner = ZeitgeistScanner()
        text = "A preprint on arxiv contradicts our finding."
        threats = scanner.detect_threats(text)
        assert "preprint" in threats
        assert "arxiv" in threats
        assert "contradicts" in threats

    def test_detect_no_threats(self) -> None:
        scanner = ZeitgeistScanner()
        text = "Normal research progress on transformer architecture."
        threats = scanner.detect_threats(text)
        assert threats == []


# -- Local scan tests ------------------------------------------------------


class TestScanLocal:
    @pytest.mark.asyncio
    async def test_scan_local_no_data(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        scanner = ZeitgeistScanner(state_dir=state_dir)
        signals = await scanner.scan()
        assert signals == []

    @pytest.mark.asyncio
    async def test_scan_local_with_notes(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        shared_dir = state_dir / "shared"
        shared_dir.mkdir(parents=True)

        # Write a note with research keywords
        (shared_dir / "research_notes.md").write_text(
            "Found interesting results on mechanistic interpretability "
            "and participation ratio in self-reference experiments."
        )

        scanner = ZeitgeistScanner(state_dir=state_dir)
        signals = await scanner.scan()

        assert len(signals) >= 1
        sig = signals[0]
        assert sig.source == "local_scan"
        assert sig.category == "methodology"
        assert sig.relevance_score > 0.0
        assert len(sig.keywords) > 0

    @pytest.mark.asyncio
    async def test_scan_local_with_threats(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        shared_dir = state_dir / "shared"
        shared_dir.mkdir(parents=True)

        (shared_dir / "alert.md").write_text(
            "A preprint on arxiv shows mechanistic interpretability "
            "results on participation ratio that could be competing."
        )

        scanner = ZeitgeistScanner(state_dir=state_dir)
        signals = await scanner.scan()

        assert len(signals) >= 1
        threat_signals = [s for s in signals if s.category == "threat"]
        assert len(threat_signals) >= 1

    @pytest.mark.asyncio
    async def test_scan_local_high_stigmergy(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        stig_dir = state_dir / "stigmergy"
        stig_dir.mkdir(parents=True)

        # Write > 1000 marks
        lines = [json.dumps({"mark": i}) for i in range(1100)]
        (stig_dir / "marks.jsonl").write_text("\n".join(lines))

        scanner = ZeitgeistScanner(state_dir=state_dir)
        signals = await scanner.scan()

        opportunity = [s for s in signals if s.category == "opportunity"]
        assert len(opportunity) == 1
        assert "stigmergy" in opportunity[0].title.lower()


# -- Persistence tests -----------------------------------------------------


class TestSaveAndLoad:
    @pytest.mark.asyncio
    async def test_save_creates_files(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        scanner = ZeitgeistScanner(state_dir=state_dir)

        # Manually add a signal
        scanner._signals = [
            ZeitgeistSignal(
                source="manual",
                category="tool_release",
                title="New SAE toolkit",
                relevance_score=0.6,
                keywords=["SAE", "sparse autoencoder"],
            )
        ]
        scanner._save()

        meta_dir = state_dir / "meta"
        assert (meta_dir / "zeitgeist.md").exists()
        assert (meta_dir / "zeitgeist.jsonl").exists()

        md_content = (meta_dir / "zeitgeist.md").read_text()
        assert "tool_release" in md_content
        assert "New SAE toolkit" in md_content

    @pytest.mark.asyncio
    async def test_load_history(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".dharma"
        state_dir.mkdir()
        scanner = ZeitgeistScanner(state_dir=state_dir)

        # Save two signals
        scanner._signals = [
            ZeitgeistSignal(source="manual", category="methodology", title="A"),
            ZeitgeistSignal(source="manual", category="threat", title="B"),
        ]
        scanner._save()

        # Load them back
        loaded = scanner.load_history()
        assert len(loaded) == 2
        assert loaded[0].title == "A"
        assert loaded[1].title == "B"


# -- Constant tests --------------------------------------------------------


class TestConstants:
    def test_research_keywords_nonempty(self) -> None:
        assert len(RESEARCH_KEYWORDS) > 10

    def test_threat_keywords_nonempty(self) -> None:
        assert len(THREAT_KEYWORDS) > 3


# -- Filter property tests -------------------------------------------------


class TestLatestThreats:
    def test_latest_threats_filter(self) -> None:
        scanner = ZeitgeistScanner()
        scanner._signals = [
            ZeitgeistSignal(source="manual", category="threat", title="T1"),
            ZeitgeistSignal(source="manual", category="methodology", title="M1"),
            ZeitgeistSignal(source="manual", category="threat", title="T2"),
        ]
        threats = scanner.latest_threats
        assert len(threats) == 2
        assert all(t.category == "threat" for t in threats)

    def test_latest_threats_empty(self) -> None:
        scanner = ZeitgeistScanner()
        scanner._signals = [
            ZeitgeistSignal(source="manual", category="methodology", title="M1"),
        ]
        threats = scanner.latest_threats
        assert threats == []
