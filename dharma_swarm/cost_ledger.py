"""Cost ledger — metabolic budget enforcement for the swarm.

Real stakes require real accounting. Without cost tracking, the metabolic
budget principle has no teeth. This module:

  1. Records per-invocation costs (tokens, USD, wall-clock)
  2. Tracks daily budget with configurable limits
  3. Enforces degradation: budget >80% → downgrade to cheaper models
  4. Hard stop at 100% budget — no silent overruns

Storage: ~/.dharma/costs/daily_ledger.jsonl (append-only, one entry per invocation)

Grounded in: SYNTHESIS.md P0 #3, Principle #2 (precariousness)
"""

from __future__ import annotations

import fcntl
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

COSTS_DIR = Path(os.getenv(
    "DHARMA_COSTS_DIR",
    str(Path.home() / ".dharma" / "costs"),
))


def _append_locked_jsonl(path: Path, line: str, *, encoding: str = "utf-8") -> None:
    """Append a single JSONL row durably under an advisory lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding=encoding) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Cost model (per-provider pricing, approximate)
# ---------------------------------------------------------------------------

# USD per 1M tokens (input/output), updated as needed
PRICING: dict[str, dict[str, float]] = {
    # OpenRouter
    "llama-3.3-70b-instruct": {"input": 0.35, "output": 0.40},
    "llama-3.1-405b-instruct": {"input": 2.00, "output": 2.00},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-r1": {"input": 0.55, "output": 2.19},
    "qwen-2.5-72b": {"input": 0.35, "output": 0.40},
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    "claude-haiku-4-20250514": {"input": 0.80, "output": 4.00},
    # Free tiers (Ollama Cloud, NVIDIA NIM)
    "ollama-cloud": {"input": 0.0, "output": 0.0},
    "nvidia-nim": {"input": 0.0, "output": 0.0},
    # Fallback
    "_default": {"input": 1.00, "output": 2.00},
}

# Degradation map: when budget is tight, suggest these cheaper alternatives
DEGRADATION_MAP: dict[str, str] = {
    "claude-opus-4-20250514": "claude-sonnet-4-20250514",
    "claude-sonnet-4-20250514": "claude-haiku-4-20250514",
    "claude-haiku-4-20250514": "llama-3.3-70b-instruct",
    "llama-3.1-405b-instruct": "llama-3.3-70b-instruct",
    "llama-3.3-70b-instruct": "deepseek-chat",
    "deepseek-r1": "deepseek-chat",
    "qwen-2.5-72b": "deepseek-chat",
}


# ---------------------------------------------------------------------------
# Invocation record
# ---------------------------------------------------------------------------

class InvocationCost(BaseModel):
    """A single LLM invocation cost record."""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str = ""
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    task_id: str = ""
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cost_usd", mode="before")
    @classmethod
    def _validate_cost_usd(cls, value: Any) -> Any:
        if value is None:
            return value
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return value
        if not math.isfinite(parsed):
            raise ValueError("cost_usd must be finite")
        return value


# ---------------------------------------------------------------------------
# Budget config
# ---------------------------------------------------------------------------

class BudgetConfig(BaseModel):
    """Daily budget configuration."""
    daily_limit_usd: float = 15.0  # $15/day default (garden daemon + agents)
    degradation_threshold: float = 0.80  # Degrade at 80%
    hard_stop_threshold: float = 1.0  # Stop at 100%
    per_invocation_max_tokens: int = 32_000  # Hard cap per call
    per_invocation_max_seconds: int = 120  # Wall-clock cap per call


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

class CostLedger:
    """Filesystem-backed cost tracking with budget enforcement.

    Append-only daily JSONL files. One file per day.
    Never deletes or overwrites — V7 immutability.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        budget: BudgetConfig | None = None,
    ) -> None:
        self.base_dir = base_dir or COSTS_DIR
        self.budget = budget or BudgetConfig()
        self._today_cache: list[InvocationCost] | None = None
        self._today_date: str = ""

    def _ledger_path(self, date_str: str | None = None) -> Path:
        """Path to the daily ledger file."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.base_dir / f"{date_str}.jsonl"

    def _ledger_date_for_invocation(self, invocation: InvocationCost) -> str:
        """Resolve the UTC ledger date for an invocation timestamp.

        The ledger is partitioned by UTC day. When callers backfill records or
        finish a long-running invocation after midnight, using the wall clock at
        write time misattributes cost to the wrong budget window.
        """
        timestamp = str(invocation.timestamp or "").strip()
        if timestamp:
            normalized = timestamp.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d")
            except ValueError:
                logger.warning("Invalid invocation timestamp %r; falling back to current UTC day", timestamp)
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost for a given model and token counts."""
        pricing = PRICING.get(model, PRICING["_default"])
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
        return round(cost, 6)

    def record(self, invocation: InvocationCost) -> None:
        """Record an invocation cost. Append-only."""
        # Auto-calculate cost if not set
        if invocation.cost_usd == 0.0 and (invocation.tokens_in or invocation.tokens_out):
            invocation.cost_usd = self.estimate_cost(
                invocation.model, invocation.tokens_in, invocation.tokens_out
            )
        if not math.isfinite(invocation.cost_usd):
            raise ValueError("Invocation cost_usd must be finite before recording")

        path = self._ledger_path(self._ledger_date_for_invocation(invocation))
        _append_locked_jsonl(path, invocation.model_dump_json() + "\n")

        # Invalidate cache
        self._today_cache = None

        logger.debug(
            "Cost recorded: %s %s $%.4f (%d in, %d out)",
            invocation.agent, invocation.model,
            invocation.cost_usd, invocation.tokens_in, invocation.tokens_out,
        )

    def _load_today(self) -> list[InvocationCost]:
        """Load today's invocations (cached)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._today_cache is not None and self._today_date == today:
            return self._today_cache

        path = self._ledger_path(today)
        entries: list[InvocationCost] = []
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = InvocationCost.model_validate_json(line)
                except Exception:
                    continue
                if not math.isfinite(entry.cost_usd):
                    logger.warning("Skipping non-finite cost entry in %s", path)
                    continue
                entries.append(entry)

        self._today_cache = entries
        self._today_date = today
        return entries

    def daily_total(self) -> float:
        """Total cost for today in USD."""
        return sum(e.cost_usd for e in self._load_today())

    def daily_invocation_count(self) -> int:
        """Number of invocations today."""
        return len(self._load_today())

    def budget_remaining(self) -> float:
        """Remaining budget for today in USD."""
        return max(0.0, self.budget.daily_limit_usd - self.daily_total())

    def budget_utilization(self) -> float:
        """Budget utilization as fraction (0.0 to 1.0+)."""
        if self.budget.daily_limit_usd <= 0:
            return 0.0
        return self.daily_total() / self.budget.daily_limit_usd

    def should_degrade(self) -> bool:
        """True when budget utilization exceeds degradation threshold."""
        return self.budget_utilization() >= self.budget.degradation_threshold

    def should_stop(self) -> bool:
        """True when budget is exhausted."""
        return self.budget_utilization() >= self.budget.hard_stop_threshold

    def suggest_model(self, requested_model: str) -> str:
        """Suggest a cheaper model if budget requires degradation.

        Returns the requested model if budget is healthy, or a cheaper
        alternative if degradation is needed.
        """
        if not self.should_degrade():
            return requested_model

        # Walk the degradation chain
        degraded = DEGRADATION_MAP.get(requested_model)
        if degraded:
            logger.info(
                "Budget degradation: %s → %s (%.0f%% utilized)",
                requested_model, degraded,
                self.budget_utilization() * 100,
            )
            return degraded

        return requested_model

    def pre_flight_check(
        self, model: str, estimated_tokens_in: int, estimated_tokens_out: int
    ) -> dict[str, Any]:
        """Pre-flight budget check before making an LLM call.

        Returns a dict with:
          - allowed: bool
          - reason: str (if not allowed)
          - suggested_model: str (possibly degraded)
          - estimated_cost: float
          - budget_remaining: float
        """
        if self.should_stop():
            return {
                "allowed": False,
                "reason": f"Daily budget exhausted (${self.daily_total():.2f} / ${self.budget.daily_limit_usd:.2f})",
                "suggested_model": model,
                "estimated_cost": 0.0,
                "budget_remaining": 0.0,
            }

        suggested = self.suggest_model(model)
        estimated = self.estimate_cost(suggested, estimated_tokens_in, estimated_tokens_out)
        remaining = self.budget_remaining()

        if estimated > remaining:
            return {
                "allowed": False,
                "reason": f"Estimated cost ${estimated:.4f} exceeds remaining ${remaining:.4f}",
                "suggested_model": suggested,
                "estimated_cost": estimated,
                "budget_remaining": remaining,
            }

        return {
            "allowed": True,
            "reason": "",
            "suggested_model": suggested,
            "estimated_cost": estimated,
            "budget_remaining": remaining,
        }

    def summary(self) -> dict[str, Any]:
        """Return a summary of today's spending."""
        entries = self._load_today()
        by_model: dict[str, float] = {}
        by_agent: dict[str, float] = {}
        for e in entries:
            by_model[e.model] = by_model.get(e.model, 0) + e.cost_usd
            by_agent[e.agent] = by_agent.get(e.agent, 0) + e.cost_usd

        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_usd": round(self.daily_total(), 4),
            "invocations": len(entries),
            "budget_limit": self.budget.daily_limit_usd,
            "budget_remaining": round(self.budget_remaining(), 4),
            "utilization_pct": round(self.budget_utilization() * 100, 1),
            "degraded": self.should_degrade(),
            "stopped": self.should_stop(),
            "by_model": {k: round(v, 4) for k, v in sorted(by_model.items(), key=lambda x: -x[1])},
            "by_agent": {k: round(v, 4) for k, v in sorted(by_agent.items(), key=lambda x: -x[1])},
        }
