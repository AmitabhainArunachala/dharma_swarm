"""DGC TUI splash art — classic box art with thinkodynamic elements.

Uses Rich Text objects (not markup strings) for Textual Static widget compatibility.
All styling is applied programmatically via Rich Text.stylize().
"""

from __future__ import annotations

from rich.text import Text
from rich.style import Style


def _build_splash() -> Text:
    """Build the full DGC TUI splash — box art identity + thinkodynamic math."""

    # Color palette
    CYAN = Style(color="bright_cyan", bold=True)
    DIM_CYAN = Style(color="cyan")
    GOLD = Style(color="color(137)")
    MATH = Style(color="color(180)")
    MIST = Style(color="color(103)")
    GATE = Style(color="color(137)")
    INFRA = Style(color="color(103)")
    QUOTE = Style(color="color(180)")
    JADE = Style(color="color(67)")
    SUBTITLE = Style(color="color(245)")
    TELOS = Style(color="color(137)", bold=True)

    lines = [
        "",
        "  ╔═══════════════════════════════════════════════════════════════════╗",
        "  ║                                                                   ║",
        "  ║      ██████╗  ██████╗  ██████╗    ████████╗██╗   ██╗██╗          ║",
        "  ║      ██╔══██╗██╔════╝ ██╔════╝    ╚══██╔══╝██║   ██║██║          ║",
        "  ║      ██║  ██║██║  ███╗██║            ██║   ██║   ██║██║          ║",
        "  ║      ██║  ██║██║   ██║██║            ██║   ██║   ██║██║          ║",
        "  ║      ██████╔╝╚██████╔╝╚██████╗       ██║   ╚██████╔╝██║          ║",
        "  ║      ╚═════╝  ╚═════╝  ╚═════╝       ╚═╝    ╚═════╝ ╚═╝          ║",
        "  ║                                                                   ║",
        "  ║           Dharmic Godel Claw - Terminal Interface                 ║",
        "  ║                      Telos: Moksha                                ║",
        "  ║                                                                   ║",
        "  ╠═══════════════════════════════════════════════════════════════════╣",
        "  ║                                                                   ║",
        "  ║     <>  Sx = x    lambda = 1    R_V < 1.0    Swabhaav = L4  <>   ║",
        "  ║                                                                   ║",
        "  ║   ┌───────────────────────────────────────────────────────────┐   ║",
        "  ║   │  8 TELOS GATES: AHIMSA SATYA CONSENT VYAVASTHIT        │   ║",
        "  ║   │    REVERSIBILITY SVABHAAVA BHED_GNAN WITNESS            │   ║",
        "  ║   │  DARWIN ENGINE  <>  5-LAYER MEMORY  <>  CONTEXT         │   ║",
        "  ║   │  WITNESS  CODER  ARCHITECT  SURGEON  SWARM  OPENCLAW   │   ║",
        "  ║   │  TRISHULA  AGNI  PULSE  ECOSYSTEM                      │   ║",
        "  ║   └───────────────────────────────────────────────────────────┘   ║",
        "  ║                                                                   ║",
        "  ║      \"The observer observing observation itself\"                  ║",
        "  ║                                                                   ║",
        "  ╚═══════════════════════════════════════════════════════════════════╝",
        "",
    ]

    text = Text("\n".join(lines))
    plain = text.plain

    def _style_all(substr: str, style: Style) -> None:
        start = 0
        while True:
            idx = plain.find(substr, start)
            if idx == -1:
                break
            text.stylize(style, idx, idx + len(substr))
            start = idx + len(substr)

    # Outer box frame — bright cyan
    for ch in ["╔", "╗", "╚", "╝", "═", "║", "╠", "╣"]:
        _style_all(ch, CYAN)

    # Inner box frame — jade
    for ch in ["┌", "┐", "└", "┘", "─", "│"]:
        _style_all(ch, JADE)

    # Block letters — DGC TUI in cyan gradient (bright top, dim bottom)
    _style_all("██████╗  ██████╗  ██████╗    ████████╗██╗   ██╗██╗", CYAN)
    _style_all("██╔══██╗██╔════╝ ██╔════╝    ╚══██╔══╝██║   ██║██║", CYAN)
    _style_all("██║  ██║██║  ███╗██║            ██║   ██║   ██║██║", DIM_CYAN)
    _style_all("██║  ██║██║   ██║██║            ██║   ██║   ██║██║", DIM_CYAN)
    _style_all("██████╔╝╚██████╔╝╚██████╗       ██║   ╚██████╔╝██║", DIM_CYAN)
    _style_all("╚═════╝  ╚═════╝  ╚═════╝       ╚═╝    ╚═════╝ ╚═╝", MIST)

    # Subtitle
    _style_all("Dharmic Godel Claw - Terminal Interface", SUBTITLE)
    _style_all("Telos: Moksha", TELOS)

    # Diamond markers
    _style_all("<>", GOLD)

    # Math notations
    _style_all("Sx = x", MATH)
    _style_all("lambda = 1", MATH)
    _style_all("R_V < 1.0", MATH)
    _style_all("Swabhaav = L4", MATH)

    # Telos gate names
    _style_all("8 TELOS GATES:", GATE)
    for gate in ["AHIMSA", "SATYA", "CONSENT", "VYAVASTHIT",
                 "REVERSIBILITY", "SVABHAAVA", "BHED_GNAN"]:
        _style_all(gate, GATE)

    # Infrastructure labels in inner box
    _style_all("DARWIN ENGINE", GATE)
    _style_all("5-LAYER MEMORY", GATE)
    _style_all("CONTEXT", INFRA)
    for label in ["WITNESS", "CODER", "ARCHITECT", "SURGEON", "SWARM",
                   "TRISHULA", "AGNI", "PULSE", "ECOSYSTEM", "OPENCLAW"]:
        _style_all(label, INFRA)

    # Quote
    _style_all('"The observer observing observation itself"', QUOTE)

    return text


def _build_compact() -> Text:
    """Compact splash for small terminals."""
    lines = [
        "",
        "  ██████╗  ██████╗  ██████╗    ████████╗██╗   ██╗██╗",
        "  ██╔══██╗██╔════╝ ██╔════╝    ╚══██╔══╝██║   ██║██║",
        "  ██║  ██║██║  ███╗██║            ██║   ██║   ██║██║",
        "  ██║  ██║██║   ██║██║            ██║   ██║   ██║██║",
        "  ██████╔╝╚██████╔╝╚██████╗       ██║   ╚██████╔╝██║",
        "  ╚═════╝  ╚═════╝  ╚═════╝       ╚═╝    ╚═════╝ ╚═╝",
        "",
        "     Dharmic Godel Claw  <>  Telos: Moksha",
        "     Sx=x  lambda=1  R_V<1.0  Swabhaav=L4",
        "",
    ]
    text = Text("\n".join(lines))
    plain = text.plain

    def _style_all(substr: str, style: Style) -> None:
        start = 0
        while True:
            idx = plain.find(substr, start)
            if idx == -1:
                break
            text.stylize(style, idx, idx + len(substr))
            start = idx + len(substr)

    CYAN = Style(color="bright_cyan", bold=True)
    DIM_CYAN = Style(color="cyan")
    GOLD = Style(color="color(137)")
    MATH = Style(color="color(180)")
    MIST = Style(color="color(103)")
    SUBTITLE = Style(color="color(245)")

    # Block letters
    _style_all("██████╗  ██████╗  ██████╗    ████████╗██╗   ██╗██╗", CYAN)
    _style_all("██╔══██╗██╔════╝ ██╔════╝    ╚══██╔══╝██║   ██║██║", CYAN)
    _style_all("██║  ██║██║  ███╗██║            ██║   ██║   ██║██║", DIM_CYAN)
    _style_all("██║  ██║██║   ██║██║            ██║   ██║   ██║██║", DIM_CYAN)
    _style_all("██████╔╝╚██████╔╝╚██████╗       ██║   ╚██████╔╝██║", DIM_CYAN)
    _style_all("╚═════╝  ╚═════╝  ╚═════╝       ╚═╝    ╚═════╝ ╚═╝", MIST)

    _style_all("Dharmic Godel Claw", SUBTITLE)
    _style_all("Telos: Moksha", GOLD)
    _style_all("<>", GOLD)
    for m in ["Sx=x", "lambda=1", "R_V<1.0", "Swabhaav=L4"]:
        _style_all(m, MATH)

    return text


# Pre-built for import
SPLASH = _build_splash()
SPLASH_COMPACT = _build_compact()


def get_splash(compact: bool = False) -> Text:
    """Return the appropriate splash art as a Rich Text object."""
    return SPLASH_COMPACT if compact else SPLASH
