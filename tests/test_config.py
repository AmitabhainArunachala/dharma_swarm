"""Tests for central configuration (config.py).

Verifies that SwarmConfig holds the right defaults, respects bounds,
and that the module-level singleton is accessible.
"""

from __future__ import annotations

import os
import pytest
from pydantic import ValidationError

from dharma_swarm.config import (
    AgentConfig_,
    DEFAULT_CONFIG,
    LiveLoopConfig,
    OrchestratorConfig,
    SwarmConfig,
    SwarmManagerConfig,
    TUIConfig,
)


class TestOrchestratorConfig:
    def test_defaults(self) -> None:
        cfg = OrchestratorConfig()
        assert cfg.task_timeout_seconds == 300.0
        assert cfg.claim_timeout_seconds == 420.0
        assert cfg.max_retries == 0
        assert cfg.transient_failure_retry_limit == 2
        assert cfg.timeout_retry_growth_factor == 1.5
        assert cfg.max_timeout_retry_seconds == 900.0

    def test_bounds_reject_negative(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorConfig(task_timeout_seconds=-1)

    def test_bounds_reject_too_large(self) -> None:
        with pytest.raises(ValidationError):
            OrchestratorConfig(task_timeout_seconds=99999)


class TestAgentConfig:
    def test_defaults(self) -> None:
        cfg = AgentConfig_()
        assert cfg.heartbeat_threshold_seconds == 60.0
        assert cfg.subprocess_timeout_seconds == 300
        assert cfg.max_output_chars == 50_000

    def test_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AgentConfig_(heartbeat_threshold_seconds=1.0)  # below ge=5


class TestLiveLoopConfig:
    def test_defaults_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear env vars so defaults apply
        for var in ("DGC_SWARM_TICK", "DGC_PULSE_INTERVAL",
                     "DGC_EVOLUTION_INTERVAL", "DGC_HEALTH_INTERVAL",
                     "DGC_LIVING_INTERVAL", "DGC_MAX_DAILY"):
            monkeypatch.delenv(var, raising=False)
        cfg = LiveLoopConfig()
        assert cfg.swarm_tick_seconds == 60
        assert cfg.pulse_interval_seconds == 300
        assert cfg.evolution_interval_seconds == 600
        assert cfg.health_interval_seconds == 120
        assert cfg.living_interval_seconds == 180
        assert cfg.max_daily_tasks == 50


class TestSwarmManagerConfig:
    def test_defaults(self) -> None:
        cfg = SwarmManagerConfig()
        assert cfg.director_interval_ticks == 10
        assert cfg.living_interval_ticks == 3
        assert cfg.auto_rescue_scan_interval_seconds == 300.0
        assert cfg.auto_rescue_max_age_hours == 24.0
        assert cfg.auto_rescue_max_attempts == 1


class TestTUIConfig:
    def test_defaults(self) -> None:
        cfg = TUIConfig()
        assert cfg.log_buffer_size == 500
        assert cfg.refresh_rate_hz == 4.0
        assert cfg.scroll_threshold == 5


class TestSwarmConfig:
    def test_unified_access(self) -> None:
        cfg = SwarmConfig()
        assert cfg.orchestrator.task_timeout_seconds == 300.0
        assert cfg.agent.heartbeat_threshold_seconds == 60.0
        assert cfg.tui.log_buffer_size == 500

    def test_singleton_matches(self) -> None:
        assert DEFAULT_CONFIG.orchestrator.task_timeout_seconds == 300.0
        assert isinstance(DEFAULT_CONFIG, SwarmConfig)
