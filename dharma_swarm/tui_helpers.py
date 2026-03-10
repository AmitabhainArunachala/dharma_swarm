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


def _load_jsonl_tail(path: Path, *, limit: int) -> list[dict]:
    """Load up to *limit* JSONL objects from the tail of *path*."""
    if not path.exists():
        return []
    try:
        text = path.read_text().strip()
    except Exception:
        return []
    if not text:
        return []

    rows: list[dict] = []
    for line in text.split("\n")[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


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


def build_darwin_status_text(
    *,
    limit: int = 20,
    archive_limit: int = 6,
) -> str:
    """Build a high-signal Darwin visibility panel for TUI/CLI surfaces."""
    from dharma_swarm.archive import FitnessScore
    from dharma_swarm.experiment_log import ExperimentRecord
    from dharma_swarm.experiment_memory import ExperimentMemory

    lines: list[str] = ["[bold cyan]--- Darwin Control ---[/bold cyan]"]
    evo_dir = DHARMA_STATE / "evolution"
    experiments_path = evo_dir / "experiments.jsonl"
    archive_path = evo_dir / "archive.jsonl"

    raw_records = _load_jsonl_tail(experiments_path, limit=limit)
    records: list[ExperimentRecord] = []
    for row in raw_records:
        try:
            if "fitness" in row and isinstance(row["fitness"], dict):
                row = dict(row)
                row["fitness"] = FitnessScore(**row["fitness"])
            records.append(ExperimentRecord.model_validate(row))
        except Exception:
            continue

    if records:
        snapshot = ExperimentMemory().analyze(records)
        strategy = snapshot.recommended_strategy or "steady"
        lines.append(
            "  Recent experiments: "
            f"{snapshot.records_considered}  "
            f"avg_fitness={snapshot.avg_weighted_fitness:.2f}  "
            f"strategy={strategy}  "
            f"confidence={snapshot.confidence:.2f}"
        )

        promotion_counts: dict[str, int] = {}
        for record in records:
            key = (
                record.promotion_state.value
                if hasattr(record.promotion_state, "value")
                else str(record.promotion_state)
            )
            promotion_counts[key] = promotion_counts.get(key, 0) + 1
        if promotion_counts:
            ordered = ", ".join(
                f"{key}={promotion_counts[key]}"
                for key in sorted(promotion_counts)
            )
            lines.append(f"  Promotion ladder: {ordered}")

        if snapshot.failure_classes:
            failure_summary = ", ".join(
                f"{name}={count}"
                for name, count in sorted(
                    snapshot.failure_classes.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:3]
            )
            lines.append(f"  Failure classes: {failure_summary}")

        if snapshot.caution_components:
            lines.append(
                "  Fragile components: "
                + ", ".join(snapshot.caution_components[:3])
            )

        if snapshot.avoidance_hints:
            lines.append("  [cyan]Avoidance hints[/cyan]")
            for hint in snapshot.avoidance_hints[:3]:
                lines.append(f"    - {hint}")
    else:
        lines.append("  [dim]No Darwin experiment history found.[/dim]")

    raw_entries = _load_jsonl_tail(archive_path, limit=archive_limit)
    if raw_entries:
        lines.append("  [cyan]Recent archived mutations[/cyan]")
        for entry in raw_entries[-archive_limit:]:
            fitness_payload = entry.get("fitness", {})
            try:
                weighted = FitnessScore(**fitness_payload).weighted()
            except Exception:
                weighted = 0.0
            lines.append(
                "    "
                f"{str(entry.get('id', '?'))[:8]}  "
                f"{entry.get('component', '?')}  "
                f"{entry.get('promotion_state', 'candidate')}  "
                f"{entry.get('execution_profile', 'default')}  "
                f"fit={weighted:.2f}"
            )
    elif not records:
        lines.append("  [dim]No Darwin archive found.[/dim]")

    return "\n".join(lines)
