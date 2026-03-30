"""Transitional entrypoint for the modular DGC command system."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import os
import sys

from .context import DgcContext, build_context
from .registry import DgcCommand, DgcCommandRegistry


@contextmanager
def _temporary_env(context: DgcContext) -> Iterator[None]:
    """Apply context-derived env overrides for the duration of one CLI run."""
    previous = {key: os.environ.get(key) for key in context.env}
    try:
        for key, value in context.env.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _build_parser() -> argparse.ArgumentParser:
    """Build the modular parser for commands already extracted from the monolith."""
    parser = argparse.ArgumentParser(prog="dgc", add_help=False)
    _build_registry().build_parser(parser)
    return parser


def _build_registry() -> DgcCommandRegistry:
    """Register the command packs already extracted from the monolith."""
    registry = DgcCommandRegistry()

    from .commands.mission import (
        cmd_campaign_brief,
        cmd_canonical_status,
        cmd_mission_brief,
        cmd_mission_status,
    )
    from .commands.ginko import build_ginko_parser, handle_ginko
    from .commands.dharma_ops import (
        build_cascade_parser,
        build_dharma_parser,
        build_forge_parser,
        build_hum_parser,
        build_loops_parser,
        build_stigmergy_parser,
        handle_cascade,
        handle_dharma,
        handle_forge,
        handle_hum,
        handle_loops,
        handle_stigmergy,
    )
    from .commands.observability import (
        build_audit_parser,
        build_eval_parser,
        build_instincts_parser,
        build_log_parser,
        build_loop_status_parser,
        build_review_parser,
        build_self_improve_parser,
        handle_audit,
        handle_eval,
        handle_instincts,
        handle_log,
        handle_loop_status,
        handle_review,
        handle_self_improve,
    )
    from .commands.runtime import (
        cmd_daemon_status,
        cmd_down,
        cmd_orchestrate_live,
        cmd_pulse,
        cmd_up,
    )
    from .commands.system import (
        build_agni_parser,
        build_bootstrap_parser,
        build_context_parser,
        build_develop_parser,
        build_free_fleet_parser,
        build_full_power_probe_parser,
        build_gates_parser,
        build_invariants_parser,
        build_map_parser,
        build_memory_parser,
        build_meta_parser,
        build_migrate_parser,
        build_model_catalog_parser,
        build_model_parser,
        build_organism_pulse_parser,
        build_prune_parser,
        build_run_parser,
        build_setup_parser,
        build_stress_parser,
        build_transcendence_parser,
        build_verify_baseline_parser,
        build_witness_parser,
        handle_agni,
        handle_bootstrap,
        handle_context,
        handle_develop,
        handle_free_fleet,
        handle_full_power_probe,
        handle_gates,
        handle_invariants,
        handle_map,
        handle_memory,
        handle_meta,
        handle_migrate,
        handle_model,
        handle_model_catalog,
        handle_organism_pulse,
        handle_prune,
        handle_run,
        handle_setup,
        handle_stress,
        handle_transcendence,
        handle_verify_baseline,
        handle_witness,
    )
    from .commands.knowledge import (
        build_field_parser,
        build_foundations_parser,
        build_telos_parser,
        handle_field,
        handle_foundations,
        handle_telos,
    )
    from .commands.ops import (
        build_cron_parser,
        build_custodians_parser,
        build_doctor_parser,
        build_foreman_parser,
        build_gateway_parser,
        build_health_check_parser,
        build_health_parser,
        build_initiatives_parser,
        build_maintenance_parser,
        build_review_cycle_parser,
        build_xray_parser,
        handle_cron,
        handle_custodians,
        handle_doctor,
        handle_foreman,
        handle_gateway,
        handle_health,
        handle_health_check,
        handle_initiatives,
        handle_maintenance,
        handle_review_cycle,
        handle_xray,
    )
    from .commands.agents import (
        build_agent_parser,
        build_evolve_parser,
        build_spawn_parser,
        build_task_parser,
        handle_agent,
        handle_evolve,
        handle_spawn,
        handle_task,
    )
    from .commands.semantic import build_parser as build_semantic_parser, handle as handle_semantic
    from .commands.status import cmd_runtime_status, cmd_status
    from .commands.swarm import cmd_swarm
    from .commands.ux import (
        build_chat_parser,
        build_dashboard_parser,
        build_ui_parser,
        handle_chat,
        handle_dashboard,
        handle_ui,
    )
    from .commands.providers import (
        build_flywheel_parser,
        build_ouroboros_parser,
        build_provider_matrix_parser,
        build_provider_smoke_parser,
        build_rag_parser,
        build_reciprocity_parser,
        handle_flywheel,
        handle_ouroboros,
        handle_provider_matrix,
        handle_provider_smoke,
        handle_rag,
        handle_reciprocity,
    )
    from .commands.workflow import (
        build_agent_memory_parser,
        build_autonomy_parser,
        build_compose_parser,
        build_context_search_parser,
        build_execute_compose_parser,
        build_handoff_parser,
        build_ledger_parser,
        build_orchestrate_parser,
        build_overnight_parser,
        build_route_parser,
        build_skills_parser,
        build_sprint_parser,
        handle_agent_memory,
        handle_autonomy,
        handle_compose,
        handle_context_search,
        handle_execute_compose,
        handle_handoff,
        handle_ledger,
        handle_orchestrate,
        handle_overnight,
        handle_route,
        handle_skills,
        handle_sprint,
    )

    def _add_status(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser("status")

    def _handle_status(_args: argparse.Namespace) -> None:
        cmd_status()

    registry.register(
        DgcCommand(
            name="status",
            handler=_handle_status,
            build_parser=_add_status,
            pack="status",
            read_only=True,
        )
    )

    def _add_runtime_status(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("runtime-status")
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--db-path", default=None)

    def _handle_runtime_status(args: argparse.Namespace) -> None:
        cmd_runtime_status(limit=args.limit, db_path=args.db_path)

    registry.register(
        DgcCommand(
            name="runtime-status",
            handler=_handle_runtime_status,
            build_parser=_add_runtime_status,
            pack="status",
            read_only=True,
        )
    )

    def _add_mission_status(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("mission-status")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--strict-core", action="store_true")
        parser.add_argument("--require-tracked", action="store_true")
        parser.add_argument("--profile", default=None)

    def _handle_mission_status(args: argparse.Namespace) -> int:
        return cmd_mission_status(
            as_json=args.json,
            strict_core=args.strict_core,
            require_tracked=args.require_tracked,
            profile=args.profile,
        )

    registry.register(
        DgcCommand(
            name="mission-status",
            handler=_handle_mission_status,
            build_parser=_add_mission_status,
            pack="mission",
            read_only=True,
        )
    )

    def _add_mission_brief(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("mission-brief")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--path", default=None)
        parser.add_argument("--state-dir", default=None)

    def _handle_mission_brief(args: argparse.Namespace) -> int:
        return cmd_mission_brief(
            path=args.path,
            state_dir=args.state_dir,
            as_json=args.json,
        )

    registry.register(
        DgcCommand(
            name="mission-brief",
            handler=_handle_mission_brief,
            build_parser=_add_mission_brief,
            pack="mission",
            read_only=True,
        )
    )

    def _add_campaign_brief(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("campaign-brief")
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--path", default=None)
        parser.add_argument("--state-dir", default=None)

    def _handle_campaign_brief(args: argparse.Namespace) -> int:
        return cmd_campaign_brief(
            path=args.path,
            state_dir=args.state_dir,
            as_json=args.json,
        )

    registry.register(
        DgcCommand(
            name="campaign-brief",
            handler=_handle_campaign_brief,
            build_parser=_add_campaign_brief,
            pack="mission",
            read_only=True,
        )
    )

    def _add_canonical_status(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("canonical-status")
        parser.add_argument("--json", action="store_true")

    def _handle_canonical_status(args: argparse.Namespace) -> int:
        return cmd_canonical_status(as_json=args.json)

    registry.register(
        DgcCommand(
            name="canonical-status",
            handler=_handle_canonical_status,
            build_parser=_add_canonical_status,
            pack="mission",
            read_only=True,
        )
    )

    def _add_up(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("up")
        parser.add_argument("--background", action="store_true")

    def _handle_up(args: argparse.Namespace) -> None:
        cmd_up(background=args.background)

    registry.register(
        DgcCommand(
            name="up",
            handler=_handle_up,
            build_parser=_add_up,
            pack="runtime",
        )
    )

    def _add_down(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser("down")

    def _handle_down(_args: argparse.Namespace) -> None:
        cmd_down()

    registry.register(
        DgcCommand(
            name="down",
            handler=_handle_down,
            build_parser=_add_down,
            pack="runtime",
        )
    )

    def _add_daemon_status(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser("daemon-status")

    def _handle_daemon_status(_args: argparse.Namespace) -> None:
        cmd_daemon_status()

    registry.register(
        DgcCommand(
            name="daemon-status",
            handler=_handle_daemon_status,
            build_parser=_add_daemon_status,
            pack="runtime",
            read_only=True,
        )
    )

    def _add_pulse(subparsers: argparse._SubParsersAction) -> None:
        subparsers.add_parser("pulse")

    def _handle_pulse(_args: argparse.Namespace) -> None:
        cmd_pulse()

    registry.register(
        DgcCommand(
            name="pulse",
            handler=_handle_pulse,
            build_parser=_add_pulse,
            pack="runtime",
        )
    )

    def _add_orchestrate_live(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("orchestrate-live")
        parser.add_argument("--background", action="store_true")

    def _handle_orchestrate_live(args: argparse.Namespace) -> None:
        cmd_orchestrate_live(background=args.background)

    registry.register(
        DgcCommand(
            name="orchestrate-live",
            handler=_handle_orchestrate_live,
            build_parser=_add_orchestrate_live,
            pack="runtime",
        )
    )

    def _add_swarm(subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser("swarm")
        parser.add_argument("swarm_args", nargs="*", default=[])

    def _handle_swarm(args: argparse.Namespace) -> None:
        cmd_swarm(args.swarm_args)

    registry.register(
        DgcCommand(
            name="swarm",
            handler=_handle_swarm,
            build_parser=_add_swarm,
            pack="swarm",
        )
    )

    registry.register(
        DgcCommand(
            name="semantic",
            handler=handle_semantic,
            build_parser=build_semantic_parser,
            pack="semantic",
        )
    )

    registry.register(
        DgcCommand(
            name="provider-smoke",
            handler=handle_provider_smoke,
            build_parser=build_provider_smoke_parser,
            pack="providers",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="provider-matrix",
            handler=handle_provider_matrix,
            build_parser=build_provider_matrix_parser,
            pack="providers",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="rag",
            handler=handle_rag,
            build_parser=build_rag_parser,
            pack="providers",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="flywheel",
            handler=handle_flywheel,
            build_parser=build_flywheel_parser,
            pack="providers",
        )
    )

    registry.register(
        DgcCommand(
            name="reciprocity",
            handler=handle_reciprocity,
            build_parser=build_reciprocity_parser,
            pack="providers",
        )
    )

    registry.register(
        DgcCommand(
            name="ouroboros",
            handler=handle_ouroboros,
            build_parser=build_ouroboros_parser,
            pack="providers",
        )
    )

    registry.register(
        DgcCommand(
            name="chat",
            handler=handle_chat,
            build_parser=build_chat_parser,
            pack="ux",
        )
    )

    registry.register(
        DgcCommand(
            name="dashboard",
            handler=handle_dashboard,
            build_parser=build_dashboard_parser,
            pack="ux",
        )
    )

    registry.register(
        DgcCommand(
            name="ui",
            handler=handle_ui,
            build_parser=build_ui_parser,
            pack="ux",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="health",
            handler=handle_health,
            build_parser=build_health_parser,
            pack="ops",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="health-check",
            handler=handle_health_check,
            build_parser=build_health_check_parser,
            pack="ops",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="doctor",
            handler=handle_doctor,
            build_parser=build_doctor_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="xray",
            handler=handle_xray,
            build_parser=build_xray_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="foreman",
            handler=handle_foreman,
            build_parser=build_foreman_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="review-cycle",
            handler=handle_review_cycle,
            build_parser=build_review_cycle_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="initiatives",
            handler=handle_initiatives,
            build_parser=build_initiatives_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="cron",
            handler=handle_cron,
            build_parser=build_cron_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="gateway",
            handler=handle_gateway,
            build_parser=build_gateway_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="custodians",
            handler=handle_custodians,
            build_parser=build_custodians_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="maintenance",
            handler=handle_maintenance,
            build_parser=build_maintenance_parser,
            pack="ops",
        )
    )

    registry.register(
        DgcCommand(
            name="field",
            handler=handle_field,
            build_parser=build_field_parser,
            pack="knowledge",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="foundations",
            handler=handle_foundations,
            build_parser=build_foundations_parser,
            pack="knowledge",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="telos",
            handler=handle_telos,
            build_parser=build_telos_parser,
            pack="knowledge",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="map",
            handler=handle_map,
            build_parser=build_map_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="stress",
            handler=handle_stress,
            build_parser=build_stress_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="full-power-probe",
            handler=handle_full_power_probe,
            build_parser=build_full_power_probe_parser,
            aliases=("probe",),
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="context",
            handler=handle_context,
            build_parser=build_context_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="memory",
            handler=handle_memory,
            build_parser=build_memory_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="witness",
            handler=handle_witness,
            build_parser=build_witness_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="develop",
            handler=handle_develop,
            build_parser=build_develop_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="gates",
            handler=handle_gates,
            build_parser=build_gates_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="organism-pulse",
            handler=handle_organism_pulse,
            build_parser=build_organism_pulse_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="invariants",
            handler=handle_invariants,
            build_parser=build_invariants_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="transcendence",
            handler=handle_transcendence,
            build_parser=build_transcendence_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="verify-baseline",
            handler=handle_verify_baseline,
            build_parser=build_verify_baseline_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="setup",
            handler=handle_setup,
            build_parser=build_setup_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="migrate",
            handler=handle_migrate,
            build_parser=build_migrate_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="model",
            handler=handle_model,
            build_parser=build_model_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="agni",
            handler=handle_agni,
            build_parser=build_agni_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="run",
            handler=handle_run,
            build_parser=build_run_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="bootstrap",
            handler=handle_bootstrap,
            build_parser=build_bootstrap_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="meta",
            handler=handle_meta,
            build_parser=build_meta_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="prune",
            handler=handle_prune,
            build_parser=build_prune_parser,
            pack="system",
        )
    )

    registry.register(
        DgcCommand(
            name="free-fleet",
            handler=handle_free_fleet,
            build_parser=build_free_fleet_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="model-catalog",
            handler=handle_model_catalog,
            build_parser=build_model_catalog_parser,
            pack="system",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="spawn",
            handler=handle_spawn,
            build_parser=build_spawn_parser,
            pack="agents",
        )
    )

    registry.register(
        DgcCommand(
            name="agent",
            handler=handle_agent,
            build_parser=build_agent_parser,
            pack="agents",
        )
    )

    registry.register(
        DgcCommand(
            name="task",
            handler=handle_task,
            build_parser=build_task_parser,
            pack="agents",
        )
    )

    registry.register(
        DgcCommand(
            name="evolve",
            handler=handle_evolve,
            build_parser=build_evolve_parser,
            pack="agents",
        )
    )

    registry.register(
        DgcCommand(
            name="dharma",
            handler=handle_dharma,
            build_parser=build_dharma_parser,
            pack="dharma",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="stigmergy",
            handler=handle_stigmergy,
            build_parser=build_stigmergy_parser,
            pack="dharma",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="hum",
            handler=handle_hum,
            build_parser=build_hum_parser,
            pack="dharma",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="cascade",
            handler=handle_cascade,
            build_parser=build_cascade_parser,
            pack="dharma",
        )
    )

    registry.register(
        DgcCommand(
            name="forge",
            handler=handle_forge,
            build_parser=build_forge_parser,
            pack="dharma",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="loops",
            handler=handle_loops,
            build_parser=build_loops_parser,
            pack="dharma",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="skills",
            handler=handle_skills,
            build_parser=build_skills_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="route",
            handler=handle_route,
            build_parser=build_route_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="orchestrate",
            handler=handle_orchestrate,
            build_parser=build_orchestrate_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="autonomy",
            handler=handle_autonomy,
            build_parser=build_autonomy_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="context-search",
            handler=handle_context_search,
            build_parser=build_context_search_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="compose",
            handler=handle_compose,
            build_parser=build_compose_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="execute-compose",
            handler=handle_execute_compose,
            build_parser=build_execute_compose_parser,
            pack="workflow",
        )
    )

    registry.register(
        DgcCommand(
            name="overnight",
            handler=handle_overnight,
            build_parser=build_overnight_parser,
            pack="workflow",
        )
    )

    registry.register(
        DgcCommand(
            name="handoff",
            handler=handle_handoff,
            build_parser=build_handoff_parser,
            pack="workflow",
        )
    )

    registry.register(
        DgcCommand(
            name="agent-memory",
            handler=handle_agent_memory,
            build_parser=build_agent_memory_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="sprint",
            handler=handle_sprint,
            build_parser=build_sprint_parser,
            pack="workflow",
        )
    )

    registry.register(
        DgcCommand(
            name="ledger",
            handler=handle_ledger,
            build_parser=build_ledger_parser,
            pack="workflow",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="eval",
            handler=handle_eval,
            build_parser=build_eval_parser,
            pack="observability",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="log",
            handler=handle_log,
            build_parser=build_log_parser,
            pack="observability",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="self-improve",
            handler=handle_self_improve,
            build_parser=build_self_improve_parser,
            pack="observability",
        )
    )

    registry.register(
        DgcCommand(
            name="audit",
            handler=handle_audit,
            build_parser=build_audit_parser,
            pack="observability",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="review",
            handler=handle_review,
            build_parser=build_review_parser,
            pack="observability",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="instincts",
            handler=handle_instincts,
            build_parser=build_instincts_parser,
            pack="observability",
        )
    )

    registry.register(
        DgcCommand(
            name="loop-status",
            handler=handle_loop_status,
            build_parser=build_loop_status_parser,
            pack="observability",
            read_only=True,
        )
    )

    registry.register(
        DgcCommand(
            name="ginko",
            handler=handle_ginko,
            build_parser=build_ginko_parser,
            pack="ginko",
        )
    )

    return registry


def _dispatch_known_command(argv: list[str]) -> bool:
    """Dispatch commands already extracted into modular packs.

    Returns ``True`` when the modular layer handled the command and ``False``
    when control should fall through to the legacy CLI.
    """
    if not argv:
        return False
    registry = _build_registry()
    if registry.resolve(argv[0]) is None:
        return False

    args = _build_parser().parse_args(argv)
    return registry.dispatch(args)


def main() -> None:
    """Delegate to the legacy CLI until command packs are extracted."""
    context = build_context()
    with _temporary_env(context):
        if _dispatch_known_command(sys.argv[1:]):
            return
        from dharma_swarm import dgc_cli

        dgc_cli.main()
