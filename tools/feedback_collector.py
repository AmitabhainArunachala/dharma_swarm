"""Feedback Collector -- scans session logs for error patterns.

Reads conversation logs from ~/.dharma/conversation_log/ and
identifies recurring error patterns that should become gotchas.

Usage:
    python3 tools/feedback_collector.py [--since DAYS] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_DIR = Path.home() / ".dharma" / "conversation_log"

# Minimum occurrences before a pattern is reported
MIN_OCCURRENCES = 2

# Maximum content length to scan per entry (skip huge blobs)
MAX_CONTENT_LEN = 50_000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GotchaEntry:
    """A single proposed gotcha, ready to render as markdown."""

    category: str
    trigger: str
    symptom: str
    fix: str
    prevention: str
    occurrences: int = 1
    example_snippet: str = ""

    def to_markdown(self) -> str:
        """Render as a markdown block matching the gotcha protocol format."""
        lines = [
            f"### {self.category} (seen {self.occurrences}x)",
            "",
            f"**Trigger**: {self.trigger}",
            f"**Symptom**: {self.symptom}",
            f"**Fix**: {self.fix}",
            f"**Prevention**: {self.prevention}",
        ]
        if self.example_snippet:
            lines.extend([
                "",
                "<details><summary>Example</summary>",
                "",
                f"```",
                self.example_snippet[:500],
                "```",
                "",
                "</details>",
            ])
        return "\n".join(lines)


@dataclass
class PatternMatch:
    """A raw match found in a log entry."""

    category: str
    key: str  # de-duplication key (e.g. the module name or error message)
    snippet: str
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------


_IMPORT_RE = re.compile(
    r"(?:ImportError|ModuleNotFoundError):\s*(?:No module named\s+)?['\"]?([^\s'\"]+)['\"]?",
)

_TYPE_VALUE_RE = re.compile(
    r"(TypeError|ValueError):\s*(.{10,120})",
)

_NOT_FOUND_RE = re.compile(
    r"(?:FileNotFoundError|No such file or directory)"
    r"[:\s]*['\"]?([^\s'\"]{5,200})['\"]?"
    r"|(?:file|path|module|directory)\s+['\"]([^\s'\"]{5,200})['\"]"
    r"\s+(?:not found|does not exist)",
    re.IGNORECASE,
)

_API_ERROR_RE = re.compile(
    r"(?:API\s*Error|ConnectionError|ENOTFOUND|ECONNREFUSED|TimeoutError)"
    r"[:\s]*(.{0,150})",
)

_PERMISSION_RE = re.compile(
    r"(?:PermissionError|permission denied|EACCES)[:\s]*(.{0,150})",
    re.IGNORECASE,
)

_ENV_VAR_RE = re.compile(
    r"(?:KeyError:\s*['\"](?:OPENROUTER_API_KEY|ANTHROPIC_API_KEY|API_KEY|CLAUDECODE)['\"]"
    r"|(?:env(?:ironment)?\s+variable)\s+['\"]?(\w+)['\"]?\s+(?:is\s+)?not\s+set"
    r"|CLAUDECODE\s+env\s+var)",
)


def _detect_import_errors(content: str) -> list[PatternMatch]:
    """Detect ImportError / ModuleNotFoundError patterns."""
    matches: list[PatternMatch] = []
    for m in _IMPORT_RE.finditer(content):
        module = m.group(1).strip("'\"")
        matches.append(PatternMatch(
            category="ImportError",
            key=f"import:{module}",
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_type_value_errors(content: str) -> list[PatternMatch]:
    """Detect TypeError / ValueError patterns."""
    matches: list[PatternMatch] = []
    for m in _TYPE_VALUE_RE.finditer(content):
        err_type = m.group(1)
        msg = m.group(2).strip()
        # Normalize the message for de-duplication
        key = f"{err_type}:{msg[:80]}"
        matches.append(PatternMatch(
            category=err_type,
            key=key,
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_not_found(content: str) -> list[PatternMatch]:
    """Detect file/path not found patterns."""
    matches: list[PatternMatch] = []
    for m in _NOT_FOUND_RE.finditer(content):
        # Try group(1) then group(2) due to alternation in regex
        path_fragment = (m.group(1) or m.group(2) or "").strip()
        if len(path_fragment) < 5:
            continue
        matches.append(PatternMatch(
            category="PathNotFound",
            key=f"path:{path_fragment[:100]}",
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_api_errors(content: str) -> list[PatternMatch]:
    """Detect API connection / timeout errors."""
    matches: list[PatternMatch] = []
    for m in _API_ERROR_RE.finditer(content):
        detail = m.group(1).strip() if m.group(1) else "unknown"
        matches.append(PatternMatch(
            category="APIError",
            key=f"api:{detail[:80]}",
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_permission_errors(content: str) -> list[PatternMatch]:
    """Detect permission / access denied patterns."""
    matches: list[PatternMatch] = []
    for m in _PERMISSION_RE.finditer(content):
        detail = m.group(1).strip() if m.group(1) else ""
        matches.append(PatternMatch(
            category="PermissionError",
            key=f"perm:{detail[:80]}",
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_env_var_issues(content: str) -> list[PatternMatch]:
    """Detect environment variable related issues."""
    matches: list[PatternMatch] = []
    for m in _ENV_VAR_RE.finditer(content):
        # Try group(1) first (named var from 'not set' pattern), fall back to full match
        detail = (m.group(1) or m.group(0)).strip()
        matches.append(PatternMatch(
            category="EnvVarIssue",
            key=f"env:{detail[:80]}",
            snippet=content[max(0, m.start() - 40):m.end() + 60].strip(),
        ))
    return matches


def _detect_circular_exploration(entries: list[dict]) -> list[PatternMatch]:
    """Detect repeated tool calls to the same file within a session.

    Looks for sessions where the same file path appears in user prompts
    more than 3 times, suggesting circular exploration.
    """
    session_files: dict[str, Counter[str]] = {}

    path_re = re.compile(
        r"(?:/Users/\S+|~/\S+|~/.dharma/\S+)",
    )

    for entry in entries:
        sid = entry.get("session_id", "")
        content = entry.get("content", "")
        if not sid or not content:
            continue
        paths = path_re.findall(content)
        if not paths:
            continue
        if sid not in session_files:
            session_files[sid] = Counter()
        session_files[sid].update(paths)

    matches: list[PatternMatch] = []
    for sid, counter in session_files.items():
        for path, count in counter.items():
            if count >= 4:
                matches.append(PatternMatch(
                    category="CircularExploration",
                    key=f"circular:{path}",
                    snippet=f"File {path} referenced {count} times in session {sid[:8]}",
                ))
    return matches


ALL_DETECTORS = [
    _detect_import_errors,
    _detect_type_value_errors,
    _detect_not_found,
    _detect_api_errors,
    _detect_permission_errors,
    _detect_env_var_issues,
]

# ---------------------------------------------------------------------------
# Gotcha generation from patterns
# ---------------------------------------------------------------------------

_CATEGORY_TEMPLATES: dict[str, dict[str, str]] = {
    "ImportError": {
        "trigger": "Importing module that is not installed or has moved",
        "fix": "Install the missing module or update the import path",
        "prevention": "Check requirements and import paths before running",
    },
    "TypeError": {
        "trigger": "Passing wrong argument type to function or method",
        "fix": "Check the function signature and pass the correct types",
        "prevention": "Use type hints and run mypy to catch type mismatches early",
    },
    "ValueError": {
        "trigger": "Passing invalid value to function or constructor",
        "fix": "Validate inputs before passing them to the function",
        "prevention": "Add input validation with Pydantic or explicit checks",
    },
    "PathNotFound": {
        "trigger": "Referencing a file or directory that does not exist",
        "fix": "Verify the path exists; create directories with exist_ok=True",
        "prevention": "Use Path.exists() checks and os.makedirs(path, exist_ok=True)",
    },
    "APIError": {
        "trigger": "Making an API call that fails due to connection or auth issues",
        "fix": "Check API endpoint, credentials, and network connectivity",
        "prevention": "Add retry logic and connection health checks before API calls",
    },
    "PermissionError": {
        "trigger": "Accessing a file or resource without adequate permissions",
        "fix": "Check file permissions and ownership; adjust as needed",
        "prevention": "Verify permissions in setup scripts; use appropriate user context",
    },
    "EnvVarIssue": {
        "trigger": "Missing or conflicting environment variable",
        "fix": "Set or unset the relevant environment variable",
        "prevention": "Document required env vars; check them at startup with clear errors",
    },
    "CircularExploration": {
        "trigger": "Repeatedly reading the same file without making progress",
        "fix": "Stop, re-read the actual error, and change approach",
        "prevention": "If you have read a file 3+ times, you are stuck. Step back and rethink",
    },
}


def _build_gotcha(category: str, key: str, count: int, snippet: str) -> GotchaEntry:
    """Build a GotchaEntry from a detected pattern."""
    template = _CATEGORY_TEMPLATES.get(category, {})

    # Extract the specific detail from the key (after the colon)
    detail = key.split(":", 1)[1] if ":" in key else key

    trigger = template.get("trigger", f"Action related to {category}")
    symptom = f"{category}: {detail}"
    fix = template.get("fix", "Investigate and resolve the root cause")
    prevention = template.get("prevention", "Add guards to prevent recurrence")

    return GotchaEntry(
        category=category,
        trigger=trigger,
        symptom=symptom,
        fix=fix,
        prevention=prevention,
        occurrences=count,
        example_snippet=snippet,
    )


# ---------------------------------------------------------------------------
# Log reading
# ---------------------------------------------------------------------------


def _log_files_since(days: int) -> list[Path]:
    """Return sorted list of JSONL log files from the last N days."""
    if not LOG_DIR.is_dir():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result: list[Path] = []

    for f in sorted(LOG_DIR.glob("2*.jsonl")):
        # Filename format: 2026-03-24.jsonl
        try:
            file_date_str = f.stem  # e.g. "2026-03-24"
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc,
            )
            if file_date >= cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                result.append(f)
        except ValueError:
            continue

    return result


def _read_entries(log_file: Path) -> Iterator[dict]:
    """Yield parsed JSON entries from a JSONL file."""
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Corrupted line, skip
                    continue
    except OSError as exc:
        print(f"WARNING: Could not read {log_file}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main scan logic
# ---------------------------------------------------------------------------


def scan_logs(
    days: int = 7,
    min_occurrences: int = MIN_OCCURRENCES,
) -> list[GotchaEntry]:
    """Scan conversation logs and return proposed gotcha entries.

    Args:
        days: Number of days of logs to scan.
        min_occurrences: Minimum times a pattern must appear to be reported.

    Returns:
        List of GotchaEntry objects, sorted by occurrence count descending.
    """
    log_files = _log_files_since(days)
    if not log_files:
        print(f"No log files found in {LOG_DIR} for the last {days} days.", file=sys.stderr)
        return []

    # Collect all pattern matches
    all_matches: list[PatternMatch] = []
    all_entries: list[dict] = []

    for log_file in log_files:
        entries = list(_read_entries(log_file))
        all_entries.extend(entries)

        for entry in entries:
            content = entry.get("content", "")
            if not content or len(content) > MAX_CONTENT_LEN:
                continue

            for detector in ALL_DETECTORS:
                all_matches.extend(detector(content))

    # Detect circular exploration across all entries
    all_matches.extend(_detect_circular_exploration(all_entries))

    # Aggregate by key
    key_counts: Counter[str] = Counter()
    key_category: dict[str, str] = {}
    key_snippet: dict[str, str] = {}

    for match in all_matches:
        key_counts[match.key] += 1
        key_category[match.key] = match.category
        # Keep the first snippet as example
        if match.key not in key_snippet:
            key_snippet[match.key] = match.snippet

    # Build gotcha entries for patterns above threshold
    gotchas: list[GotchaEntry] = []
    for key, count in key_counts.most_common():
        if count < min_occurrences:
            continue
        category = key_category[key]
        snippet = key_snippet.get(key, "")
        gotchas.append(_build_gotcha(category, key, count, snippet))

    return gotchas


def render_report(gotchas: list[GotchaEntry], days: int) -> str:
    """Render gotcha entries as a full markdown report.

    Args:
        gotchas: List of GotchaEntry objects to render.
        days: Number of days the scan covered.

    Returns:
        Complete markdown string ready to write to a file.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Sprint Gotchas",
        "",
        "Errors encountered during the upgrade sprint. Each entry is a learning.",
        "",
        "## Format",
        "**Trigger**: What caused the error",
        "**Symptom**: What happened",
        "**Fix**: How it was resolved",
        "**Prevention**: How to avoid it next time",
        "",
        "---",
        "",
        f"*Auto-generated by feedback_collector.py on {now} (last {days} days)*",
        "",
    ]

    if not gotchas:
        lines.append("No recurring error patterns detected. Clean sprint.")
    else:
        lines.append(f"**{len(gotchas)} patterns detected:**")
        lines.append("")
        for gotcha in gotchas:
            lines.append("---")
            lines.append("")
            lines.append(gotcha.to_markdown())
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the feedback collector."""
    parser = argparse.ArgumentParser(
        description="Scan session logs for error patterns and propose gotcha entries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 tools/feedback_collector.py --since 7\n"
            "  python3 tools/feedback_collector.py --since 3 --output docs/plans/SPRINT_GOTCHAS.md\n"
            "  python3 tools/feedback_collector.py --since 14 --min-occurrences 3\n"
        ),
    )
    parser.add_argument(
        "--since",
        type=int,
        default=7,
        metavar="DAYS",
        help="Number of days of logs to scan (default: 7)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Write markdown report to FILE instead of stdout",
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=MIN_OCCURRENCES,
        metavar="N",
        help=f"Minimum pattern occurrences to report (default: {MIN_OCCURRENCES})",
    )

    args = parser.parse_args()

    gotchas = scan_logs(days=args.since, min_occurrences=args.min_occurrences)
    report = render_report(gotchas, days=args.since)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Report written to {out_path} ({len(gotchas)} patterns)", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
