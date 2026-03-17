"""Instinct Bridge — ECC observations ↔ dharma_swarm fitness signals.

Reads 3,333+ ECC observations from the homunculus JSONL, extracts patterns
(tool failures, successful edit sequences), and:
  - Emits fitness signals via MessageBus.emit_event("ECC_INSTINCT_SIGNAL", ...)
  - Writes synthetic instincts back to ECC's instinct directory

Knowledge flows both ways: ECC learns from dharma_swarm evolution successes,
dharma_swarm learns from ECC's observed tool patterns.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"

# ECC observation and instinct paths
_ECC_BASE = Path.home() / ".claude" / "homunculus" / "projects" / "ba3bce345c46"
OBSERVATIONS_FILE = _ECC_BASE / "observations.jsonl"
INSTINCTS_DIR = _ECC_BASE / "instincts" / "personal"

# Bridge state
BRIDGE_STATE_DIR = STATE_DIR / "instinct_bridge"
CURSOR_FILE = BRIDGE_STATE_DIR / "cursor.json"


# ---------------------------------------------------------------------------
# Observation parsing
# ---------------------------------------------------------------------------

def load_observations(
    since_line: int = 0,
    limit: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    """Load observations from ECC JSONL, starting after *since_line*.

    Returns:
        (observations, new_cursor) — list of parsed observations and the
        new line cursor for next invocation.
    """
    if not OBSERVATIONS_FILE.exists():
        return [], since_line

    observations: list[dict] = []
    current_line = 0
    with OBSERVATIONS_FILE.open() as f:
        for line in f:
            current_line += 1
            if current_line <= since_line:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            try:
                observations.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
            if len(observations) >= limit:
                break

    return observations, current_line


def _load_cursor() -> int:
    """Load the last-processed line number."""
    if CURSOR_FILE.exists():
        try:
            data = json.loads(CURSOR_FILE.read_text())
            return data.get("line", 0)
        except (json.JSONDecodeError, KeyError):
            pass
    return 0


def _save_cursor(line: int) -> None:
    """Persist the cursor for incremental processing."""
    BRIDGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_FILE.write_text(json.dumps({
        "line": line,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }))


# ---------------------------------------------------------------------------
# Pattern extraction
# ---------------------------------------------------------------------------

def extract_patterns(observations: list[dict]) -> list[dict[str, Any]]:
    """Extract actionable patterns from raw observations.

    Patterns:
      - tool_failure: a tool call failed on a dharma_swarm file → negative signal
      - successful_edit: edit + passing test → positive signal
      - read_before_edit: consistent read-before-edit pattern → instinct candidate
    """
    patterns: list[dict] = []
    # Track sequential events by session
    sessions: dict[str, list[dict]] = {}
    for obs in observations:
        session = obs.get("session_id", "unknown")
        sessions.setdefault(session, []).append(obs)

    for session_id, events in sessions.items():
        _extract_from_session(events, patterns)

    return patterns


def _extract_from_session(events: list[dict], patterns: list[dict]) -> None:
    """Extract patterns from a single session's events."""
    for i, event in enumerate(events):
        tool = event.get("tool", "")
        status = event.get("status", "")
        file_path = event.get("file_path", "") or event.get("path", "")

        # Pattern: tool failure on dharma_swarm file
        if status in ("error", "failed") and "dharma_swarm" in str(file_path):
            module = _path_to_module(file_path)
            if module:
                patterns.append({
                    "type": "tool_failure",
                    "module": module,
                    "tool": tool,
                    "signal": "negative",
                    "confidence": 0.6,
                    "detail": event.get("error", "")[:200],
                })

        # Pattern: successful edit followed by test pass
        if tool in ("Edit", "Write") and status == "success" and "dharma_swarm" in str(file_path):
            # Look ahead for test success
            for j in range(i + 1, min(i + 5, len(events))):
                next_evt = events[j]
                if next_evt.get("tool") == "Bash" and "pytest" in str(next_evt.get("command", "")):
                    if next_evt.get("status") == "success":
                        module = _path_to_module(file_path)
                        if module:
                            patterns.append({
                                "type": "successful_edit",
                                "module": module,
                                "signal": "positive",
                                "confidence": 0.8,
                            })
                    break

        # Pattern: read-before-edit
        if tool == "Read" and "dharma_swarm" in str(file_path):
            for j in range(i + 1, min(i + 3, len(events))):
                next_evt = events[j]
                if next_evt.get("tool") in ("Edit", "Write"):
                    next_path = next_evt.get("file_path", "") or next_evt.get("path", "")
                    if next_path == file_path:
                        patterns.append({
                            "type": "read_before_edit",
                            "module": _path_to_module(file_path) or file_path,
                            "signal": "instinct",
                            "confidence": 0.5,
                        })
                        break


def _path_to_module(path: str) -> str | None:
    """Convert a file path to a dharma_swarm module name."""
    try:
        p = Path(path)
        if p.suffix != ".py":
            return None
        parts = p.parts
        if "dharma_swarm" in parts:
            idx = parts.index("dharma_swarm")
            # Take from the second dharma_swarm (package dir)
            remaining = parts[idx + 1:]
            if remaining and remaining[0] == "dharma_swarm":
                remaining = remaining[1:]
            if remaining:
                return remaining[-1].replace(".py", "")
        return p.stem
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Signal emission
# ---------------------------------------------------------------------------

async def emit_fitness_signals(
    patterns: list[dict],
    bus: Any | None = None,
) -> int:
    """Emit patterns as MessageBus events. Returns count emitted."""
    if bus is None:
        from dharma_swarm.message_bus import MessageBus
        db_path = STATE_DIR / "db" / "messages.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        bus = MessageBus(db_path)
        await bus.init_db()

    count = 0
    for p in patterns:
        if p.get("signal") in ("positive", "negative"):
            await bus.emit_event(
                "ECC_INSTINCT_SIGNAL",
                agent_id="instinct_bridge",
                payload={
                    "pattern_type": p["type"],
                    "module": p.get("module", ""),
                    "signal": p["signal"],
                    "confidence": p.get("confidence", 0.5),
                    "detail": p.get("detail", ""),
                },
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Synthetic instinct generation
# ---------------------------------------------------------------------------

def write_synthetic_instinct(
    name: str,
    description: str,
    confidence: float,
    source: str = "dharma_swarm_evolution",
) -> Path | None:
    """Write a synthetic instinct YAML to ECC's instinct directory.

    Only writes if confidence >= 0.7 (high confidence threshold).
    """
    if confidence < 0.7:
        return None

    INSTINCTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace(" ", "_").replace("/", "_")[:50]
    instinct_path = INSTINCTS_DIR / f"ds_{safe_name}.yaml"

    content = (
        f"name: {name}\n"
        f"description: {description}\n"
        f"confidence: {confidence}\n"
        f"source: {source}\n"
        f"created_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"type: synthetic\n"
    )
    instinct_path.write_text(content)
    logger.info("Wrote synthetic instinct: %s (confidence=%.2f)", instinct_path, confidence)
    return instinct_path


# ---------------------------------------------------------------------------
# InstinctBridge class
# ---------------------------------------------------------------------------

class InstinctBridge:
    """Bidirectional bridge between ECC observations and dharma_swarm fitness."""

    def __init__(self, bus: Any | None = None) -> None:
        self._bus = bus

    async def process_new_observations(self) -> dict[str, int]:
        """Process new observations since last cursor, emit signals.

        Returns:
            Dict with counts: observations_read, patterns_found, signals_emitted
        """
        cursor = _load_cursor()
        observations, new_cursor = load_observations(since_line=cursor)

        if not observations:
            return {"observations_read": 0, "patterns_found": 0, "signals_emitted": 0}

        patterns = extract_patterns(observations)
        signals_emitted = await emit_fitness_signals(patterns, bus=self._bus)
        _save_cursor(new_cursor)

        return {
            "observations_read": len(observations),
            "patterns_found": len(patterns),
            "signals_emitted": signals_emitted,
        }

    def write_evolution_instincts(
        self,
        entries: list[dict[str, Any]],
        fitness_threshold: float = 0.7,
    ) -> int:
        """Write synthetic instincts from high-fitness evolution entries.

        Args:
            entries: List of evolution archive entries (dicts).
            fitness_threshold: Minimum weighted fitness to generate instinct.

        Returns:
            Number of instincts written.
        """
        count = 0
        for entry in entries:
            fitness = entry.get("fitness", {})
            if isinstance(fitness, dict):
                weighted = sum(fitness.values()) / max(len(fitness), 1)
            else:
                weighted = 0.0
            if weighted < fitness_threshold:
                continue

            component = entry.get("component", "unknown")
            description = entry.get("description", "")[:200]
            result = write_synthetic_instinct(
                name=f"evolution_{component}",
                description=f"High-fitness pattern from evolution: {description}",
                confidence=min(weighted, 1.0),
                source="darwin_engine",
            )
            if result:
                count += 1
        return count

    def status(self) -> dict[str, Any]:
        """Return bridge status summary."""
        cursor = _load_cursor()
        obs_exists = OBSERVATIONS_FILE.exists()
        obs_lines = 0
        if obs_exists:
            with OBSERVATIONS_FILE.open() as f:
                obs_lines = sum(1 for _ in f)

        instinct_count = 0
        if INSTINCTS_DIR.exists():
            instinct_count = len(list(INSTINCTS_DIR.glob("ds_*.yaml")))

        return {
            "observations_file_exists": obs_exists,
            "total_observations": obs_lines,
            "cursor_position": cursor,
            "unprocessed": max(0, obs_lines - cursor),
            "synthetic_instincts": instinct_count,
            "instincts_dir": str(INSTINCTS_DIR),
        }


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def cmd_instincts_status() -> int:
    """Print instinct bridge status."""
    bridge = InstinctBridge()
    status = bridge.status()
    print("Instinct Bridge Status")
    print("=" * 45)
    print(f"  Observations file: {'exists' if status['observations_file_exists'] else 'MISSING'}")
    print(f"  Total observations: {status['total_observations']}")
    print(f"  Cursor: {status['cursor_position']}")
    print(f"  Unprocessed: {status['unprocessed']}")
    print(f"  Synthetic instincts: {status['synthetic_instincts']}")
    return 0


async def cmd_instincts_sync() -> int:
    """Process new observations and emit signals."""
    bridge = InstinctBridge()
    result = await bridge.process_new_observations()
    print(f"Instinct Bridge Sync")
    print(f"  Observations read: {result['observations_read']}")
    print(f"  Patterns found: {result['patterns_found']}")
    print(f"  Signals emitted: {result['signals_emitted']}")
    return 0
