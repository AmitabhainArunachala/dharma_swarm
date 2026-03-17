"""Context Agent — the ecosystem's autonomous nervous system.

Full-time agent that monitors, distills, cross-pollinates, and pre-assembles
context for all agents and sessions. Two layers:

  NervousSystem (pure Python, always on):
    - File freshness scanning across 11 tiers
    - Context health scoring
    - Pre-assembled package generation

  Intelligence (Ollama Cloud, event-driven):
    - Agent note distillation (>50KB → ~5KB)
    - Cross-pollination (bridge notes across domains)
    - Latent inquiry extraction
    - Dream-mode speculation (quiet hours 2-4 AM)

Runs as 6th loop in orchestrate-live. Emits CONTEXT_HEALTH signals.
Leaves stigmergic marks. Participates in the Strange Loop.

Integration:
  - context.py reads distilled/ instead of raw 600KB agent notes
  - meta_daemon.py includes context health in recognition seed
  - context-engineer skill reads packages/ for instant session starts
  - signal_bus carries CONTEXT_HEALTH + CONTEXT_STALE events
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.signal_bus import SignalBus
from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DHARMA = Path.home() / ".dharma"
_CONTEXT_DIR = _DHARMA / "context"
_PACKAGES_DIR = _CONTEXT_DIR / "packages"
_DISTILLED_DIR = _CONTEXT_DIR / "distilled"
_DREAMS_DIR = _CONTEXT_DIR / "dreams"
_BRIDGE_DIR = _CONTEXT_DIR / "bridge_notes"
_SHARED_DIR = _DHARMA / "shared"
_META_DIR = _DHARMA / "meta"
_STIGMERGY_DIR = _DHARMA / "stigmergy"

# Agent note files and their roles
AGENT_NOTES = {
    "researcher": _SHARED_DIR / "researcher_notes.md",
    "archeologist": _SHARED_DIR / "archeologist_notes.md",
    "architect": _SHARED_DIR / "architect_notes.md",
    "builder": _SHARED_DIR / "builder_notes.md",
    "cartographer": _SHARED_DIR / "cartographer_notes.md",
    "surgeon": _SHARED_DIR / "surgeon_notes.md",
    "validator": _SHARED_DIR / "validator_notes.md",
}

# All context sources with their tiers
CONTEXT_SOURCES: list[dict[str, Any]] = [
    # Tier 3: Live state
    {"name": ".FOCUS", "path": _DHARMA / ".FOCUS", "tier": 3},
    {"name": "NOW.json", "path": _DHARMA / "state" / "NOW.json", "tier": 3},
    {"name": "thread_state", "path": _DHARMA / "thread_state.json", "tier": 3},
    {"name": "daemon.pid", "path": _DHARMA / "daemon.pid", "tier": 3},
    {"name": "recognition_seed", "path": _META_DIR / "recognition_seed.md", "tier": 8},
    # Tier 4: Agent signals
    {"name": "morning_brief", "path": _SHARED_DIR, "tier": 4, "glob": "morning_brief_*.md"},
    {"name": "jk_pulse", "path": _SHARED_DIR / "jk_pulse.md", "tier": 4},
    {"name": "jk_alert", "path": _SHARED_DIR / "jk_alert.md", "tier": 4},
    {"name": "distilled_briefing", "path": _SHARED_DIR / "distilled_briefing.md", "tier": 4},
    # Tier 5: Stigmergy
    {"name": "marks", "path": _STIGMERGY_DIR / "marks.jsonl", "tier": 5},
    # Tier 6: Health
    {"name": "dgc_health", "path": _STIGMERGY_DIR / "dgc_health.json", "tier": 6},
    {"name": "tcs", "path": _STIGMERGY_DIR / "mycelium_identity_tcs.json", "tier": 6},
    {"name": "scoring", "path": _STIGMERGY_DIR / "mycelium_scoring_report.json", "tier": 6},
    # Tier 7: Cascade
    {"name": "cascade_history", "path": _META_DIR / "cascade_history.jsonl", "tier": 7},
]

# Thresholds
NOTE_DISTILL_THRESHOLD_KB = 50
HEALTH_TARGET = 0.8
HEALTH_ALERT = 0.6
HEALTH_CRITICAL = 0.4
SEED_MAX_AGE_HOURS = 6
QUIET_HOUR_START = 2  # 2 AM local
QUIET_HOUR_END = 4  # 4 AM local

# LLM config — uses Ollama Cloud when OLLAMA_API_KEY is set
# Default: kimi-k2.5:cloud (Ollama Cloud frontier model)
# Override: CONTEXT_AGENT_MODEL env var
DISTILL_MODEL = os.environ.get("CONTEXT_AGENT_MODEL", "")  # empty = let provider auto-detect
DISTILL_MAX_TOKENS = 2000


# ---------------------------------------------------------------------------
# NervousSystem — pure Python, always on
# ---------------------------------------------------------------------------

class NervousSystem:
    """Monitors all context sources, scores freshness, detects anomalies."""

    def __init__(self, base_path: Path | None = None) -> None:
        self._last_scan: dict[str, float] = {}  # source_name → mtime
        self._base = base_path or _DHARMA
        self._shared = self._base / "shared"
        self._meta = self._base / "meta"
        self._stigmergy = self._base / "stigmergy"
        # Build sources relative to base
        self._sources = self._build_sources()
        self._agent_notes = {
            role: self._shared / f"{role}_notes.md"
            for role in ["researcher", "archeologist", "architect",
                         "builder", "cartographer", "surgeon", "validator"]
        }

    def _build_sources(self) -> list[dict[str, Any]]:
        """Build context source list relative to base path."""
        return [
            {"name": ".FOCUS", "path": self._base / ".FOCUS", "tier": 3},
            {"name": "NOW.json", "path": self._base / "state" / "NOW.json", "tier": 3},
            {"name": "thread_state", "path": self._base / "thread_state.json", "tier": 3},
            {"name": "daemon.pid", "path": self._base / "daemon.pid", "tier": 3},
            {"name": "recognition_seed", "path": self._meta / "recognition_seed.md", "tier": 8},
            {"name": "morning_brief", "path": self._shared, "tier": 4, "glob": "morning_brief_*.md"},
            {"name": "jk_pulse", "path": self._shared / "jk_pulse.md", "tier": 4},
            {"name": "jk_alert", "path": self._shared / "jk_alert.md", "tier": 4},
            {"name": "distilled_briefing", "path": self._shared / "distilled_briefing.md", "tier": 4},
            {"name": "marks", "path": self._stigmergy / "marks.jsonl", "tier": 5},
            {"name": "dgc_health", "path": self._stigmergy / "dgc_health.json", "tier": 6},
            {"name": "tcs", "path": self._stigmergy / "mycelium_identity_tcs.json", "tier": 6},
            {"name": "scoring", "path": self._stigmergy / "mycelium_scoring_report.json", "tier": 6},
            {"name": "cascade_history", "path": self._meta / "cascade_history.jsonl", "tier": 7},
        ]

    def scan_freshness(self) -> dict[str, dict[str, Any]]:
        """Scan all context sources and compute freshness scores.

        Returns dict of source_name → {path, mtime, age_seconds, freshness, size_kb, tier}.
        Freshness: 1.0 = just updated, 0.0 = very stale.
        """
        now = time.time()
        results: dict[str, dict[str, Any]] = {}

        for source in self._sources:
            name = source["name"]
            path = Path(source["path"])

            if "glob" in source:
                # Find most recent matching file
                matches = sorted(path.glob(source["glob"]), key=lambda p: p.stat().st_mtime if p.exists() else 0)
                path = matches[-1] if matches else path / "MISSING"

            if not path.exists():
                results[name] = {
                    "path": str(path), "exists": False,
                    "freshness": 0.0, "tier": source["tier"],
                }
                continue

            stat = path.stat()
            age_seconds = now - stat.st_mtime
            age_hours = age_seconds / 3600

            # Freshness decay: 1.0 at 0h, ~0.5 at 6h, ~0.1 at 24h
            freshness = max(0.0, 1.0 / (1.0 + age_hours / 3.0))

            results[name] = {
                "path": str(path),
                "exists": True,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "age_seconds": round(age_seconds),
                "age_hours": round(age_hours, 1),
                "freshness": round(freshness, 3),
                "size_kb": round(stat.st_size / 1024, 1),
                "tier": source["tier"],
            }

        # Also scan agent notes
        for role, path in self._agent_notes.items():
            if not path.exists():
                results[f"notes_{role}"] = {"exists": False, "freshness": 0.0, "tier": 4}
                continue
            stat = path.stat()
            age_hours = (now - stat.st_mtime) / 3600
            results[f"notes_{role}"] = {
                "path": str(path),
                "exists": True,
                "age_hours": round(age_hours, 1),
                "freshness": round(max(0.0, 1.0 / (1.0 + age_hours / 3.0)), 3),
                "size_kb": round(stat.st_size / 1024, 1),
                "tier": 4,
                "bloated": stat.st_size > NOTE_DISTILL_THRESHOLD_KB * 1024,
            }

        return results

    def assess_health(self, freshness: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Compute context health score from freshness data.

        Formula:
          0.30 * mean_freshness(tier_3) +    # live state
          0.20 * mean_freshness(tier_4) +    # agent signals
          0.20 * (1 - bloat_ratio) +         # notes under 50KB = 1.0
          0.15 * recognition_seed_freshness + # seed < 2h = 1.0
          0.15 * thread_balance               # even distribution = 1.0
        """
        def tier_mean(tier: int) -> float:
            vals = [v["freshness"] for v in freshness.values()
                    if v.get("tier") == tier and v.get("exists", False)]
            return sum(vals) / len(vals) if vals else 0.0

        # Bloat ratio: fraction of agent notes exceeding threshold
        bloated = [v for k, v in freshness.items()
                   if k.startswith("notes_") and v.get("bloated", False)]
        total_notes = [v for k, v in freshness.items() if k.startswith("notes_")]
        bloat_ratio = len(bloated) / len(total_notes) if total_notes else 0.0

        # Recognition seed freshness
        seed_freshness = freshness.get("recognition_seed", {}).get("freshness", 0.0)

        # Thread balance (read thread_state.json)
        thread_balance = self._compute_thread_balance()

        score = (
            0.30 * tier_mean(3) +
            0.20 * tier_mean(4) +
            0.20 * (1.0 - bloat_ratio) +
            0.15 * seed_freshness +
            0.15 * thread_balance
        )

        # Identify issues
        alerts: list[str] = []
        if score < HEALTH_CRITICAL:
            alerts.append(f"CRITICAL: context health {score:.2f} < {HEALTH_CRITICAL}")
        elif score < HEALTH_ALERT:
            alerts.append(f"ALERT: context health {score:.2f} < {HEALTH_ALERT}")

        stale = [k for k, v in freshness.items()
                 if v.get("exists") and v.get("freshness", 1.0) < 0.2]
        if stale:
            alerts.append(f"Stale sources: {', '.join(stale)}")

        if bloated:
            names = [k for k, v in freshness.items()
                     if k.startswith("notes_") and v.get("bloated")]
            alerts.append(f"Bloated notes need distillation: {', '.join(names)}")

        return {
            "score": round(score, 3),
            "tier_3_freshness": round(tier_mean(3), 3),
            "tier_4_freshness": round(tier_mean(4), 3),
            "bloat_ratio": round(bloat_ratio, 3),
            "seed_freshness": round(seed_freshness, 3),
            "thread_balance": round(thread_balance, 3),
            "alerts": alerts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_thread_balance(self) -> float:
        """How evenly distributed are contributions across research threads?

        1.0 = perfectly balanced, 0.0 = all in one thread.
        """
        thread_path = self._base / "thread_state.json"
        if not thread_path.exists():
            return 0.5  # neutral if no data

        try:
            data = json.loads(thread_path.read_text())
            contributions = data.get("contributions", {})
            values = list(contributions.values())
            if not values or sum(values) == 0:
                return 0.5

            total = sum(values)
            n = len(values)
            # Normalized entropy: -sum(p*log(p)) / log(n)
            import math
            entropy = 0.0
            for v in values:
                if v > 0:
                    p = v / total
                    entropy -= p * math.log(p)
            max_entropy = math.log(n) if n > 1 else 1.0
            return round(entropy / max_entropy, 3)
        except Exception:
            return 0.5

    def find_bloated_notes(self) -> list[tuple[str, Path, int]]:
        """Return (role, path, size_kb) for agent notes exceeding threshold."""
        bloated = []
        for role, path in self._agent_notes.items():
            if path.exists() and path.stat().st_size > NOTE_DISTILL_THRESHOLD_KB * 1024:
                size_kb = path.stat().st_size // 1024
                bloated.append((role, path, size_kb))
        return sorted(bloated, key=lambda x: -x[2])  # biggest first


# ---------------------------------------------------------------------------
# Intelligence — Ollama Cloud, event-driven
# ---------------------------------------------------------------------------

class Intelligence:
    """LLM-powered context operations: distillation, cross-pollination, dreams."""

    def __init__(self, provider: Any = None, base_path: Path | None = None) -> None:
        self._provider = provider  # OllamaProvider instance, lazy init
        self._base = base_path or _DHARMA
        self._shared = self._base / "shared"
        self._meta = self._base / "meta"
        self._distilled_dir = self._base / "context" / "distilled"
        self._bridge_dir = self._base / "context" / "bridge_notes"
        self._dreams_dir = self._base / "context" / "dreams"
        self._context_dir = self._base / "context"
        self._agent_notes = {
            role: self._shared / f"{role}_notes.md"
            for role in ["researcher", "archeologist", "architect",
                         "builder", "cartographer", "surgeon", "validator"]
        }

    async def _get_provider(self) -> Any:
        """Lazy-init Ollama provider."""
        if self._provider is None:
            try:
                from dharma_swarm.providers import OllamaProvider
                self._provider = OllamaProvider(model=DISTILL_MODEL)
            except Exception as e:
                logger.warning("Could not init Ollama provider: %s", e)
                return None
        return self._provider

    async def _complete(self, system: str, prompt: str) -> str | None:
        """Make a single LLM completion call."""
        provider = await self._get_provider()
        if provider is None:
            return None

        try:
            from dharma_swarm.models import LLMRequest
            request = LLMRequest(
                model=DISTILL_MODEL or provider.default_model,
                messages=[{"role": "user", "content": prompt}],
                system=system,
                max_tokens=DISTILL_MAX_TOKENS,
                temperature=0.3,
            )
            response = await provider.complete(request)
            return response.content
        except Exception as e:
            logger.error("LLM completion failed: %s", e)
            return None

    async def distill_notes(self, role: str, path: Path) -> Path | None:
        """Compress an agent's notes file to key findings.

        Keeps last 3 task entries verbatim. Summarizes everything older.
        Writes to ~/.dharma/context/distilled/<role>_distilled.md
        """
        if not path.exists():
            return None

        content = path.read_text()
        size_kb = len(content) // 1024
        logger.info("Distilling %s notes: %dKB → target ~5KB", role, size_kb)

        # Split into task entries (delimited by --- or ## headers with timestamps)
        entries = content.split("\n---\n")
        if len(entries) < 4:
            # Try splitting by ## headers
            import re
            entries = re.split(r'\n(?=## )', content)

        if len(entries) <= 3:
            # Already small enough or can't split
            return None

        # Keep last 3 verbatim
        recent = "\n---\n".join(entries[-3:])

        # Summarize older entries
        older = "\n---\n".join(entries[:-3])
        # Truncate to ~10K chars for LLM input
        if len(older) > 10000:
            older = older[-10000:]

        summary = await self._complete(
            system=(
                "You are a research assistant distilling agent notes. "
                "Extract ONLY key findings, decisions, numbers, and discoveries. "
                "Omit routine task completions, status updates, and boilerplate. "
                "Be extremely concise — bullet points, not paragraphs. "
                "Preserve any specific numbers, file paths, or error messages."
            ),
            prompt=f"Distill these {role} agent notes to key findings:\n\n{older}",
        )

        if summary is None:
            return None

        # Write distilled file
        self._distilled_dir.mkdir(parents=True, exist_ok=True)
        distilled_path = self._distilled_dir / f"{role}_distilled.md"
        output = (
            f"# {role.title()} Notes — Distilled\n"
            f"*Auto-distilled {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
            f"from {size_kb}KB original*\n\n"
            f"## Key Findings (older entries)\n\n{summary}\n\n"
            f"## Recent Entries (verbatim)\n\n{recent}\n"
        )
        distilled_path.write_text(output)

        logger.info("Distilled %s: %dKB → %dKB at %s",
                     role, size_kb, len(output) // 1024, distilled_path)
        return distilled_path

    async def cross_pollinate(self) -> Path | None:
        """Detect connections across agent notes and write bridge notes.

        Reads recent entries from multiple agent notes, looks for
        overlapping concepts, and writes a bridge note highlighting
        the connection.
        """
        # Collect recent entries from each agent
        recent_by_role: dict[str, str] = {}
        for role, path in self._agent_notes.items():
            if path.exists():
                content = path.read_text()
                # Take last 2000 chars (most recent work)
                recent_by_role[role] = content[-2000:] if len(content) > 2000 else content

        if len(recent_by_role) < 2:
            return None

        # Build prompt with all recent entries
        entries_text = ""
        for role, text in recent_by_role.items():
            entries_text += f"\n### {role.upper()} (recent):\n{text}\n"

        bridge = await self._complete(
            system=(
                "You are a cross-domain synthesis agent. You read notes from "
                "multiple specialist agents and find CONNECTIONS between their work "
                "that neither agent sees alone. Look for:\n"
                "- Concepts that appear in different domains\n"
                "- Questions one agent asks that another has answers to\n"
                "- Patterns that recur across domains\n"
                "- Contradictions that need resolution\n\n"
                "Output ONLY genuine connections. If nothing connects, say so. "
                "Do not force connections that aren't there. "
                "Be specific — cite which agents and what they said."
            ),
            prompt=f"Find connections across these agent notes:\n{entries_text}",
        )

        if bridge is None or "nothing connects" in bridge.lower():
            return None

        self._bridge_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        bridge_path = self._bridge_dir / f"bridge_{ts}.md"
        bridge_path.write_text(
            f"# Bridge Note — {ts}\n"
            f"*Auto-generated by context agent cross-pollination*\n\n"
            f"{bridge}\n"
        )

        logger.info("Bridge note written: %s", bridge_path)
        return bridge_path

    async def generate_questions(self, freshness: dict[str, dict[str, Any]]) -> list[str]:
        """Extract latent inquiries from ecosystem patterns.

        Looks at: thread imbalance, stale sources, bloated notes,
        cascade fitness gaps. Generates questions the system is
        implicitly circling but hasn't asked.
        """
        # Build a situation summary
        stale = [k for k, v in freshness.items()
                 if v.get("exists") and v.get("freshness", 1.0) < 0.2]
        bloated = [k for k, v in freshness.items()
                   if k.startswith("notes_") and v.get("bloated")]

        # Read thread state
        thread_text = ""
        thread_path = self._base / "thread_state.json"
        if thread_path.exists():
            thread_text = thread_path.read_text()

        # Read latest cascade scores
        cascade_text = ""
        cascade_path = self._meta / "cascade_history.jsonl"
        if cascade_path.exists():
            lines = cascade_path.read_text().strip().split("\n")
            cascade_text = "\n".join(lines[-5:])  # last 5 entries

        prompt = (
            f"System state:\n"
            f"- Stale sources: {stale or 'none'}\n"
            f"- Bloated notes: {bloated or 'none'}\n"
            f"- Thread state: {thread_text}\n"
            f"- Recent cascade: {cascade_text}\n\n"
            f"What questions should this system be asking that it isn't? "
            f"What patterns suggest something is being overlooked? "
            f"Generate 3-5 specific, actionable questions."
        )

        result = await self._complete(
            system=(
                "You are a metacognitive agent. Given the state of a "
                "self-evolving AI system, generate questions that the system "
                "should be asking but isn't. Focus on blind spots, imbalances, "
                "and implicit assumptions. Be specific and actionable."
            ),
            prompt=prompt,
        )

        if result is None:
            return []

        # Parse questions from response
        questions = [
            line.strip().lstrip("0123456789.-) ")
            for line in result.split("\n")
            if line.strip() and "?" in line
        ]
        return questions[:5]

    async def dream(self) -> Path | None:
        """Speculative juxtaposition during quiet hours.

        Combines unexpected context sources to find latent connections.
        Only runs during quiet hours (2-4 AM local).
        """
        hour = datetime.now().hour
        if not (QUIET_HOUR_START <= hour < QUIET_HOUR_END):
            return None

        # Gather unusual combinations
        ingredients: list[str] = []

        # Read recognition seed
        seed_path = self._meta / "recognition_seed.md"
        if seed_path.exists():
            ingredients.append(f"RECOGNITION SEED:\n{seed_path.read_text()}")

        # Read latest dream associations
        hum_path = self._base / "subconscious" / "hum.jsonl"
        if hum_path.exists():
            lines = hum_path.read_text().strip().split("\n")
            if lines:
                ingredients.append(f"SUBCONSCIOUS HUM (last 3):\n" + "\n".join(lines[-3:]))

        # Read top seeds
        seeds_path = self._base / "seeds" / "top_seeds.md"
        if seeds_path.exists():
            content = seeds_path.read_text()
            ingredients.append(f"ARCHAEOLOGY SEEDS:\n{content[:2000]}")

        # Read cascade fitness
        cascade_path = self._meta / "cascade_history.jsonl"
        if cascade_path.exists():
            lines = cascade_path.read_text().strip().split("\n")
            ingredients.append(f"CASCADE STATE:\n" + "\n".join(lines[-3:]))

        if len(ingredients) < 2:
            return None

        dream_text = await self._complete(
            system=(
                "You are a dream engine. You receive fragments from different "
                "parts of a consciousness research system and create speculative "
                "connections between them. Think like a dream — associative, "
                "unexpected, pattern-finding. Don't be random — find the deep "
                "structure that connects these fragments. Most dreams are noise; "
                "the good ones reveal something the waking mind missed."
            ),
            prompt=f"Dream with these fragments:\n\n" + "\n\n---\n\n".join(ingredients),
        )

        if dream_text is None:
            return None

        self._dreams_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dream_path = self._dreams_dir / f"dream_{ts}.md"
        dream_path.write_text(
            f"# Dream — {ts}\n"
            f"*Context agent quiet-hours speculation*\n\n"
            f"{dream_text}\n"
        )

        logger.info("Dream written: %s", dream_path)
        return dream_path


# ---------------------------------------------------------------------------
# Package Assembly
# ---------------------------------------------------------------------------

def _tail_file(path: Path, lines: int = 30) -> str:
    """Read last N lines of a file."""
    if not path.exists():
        return ""
    all_lines = path.read_text().split("\n")
    return "\n".join(all_lines[-lines:])


def _read_json_safe(path: Path) -> dict[str, Any]:
    """Read JSON file safely, return empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_safe(path: Path, max_chars: int = 5000) -> str:
    """Read file safely, truncate if too large."""
    if not path.exists():
        return ""
    content = path.read_text()
    if len(content) > max_chars:
        return content[:max_chars] + "\n...[truncated]"
    return content


def assemble_package(recipe: str, base_path: Path | None = None) -> str:
    """Assemble a context package for a given recipe.

    Returns markdown string ready to inject into a session or agent prompt.
    """
    base = base_path or _DHARMA
    shared = base / "shared"
    meta = base / "meta"
    stigmergy = base / "stigmergy"
    distilled = base / "context" / "distilled"

    sections: list[str] = []
    sections.append(f"# Context Package: {recipe}")
    sections.append(f"*Assembled {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n")

    # Always include: recognition seed, .FOCUS, thread state
    focus = _read_safe(base / ".FOCUS", 200)
    if focus:
        sections.append(f"## Focus\n{focus.strip()}\n")

    seed = _read_safe(meta / "recognition_seed.md", 1000)
    if seed:
        sections.append(f"## Recognition Seed\n{seed}\n")

    thread = _read_json_safe(base / "thread_state.json")
    if thread:
        sections.append(f"## Research Thread\nActive: {thread.get('current_thread', 'unknown')}\n")

    # Recipe-specific content
    if recipe == "session-start":
        _add_session_start(sections, shared)
    elif recipe == "rv-paper":
        _add_rv_paper(sections, shared, distilled)
    elif recipe == "dharma-swarm":
        _add_dharma_swarm(sections, shared, distilled, stigmergy, meta)
    elif recipe == "jagat-kalyan":
        _add_jagat_kalyan(sections, shared)
    elif recipe == "system-health":
        _add_system_health(sections, stigmergy, base)
    elif recipe == "full-state":
        _add_session_start(sections, shared)
        _add_system_health(sections, stigmergy, base)

    return "\n".join(sections)


def _add_session_start(sections: list[str], shared: Path) -> None:
    """Add session-start specific context."""
    # Morning brief
    briefs = sorted(shared.glob("morning_brief_*.md"))
    if briefs:
        sections.append(f"## Morning Brief\n{_read_safe(briefs[-1], 3000)}\n")

    # JK signals
    jk_pulse = _read_safe(shared / "jk_pulse.md", 500)
    if jk_pulse:
        sections.append(f"## JK Pulse\n{jk_pulse}\n")

    jk_alert = _read_safe(shared / "jk_alert.md", 500)
    if jk_alert:
        sections.append(f"## JK Alert\n{jk_alert}\n")


def _add_rv_paper(sections: list[str], shared: Path, distilled_dir: Path) -> None:
    """Add R_V paper specific context."""
    # Paper status from memory
    rv_status = Path.home() / ".claude" / "projects" / "-Users-dhyana" / "memory" / "rv_paper_status.md"
    if rv_status.exists():
        sections.append(f"## R_V Paper Status\n{_read_safe(rv_status, 3000)}\n")

    # Recent researcher notes (distilled if available, otherwise tail)
    distilled_file = distilled_dir / "researcher_distilled.md"
    if distilled_file.exists():
        sections.append(f"## Researcher Findings (Distilled)\n{_read_safe(distilled_file, 3000)}\n")
    else:
        tail = _tail_file(shared / "researcher_notes.md", 30)
        if tail:
            sections.append(f"## Researcher Findings (Recent)\n{tail}\n")


def _add_dharma_swarm(sections: list[str], shared: Path, distilled_dir: Path, stigmergy: Path, meta: Path) -> None:
    """Add dharma_swarm development context."""
    # Module scoring
    scoring = _read_json_safe(stigmergy / "mycelium_scoring_report.json")
    if scoring:
        sections.append(
            f"## Module Quality\n"
            f"- Scored: {scoring.get('scored_count', '?')} modules\n"
            f"- Mean: {scoring.get('mean_stars', '?')} stars\n"
        )

    # Recent builder + surgeon notes
    for role in ["builder", "surgeon"]:
        distilled_file = distilled_dir / f"{role}_distilled.md"
        if distilled_file.exists():
            sections.append(f"## {role.title()} Notes (Distilled)\n{_read_safe(distilled_file, 2000)}\n")
        else:
            tail = _tail_file(shared / f"{role}_notes.md", 20)
            if tail:
                sections.append(f"## {role.title()} Notes (Recent)\n{tail}\n")

    # Cascade state
    cascade_path = meta / "cascade_history.jsonl"
    if cascade_path.exists():
        lines = cascade_path.read_text().strip().split("\n")
        sections.append(f"## Cascade State (last 5)\n```json\n" + "\n".join(lines[-5:]) + "\n```\n")


def _add_jagat_kalyan(sections: list[str], shared: Path) -> None:
    """Add Jagat Kalyan context."""
    for name in ["jk_pulse.md", "jk_alert.md", "jk_iteration_queue.md", "jk_proof_lattice.md"]:
        content = _read_safe(shared / name, 1000)
        if content:
            sections.append(f"## {name}\n{content}\n")


def _add_system_health(sections: list[str], stigmergy: Path, base: Path) -> None:
    """Add system health context."""
    for name, label in [
        ("dgc_health.json", "DGC Health"),
        ("mycelium_identity_tcs.json", "Identity TCS"),
        ("mycelium_scoring_report.json", "Module Scoring"),
    ]:
        data = _read_json_safe(stigmergy / name)
        if data:
            sections.append(f"## {label}\n```json\n{json.dumps(data, indent=2)}\n```\n")

    # Daemon status
    pid_path = base / "daemon.pid"
    if pid_path.exists():
        pid = pid_path.read_text().strip()
        sections.append(f"## Daemon\nPID file: {pid}\n")


# ---------------------------------------------------------------------------
# ContextAgent — orchestrates everything
# ---------------------------------------------------------------------------

class ContextAgent:
    """Full-time autonomous context agent.

    Two layers:
      nervous_system — pure Python, always on
      intelligence — Ollama Cloud, event-driven

    Call run_cycle() from the daemon loop.
    """

    def __init__(self, signal_bus: SignalBus | None = None, base_path: Path | None = None) -> None:
        self._base = base_path or _DHARMA
        self.nervous = NervousSystem(base_path=self._base)
        self.intelligence = Intelligence(base_path=self._base)
        self.bus = signal_bus or SignalBus.get()
        self.store = StigmergyStore()
        self._cycle_count = 0
        self._last_distill_time = 0.0
        self._last_cross_pollinate_time = 0.0
        self._last_dream_time = 0.0

    async def run_cycle(self) -> dict[str, Any]:
        """Execute one full sense → assess → act → serve cycle.

        Returns cycle report dict.
        """
        self._cycle_count += 1
        cycle_start = time.time()
        report: dict[str, Any] = {"cycle": self._cycle_count}

        # 1. SENSE
        freshness = self.nervous.scan_freshness()

        # 2. ASSESS
        health = self.nervous.assess_health(freshness)
        report["health"] = health

        # 3. ACT — based on what needs attention
        actions: list[str] = []

        # Distill bloated notes (at most every 30 min)
        if time.time() - self._last_distill_time > 1800:
            bloated = self.nervous.find_bloated_notes()
            if bloated:
                for role, path, size_kb in bloated[:2]:  # max 2 per cycle
                    result = await self.intelligence.distill_notes(role, path)
                    if result:
                        actions.append(f"distilled:{role}({size_kb}KB)")
                        await self.store.leave_mark(StigmergicMark(
                            agent="context-agent",
                            file_path=str(result),
                            action="write",
                            observation=f"Distilled {role} notes: {size_kb}KB → {result.stat().st_size // 1024}KB",
                            salience=0.7,
                        ))
                self._last_distill_time = time.time()

        # Cross-pollinate (at most every 2 hours)
        if time.time() - self._last_cross_pollinate_time > 7200:
            bridge = await self.intelligence.cross_pollinate()
            if bridge:
                actions.append(f"bridge:{bridge.name}")
                await self.store.leave_mark(StigmergicMark(
                    agent="context-agent",
                    file_path=str(bridge),
                    action="connect",
                    observation=f"Cross-pollination bridge note: {bridge.name}",
                    salience=0.8,
                    connections=[str(p) for p in AGENT_NOTES.values() if p.exists()],
                ))
            self._last_cross_pollinate_time = time.time()

        # Generate questions (at most every 4 hours)
        if self._cycle_count % 12 == 0:  # ~every 12 cycles
            questions = await self.intelligence.generate_questions(freshness)
            if questions:
                actions.append(f"questions:{len(questions)}")
                # Write questions to a signal file
                q_path = self._base / "context" / "latent_inquiries.md"
                q_path.write_text(
                    f"# Latent Inquiries\n"
                    f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n\n"
                    + "\n".join(f"- {q}" for q in questions) + "\n"
                )

        # Dream during quiet hours (at most once per night)
        if time.time() - self._last_dream_time > 86400:  # 24h
            dream = await self.intelligence.dream()
            if dream:
                actions.append(f"dream:{dream.name}")
                await self.store.leave_mark(StigmergicMark(
                    agent="context-agent",
                    file_path=str(dream),
                    action="dream",
                    observation=f"Quiet-hours dream: {dream.name}",
                    salience=0.6,
                ))
                self._last_dream_time = time.time()

        report["actions"] = actions

        # 4. SERVE — pre-assemble packages
        recipes = [
            "session-start", "rv-paper", "dharma-swarm",
            "jagat-kalyan", "system-health", "full-state",
        ]
        packages_dir = self._base / "context" / "packages"
        packages_dir.mkdir(parents=True, exist_ok=True)
        for recipe in recipes:
            try:
                package = assemble_package(recipe, base_path=self._base)
                (packages_dir / f"{recipe.replace('-', '_')}.md").write_text(package)
            except Exception as e:
                logger.error("Failed to assemble package %s: %s", recipe, e)

        # 5. EMIT signals
        self.bus.emit({
            "type": "CONTEXT_HEALTH",
            "score": health["score"],
            "alerts": health["alerts"],
            "cycle": self._cycle_count,
        })

        if health["score"] < HEALTH_ALERT:
            self.bus.emit({
                "type": "CONTEXT_STALE",
                "score": health["score"],
                "stale_sources": [k for k, v in freshness.items()
                                  if v.get("exists") and v.get("freshness", 1.0) < 0.2],
            })

        # Write health to file for other systems
        context_dir = self._base / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        health_path = context_dir / "freshness.json"
        health_path.write_text(json.dumps({
            "health": health,
            "freshness": freshness,
        }, indent=2, default=str))

        alerts_path = context_dir / "alerts.json"
        alerts_path.write_text(json.dumps({
            "alerts": health["alerts"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))

        duration = time.time() - cycle_start
        report["duration_seconds"] = round(duration, 2)
        logger.info(
            "Context agent cycle %d: health=%.3f actions=%s duration=%.1fs",
            self._cycle_count, health["score"], actions or "none", duration,
        )

        return report


# ---------------------------------------------------------------------------
# Daemon loop entry point
# ---------------------------------------------------------------------------

CONTEXT_AGENT_INTERVAL = int(os.environ.get("DGC_CONTEXT_AGENT_INTERVAL", "180"))


async def run_context_agent_loop(
    shutdown_event: asyncio.Event,
    signal_bus: SignalBus | None = None,
) -> None:
    """Run the context agent as a daemon loop.

    Designed to be added as 6th task in orchestrate_live.orchestrate().
    """
    agent = ContextAgent(signal_bus=signal_bus)
    logger.info("Context agent started (interval=%ds)", CONTEXT_AGENT_INTERVAL)

    while not shutdown_event.is_set():
        try:
            await agent.run_cycle()
        except Exception:
            logger.exception("Context agent cycle failed")

        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=CONTEXT_AGENT_INTERVAL,
            )
            break  # shutdown requested
        except asyncio.TimeoutError:
            pass  # normal — time for next cycle

    logger.info("Context agent stopped after %d cycles", agent._cycle_count)
