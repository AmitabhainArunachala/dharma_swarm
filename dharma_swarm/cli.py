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
                console.print(f"  {ts[:19]}  {fitness:.3f}")
        await swarm.shutdown()

    _run(_trend())


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


if __name__ == "__main__":
    app()
