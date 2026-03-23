"""Tests for daemon_config, thread_manager, and ecosystem_bridge."""

import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.daemon_config import (
    CircuitBreaker,
    DaemonConfig,
    ROLE_BRIEFINGS,
    THREAD_PROMPTS,
    V7_BASE_RULES,
)
from dharma_swarm.thread_manager import ThreadManager


# --- CircuitBreaker ---

def test_circuit_breaker_defaults():
    cb = CircuitBreaker()
    assert cb.consecutive_failures == 0
    assert cb.max_failures == 3
    assert not cb.is_broken


def test_circuit_breaker_trips():
    cb = CircuitBreaker()
    assert not cb.record_failure()
    assert not cb.record_failure()
    assert cb.record_failure()  # 3rd failure trips it
    assert cb.is_broken


def test_circuit_breaker_resets():
    cb = CircuitBreaker()
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.consecutive_failures == 0
    assert not cb.is_broken


def test_circuit_breaker_fitness_trend():
    cb = CircuitBreaker()
    assert not cb.record_fitness(0.5, 0.6)  # down
    assert not cb.record_fitness(0.4, 0.5)  # down
    assert cb.record_fitness(0.3, 0.4)      # 3rd downtrend trips


# --- DaemonConfig ---

def test_daemon_config_defaults():
    cfg = DaemonConfig()
    assert cfg.heartbeat_interval == 21600.0
    assert cfg.max_daily_contributions == 40
    assert cfg.fitness_threshold == 0.6
    assert cfg.crown_jewel_threshold == 0.85
    assert len(cfg.threads) == 5
    assert cfg.rotation_mode == "sequential"
    assert 2 in cfg.quiet_hours


def test_thread_prompts_complete():
    cfg = DaemonConfig()
    for thread in cfg.threads:
        assert thread in THREAD_PROMPTS
        assert len(THREAD_PROMPTS[thread]) > 20


def test_role_briefings_complete():
    for role in ["cartographer", "archeologist", "surgeon", "architect", "validator"]:
        assert role in ROLE_BRIEFINGS
        assert len(ROLE_BRIEFINGS[role]) > 50


def test_v7_base_rules():
    assert "IMMUTABILITY" in V7_BASE_RULES
    assert "AHIMSA" in V7_BASE_RULES
    assert "SILENCE IS VALID" in V7_BASE_RULES
    assert "seven non-negotiable rules" in V7_BASE_RULES
    assert "LEAVE MARKS" in V7_BASE_RULES


# --- ThreadManager ---

def test_thread_manager_init():
    cfg = DaemonConfig()
    with tempfile.TemporaryDirectory() as tmp:
        tm = ThreadManager(cfg, Path(tmp))
        assert tm.current_thread == "mechanistic"
        assert "R_V" in tm.current_prompt


def test_thread_manager_rotate_sequential():
    cfg = DaemonConfig(rotation_mode="sequential")
    with tempfile.TemporaryDirectory() as tmp:
        tm = ThreadManager(cfg, Path(tmp))
        assert tm.current_thread == "mechanistic"
        tm.rotate()
        assert tm.current_thread == "phenomenological"
        tm.rotate()
        assert tm.current_thread == "architectural"


def test_thread_manager_rotate_wraps():
    cfg = DaemonConfig(rotation_mode="sequential")
    with tempfile.TemporaryDirectory() as tmp:
        tm = ThreadManager(cfg, Path(tmp))
        for _ in range(5):
            tm.rotate()
        assert tm.current_thread == "mechanistic"  # wrapped around


def test_thread_manager_contribution_tracking():
    cfg = DaemonConfig()
    with tempfile.TemporaryDirectory() as tmp:
        tm = ThreadManager(cfg, Path(tmp))
        tm.record_contribution()
        tm.record_contribution()
        stats = tm.stats()
        assert stats["contributions"]["mechanistic"] == 2
        assert stats["total"] == 2


def test_thread_manager_persistence():
    cfg = DaemonConfig(rotation_mode="sequential")
    with tempfile.TemporaryDirectory() as tmp:
        tm = ThreadManager(cfg, Path(tmp))
        tm.rotate()
        tm.record_contribution()

        # New instance should load state
        tm2 = ThreadManager(cfg, Path(tmp))
        assert tm2.current_thread == "phenomenological"
        assert tm2.stats()["contributions"]["phenomenological"] == 1


def test_thread_manager_focus_override():
    cfg = DaemonConfig()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        tm = ThreadManager(cfg, p)
        assert tm.check_focus_override(p) is None

        (p / ".FOCUS").write_text("alignment")
        assert tm.check_focus_override(p) == "alignment"


def test_thread_manager_inject_override():
    cfg = DaemonConfig()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        tm = ThreadManager(cfg, p)
        assert tm.check_inject_override(p) is None

        (p / ".INJECT").write_text("Focus on R_V paper deadline")
        assert tm.check_inject_override(p) == "Focus on R_V paper deadline"
