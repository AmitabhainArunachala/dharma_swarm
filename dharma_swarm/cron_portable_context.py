"""Local snapshot builders for hosted-portable cron jobs."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from dharma_swarm.context import (
    read_agni_state,
    read_agent_notes,
    read_manifest,
    read_memory_context,
    read_trishula_inbox,
)

_HOME = Path.home()
_STATE_DIR = _HOME / ".dharma"
_SHARED_DIR = _STATE_DIR / "shared"
_JK_DIR = _HOME / "jagat_kalyan"
_DGC_DAEMON_DIR = _HOME / "dgc-core" / "daemon"


def _assurance_critical_summary() -> str:
    scans_dir = _STATE_DIR / "assurance" / "scans"
    if not scans_dir.exists():
        return "No assurance scan summaries found."

    critical_total = 0
    scanned = 0
    for path in sorted(scans_dir.glob("*latest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        scanned += 1
        summary = payload.get("summary")
        if isinstance(summary, dict):
            try:
                critical_total += int(summary.get("critical", 0) or 0)
            except (TypeError, ValueError):
                pass
            continue
        findings = payload.get("findings")
        if isinstance(findings, list):
            critical_total += sum(
                1
                for finding in findings
                if isinstance(finding, dict)
                and str(finding.get("severity", "")).lower() == "critical"
            )
    if scanned == 0:
        return "No readable latest assurance scans."
    noun = "finding" if critical_total == 1 else "findings"
    return f"{critical_total} critical assurance {noun} across {scanned} latest scans."


def _file_age_days(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        age_days = (time.time() - path.stat().st_mtime) / 86400
    except OSError:
        return "unreadable"
    return f"{age_days:.1f}"


def _read_text(path: Path, limit: int = 400) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except Exception:
        return ""


def _read_rv_status(limit: int = 600) -> str:
    paper_dir = _HOME / "mech-interp-latent-lab-phase1" / "R_V_PAPER"
    if not paper_dir.exists():
        return "R_V paper directory missing."
    try:
        recent = sorted(
            [p for p in paper_dir.iterdir() if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]
    except OSError:
        return "R_V paper directory unreadable."
    if not recent:
        return "R_V paper directory empty."
    lines = ["Recent paper files:"]
    for path in recent:
        try:
            age_hours = (time.time() - path.stat().st_mtime) / 3600
        except OSError:
            age_hours = -1
        age = f"{age_hours:.1f}h" if age_hours >= 0 else "unknown"
        lines.append(f"- {path.name} ({age} ago)")
    return "\n".join(lines)[:limit]


def _build_pulse_prompt(job: dict[str, Any]) -> str:
    agni = read_agni_state()
    trishula = read_trishula_inbox()
    memory = read_memory_context(limit=3)
    shared = read_agent_notes(max_per_agent=200)
    manifest = read_manifest()
    assurance = _assurance_critical_summary()

    return (
        "You are DGC Pulse. Work only from the provided local snapshot. "
        "Do not invent file reads, shell commands, or hidden state.\n\n"
        "## Local Snapshot\n"
        f"AGNI:\n{json.dumps(agni, indent=2)[:1200]}\n\n"
        f"Trishula:\n{trishula}\n\n"
        f"Assurance:\n{assurance}\n\n"
        f"Memory:\n{memory}\n\n"
        f"Shared Notes:\n{shared or 'No recent shared notes.'}\n\n"
        f"Manifest:\n{manifest}\n\n"
        "Task:\n"
        "1. State whether AGNI looks blocked or stale.\n"
        "2. Mention any inbox, assurance, memory, or shared-note developments worth attention.\n"
        "3. If anything needs action, say exactly what.\n"
        "4. Otherwise, log a brief witness observation.\n"
        "Max 200 words."
    )


def _build_morning_brief_prompt(job: dict[str, Any]) -> str:
    agni = read_agni_state()
    trishula = read_trishula_inbox()
    memory = read_memory_context(limit=5)
    shared = read_agent_notes(max_per_agent=250)
    rv_status = _read_rv_status()
    dream_journal = _read_text(
        _STATE_DIR / "subconscious" / "journal" / "LATEST_JOURNAL.md",
        1200,
    ) or "No dream journal found."
    jk_pulse = _read_text(_SHARED_DIR / "jk_pulse.md", 500) or "No JK pulse found."
    jk_alert = _read_text(_SHARED_DIR / "jk_alert.md", 500) or "No JK alert file."
    jk_evolution_age = _file_age_days(_JK_DIR / "EVOLUTION_LOG.md")

    return (
        "Generate the morning briefing from the provided local snapshot only. "
        "Do not invent file reads, shell commands, or hidden state.\n\n"
        "## Local Snapshot\n"
        f"AGNI:\n{json.dumps(agni, indent=2)[:1200]}\n\n"
        f"Trishula:\n{trishula}\n\n"
        f"Memory:\n{memory}\n\n"
        f"Shared Notes:\n{shared or 'No recent shared notes.'}\n\n"
        f"R_V Paper:\n{rv_status}\n\n"
        f"Dream Journal:\n{dream_journal}\n\n"
        f"JK Pulse:\n{jk_pulse}\n\n"
        f"JK Alert:\n{jk_alert}\n\n"
        f"JK Evolution Log age days: {jk_evolution_age}\n\n"
        "Write a concise actionable briefing with these sections when relevant:\n"
        "- AGNI\n"
        "- Blockers\n"
        "- From the Subconscious\n"
        "- Jagat Kalyan\n"
        "Output only the briefing body."
    )


def _build_agni_check_prompt(job: dict[str, Any]) -> str:
    agni = read_agni_state()
    manifest = read_manifest()
    priorities_age = agni.get("priorities_age_hours", "unknown")

    return (
        "You are AGNI State Check. Work only from the provided local snapshot. "
        "Do not invent file reads or remote state.\n\n"
        "## Local Snapshot\n"
        f"AGNI:\n{json.dumps(agni, indent=2)[:1200]}\n\n"
        f"Manifest:\n{manifest}\n\n"
        "Task:\n"
        f"- Say whether AGNI is blocked, stale, or healthy.\n"
        f"- Mention priorities age if relevant (current value: {priorities_age}).\n"
        "- Be brief and concrete."
    )


def _build_trishula_triage_prompt(job: dict[str, Any]) -> str:
    inbox = _HOME / "trishula" / "inbox"
    ack = 0
    substantive: list[str] = []
    diagnostic = 0
    if inbox.exists():
        try:
            files = sorted(inbox.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            files = []
        for path in files:
            name = path.name
            lowered = name.lower()
            if "ack" in lowered:
                ack += 1
                continue
            if "test" in lowered or "diag" in lowered or "ping" in lowered:
                diagnostic += 1
                continue
            substantive.append(name)
    recent_substantive = substantive[:10]
    return (
        "You are Trishula Inbox Triage. Work only from the provided local snapshot. "
        "Do not invent file reads.\n\n"
        "## Local Snapshot\n"
        f"ack_messages={ack}\n"
        f"substantive_messages={len(substantive)}\n"
        f"diagnostic_messages={diagnostic}\n"
        f"recent_substantive={json.dumps(recent_substantive)}\n\n"
        "Task:\n"
        "Report the counts only. If there are substantive messages newer than 24h, list their filenames. Max 100 words."
    )


def _build_jk_pulse_prompt(job: dict[str, Any]) -> str:
    db_path = _JK_DIR / "jagat_kalyan.db"
    project_count = "unknown"
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
            finally:
                conn.close()
            if row:
                project_count = str(row[0])
        except Exception:
            project_count = "unreadable"
    else:
        project_count = "missing"

    jk_alert = _read_text(_SHARED_DIR / "jk_alert.md", 500) or "No alert file."
    scout_age_days = _file_age_days(_JK_DIR / "SCOUT_LOG.md")
    evolution_age_days = _file_age_days(_JK_DIR / "EVOLUTION_LOG.md")
    file_presence = {
        "app.py": (_JK_DIR / "app.py").exists(),
        "matching.py": (_JK_DIR / "matching.py").exists(),
        "models.py": (_JK_DIR / "models.py").exists(),
        "db_present": db_path.exists(),
    }

    return (
        "You are the Jagat Kalyan Pulse. Work only from the provided local snapshot. "
        "Do not invent commands or file reads.\n\n"
        "## Local Snapshot\n"
        f"Core files:\n{json.dumps(file_presence, indent=2)}\n\n"
        f"Projects table count: {project_count}\n"
        f"SCOUT_LOG age days: {scout_age_days}\n"
        f"EVOLUTION_LOG age days: {evolution_age_days}\n"
        f"Alerts:\n{jk_alert}\n\n"
        "Task:\n"
        "Compute a momentum read as GREEN, YELLOW, or RED based on freshness and missing files.\n"
        "Then write a one-line JK pulse in the format:\n"
        "JK PULSE [DATE] [GREEN/YELLOW/RED] — [one sentence summary]\n"
        "Max 50 words total."
    )


_BUILDERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "pulse": _build_pulse_prompt,
    "agni_check": _build_agni_check_prompt,
    "morning_brief": _build_morning_brief_prompt,
    "trishula_triage": _build_trishula_triage_prompt,
    "jk_pulse": _build_jk_pulse_prompt,
}


def persist_portable_job_output(job: dict[str, Any], content: str) -> Path | None:
    """Persist hosted portable job outputs when the original job expected an artifact."""

    job_id = str(job.get("id", "")).strip()
    if job_id == "jk_pulse":
        target = _SHARED_DIR / "jk_pulse.md"
    elif job_id == "morning_brief":
        target = _DGC_DAEMON_DIR / "morning_brief.md"
    else:
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.strip() + "\n", encoding="utf-8")
    return target


def build_portable_job_prompt(job: dict[str, Any]) -> str:
    """Materialize local state for hosted-portable cron jobs when possible."""

    prompt = str(job.get("prompt", "")).strip()
    builder = _BUILDERS.get(str(job.get("id", "")).strip())
    if builder is None:
        return prompt
    return builder(job)


__all__ = ["build_portable_job_prompt", "persist_portable_job_output"]
