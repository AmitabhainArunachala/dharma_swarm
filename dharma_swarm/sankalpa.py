"""SANKALPA -- accountability concierge for dharma_swarm agents.

One call to ``onboard_agent()`` plugs a new agent into the full accountability
stack (AgentRegistry, StigmergyStore, witness logs, commitment tracking).
The returned ``SankalpaHandle`` gives the agent a clean interface for making
and fulfilling commitments, logging actions, reading its own history, and
leaving stigmergy marks.

``audit_agent()`` and ``audit_fleet()`` provide external oversight without
needing the agent's handle.

All timestamps are ISO-8601 UTC (JIKOKU protocol).
Commitments stored as JSONL at ``~/.dharma/sankalpa/{name}/commitments.jsonl``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DHARMA_HOME = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
_SANKALPA_DIR = _DHARMA_HOME / "sankalpa"
_WITNESS_DIR = _DHARMA_HOME / "witness"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jikoku() -> str:
    return _utc_now().isoformat()


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


@dataclass
class SankalpaScorecard:
    """Objective accountability report for an agent."""

    agent_name: str
    total_actions: int
    success_rate: float
    commitments_made: int
    commitments_fulfilled: int
    commitments_overdue: int
    fulfillment_rate: float
    mean_quality: float
    fitness_trend: str  # "improving" | "stable" | "declining" | "insufficient_data"
    total_cost_usd: float
    total_tokens: int
    active_commitments: list[dict] = field(default_factory=list)
    recent_actions: list[dict] = field(default_factory=list)
    days_active: float = 0.0
    sankalpa_statement: str = ""


# ---------------------------------------------------------------------------
# Handle
# ---------------------------------------------------------------------------


@dataclass
class SankalpaHandle:
    """Agent's accountability interface returned by ``onboard_agent()``."""

    name: str
    agent_dir: Path
    sankalpa_dir: Path
    _registry_dir: Path | None = field(default=None, repr=False)

    # -- commitments ---------------------------------------------------------

    async def commit(self, promise: str, deadline_hours: float = 24.0) -> str:
        """Record a commitment. Returns commitment_id."""
        from dharma_swarm.models import _new_id

        cid = f"cmt_{_new_id()}"
        now = _jikoku()
        deadline = (_utc_now() + timedelta(hours=deadline_hours)).isoformat()
        entry = {
            "commitment_id": cid,
            "promise": promise,
            "status": "active",
            "created_at": now,
            "deadline": deadline,
            "fulfilled_at": None,
            "evidence": None,
            "progress_pct": 0.0,
            "progress_notes": [],
        }
        _append_jsonl(self._commitments_path, entry)
        logger.info("SANKALPA [%s] committed: %s (deadline %s)", self.name, promise, deadline)
        return cid

    async def fulfill(self, commitment_id: str, evidence: str = "") -> None:
        """Mark a commitment as fulfilled with evidence."""
        entries = _read_jsonl(self._commitments_path)
        found = False
        for entry in entries:
            if entry.get("commitment_id") == commitment_id:
                entry["status"] = "fulfilled"
                entry["fulfilled_at"] = _jikoku()
                entry["evidence"] = evidence
                entry["progress_pct"] = 100.0
                found = True
                break

        if not found:
            raise ValueError(f"Commitment '{commitment_id}' not found for agent '{self.name}'.")

        self._rewrite_commitments(entries)
        logger.info("SANKALPA [%s] fulfilled: %s", self.name, commitment_id)

    async def report_progress(
        self, commitment_id: str, progress: str, pct: float = 0.0
    ) -> None:
        """Report incremental progress on a commitment."""
        entries = _read_jsonl(self._commitments_path)
        found = False
        for entry in entries:
            if entry.get("commitment_id") == commitment_id:
                entry["progress_pct"] = min(pct, 100.0)
                notes = entry.get("progress_notes", [])
                notes.append({"ts": _jikoku(), "note": progress, "pct": pct})
                entry["progress_notes"] = notes
                found = True
                break

        if not found:
            raise ValueError(f"Commitment '{commitment_id}' not found for agent '{self.name}'.")

        self._rewrite_commitments(entries)

    # -- action logging ------------------------------------------------------

    async def log_action(
        self,
        action: str,
        success: bool,
        tokens: int = 0,
        cost_usd: float = 0.0,
        quality: float = 0.0,
    ) -> None:
        """Log a completed action (wraps AgentRegistry.log_task)."""
        from dharma_swarm.agent_registry import AgentRegistry

        registry = AgentRegistry(agents_dir=self._registry_dir)
        registry.log_task(
            name=self.name,
            task=action,
            success=success,
            tokens=tokens,
            latency_ms=0.0,
            response_preview="",
        )

    # -- self-awareness ------------------------------------------------------

    async def get_own_history(self, limit: int = 50) -> list[dict]:
        """Agent reads its own task log -- self-awareness of past performance."""
        task_log = self.agent_dir / "task_log.jsonl"
        entries = _read_jsonl(task_log)
        return entries[-limit:]

    async def get_own_commitments(self, status: str = "all") -> list[dict]:
        """Agent reads its own commitments -- what it promised to do."""
        entries = _read_jsonl(self._commitments_path)
        now = _utc_now()

        # Mark overdue active commitments
        for entry in entries:
            if entry.get("status") == "active":
                deadline_str = entry.get("deadline", "")
                if deadline_str:
                    try:
                        deadline = datetime.fromisoformat(deadline_str)
                        if now > deadline:
                            entry["status"] = "overdue"
                    except (ValueError, TypeError):
                        pass

        if status == "all":
            return entries
        return [e for e in entries if e.get("status") == status]

    # -- stigmergy -----------------------------------------------------------

    async def leave_trace(self, observation: str, salience: float = 0.5) -> None:
        """Leave a stigmergy mark (wraps StigmergyStore.leave_mark)."""
        from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

        store = StigmergyStore(base_path=self.sankalpa_dir.parent.parent / "stigmergy")
        mark = StigmergicMark(
            agent=self.name,
            file_path=f"sankalpa/{self.name}",
            action="write",
            observation=observation,
            salience=salience,
        )
        await store.leave_mark(mark)

    # -- witness -------------------------------------------------------------

    async def witness(self, event: str, detail: str) -> None:
        """Write to the witness log."""
        today = _utc_now().strftime("%Y-%m-%d")
        witness_path = _WITNESS_DIR / f"{today}.jsonl"
        entry = {
            "timestamp": _jikoku(),
            "agent": self.name,
            "event": event,
            "detail": detail,
            "source": "sankalpa",
        }
        _append_jsonl(witness_path, entry)

    # -- scorecard -----------------------------------------------------------

    async def get_scorecard(self) -> SankalpaScorecard:
        """Get the agent's full accountability scorecard."""
        return await _build_scorecard(self.name, self._registry_dir)

    # -- internals -----------------------------------------------------------

    @property
    def _commitments_path(self) -> Path:
        return self.sankalpa_dir / "commitments.jsonl"

    def _rewrite_commitments(self, entries: list[dict[str, Any]]) -> None:
        """Rewrite the entire commitments JSONL (for status updates)."""
        path = self._commitments_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


async def onboard_agent(
    name: str,
    role: str,
    model: str = "anthropic/claude-sonnet-4",
    provider: str = "openrouter",
    system_prompt: str = "",
    sankalpa_statement: str = "",
    wake_interval: float = 3600.0,
    budget_daily_usd: float = 1.0,
    *,
    registry_dir: Path | None = None,
    stigmergy_dir: Path | None = None,
) -> SankalpaHandle:
    """One-call full wiring of a new agent into the accountability stack.

    Steps:
        1. Register in AgentRegistry.
        2. Create SANKALPA commitment directory and metadata.
        3. Initialize fitness baseline snapshot.
        4. Leave an initial stigmergy mark announcing the agent.
        5. Write a witness log entry recording the onboarding.
        6. Return a SankalpaHandle.

    Args:
        name: Unique agent identifier.
        role: Maps to AgentRole (e.g. "researcher", "coder").
        model: LLM model identifier.
        provider: LLM provider name.
        system_prompt: Agent's system prompt.
        sankalpa_statement: What this agent commits to doing.
        wake_interval: Seconds between wake cycles.
        budget_daily_usd: Daily budget cap for this agent.
        registry_dir: Override AgentRegistry agents dir (for testing).
        stigmergy_dir: Override StigmergyStore base path (for testing).

    Returns:
        SankalpaHandle with methods for the agent to use.
    """
    from dharma_swarm.agent_registry import AgentRegistry
    from dharma_swarm.stigmergy import StigmergicMark, StigmergyStore

    # 1. Register in AgentRegistry
    registry = AgentRegistry(agents_dir=registry_dir)
    registry.register_agent(
        name=name,
        role=role,
        model=model,
        system_prompt=system_prompt,
    )
    agent_dir = registry._agent_dir(name)

    # 2. Create SANKALPA commitment dir + metadata
    sankalpa_dir = _SANKALPA_DIR / name
    sankalpa_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "name": name,
        "role": role,
        "model": model,
        "provider": provider,
        "sankalpa_statement": sankalpa_statement,
        "wake_interval": wake_interval,
        "budget_daily_usd": budget_daily_usd,
        "onboarded_at": _jikoku(),
    }
    meta_path = sankalpa_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 3. Initialize fitness baseline snapshot
    registry.update_fitness_history(name)

    # 4. Leave an initial stigmergy mark
    store = StigmergyStore(base_path=stigmergy_dir)
    observation = (
        f"Agent '{name}' onboarded with role={role}, model={model}. "
        f"Sankalpa: {sankalpa_statement or 'none stated'}. "
        f"Wake interval: {wake_interval}s."
    )
    mark = StigmergicMark(
        agent=name,
        file_path=f"sankalpa/{name}",
        action="write",
        observation=observation,
        salience=0.7,
    )
    await store.leave_mark(mark)

    # 5. Write witness log entry
    today = _utc_now().strftime("%Y-%m-%d")
    witness_path = _WITNESS_DIR / f"{today}.jsonl"
    witness_entry = {
        "timestamp": _jikoku(),
        "agent": name,
        "event": "onboarded",
        "detail": f"Role={role}, model={model}, sankalpa={sankalpa_statement!r}",
        "source": "sankalpa",
    }
    _append_jsonl(witness_path, witness_entry)

    # 6. Return handle
    handle = SankalpaHandle(
        name=name,
        agent_dir=agent_dir,
        sankalpa_dir=sankalpa_dir,
        _registry_dir=registry_dir,
    )

    logger.info(
        "SANKALPA onboarded agent '%s' (role=%s, model=%s, sankalpa=%r)",
        name, role, model, sankalpa_statement,
    )
    return handle


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def _build_scorecard(
    name: str,
    registry_dir: Path | None = None,
) -> SankalpaScorecard:
    """Build a SankalpaScorecard for a named agent."""
    from dharma_swarm.agent_registry import AgentRegistry

    registry = AgentRegistry(agents_dir=registry_dir)

    # Fitness data from registry
    fitness = registry.get_agent_fitness(name)
    identity = registry.load_agent(name)

    # Commitment data from SANKALPA dir
    sankalpa_dir = _SANKALPA_DIR / name
    commitments_path = sankalpa_dir / "commitments.jsonl"
    all_commitments = _read_jsonl(commitments_path)

    now = _utc_now()

    # Classify commitments
    fulfilled = 0
    overdue = 0
    active_list: list[dict] = []
    for c in all_commitments:
        status = c.get("status", "active")
        if status == "fulfilled":
            fulfilled += 1
        elif status in ("active", "overdue"):
            deadline_str = c.get("deadline", "")
            if deadline_str:
                try:
                    deadline = datetime.fromisoformat(deadline_str)
                    if now > deadline:
                        status = "overdue"
                        overdue += 1
                    else:
                        active_list.append(c)
                except (ValueError, TypeError):
                    active_list.append(c)
            else:
                active_list.append(c)
        # Already marked overdue from a previous pass
        if status == "overdue" and c not in active_list:
            if c.get("status") != "fulfilled":
                pass  # already counted

    # Re-count overdue properly
    overdue_count = 0
    active_commitments: list[dict] = []
    for c in all_commitments:
        s = c.get("status", "active")
        if s == "fulfilled":
            continue
        deadline_str = c.get("deadline", "")
        if deadline_str:
            try:
                dl = datetime.fromisoformat(deadline_str)
                if now > dl:
                    overdue_count += 1
                else:
                    active_commitments.append(c)
            except (ValueError, TypeError):
                active_commitments.append(c)
        else:
            active_commitments.append(c)

    total_made = len(all_commitments)
    fulfillment_rate = (fulfilled / total_made) if total_made > 0 else 0.0

    # Task log for recent actions
    task_log_path = registry._task_log_path(name)
    all_tasks = _read_jsonl(task_log_path)
    recent = all_tasks[-10:]

    # Fitness trend from history
    fitness_history = registry.get_fitness_history(name)
    if len(fitness_history) >= 3:
        recent_composites = [
            h.get("composite_fitness", 0.0) for h in fitness_history[-5:]
        ]
        if len(recent_composites) >= 2:
            first_half = sum(recent_composites[: len(recent_composites) // 2]) / max(
                len(recent_composites) // 2, 1
            )
            second_half = sum(recent_composites[len(recent_composites) // 2 :]) / max(
                len(recent_composites) - len(recent_composites) // 2, 1
            )
            if second_half > first_half + 0.01:
                trend = "improving"
            elif second_half < first_half - 0.01:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
    else:
        trend = "insufficient_data"

    # Days active
    created_at_str = (identity or {}).get("created_at", "")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
            days_active = (now - created_at).total_seconds() / 86400.0
        except (ValueError, TypeError):
            days_active = 0.0
    else:
        days_active = 0.0

    # Sankalpa statement from metadata
    meta_path = sankalpa_dir / "metadata.json"
    sankalpa_statement = ""
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            sankalpa_statement = meta.get("sankalpa_statement", "")
        except Exception:
            pass

    return SankalpaScorecard(
        agent_name=name,
        total_actions=fitness.get("total_calls", 0),
        success_rate=fitness.get("success_rate", 0.0),
        commitments_made=total_made,
        commitments_fulfilled=fulfilled,
        commitments_overdue=overdue_count,
        fulfillment_rate=round(fulfillment_rate, 4),
        mean_quality=fitness.get("avg_quality", 0.0),
        fitness_trend=trend,
        total_cost_usd=fitness.get("total_cost_usd", 0.0),
        total_tokens=fitness.get("total_tokens", 0),
        active_commitments=active_commitments,
        recent_actions=recent,
        days_active=round(days_active, 2),
        sankalpa_statement=sankalpa_statement,
    )


async def audit_agent(
    name: str,
    *,
    registry_dir: Path | None = None,
) -> SankalpaScorecard:
    """Get any agent's scorecard without needing their handle. For oversight."""
    return await _build_scorecard(name, registry_dir=registry_dir)


async def audit_fleet(
    *,
    registry_dir: Path | None = None,
) -> list[SankalpaScorecard]:
    """Get scorecards for all onboarded agents, sorted by fulfillment rate."""
    if not _SANKALPA_DIR.exists():
        return []

    scorecards: list[SankalpaScorecard] = []
    for child in sorted(_SANKALPA_DIR.iterdir()):
        if child.is_dir():
            name = child.name
            try:
                sc = await _build_scorecard(name, registry_dir=registry_dir)
                scorecards.append(sc)
            except Exception as exc:
                logger.warning("Failed to build scorecard for '%s': %s", name, exc)

    scorecards.sort(key=lambda s: s.fulfillment_rate, reverse=True)
    return scorecards
