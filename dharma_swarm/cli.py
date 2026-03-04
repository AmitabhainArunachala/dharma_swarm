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
    model: str = typer.Option("claude-sonnet-4-20250514", help="Model ID"),
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
            raise typer.Exit(1)
        task = await swarm.create_task(title=title, description=description, priority=p)
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


if __name__ == "__main__":
    app()
