"""Cost tracking for LLM calls across all providers.

Logs every call with provider, model, tokens, estimated cost, and task context.
Appended to ~/.dharma/cost_log.jsonl for analysis.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_DIR = Path.home() / ".dharma"
_COST_LOG = _STATE_DIR / "cost_log.jsonl"

# Approximate cost per million tokens (input) by model pattern.
# These are rough estimates for budgeting, not billing.
_COST_PER_M_INPUT: dict[str, float] = {
    # T0 — Ollama Cloud
    "kimi-k2.5": 0.0,
    "glm-5": 0.0,
    # T1 — Free/cheap
    "llama-3.3-70b-instruct:free": 0.0,
    "mistral-small": 0.10,
    "llama-3.3-70b": 0.50,
    # T2 — Premium
    "gpt-4o": 2.50,
    "claude-sonnet-4-6": 3.00,
    "gpt-4.1": 2.00,
    # T3 — Frontier
    "claude-opus-4-6": 15.00,
    "gpt-5": 10.00,
    "codex": 15.00,
    "claude-code": 15.00,
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost based on model and token counts."""
    model_lower = model.lower()
    rate = 0.0
    for pattern, cost in _COST_PER_M_INPUT.items():
        if pattern in model_lower:
            rate = cost
            break
    # Output tokens typically cost 3-5x input; use 3x as conservative estimate.
    input_cost = (input_tokens / 1_000_000) * rate
    output_cost = (output_tokens / 1_000_000) * rate * 3.0
    return round(input_cost + output_cost, 6)


@dataclass
class CostEntry:
    timestamp: float
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    task_id: str = ""
    agent_name: str = ""
    tier: str = ""


def _parse_finite_float(value: object) -> float | None:
    """Return a finite float or None for malformed replayed values."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def log_cost(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    task_id: str = "",
    agent_name: str = "",
    tier: str = "",
) -> CostEntry:
    """Log a cost entry to the JSONL file."""
    entry = CostEntry(
        timestamp=time.time(),
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimate_cost(model, input_tokens, output_tokens),
        task_id=task_id,
        agent_name=agent_name,
        tier=tier,
    )
    try:
        _COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_COST_LOG, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
    except Exception as exc:
        logger.warning("Failed to log cost entry: %s", exc)
    return entry


def read_cost_log(since_hours: float = 24.0, state_dir: Path | None = None) -> list[CostEntry]:
    """Read cost entries from the last N hours."""
    cost_log = (state_dir / "cost_log.jsonl") if state_dir is not None else _COST_LOG
    if not cost_log.exists():
        return []
    cutoff = time.time() - (since_hours * 3600)
    entries = []
    try:
        with open(cost_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    timestamp = _parse_finite_float(data.get("timestamp"))
                    cost = _parse_finite_float(data.get("estimated_cost_usd"))
                    if timestamp is None or cost is None or timestamp < cutoff:
                        continue
                    data["timestamp"] = timestamp
                    data["estimated_cost_usd"] = cost
                    entries.append(CostEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
    except Exception as exc:
        logger.warning("Failed to read cost log: %s", exc)
    return entries


def cost_summary(since_hours: float = 24.0) -> str:
    """Return a human-readable cost summary."""
    entries = read_cost_log(since_hours=since_hours)
    if not entries:
        return f"No LLM calls in the last {since_hours:.0f}h."

    total_cost = sum(e.estimated_cost_usd for e in entries)
    total_input = sum(e.input_tokens for e in entries)
    total_output = sum(e.output_tokens for e in entries)

    # By tier
    by_tier: dict[str, list[CostEntry]] = {}
    for e in entries:
        tier = e.tier or "unknown"
        by_tier.setdefault(tier, []).append(e)

    lines = [
        f"Cost summary (last {since_hours:.0f}h): {len(entries)} calls, ${total_cost:.4f}",
        f"  Tokens: {total_input:,} in / {total_output:,} out",
        "",
        "  By tier:",
    ]
    for tier in sorted(by_tier.keys()):
        tier_entries = by_tier[tier]
        tier_cost = sum(e.estimated_cost_usd for e in tier_entries)
        pct = (len(tier_entries) / len(entries) * 100) if entries else 0
        lines.append(f"    {tier}: {len(tier_entries)} calls ({pct:.0f}%), ${tier_cost:.4f}")

    return "\n".join(lines)


__all__ = [
    "CostEntry",
    "cost_summary",
    "log_cost",
    "read_cost_log",
]
