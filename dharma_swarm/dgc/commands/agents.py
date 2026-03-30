"""Agent, task, and evolution command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse


def cmd_spawn(name: str, role: str, model: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_spawn(name=name, role=role, model=model)


def cmd_agent(agent_cmd: str | None, *, name: str = "", task: str = "", model: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    match agent_cmd:
        case "wake":
            dgc_cli._cmd_agent_wake(name, task, model)
        case "list":
            dgc_cli._cmd_agent_list()
        case "runs":
            dgc_cli._cmd_agent_runs()
        case _:
            raise SystemExit(2)


def cmd_task(task_cmd: str | None, *, title: str = "", description: str = "", priority: str = "normal", status_filter: str | None = None) -> None:
    from dharma_swarm import dgc_cli

    match task_cmd:
        case "create":
            dgc_cli.cmd_task_create(title, description, priority)
        case "list":
            dgc_cli.cmd_task_list(status_filter)
        case _:
            raise SystemExit(2)


def cmd_evolve(evolve_cmd: str | None, **kwargs) -> None:
    from dharma_swarm import dgc_cli

    match evolve_cmd:
        case "propose":
            dgc_cli.cmd_evolve_propose(
                kwargs["component"],
                kwargs["description"],
                kwargs["change_type"],
                kwargs["diff"],
            )
        case "trend":
            dgc_cli.cmd_evolve_trend(kwargs.get("component"))
        case "apply":
            dgc_cli.cmd_evolve_apply(kwargs["component"], kwargs["description"])
        case "promote":
            dgc_cli.cmd_evolve_promote(kwargs["entry_id"])
        case "rollback":
            dgc_cli.cmd_evolve_rollback(kwargs["entry_id"], kwargs["reason"])
        case "auto":
            dgc_cli.cmd_evolve_auto(
                kwargs.get("files"),
                kwargs["model"],
                kwargs["context"],
                single_model=kwargs["single_model"],
                shadow=kwargs["shadow"],
                token_budget=kwargs["token_budget"],
            )
        case "daemon":
            dgc_cli.cmd_evolve_daemon(
                kwargs["interval"],
                kwargs["threshold"],
                kwargs["model"],
                kwargs["cycles"],
                single_model=kwargs["single_model"],
                shadow=kwargs["shadow"],
                token_budget=kwargs["token_budget"],
            )
        case _:
            raise SystemExit(2)


def build_spawn_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("spawn", help="Spawn a new agent")
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="general")
    parser.add_argument("--model", default="anthropic/claude-opus-4-6")


def handle_spawn(args: argparse.Namespace) -> None:
    cmd_spawn(name=args.name, role=args.role, model=args.model)


def build_agent_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("agent", help="Autonomous agents with multi-step reasoning and tool use")
    agent_sub = parser.add_subparsers(dest="agent_cmd")
    wake = agent_sub.add_parser("wake", help="Wake an agent with a task")
    wake.add_argument("name")
    wake.add_argument("--task", "-t", required=True)
    wake.add_argument("--model", "-m", default=None)
    agent_sub.add_parser("list", help="List available preset agents")
    agent_sub.add_parser("runs", help="Show recent agent run reports")


def handle_agent(args: argparse.Namespace) -> None:
    cmd_agent(
        args.agent_cmd,
        name=getattr(args, "name", ""),
        task=getattr(args, "task", ""),
        model=getattr(args, "model", None),
    )


def build_task_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="Task management")
    task_sub = parser.add_subparsers(dest="task_cmd")
    create = task_sub.add_parser("create", help="Create a task")
    create.add_argument("title")
    create.add_argument("--description", default="")
    create.add_argument("--priority", default="normal")
    list_parser = task_sub.add_parser("list", help="List tasks")
    list_parser.add_argument("--status", dest="status_filter", default=None)


def handle_task(args: argparse.Namespace) -> None:
    cmd_task(
        args.task_cmd,
        title=getattr(args, "title", ""),
        description=getattr(args, "description", ""),
        priority=getattr(args, "priority", "normal"),
        status_filter=getattr(args, "status_filter", None),
    )


def build_evolve_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("evolve", help="Evolution engine commands")
    evolve_sub = parser.add_subparsers(dest="evolve_cmd")

    propose = evolve_sub.add_parser("propose", help="Propose an evolution")
    propose.add_argument("component")
    propose.add_argument("description")
    propose.add_argument("--change-type", default="mutation")
    propose.add_argument("--diff", default="")

    trend = evolve_sub.add_parser("trend", help="Show fitness trend")
    trend.add_argument("--component", default=None)

    apply_parser = evolve_sub.add_parser("apply", help="Apply evolution with sandbox")
    apply_parser.add_argument("component")
    apply_parser.add_argument("description")

    promote = evolve_sub.add_parser("promote", help="Promote a canary")
    promote.add_argument("entry_id")

    rollback = evolve_sub.add_parser("rollback", help="Rollback a deployment")
    rollback.add_argument("entry_id")
    rollback.add_argument("--reason", default="Manual rollback")

    auto = evolve_sub.add_parser("auto", help="LLM-powered autonomous evolution")
    auto.add_argument("--files", nargs="*")
    auto.add_argument("--model", default="")
    auto.add_argument("--context", default="")
    auto.add_argument("--single-model", action="store_true")
    auto.add_argument("--shadow", action="store_true")
    auto.add_argument("--token-budget", type=int, default=0)

    daemon = evolve_sub.add_parser("daemon", help="Run continuous autonomous evolution")
    daemon.add_argument("--interval", type=float, default=1800.0)
    daemon.add_argument("--threshold", type=float, default=0.6)
    daemon.add_argument("--model", default="")
    daemon.add_argument("--cycles", type=int, default=None)
    daemon.add_argument("--single-model", action="store_true")
    daemon.add_argument("--shadow", action="store_true")
    daemon.add_argument("--token-budget", type=int, default=0)


def handle_evolve(args: argparse.Namespace) -> None:
    cmd_evolve(
        args.evolve_cmd,
        component=getattr(args, "component", None),
        description=getattr(args, "description", None),
        change_type=getattr(args, "change_type", "mutation"),
        diff=getattr(args, "diff", ""),
        entry_id=getattr(args, "entry_id", None),
        reason=getattr(args, "reason", "Manual rollback"),
        files=getattr(args, "files", None),
        model=getattr(args, "model", ""),
        context=getattr(args, "context", ""),
        single_model=getattr(args, "single_model", False),
        shadow=getattr(args, "shadow", False),
        token_budget=getattr(args, "token_budget", 0),
        interval=getattr(args, "interval", 1800.0),
        threshold=getattr(args, "threshold", 0.6),
        cycles=getattr(args, "cycles", None),
    )
