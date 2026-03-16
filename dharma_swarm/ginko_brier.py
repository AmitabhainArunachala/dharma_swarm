"""Ginko Brier Scoring — prediction tracking with SATYA-enforced honesty.

Every directional prediction is recorded, timestamped, and scored.
SATYA gate: ALL predictions are published, including misses.

Brier score = mean((probability - outcome)^2)
  - Perfect calibration: 0.0
  - Random binary: 0.25
  - Target: < 0.125 across 500+ predictions before live capital

Persistence: ~/.dharma/ginko/predictions.jsonl
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
PREDICTIONS_FILE = GINKO_DIR / "predictions.jsonl"
DASHBOARD_FILE = GINKO_DIR / "brier_dashboard.json"
NOTIFICATIONS_FILE = GINKO_DIR / "resolved_notifications.jsonl"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    GINKO_DIR.mkdir(parents=True, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DATA MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class Prediction:
    """A directional prediction with probability and resolution."""
    id: str
    question: str
    probability: float          # 0.0 to 1.0 — predicted probability of YES
    category: str               # "macro", "equity", "crypto", "policy", "general"
    source: str                 # "financial-intel", "quant-analyst", "regime-model"
    created_at: str
    resolve_by: str             # ISO timestamp — when this should be resolved
    resolved_at: str | None = None
    outcome: float | None = None  # 1.0 = YES happened, 0.0 = NO
    brier_score: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class BrierDashboard:
    """Aggregate Brier score statistics."""
    total_predictions: int
    resolved_predictions: int
    pending_predictions: int
    overall_brier: float | None      # Mean Brier score across all resolved
    brier_by_category: dict[str, float]
    brier_by_source: dict[str, float]
    calibration_bins: list[dict[str, float]]  # 10 bins of predicted vs actual
    last_updated: str
    edge_validated: bool         # True if Brier < 0.125 across 500+ predictions
    win_rate: float | None       # Fraction where outcome matched (prob > 0.5 → 1.0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PREDICTION CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def record_prediction(
    question: str,
    probability: float,
    resolve_by: str,
    category: str = "general",
    source: str = "financial-intel",
    metadata: dict[str, Any] | None = None,
) -> Prediction:
    """Record a new prediction. SATYA: once recorded, cannot be deleted.

    Args:
        question: The yes/no question being predicted.
        probability: Predicted probability of YES (0.0 to 1.0).
        resolve_by: ISO timestamp for when this should be resolved.
        category: Prediction category for tracking.
        source: Which agent/model generated this prediction.
        metadata: Additional context (regime, signals, etc).

    Returns:
        The recorded Prediction.

    Raises:
        ValueError: If probability is outside [0, 1].
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be [0, 1], got {probability}")

    pred = Prediction(
        id=uuid.uuid4().hex[:12],
        question=question,
        probability=probability,
        category=category,
        source=source,
        created_at=_utc_now().isoformat(),
        resolve_by=resolve_by,
        metadata=metadata,
    )

    _ensure_dirs()
    with open(PREDICTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(pred), default=str) + "\n")

    logger.info(
        "Prediction recorded: %s (p=%.2f, resolve_by=%s)",
        question[:50], probability, resolve_by,
    )
    return pred


def resolve_prediction(
    prediction_id: str,
    outcome: float,
) -> Prediction | None:
    """Resolve a prediction with actual outcome.

    Args:
        prediction_id: The prediction ID to resolve.
        outcome: 1.0 = YES happened, 0.0 = NO.

    Returns:
        Updated Prediction or None if not found.
    """
    if outcome not in (0.0, 1.0):
        raise ValueError(f"outcome must be 0.0 or 1.0, got {outcome}")

    predictions = _load_all_predictions()
    updated = None

    for pred in predictions:
        if pred.id == prediction_id and pred.outcome is None:
            pred.outcome = outcome
            pred.resolved_at = _utc_now().isoformat()
            pred.brier_score = (pred.probability - outcome) ** 2
            updated = pred
            break

    if updated:
        _save_all_predictions(predictions)
        _update_dashboard()
        logger.info(
            "Prediction resolved: %s → %s (Brier=%.4f)",
            prediction_id, "YES" if outcome == 1.0 else "NO", updated.brier_score,
        )

    return updated


def get_prediction(prediction_id: str) -> Prediction | None:
    """Get a single prediction by ID."""
    for pred in _load_all_predictions():
        if pred.id == prediction_id:
            return pred
    return None


def get_pending_predictions() -> list[Prediction]:
    """Get all unresolved predictions."""
    return [p for p in _load_all_predictions() if p.outcome is None]


def get_overdue_predictions() -> list[Prediction]:
    """Get predictions past their resolve_by date that haven't been resolved."""
    now = _utc_now().isoformat()
    return [
        p for p in _load_all_predictions()
        if p.outcome is None and p.resolve_by < now
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BRIER SCORE COMPUTATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def compute_brier_score(predictions: list[Prediction] | None = None) -> float | None:
    """Compute overall Brier score across all resolved predictions.

    Brier = (1/N) * sum((probability - outcome)^2)

    Returns:
        Brier score or None if no resolved predictions.
    """
    if predictions is None:
        predictions = _load_all_predictions()

    resolved = [p for p in predictions if p.outcome is not None]
    if not resolved:
        return None

    scores = [(p.probability - (p.outcome or 0.0)) ** 2 for p in resolved]
    return sum(scores) / len(scores)


def compute_brier_by_group(
    group_key: str = "category",
    predictions: list[Prediction] | None = None,
) -> dict[str, float]:
    """Compute Brier score grouped by category or source.

    Args:
        group_key: "category" or "source".
        predictions: Optional pre-loaded predictions.

    Returns:
        Dict of group_name → Brier score.
    """
    if predictions is None:
        predictions = _load_all_predictions()

    resolved = [p for p in predictions if p.outcome is not None]
    groups: dict[str, list[float]] = {}

    for p in resolved:
        key = getattr(p, group_key, "unknown")
        groups.setdefault(key, []).append((p.probability - (p.outcome or 0.0)) ** 2)

    return {k: sum(v) / len(v) for k, v in groups.items()}


def compute_calibration(
    predictions: list[Prediction] | None = None,
    n_bins: int = 10,
) -> list[dict[str, float]]:
    """Compute calibration curve (predicted vs actual in bins).

    Returns:
        List of dicts with bin_center, predicted_mean, actual_mean, count.
    """
    if predictions is None:
        predictions = _load_all_predictions()

    resolved = [p for p in predictions if p.outcome is not None]
    if not resolved:
        return []

    bins: list[list[Prediction]] = [[] for _ in range(n_bins)]
    for p in resolved:
        idx = min(int(p.probability * n_bins), n_bins - 1)
        bins[idx].append(p)

    calibration = []
    for i, bin_preds in enumerate(bins):
        if not bin_preds:
            continue
        calibration.append({
            "bin_center": (i + 0.5) / n_bins,
            "predicted_mean": sum(p.probability for p in bin_preds) / len(bin_preds),
            "actual_mean": sum((p.outcome or 0.0) for p in bin_preds) / len(bin_preds),
            "count": float(len(bin_preds)),
        })

    return calibration


def compute_win_rate(predictions: list[Prediction] | None = None) -> float | None:
    """Compute win rate: fraction where direction was correct.

    A prediction "wins" if:
      - probability > 0.5 and outcome == 1.0, or
      - probability < 0.5 and outcome == 0.0
    """
    if predictions is None:
        predictions = _load_all_predictions()

    resolved = [p for p in predictions if p.outcome is not None]
    if not resolved:
        return None

    wins = sum(
        1 for p in resolved
        if (p.probability > 0.5 and p.outcome == 1.0)
        or (p.probability < 0.5 and p.outcome == 0.0)
        or (p.probability == 0.5)  # toss-up counts as half
    )
    return wins / len(resolved)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DASHBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def build_dashboard() -> BrierDashboard:
    """Build the complete Brier score dashboard."""
    predictions = _load_all_predictions()
    resolved = [p for p in predictions if p.outcome is not None]
    pending = [p for p in predictions if p.outcome is None]

    overall = compute_brier_score(predictions)
    by_category = compute_brier_by_group("category", predictions)
    by_source = compute_brier_by_group("source", predictions)
    calibration = compute_calibration(predictions)
    win_rate = compute_win_rate(predictions)

    edge_validated = (
        overall is not None
        and overall < 0.125
        and len(resolved) >= 500
    )

    return BrierDashboard(
        total_predictions=len(predictions),
        resolved_predictions=len(resolved),
        pending_predictions=len(pending),
        overall_brier=overall,
        brier_by_category=by_category,
        brier_by_source=by_source,
        calibration_bins=calibration,
        last_updated=_utc_now().isoformat(),
        edge_validated=edge_validated,
        win_rate=win_rate,
    )


def _update_dashboard() -> None:
    """Rebuild and persist the dashboard."""
    dashboard = build_dashboard()
    _ensure_dirs()
    try:
        DASHBOARD_FILE.write_text(
            json.dumps(asdict(dashboard), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Failed to persist dashboard: %s", e)


def load_dashboard() -> BrierDashboard | None:
    """Load the latest dashboard from disk."""
    if not DASHBOARD_FILE.exists():
        return None
    try:
        data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
        return BrierDashboard(**data)
    except Exception as e:
        logger.error("Failed to load dashboard: %s", e)
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EDGE VALIDATION (SATYA gate)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_edge_validation() -> dict[str, Any]:
    """Check if edge is validated for live trading.

    Requires:
      - Brier < 0.125
      - 500+ resolved predictions
      - Win rate > 55%

    Returns:
        Dict with validation status and reasons.
    """
    predictions = _load_all_predictions()
    resolved = [p for p in predictions if p.outcome is not None]

    result: dict[str, Any] = {
        "validated": False,
        "reasons": [],
        "metrics": {},
    }

    n = len(resolved)
    result["metrics"]["resolved_count"] = n

    if n < 500:
        result["reasons"].append(f"Need 500+ predictions, have {n}")

    brier = compute_brier_score(predictions)
    result["metrics"]["brier_score"] = brier
    if brier is None or brier >= 0.125:
        result["reasons"].append(
            f"Brier score {brier:.4f} >= 0.125 threshold"
            if brier else "No Brier score yet"
        )

    win_rate = compute_win_rate(predictions)
    result["metrics"]["win_rate"] = win_rate
    if win_rate is None or win_rate < 0.55:
        result["reasons"].append(
            f"Win rate {win_rate:.2%} < 55% threshold"
            if win_rate else "No win rate yet"
        )

    if not result["reasons"]:
        result["validated"] = True

    return result


def format_dashboard_report() -> str:
    """Format dashboard as human-readable report (for Substack/reports)."""
    dashboard = build_dashboard()

    lines = [
        "Shakti Ginko — Prediction Dashboard",
        "=" * 40,
        f"Total predictions: {dashboard.total_predictions}",
        f"Resolved: {dashboard.resolved_predictions}",
        f"Pending: {dashboard.pending_predictions}",
        "",
    ]

    if dashboard.overall_brier is not None:
        lines.append(f"Overall Brier score: {dashboard.overall_brier:.4f}")
        lines.append(f"  (Polymarket baseline: 0.058)")
        lines.append(f"  (Target: < 0.125)")
    else:
        lines.append("Overall Brier score: N/A (no resolved predictions)")

    if dashboard.win_rate is not None:
        lines.append(f"Win rate: {dashboard.win_rate:.1%}")

    lines.append(f"\nEdge validated: {'YES' if dashboard.edge_validated else 'NO'}")

    if dashboard.brier_by_category:
        lines.append("\nBy category:")
        for cat, score in sorted(dashboard.brier_by_category.items()):
            lines.append(f"  {cat}: {score:.4f}")

    if dashboard.brier_by_source:
        lines.append("\nBy source:")
        for src, score in sorted(dashboard.brier_by_source.items()):
            lines.append(f"  {src}: {score:.4f}")

    lines.append(f"\nLast updated: {dashboard.last_updated}")
    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESOLUTION NOTIFICATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def log_resolution_notification(
    prediction: dict[str, Any],
    outcome: float,
    brier_score: float,
) -> None:
    """Append a resolution notification to the JSONL log.

    Always writes to ~/.dharma/ginko/resolved_notifications.jsonl regardless
    of whether a webhook is configured. Provides a durable audit trail for
    every resolution event.

    Args:
        prediction: Dict representation of the resolved prediction.
        outcome: The actual outcome (1.0 = YES, 0.0 = NO).
        brier_score: The Brier score for this prediction.
    """
    _ensure_dirs()
    entry = {
        "question": prediction.get("question", ""),
        "probability": prediction.get("probability"),
        "outcome": outcome,
        "brier_score": brier_score,
        "prediction_id": prediction.get("prediction_id") or prediction.get("id", ""),
        "timestamp": _utc_now().isoformat(),
    }
    try:
        with open(NOTIFICATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        logger.info(
            "Resolution notification logged: %s (Brier=%.4f)",
            entry["question"][:50],
            brier_score,
        )
    except Exception as e:
        logger.error("Failed to log resolution notification: %s", e)


async def webhook_notify(
    prediction: dict[str, Any],
    outcome: float,
    brier_score: float,
) -> bool:
    """Send a resolution notification to the configured webhook URL.

    Reads GINKO_WEBHOOK_URL from the environment. If not set, returns False
    without attempting any network call. On success, returns True. On any
    error (network, HTTP status, timeout), logs the failure and returns False.

    Args:
        prediction: Dict representation of the resolved prediction.
        outcome: The actual outcome (1.0 = YES, 0.0 = NO).
        brier_score: The Brier score for this prediction.

    Returns:
        True if the webhook was sent successfully, False otherwise.
    """
    webhook_url = os.environ.get("GINKO_WEBHOOK_URL")
    if not webhook_url:
        logger.debug("GINKO_WEBHOOK_URL not set, skipping webhook")
        return False

    running_brier = compute_brier_score()

    payload = {
        "prediction_question": prediction.get("question", ""),
        "probability": prediction.get("probability"),
        "outcome": outcome,
        "brier_score": brier_score,
        "running_brier": running_brier,
        "timestamp": _utc_now().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info(
            "Webhook sent for '%s' -> %s (HTTP %d)",
            prediction.get("question", "")[:50],
            webhook_url,
            response.status_code,
        )
        return True
    except httpx.HTTPStatusError as e:
        logger.error(
            "Webhook HTTP error for '%s': %s",
            prediction.get("question", "")[:50],
            e,
        )
        return False
    except Exception as e:
        logger.error(
            "Webhook failed for '%s': %s",
            prediction.get("question", "")[:50],
            e,
        )
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTO-RESOLUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def extract_prediction_target(question: str) -> dict[str, Any] | None:
    """Extract prediction target from question text.

    Parses questions like:
    - "Will SPY close higher tomorrow?"
    - "Will AAPL be above $200 by March 25?"
    - "Will BTC reach $70000 this week?"

    Args:
        question: The yes/no prediction question.

    Returns:
        Dict with ticker, direction, target_price (optional), or None if
        the question cannot be parsed into a resolvable target.
    """
    import re

    question_upper = question.upper()

    # Common ticker patterns
    ticker_match = re.search(r"\b([A-Z]{1,5})\b", question_upper)
    ticker = ticker_match.group(1) if ticker_match else None

    # Skip common non-ticker words
    skip_words = {
        "WILL", "THE", "THIS", "THAT", "WHAT", "HOW", "CAN",
        "DOES", "ARE", "HAS", "FOR", "AND", "NOT", "BE",
    }
    if ticker in skip_words:
        # Try to find next ticker-like word
        for match in re.finditer(r"\b([A-Z]{1,5})\b", question_upper):
            if match.group(1) not in skip_words:
                ticker = match.group(1)
                break

    # Direction
    direction: str | None = None
    question_lower = question.lower()
    if any(w in question_lower for w in [
        "higher", "above", "up", "rise", "increase", "reach", "bull",
    ]):
        direction = "higher"
    elif any(w in question_lower for w in [
        "lower", "below", "down", "fall", "decrease", "drop", "bear",
    ]):
        direction = "lower"

    # Target price
    price_match = re.search(r"\$?([\d,]+(?:\.\d+)?)", question)
    target_price = (
        float(price_match.group(1).replace(",", ""))
        if price_match
        else None
    )

    if not ticker or not direction:
        return None

    return {
        "ticker": ticker,
        "direction": direction,
        "target_price": target_price,
    }


async def auto_resolve_predictions() -> list[dict[str, Any]]:
    """Auto-resolve overdue predictions against real market data.

    For each pending prediction past resolve_by:
    1. Parse the question for ticker + direction.
    2. Fetch current price from finnhub via ginko_data.
    3. Resolve as 1.0 (YES) or 0.0 (NO) based on actual price movement.

    Returns:
        List of resolved prediction dicts with resolution details.
    """
    overdue = get_overdue_predictions()
    if not overdue:
        return []

    resolved_list: list[dict[str, Any]] = []

    for pred in overdue:
        target = extract_prediction_target(pred.question)
        if not target:
            logger.warning(
                "Cannot parse prediction target: %s", pred.question[:50],
            )
            continue

        ticker = target["ticker"]
        direction = target["direction"]

        # Try to get current price
        try:
            from dharma_swarm.ginko_data import fetch_stock_quote

            quote = await fetch_stock_quote(ticker)
            if not quote:
                logger.warning(
                    "No price data for %s, skipping auto-resolve", ticker,
                )
                continue

            current_price = quote.current_price
            previous_close = quote.previous_close

            # Determine outcome
            if direction == "higher":
                outcome = 1.0 if current_price > previous_close else 0.0
            else:  # lower
                outcome = 1.0 if current_price < previous_close else 0.0

            # Check against target price if specified
            if target.get("target_price"):
                tp = target["target_price"]
                if direction == "higher":
                    outcome = 1.0 if current_price >= tp else 0.0
                else:
                    outcome = 1.0 if current_price <= tp else 0.0

            # Resolve
            resolved = resolve_prediction(pred.id, outcome)
            if resolved:
                resolution_info: dict[str, Any] = {
                    "prediction_id": pred.id,
                    "question": pred.question,
                    "probability": pred.probability,
                    "outcome": outcome,
                    "brier_score": resolved.brier_score,
                    "ticker": ticker,
                    "current_price": current_price,
                    "previous_close": previous_close,
                    "direction": direction,
                }
                resolved_list.append(resolution_info)

                # Notification: always log, optionally webhook
                log_resolution_notification(
                    resolution_info, outcome, resolved.brier_score,
                )
                if os.environ.get("GINKO_WEBHOOK_URL"):
                    await webhook_notify(
                        resolution_info, outcome, resolved.brier_score,
                    )
        except ImportError:
            logger.warning("ginko_data not available for auto-resolve")
            break
        except Exception as e:
            logger.error("Auto-resolve failed for %s: %s", pred.id, e)

    return resolved_list


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENCE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _load_all_predictions() -> list[Prediction]:
    """Load all predictions from JSONL file."""
    _ensure_dirs()
    if not PREDICTIONS_FILE.exists():
        return []

    predictions = []
    try:
        for line in PREDICTIONS_FILE.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                data = json.loads(line)
                predictions.append(Prediction(**data))
    except Exception as e:
        logger.error("Failed to load predictions: %s", e)

    return predictions


def _save_all_predictions(predictions: list[Prediction]) -> None:
    """Rewrite all predictions to JSONL (used after resolution)."""
    _ensure_dirs()
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        for pred in predictions:
            f.write(json.dumps(asdict(pred), default=str) + "\n")
