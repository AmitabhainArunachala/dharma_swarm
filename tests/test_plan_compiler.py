from __future__ import annotations

from dataclasses import dataclass, field

from dharma_swarm.plan_compiler import PlanCompiler


@dataclass
class _Proposal:
    id: str
    description: str
    target_files: list[str]
    fix_type: str = "patch"
    risk_level: str = "low"
    metadata: dict = field(default_factory=dict)


def test_plan_compiler_merges_substrate_jobs_and_raises_risk() -> None:
    compiler = PlanCompiler()
    proposals = [
        _Proposal(
            id="P1",
            description="Tune Triton kernel",
            target_files=["swarm/substrate/triton_runtime.py"],
            risk_level="medium",
            metadata={
                "substrate_plan": {
                    "tier": "mutate",
                    "jobs": [
                        {
                            "runtime": "triton",
                            "operation": "benchmark_from_payload",
                            "benchmark_payload": {"speedup": 1.1},
                        },
                        {
                            "runtime": "triton",
                            "operation": "rewrite_kernel_file",
                            "candidate_path": "/tmp/cand.py",
                            "target_path": "/tmp/target.py",
                        },
                    ],
                }
            },
        )
    ]

    plan = compiler.compile_cycle(
        proposal_batch_id="PROP-TEST-1",
        target_area="swarm/substrate",
        proposals=proposals,
    )

    assert plan.substrate_plan["tier"] == "mutate"
    assert len(plan.substrate_plan["jobs"]) == 2
    assert plan.aggregate_risk >= 0.86
    assert plan.highest_risk_level in {"high", "critical"}
    assert "KernelGate" in " ".join(plan.proposals[0].contracts.test_contract)


def test_plan_compiler_accepts_env_fallback_substrate_plan() -> None:
    compiler = PlanCompiler()
    proposals = [
        _Proposal(
            id="P2",
            description="Refactor orchestrator logs",
            target_files=["swarm/orchestrator.py"],
            risk_level="low",
        )
    ]
    env_plan = (
        '{"tier":"calibrate","jobs":[{"runtime":"ebpf","operation":"tcp_coherence_tracker"}]}'
    )

    plan = compiler.compile_cycle(
        proposal_batch_id="PROP-TEST-2",
        target_area="swarm",
        proposals=proposals,
        env_substrate_plan_json=env_plan,
    )

    assert plan.substrate_plan["tier"] == "calibrate"
    assert plan.substrate_plan["jobs"][0]["operation"] == "tcp_coherence_tracker"
    assert plan.aggregate_risk >= 0.60
