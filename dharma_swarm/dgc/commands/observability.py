"""Observability and oversight command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path


def cmd_eval(eval_cmd: str | None) -> int | None:
    from dharma_swarm.ecc_eval_harness import (
        cmd_eval_dashboard,
        cmd_eval_report,
        cmd_eval_run,
        cmd_eval_trend,
    )

    match eval_cmd:
        case "run":
            return asyncio.run(cmd_eval_run())
        case "report":
            return cmd_eval_report()
        case "trend":
            return cmd_eval_trend()
        case "dashboard":
            return cmd_eval_dashboard()
        case _:
            raise SystemExit(2)


def cmd_log(log_cmd: str | None, query: str | None = None) -> None:
    checker = str(Path.home() / ".dharma" / "conversation_log" / "promise_checker.py")
    match log_cmd:
        case "promises":
            subprocess.run([sys.executable, checker, "--promises"])
        case "stats":
            subprocess.run([sys.executable, checker, "--stats"])
        case "search":
            subprocess.run([sys.executable, checker, "--search", query or ""])
        case _:
            subprocess.run([sys.executable, checker, "--log"])


def cmd_self_improve(si_cmd: str | None) -> int | None:
    from dharma_swarm.self_improve import (
        cmd_self_improve_history,
        cmd_self_improve_run,
        cmd_self_improve_status,
    )

    match si_cmd:
        case "status":
            return cmd_self_improve_status()
        case "history":
            return cmd_self_improve_history()
        case "run":
            return asyncio.run(cmd_self_improve_run())
        case _:
            return cmd_self_improve_status()


def cmd_audit(audit_cmd: str | None) -> int | None:
    from dharma_swarm.harness_audit import cmd_audit, cmd_audit_trend

    match audit_cmd:
        case "trend":
            return cmd_audit_trend()
        case _:
            return cmd_audit()


def cmd_review() -> int | None:
    from dharma_swarm.review_bridge import cmd_review_scan

    return cmd_review_scan()


def cmd_instincts(instinct_cmd: str | None) -> int | None:
    from dharma_swarm.instinct_bridge import cmd_instincts_status, cmd_instincts_sync

    match instinct_cmd:
        case "status":
            return cmd_instincts_status()
        case "sync":
            return asyncio.run(cmd_instincts_sync())
        case _:
            raise SystemExit(2)


def cmd_loop_status() -> int | None:
    from dharma_swarm.loop_supervisor import cmd_loop_status

    return cmd_loop_status()


def build_eval_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("eval", help="ECC eval harness — measure system health")
    eval_sub = parser.add_subparsers(dest="eval_cmd")
    eval_sub.add_parser("run", help="Run all evals and print scorecard")
    eval_sub.add_parser("report", help="Print latest eval report")
    eval_sub.add_parser("trend", help="Show historical pass rates")
    eval_sub.add_parser("dashboard", help="Single-screen eval dashboard")


def handle_eval(args: argparse.Namespace) -> int | None:
    return cmd_eval(args.eval_cmd)


def build_log_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("log", help="Conversation log — what was said + promises")
    log_sub = parser.add_subparsers(dest="log_cmd")
    log_sub.add_parser("recent", help="Show recent conversation entries (default)")
    log_sub.add_parser("promises", help="Show detected promises/commitments")
    log_sub.add_parser("stats", help="Conversation statistics")
    search = log_sub.add_parser("search", help="Search promises")
    search.add_argument("query", nargs="+")


def handle_log(args: argparse.Namespace) -> None:
    cmd_log(args.log_cmd, query=" ".join(getattr(args, "query", []) or []))


def build_self_improve_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("self-improve", help="Self-improvement cycle — strange loop")
    si_sub = parser.add_subparsers(dest="si_cmd")
    si_sub.add_parser("status", help="Show self-improvement status")
    si_sub.add_parser("history", help="Show cycle history")
    si_sub.add_parser("run", help="Run one cycle manually (requires DHARMA_SELF_IMPROVE=1)")


def handle_self_improve(args: argparse.Namespace) -> int | None:
    return cmd_self_improve(args.si_cmd)


def build_audit_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("audit", help="Harness audit — 7-dimension scorecard")
    audit_sub = parser.add_subparsers(dest="audit_cmd")
    audit_sub.add_parser("run", help="Run audit and print scorecard (default)")
    audit_sub.add_parser("trend", help="Show audit trend over time")


def handle_audit(args: argparse.Namespace) -> int | None:
    return cmd_audit(args.audit_cmd)


def build_review_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("review", help="Review bridge — ruff findings as evolution proposals")


def handle_review(_args: argparse.Namespace) -> int | None:
    return cmd_review()


def build_instincts_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("instincts", help="Instinct bridge — ECC ↔ fitness signals")
    inst_sub = parser.add_subparsers(dest="instinct_cmd")
    inst_sub.add_parser("status", help="Show bridge status")
    inst_sub.add_parser("sync", help="Process new observations and emit signals")


def handle_instincts(args: argparse.Namespace) -> int | None:
    return cmd_instincts(args.instinct_cmd)


def build_loop_status_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("loop-status", help="Loop supervisor — health of all loops")


def handle_loop_status(_args: argparse.Namespace) -> int | None:
    return cmd_loop_status()
