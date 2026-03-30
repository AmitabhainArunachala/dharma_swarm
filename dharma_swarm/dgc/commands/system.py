"""System and control-plane command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def cmd_stress(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_stress(**kwargs)


def cmd_full_power_probe(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_full_power_probe(**kwargs)


def cmd_context(domain: str = "all") -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_context(domain)


def cmd_memory() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_memory()


def cmd_witness(message: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_witness(message)


def cmd_develop(what: str, evidence: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_develop(what, evidence)


def cmd_gates(action: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_gates(action)


def cmd_organism_pulse(task: str | None = None, dry_run: bool = False) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_organism_pulse(task=task, dry_run=dry_run)


def cmd_invariants() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_invariants()


def cmd_transcendence() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_transcendence()


def cmd_verify_baseline() -> None:
    from dharma_swarm.claude_hooks import verify_baseline

    result = verify_baseline()
    print(json.dumps(result, indent=2))
    gates = result.get("gates", {})
    health = result.get("health", {})
    status = health.get("status", "unknown") if isinstance(health, dict) else "unknown"
    print(f"\nGates: {gates.get('passed', '?')}/{gates.get('total', '?')} | Health: {status}")
    if gates.get("decision") == "BLOCK":
        raise SystemExit(1)


def cmd_setup() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_setup()


def cmd_migrate() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_migrate()


def cmd_model(action: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_model(action)


def cmd_agni(command: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_agni(command)


def cmd_run(interval: float) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_run(interval)


def cmd_bootstrap() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_bootstrap()


def cmd_map(*, as_json: bool = False, layer: int | None = None) -> None:
    from dharma_swarm.living_map import generate, generate_json

    if as_json:
        print(json.dumps(generate_json(), indent=2, default=str))
    else:
        print(generate(layer=layer))


def cmd_meta() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli._run_meta()


def cmd_prune(
    *,
    dry_run: bool = False,
    stig_threshold: float = 0.3,
    bridge_threshold: float = 0.2,
    trace_days: int = 14,
) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli._run_prune(
        dry_run=dry_run,
        stig_threshold=stig_threshold,
        bridge_threshold=bridge_threshold,
        trace_days=trace_days,
    )


def cmd_free_fleet(*, tier: int | None = None, as_json: bool = False, set_env: bool = False) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_free_fleet(tier=tier, as_json=as_json, set_env=set_env)


def cmd_model_catalog(*, selector: str | None = None, as_json: bool = False) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_model_catalog(selector=selector, as_json=as_json)


def build_stress_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stress", help="Run max-capacity DGC stress harness")
    parser.add_argument("--profile", choices=["quick", "full", "max"], default="full")
    parser.add_argument("--state-dir", default=str(Path.home() / ".dharma" / "stress_lab"))
    parser.add_argument(
        "--provider-mode",
        choices=["auto", "mock", "claude", "codex", "openrouter"],
        default="auto",
    )
    parser.add_argument("--agents", type=int, default=8)
    parser.add_argument("--tasks", type=int, default=36)
    parser.add_argument("--evolutions", type=int, default=24)
    parser.add_argument("--evolution-concurrency", type=int, default=6)
    parser.add_argument("--cli-rounds", type=int, default=2)
    parser.add_argument("--cli-concurrency", type=int, default=8)
    parser.add_argument("--orchestration-timeout-sec", type=int, default=240)
    parser.add_argument("--external-timeout-sec", type=int, default=120)
    parser.add_argument("--external-research", action="store_true")


def handle_stress(args: argparse.Namespace) -> None:
    cmd_stress(
        profile=args.profile,
        state_dir=args.state_dir,
        provider_mode=args.provider_mode,
        agents=args.agents,
        tasks=args.tasks,
        evolutions=args.evolutions,
        evolution_concurrency=args.evolution_concurrency,
        cli_rounds=args.cli_rounds,
        cli_concurrency=args.cli_concurrency,
        orchestration_timeout_sec=args.orchestration_timeout_sec,
        external_research=args.external_research,
        external_timeout_sec=args.external_timeout_sec,
    )


def build_full_power_probe_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "full-power-probe",
        aliases=["probe"],
        help="Run the reusable operator-facing full-power probe",
    )
    parser.add_argument(
        "--route-task",
        default="test the full power of dgc from inside the system and show what it can do",
    )
    parser.add_argument(
        "--context-search-query",
        default="mechanistic thread reports unfinished work active modules evidence paths",
    )
    parser.add_argument(
        "--compose-task",
        default=(
            "Probe DGC full power from inside this workspace, verify the mechanistic "
            "thread snapshot, and produce a concrete artifact"
        ),
    )
    parser.add_argument(
        "--autonomy-action",
        default="run a broad but safe local full-power probe without mutating external systems",
    )
    parser.add_argument("--skip-sprint-probe", action="store_true")
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")


def handle_full_power_probe(args: argparse.Namespace) -> None:
    cmd_full_power_probe(
        route_task=args.route_task,
        context_search_query=args.context_search_query,
        compose_task=args.compose_task,
        autonomy_action=args.autonomy_action,
        skip_sprint_probe=args.skip_sprint_probe,
        skip_stress=args.skip_stress,
        skip_pytest=args.skip_pytest,
    )


def build_context_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("context", help="Load context for a domain")
    parser.add_argument("domain", nargs="?", default="all")


def handle_context(args: argparse.Namespace) -> None:
    cmd_context(args.domain)


def build_memory_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("memory", help="Show memory status")


def handle_memory(_args: argparse.Namespace) -> None:
    cmd_memory()


def build_witness_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("witness", help="Record a witness observation")
    parser.add_argument("message", nargs="+")


def handle_witness(args: argparse.Namespace) -> None:
    cmd_witness(" ".join(args.message))


def build_develop_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("develop", help="Record a development marker")
    parser.add_argument("what")
    parser.add_argument("evidence", nargs="+")


def handle_develop(args: argparse.Namespace) -> None:
    cmd_develop(args.what, " ".join(args.evidence))


def build_gates_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("gates", help="Run telos gates on an action")
    parser.add_argument("action", nargs="+")


def handle_gates(args: argparse.Namespace) -> None:
    cmd_gates(" ".join(args.action))


def build_organism_pulse_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "organism-pulse",
        help="Run one canonical organism pulse (sense→constrain→execute→evaluate→adapt)",
    )
    parser.add_argument("--task", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")


def handle_organism_pulse(args: argparse.Namespace) -> None:
    cmd_organism_pulse(task=args.task, dry_run=args.dry_run)


def build_invariants_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("invariants", help="Show the 4 computable system invariants")


def handle_invariants(_args: argparse.Namespace) -> None:
    cmd_invariants()


def build_transcendence_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("transcendence", help="Show transcendence metrics (ensemble vs individual)")


def handle_transcendence(_args: argparse.Namespace) -> None:
    cmd_transcendence()


def build_verify_baseline_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("verify-baseline", help="Full baseline verification (gates + health)")


def handle_verify_baseline(_args: argparse.Namespace) -> None:
    cmd_verify_baseline()


def build_setup_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("setup", help="Install dependencies")


def handle_setup(_args: argparse.Namespace) -> None:
    cmd_setup()


def build_migrate_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("migrate", help="Migrate old DGC memory")


def handle_migrate(_args: argparse.Namespace) -> None:
    cmd_migrate()


def build_model_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("model", help="Model management and switching")
    parser.add_argument("action", nargs="?", default="status")


def handle_model(args: argparse.Namespace) -> None:
    cmd_model(args.action)


def build_agni_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("agni", help="Run command on AGNI VPS")
    parser.add_argument("remote_cmd", nargs="+")


def handle_agni(args: argparse.Namespace) -> None:
    cmd_agni(" ".join(args.remote_cmd))


def build_run_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("run", help="Run orchestration loop")
    parser.add_argument("--interval", type=float, default=2.0)


def handle_run(args: argparse.Namespace) -> None:
    cmd_run(interval=args.interval)


def build_bootstrap_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("bootstrap", help="Generate bootstrap manifest (NOW.json) — orients any new LLM instance")


def handle_bootstrap(_args: argparse.Namespace) -> None:
    cmd_bootstrap()


def build_map_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("map", help="Living map — all 8 layers, regenerated fresh from live sources")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--layer", type=int, default=None)


def handle_map(args: argparse.Namespace) -> None:
    cmd_map(as_json=args.json, layer=args.layer)


def build_meta_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("meta", help="Overseeing I — wholistic system assessment")


def handle_meta(_args: argparse.Namespace) -> None:
    cmd_meta()


def build_prune_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("prune", help="Sweep the zen garden — cut noise, keep signal")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stig-threshold", type=float, default=0.3)
    parser.add_argument("--bridge-threshold", type=float, default=0.2)
    parser.add_argument("--trace-days", type=int, default=14)


def handle_prune(args: argparse.Namespace) -> None:
    cmd_prune(
        dry_run=args.dry_run,
        stig_threshold=args.stig_threshold,
        bridge_threshold=args.bridge_threshold,
        trace_days=args.trace_days,
    )


def build_free_fleet_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("free-fleet", help="Show free-tier OpenRouter model fleet")
    parser.add_argument("--tier", type=int, default=None)
    parser.add_argument("--json", dest="json", action="store_true", default=False)
    parser.add_argument("--set-env", dest="set_env", action="store_true", default=False)


def handle_free_fleet(args: argparse.Namespace) -> None:
    cmd_free_fleet(tier=args.tier, as_json=args.json, set_env=args.set_env)


def build_model_catalog_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("model-catalog", help="Show canonical model packs and routing selectors")
    parser.add_argument("selector", nargs="?", default=None)
    parser.add_argument("--json", dest="json", action="store_true", default=False)


def handle_model_catalog(args: argparse.Namespace) -> None:
    cmd_model_catalog(selector=args.selector, as_json=args.json)
