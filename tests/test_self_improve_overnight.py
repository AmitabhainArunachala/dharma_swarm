"""Tests for self_improve.py overnight activation functions."""

from __future__ import annotations

import os

from dharma_swarm.self_improve import (
    AUTONOMY_LEVEL_0,
    AUTONOMY_LEVEL_1,
    AUTONOMY_LEVEL_2,
    AUTONOMY_LEVEL_3,
    disable_overnight,
    enable_for_overnight,
    is_enabled,
    is_overnight_active,
    overnight_autonomy_level,
)


class TestOvernightActivation:
    def setup_method(self):
        """Clean state before each test."""
        disable_overnight()
        os.environ.pop("DHARMA_SELF_IMPROVE", None)

    def teardown_method(self):
        """Clean state after each test."""
        disable_overnight()
        os.environ.pop("DHARMA_SELF_IMPROVE", None)

    def test_enable_sets_env_var(self):
        enable_for_overnight()
        assert os.environ.get("DHARMA_SELF_IMPROVE") == "1"
        assert is_enabled()

    def test_enable_sets_overnight_active(self):
        enable_for_overnight()
        assert is_overnight_active()

    def test_default_autonomy_level_is_1(self):
        enable_for_overnight()
        assert overnight_autonomy_level() == AUTONOMY_LEVEL_1

    def test_custom_autonomy_level(self):
        enable_for_overnight(autonomy_level=AUTONOMY_LEVEL_0)
        assert overnight_autonomy_level() == AUTONOMY_LEVEL_0

    def test_autonomy_level_clamped_high(self):
        enable_for_overnight(autonomy_level=99)
        assert overnight_autonomy_level() == AUTONOMY_LEVEL_3

    def test_autonomy_level_clamped_low(self):
        enable_for_overnight(autonomy_level=-5)
        assert overnight_autonomy_level() == AUTONOMY_LEVEL_0

    def test_disable_clears_env(self):
        enable_for_overnight()
        disable_overnight()
        assert not is_enabled()
        assert not is_overnight_active()

    def test_autonomy_level_negative_when_inactive(self):
        assert overnight_autonomy_level() == -1

    def test_enable_disable_cycle(self):
        enable_for_overnight(AUTONOMY_LEVEL_2)
        assert is_overnight_active()
        assert overnight_autonomy_level() == AUTONOMY_LEVEL_2
        disable_overnight()
        assert not is_overnight_active()
        assert overnight_autonomy_level() == -1
