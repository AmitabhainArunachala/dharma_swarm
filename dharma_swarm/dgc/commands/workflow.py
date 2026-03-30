"""Workflow and orchestration command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse
import asyncio
import json


DEFAULT_SPRINT_LLM_TIMEOUT_SEC = 12.0


def cmd_skills() -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_skills()


def cmd_route(description: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_route(description)


def cmd_orchestrate(description: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_orchestrate(description)


def cmd_autonomy(action: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_autonomy(action)


def cmd_context_search(query: str, budget: int = 10_000) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_context_search(query, budget=budget)


def cmd_compose(description: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_compose(description)


def cmd_execute_compose(description: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_execute_compose(description)


def cmd_overnight(
    *,
    hours: float = 8.0,
    dry_run: bool = False,
    autonomy: int = 1,
    max_tokens: int = 500_000,
    cycle_timeout: float = 900.0,
) -> None:
    from dharma_swarm.overnight_director import run_overnight

    result = asyncio.run(
        run_overnight(
            hours=hours,
            dry_run=dry_run,
            autonomy_level=autonomy,
            max_tokens=max_tokens,
            cycle_timeout=cycle_timeout,
        )
    )
    print(json.dumps(result, indent=2))


def cmd_handoff(from_agent: str, to_agent: str, context: str, content: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_handoff(from_agent, to_agent, context, content)


def cmd_agent_memory(agent_name: str) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_agent_memory(agent_name)


def cmd_sprint(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_sprint(**kwargs)


def cmd_ledger(**kwargs) -> None:
    from dharma_swarm import dgc_cli

    dgc_cli.cmd_ledger(**kwargs)


def build_skills_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("skills", help="List discovered skills (v0.4.0)")


def handle_skills(_args: argparse.Namespace) -> None:
    cmd_skills()


def build_route_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("route", help="Route a task to best skill (v0.4.0)")
    parser.add_argument("task_desc", nargs="+")


def handle_route(args: argparse.Namespace) -> None:
    cmd_route(" ".join(args.task_desc))


def build_orchestrate_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("orchestrate", help="Decompose and orchestrate a task (v0.4.0)")
    parser.add_argument("orch_desc", nargs="+")


def handle_orchestrate(args: argparse.Namespace) -> None:
    cmd_orchestrate(" ".join(args.orch_desc))


def build_autonomy_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("autonomy", help="Check autonomy for an action (v0.4.0)")
    parser.add_argument("auto_action", nargs="+")


def handle_autonomy(args: argparse.Namespace) -> None:
    cmd_autonomy(" ".join(args.auto_action))


def build_context_search_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("context-search", help="Search for task-relevant context (v0.4.0)")
    parser.add_argument("cs_query", nargs="+")
    parser.add_argument("--budget", type=int, default=10000)


def handle_context_search(args: argparse.Namespace) -> None:
    cmd_context_search(" ".join(args.cs_query), budget=args.budget)


def build_compose_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("compose", help="Compose a task into DAG execution plan (v0.4.1)")
    parser.add_argument("comp_desc", nargs="+")


def handle_compose(args: argparse.Namespace) -> None:
    cmd_compose(" ".join(args.comp_desc))


def build_execute_compose_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("execute-compose", help="Compose and execute a task DAG end-to-end")
    parser.add_argument("exec_comp_desc", nargs="+")


def handle_execute_compose(args: argparse.Namespace) -> None:
    cmd_execute_compose(" ".join(args.exec_comp_desc))


def build_overnight_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("overnight", help="Run overnight autonomous loop")
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--autonomy", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=500_000)
    parser.add_argument("--cycle-timeout", type=float, default=900.0)


def handle_overnight(args: argparse.Namespace) -> None:
    cmd_overnight(
        hours=args.hours,
        dry_run=args.dry_run,
        autonomy=args.autonomy,
        max_tokens=args.max_tokens,
        cycle_timeout=args.cycle_timeout,
    )


def build_handoff_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("handoff", help="Create a structured agent handoff (v0.4.1)")
    parser.add_argument("--from", dest="ho_from", required=True)
    parser.add_argument("--to", dest="ho_to", required=True)
    parser.add_argument("--context", dest="ho_context", required=True)
    parser.add_argument("content", nargs="+")


def handle_handoff(args: argparse.Namespace) -> None:
    cmd_handoff(args.ho_from, args.ho_to, args.ho_context, " ".join(args.content))


def build_agent_memory_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("agent-memory", help="Agent self-editing memory (v0.4.1)")
    parser.add_argument("mem_agent")


def handle_agent_memory(args: argparse.Namespace) -> None:
    cmd_agent_memory(args.mem_agent)


def build_sprint_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sprint", help="Generate today's adaptive 8-hour sprint prompt")
    parser.add_argument("--output", default=None)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--test-summary", default="")
    parser.add_argument("--prev-todo", default="")
    parser.add_argument("--llm-timeout-sec", type=float, default=DEFAULT_SPRINT_LLM_TIMEOUT_SEC)


def handle_sprint(args: argparse.Namespace) -> None:
    cmd_sprint(
        output=args.output,
        local=args.local,
        test_summary=args.test_summary,
        prev_todo=args.prev_todo,
        llm_timeout_sec=args.llm_timeout_sec,
    )


def build_ledger_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ledger", help="Inspect orchestrator session ledgers")
    ledger_sub = parser.add_subparsers(dest="ledger_cmd")

    tail = ledger_sub.add_parser("tail", help="Show recent ledger events")
    tail.add_argument("-n", type=int, default=20)
    tail.add_argument("--session", default=None)
    tail.add_argument("--kind", choices=["task", "progress", "all"], default="all")

    ledger_sub.add_parser("sessions", help="List recent sessions")

    search = ledger_sub.add_parser("search", help="Search indexed ledger events")
    search.add_argument("query", nargs="+")
    search.add_argument("-n", type=int, default=10)
    search.add_argument("--session", default=None)
    search.add_argument("--kind", choices=["task", "progress", "all"], default="all")
    search.add_argument("--db-path", default=None)
    search.add_argument("--no-sync-ledgers", action="store_true")
    search.add_argument("--limit-sessions", type=int, default=None)

    index = ledger_sub.add_parser("index", help="Index ledger JSONL into runtime search store")
    index.add_argument("--session", default=None)
    index.add_argument("--db-path", default=None)
    index.add_argument("--limit-sessions", type=int, default=None)


def handle_ledger(args: argparse.Namespace) -> None:
    cmd_ledger(
        ledger_cmd=args.ledger_cmd,
        n=getattr(args, "n", 20),
        session=getattr(args, "session", None),
        kind=getattr(args, "kind", "all"),
        query=" ".join(getattr(args, "query", []) or []),
        db_path=getattr(args, "db_path", None),
        sync_ledgers=not getattr(args, "no_sync_ledgers", False),
        limit_sessions=getattr(args, "limit_sessions", None),
    )
