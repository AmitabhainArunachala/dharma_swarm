# Recent Change Merge Map

Date: 2026-03-27
Branch: `checkpoint/dashboard-stabilization-2026-03-19`
Head: `f57660c`
Anchor: `735cc82`

## Snapshot

- Purpose: map the recent change surface into mergeable lanes without merging yet.
- Current branch-local committed stack after `735cc82`:
  - `5bd0a10` Add git-friendly roaming mailbox bridge
  - `60096b9` Enqueue live mailbox ping for kimi-claw-phone
  - `9b70917` Add roaming mailbox poller
  - `736575a` Add roaming operator bridge
  - `0c7fec9` Add roaming dispatch daemon and control plane spec
  - `885f696` Harden operator bridge sqlite locking
  - `f57660c` Build self-evolving organism runtime
- Current dirty tree:
  - `83` modified tracked paths
  - `59` untracked paths

## Merge Principle

- Preserve the already-committed self-evolving organism stack as a first-class merge lane, not as incidental fallout from other cleanup.
- Peel mixed runtime files before merging adjacent working-tree lanes.
- Treat `agent_runner.py` and `orchestrator.py` as overlap files with explicit lane ownership.
- Prefer small mergeable branches or cherry-pickable commits per lane once each lane is cut cleanly.

## Lane Map

### Lane A: Self-Evolving Organism Base

- Status: committed
- Commit: `f57660c`
- Scope:
  - `dharma_swarm/auto_research/`
  - `dharma_swarm/auto_grade/`
  - `dharma_swarm/optimizer_bridge.py`
  - `dharma_swarm/topology_genome.py`
  - `dharma_swarm/curriculum_engine.py`
  - `dharma_swarm/agent_install.py`
  - `dharma_swarm/offline_training_bridge.py`
  - `dharma_swarm/runtime_fields.py`
  - `dharma_swarm/causal_credit.py`
  - `dharma_swarm/archive.py`
  - `dharma_swarm/evaluator.py`
  - `dharma_swarm/evaluation_registry.py`
  - `dharma_swarm/evolution.py`
  - `dharma_swarm/workflow.py`
  - `dharma_swarm/traces.py`
  - `dharma_swarm/lineage.py`
  - committed hunks in `dharma_swarm/agent_runner.py`
  - committed hunks in `dharma_swarm/orchestrator.py`
  - canonical docs/spec-forge packet
- Merge gate:
  - preserve single-runtime constraint
  - rerun widened organism suite before merge
- Notes:
  - this is the primary lane to keep centered during conflict resolution
  - later lanes should rebase around this commit, not reopen its architecture

### Lane B: Roaming Control Plane Stack

- Status: committed
- Commits:
  - `5bd0a10`
  - `60096b9`
  - `9b70917`
  - `736575a`
  - `0c7fec9`
  - `885f696`
- Scope:
  - `dharma_swarm/roaming_mailbox.py`
  - `dharma_swarm/roaming_poller.py`
  - `dharma_swarm/roaming_operator_bridge.py`
  - `dharma_swarm/roaming_dispatch_daemon.py`
  - `dharma_swarm/operator_bridge.py`
  - `roaming_mailbox/tasks/mbx_81f02f117c024f76.json`
  - `docs/plans/2026-03-26-roaming-control-plane-spec.md`
- Merge gate:
  - mailbox and dispatch tests pass as a stack
  - operator bridge locking stays hardened
- Notes:
  - structurally independent from Lane A except where operator orchestration later touches shared runtime control paths

### Lane C: Agent Memory And Observability Runtime

- Status: working tree only
- Primary scope:
  - `dharma_swarm/agent_memory_manager.py`
  - unstaged residue in `dharma_swarm/agent_runner.py`
  - `dharma_swarm/engine/conversation_memory.py`
  - `dharma_swarm/engine/event_memory.py`
  - `dharma_swarm/message_bus.py`
  - `dharma_swarm/observability.py`
  - `dharma_swarm/runtime_artifacts.py`
  - `tests/test_agent_memory_manager.py`
  - `tests/test_conversation_memory.py`
  - `tests/test_message_bus.py`
  - `tests/test_observability.py`
  - `tests/test_runtime_artifacts.py`
- Overlap files:
  - `dharma_swarm/agent_runner.py`
- Merge gate:
  - cut `agent_runner.py` so only advanced-memory and observability hunks remain in this lane
  - verify no self-evolving runtime regression against Lane A
- Notes:
  - this is the highest-risk uncommitted lane because it shares the hottest runtime seam with Lane A

### Lane D: Director Routing And Telic Dispatch

- Status: working tree only
- Primary scope:
  - unstaged residue in `dharma_swarm/orchestrator.py`
  - `dharma_swarm/telic_seam.py`
  - `dharma_swarm/thinkodynamic_director.py`
  - `dharma_swarm/startup_crew.py`
  - `dharma_swarm/swarm.py`
  - `tests/test_orchestrator.py`
  - `tests/test_telic_seam.py`
  - `tests/test_thinkodynamic_director.py`
  - `tests/test_startup_crew.py`
  - `tests/test_swarm.py`
- Overlap files:
  - `dharma_swarm/orchestrator.py`
- Merge gate:
  - split topology-genome hunks from preferred-agent routing and telic execution lease hunks
  - verify route selection behavior separately from self-evolving topology behavior
- Notes:
  - this lane is adjacent to Lane A but should not be merged as a hidden amendment to it

### Lane E: Provider Policy, Assurance, And Truthfulness

- Status: working tree only
- Primary scope:
  - `dharma_swarm/assurance/`
  - `dharma_swarm/provider_policy.py`
  - `dharma_swarm/provider_smoke.py`
  - `dharma_swarm/providers.py`
  - `dharma_swarm/runtime_provider.py`
  - `dharma_swarm/model_manager.py`
  - `dharma_swarm/ollama_config.py`
  - `dharma_swarm/provider_matrix.py`
  - `docs/PROVIDER_MATRIX_HARNESS.md`
  - `docs/plans/2026-03-26-provider-matrix-harness.md`
  - `docs/plans/2026-03-26-runtime-truthfulness-cleanup.md`
  - `docs/plans/2026-03-26-status-doctor-truthfulness.md`
  - assurance and provider tests
- Merge gate:
  - provider policy, provider smoke, runtime provider, and assurance suites all pass together
  - keep truthfulness and provider-matrix claims aligned with tested behavior
- Notes:
  - this lane likely feeds the operator-shell lane but can be reviewed separately

### Lane F: DGC Operator Shell And Live Runtime Control

- Status: working tree only
- Primary scope:
  - `dharma_swarm/dgc_cli.py`
  - `dharma_swarm/orchestrate_live.py`
  - `dharma_swarm/cron_runner.py`
  - `dharma_swarm/daemon_config.py`
  - `dharma_swarm/codex_overnight.py`
  - `dharma_swarm/overnight_director.py`
  - `dharma_swarm/dharma_kernel.py`
  - `dharma_swarm/doctor.py`
  - `dharma_swarm/cli.py`
  - `garden_daemon.py`
  - `run_daemon.sh`
  - `cron_jobs.json`
  - `tests/test_dgc_cli.py`
  - `tests/test_orchestrate_live.py`
  - `tests/test_cron_runner.py`
  - `tests/test_daemon_config.py`
  - `tests/test_doctor.py`
  - `tests/test_codex_overnight.py`
- Merge gate:
  - CLI, daemon, and doctor suites pass together
  - shell and cron changes must match actual runtime entrypoints
- Notes:
  - broad lane with operational impact; keep it separate from Lane A unless a runtime seam forces an explicit dependency

### Lane G: Router, Shadow Routing, And Model Selection

- Status: working tree only
- Primary scope:
  - `dharma_swarm/router_v1.py`
  - `dharma_swarm/smart_router.py`
  - `dharma_swarm/tiny_router_shadow.py`
  - `dharma_swarm/model_hierarchy.py`
  - `dharma_swarm/model_routing.py`
  - `dharma_swarm/tui/model_routing.py`
  - `dashboard/src/lib/api.ts`
  - `dashboard/src/lib/api.test.ts`
  - `tests/test_router_v1.py`
  - `tests/test_smart_router.py`
  - `tests/test_tiny_router_shadow.py`
  - `tests/tui/test_model_routing.py`
- Merge gate:
  - router and UI routing tests pass together
  - dashboard API expectations match runtime routing behavior
- Notes:
  - this lane can conflict conceptually with Lane E if provider policy and router contracts drift

### Lane H: Self-Evolving Research Adjacent Truth Layer

- Status: working tree only
- Primary scope:
  - `dharma_swarm/citation_index.py`
  - `dharma_swarm/contradiction_registry.py`
  - `dharma_swarm/structured_predicate.py`
  - `dharma_swarm/auto_proposer.py`
  - `dharma_swarm/seed_harvester.py`
  - `docs/plans/2026-03-26-self-evolving-integration.md`
  - `docs/plans/2026-03-26-self-evolving-integration-design.md`
  - `scripts/ingest_ashby_claims.py`
  - `scripts/seed_ashby_citations.py`
  - `scripts/seed_contradictions.py`
  - `tests/test_citation_index.py`
  - `tests/test_contradiction_registry.py`
  - `tests/test_auto_proposer.py`
- Merge gate:
  - keep this lane downstream of Lane A
  - prove it extends organism truth/evaluation flows instead of introducing a parallel subsystem
- Notes:
  - this is the most self-evolving-adjacent uncommitted lane after Lane A itself

### Lane I: Cybernetics Directive And Onboarding

- Status: working tree only
- Primary scope:
  - `dharma_swarm/roaming_onboarding.py`
  - `dharma_swarm/policy_compiler.py`
  - `dharma_swarm/identity.py`
  - `dharma_swarm/ontology.py`
  - `dharma_swarm/self_improve.py`
  - `dharma_swarm/samvara.py`
  - `docs/missions/CYBERNETIC_DIRECTIVE.md`
  - `docs/missions/CYBERNETICS_POPULATION_CYCLE_V1.md`
  - `docs/missions/CYBERNETICS_RUNTIME_ACTIVATION_STATUS_2026-03-27.md`
  - `docs/plans/2026-03-26-living-agent-roaming-onboarding-architecture.md`
  - `scripts/onboard_cybernetics_stewards.py`
  - `scripts/rebind_cybernetics_directive.py`
  - `scripts/seed_cybernetics_directive.py`
  - `scripts/seed_cybernetics_population_cycle.py`
  - `tests/test_roaming_onboarding.py`
  - `tests/test_identity_v2.py`
  - `tests/test_samvara.py`
- Merge gate:
  - policy, identity, and onboarding tests pass together
  - docs and seeding scripts match the implemented directive model
- Notes:
  - mission-heavy lane; review for operational clarity before merge

### Lane J: A2A, Browser, And External Agent Adapters

- Status: working tree only
- Primary scope:
  - `dharma_swarm/a2a/`
  - `dharma_swarm/browser_agent.py`
  - `dharma_swarm/claude_cli.py`
  - `dharma_swarm/codex_cli.py`
  - `mcp_servers/playwright_server.py`
  - `dharma_swarm/tui/engine/adapters/codex.py`
  - `dharma_swarm/tui/engine/adapters/openrouter.py`
  - `tests/test_a2a.py`
  - `tests/test_browser_agent.py`
  - `tests/test_claude_cli.py`
  - `tests/tui/test_codex_adapter.py`
  - `tests/tui/test_openrouter_adapter.py`
- Merge gate:
  - adapter tests pass
  - external-agent contracts remain separated from the organism runtime core
- Notes:
  - merge after the core runtime lanes unless external integration is urgently needed

## Hot Overlap Files

- `dharma_swarm/agent_runner.py`
  - Lane A owns the committed self-evolving runtime-field and auto-research seam
  - Lane C owns the unstaged advanced-memory and observability residue
- `dharma_swarm/orchestrator.py`
  - Lane A owns the committed topology-genome dispatch seam
  - Lane D owns the unstaged preferred-agent routing and telic execution lease residue
- `dashboard/src/lib/api.ts`
  - likely depends on whichever runtime control API Lane F and Lane G finally expose
- `dharma_swarm/provider_policy.py`
  - sits between Lane E provider truthfulness work and Lane F operator control decisions

## Recommended Merge Order

1. Preserve Lane A as the base organism lane.
2. Preserve Lane B as the roaming/operator sub-stack.
3. Cut Lane C cleanly out of `agent_runner.py`.
4. Cut Lane D cleanly out of `orchestrator.py`.
5. Merge Lane H before broader mission/control-plane lanes if the goal is to keep self-evolving work central.
6. Merge Lane E before Lane F so operator-shell behavior rides on a settled provider/assurance contract.
7. Merge Lane G after Lane E if routing policy depends on provider matrix behavior.
8. Merge Lane I and Lane J after the runtime/control contracts are stable.

## Immediate Next Actions

- Export Lane C and Lane D into separate commits or branch-local patch stacks.
- Keep Lane A verification as the standing regression gate for any lane touching `agent_runner.py`, `orchestrator.py`, `workflow.py`, or `evolution.py`.
- Do not merge the remaining dirty-tree lanes directly from the current mixed worktree.
