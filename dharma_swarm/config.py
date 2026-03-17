"""Central configuration — the nervous system of dharma_swarm.

Beer's S5 (identity): configuration IS system identity.  Every timeout,
interval, threshold, and bound lives here.  A single import replaces 50+
hardcoded values scattered across orchestrator, swarm, agent_runner, and
orchestrate_live.

Environment variables override defaults; Pydantic validates bounds.
"""

from __future__ import annotations

import os
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Orchestrator parameters
# ---------------------------------------------------------------------------

class OrchestratorConfig(BaseModel):
    """Timeouts, retries, and backoff for the task orchestrator."""

    tick_interval_seconds: float = Field(
        default=1.0, ge=0.1, le=60.0,
        description="Seconds between orchestrator ticks",
    )
    task_timeout_seconds: float = Field(
        default=300.0, ge=10.0, le=7200.0,
        description="Default timeout for a dispatched task",
    )
    claim_timeout_seconds: float = Field(
        default=420.0, ge=30.0, le=7200.0,
        description="Timeout for an agent to claim a task before requeue",
    )
    max_retries: int = Field(
        default=0, ge=0, le=10,
        description="Default retry count for failed tasks",
    )
    retry_backoff_seconds: float = Field(
        default=0.0, ge=0.0, le=300.0,
        description="Base backoff between retries",
    )
    transient_failure_retry_limit: int = Field(
        default=2, ge=0, le=10,
        description="Retries for transient failures (network, rate-limit)",
    )
    transient_failure_backoff_seconds: float = Field(
        default=30.0, ge=1.0, le=300.0,
        description="Backoff after transient failure",
    )
    long_timeout_retry_limit: int = Field(
        default=1, ge=0, le=5,
        description="Retries for long-timeout failures",
    )
    long_timeout_backoff_seconds: float = Field(
        default=15.0, ge=1.0, le=300.0,
        description="Backoff after long-timeout retry",
    )
    long_timeout_threshold_seconds: float = Field(
        default=120.0, ge=30.0, le=3600.0,
        description="Task duration above which timeout-retry logic kicks in",
    )
    timeout_retry_growth_factor: float = Field(
        default=1.5, ge=1.0, le=5.0,
        description="Multiplicative growth of timeout on retry",
    )
    max_timeout_retry_seconds: float = Field(
        default=900.0, ge=60.0, le=7200.0,
        description="Hard ceiling on retried timeout",
    )


# ---------------------------------------------------------------------------
# Agent runner parameters
# ---------------------------------------------------------------------------

class AgentConfig_(BaseModel):
    """Agent lifecycle parameters.  Underscore suffix avoids collision with
    models.AgentConfig (the per-agent spawn spec)."""

    heartbeat_threshold_seconds: float = Field(
        default=60.0, ge=5.0, le=600.0,
        description="Seconds before an agent is considered silent",
    )
    subprocess_timeout_seconds: int = Field(
        default=300, ge=30, le=3600,
        description="Default timeout for CLI subprocess providers",
    )
    max_output_chars: int = Field(
        default=50_000, ge=1000, le=500_000,
        description="Truncation limit for subprocess stdout",
    )


# ---------------------------------------------------------------------------
# Live orchestrator loop intervals
# ---------------------------------------------------------------------------

class LiveLoopConfig(BaseModel):
    """Intervals for the 5-system concurrent live orchestrator.

    All overridable via DGC_* environment variables.
    """

    swarm_tick_seconds: int = Field(
        default=int(os.environ.get("DGC_SWARM_TICK", "60")),
        ge=5, le=3600,
        description="Swarm tick interval",
    )
    pulse_interval_seconds: int = Field(
        default=int(os.environ.get("DGC_PULSE_INTERVAL", "300")),
        ge=30, le=7200,
        description="Pulse heartbeat interval",
    )
    evolution_interval_seconds: int = Field(
        default=int(os.environ.get("DGC_EVOLUTION_INTERVAL", "600")),
        ge=60, le=7200,
        description="Darwin Engine cycle interval",
    )
    health_interval_seconds: int = Field(
        default=int(os.environ.get("DGC_HEALTH_INTERVAL", "120")),
        ge=10, le=3600,
        description="Health monitor interval",
    )
    living_interval_seconds: int = Field(
        default=int(os.environ.get("DGC_LIVING_INTERVAL", "180")),
        ge=10, le=3600,
        description="Living layers (stigmergy, shakti, subconscious) interval",
    )
    max_daily_tasks: int = Field(
        default=int(os.environ.get("DGC_MAX_DAILY", "50")),
        ge=1, le=1000,
        description="Maximum tasks per day",
    )
    shutdown_wait_seconds: float = Field(
        default=60.0, ge=5.0, le=600.0,
        description="How long to wait for graceful shutdown",
    )


# ---------------------------------------------------------------------------
# TUI parameters
# ---------------------------------------------------------------------------

class TUIConfig(BaseModel):
    """TUI-specific display parameters."""

    log_buffer_size: int = Field(
        default=500, ge=50, le=10000,
        description="Maximum log lines kept in TUI buffer",
    )
    refresh_rate_hz: float = Field(
        default=4.0, ge=0.5, le=30.0,
        description="TUI refresh rate",
    )
    scroll_threshold: int = Field(
        default=5, ge=1, le=50,
        description="Lines from bottom before auto-scroll disengages",
    )


# ---------------------------------------------------------------------------
# Swarm manager parameters
# ---------------------------------------------------------------------------

class SwarmManagerConfig(BaseModel):
    """Parameters for SwarmManager internal scheduling."""

    director_interval_ticks: int = Field(
        default=10, ge=1, le=100,
        description="Run ThinkodynamicDirector every N ticks",
    )
    living_interval_ticks: int = Field(
        default=3, ge=1, le=50,
        description="Run living layers every N ticks",
    )
    auto_rescue_scan_interval_seconds: float = Field(
        default=300.0, ge=30.0, le=3600.0,
        description="Interval between automatic rescue scans",
    )
    auto_rescue_max_age_hours: float = Field(
        default=24.0, ge=1.0, le=168.0,
        description="Max age of a stuck task before auto-rescue",
    )
    auto_rescue_max_attempts: int = Field(
        default=1, ge=0, le=5,
        description="Maximum rescue attempts per task",
    )


# ---------------------------------------------------------------------------
# Unified config
# ---------------------------------------------------------------------------

class SwarmConfig(BaseModel):
    """Root configuration — the single source of truth.

    Beer's S5: this object IS system identity at the parameter level.
    """

    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    agent: AgentConfig_ = Field(default_factory=AgentConfig_)
    live_loop: LiveLoopConfig = Field(default_factory=LiveLoopConfig)
    tui: TUIConfig = Field(default_factory=TUIConfig)
    swarm: SwarmManagerConfig = Field(default_factory=SwarmManagerConfig)


# Module-level singleton — import this, not the class.
DEFAULT_CONFIG = SwarmConfig()
