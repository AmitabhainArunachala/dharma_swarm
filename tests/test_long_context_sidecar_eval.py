from __future__ import annotations

import json

from dharma_swarm.long_context_sidecar_eval import build_default_plan, render_markdown


def test_build_default_plan_collects_cases_and_sources(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    dharma_home = tmp_path / ".dharma"

    (repo_root / "dharma_swarm" / "engine").mkdir(parents=True)
    (repo_root / "reports" / "architectural").mkdir(parents=True)
    (repo_root / "reports" / "dual_engine_swarm_20260313_run" / "state").mkdir(parents=True)
    (repo_root / "reports" / "psmv_hyperfiles_20260313").mkdir(parents=True)
    (dharma_home / "conversations").mkdir(parents=True)
    (dharma_home / "distilled").mkdir(parents=True)
    (dharma_home / "evolution").mkdir(parents=True)
    (dharma_home / "foreman").mkdir(parents=True)

    (repo_root / "dharma_swarm" / "engine" / "event_memory.py").write_text("event memory", encoding="utf-8")
    (repo_root / "dharma_swarm" / "engine" / "hybrid_retriever.py").write_text(
        "hybrid retriever", encoding="utf-8"
    )
    (repo_root / "dharma_swarm" / "semantic_memory_bridge.py").write_text(
        "semantic bridge", encoding="utf-8"
    )
    (repo_root / "reports" / "architectural" / "STRANGE_LOOP_MASTER_PLAN_20260314.md").write_text(
        "master plan", encoding="utf-8"
    )
    (repo_root / "reports" / "dual_engine_swarm_20260313_run" / "state" / "mission.json").write_text(
        json.dumps({"mission": "test"}),
        encoding="utf-8",
    )
    (repo_root / "reports" / "psmv_hyperfiles_20260313" / "repo_semantic_summary.md").write_text(
        "semantic summary", encoding="utf-8"
    )
    (repo_root / "program.md").write_text("program", encoding="utf-8")
    (repo_root / "LIVING_LAYERS.md").write_text("layers", encoding="utf-8")
    (dharma_home / "conversations" / "dashboard_2026-03-15.jsonl").write_text("{}", encoding="utf-8")
    (dharma_home / "distilled" / "2026-03-15_15.md").write_text("distilled note", encoding="utf-8")
    (dharma_home / "distilled" / "ideas.jsonl").write_text('{"idea": 1}', encoding="utf-8")
    (dharma_home / "evolution" / "archive.jsonl").write_text('{"archive": 1}', encoding="utf-8")
    (dharma_home / "foreman" / "cycles.jsonl").write_text('{"cycle": 1}', encoding="utf-8")
    (dharma_home / "DGC_SEED_CONTEXT.md").write_text("seed context", encoding="utf-8")

    plan = build_default_plan(repo_root=repo_root, dharma_home=dharma_home, max_chars=200)

    assert plan.candidate_model == "moonshotai/Kimi-Linear-48B-A3B-Instruct"
    assert len(plan.cases) == 5
    assert plan.cases[0].case_id == "repo_digest"
    assert any(source.exists for source in plan.cases[0].sources)
    assert plan.cases[1].sources[0].path.endswith("dashboard_2026-03-15.jsonl")


def test_render_markdown_mentions_candidate_model_and_workloads(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    dharma_home = tmp_path / ".dharma"
    repo_root.mkdir()
    dharma_home.mkdir()

    plan = build_default_plan(repo_root=repo_root, dharma_home=dharma_home, max_chars=80)
    rendered = render_markdown(plan)

    assert "moonshotai/Kimi-Linear-48B-A3B-Instruct" in rendered
    assert "Repo Digestion" in rendered
    assert "Memory Distillation" in rendered
