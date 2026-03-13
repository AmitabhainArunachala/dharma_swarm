"""CLI for DHARMA SWARM — Typer-based command interface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from dharma_swarm.models import AgentRole, TaskPriority, TaskStatus

app = typer.Typer(name="dharma-swarm", help="DHARMA SWARM orchestrator CLI")
console = Console()


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


async def _get_swarm(state_dir: str = ".dharma"):
    from dharma_swarm.swarm import SwarmManager
    swarm = SwarmManager(state_dir=state_dir)
    await swarm.init()
    return swarm


# --- Init ---

@app.command()
def init(
    state_dir: str = typer.Option(".dharma", help="State directory path"),
):
    """Initialize a new DHARMA SWARM workspace."""
    async def _init():
        p = Path(state_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / "db").mkdir(exist_ok=True)
        swarm = await _get_swarm(state_dir)
        await swarm.shutdown()
        console.print(f"[green]Initialized DHARMA SWARM at {p.resolve()}[/green]")

    _run(_init())


# --- Spawn ---

@app.command()
def spawn(
    name: str = typer.Option(..., help="Agent name"),
    role: str = typer.Option("general", help="Agent role"),
    model: str = typer.Option("anthropic/claude-sonnet-4", help="Model ID (OpenRouter format)"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Spawn a new agent."""
    async def _spawn():
        swarm = await _get_swarm(state_dir)
        try:
            agent_role = AgentRole(role)
        except ValueError:
            console.print(f"[red]Invalid role: {role}. Choose from: {[r.value for r in AgentRole]}[/red]")
            raise typer.Exit(1)
        state = await swarm.spawn_agent(name=name, role=agent_role, model=model)
        console.print(f"[green]Spawned agent: {state.name} ({state.role.value}) — ID: {state.id}[/green]")
        await swarm.shutdown()

    _run(_spawn())


# --- Status ---

@app.command()
def status(
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Show swarm status."""
    async def _status():
        swarm = await _get_swarm(state_dir)
        state = await swarm.status()

        table = Table(title="DHARMA SWARM Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Uptime", f"{state.uptime_seconds:.1f}s")
        table.add_row("Agents", str(len(state.agents)))
        table.add_row("Tasks Pending", str(state.tasks_pending))
        table.add_row("Tasks Running", str(state.tasks_running))
        table.add_row("Tasks Completed", str(state.tasks_completed))
        table.add_row("Tasks Failed", str(state.tasks_failed))
        console.print(table)

        if state.agents:
            agent_table = Table(title="Agents")
            agent_table.add_column("ID", style="dim")
            agent_table.add_column("Name")
            agent_table.add_column("Role")
            agent_table.add_column("Status")
            for a in state.agents:
                color = {"idle": "green", "busy": "yellow", "dead": "red"}.get(a.status.value, "white")
                agent_table.add_row(a.id[:8], a.name, a.role.value, f"[{color}]{a.status.value}[/{color}]")
            console.print(agent_table)

        await swarm.shutdown()

    _run(_status())


# --- Task Commands ---

task_app = typer.Typer(help="Task management")
app.add_typer(task_app, name="task")


@task_app.command("create")
def task_create(
    title: str = typer.Argument(..., help="Task title"),
    description: str = typer.Option("", help="Task description"),
    priority: str = typer.Option("normal", help="Priority level"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Create a new task."""
    async def _create():
        swarm = await _get_swarm(state_dir)
        try:
            p = TaskPriority(priority)
        except ValueError:
            console.print(f"[red]Invalid priority: {priority}[/red]")
            await swarm.shutdown()
            raise typer.Exit(1)
        try:
            task = await swarm.create_task(title=title, description=description, priority=p)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            await swarm.shutdown()
            raise typer.Exit(1)
        console.print(f"[green]Created task: {task.title} — ID: {task.id}[/green]")
        await swarm.shutdown()

    _run(_create())


@task_app.command("list")
def task_list(
    status_filter: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """List tasks."""
    async def _list():
        swarm = await _get_swarm(state_dir)
        s = TaskStatus(status_filter) if status_filter else None
        tasks = await swarm.list_tasks(status=s)

        table = Table(title="Tasks")
        table.add_column("ID", style="dim")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Priority")
        table.add_column("Assigned")
        for t in tasks:
            table.add_row(t.id[:8], t.title, t.status.value, t.priority.value, t.assigned_to or "-")
        console.print(table)
        await swarm.shutdown()

    _run(_list())


# --- Memory ---

memory_app = typer.Typer(help="Memory operations")
app.add_typer(memory_app, name="memory")


@memory_app.command("store")
def memory_store(
    content: str = typer.Argument(..., help="Content to remember"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Store a memory."""
    async def _store():
        swarm = await _get_swarm(state_dir)
        await swarm.remember(content)
        console.print("[green]Stored.[/green]")
        await swarm.shutdown()

    _run(_store())


@memory_app.command("recall")
def memory_recall(
    limit: int = typer.Option(10, help="Max entries"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Recall recent memories."""
    async def _recall():
        swarm = await _get_swarm(state_dir)
        entries = await swarm.recall(limit=limit)
        for e in entries:
            console.print(f"[dim]{e.timestamp}[/dim] [{e.layer.value}] {e.content[:100]}")
        await swarm.shutdown()

    _run(_recall())


# --- Context ---

@app.command()
def context(
    role: str = typer.Option("general", help="Agent role"),
    thread: str = typer.Option(None, help="Research thread"),
):
    """Show what context an agent would receive."""
    from dharma_swarm.context import build_agent_context

    ctx = build_agent_context(role=role, thread=thread)
    console.print(f"[cyan]Context for role={role}, thread={thread}[/cyan]")
    console.print(f"[dim]{len(ctx):,} chars[/dim]\n")
    # Show section headers
    for line in ctx.split("\n"):
        if line.startswith("# ") or line.startswith("## "):
            console.print(f"[green]{line}[/green]")
    console.print(f"\n[dim]Full context: {len(ctx):,} chars ({len(ctx.split(chr(10)))} lines)[/dim]")


@app.command()
def context_full(
    role: str = typer.Option("general", help="Agent role"),
    thread: str = typer.Option(None, help="Research thread"),
):
    """Dump full context for an agent (for inspection)."""
    from dharma_swarm.context import build_agent_context

    ctx = build_agent_context(role=role, thread=thread)
    console.print(ctx)


# --- Swarm Run ---

@app.command()
def run(
    interval: float = typer.Option(2.0, help="Tick interval in seconds"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Run the orchestration loop."""
    async def _run_loop():
        swarm = await _get_swarm(state_dir)
        console.print("[green]DHARMA SWARM running. Ctrl+C to stop.[/green]")
        try:
            await swarm.run(interval=interval)
        except KeyboardInterrupt:
            pass
        finally:
            await swarm.shutdown()
            console.print("[yellow]Swarm stopped.[/yellow]")

    _run(_run_loop())


# --- Ledger ---

ledger_app = typer.Typer(help="Orchestrator ledger commands")
app.add_typer(ledger_app, name="ledger")


@ledger_app.command("tail")
def ledger_tail(
    n: int = typer.Option(20, help="Number of recent events to show"),
    session: Optional[str] = typer.Option(None, help="Session ID (default: most recent)"),
    kind: str = typer.Option("all", help="Which ledger: task, progress, or all"),
):
    """Show recent events from the orchestrator ledgers."""
    import json as _json
    from pathlib import Path as _Path

    ledger_base = _Path.home() / ".dharma" / "ledgers"
    if not ledger_base.exists():
        console.print("[dim]No ledgers found at ~/.dharma/ledgers/[/dim]")
        return

    sessions = sorted(ledger_base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    if session:
        target = ledger_base / session
        if not target.exists():
            console.print(f"[red]Session {session} not found.[/red]")
            raise typer.Exit(1)
    else:
        target = sessions[0]

    console.print(f"[cyan]Session: {target.name}[/cyan]")

    def _tail_file(path: _Path, label: str) -> None:
        if not path.exists():
            return
        lines = [l for l in path.read_text().splitlines() if l.strip()][-n:]
        if not lines:
            return
        console.print(f"\n[bold]{label}[/bold] ({path.name})")
        for line in lines:
            try:
                ev = _json.loads(line)
                ts = ev.get("ts_utc", "")[:19]
                event = ev.get("event", "?")
                task_id = ev.get("task_id", "")[:8]
                extra = ""
                if "duration_sec" in ev:
                    extra = f" ({ev['duration_sec']:.2f}s)"
                if "failure_signature" in ev:
                    extra = f" sig={ev['failure_signature'][:40]}"
                console.print(f"  [dim]{ts}[/dim] [green]{event}[/green] {task_id}{extra}")
            except Exception:
                console.print(f"  {line[:120]}")

    if kind in ("task", "all"):
        _tail_file(target / "task_ledger.jsonl", "Task Ledger")
    if kind in ("progress", "all"):
        _tail_file(target / "progress_ledger.jsonl", "Progress Ledger")


@ledger_app.command("sessions")
def ledger_sessions(
    n: int = typer.Option(10, help="Number of recent sessions to list"),
):
    """List recent orchestrator sessions."""
    from pathlib import Path as _Path

    ledger_base = _Path.home() / ".dharma" / "ledgers"
    if not ledger_base.exists():
        console.print("[dim]No ledgers directory found.[/dim]")
        return

    sessions = sorted(ledger_base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Recent Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Task Events", style="green")
    table.add_column("Progress Events", style="yellow")
    table.add_column("Age")

    import time as _time
    now = _time.time()
    for sess in sessions:
        task_f = sess / "task_ledger.jsonl"
        prog_f = sess / "progress_ledger.jsonl"
        task_n = sum(1 for _ in task_f.open()) if task_f.exists() else 0
        prog_n = sum(1 for _ in prog_f.open()) if prog_f.exists() else 0
        age_h = (now - sess.stat().st_mtime) / 3600
        age_str = f"{age_h:.1f}h ago" if age_h < 48 else f"{age_h/24:.0f}d ago"
        table.add_row(sess.name, str(task_n), str(prog_n), age_str)

    console.print(table)


# --- Evolution ---

evolve_app = typer.Typer(help="Evolution engine commands")
app.add_typer(evolve_app, name="evolve")


@evolve_app.command("propose")
def evolve_propose(
    component: str = typer.Argument(..., help="Module or file being changed"),
    description: str = typer.Argument(..., help="Description of the change"),
    change_type: str = typer.Option("mutation", help="mutation, crossover, or ablation"),
    diff: str = typer.Option("", help="Code diff (patch text)"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Propose an evolution and run it through the full pipeline."""
    async def _propose():
        swarm = await _get_swarm(state_dir)
        result = await swarm.evolve(
            component=component,
            change_type=change_type,
            description=description,
            diff=diff,
        )
        if result["status"] == "rejected":
            console.print(f"[red]REJECTED: {result['reason']}[/red]")
        else:
            console.print(
                f"[green]ARCHIVED: {result['entry_id']} "
                f"(fitness: {result['weighted_fitness']:.3f})[/green]"
            )
        await swarm.shutdown()

    _run(_propose())


@evolve_app.command("trend")
def evolve_trend(
    component: Optional[str] = typer.Option(None, help="Filter by component"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Show fitness trend over time."""
    async def _trend():
        swarm = await _get_swarm(state_dir)
        trend = await swarm.fitness_trend(component=component)
        if not trend:
            console.print("[dim]No fitness data yet.[/dim]")
        else:
            table = Table(title="Fitness Trend")
            table.add_column("Timestamp", style="dim")
            table.add_column("Fitness", style="green")
            for ts, fitness in trend:
                table.add_row(ts[:19], f"{fitness:.3f}")
            console.print(table)
        await swarm.shutdown()

    _run(_trend())


@app.command()
def evolve_verify(
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Verify cryptographic integrity of evolution archive (Merkle chain)."""
    async def _verify():
        swarm = await _get_swarm(state_dir)
        if swarm._engine is None:
            console.print("[red]Darwin engine not initialized. Run 'dgc evolve propose' first.[/red]")
            await swarm.shutdown()
            return

        valid, msg = swarm._engine.archive.verify_merkle_chain()
        if valid:
            console.print(f"[green]{msg}[/green]")
        else:
            console.print(f"[red]✗ {msg}[/red]")
        await swarm.shutdown()

    _run(_verify())


@app.command()
def evolve_economic(
    entry_id: Optional[str] = typer.Option(None, help="Entry ID (or latest if not provided)"),
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Show economic impact report for an evolution entry."""
    async def _economic():
        swarm = await _get_swarm(state_dir)
        if swarm._engine is None:
            console.print("[red]Darwin engine not initialized. Run 'dgc evolve propose' first.[/red]")
            await swarm.shutdown()
            return

        await swarm._engine.archive.load()

        # Get entry
        if entry_id:
            entry = await swarm._engine.archive.get_entry(entry_id)
        else:
            latest = await swarm._engine.archive.get_latest(n=1)
            entry = latest[0] if latest else None

        if not entry:
            console.print("[red]Entry not found[/red]")
            await swarm.shutdown()
            return

        # Get fitness score
        fitness = entry.fitness
        if fitness.economic_value == 0.5:
            console.print(f"[yellow]Entry {entry.id[:8]} has no economic metrics (neutral score)[/yellow]")
        else:
            # Try to extract economic metrics from test results
            # (In a real implementation, we'd store EconomicMetrics in test_results)
            console.print(f"\n[bold]Economic Impact: Entry {entry.id[:8]}[/bold]")
            console.print(f"Component: {entry.component}")
            console.print(f"Description: {entry.description}")
            console.print(f"\n[bold]Fitness Score[/bold]")
            console.print(f"Economic Value: {fitness.economic_value:.3f}")
            console.print(f"Overall Weighted: {fitness.weighted():.3f}")

            # If we have test_results with economic metrics, display them
            if "economic_metrics" in entry.test_results:
                metrics = entry.test_results["economic_metrics"]
                console.print(f"\n[bold]Detailed Metrics[/bold]")
                console.print(f"Annual Value: ${metrics.get('annual_value_usd', 0):.2f}/year")
                console.print(f"API Cost Saved: ${metrics.get('api_cost_saved', 0):.4f}/call")
                console.print(f"Time Saved: {metrics.get('time_saved_ms', 0):.0f}ms/call")
                console.print(f"Throughput Gain: {metrics.get('throughput_gain_pct', 0):.1f}%")
                console.print(f"Maintenance Cost: ${metrics.get('maintenance_cost', 0):.2f}/year")

        await swarm.shutdown()

    _run(_economic())


# --- Health ---

@app.command()
def health(
    state_dir: str = typer.Option(".dharma", help="State directory"),
):
    """Run system health check."""
    async def _health():
        swarm = await _get_swarm(state_dir)
        report = await swarm.health_check()

        status = report.get("overall_status", "unknown")
        color = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(status, "white")
        console.print(f"[{color}]Overall: {status}[/{color}]")
        console.print(f"  Total traces: {report.get('total_traces', 0)}")
        console.print(f"  Traces last hour: {report.get('traces_last_hour', 0)}")
        console.print(f"  Failure rate: {report.get('failure_rate', 0):.1%}")

        mean_f = report.get("mean_fitness")
        if mean_f is not None:
            console.print(f"  Mean fitness: {mean_f:.3f}")

        anomalies = report.get("anomalies", [])
        if anomalies:
            console.print(f"\n[yellow]Anomalies ({len(anomalies)}):[/yellow]")
            for a in anomalies:
                console.print(f"  [{a.get('severity', '?')}] {a.get('description', '')}")

        await swarm.shutdown()

    _run(_health())


@app.command()
def sprint(
    output: Optional[str] = typer.Option(None, help="Output file path (default: ~/.dharma/shared/SPRINT_8H_<date>.md)"),
    local: bool = typer.Option(False, "--local", help="Generate locally without LLM call (offline mode)"),
    test_summary: str = typer.Option("", help="Test results to include"),
    prev_todo: str = typer.Option("", help="Previous TODO items to include"),
    llm_timeout_sec: float = typer.Option(
        12.0,
        help="Timeout for remote sprint prompt generation before local fallback",
    ),
):
    """Generate today's adaptive 8-hour sprint prompt from live system state.

    Reads morning brief, dream seeds, sprint handoff, witness logs, and
    allout cycle history to generate a fresh GRANULAR/META/QUALITY sprint.
    """
    from datetime import date as _date
    from dharma_swarm.master_prompt_engineer import (
        gather_system_state,
        generate_evolved_prompt,
        generate_local_prompt,
        _days_to_colm,
        _SHARED_DIR,
    )

    today = _date.today().strftime("%Y%m%d")
    out_path = Path(output) if output else _SHARED_DIR / f"SPRINT_8H_{today}.md"

    async def _sprint():
        system_state = gather_system_state()
        colm_days, colm_paper = _days_to_colm()

        live = system_state.get("live_signals", {})
        console.print(f"[cyan]Sprint generator — {today}[/cyan]")
        console.print(f"  COLM abstract: {colm_days} days | paper: {colm_paper} days")
        console.print(f"  Morning brief: {'yes' if 'no morning' not in live.get('morning_brief','') else 'none'}")
        console.print(f"  Dream seeds: {'yes' if 'no dream' not in live.get('dream_seeds','') else 'none'}")
        console.print(f"  Sprint handoff: {'yes' if 'no handoff' not in live.get('sprint_handoff','') else 'none'}")

        if local:
            prompt_text = generate_local_prompt(
                test_summary=test_summary,
                prev_todo=prev_todo,
                colm_days=colm_days,
            )
            mode = "local"
        else:
            try:
                prompt_text = await generate_evolved_prompt(
                    system_state=system_state,
                    test_summary=test_summary,
                    prev_todo=prev_todo,
                    colm_days=colm_days,
                    llm_timeout_sec=llm_timeout_sec,
                )
                mode = "LLM"
            except Exception as e:
                console.print(f"[yellow]LLM unavailable ({e}), falling back to local mode[/yellow]")
                prompt_text = generate_local_prompt(
                    test_summary=test_summary,
                    prev_todo=prev_todo,
                    colm_days=colm_days,
                )
                mode = "local (fallback)"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f"# 8-HOUR SPRINT — {today}\n"
            f"**Generated**: {_date.today().isoformat()} | **Mode**: {mode}\n"
            f"**COLM**: {colm_days} days (abstract) / {colm_paper} days (paper)\n\n"
            + prompt_text
        )
        console.print(f"[green]Sprint written to: {out_path}[/green]")
        console.print(f"  Length: {len(prompt_text):,} chars | Mode: {mode}")

    _run(_sprint())


if __name__ == "__main__":
    app()
