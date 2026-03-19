"""Tests for dharma_swarm.council — models, engine, store."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from dharma_swarm.council.models import (
    ALL_MODELS,
    COUNCIL_PERSONAS,
    CouncilModel,
    Tier,
    get_models,
    get_personas,
)
from dharma_swarm.council.store import CouncilStore
from dharma_swarm.council.engine import (
    CouncilEngine,
    CouncilResult,
    ModelResponse,
    _extract_text,
)


# ── Model registry tests ─────────────────────────────────────────────


class TestModels:
    def test_all_models_count(self):
        assert len(ALL_MODELS) == 14

    def test_tier_distribution(self):
        free = [m for m in ALL_MODELS if m.tier == Tier.FREE]
        cheap = [m for m in ALL_MODELS if m.tier == Tier.CHEAP]
        premium = [m for m in ALL_MODELS if m.tier == Tier.PREMIUM]
        assert len(free) == 2
        assert len(cheap) == 10
        assert len(premium) == 2

    def test_get_models_default_no_premium(self):
        models = get_models()
        for m in models:
            assert m.tier != Tier.PREMIUM

    def test_get_models_free_only(self):
        models = get_models(tiers=[0])
        assert len(models) == 2
        assert all(m.tier == Tier.FREE for m in models)

    def test_get_models_all_tiers(self):
        models = get_models(tiers=[0, 1, 2])
        assert len(models) == 14

    def test_model_short_name(self):
        m = CouncilModel(
            name="Test", model_id="provider/model-name",
            base_url="http://x", key_env="TEST_KEY",
        )
        assert m.short_name == "model-name"

    def test_free_models_have_correct_urls(self):
        free = get_models(tiers=[0])
        urls = {m.base_url for m in free}
        assert "https://ollama.com/v1" in urls
        assert "https://integrate.api.nvidia.com/v1" in urls


class TestPersonas:
    def test_persona_count(self):
        assert len(COUNCIL_PERSONAS) == 20

    def test_get_personas_limited(self):
        p = get_personas(5)
        assert len(p) == 5

    def test_get_personas_all(self):
        p = get_personas()
        assert len(p) == 20

    def test_personas_have_required_fields(self):
        for p in COUNCIL_PERSONAS:
            assert p.name
            assert p.role
            assert p.persona
            assert len(p.persona) > 20

    def test_unique_persona_names(self):
        names = [p.name for p in COUNCIL_PERSONAS]
        assert len(names) == len(set(names))


# ── Store tests ───────────────────────────────────────────────────────


class TestStore:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = CouncilStore(db_path=self.tmp.name)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_save_and_get_session(self):
        self.store.save_session(
            session_id="test-001",
            question="What is 2+2?",
            mode="quick",
            tiers=[0, 1],
        )
        session = self.store.get_session("test-001")
        assert session is not None
        assert session.question == "What is 2+2?"
        assert session.mode == "quick"

    def test_save_and_get_responses(self):
        self.store.save_session(
            session_id="test-002",
            question="Test",
            mode="quick",
            tiers=[0],
        )
        self.store.save_response(
            session_id="test-002",
            model_id="glm-5:cloud",
            response="Answer from GLM",
            model_name="GLM-5",
            latency_ms=500,
        )
        self.store.save_response(
            session_id="test-002",
            model_id="meta/llama-3.3-70b-instruct",
            response="Answer from Llama",
            model_name="Llama 3.3 70B",
            latency_ms=800,
        )
        responses = self.store.get_responses("test-002")
        assert len(responses) == 2
        assert responses[0]["model_id"] == "glm-5:cloud"

    def test_update_synthesis(self):
        self.store.save_session(
            session_id="test-003",
            question="Test",
            mode="quick",
            tiers=[0],
        )
        self.store.update_synthesis("test-003", "All agree: 4", model_count=2)
        session = self.store.get_session("test-003")
        assert session.synthesis == "All agree: 4"
        assert session.model_count == 2

    def test_list_sessions(self):
        for i in range(5):
            self.store.save_session(
                session_id=f"test-{i:03d}",
                question=f"Q{i}",
                mode="quick",
                tiers=[0],
            )
        sessions = self.store.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_get_responses_by_round(self):
        self.store.save_session(
            session_id="test-round",
            question="Test",
            mode="deep",
            tiers=[0],
        )
        self.store.save_response(
            session_id="test-round",
            model_id="m1", response="R1",
            round_num=1,
        )
        self.store.save_response(
            session_id="test-round",
            model_id="m1", response="R2",
            round_num=2,
        )
        r1 = self.store.get_responses("test-round", round_num=1)
        assert len(r1) == 1
        assert r1[0]["response"] == "R1"

    def test_nonexistent_session(self):
        assert self.store.get_session("nonexistent") is None


# ── Engine tests (mocked LLM calls) ──────────────────────────────────


class TestTextExtraction:
    def test_extract_from_openai_response(self):
        mock_resp = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "Hello world"
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp.choices = [mock_choice]
        assert _extract_text(mock_resp) == "Hello world"

    def test_extract_from_empty(self):
        mock_resp = MagicMock()
        mock_resp.choices = []
        assert _extract_text(mock_resp) == ""

    def test_extract_from_dict(self):
        resp = {
            "choices": [
                {"message": {"content": "Dict response"}}
            ]
        }
        assert _extract_text(resp) == "Dict response"


class TestCouncilResult:
    def test_successful_filter(self):
        result = CouncilResult(
            session_id="x", question="Q", mode="quick",
            responses=[
                ModelResponse(model_id="a", model_name="A", response="OK"),
                ModelResponse(model_id="b", model_name="B", response="", error="fail"),
            ],
        )
        assert len(result.successful) == 1
        assert len(result.failed) == 1

    def test_format_markdown(self):
        result = CouncilResult(
            session_id="x", question="Q", mode="quick",
            responses=[
                ModelResponse(model_id="a", model_name="Model A", response="Answer A"),
            ],
            synthesis="All agree",
        )
        md = result.format_markdown()
        assert "Model A" in md
        assert "Answer A" in md
        assert "Synthesis" in md
        assert "All agree" in md


class TestConvergence:
    def setup_method(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.engine = CouncilEngine(
            store=CouncilStore(db_path=tmp.name)
        )
        self._tmp = tmp.name

    def teardown_method(self):
        Path(self._tmp).unlink(missing_ok=True)

    def test_convergence_same_content(self):
        history = [
            "the cat sat on the mat",
            "the cat sat on the mat",
        ]
        assert self.engine._check_convergence(history, 0.10) is True

    def test_no_convergence_different_content(self):
        history = [
            "the cat sat on the mat",
            "quantum mechanics explains entanglement phenomena",
        ]
        assert self.engine._check_convergence(history, 0.10) is False

    def test_convergence_needs_two_rounds(self):
        assert self.engine._check_convergence(["only one"], 0.10) is False


class TestEngineQuick:
    """Test quick mode with mocked API calls."""

    def setup_method(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.engine = CouncilEngine(
            store=CouncilStore(db_path=tmp.name)
        )
        self._tmp = tmp.name

    def teardown_method(self):
        Path(self._tmp).unlink(missing_ok=True)

    def test_quick_with_no_keys(self):
        """With no API keys set, all models should return errors."""
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(
                self.engine.quick("test question", tiers=[0])
            )
        assert result.mode == "quick"
        assert result.question == "test question"
        # All should fail (no API keys)
        assert all(r.error for r in result.responses)

    def test_quick_result_has_session_id(self):
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(
                self.engine.quick("test", tiers=[0])
            )
        assert result.session_id
        assert len(result.session_id) > 0

    def test_quick_stores_session(self):
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(
                self.engine.quick("stored?", tiers=[0])
            )
        stored = self.engine.store.get_session(result.session_id)
        assert stored is not None
        assert stored.question == "stored?"


class TestEngineDeep:
    """Test deep mode with mocked API calls."""

    def setup_method(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.engine = CouncilEngine(
            store=CouncilStore(db_path=tmp.name)
        )
        self._tmp = tmp.name

    def teardown_method(self):
        Path(self._tmp).unlink(missing_ok=True)

    def test_deep_with_no_keys(self):
        """With no API keys, deep mode should still complete."""
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(
                self.engine.deep("test deep", tiers=[0], rounds=2)
            )
        assert result.mode == "deep"
        assert result.rounds_completed >= 1

    def test_deep_stores_session_as_deep(self):
        with patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(
                self.engine.deep("deep test", tiers=[0], rounds=1)
            )
        stored = self.engine.store.get_session(result.session_id)
        assert stored.mode == "deep"
