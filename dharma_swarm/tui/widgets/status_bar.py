"""Always-visible top status bar with live reactive metrics.

Displays the active route, current phase, tool activity, token I/O, cost,
context usage, and turn count. All fields are Textual reactives, so updating
any field triggers a re-render of just this single-line widget.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from rich.text import Text

INDIGO = "#46525B"
VERDIGRIS = "#62725D"
OCHRE = "#9C7444"
BENGARA = "#8C5448"
WISTERIA = "#74677D"


class StatusBar(Widget):
    """Single-line status bar showing session metrics.

    Reactive attributes:
    - model: current LLM model name
    - activity: short live phase label (thinking, tool:bash, complete, etc.)
    - tool_count: number of tool calls observed in the current run
    - last_tool: last tool name seen in the current run
    - input_tokens: latest provider-reported input token count
    - output_tokens: latest provider-reported output token count
    - cost_usd: accumulated cost for the session
    - context_pct: context window utilization (0-100)
    - turn_count: number of assistant turns
    - mode: operating mode (N=Normal, A=Auto, P=Plan, S=Sage)
    - session_name: display name for the session
    - is_running: whether the active provider is currently generating
    """

    model: reactive[str] = reactive("claude-sonnet-4-5")
    activity: reactive[str] = reactive("ready")
    tool_count: reactive[int] = reactive(0)
    last_tool: reactive[str] = reactive("")
    input_tokens: reactive[int] = reactive(0)
    output_tokens: reactive[int] = reactive(0)
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
        "N": VERDIGRIS,
        "A": OCHRE,
        "P": INDIGO,
        "S": WISTERIA,
    }

    def _activity_color(self) -> str:
        label = self.activity.lower()
        if any(term in label for term in ("error", "fail", "rate", "cancel")):
            return BENGARA
        if "think" in label:
            return WISTERIA
        if "tool" in label or "agent" in label:
            return OCHRE
        if any(term in label for term in ("wait", "start", "queue", "connect")):
            return INDIGO
        return VERDIGRIS

    @staticmethod
    def _clip(text: str, limit: int = 16) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    @staticmethod
    def _fmt_tokens(value: int) -> str:
        if value < 1000:
            return str(value)
        if value < 10000:
            return f"{value / 1000:.1f}k"
        return f"{value // 1000}k"

    def render(self) -> Text:
        """Render the status bar as a single Rich Text line."""
        mode_color = self.MODE_COLORS.get(self.mode, "white")
        activity_color = self._activity_color()

        if self.context_pct > 80:
            ctx_color = BENGARA
        elif self.context_pct > 60:
            ctx_color = OCHRE
        else:
            ctx_color = VERDIGRIS

        running_indicator = "\u27f3 " if self.is_running else "\u25cf "
        display_name = self.session_name or "dgc"
        tool_suffix = ""
        if self.last_tool:
            tool_suffix = f" {self._clip(self.last_tool, 12)}"

        parts = [
            f" [{mode_color}][{self.mode}][/{mode_color}]",
            f"  {running_indicator}{display_name}",
            f"  |  [{OCHRE}]{self.model}[/{OCHRE}]",
            f"  |  [{activity_color}]act:{self._clip(self.activity, 18)}[/{activity_color}]",
            f"  |  tools:{self.tool_count}{tool_suffix}",
            f"  |  io:{self._fmt_tokens(self.input_tokens)}/{self._fmt_tokens(self.output_tokens)}",
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
        self.activity = "ready"
        self.tool_count = 0
        self.last_tool = ""
        self.input_tokens = 0
        self.output_tokens = 0

    def update_from_result(
        self,
        *,
        cost_usd: float = 0.0,
        num_turns: int = 0,
    ) -> None:
        """Bulk-update from a ResultMessage event."""
        self.cost_usd = cost_usd
        self.turn_count = num_turns
        self.activity = "complete"
        self.is_running = False

    def increment_turn(self) -> None:
        """Increment the turn counter by one."""
        self.turn_count += 1
