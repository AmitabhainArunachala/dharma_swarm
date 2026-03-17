"""Truth-surface builders for the dashboard module view.

This module reads the same runtime files an operator would inspect by hand and
packages them into simple, drillable module summaries for the UI.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any


HOME = Path.home()
STATE = HOME / ".dharma"
_MODULE_CACHE: dict[str, Any] = {"built_at": 0.0, "data": []}
_PS_CACHE: dict[str, Any] = {"built_at": 0.0, "rows": []}
_LSOF_CACHE: dict[int, list[str]] = {}


@dataclass(slots=True)
class Candidate:
    score: float
    data: dict[str, Any]


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


def _age_hours(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return None
    return max(
        (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        / 3600.0,
        0.0,
    )


def _recency_score(iso_ts: str | None) -> float:
    hours = _age_hours(iso_ts)
    if hours is None:
        return 0.0
    if hours <= 1:
        return 12.0
    if hours <= 6:
        return 9.0
    if hours <= 24:
        return 7.0
    if hours <= 72:
        return 4.0
    if hours <= 168:
        return 2.0
    return 0.0


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def _tail_lines(path: Path, limit: int = 5) -> list[str]:
    if not path.exists():
        return []
    lines: deque[str] = deque(maxlen=limit)
    try:
        with path.open("r", errors="ignore") as handle:
            for line in handle:
                line = line.rstrip()
                if line:
                    lines.append(line)
    except Exception:
        return []
    return list(lines)


def _latest_heading_lines(path: Path, limit: int = 5) -> list[str]:
    lines = [line.strip() for line in _safe_read_text(path).splitlines() if line.startswith("## ")]
    return lines[-limit:]


def _path_record(label: str, path: Path, kind: str = "project") -> dict[str, Any]:
    exists = path.exists()
    modified_at = _iso_from_ts(path.stat().st_mtime) if exists else None
    return {
        "label": label,
        "path": str(path),
        "exists": exists,
        "kind": kind,
        "modified_at": modified_at,
    }


def _file_metric(path: Path) -> tuple[str | None, int]:
    if not path.exists():
        return None, 0
    return _iso_from_ts(path.stat().st_mtime), path.stat().st_size


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", errors="ignore") as handle:
            return sum(1 for _ in handle)
    except Exception:
        return 0


def _count_words(path: Path) -> int:
    return len(_safe_read_text(path).split())


def _tail_jsonl(path: Path, limit: int = 5) -> list[dict[str, Any]]:
    entries: deque[dict[str, Any]] = deque(maxlen=limit)
    if not path.exists():
        return []
    try:
        with path.open("r", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return list(entries)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _ps_rows() -> list[tuple[int, str]]:
    cache_age = time.time() - float(_PS_CACHE.get("built_at", 0.0))
    if cache_age < 2.0 and _PS_CACHE.get("rows"):
        return list(_PS_CACHE["rows"])

    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []

    rows: list[tuple[int, str]] = []
    for raw in proc.stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1] if len(parts) > 1 else ""
        rows.append((pid, command))
    _PS_CACHE["built_at"] = time.time()
    _PS_CACHE["rows"] = rows
    return rows


def _pid_live(pid: int | None) -> bool:
    if pid is None:
        return False
    return any(row_pid == pid for row_pid, _ in _ps_rows())


def _pid_command(pid: int | None) -> str | None:
    if pid is None:
        return None
    for row_pid, command in _ps_rows():
        if row_pid == pid:
            return command
    return None


def _lsof_paths(pid: int | None) -> list[str]:
    if pid is None:
        return []
    if pid in _LSOF_CACHE:
        return list(_LSOF_CACHE[pid])
    try:
        proc = subprocess.run(
            ["lsof", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []

    observed: list[str] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        observed.append(parts[-1])
    _LSOF_CACHE[pid] = observed
    return observed


def _discover_processes(
    *,
    contains: list[str],
    cwd_hint: str | None = None,
    source: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for pid, command in _ps_rows():
        lowered = command.lower()
        if not all(token.lower() in lowered for token in contains):
            continue
        observed_paths = _lsof_paths(pid) if cwd_hint else []
        if cwd_hint and not any(cwd_hint in path for path in observed_paths):
            continue
        results.append(
            {
                "pid": pid,
                "live": True,
                "source": source,
                "command": command,
                "observed_paths": observed_paths[:6],
            }
        )
    return results


def _history_event(
    *,
    title: str,
    detail: str,
    source: str,
    timestamp: str | None = None,
    status: str = "info",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "title": title,
        "detail": detail,
        "source": source,
        "status": status,
    }


def _candidate_from_file(
    *,
    title: str,
    path: Path,
    reason: str,
    kind: str = "file",
    bonus: float = 0.0,
) -> Candidate:
    timestamp = _iso_from_ts(path.stat().st_mtime) if path.exists() else None
    detail = reason if path.exists() else f"Missing: {reason}"
    score = _recency_score(timestamp) + bonus + (1.5 if path.exists() else 0.5)
    return Candidate(
        score=score,
        data={
            "kind": kind,
            "title": title,
            "detail": detail,
            "path": str(path),
            "timestamp": timestamp,
            "reason": reason,
            "score": round(score, 2),
        },
    )


def _candidate_from_event(
    *,
    title: str,
    detail: str,
    source: str,
    timestamp: str | None,
    status: str = "info",
    bonus: float = 0.0,
) -> Candidate:
    score = _recency_score(timestamp) + bonus + (2.0 if status in {"broken", "warn"} else 1.0)
    return Candidate(
        score=score,
        data={
            "kind": "history",
            "title": title,
            "detail": detail,
            "path": source,
            "timestamp": timestamp,
            "reason": source,
            "score": round(score, 2),
        },
    )


def _select_salient(candidates: list[Candidate], limit: int = 10) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    return [candidate.data for candidate in ordered[:limit]]


def _latest_paths(pattern: str, limit: int = 5) -> list[Path]:
    paths = sorted(HOME.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return paths[:limit]


def _control_plane_module() -> dict[str, Any]:
    daemon_log = STATE / "logs" / "daemon.log"
    runtime_db = STATE / "db" / "memory.db"
    daemon_pid_file = STATE / "daemon.pid"
    orchestrator_pid_file = STATE / "orchestrator.pid"
    sentinel_pid_file = STATE / "sentinel.pid"
    orchestrator_state = STATE / "orchestrator_state.json"
    task_counts = STATE / "shared" / "task_status_counts.json"
    latest_notes = _latest_paths(".dharma/shared/*_notes.md", limit=4)
    witness_today = max(
        _latest_paths(".dharma/witness/witness_*.jsonl", limit=1),
        default=None,
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
    )

    processes = _discover_processes(
        contains=["swarmmanager", "await swarm.run(interval=60)"],
        source="process-discovery",
    )

    pid_history: list[dict[str, Any]] = []
    for label, pid_file in (
        ("daemon.pid", daemon_pid_file),
        ("orchestrator.pid", orchestrator_pid_file),
        ("sentinel.pid", sentinel_pid_file),
    ):
        pid = _read_pid(pid_file)
        live = _pid_live(pid)
        pid_history.append(
            _history_event(
                title=f"{label} {'live' if live else 'stale'}",
                detail=f"{label} -> {pid if pid is not None else 'missing'}",
                source=str(pid_file),
                timestamp=_iso_from_ts(pid_file.stat().st_mtime) if pid_file.exists() else None,
                status="ok" if live else "broken",
            )
        )

    log_tail = _tail_lines(daemon_log, limit=5)
    history = pid_history + [
        _history_event(
            title="Daemon log",
            detail=line,
            source=str(daemon_log),
            timestamp=_iso_from_ts(daemon_log.stat().st_mtime) if daemon_log.exists() else None,
        )
        for line in log_tail
    ]

    if orchestrator_state.exists():
        state = _read_json(orchestrator_state)
        history.append(
            _history_event(
                title="Orchestrator state snapshot",
                detail=f"last_run={state.get('last_run', 'unknown')}, agents_spawned={state.get('agents_spawned', 'unknown')}",
                source=str(orchestrator_state),
                timestamp=_iso_from_ts(orchestrator_state.stat().st_mtime),
                status="warn",
            )
        )

    task_snapshot = _read_json(task_counts)
    last_activity = None
    if runtime_db.exists():
        last_activity = _iso_from_ts(runtime_db.stat().st_mtime)
    elif daemon_log.exists():
        last_activity = _iso_from_ts(daemon_log.stat().st_mtime)

    status = "active" if processes and _recency_score(last_activity) >= 7 else "stale"
    status_reason = "Live swarm daemon found from process table."
    if any(event["status"] == "broken" for event in pid_history):
        status = "mixed" if status == "active" else "broken"
        status_reason = "Live daemon exists, but canonical PID files are stale."

    salient: list[Candidate] = [
        _candidate_from_file(
            title="Swarm daemon log",
            path=daemon_log,
            reason="Current control-plane execution log.",
            bonus=4.0,
        ),
        _candidate_from_file(
            title="Runtime memory DB",
            path=runtime_db,
            reason="Live SQLite state used by the running daemon.",
            bonus=3.0,
        ),
        _candidate_from_file(
            title="Daemon PID file",
            path=daemon_pid_file,
            reason="Canonical PID surface checked by operators.",
            kind="state",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="Orchestrator state",
            path=orchestrator_state,
            reason="Derived orchestrator status snapshot.",
            kind="state",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="Task status counts",
            path=task_counts,
            reason="Queue summary used by the shared UI/state layer.",
            kind="state",
            bonus=1.0,
        ),
        _candidate_from_file(
            title="Swarm source",
            path=HOME / "dharma_swarm" / "dharma_swarm" / "swarm.py",
            reason="Primary swarm runtime implementation.",
            kind="source",
        ),
        _candidate_from_file(
            title="Orchestrator source",
            path=HOME / "dharma_swarm" / "dharma_swarm" / "orchestrator.py",
            reason="Task dispatch/orchestration logic.",
            kind="source",
        ),
    ]
    for note in latest_notes:
        salient.append(
            _candidate_from_file(
                title=note.name,
                path=note,
                reason="Shared agent note updated by the control plane.",
                bonus=2.5,
            )
        )
    if witness_today is not None:
        salient.append(
            _candidate_from_file(
                title=witness_today.name,
                path=witness_today,
                reason="Current witness ledger for operator-visible history.",
                bonus=2.5,
            )
        )
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                status=event["status"],
                bonus=1.5 if event["status"] == "broken" else 0.5,
            )
        )

    return {
        "id": "control_plane",
        "name": "Control Plane",
        "status": status,
        "live": bool(processes),
        "summary": "Swarm daemon, orchestrator state, shared notes, and witness/control logs.",
        "status_reason": status_reason,
        "last_activity": last_activity,
        "metrics": {
            "live_processes": str(len(processes)),
            "latest_notes": latest_notes[0].name if latest_notes else "none",
            "task_snapshot": (
                f"{task_snapshot.get('completed', 0)} completed / {task_snapshot.get('failed', 0)} failed"
                if task_snapshot
                else "missing"
            ),
            "witness_today": witness_today.name if witness_today else "missing",
        },
        "processes": processes,
        "projects": [
            _path_record("dharma_swarm repo", HOME / "dharma_swarm", "project"),
            _path_record("runtime state", STATE, "state"),
            _path_record("swarm.py", HOME / "dharma_swarm" / "dharma_swarm" / "swarm.py", "source"),
            _path_record("orchestrator.py", HOME / "dharma_swarm" / "dharma_swarm" / "orchestrator.py", "source"),
            _path_record("daemon.log", daemon_log, "log"),
            _path_record("db/memory.db", runtime_db, "artifact"),
        ],
        "wiring": [
            {"direction": "writes", "target": "~/.dharma/shared/*_notes.md", "detail": "shared agent notes for operator review"},
            {"direction": "writes", "target": "~/.dharma/witness/witness_*.jsonl", "detail": "append-only witness trail"},
            {"direction": "writes", "target": "~/.dharma/stigmergy/marks.jsonl", "detail": "stigmergic coordination surface"},
            {"direction": "feeds", "target": "Living Layers", "detail": "task completions and notes become marks and witness events"},
            {"direction": "feeds", "target": "Trishula", "detail": "tasks and notes consume inbox-triggered work"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _living_layers_module() -> dict[str, Any]:
    living_state = STATE / "living_state.json"
    marks = STATE / "stigmergy" / "marks.jsonl"
    hum = STATE / "subconscious" / "hum.jsonl"
    journal = STATE / "subconscious" / "journal" / "LATEST_JOURNAL.md"
    witness_dir = STATE / "witness"
    state = _read_json(living_state)
    last_shakti_raw = state.get("last_shakti_at")
    last_shakti = None
    if isinstance(last_shakti_raw, (int, float)) and last_shakti_raw > 0:
        last_shakti = datetime.fromtimestamp(last_shakti_raw, tz=timezone.utc).isoformat(
            timespec="seconds"
        )

    recent_marks = _tail_jsonl(marks, limit=3)
    recent_hum = _tail_jsonl(hum, limit=3)
    mark_count = _count_lines(marks)
    hum_count = _count_lines(hum)
    last_activity = None
    for path in (marks, hum, journal):
        if path.exists():
            modified_at = _iso_from_ts(path.stat().st_mtime)
            if not last_activity or _age_hours(modified_at) is not None and _age_hours(modified_at) < _age_hours(last_activity):
                last_activity = modified_at

    active_marks = _recency_score(_iso_from_ts(marks.stat().st_mtime) if marks.exists() else None) >= 7
    active_hum = _recency_score(_iso_from_ts(hum.stat().st_mtime) if hum.exists() else None) >= 7
    shakti_fresh = _recency_score(last_shakti) >= 7

    if active_marks or active_hum:
        status = "active" if shakti_fresh else "mixed"
    else:
        status = "stale"

    history: list[dict[str, Any]] = []
    if last_shakti:
        history.append(
            _history_event(
                title="Shakti heartbeat",
                detail=f"last_shakti_at={last_shakti}",
                source=str(living_state),
                timestamp=last_shakti,
                status="ok" if shakti_fresh else "warn",
            )
        )
    for entry in recent_marks:
        history.append(
            _history_event(
                title="Stigmergy mark",
                detail=entry.get("observation", ""),
                source=str(marks),
                timestamp=entry.get("timestamp"),
            )
        )
    for entry in recent_hum:
        history.append(
            _history_event(
                title="HUM resonance",
                detail=entry.get("description", ""),
                source=str(hum),
                timestamp=entry.get("timestamp"),
            )
        )
    if journal.exists():
        history.append(
            _history_event(
                title="Journal snapshot",
                detail=_tail_lines(journal, limit=1)[0] if _tail_lines(journal, limit=1) else journal.name,
                source=str(journal),
                timestamp=_iso_from_ts(journal.stat().st_mtime),
                status="ok" if _recency_score(_iso_from_ts(journal.stat().st_mtime)) >= 7 else "warn",
            )
        )

    salient: list[Candidate] = [
        _candidate_from_file(
            title="marks.jsonl",
            path=marks,
            reason="Primary stigmergy ledger for cross-agent coordination.",
            bonus=4.0,
        ),
        _candidate_from_file(
            title="hum.jsonl",
            path=hum,
            reason="Subconscious dream/resonance stream.",
            bonus=4.0,
        ),
        _candidate_from_file(
            title="LATEST_JOURNAL.md",
            path=journal,
            reason="Most recent hypnagogic journal output.",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="living_state.json",
            path=living_state,
            reason="Shakti/living-layer heartbeat state.",
            kind="state",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="stigmergy.py",
            path=HOME / "dharma_swarm" / "dharma_swarm" / "stigmergy.py",
            reason="Stigmergy implementation.",
            kind="source",
        ),
        _candidate_from_file(
            title="subconscious.py",
            path=HOME / "dharma_swarm" / "dharma_swarm" / "subconscious.py",
            reason="Subconscious dream stream implementation.",
            kind="source",
        ),
        _candidate_from_file(
            title="shakti.py",
            path=HOME / "dharma_swarm" / "dharma_swarm" / "shakti.py",
            reason="Shakti perception loop implementation.",
            kind="source",
        ),
    ]
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                status=event["status"],
                bonus=1.0,
            )
        )

    return {
        "id": "living_layers",
        "name": "Living Layers",
        "status": status,
        "live": active_marks or active_hum,
        "summary": "Stigmergy, subconscious HUM, shakti heartbeat, journal, and witness-linked resonance.",
        "status_reason": (
            "Marks and HUM are fresh, but Shakti is stale."
            if status == "mixed"
            else "Recent marks/HUM activity found."
            if status == "active"
            else "No fresh living-layer writes found."
        ),
        "last_activity": last_activity,
        "metrics": {
            "marks": str(mark_count),
            "hum_entries": str(hum_count),
            "last_shakti": last_shakti or "missing",
            "journal": journal.name if journal.exists() else "missing",
        },
        "processes": [],
        "projects": [
            _path_record("stigmergy", STATE / "stigmergy", "state"),
            _path_record("subconscious", STATE / "subconscious", "state"),
            _path_record("witness", witness_dir, "state"),
            _path_record("living_state.json", living_state, "state"),
            _path_record("marks.jsonl", marks, "artifact"),
            _path_record("hum.jsonl", hum, "artifact"),
        ],
        "wiring": [
            {"direction": "reads", "target": "~/.dharma/stigmergy/marks.jsonl", "detail": "subconscious and shakti scan recent marks"},
            {"direction": "writes", "target": "~/.dharma/subconscious/hum.jsonl", "detail": "dream associations and resonance events"},
            {"direction": "writes", "target": "~/.dharma/subconscious/journal/LATEST_JOURNAL.md", "detail": "latest journal handoff"},
            {"direction": "feeds", "target": "Morning Brief", "detail": "journal path is read by the morning brief job"},
            {"direction": "feeds", "target": "Control Plane", "detail": "dream marks re-enter stigmergy and witness"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _mycelium_module() -> dict[str, Any]:
    root = STATE / "mycelium"
    daemon_pid = root / "daemon.pid"
    daemon_log = root / "logs" / "daemon.log"
    stderr_log = root / "logs" / "launchd_stderr.log"
    synthesis_log = root / "results" / "synthesis_log.jsonl"
    canonical_pid = _read_pid(daemon_pid)
    canonical_process = {
        "pid": canonical_pid or 0,
        "live": _pid_live(canonical_pid),
        "source": str(daemon_pid),
        "command": _pid_command(canonical_pid),
        "observed_paths": _lsof_paths(canonical_pid)[:6] if canonical_pid else [],
    } if canonical_pid is not None else None

    discovered = _discover_processes(
        contains=[".dharma/mycelium/daemon.py"],
        source="process-discovery",
    )
    processes = discovered
    if canonical_process and not any(item["pid"] == canonical_process["pid"] for item in processes):
        processes.insert(0, canonical_process)

    history = [
        _history_event(
            title="Mycelium log",
            detail=line,
            source=str(daemon_log),
            timestamp=_iso_from_ts(daemon_log.stat().st_mtime) if daemon_log.exists() else None,
        )
        for line in _tail_lines(daemon_log, limit=5)
    ]
    for entry in _tail_jsonl(synthesis_log, limit=2):
        history.append(
            _history_event(
                title="Synthesis result",
                detail=entry.get("raw_response", "")[:220],
                source=str(synthesis_log),
                timestamp=entry.get("timestamp"),
            )
        )

    daemon_ts = _iso_from_ts(daemon_log.stat().st_mtime) if daemon_log.exists() else None
    status = "active" if processes and _recency_score(daemon_ts) >= 7 else "stale"
    status_reason = "Live mycelium daemon with fresh log activity." if status == "active" else "No fresh mycelium daemon activity found."

    salient: list[Candidate] = [
        _candidate_from_file(
            title="mycelium daemon.log",
            path=daemon_log,
            reason="Primary mycelium runtime log.",
            bonus=4.0,
        ),
        _candidate_from_file(
            title="launchd stderr",
            path=stderr_log,
            reason="Launchd stderr surface for mycelium.",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="synthesis_log.jsonl",
            path=synthesis_log,
            reason="Structured synthesis outputs from mycelium.",
            bonus=2.5,
        ),
        _candidate_from_file(
            title="mycelium daemon.pid",
            path=daemon_pid,
            reason="Canonical mycelium PID file.",
            kind="state",
            bonus=1.0,
        ),
        _candidate_from_file(
            title="mycelium daemon.py",
            path=root / "daemon.py",
            reason="Mycelium daemon source.",
            kind="source",
        ),
    ]
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                bonus=1.0,
            )
        )

    return {
        "id": "mycelium",
        "name": "Mycelium",
        "status": status,
        "live": bool(processes),
        "summary": "Skill-health, catalytic graph, and stigmergy maintenance daemon under ~/.dharma/mycelium.",
        "status_reason": status_reason,
        "last_activity": daemon_ts,
        "metrics": {
            "live_processes": str(len(processes)),
            "canonical_pid": str(canonical_pid) if canonical_pid is not None else "missing",
            "results_lines": str(_count_lines(synthesis_log)),
            "stderr_words": str(_count_words(stderr_log)) if stderr_log.exists() else "0",
        },
        "processes": processes,
        "projects": [
            _path_record("mycelium root", root, "project"),
            _path_record("daemon.py", root / "daemon.py", "source"),
            _path_record("daemon.log", daemon_log, "log"),
            _path_record("launchd_stderr.log", stderr_log, "log"),
            _path_record("synthesis_log.jsonl", synthesis_log, "artifact"),
        ],
        "wiring": [
            {"direction": "reads", "target": "~/.codex/skills", "detail": "skill health scan references installed skills"},
            {"direction": "writes", "target": "~/.dharma/mycelium/logs/daemon.log", "detail": "runtime health and catalytic-update log"},
            {"direction": "feeds", "target": "Living Layers", "detail": "recent log lines show stigmergy maintenance activity"},
            {"direction": "writes", "target": "~/.dharma/mycelium/results/synthesis_log.jsonl", "detail": "structured synthesis outputs"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _trishula_module() -> dict[str, Any]:
    trishula_root = HOME / "trishula"
    inbox = trishula_root / "inbox"
    logs = [
        trishula_root / "logs" / "router_mac.log",
        trishula_root / "logs" / "dc_router.log",
        trishula_root / "logs" / "dashboard.log",
        trishula_root / "logs" / "pipeline_sync.log",
        trishula_root / "logs" / "continuation.log",
        trishula_root / "logs" / "review.log",
    ]
    newest_log = max((path for path in logs if path.exists()), default=None, key=lambda item: item.stat().st_mtime)
    newest_inbox = max((path for path in inbox.glob("*") if path.is_file()), default=None, key=lambda item: item.stat().st_mtime) if inbox.exists() else None
    last_activity = _iso_from_ts(newest_log.stat().st_mtime) if newest_log else None
    fresh_logs = [path for path in logs if path.exists() and _recency_score(_iso_from_ts(path.stat().st_mtime)) >= 7]
    status = "active" if fresh_logs else "stale"
    history = [
        _history_event(
            title=path.name,
            detail=_tail_lines(path, limit=1)[0] if _tail_lines(path, limit=1) else path.name,
            source=str(path),
            timestamp=_iso_from_ts(path.stat().st_mtime),
        )
        for path in sorted((path for path in logs if path.exists()), key=lambda item: item.stat().st_mtime, reverse=True)[:6]
    ]

    salient: list[Candidate] = []
    for path in logs:
        salient.append(
            _candidate_from_file(
                title=path.name,
                path=path,
                reason="Trishula cron output log.",
                bonus=3.0 if path == newest_log else 1.5,
            )
        )
    if newest_inbox:
        salient.append(
            _candidate_from_file(
                title=newest_inbox.name,
                path=newest_inbox,
                reason="Newest inbox artifact feeding Trishula routing.",
                bonus=2.0,
            )
        )
    salient.extend(
        [
            _candidate_from_file(
                title="trishula root",
                path=trishula_root,
                reason="Inter-VPS messaging project root.",
                kind="project",
            ),
            _candidate_from_file(
                title="agni-workspace",
                path=HOME / "agni-workspace",
                reason="Pipeline/dashboard outputs feed AGNI mirror state.",
                kind="project",
            ),
        ]
    )
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                bonus=1.0,
            )
        )

    return {
        "id": "trishula",
        "name": "Trishula",
        "status": status,
        "live": bool(fresh_logs),
        "summary": "Inbox routing, dashboard export, continuation, review, and pipeline-sync cron surfaces.",
        "status_reason": "Fresh Trishula cron logs exist." if status == "active" else "No fresh Trishula cron logs found.",
        "last_activity": last_activity,
        "metrics": {
            "fresh_logs": str(len(fresh_logs)),
            "latest_log": newest_log.name if newest_log else "missing",
            "latest_inbox": newest_inbox.name if newest_inbox else "missing",
            "inbox_files": str(sum(1 for _ in inbox.glob("*"))) if inbox.exists() else "0",
        },
        "processes": [],
        "projects": [
            _path_record("trishula root", trishula_root, "project"),
            _path_record("inbox", inbox, "project"),
            _path_record("agni-workspace", HOME / "agni-workspace", "project"),
        ]
        + [_path_record(path.name, path, "log") for path in logs],
        "wiring": [
            {"direction": "reads", "target": "~/trishula/inbox", "detail": "router/continuation jobs scan inbox artifacts"},
            {"direction": "writes", "target": "~/trishula/logs/*.log", "detail": "router, dashboard, sync, continuation, and review logs"},
            {"direction": "feeds", "target": "AGNI workspace", "detail": "dashboard and pipeline sync reflect workspace state"},
            {"direction": "feeds", "target": "Control Plane", "detail": "inbox contents become operator-visible tasks and notes"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _pulse_cron_module() -> dict[str, Any]:
    cron_jobs = HOME / "dharma_swarm" / "cron_jobs.json"
    pulse_log = STATE / "pulse.log"
    morning_brief = STATE / "shared" / "morning_brief_2026-03-15.md"
    shared_brief = STATE / "shared" / "morning_brief.md"
    configured_brief = HOME / "dgc-core" / "daemon" / "morning_brief.md"
    jk_pulse = STATE / "shared" / "jk_pulse.md"
    pulse_lines = _tail_lines(pulse_log, limit=6)
    pulse_error = next((line for line in reversed(pulse_lines) if "Error (" in line or "ERROR" in line), "")
    brief_title = _safe_read_text(morning_brief).splitlines()[0] if morning_brief.exists() else ""
    cron_data = _safe_read_text(cron_jobs)
    enabled_jobs = cron_data.count('"enabled": true')

    last_activity = None
    for path in (morning_brief, pulse_log, shared_brief, jk_pulse):
        if path.exists():
            path_iso = _iso_from_ts(path.stat().st_mtime)
            if not last_activity or (_age_hours(path_iso) is not None and _age_hours(path_iso) < _age_hours(last_activity)):
                last_activity = path_iso

    status = "broken" if pulse_error or not configured_brief.exists() else "active"
    status_reason = (
        "Pulse log shows an execution error and configured morning brief path is missing."
        if status == "broken"
        else "Cron outputs are present."
    )

    history: list[dict[str, Any]] = []
    if pulse_error:
        history.append(
            _history_event(
                title="Pulse error",
                detail=pulse_error,
                source=str(pulse_log),
                timestamp=_iso_from_ts(pulse_log.stat().st_mtime) if pulse_log.exists() else None,
                status="broken",
            )
        )
    if morning_brief.exists():
        history.append(
            _history_event(
                title="Morning brief artifact",
                detail=brief_title or morning_brief.name,
                source=str(morning_brief),
                timestamp=_iso_from_ts(morning_brief.stat().st_mtime),
                status="warn" if "Saturday" in brief_title else "ok",
            )
        )
    history.append(
        _history_event(
            title="Configured brief target",
            detail="missing" if not configured_brief.exists() else "present",
            source=str(configured_brief),
            timestamp=_iso_from_ts(configured_brief.stat().st_mtime) if configured_brief.exists() else None,
            status="broken" if not configured_brief.exists() else "ok",
        )
    )

    salient: list[Candidate] = [
        _candidate_from_file(
            title="cron_jobs.json",
            path=cron_jobs,
            reason="Scheduler source for pulse/morning-brief/JK jobs.",
            kind="config",
            bonus=2.5,
        ),
        _candidate_from_file(
            title="pulse.log",
            path=pulse_log,
            reason="DGC Pulse runtime output.",
            bonus=3.5,
        ),
        _candidate_from_file(
            title="morning_brief_2026-03-15.md",
            path=morning_brief,
            reason="Observed morning brief artifact in shared state.",
            bonus=3.0,
        ),
        _candidate_from_file(
            title="morning_brief.md",
            path=shared_brief,
            reason="Shared canonical morning brief mirror.",
            bonus=1.5,
        ),
        _candidate_from_file(
            title="dgc-core/daemon/morning_brief.md",
            path=configured_brief,
            reason="Configured morning brief output target from cron prompt.",
            kind="state",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="jk_pulse.md",
            path=jk_pulse,
            reason="JK heartbeat consumed by morning brief.",
            bonus=1.5,
        ),
    ]
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                status=event["status"],
                bonus=1.5,
            )
        )

    return {
        "id": "pulse_cron",
        "name": "Pulse + Cron",
        "status": status,
        "live": status == "active",
        "summary": "DGC Pulse, morning brief generation, and cron-configured module wiring.",
        "status_reason": status_reason,
        "last_activity": last_activity,
        "metrics": {
            "enabled_jobs": str(enabled_jobs),
            "pulse_log_words": str(_count_words(pulse_log)) if pulse_log.exists() else "0",
            "brief_path": "missing" if not configured_brief.exists() else "present",
            "jk_pulse": _iso_from_ts(jk_pulse.stat().st_mtime) if jk_pulse.exists() else "missing",
        },
        "processes": [],
        "projects": [
            _path_record("cron_jobs.json", cron_jobs, "config"),
            _path_record("pulse.log", pulse_log, "log"),
            _path_record("morning brief (shared)", morning_brief, "artifact"),
            _path_record("morning brief (configured)", configured_brief, "artifact"),
            _path_record("jk_pulse.md", jk_pulse, "artifact"),
        ],
        "wiring": [
            {"direction": "reads", "target": "~/agni-workspace/WORKING.md", "detail": "pulse and morning brief prompts read AGNI state"},
            {"direction": "reads", "target": "~/trishula/inbox", "detail": "pulse and trishula triage consume inbox state"},
            {"direction": "reads", "target": "~/.dharma/subconscious/journal/LATEST_JOURNAL.md", "detail": "morning brief imports subconscious journal"},
            {"direction": "writes", "target": "~/.dharma/pulse.log", "detail": "pulse output surface"},
            {"direction": "writes", "target": "~/.dharma/shared/morning_brief_*.md", "detail": "observed morning brief artifact path"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _allout_module() -> dict[str, Any]:
    heartbeat = STATE / "allout_heartbeat.json"
    todo_cycles = _latest_paths(".dharma/shared/allout_todo_cycle_*.md", limit=3)
    heartbeat_data = _read_json(heartbeat)

    last_activity = _iso_from_ts(heartbeat.stat().st_mtime) if heartbeat.exists() else None
    status = "stale" if _recency_score(last_activity) < 7 else "active"
    history = [
        _history_event(
            title="Heartbeat",
            detail=f"status={heartbeat_data.get('status', 'unknown')} run_id={heartbeat_data.get('run_id', 'unknown')}",
            source=str(heartbeat),
            timestamp=heartbeat_data.get("ts_utc") or last_activity,
            status="warn" if status == "stale" else "ok",
        )
    ]
    for cycle in todo_cycles:
        history.append(
            _history_event(
                title=cycle.name,
                detail=_tail_lines(cycle, limit=1)[0] if _tail_lines(cycle, limit=1) else cycle.name,
                source=str(cycle),
                timestamp=_iso_from_ts(cycle.stat().st_mtime),
            )
        )

    salient: list[Candidate] = [
        _candidate_from_file(
            title="allout_heartbeat.json",
            path=heartbeat,
            reason="Canonical allout run heartbeat.",
            kind="state",
            bonus=3.0,
        )
    ]
    for cycle in todo_cycles:
        salient.append(
            _candidate_from_file(
                title=cycle.name,
                path=cycle,
                reason="Latest allout cycle markdown output.",
                bonus=2.0,
            )
        )
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                status=event["status"],
                bonus=1.0,
            )
        )

    return {
        "id": "allout",
        "name": "Allout",
        "status": status,
        "live": status == "active",
        "summary": "Allout heartbeat, todo-cycle markdown, and last-run evidence.",
        "status_reason": "Allout heartbeat is stale." if status == "stale" else "Fresh allout heartbeat found.",
        "last_activity": last_activity,
        "metrics": {
            "heartbeat": heartbeat_data.get("ts_utc", "missing"),
            "todo_cycles": str(len(todo_cycles)),
            "latest_cycle": todo_cycles[0].name if todo_cycles else "missing",
            "log": heartbeat_data.get("log", "missing"),
        },
        "processes": [],
        "projects": [
            _path_record("allout_heartbeat.json", heartbeat, "state"),
            _path_record("allout log", Path(heartbeat_data.get("log", "")) if heartbeat_data.get("log") else STATE / "logs" / "allout", "log"),
            _path_record("allout snapshots", Path(heartbeat_data.get("snapshots", "")) if heartbeat_data.get("snapshots") else STATE / "logs" / "allout", "artifact"),
        ]
        + [_path_record(cycle.name, cycle, "artifact") for cycle in todo_cycles],
        "wiring": [
            {"direction": "writes", "target": "~/.dharma/allout_heartbeat.json", "detail": "last allout run heartbeat"},
            {"direction": "writes", "target": "~/.dharma/shared/allout_todo_cycle_*.md", "detail": "todo-cycle markdown outputs"},
            {"direction": "writes", "target": "~/.dharma/logs/allout/*", "detail": "run log and snapshots"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def _jagat_kalyan_module() -> dict[str, Any]:
    root = HOME / "jagat_kalyan"
    scout_log = root / "SCOUT_LOG.md"
    evolution_log = root / "EVOLUTION_LOG.md"
    app_py = root / "app.py"
    matching_py = root / "matching.py"
    models_py = root / "models.py"
    spec_md = root / "WELFARE_TONS_SPEC.md"
    jk_pulse = STATE / "shared" / "jk_pulse.md"
    jk_alert = STATE / "shared" / "jk_alert.md"

    scout_headings = _latest_heading_lines(scout_log, limit=3)
    evolution_headings = _latest_heading_lines(evolution_log, limit=3)
    scout_manual = any("Manual" in heading for heading in scout_headings[-1:]) if scout_headings else False
    pulse_fresh = jk_pulse.exists() and _recency_score(_iso_from_ts(jk_pulse.stat().st_mtime)) >= 7
    latest_candidate_paths = [path for path in (scout_log, evolution_log, jk_pulse, jk_alert, app_py, matching_py, models_py, spec_md) if path.exists()]
    newest = max(latest_candidate_paths, key=lambda item: item.stat().st_mtime) if latest_candidate_paths else None
    last_activity = _iso_from_ts(newest.stat().st_mtime) if newest else None

    status = "mixed" if scout_manual or not pulse_fresh else "active"
    status_reason = (
        "Recent JK artifacts exist, but the latest scout is explicitly manual and JK pulse is stale."
        if status == "mixed"
        else "Recent JK automation artifacts found."
    )

    history: list[dict[str, Any]] = []
    for heading in scout_headings:
        history.append(
            _history_event(
                title="Scout log",
                detail=heading,
                source=str(scout_log),
                timestamp=_iso_from_ts(scout_log.stat().st_mtime) if scout_log.exists() else None,
                status="warn" if "Manual" in heading else "ok",
            )
        )
    for heading in evolution_headings:
        history.append(
            _history_event(
                title="Evolution log",
                detail=heading,
                source=str(evolution_log),
                timestamp=_iso_from_ts(evolution_log.stat().st_mtime) if evolution_log.exists() else None,
            )
        )
    if jk_pulse.exists():
        history.append(
            _history_event(
                title="JK pulse",
                detail=_safe_read_text(jk_pulse).strip(),
                source=str(jk_pulse),
                timestamp=_iso_from_ts(jk_pulse.stat().st_mtime),
                status="warn" if not pulse_fresh else "ok",
            )
        )

    salient: list[Candidate] = [
        _candidate_from_file(
            title="SCOUT_LOG.md",
            path=scout_log,
            reason="Scout history for the JK loop.",
            bonus=3.0,
        ),
        _candidate_from_file(
            title="EVOLUTION_LOG.md",
            path=evolution_log,
            reason="Codebase evolution log for JK.",
            bonus=3.0,
        ),
        _candidate_from_file(
            title="jk_pulse.md",
            path=jk_pulse,
            reason="Automated JK pulse heartbeat.",
            bonus=2.0,
        ),
        _candidate_from_file(
            title="jk_alert.md",
            path=jk_alert,
            reason="JK urgency handoff consumed by morning brief.",
            bonus=1.5,
        ),
        _candidate_from_file(
            title="app.py",
            path=app_py,
            reason="JK FastAPI application.",
            kind="source",
        ),
        _candidate_from_file(
            title="matching.py",
            path=matching_py,
            reason="JK matching engine.",
            kind="source",
        ),
        _candidate_from_file(
            title="models.py",
            path=models_py,
            reason="JK SQLAlchemy models.",
            kind="source",
        ),
        _candidate_from_file(
            title="WELFARE_TONS_SPEC.md",
            path=spec_md,
            reason="JK mathematical welfare-ton spec.",
            kind="source",
        ),
    ]
    for event in history:
        salient.append(
            _candidate_from_event(
                title=event["title"],
                detail=event["detail"],
                source=event["source"],
                timestamp=event["timestamp"],
                status=event["status"],
                bonus=1.0,
            )
        )

    return {
        "id": "jagat_kalyan",
        "name": "Jagat Kalyan",
        "status": status,
        "live": bool(newest),
        "summary": "JK project root, scout/evolution logs, welfare-ton spec, and heartbeat files.",
        "status_reason": status_reason,
        "last_activity": last_activity,
        "metrics": {
            "latest_artifact": newest.name if newest else "missing",
            "jk_pulse": _iso_from_ts(jk_pulse.stat().st_mtime) if jk_pulse.exists() else "missing",
            "scout_log_words": str(_count_words(scout_log)) if scout_log.exists() else "0",
            "evolution_log_words": str(_count_words(evolution_log)) if evolution_log.exists() else "0",
        },
        "processes": [],
        "projects": [
            _path_record("jagat_kalyan root", root, "project"),
            _path_record("app.py", app_py, "source"),
            _path_record("matching.py", matching_py, "source"),
            _path_record("models.py", models_py, "source"),
            _path_record("WELFARE_TONS_SPEC.md", spec_md, "source"),
            _path_record("SCOUT_LOG.md", scout_log, "artifact"),
            _path_record("EVOLUTION_LOG.md", evolution_log, "artifact"),
            _path_record("jk_pulse.md", jk_pulse, "artifact"),
            _path_record("jk_alert.md", jk_alert, "artifact"),
        ],
        "wiring": [
            {"direction": "writes", "target": "~/jagat_kalyan/SCOUT_LOG.md", "detail": "scout findings log"},
            {"direction": "writes", "target": "~/jagat_kalyan/EVOLUTION_LOG.md", "detail": "evolution changes log"},
            {"direction": "writes", "target": "~/.dharma/shared/jk_pulse.md", "detail": "JK heartbeat for morning brief"},
            {"direction": "writes", "target": "~/.dharma/shared/jk_alert.md", "detail": "urgency handoff for morning brief"},
            {"direction": "feeds", "target": "Pulse + Cron", "detail": "morning brief explicitly reads JK pulse, alert, and evolution log"},
        ],
        "history": history[:12],
        "salient": _select_salient(salient),
    }


def list_truth_modules() -> list[dict[str, Any]]:
    cache_age = time.time() - float(_MODULE_CACHE.get("built_at", 0.0))
    if cache_age < 20.0 and _MODULE_CACHE.get("data"):
        return list(_MODULE_CACHE["data"])

    _PS_CACHE["built_at"] = 0.0
    _PS_CACHE["rows"] = []
    _LSOF_CACHE.clear()

    modules = [
        _control_plane_module(),
        _living_layers_module(),
        _mycelium_module(),
        _trishula_module(),
        _pulse_cron_module(),
        _allout_module(),
        _jagat_kalyan_module(),
    ]
    priority = {"broken": 0, "mixed": 1, "active": 2, "stale": 3, "unknown": 4}
    ordered = sorted(
        modules,
        key=lambda module: (
            priority.get(str(module.get("status")), 9),
            _age_hours(str(module.get("last_activity"))) if module.get("last_activity") else 9999,
        ),
    )
    _MODULE_CACHE["built_at"] = time.time()
    _MODULE_CACHE["data"] = ordered
    return list(ordered)


def get_truth_module(module_id: str) -> dict[str, Any] | None:
    for module in list_truth_modules():
        if module["id"] == module_id:
            return module
    return None
