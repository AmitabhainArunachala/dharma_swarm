"""Tests for legacy archive import pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "dharma_swarm" / "scripts"))

from scripts import import_legacy_archive as ila


def _mk_entry(
    *,
    eid: str,
    status: str,
    component: str = "swarm",
    change_type: str = "mutation",
    diff: str = "line1\nline2",
    fitness: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "id": eid,
        "status": status,
        "component": component,
        "change_type": change_type,
        "diff": diff,
        "fitness": fitness
        or {
            "correctness": 1.0,
            "dharmic_alignment": 1.0,
            "elegance": 1.0,
            "efficiency": 1.0,
            "safety": 1.0,
        },
        "gates_passed": ["ahimsa", "satya"],
        "test_results": {"passed": 1, "failed": 0},
    }


def test_compute_weighted_fitness_old_weights():
    f = {
        "correctness": 1.0,
        "dharmic_alignment": 0.5,
        "elegance": 0.0,
        "efficiency": 0.0,
        "safety": 0.0,
    }
    # 0.30*1.0 + 0.25*0.5 = 0.425
    assert ila.compute_weighted_fitness(f) == 0.425


def test_compute_weighted_fitness_new_weights_when_perf_present():
    f = {
        "correctness": 1.0,
        "dharmic_alignment": 1.0,
        "performance": 1.0,
        "utilization": 1.0,
        "elegance": 1.0,
        "efficiency": 1.0,
        "safety": 1.0,
    }
    assert ila.compute_weighted_fitness(f) == 1.0


def test_import_legacy_idempotent(tmp_path: Path):
    source = tmp_path / "archive.jsonl"
    predictor = tmp_path / "predictor_data.jsonl"
    state = tmp_path / "legacy_import_state.json"
    reports = tmp_path / "reports"

    rows = [
        _mk_entry(eid="e1", status="applied", component="swarm"),
        _mk_entry(eid="e2", status="rejected", component="broken.py"),
        _mk_entry(eid="e3", status="dry_run", component="swarm"),
    ]
    source.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    allowed = {"applied", "rejected"}

    first = ila.import_legacy(
        source_archive=source,
        predictor_path=predictor,
        state_path=state,
        report_dir=reports,
        allowed_statuses=allowed,
    )
    assert first["source_total"] == 3
    assert first["eligible_total"] == 2
    assert first["imported_now"] == 2
    assert predictor.exists()
    lines1 = [ln for ln in predictor.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines1) == 2

    second = ila.import_legacy(
        source_archive=source,
        predictor_path=predictor,
        state_path=state,
        report_dir=reports,
        allowed_statuses=allowed,
    )
    assert second["imported_now"] == 0
    lines2 = [ln for ln in predictor.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines2) == 2


def test_normalize_entry_sets_features():
    entry = _mk_entry(
        eid="e4",
        status="approved",
        component="src/dgm/archive.py",
        change_type="refactor",
        diff="a\nb\nc",
    )
    norm = ila.normalize_entry(entry)
    assert norm["status"] == "approved"
    assert norm["features"]["component"] == "src/dgm/archive.py"
    assert norm["features"]["change_type"] == "refactor"
    assert norm["features"]["diff_size"] == 3
    assert norm["features"]["test_coverage_exists"] is True
    assert norm["features"]["gates_likely_to_pass"] == 2
