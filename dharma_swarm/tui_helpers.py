"""Shared TUI helpers -- status text builders extracted from old tui.py.

Used by both the old monolithic tui.py and the new tui/ package so that
``/status`` output is consistent regardless of which frontend is active.
"""

from __future__ import annotations

import json
from pathlib import Path

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def build_status_text() -> str:
    """Build the system status panel text (Rich markup).

    Returns:
        Multi-line string with Rich markup suitable for writing into a
        StreamOutput or RichLog widget.
    """
    lines: list[str] = ["[bold cyan]--- DGC System Status ---[/bold cyan]"]

    # Active research thread
    thread_file = DHARMA_STATE / "thread_state.json"
    if thread_file.exists():
        ts = _read_json(thread_file)
        if ts:
            lines.append(
                f"  Thread: [cyan]{ts.get('current_thread', 'unknown')}[/cyan]"
            )

    # Last pulse timestamp
    pulse_log = DHARMA_STATE / "pulse_log.jsonl"
    if pulse_log.exists():
        try:
            last_line = pulse_log.read_text().strip().split("\n")[-1]
            pulse = json.loads(last_line)
            lines.append(
                f"  Last pulse: {pulse.get('timestamp', 'unknown')[:19]}"
            )
        except Exception:
            pass

    # Memory entry count
    mem_db = DHARMA_STATE / "memory.db"
    if mem_db.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(mem_db))
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()
            lines.append(f"  Memory entries: {count}")
        except Exception:
            lines.append("  Memory: [dim]unavailable[/dim]")

    # Source module count
    src_dir = DHARMA_SWARM / "dharma_swarm"
    if src_dir.is_dir():
        src_files = list(src_dir.glob("*.py"))
        lines.append(f"  Source modules: {len(src_files)}")

    # Evolution archive size
    archive_path = DHARMA_STATE / "evolution" / "archive.jsonl"
    if archive_path.exists():
        try:
            archive_text = archive_path.read_text().strip()
            if archive_text:
                count = len(archive_text.split("\n"))
                lines.append(f"  Archive entries: {count}")
        except Exception:
            pass

    # Manifest / ecosystem health
    manifest_path = HOME / ".dharma_manifest.json"
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        if manifest:
            eco = manifest.get("ecosystem", {})
            if eco:
                alive = sum(1 for v in eco.values() if v.get("exists"))
                lines.append(f"  Ecosystem: {alive}/{len(eco)} alive")

    return "\n".join(lines)
