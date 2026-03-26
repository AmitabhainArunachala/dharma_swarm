from __future__ import annotations

from pathlib import Path

from dharma_swarm.auto_grade.models import GradeCard, RewardSignal
from dharma_swarm.auto_research.models import ClaimRecord, ResearchBrief, ResearchReport


def _report() -> ResearchReport:
    brief = ResearchBrief(
        task_id="task-offline",
        topic="Offline learning",
        question="What should be exported?",
    )
    return ResearchReport(
        report_id="report-offline",
        task_id="task-offline",
        brief=brief,
        summary="Offline export summary.",
        body="Offline export body.",
        claims=[
            ClaimRecord(
                claim_id="claim-1",
                text="Export trajectories and rewards only.",
                support_level="supported",
                confidence=0.9,
            )
        ],
        source_ids=["src-1"],
    )


def _reward() -> RewardSignal:
    grade_card = GradeCard(
        task_id="task-offline",
        report_id="report-offline",
        groundedness=0.9,
        citation_precision=0.9,
        citation_coverage=0.9,
        source_quality=0.9,
        source_diversity=0.8,
        topical_coverage=0.85,
        contradiction_handling=0.9,
        freshness=0.8,
        structure=0.8,
        actionability=0.75,
        novelty=0.7,
        traceability=0.9,
        final_score=0.84,
        promotion_state="promotable",
    )
    return RewardSignal(
        task_id=grade_card.task_id,
        report_id=grade_card.report_id,
        grade_card=grade_card,
        scalar_reward=0.68,
        gate_multiplier=1.0,
    )


def test_offline_training_bridge_exports_trajectories_grades_and_rewards(tmp_path) -> None:
    from dharma_swarm.offline_training_bridge import (
        build_offline_training_bundle,
        export_offline_training_bundle,
    )

    bundle = build_offline_training_bundle(
        report=_report(),
        reward_signal=_reward(),
        trajectory=[
            {"role": "system", "content": "Research carefully."},
            {"role": "assistant", "content": "Offline export body."},
        ],
    )
    manifest = export_offline_training_bundle(bundle, export_dir=tmp_path)

    assert Path(manifest.trajectories_path).exists()
    assert Path(manifest.grades_path).exists()
    assert Path(manifest.rewards_path).exists()
    assert set(manifest.members) == {"trajectories.jsonl", "grades.json", "rewards.json", "manifest.json"}


def test_offline_training_bridge_has_no_live_training_entrypoint() -> None:
    import dharma_swarm.offline_training_bridge as bridge

    assert hasattr(bridge, "build_offline_training_bundle")
    assert hasattr(bridge, "export_offline_training_bundle")
    assert not hasattr(bridge, "train")
    assert not hasattr(bridge, "run_training")
    assert not hasattr(bridge, "launch_verl")


def test_offline_training_lane_doc_exists() -> None:
    path = Path("/Users/dhyana/dharma_swarm/docs/plans/2026-03-26-offline-training-lane.md")

    assert path.exists()
