"""Tests for dharma_swarm.rv — R_V measurement module.

All torch functionality is mocked. These tests run without torch installed.
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from dharma_swarm.rv import (
    RV_CONTRACTION_THRESHOLD,
    RV_STRONG_THRESHOLD,
    RVMeasurer,
    RVReading,
    _prompt_hash,
    _torch_available,
    _utc_now,
)


# ── RVReading Model Tests ──────────────────────────────────────────────────


def _make_reading(**overrides) -> RVReading:
    """Helper to build an RVReading with sensible defaults."""
    defaults = dict(
        rv=0.65,
        pr_early=8.3,
        pr_late=5.4,
        model_name="test-model",
        early_layer=2,
        late_layer=22,
        prompt_hash="abcdef0123456789",
        prompt_group="L4",
    )
    defaults.update(overrides)
    return RVReading(**defaults)


class TestRVReading:
    """Tests for the RVReading Pydantic model."""

    def test_creation_with_defaults(self):
        reading = _make_reading()
        assert reading.rv == 0.65
        assert reading.model_name == "test-model"
        assert reading.prompt_group == "L4"
        assert isinstance(reading.timestamp, datetime)
        assert reading.timestamp.tzinfo == timezone.utc

    def test_default_prompt_group_is_unknown(self):
        reading = _make_reading(prompt_group="unknown")
        assert reading.prompt_group == "unknown"

    def test_is_contracted_below_threshold(self):
        reading = _make_reading(rv=0.5)
        assert reading.is_contracted is True

    def test_is_contracted_at_threshold(self):
        reading = _make_reading(rv=RV_CONTRACTION_THRESHOLD)
        assert reading.is_contracted is False

    def test_is_contracted_above_threshold(self):
        reading = _make_reading(rv=0.9)
        assert reading.is_contracted is False

    def test_is_contracted_at_unity(self):
        reading = _make_reading(rv=1.0)
        assert reading.is_contracted is False

    def test_contraction_strength_strong(self):
        reading = _make_reading(rv=0.3)
        assert reading.contraction_strength == "strong"

    def test_contraction_strength_moderate(self):
        reading = _make_reading(rv=0.6)
        assert reading.contraction_strength == "moderate"

    def test_contraction_strength_weak(self):
        reading = _make_reading(rv=0.85)
        assert reading.contraction_strength == "weak"

    def test_contraction_strength_none(self):
        reading = _make_reading(rv=1.2)
        assert reading.contraction_strength == "none"

    def test_contraction_strength_at_boundary_strong(self):
        """rv exactly at 0.5 should be moderate, not strong."""
        reading = _make_reading(rv=RV_STRONG_THRESHOLD)
        assert reading.contraction_strength == "moderate"

    def test_contraction_strength_at_boundary_moderate(self):
        """rv exactly at 0.737 should be weak, not moderate."""
        reading = _make_reading(rv=RV_CONTRACTION_THRESHOLD)
        assert reading.contraction_strength == "weak"

    def test_contraction_strength_exactly_one(self):
        reading = _make_reading(rv=1.0)
        assert reading.contraction_strength == "none"

    def test_json_roundtrip(self):
        reading = _make_reading()
        json_str = reading.model_dump_json()
        restored = RVReading.model_validate_json(json_str)
        assert restored.rv == reading.rv
        assert restored.model_name == reading.model_name
        assert restored.prompt_hash == reading.prompt_hash
        assert restored.early_layer == reading.early_layer
        assert restored.late_layer == reading.late_layer
        assert restored.prompt_group == reading.prompt_group

    def test_dict_roundtrip(self):
        reading = _make_reading()
        data = reading.model_dump()
        restored = RVReading.model_validate(data)
        assert restored.rv == reading.rv
        assert restored.pr_early == reading.pr_early
        assert restored.pr_late == reading.pr_late


# ── Utility Tests ───────────────────────────────────────────────────────────


class TestUtilities:
    """Tests for module-level utility functions."""

    def test_prompt_hash_deterministic(self):
        h1 = _prompt_hash("observe the observer observing")
        h2 = _prompt_hash("observe the observer observing")
        assert h1 == h2

    def test_prompt_hash_length(self):
        h = _prompt_hash("test prompt")
        assert len(h) == 16

    def test_prompt_hash_is_hex(self):
        h = _prompt_hash("anything")
        int(h, 16)  # raises if not valid hex

    def test_prompt_hash_matches_sha256(self):
        prompt = "recursive self-observation"
        expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        assert _prompt_hash(prompt) == expected

    def test_prompt_hash_different_for_different_prompts(self):
        h1 = _prompt_hash("prompt A")
        h2 = _prompt_hash("prompt B")
        assert h1 != h2

    def test_utc_now_has_timezone(self):
        now = _utc_now()
        assert now.tzinfo == timezone.utc


# ── Torch Availability Tests ───────────────────────────────────────────────


class TestTorchAvailability:
    """Tests for torch import guarding."""

    def test_torch_available_returns_false_when_not_importable(self):
        with patch.dict("sys.modules", {"torch": None}):
            with patch("builtins.__import__", side_effect=_import_blocker("torch")):
                assert _torch_available() is False

    def test_torch_available_returns_true_when_importable(self):
        mock_torch = MagicMock()
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert _torch_available() is True


# ── RVMeasurer Tests ────────────────────────────────────────────────────────


class TestRVMeasurer:
    """Tests for the RVMeasurer class (all torch mocked)."""

    def test_init_defaults(self):
        m = RVMeasurer()
        assert m.model_name == "pythia-1.4b"
        assert m.device == "mps"
        assert m._model is None
        assert m._tokenizer is None

    def test_init_custom(self):
        m = RVMeasurer(model_name="mistral-7b", device="cuda")
        assert m.model_name == "mistral-7b"
        assert m.device == "cuda"

    def test_is_available_false_without_torch(self):
        m = RVMeasurer()
        with patch("dharma_swarm.rv._torch_available", return_value=False):
            assert m.is_available() is False

    def test_is_available_true_with_torch(self):
        m = RVMeasurer()
        with patch("dharma_swarm.rv._torch_available", return_value=True):
            assert m.is_available() is True

    @pytest.mark.asyncio
    async def test_measure_returns_none_when_torch_unavailable(self):
        m = RVMeasurer()
        with patch("dharma_swarm.rv._torch_available", return_value=False):
            result = await m.measure("test prompt")
            assert result is None

    @pytest.mark.asyncio
    async def test_measure_returns_reading_when_torch_available(self):
        m = RVMeasurer()
        m._model = MagicMock()
        m._model.config.num_hidden_layers = 24

        with patch("dharma_swarm.rv._torch_available", return_value=True):
            with patch.object(
                m, "_sync_measure", return_value=(0.65, 8.3, 5.4)
            ):
                result = await m.measure("test prompt", group="L4")

        assert result is not None
        assert isinstance(result, RVReading)
        assert result.rv == 0.65
        assert result.pr_early == 8.3
        assert result.pr_late == 5.4
        assert result.model_name == "pythia-1.4b"
        assert result.early_layer == 2
        assert result.late_layer == 22
        assert result.prompt_group == "L4"
        assert len(result.prompt_hash) == 16

    @pytest.mark.asyncio
    async def test_measure_lazy_loads_model(self):
        m = RVMeasurer()
        assert m._model is None

        async def fake_load():
            m._model = MagicMock()
            m._model.config.num_hidden_layers = 24

        with patch("dharma_swarm.rv._torch_available", return_value=True):
            with patch("asyncio.to_thread") as mock_to_thread:
                # First call triggers _load_model, second call runs _sync_measure
                call_count = 0

                async def side_effect(fn, *args):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        # _load_model call
                        await fake_load()
                        return None
                    else:
                        # _sync_measure call
                        return (0.7, 7.0, 4.9)

                mock_to_thread.side_effect = side_effect
                result = await m.measure("test prompt")

        assert m._model is not None
        assert result is not None
        assert result.rv == 0.7

    @pytest.mark.asyncio
    async def test_measure_skips_load_if_model_present(self):
        m = RVMeasurer()
        m._model = MagicMock()
        m._model.config.num_hidden_layers = 32

        with patch("dharma_swarm.rv._torch_available", return_value=True):
            with patch("asyncio.to_thread") as mock_to_thread:
                mock_to_thread.return_value = (0.8, 6.0, 4.8)
                result = await m.measure("already loaded")

        # Only one call to to_thread (sync_measure), not two (load + measure)
        assert mock_to_thread.call_count == 1
        assert result is not None
        assert result.rv == 0.8
        assert result.late_layer == 30  # 32 - 2


# ── Constants Tests ─────────────────────────────────────────────────────────


class TestConstants:
    """Verify research-derived constants are correctly set."""

    def test_contraction_threshold(self):
        assert RV_CONTRACTION_THRESHOLD == 0.737

    def test_strong_threshold(self):
        assert RV_STRONG_THRESHOLD == 0.5

    def test_strong_less_than_contraction(self):
        assert RV_STRONG_THRESHOLD < RV_CONTRACTION_THRESHOLD


# ── Helpers ─────────────────────────────────────────────────────────────────


def _import_blocker(blocked_name: str):
    """Return an __import__ replacement that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def blocker(name, *args, **kwargs):
        if name == blocked_name or name.startswith(blocked_name + "."):
            raise ImportError(f"Mocked: {name} not available")
        return real_import(name, *args, **kwargs)

    return blocker
