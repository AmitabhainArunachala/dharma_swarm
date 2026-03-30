"""Operations command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_health() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_health()


def cmd_health_check() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_health_check()


def cmd_doctor(
    *,
    doctor_cmd: str = "run",
    as_json: bool = False,
    strict: bool = False,
    quick: bool = False,
    timeout: float = 1.5,
    schedule: str = "every 6h",
    interval_sec: float = 1800.0,
    max_runs: int | None = None,
) -> int:
    from dharma_swarm import dgc_cli

    return dgc_cli.cmd_doctor(
        doctor_cmd=doctor_cmd,
        as_json=as_json,
        strict=strict,
        quick=quick,
        timeout=timeout,
        schedule=schedule,
        interval_sec=interval_sec,
        max_runs=max_runs,
    )


def cmd_xray(
    repo_path: str,
    output: str | None = None,
    as_json: bool = False,
    exclude: list[str] | None = None,
    packet: bool = False,
    buyer: str = "CTO or founder under shipping pressure",
) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_xray(
        repo_path=repo_path,
        output=output,
        as_json=as_json,
        exclude=exclude,
        packet=packet,
        buyer=buyer,
    )


def cmd_foreman(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_foreman(**kwargs)


def cmd_review(hours: float = 6.0, skip_tests: bool = False) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_review(hours=hours, skip_tests=skip_tests)


def cmd_initiatives(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_initiatives(**kwargs)


def cmd_cron(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_cron(**kwargs)


def cmd_gateway(config_path: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_gateway(config_path=config_path)


def cmd_custodians(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_custodians(**kwargs)


def build_health_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("health", help="Ecosystem file health")


def handle_health(_args: argparse.Namespace) -> None:
    cmd_health()


def build_health_check_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("health-check", help="Monitor-based system health check")


def handle_health_check(_args: argparse.Namespace) -> None:
    cmd_health_check()


def build_doctor_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("doctor", help="Deep runtime diagnostics and fix guidance")
    parser.add_argument("doctor_action", nargs="?", default="run", choices=("run", "latest", "schedule", "watch"))
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on WARN")
    parser.add_argument("--quick", action="store_true", help="Skip deep network/package probes")
    parser.add_argument("--timeout", type=float, default=1.5, help="Probe timeout seconds")
    parser.add_argument("--schedule", default="every 6h", help="Recurring schedule for `dgc doctor schedule`")
    parser.add_argument("--interval-sec", type=float, default=1800.0, help="Loop interval seconds for `dgc doctor watch`")
    parser.add_argument("--max-runs", type=int, default=None, help="Optional max iterations for `dgc doctor watch`")


def handle_doctor(args: argparse.Namespace) -> int:
    return cmd_doctor(
        doctor_cmd=args.doctor_action,
        as_json=args.json,
        strict=args.strict,
        quick=args.quick,
        timeout=args.timeout,
        schedule=args.schedule,
        interval_sec=args.interval_sec,
        max_runs=args.max_runs,
    )


def build_xray_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("xray", help="Run Repo X-Ray — codebase analysis for any repo")
    parser.add_argument("repo_path", help="Path to repository to analyze")
    parser.add_argument("--output", "-o", default=None, help="Output file path")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON instead of markdown")
    parser.add_argument("--exclude", nargs="*", default=None, help="Path patterns to exclude")
    parser.add_argument("--packet", action="store_true", help="Generate a productized Repo X-Ray packet directory instead of a single report file")
    parser.add_argument("--buyer", default="CTO or founder under shipping pressure", help="Target buyer persona for the productized packet")


def handle_xray(args: argparse.Namespace) -> None:
    cmd_xray(
        repo_path=args.repo_path,
        output=args.output,
        as_json=args.as_json,
        exclude=getattr(args, "exclude", None),
        packet=getattr(args, "packet", False),
        buyer=getattr(args, "buyer", "CTO or founder under shipping pressure"),
    )


def build_foreman_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("foreman", help="The Foreman — focused quality forge")
    foreman_sub = parser.add_subparsers(dest="foreman_cmd")
    p_fm_add = foreman_sub.add_parser("add", help="Register a project")
    p_fm_add.add_argument("path", help="Path to the project root")
    p_fm_add.add_argument("--name", default=None, help="Friendly project name")
    p_fm_add.add_argument("--test-command", default=None, help="Test command (e.g. 'pytest')")
    p_fm_add.add_argument("--exclude", nargs="*", default=None, help="Path patterns to exclude")
    p_fm_run = foreman_sub.add_parser("run", help="Run one forge cycle")
    p_fm_run.add_argument("--level", default="observe", choices=["observe", "advise", "build"], help="Execution level")
    p_fm_run.add_argument("--project", default=None, help="Filter to one project")
    p_fm_run.add_argument("--skip-tests", action="store_true", help="Skip running test suites")
    foreman_sub.add_parser("status", help="Show quality dashboard")
    p_fm_cron = foreman_sub.add_parser("cron", help="Start recurring forge cycle")
    p_fm_cron.add_argument("--schedule", default="every 4h", help="Cron schedule")
    p_fm_cron.add_argument("--level", default="advise", choices=["observe", "advise", "build"], help="Execution level")


def handle_foreman(args: argparse.Namespace) -> None:
    cmd_foreman(
        foreman_cmd=args.foreman_cmd,
        path=getattr(args, "path", ""),
        name=getattr(args, "name", None),
        test_command=getattr(args, "test_command", None),
        exclude=getattr(args, "exclude", None),
        level=getattr(args, "level", "observe"),
        project=getattr(args, "project", None),
        skip_tests=getattr(args, "skip_tests", False),
        schedule=getattr(args, "schedule", "every 4h"),
    )


def build_review_cycle_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("review-cycle", help="Generate 6-hour review cycle report")
    parser.add_argument("--hours", type=float, default=6.0, help="Review window in hours")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")


def handle_review_cycle(args: argparse.Namespace) -> None:
    cmd_review(hours=args.hours, skip_tests=args.skip_tests)


def build_initiatives_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("initiatives", help="Initiative depth ledger")
    init_sub = parser.add_subparsers(dest="init_cmd")
    init_sub.add_parser("list", help="List all initiatives")
    p_init_add = init_sub.add_parser("add", help="Add a new initiative")
    p_init_add.add_argument("--title", required=True, help="Initiative title")
    p_init_add.add_argument("--description", default="", help="Description")
    p_init_promote = init_sub.add_parser("promote", help="Promote an initiative")
    p_init_promote.add_argument("initiative_id", help="Initiative ID")
    p_init_abandon = init_sub.add_parser("abandon", help="Abandon an initiative")
    p_init_abandon.add_argument("initiative_id", help="Initiative ID")
    p_init_abandon.add_argument("--reason", required=True, help="Reason for abandonment")
    init_sub.add_parser("summary", help="Show initiative summary")


def handle_initiatives(args: argparse.Namespace) -> None:
    cmd_initiatives(
        init_cmd=args.init_cmd,
        title=getattr(args, "title", ""),
        description=getattr(args, "description", ""),
        initiative_id=getattr(args, "initiative_id", ""),
        reason=getattr(args, "reason", ""),
    )


def build_cron_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("cron", help="Cron job scheduler (v0.6.0)")
    cron_sub = parser.add_subparsers(dest="cron_cmd")
    p_cron_add = cron_sub.add_parser("add", help="Add a new cron job")
    p_cron_add.add_argument("prompt", help="Task prompt to execute")
    p_cron_add.add_argument("schedule", help="Schedule: '30m', 'every 2h', '0 9 * * *'")
    p_cron_add.add_argument("--name", default=None, help="Friendly job name")
    p_cron_add.add_argument("--repeat", type=int, default=None, help="Repeat count (None=forever)")
    p_cron_add.add_argument("--deliver", default="local", help="Delivery target")
    p_cron_add.add_argument("--urgent", action="store_true", help="Run even during quiet hours")
    cron_sub.add_parser("list", help="List all cron jobs")
    p_cron_rm = cron_sub.add_parser("remove", help="Remove a cron job")
    p_cron_rm.add_argument("job_id", help="Job ID to remove")
    cron_sub.add_parser("tick", help="Manually trigger a cron tick")
    p_cron_daemon = cron_sub.add_parser("daemon", help="Run the cron scheduler as a local daemon")
    p_cron_daemon.add_argument("--interval-sec", type=float, default=60.0, help="Seconds between cron ticks")
    p_cron_daemon.add_argument("--max-loops", type=int, default=None, help="Stop after N tick loops (useful for testing)")
    p_cron_daemon.add_argument("--no-run-immediately", dest="run_immediately", action="store_false", help="Sleep for one interval before the first tick")
    p_cron_daemon.set_defaults(run_immediately=True)


def handle_cron(args: argparse.Namespace) -> None:
    cmd_cron(
        cron_cmd=args.cron_cmd,
        prompt=getattr(args, "prompt", ""),
        schedule=getattr(args, "schedule", ""),
        name=getattr(args, "name", None),
        repeat=getattr(args, "repeat", None),
        deliver=getattr(args, "deliver", "local"),
        urgent=getattr(args, "urgent", False),
        job_id=getattr(args, "job_id", ""),
        interval_sec=getattr(args, "interval_sec", 60.0),
        max_loops=getattr(args, "max_loops", None),
        run_immediately=getattr(args, "run_immediately", True),
    )


def build_gateway_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("gateway", help="Start messaging gateway (v0.6.0)")
    parser.add_argument("--config", default=None, help="Path to gateway.yaml")


def handle_gateway(args: argparse.Namespace) -> None:
    cmd_gateway(config_path=args.config)


def build_custodians_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("custodians", help="Autonomous code maintenance fleet")
    cust_sub = parser.add_subparsers(dest="custodians_cmd")
    p_cust_run = cust_sub.add_parser("run", help="Run custodian maintenance cycle")
    p_cust_run.add_argument("--roles", default=None, help="Comma-separated roles (default: all)")
    p_cust_run.add_argument("--dry-run", dest="dry_run", action="store_true", default=True, help="Show what would be done (default)")
    p_cust_run.add_argument("--execute", dest="dry_run", action="store_false", help="Actually execute changes")
    cust_sub.add_parser("status", help="Show custodian fleet status")
    cust_sub.add_parser("schedule", help="Create recurring custodian cron jobs")


def handle_custodians(args: argparse.Namespace) -> None:
    cmd_custodians(
        custodians_cmd=args.custodians_cmd,
        roles=getattr(args, "roles", None),
        dry_run=getattr(args, "dry_run", True),
    )


def cmd_maintenance(*, dry_run: bool = False, max_mb: float = 50.0) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_maintenance(dry_run=dry_run, max_mb=max_mb)


def build_maintenance_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("maintenance", help="WAL checkpoint + JSONL rotation")
    parser.add_argument("--dry-run", action="store_true", help="Preview rotations without executing")
    parser.add_argument("--max-mb", type=float, default=50.0, help="JSONL rotation threshold in MB")


def handle_maintenance(args: argparse.Namespace) -> None:
    cmd_maintenance(
        dry_run=getattr(args, "dry_run", False),
        max_mb=getattr(args, "max_mb", 50.0),
    )
