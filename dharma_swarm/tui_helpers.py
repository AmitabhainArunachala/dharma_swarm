"""Shared TUI helpers -- status text builders extracted from old tui.py.

Used by both the old monolithic tui.py and the new tui/ package so that
``/status`` output is consistent regardless of which frontend is active.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = Path(__file__).resolve().parent.parent
AI_DEEP = "#9C7444"
VERDIGRIS = "#62725D"
OCHRE = "#A17A47"
BENGARA = "#8C5448"
WISTERIA = "#74677D"


def _read_json(path: Path) -> dict | None:
    """Read and parse a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _read_json_object(raw: object) -> dict[str, object]:
    """Parse a JSON object payload, returning an empty dict on failure."""
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _count_rows(db: sqlite3.Connection, table: str, where: str = "") -> int:
    query = f"SELECT COUNT(*) FROM {table}{where}"
    return int(db.execute(query).fetchone()[0])


def _runtime_db_path() -> Path:
    return DHARMA_STATE / "state" / "runtime.db"


def _maybe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return False


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def load_resident_seat_summary(
    *,
    runtime_db_path: Path | None = None,
    limit: int = 6,
) -> list[dict[str, str]]:
    """Return resident-seat identities from the canonical runtime telemetry DB."""
    db_path = runtime_db_path or _runtime_db_path()
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT tr.agent_id, tr.role, tr.active, tr.updated_at, tr.metadata_json,"
                " ai.status AS identity_status, ai.metadata_json AS identity_metadata"
                " FROM team_roster tr"
                " LEFT JOIN agent_identity ai ON ai.agent_id = tr.agent_id"
                " WHERE tr.active = 1"
                " ORDER BY tr.updated_at DESC"
                " LIMIT ?",
                (max(1, limit * 4),),
            ).fetchall()
    except sqlite3.Error:
        return []

    summary: list[dict[str, str]] = []
    for row in rows:
        roster_meta = _read_json_object(row["metadata_json"])
        identity_meta = _read_json_object(row["identity_metadata"])
        seat_id = str(
            roster_meta.get("seat_id")
            or identity_meta.get("seat_id")
            or ""
        ).strip()
        agent_id = str(row["agent_id"] or "").strip()
        if not seat_id and not agent_id.startswith("resident."):
            continue
        display_name = str(
            roster_meta.get("agent_display_name")
            or roster_meta.get("display_name")
            or identity_meta.get("agent_display_name")
            or identity_meta.get("display_name")
            or identity_meta.get("codename")
            or agent_id
        ).strip()
        runtime_name = str(
            identity_meta.get("runtime_agent_name")
            or roster_meta.get("runtime_agent_name")
            or identity_meta.get("bus_agent_id")
            or agent_id
        ).strip()
        current_binding = str(
            identity_meta.get("current_binding")
            or roster_meta.get("current_binding")
            or identity_meta.get("selected_model_hint")
            or ""
        ).strip()
        status = str(
            row["identity_status"]
            or identity_meta.get("bus_status")
            or "active"
        ).strip()
        summary.append(
            {
                "agent_id": agent_id,
                "display_name": display_name,
                "seat_id": seat_id,
                "runtime_name": runtime_name,
                "current_binding": current_binding,
                "status": status,
                "role": str(row["role"] or "").strip(),
            }
        )
        if len(summary) >= max(1, limit):
            break

    try:
        from dharma_swarm.startup_crew import FRONTIER_MODEL_CREW
    except Exception:
        FRONTIER_MODEL_CREW = []

    known_agent_ids = {seat["agent_id"] for seat in summary}
    for spec in FRONTIER_MODEL_CREW:
        metadata = spec.get("metadata", {})
        agent_id = str(metadata.get("agent_id") or "").strip()
        if not agent_id or agent_id in known_agent_ids:
            continue
        summary.append(
            {
                "agent_id": agent_id,
                "display_name": str(
                    metadata.get("display_name")
                    or spec.get("name")
                    or agent_id
                ).strip(),
                "seat_id": str(metadata.get("seat_id") or "").strip(),
                "runtime_name": str(spec.get("name") or agent_id).strip(),
                "current_binding": str(
                    metadata.get("current_binding")
                    or spec.get("model")
                    or ""
                ).strip(),
                "status": "configured",
                "role": str(spec.get("role") or "").strip(),
            }
        )
        known_agent_ids.add(agent_id)
        if len(summary) >= max(1, limit):
            break

    return summary


def build_status_text() -> str:
    """Build the system status panel text (Rich markup).

    Returns:
        Multi-line string with Rich markup suitable for writing into a
        StreamOutput or RichLog widget.
    """
    lines: list[str] = [f"[bold {AI_DEEP}]--- DGC System Status ---[/bold {AI_DEEP}]"]

    # Active research thread
    thread_file = DHARMA_STATE / "thread_state.json"
    if thread_file.exists():
        ts = _read_json(thread_file)
        if ts:
            lines.append(
                f"  Thread: [{VERDIGRIS}]{ts.get('current_thread', 'unknown')}[/{VERDIGRIS}]"
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


def build_runtime_status_text(
    *,
    limit: int = 5,
    runtime_db_path: Path | None = None,
) -> str:
    """Build a runtime control-plane summary from the canonical SQLite spine."""
    lines: list[str] = [f"[bold {AI_DEEP}]--- Runtime Control Plane ---[/bold {AI_DEEP}]"]
    db_path = runtime_db_path or _runtime_db_path()

    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path)) as db:
                db.row_factory = sqlite3.Row
                lines.append(f"  Runtime DB: {db_path}")
                lines.append(
                    "  Sessions={sessions}  Claims={claims}  ActiveClaims={active_claims}  "
                    "AckedClaims={acknowledged_claims}  Runs={runs}  ActiveRuns={active_runs}".format(
                        sessions=_count_rows(db, "sessions"),
                        claims=_count_rows(db, "task_claims"),
                        active_claims=_count_rows(
                            db,
                            "task_claims",
                            " WHERE status IN ('claimed','in_progress')",
                        ),
                        acknowledged_claims=_count_rows(
                            db,
                            "task_claims",
                            " WHERE status = 'acknowledged'",
                        ),
                        runs=_count_rows(db, "delegation_runs"),
                        active_runs=_count_rows(
                            db,
                            "delegation_runs",
                            " WHERE status NOT IN ('completed','failed','stale_recovered')",
                        ),
                    )
                )
                lines.append(
                    "  Artifacts={artifacts}  PromotedFacts={promoted_facts}  "
                    "ContextBundles={context_bundles}  OperatorActions={operator_actions}".format(
                        artifacts=_count_rows(db, "artifact_records"),
                        promoted_facts=_count_rows(
                            db,
                            "memory_facts",
                            " WHERE truth_state = 'promoted'",
                        ),
                        context_bundles=_count_rows(db, "context_bundles"),
                        operator_actions=_count_rows(db, "operator_actions"),
                    )
                )

                runs = db.execute(
                    "SELECT run_id, task_id, assigned_to, status, current_artifact_id"
                    " FROM delegation_runs"
                    " WHERE status NOT IN ('completed','failed','stale_recovered')"
                    " ORDER BY started_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
                if runs:
                    lines.append(f"  [{AI_DEEP}]Active runs[/{AI_DEEP}]")
                    for row in runs:
                        artifact_id = str(row["current_artifact_id"] or "")
                        artifact_label = artifact_id[:8] if artifact_id else "-"
                        lines.append(
                            "    "
                            f"{str(row['run_id'])[:8]}  "
                            f"{row['assigned_to']}  "
                            f"{row['status']}  "
                            f"task={str(row['task_id'])[:12]}  "
                            f"artifact={artifact_label}"
                        )

                artifacts = db.execute(
                    "SELECT artifact_id, artifact_kind, promotion_state, payload_path"
                    " FROM artifact_records"
                    " ORDER BY created_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
                if artifacts:
                    lines.append(f"  [{AI_DEEP}]Recent artifacts[/{AI_DEEP}]")
                    for row in artifacts:
                        payload_name = Path(str(row["payload_path"] or "")).name or "-"
                        lines.append(
                            "    "
                            f"{str(row['artifact_id'])[:8]}  "
                            f"{row['artifact_kind']}  "
                            f"{row['promotion_state']}  "
                            f"{payload_name}"
                        )

                actions = db.execute(
                    "SELECT action_name, actor, task_id"
                    " FROM operator_actions"
                    " ORDER BY created_at DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
                if actions:
                    lines.append(f"  [{AI_DEEP}]Recent operator actions[/{AI_DEEP}]")
                    for row in actions:
                        task_id = str(row["task_id"] or "")
                        task_label = task_id[:12] if task_id else "-"
                        lines.append(
                            "    "
                            f"{row['action_name']}  "
                            f"actor={row['actor']}  "
                            f"task={task_label}"
                        )
        except sqlite3.Error as exc:
            lines.append(f"  [{BENGARA}]Runtime DB unreadable: {exc}[/{BENGARA}]")
    else:
        lines.append(f"  [dim]No canonical runtime database found at {db_path}[/dim]")

    lines.append(f"  [{AI_DEEP}]Toolchain[/{AI_DEEP}]")
    for prog in ("claude", "python3", "node"):
        lines.append(f"    {prog}: {shutil.which(prog) or 'not found'}")

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

    lines: list[str] = [f"[bold {AI_DEEP}]--- Darwin Control ---[/bold {AI_DEEP}]"]
    evo_dir = DHARMA_STATE / "evolution"
    experiments_path = evo_dir / "experiments.jsonl"
    archive_path = evo_dir / "archive.jsonl"
    observations_dir = evo_dir / "observations"
    dse_observations_path = observations_dir / "coalgebra_stream.jsonl"
    coordination_path = observations_dir / "coordination_log.jsonl"

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
            lines.append(f"  [{AI_DEEP}]Avoidance hints[/{AI_DEEP}]")
            for hint in snapshot.avoidance_hints[:3]:
                lines.append(f"    - {hint}")
    else:
        lines.append("  [dim]No Darwin experiment history found.[/dim]")

    raw_entries = _load_jsonl_tail(archive_path, limit=archive_limit)
    if raw_entries:
        lines.append(f"  [{AI_DEEP}]Recent archived mutations[/{AI_DEEP}]")
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

    dse_rows = _load_jsonl_tail(dse_observations_path, limit=limit)
    if dse_rows:
        components = {
            str(row.get("component")).strip()
            for row in dse_rows
            if str(row.get("component") or "").strip()
        }
        rv_values = [
            value
            for row in dse_rows
            if (value := _maybe_float(row.get("rv"))) is not None
        ]
        fitness_values = [
            value
            for row in dse_rows
            if (value := _maybe_float(row.get("best_fitness"))) is not None
        ]
        fixed_point_count = sum(
            1 for row in dse_rows if _as_bool(row.get("approaching_fixed_point"))
        )

        ouroboros_count = 0
        mimicry_count = 0
        witness_values: list[float] = []
        latest_recognition = ""
        l4_rows = 0
        l4_like_count = 0
        reciprocity_count = 0
        invalid_chain_count = 0
        fresh_reciprocity_count = 0
        fresh_invalid_chain_count = 0
        stale_reciprocity_count = 0
        latest_reciprocity: dict | None = None
        for row in dse_rows:
            ouroboros = row.get("ouroboros")
            if isinstance(ouroboros, dict):
                ouroboros_count += 1
                if _as_bool(ouroboros.get("is_mimicry")):
                    mimicry_count += 1
                witness = _maybe_float(ouroboros.get("swabhaav_ratio"))
                if witness is not None:
                    witness_values.append(witness)
                recognition = str(ouroboros.get("recognition_type") or "").strip()
                if recognition:
                    latest_recognition = recognition

            correlation = row.get("l4_correlation")
            if isinstance(correlation, dict):
                l4_rows += 1
                if _as_bool(correlation.get("is_l4_like")):
                    l4_like_count += 1

            reciprocity = row.get("reciprocity")
            if isinstance(reciprocity, dict):
                reciprocity_count += 1
                is_stale = _as_bool(reciprocity.get("stale"))
                if is_stale:
                    stale_reciprocity_count += 1
                else:
                    fresh_reciprocity_count += 1
                if not _as_bool(reciprocity.get("chain_valid")):
                    invalid_chain_count += 1
                    if not is_stale:
                        fresh_invalid_chain_count += 1
                latest_reciprocity = reciprocity

        lines.append(f"  [{AI_DEEP}]DSE observation stream[/{AI_DEEP}]")
        dse_summary = [f"observations={len(dse_rows)}"]
        if components:
            dse_summary.append(f"components={len(components)}")
        avg_rv = _mean(rv_values)
        if avg_rv is not None:
            dse_summary.append(f"avg_rv={avg_rv:.2f}")
        avg_fitness = _mean(fitness_values)
        if avg_fitness is not None:
            dse_summary.append(f"avg_fitness={avg_fitness:.2f}")
        lines.append("    " + "  ".join(dse_summary))

        ouroboros_summary: list[str] = []
        if ouroboros_count > 0:
            ouroboros_summary.append(
                f"mimicry={mimicry_count / ouroboros_count:.1%}"
            )
            avg_witness = _mean(witness_values)
            if avg_witness is not None:
                ouroboros_summary.append(f"witness={avg_witness:.2f}")
            if latest_recognition:
                ouroboros_summary.append(f"latest={latest_recognition}")
        if l4_rows > 0:
            ouroboros_summary.append(f"l4_like={l4_like_count}/{l4_rows}")
        if ouroboros_summary:
            lines.append("    ouroboros " + "  ".join(ouroboros_summary))

        if reciprocity_count > 0 and latest_reciprocity is not None:
            invalid_numerator = (
                fresh_invalid_chain_count
                if fresh_reciprocity_count > 0
                else invalid_chain_count
            )
            invalid_denominator = (
                fresh_reciprocity_count
                if fresh_reciprocity_count > 0
                else reciprocity_count
            )
            reciprocity_summary = [f"invalid_chain={invalid_numerator}/{invalid_denominator}"]
            if stale_reciprocity_count > 0:
                reciprocity_summary.append(
                    f"stale_rows={stale_reciprocity_count}/{reciprocity_count}"
                )
            latest_issues = _maybe_int(latest_reciprocity.get("invariant_issues"))
            if latest_issues is not None:
                reciprocity_summary.append(f"latest_issues={latest_issues}")
            challenged_claims = _maybe_int(latest_reciprocity.get("challenged_claims"))
            if challenged_claims is not None:
                reciprocity_summary.append(f"challenged={challenged_claims}")
            routed_usd = _maybe_float(latest_reciprocity.get("total_routed_usd"))
            if routed_usd is not None:
                reciprocity_summary.append(f"routed_usd={routed_usd:.2f}")
            issue_codes = latest_reciprocity.get("issue_codes")
            if isinstance(issue_codes, list) and issue_codes:
                reciprocity_summary.append(
                    "issue_codes=" + ",".join(str(code) for code in issue_codes[:3])
                )
            if _as_bool(latest_reciprocity.get("stale")):
                reciprocity_summary.append("stale=yes")
            lines.append("    reciprocity " + "  ".join(reciprocity_summary))

        latest_component = str(dse_rows[-1].get("component") or "").strip()
        tail_summary = [f"fixed_point={fixed_point_count}/{len(dse_rows)}"]
        if latest_component:
            tail_summary.append(f"latest_component={latest_component}")
        lines.append("    " + "  ".join(tail_summary))

        latest_coordination = _load_jsonl_tail(coordination_path, limit=1)
        if latest_coordination:
            snapshot = latest_coordination[-1]
            coherence = "yes" if _as_bool(snapshot.get("is_globally_coherent", True)) else "no"
            lines.append(
                "    coordination "
                f"truths={int(snapshot.get('global_truths', 0) or 0)}  "
                f"disagreements={int(snapshot.get('productive_disagreements', 0) or 0)}  "
                f"coherent={coherence}"
            )

    return "\n".join(lines)
