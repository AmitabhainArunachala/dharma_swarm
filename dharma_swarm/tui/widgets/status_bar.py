"""Always-visible top status bar with live reactive metrics.

Displays model, cost, context usage, turn count, mode, and running state.
All fields are Textual reactives -- updating any field triggers a re-render
of just this single-line widget.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from rich.text import Text


class StatusBar(Widget):
    """Single-line status bar showing session metrics.

    Reactive attributes:
    - model: current LLM model name
    - cost_usd: accumulated cost for the session
    - context_pct: context window utilization (0-100)
    - turn_count: number of assistant turns
    - mode: operating mode (N=Normal, A=Auto, P=Plan, S=Sage)
    - session_name: display name for the session
    - is_running: whether Claude is currently generating
    """

    model: reactive[str] = reactive("claude-sonnet-4-5")
    cost_usd: reactive[float] = reactive(0.0)
    context_pct: reactive[int] = reactive(0)
    turn_count: reactive[int] = reactive(0)
    mode: reactive[str] = reactive("N")
    session_name: reactive[str] = reactive("")
    is_running: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text 60%;
    }
    """

    MODE_COLORS: dict[str, str] = {
        "N": "#5D8C6E",   # Rokusho — verdigris
        "A": "#C2956B",   # Kitsurubami — persimmon
        "P": "#6B9BB5",   # Hanada — washed indigo
        "S": "#9B85B8",   # Fuji — wisteria
    }

    def render(self) -> Text:
        """Render the status bar as a single Rich Text line."""
        mode_color = self.MODE_COLORS.get(self.mode, "white")

        if self.context_pct > 80:
            ctx_color = "#C25B52"   # Bengara
        elif self.context_pct > 60:
            ctx_color = "#C2956B"   # Kitsurubami
        else:
            ctx_color = "#5D8C6E"   # Rokusho

        running_indicator = "\u27f3 " if self.is_running else ""
        display_name = self.session_name or "dgc"

        parts = [
            f" [{mode_color}][{self.mode}][/{mode_color}]",
            f"  {running_indicator}{display_name}",
            f"  |  {self.model}",
            f"  |  [{ctx_color}]ctx:{self.context_pct}%[/{ctx_color}]",
            f"  |  ${self.cost_usd:.4f}",
            f"  |  turns:{self.turn_count}",
        ]
        return Text.from_markup("".join(parts))

    # ── Convenience updaters ──────────────────────────────────────────

    def update_from_init(
        self,
        *,
        model: str = "",
        session_name: str = "",
    ) -> None:
        """Bulk-update from a SystemInit event."""
        if model:
            self.model = model
        if session_name:
            self.session_name = session_name

    def update_from_result(
        self,
        *,
        cost_usd: float = 0.0,
        num_turns: int = 0,
    ) -> None:
        """Bulk-update from a ResultMessage event."""
        self.cost_usd = cost_usd
        self.turn_count = num_turns
        self.is_running = False

    def increment_turn(self) -> None:
        """Increment the turn counter by one."""
        self.turn_count += 1
