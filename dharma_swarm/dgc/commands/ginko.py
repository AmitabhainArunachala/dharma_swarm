"""Ginko command pack for the modular DGC CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone


def cmd_ginko(ginko_cmd: str | None, **kwargs) -> None:
    try:
        match ginko_cmd:
            case "status":
                from dharma_swarm.ginko_orchestrator import ginko_status

                print(ginko_status())
            case "dashboard":
                from dharma_swarm.ginko_brier import format_dashboard_report

                print(format_dashboard_report())
            case "edge":
                from dharma_swarm.ginko_orchestrator import check_edge_validation

                result = check_edge_validation()
                print(json.dumps(result, indent=2, default=str))
            case "register-crons":
                from dharma_swarm.ginko_orchestrator import register_ginko_crons

                created = register_ginko_crons()
                if created:
                    for job in created:
                        print(f"  Created: {job['name']} ({job.get('schedule_display', '')})")
                else:
                    print("  All Ginko crons already registered.")
            case "pull":
                from dharma_swarm.ginko_orchestrator import action_data_pull

                result = asyncio.run(action_data_pull())
                print("Data pull complete:")
                print(f"  Macro: {'yes' if result.get('macro_available') else 'no'}")
                print(f"  Stocks: {result.get('stocks_count', 0)}")
                print(f"  Crypto: {result.get('crypto_count', 0)}")
                if result.get("errors"):
                    print(f"  Errors: {', '.join(result['errors'])}")
            case "signals":
                from dharma_swarm.ginko_orchestrator import action_generate_signals

                result = asyncio.run(action_generate_signals())
                if result.get("error"):
                    print(f"Error: {result['error']}")
                else:
                    print(result.get("report_text", "No report generated"))
            case "predict":
                from dharma_swarm.ginko_brier import record_prediction

                resolve_by = kwargs.get("resolve_by") or (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                pred = record_prediction(
                    question=kwargs["question"],
                    probability=kwargs["probability"],
                    resolve_by=resolve_by,
                    category=kwargs["category"],
                )
                print("Prediction recorded:")
                print(f"  ID: {pred.id}")
                print(f"  Question: {pred.question}")
                print(f"  Probability: {pred.probability:.0%}")
                print(f"  Resolve by: {pred.resolve_by}")
            case "resolve":
                from dharma_swarm.ginko_brier import resolve_prediction

                pred = resolve_prediction(kwargs["prediction_id"], kwargs["outcome"])
                if pred:
                    print(f"Resolved: {pred.question}")
                    print(f"  Outcome: {'YES' if pred.outcome == 1.0 else 'NO'}")
                    print(f"  Brier score: {pred.brier_score:.4f}")
                else:
                    print(f"Prediction {kwargs['prediction_id']} not found or already resolved")
            case "brier":
                from dharma_swarm.ginko_brier import format_dashboard_report

                print(format_dashboard_report())
            case "report":
                from dharma_swarm.ginko_orchestrator import action_generate_report

                result = asyncio.run(action_generate_report())
                print(result.get("report_text", "No report generated"))
            case "portfolio":
                try:
                    from dharma_swarm.ginko_paper_trade import PaperPortfolio

                    portfolio = PaperPortfolio()
                    stats = portfolio.get_portfolio_stats()
                    print("Dharmic Quant — Paper Portfolio")
                    print("=" * 40)
                    print(f"  Total value: ${stats.get('total_value', 0):,.2f}")
                    print(f"  Cash: ${stats.get('cash', 0):,.2f}")
                    print(f"  P&L: {stats.get('total_pnl_pct', 0):+.2f}%")
                    print(f"  Open positions: {stats.get('open_positions', 0)}")
                    print(f"  Sharpe ratio: {stats.get('sharpe_ratio', 0):.2f}")
                    print(f"  Max drawdown: {stats.get('max_drawdown', 0):.1%}")
                    print(f"  Win rate: {stats.get('win_rate', 0):.1%}")
                    print(f"  Trades: {stats.get('trade_count', 0)}")
                except Exception as exc:
                    print(f"Portfolio not available: {exc}")
            case "cycle":
                from dharma_swarm.ginko_orchestrator import action_full_cycle

                print("Running full Ginko cycle...")
                result = asyncio.run(action_full_cycle())
                for phase, data in result.items():
                    if phase == "total_duration_ms":
                        continue
                    status = "ERROR" if isinstance(data, dict) and "error" in data else "OK"
                    print(f"  {phase}: {status}")
                print(f"\nTotal duration: {result.get('total_duration_ms', 0)}ms")
            case "fleet":
                try:
                    from dharma_swarm.ginko_agents import GinkoFleet

                    fleet = GinkoFleet()
                    agents = fleet.list_agents()
                    print("Dharmic Quant — Agent Fleet")
                    print("=" * 40)
                    for agent in agents:
                        status = agent.status if hasattr(agent, "status") else "unknown"
                        fitness = agent.fitness if hasattr(agent, "fitness") else 0.0
                        calls = agent.total_calls if hasattr(agent, "total_calls") else 0
                        name = agent.name if hasattr(agent, "name") else str(agent)
                        role = agent.role if hasattr(agent, "role") else ""
                        print(f"  {name.upper():12s} {role:20s} fitness={fitness:.0%} calls={calls} [{status}]")
                except Exception as exc:
                    print(f"Fleet not available: {exc}")
            case _:
                print("Usage: dgc ginko {status|pull|signals|predict|resolve|brier|report|portfolio|cycle|fleet|dashboard|edge|register-crons}")
    except Exception as exc:
        print(f"Ginko command failed: {exc}")
        raise SystemExit(2) from exc


def build_ginko_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ginko", help="Shakti Ginko autonomous economic engine")
    ginko_sub = parser.add_subparsers(dest="ginko_cmd")
    ginko_sub.add_parser("status", help="Ginko VentureCell status + Brier dashboard")
    ginko_sub.add_parser("dashboard", help="Full Brier score dashboard report")
    ginko_sub.add_parser("register-crons", help="Register Ginko cron jobs")
    ginko_sub.add_parser("edge", help="Check edge validation status")
    ginko_sub.add_parser("pull", help="Pull market data from all sources")
    ginko_sub.add_parser("signals", help="Generate signal report")
    predict = ginko_sub.add_parser("predict", help="Record a new prediction")
    predict.add_argument("question")
    predict.add_argument("probability", type=float)
    predict.add_argument("--category", default="general")
    predict.add_argument("--resolve-by", default=None)
    resolve = ginko_sub.add_parser("resolve", help="Resolve a prediction")
    resolve.add_argument("prediction_id")
    resolve.add_argument("outcome", type=float)
    ginko_sub.add_parser("brier", help="Show Brier score dashboard")
    ginko_sub.add_parser("report", help="Generate daily intelligence report")
    ginko_sub.add_parser("portfolio", help="Show paper portfolio status")
    ginko_sub.add_parser("cycle", help="Run full daily cycle")
    ginko_sub.add_parser("fleet", help="List all agents with status and fitness")


def handle_ginko(args: argparse.Namespace) -> None:
    cmd_ginko(
        args.ginko_cmd,
        question=getattr(args, "question", None),
        probability=getattr(args, "probability", None),
        category=getattr(args, "category", "general"),
        resolve_by=getattr(args, "resolve_by", None),
        prediction_id=getattr(args, "prediction_id", None),
        outcome=getattr(args, "outcome", None),
    )
