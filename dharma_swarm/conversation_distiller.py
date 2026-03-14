"""Conversation Distiller — extracts ideas from ALL conversation sources.

Sources:
  1. Claude Code JSONL transcripts (~/.claude/projects/-Users-dhyana/*.jsonl)
  2. Dashboard chat logs (~/.dharma/conversations/*.jsonl)
  3. TUI chat logs (if any)

Output:
  ~/.dharma/distilled/YYYY-MM-DD_HH.md  — periodic insight extraction
  ~/.dharma/distilled/ideas.jsonl        — append-only idea log
  ~/.dharma/shared/conversation_insights.md — latest synthesis (read by morning brief)

Run via: dgc distill-conversations
Cron:    every 4 hours
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DASHBOARD_CONVERSATIONS_DIR = Path.home() / ".dharma" / "conversations"
DISTILLED_DIR = Path.home() / ".dharma" / "distilled"
SHARED_DIR = Path.home() / ".dharma" / "shared"
IDEAS_LOG = DISTILLED_DIR / "ideas.jsonl"
STATE_FILE = DISTILLED_DIR / ".last_distill"


def _ensure_dirs():
    DISTILLED_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_DIR.mkdir(parents=True, exist_ok=True)


def _load_last_distill_time() -> datetime:
    """Load the timestamp of the last distillation run."""
    if STATE_FILE.exists():
        try:
            ts = STATE_FILE.read_text().strip()
            return datetime.fromisoformat(ts)
        except (ValueError, OSError):
            pass
    # Default: 24 hours ago
    return datetime.now(timezone.utc) - timedelta(hours=24)


def _save_distill_time():
    STATE_FILE.write_text(datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Source 1: Claude Code JSONL transcripts
# ---------------------------------------------------------------------------

def _find_recent_transcripts(since: datetime) -> list[Path]:
    """Find Claude Code JSONL transcripts modified since the given time."""
    results = []
    # Scan all project directories
    if not CLAUDE_PROJECTS_DIR.exists():
        return results

    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
                if mtime > since:
                    results.append(jsonl)
            except OSError:
                continue

    return sorted(results, key=lambda p: p.stat().st_mtime, reverse=True)


def _parse_transcript(path: Path) -> list[dict]:
    """Parse a Claude Code JSONL transcript into conversation turns."""
    turns = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = record.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            message = record.get("message", {})
            content = message.get("content", "")
            if isinstance(content, list):
                # Multi-part content (tool use blocks)
                text_parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                content = "\n".join(text_parts)

            if not content or len(content) < 20:
                continue

            turns.append({
                "role": message.get("role", msg_type),
                "content": content,
                "timestamp": record.get("timestamp", ""),
                "session_id": record.get("sessionId", ""),
                "source": "claude_code",
                "source_file": str(path),
            })
    except Exception as e:
        logger.warning("Failed to parse transcript %s: %s", path, e)

    return turns


# ---------------------------------------------------------------------------
# Source 2: Dashboard chat logs
# ---------------------------------------------------------------------------

def _find_recent_dashboard_logs(since: datetime) -> list[Path]:
    """Find dashboard conversation logs modified since the given time."""
    if not DASHBOARD_CONVERSATIONS_DIR.exists():
        return []
    results = []
    for jsonl in DASHBOARD_CONVERSATIONS_DIR.glob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(jsonl.stat().st_mtime, tz=timezone.utc)
            if mtime > since:
                results.append(jsonl)
        except OSError:
            continue
    return results


def _parse_dashboard_log(path: Path) -> list[dict]:
    """Parse a dashboard conversation JSONL log."""
    turns = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        content = record.get("content", "")
        if not content or len(content) < 20:
            continue

        turns.append({
            "role": record.get("role", "unknown"),
            "content": content,
            "timestamp": record.get("timestamp", ""),
            "session_id": record.get("session_id", ""),
            "source": "dashboard",
            "source_file": str(path),
        })
    return turns


# ---------------------------------------------------------------------------
# Idea extraction
# ---------------------------------------------------------------------------

# Patterns that signal ideas worth capturing
IDEA_PATTERNS = [
    # Questions / hypotheses
    ("hypothesis", ["what if", "i think", "could we", "maybe we should", "i wonder",
                     "hypothesis:", "theory:", "the idea is"]),
    # Decisions / conclusions
    ("decision", ["decided to", "going with", "the plan is", "we'll use",
                   "the approach:", "conclusion:", "verdict:"]),
    # Discoveries / insights
    ("insight", ["found that", "realized", "turns out", "interesting:",
                  "key finding", "important:", "notice that", "the reason"]),
    # TODOs / action items
    ("todo", ["need to", "should add", "todo:", "fixme:", "remember to",
              "don't forget", "next step", "action item", "p0:", "p1:"]),
    # Architecture / design
    ("design", ["architecture:", "design:", "pattern:", "the structure",
                 "component:", "interface:", "api:", "schema:"]),
    # Bugs / issues
    ("bug", ["bug:", "issue:", "broken:", "doesn't work", "failing because",
              "root cause", "the problem is", "error:"]),
    # Warnings / risks
    ("warning", ["careful with", "watch out", "risk:", "danger:", "don't",
                  "never", "avoid", "gotcha:"]),
]


def _extract_ideas(turns: list[dict]) -> list[dict]:
    """Extract idea-like snippets from conversation turns."""
    ideas = []
    seen_hashes: set[str] = set()

    for turn in turns:
        content = turn["content"]
        content_lower = content.lower()

        # Check each paragraph/sentence for idea patterns
        paragraphs = content.split("\n\n")
        for para in paragraphs:
            para_stripped = para.strip()
            if len(para_stripped) < 30:
                continue

            para_lower = para_stripped.lower()

            for idea_type, patterns in IDEA_PATTERNS:
                if any(p in para_lower for p in patterns):
                    # Deduplicate by content hash
                    h = hashlib.sha256(para_stripped[:200].encode()).hexdigest()[:16]
                    if h in seen_hashes:
                        continue
                    seen_hashes.add(h)

                    # Truncate to reasonable length
                    text = para_stripped[:500]
                    if len(para_stripped) > 500:
                        text += "..."

                    ideas.append({
                        "type": idea_type,
                        "text": text,
                        "role": turn["role"],
                        "timestamp": turn["timestamp"],
                        "session_id": turn["session_id"],
                        "source": turn["source"],
                        "hash": h,
                    })
                    break  # One idea per paragraph

    return ideas


def _compute_salience(idea: dict) -> float:
    """Score an idea's importance (0-1)."""
    score = 0.5
    text_lower = idea["text"].lower()

    # Type bonuses
    type_scores = {
        "decision": 0.15, "insight": 0.15, "bug": 0.12,
        "warning": 0.10, "todo": 0.08, "hypothesis": 0.08,
        "design": 0.10,
    }
    score += type_scores.get(idea["type"], 0)

    # Length bonus (longer = more substantive, usually)
    if len(idea["text"]) > 200:
        score += 0.05
    if len(idea["text"]) > 400:
        score += 0.05

    # Evidence markers (specific = more valuable)
    evidence_words = ["file:", "line", "error:", "test", "function", "class", "module"]
    for w in evidence_words:
        if w in text_lower:
            score += 0.03

    # User messages slightly more valuable (explicit intent)
    if idea["role"] == "user":
        score += 0.05

    return min(1.0, score)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _write_ideas_log(ideas: list[dict]):
    """Append new ideas to the append-only ideas log."""
    if not ideas:
        return
    with open(IDEAS_LOG, "a") as f:
        for idea in ideas:
            idea["distilled_at"] = datetime.now(timezone.utc).isoformat()
            idea["salience"] = _compute_salience(idea)
            f.write(json.dumps(idea) + "\n")
    logger.info("Appended %d ideas to %s", len(ideas), IDEAS_LOG)


def _write_distill_report(ideas: list[dict], sources_processed: int):
    """Write a timestamped distillation report."""
    now = datetime.now(timezone.utc)
    filename = now.strftime("%Y-%m-%d_%H") + ".md"
    report_path = DISTILLED_DIR / filename

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for idea in ideas:
        by_type.setdefault(idea["type"], []).append(idea)

    lines = [
        f"# Conversation Distillation — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"**Sources processed**: {sources_processed} conversations",
        f"**Ideas extracted**: {len(ideas)}",
        f"",
    ]

    type_order = ["decision", "insight", "bug", "warning", "todo", "hypothesis", "design"]
    type_labels = {
        "decision": "Decisions", "insight": "Insights", "bug": "Bugs/Issues",
        "warning": "Warnings", "todo": "Action Items", "hypothesis": "Hypotheses",
        "design": "Design Notes",
    }

    for t in type_order:
        group = by_type.get(t, [])
        if not group:
            continue
        # Sort by salience
        group.sort(key=lambda i: _compute_salience(i), reverse=True)
        lines.append(f"## {type_labels.get(t, t.title())} ({len(group)})")
        lines.append("")
        for idea in group[:15]:  # Cap per section
            salience = _compute_salience(idea)
            source_tag = f"[{idea['source']}]"
            lines.append(f"- **[{salience:.2f}]** {source_tag} {idea['text'][:300]}")
        lines.append("")

    report_path.write_text("\n".join(lines))
    logger.info("Wrote distill report: %s", report_path)
    return report_path


def _write_latest_synthesis(ideas: list[dict]):
    """Write the latest synthesis file for the morning brief to consume."""
    if not ideas:
        return

    # Top ideas by salience
    scored = [(i, _compute_salience(i)) for i in ideas]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:20]

    lines = [
        "# Conversation Insights (Auto-Distilled)",
        f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Total ideas: {len(ideas)} | Showing top {len(top)}",
        "",
    ]

    for idea, salience in top:
        lines.append(f"- [{idea['type']}] (s={salience:.2f}) {idea['text'][:200]}")

    out = SHARED_DIR / "conversation_insights.md"
    out.write_text("\n".join(lines))
    logger.info("Updated %s with %d top ideas", out, len(top))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def distill(hours_back: float | None = None) -> dict:
    """Run a distillation cycle.

    Args:
        hours_back: Override how far back to look. None = since last run.

    Returns:
        Summary dict with counts.
    """
    _ensure_dirs()

    if hours_back is not None:
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    else:
        since = _load_last_distill_time()

    logger.info("Distilling conversations since %s", since.isoformat())

    # Gather sources
    cc_transcripts = _find_recent_transcripts(since)
    dash_logs = _find_recent_dashboard_logs(since)

    logger.info("Found %d Claude Code transcripts, %d dashboard logs",
                len(cc_transcripts), len(dash_logs))

    # Parse all turns
    all_turns: list[dict] = []
    for t in cc_transcripts:
        all_turns.extend(_parse_transcript(t))
    for d in dash_logs:
        all_turns.extend(_parse_dashboard_log(d))

    logger.info("Parsed %d conversation turns", len(all_turns))

    # Extract ideas
    ideas = _extract_ideas(all_turns)
    logger.info("Extracted %d ideas", len(ideas))

    # Deduplicate against existing ideas log
    existing_hashes: set[str] = set()
    if IDEAS_LOG.exists():
        for line in IDEAS_LOG.read_text().splitlines():
            try:
                existing_hashes.add(json.loads(line).get("hash", ""))
            except (json.JSONDecodeError, KeyError):
                continue

    new_ideas = [i for i in ideas if i["hash"] not in existing_hashes]
    logger.info("%d new ideas (after dedup against %d existing)",
                len(new_ideas), len(existing_hashes))

    # Write outputs
    _write_ideas_log(new_ideas)
    report_path = _write_distill_report(new_ideas, len(cc_transcripts) + len(dash_logs))
    _write_latest_synthesis(new_ideas)

    _save_distill_time()

    return {
        "transcripts_processed": len(cc_transcripts),
        "dashboard_logs_processed": len(dash_logs),
        "turns_parsed": len(all_turns),
        "ideas_extracted": len(ideas),
        "new_ideas": len(new_ideas),
        "report": str(report_path) if report_path else None,
    }


# CLI entry point
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else None
    result = distill(hours_back=hours)
    print(json.dumps(result, indent=2))
