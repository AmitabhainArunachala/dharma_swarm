"""Loop detector — 4-signal detection for stuck autonomous agents.

Production evidence (Agent 7 research): agents get stuck in loops that
waste resources and produce no value. Four independent signals detect
this reliably:

  1. Action signature repetition (same action hash 3+ times in window)
  2. Error pattern matching (80%+ same error type in last 5 actions)
  3. Semantic similarity (keyword overlap > threshold)
  4. Global resource limits (total actions in window exceeds budget)

Grounded in: SYNTHESIS.md P1 #9, Principle #10 (context rots)
Sources: JZ Tan error patterns, 220 stuck loop analysis, Devin agents 101
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LoopSignal(str, Enum):
    """Which signal detected the loop."""
    SIGNATURE_REPEAT = "signature_repeat"
    ERROR_PATTERN = "error_pattern"
    SEMANTIC_REPEAT = "semantic_repeat"
    RESOURCE_LIMIT = "resource_limit"


class LoopSeverity(str, Enum):
    """How bad is the loop."""
    NONE = "none"
    WARNING = "warning"  # 1 signal
    LIKELY = "likely"    # 2 signals
    CERTAIN = "certain"  # 3+ signals


@dataclass
class ActionRecord:
    """A recorded action for loop analysis."""
    timestamp: str = ""
    action_type: str = ""  # e.g., "write_file", "run_test", "llm_call"
    target: str = ""       # e.g., file path, test name
    result: str = ""       # "success", "error", "timeout"
    error_type: str = ""   # e.g., "SyntaxError", "TimeoutError"
    keywords: list[str] = field(default_factory=list)
    tokens_used: int = 0
    signature: str = ""    # computed hash

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.signature:
            raw = f"{self.action_type}:{self.target}:{self.result}"
            self.signature = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class LoopDetection:
    """Result of loop detection check."""
    detected: bool = False
    severity: LoopSeverity = LoopSeverity.NONE
    signals: list[LoopSignal] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""

    @property
    def should_break(self) -> bool:
        """True if the loop is bad enough to warrant breaking execution."""
        return self.severity in (LoopSeverity.LIKELY, LoopSeverity.CERTAIN)


class LoopDetector:
    """Sliding-window loop detector with 4 independent signals.

    Usage::

        detector = LoopDetector()

        # After each action:
        detector.record(ActionRecord(
            action_type="write_file",
            target="foo.py",
            result="success",
        ))

        # Before next action:
        result = detector.check()
        if result.should_break:
            # Break the loop, checkpoint state, fresh start
            ...
    """

    def __init__(
        self,
        window_size: int = 20,
        signature_threshold: int = 3,
        error_threshold: float = 0.80,
        semantic_threshold: float = 0.60,
        resource_limit: int = 50,
        persist_path: Path | None = None,
    ) -> None:
        self.window: deque[ActionRecord] = deque(maxlen=window_size)
        self.signature_threshold = signature_threshold
        self.error_threshold = error_threshold
        self.semantic_threshold = semantic_threshold
        self.resource_limit = resource_limit
        self.total_actions: int = 0
        self.total_tokens: int = 0
        self._persist_path = persist_path

    def record(self, action: ActionRecord) -> None:
        """Record an action into the sliding window."""
        self.window.append(action)
        self.total_actions += 1
        self.total_tokens += action.tokens_used
        # Auto-persist every 10 actions
        if self._persist_path and self.total_actions % 10 == 0:
            self.persist()

    def check(self) -> LoopDetection:
        """Run all 4 detection signals against the current window.

        Returns a LoopDetection with combined severity.
        """
        if len(self.window) < 3:
            return LoopDetection()

        signals: list[LoopSignal] = []
        details: dict[str, Any] = {}

        # Signal 1: Action signature repetition
        sig_result = self._check_signature_repeat()
        if sig_result:
            signals.append(LoopSignal.SIGNATURE_REPEAT)
            details["signature"] = sig_result

        # Signal 2: Error pattern
        err_result = self._check_error_pattern()
        if err_result:
            signals.append(LoopSignal.ERROR_PATTERN)
            details["error"] = err_result

        # Signal 3: Semantic similarity
        sem_result = self._check_semantic_repeat()
        if sem_result:
            signals.append(LoopSignal.SEMANTIC_REPEAT)
            details["semantic"] = sem_result

        # Signal 4: Global resource limits
        res_result = self._check_resource_limits()
        if res_result:
            signals.append(LoopSignal.RESOURCE_LIMIT)
            details["resource"] = res_result

        # Compute severity
        n = len(signals)
        if n == 0:
            severity = LoopSeverity.NONE
        elif n == 1:
            severity = LoopSeverity.WARNING
        elif n == 2:
            severity = LoopSeverity.LIKELY
        else:
            severity = LoopSeverity.CERTAIN

        # Generate recommendation
        recommendation = ""
        if severity == LoopSeverity.WARNING:
            recommendation = "Possible loop detected. Monitor closely."
        elif severity == LoopSeverity.LIKELY:
            recommendation = "Loop likely. Checkpoint state and consider alternative approach."
        elif severity == LoopSeverity.CERTAIN:
            recommendation = "Loop confirmed. BREAK: checkpoint state, restart with fresh context."

        detected = severity != LoopSeverity.NONE

        if detected:
            logger.warning(
                "Loop detected: severity=%s signals=%s",
                severity.value,
                [s.value for s in signals],
            )

        return LoopDetection(
            detected=detected,
            severity=severity,
            signals=signals,
            details=details,
            recommendation=recommendation,
        )

    def reset(self) -> None:
        """Reset the detector (e.g., after a successful fresh start)."""
        self.window.clear()
        self.total_actions = 0
        self.total_tokens = 0

    # ---- Persistence ----

    def persist(self) -> None:
        """Write current window to JSONL file for cross-task memory."""
        if self._persist_path is None:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persist_path, "w") as f:
                for action in self.window:
                    record = {
                        "timestamp": action.timestamp,
                        "action_type": action.action_type,
                        "target": action.target,
                        "result": action.result,
                        "error_type": action.error_type,
                        "keywords": action.keywords,
                        "tokens_used": action.tokens_used,
                        "signature": action.signature,
                    }
                    f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error("LoopDetector persist failed: %s", e)

    def load(self) -> bool:
        """Load persisted window from JSONL file. Returns True if loaded."""
        if self._persist_path is None or not self._persist_path.exists():
            return False
        try:
            loaded = 0
            with open(self._persist_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    action = ActionRecord(
                        timestamp=data.get("timestamp", ""),
                        action_type=data.get("action_type", ""),
                        target=data.get("target", ""),
                        result=data.get("result", ""),
                        error_type=data.get("error_type", ""),
                        keywords=data.get("keywords", []),
                        tokens_used=data.get("tokens_used", 0),
                        signature=data.get("signature", ""),
                    )
                    self.window.append(action)
                    self.total_actions += 1
                    self.total_tokens += action.tokens_used
                    loaded += 1
            if loaded:
                logger.info("LoopDetector loaded %d actions from %s", loaded, self._persist_path)
            return loaded > 0
        except Exception as e:
            logger.error("LoopDetector load failed: %s", e)
            return False

    # ---- Signal implementations ----

    def _check_signature_repeat(self) -> dict[str, Any] | None:
        """Signal 1: Same action signature appears 3+ times in window."""
        sig_counts: dict[str, int] = {}
        for a in self.window:
            sig_counts[a.signature] = sig_counts.get(a.signature, 0) + 1

        repeats = {
            sig: count for sig, count in sig_counts.items()
            if count >= self.signature_threshold
        }

        if not repeats:
            return None

        # Find the most repeated action's details
        worst_sig = max(repeats, key=repeats.get)  # type: ignore[arg-type]
        worst_action = next(a for a in reversed(self.window) if a.signature == worst_sig)

        return {
            "repeated_action": f"{worst_action.action_type}:{worst_action.target}",
            "count": repeats[worst_sig],
            "threshold": self.signature_threshold,
        }

    def _check_error_pattern(self) -> dict[str, Any] | None:
        """Signal 2: 80%+ of recent actions have the same error type."""
        recent = list(self.window)[-5:]  # Last 5 actions
        if len(recent) < 3:
            return None

        error_types = [a.error_type for a in recent if a.error_type]
        if not error_types:
            return None

        error_rate = len(error_types) / len(recent)
        if error_rate < self.error_threshold:
            return None

        # Check if errors are the same type
        from collections import Counter
        type_counts = Counter(error_types)
        most_common_type, most_common_count = type_counts.most_common(1)[0]
        homogeneity = most_common_count / len(error_types)

        if homogeneity < self.error_threshold:
            return None

        return {
            "error_type": most_common_type,
            "error_rate": round(error_rate, 2),
            "homogeneity": round(homogeneity, 2),
            "threshold": self.error_threshold,
        }

    def _check_semantic_repeat(self) -> dict[str, Any] | None:
        """Signal 3: High keyword overlap between consecutive actions."""
        if len(self.window) < 3:
            return None

        # Compare last 3 pairs of consecutive actions
        recent = list(self.window)[-4:]
        similarities = []

        for i in range(len(recent) - 1):
            a, b = recent[i], recent[i + 1]
            kw_a = set(a.keywords) | {a.action_type, a.target}
            kw_b = set(b.keywords) | {b.action_type, b.target}
            kw_a.discard("")
            kw_b.discard("")

            if not kw_a or not kw_b:
                continue

            # Jaccard similarity
            intersection = kw_a & kw_b
            union = kw_a | kw_b
            sim = len(intersection) / len(union) if union else 0.0
            similarities.append(sim)

        if not similarities:
            return None

        avg_sim = sum(similarities) / len(similarities)
        if avg_sim < self.semantic_threshold:
            return None

        return {
            "avg_similarity": round(avg_sim, 3),
            "threshold": self.semantic_threshold,
            "pairs_checked": len(similarities),
        }

    def _check_resource_limits(self) -> dict[str, Any] | None:
        """Signal 4: Current sliding window exceeds the configured action budget."""
        window_actions = len(self.window)
        if window_actions <= self.resource_limit:
            return None

        return {
            "window_actions": window_actions,
            "limit": self.resource_limit,
            "window_tokens": sum(action.tokens_used for action in self.window),
            "lifetime_actions": self.total_actions,
            "lifetime_tokens": self.total_tokens,
        }
