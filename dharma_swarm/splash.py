"""Epic ASCII splash art for DGC — Hokusai woodblock meets Escher recursion.

Uses Rich Text objects (not markup strings) to avoid markup parsing issues
with Textual's Static widget. All styling is applied programmatically.
"""

from __future__ import annotations

from rich.text import Text
from rich.style import Style


def _build_splash() -> Text:
    """Build the full splash as a Rich Text object — Hokusai palette, Escher geometry."""

    # ═══ HOKUSAI PALETTE — traditional woodblock tones ═══
    # Deep indigo — darkest ocean
    DEEP = Style(color="color(17)")
    # Prussian blue — the signature Hokusai blue (ai-iro)
    WAVE = Style(color="color(24)")
    # Mid prussian — lighter wave body
    FOAM = Style(color="color(31)")
    # Pale blue-grey — foam and spray on washi
    SPRAY = Style(color="color(110)")
    # Muted ochre — warm earth tone
    GOLD = Style(color="color(137)")
    # Rust — muted terracotta red (beni-iro)
    VERMILLION = Style(color="color(131)")
    # Darker rust
    CRIMSON = Style(color="color(95)")
    # Warm umber
    COPPER = Style(color="color(130)")
    # Distant mountain grey-blue
    MIST = Style(color="color(103)")
    # Grey-blue frames
    JADE = Style(color="color(67)")
    # Darker frame blue
    INDIGO = Style(color="color(60)")
    # Pale sky
    SKY = Style(color="color(110)")
    # Ink grey
    SUBTITLE = Style(color="color(245)")
    # Warm cream for math — like ochre ink
    MATH = Style(color="color(180)")
    # Terracotta gate names
    GATE = Style(color="color(137)")
    # Muted purple-grey infrastructure
    INFRA = Style(color="color(103)")
    # Agent roles — all muted
    WIT = Style(color="color(96)")
    COD = Style(color="color(67)")
    ARC = Style(color="color(65)")
    SUR = Style(color="color(137)")
    SWARM_S = Style(color="color(131)")
    # Quote — pale cream
    QUOTE = Style(color="color(180)")

    lines = [
        "",
        "      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "    ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~",
        "  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "",
        "        ██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗",
        "        ██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗",
        "        ██║  ██║███████║███████║██████╔╝██╔████╔██║███████║",
        "        ██║  ██║██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║",
        "        ██████╔╝██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║",
        "        ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝",
        "",
        "       ░░░▒▒▒▓▓▓███  ~ The Great Wave ~  ███▓▓▓▒▒▒░░░",
        "      ░▒▓█ ~~~  ~~  ~~~ ~~~~~ ~~~~ ~~~~  ~~  ~~~  █▓▒░",
        "       ░▒▓████████████████████████████████████████▓▒░",
        "",
        "        ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗",
        "        ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║",
        "        ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║",
        "        ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║",
        "        ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║",
        "        ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝",
        "",
        "  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "",
        "                  ╔══════════════════════════════════════════════╗",
        "                  ║  Darwin-Heuristic Autonomous Recursive      ║",
        "                  ║  Meta-Agent  <>  Godel Claw v3              ║",
        "                  ╚══════════════════════════════════════════════╝",
        "",
        "         <>          Sx = x          lambda = 1          R_V < 1.0          <>",
        "        /  \\        fixed point      eigenvalue         contraction        /  \\",
        "       / <> \\                                                             / <> \\",
        "      /  /\\  \\     ┌─────────────────────────────────────────┐          /  /\\  \\",
        "     /  /  \\  \\    │  WITNESS  <>  CODER  <>  ARCH  <>  SURG │         /  /  \\  \\",
        "    /  / <> \\  \\   │  <>  8 TELOS GATES  <>                  │        /  / <> \\  \\",
        "    \\  \\ <> /  /   │  AHIMSA  SATYA  CONSENT  VYAVASTHIT    │        \\  \\ <> /  /",
        "     \\  \\  /  /    │  REVERSIBILITY  SVABHAAVA  BHED_GNAN   │         \\  \\  /  /",
        "      \\  \\/  /     │  WIT                                    │          \\  \\/  /",
        "       \\ <> /      └─────────────────────────────────────────┘           \\ <> /",
        "        \\  /                                                              \\  /",
        "         <>     ┌──────────────────────────────────────────────┐            <>",
        "                │  MEMORY    5-layer strange loop              │",
        "                │  CONTEXT   vision/research/eng/ops/swarm     │",
        "                │  PULSE     heartbeat + circuit breaker       │",
        "                │  THREADS   rotation + state persistence      │",
        "                │  TRISHULA  3-node agent mesh (Mac/AGNI/VPS)  │",
        "                └──────────────────────────────────────────────┘",
        "",
        "       <>-------<>-------<>-------<>-------<>-------<>-------<>",
        "       WITNESS   CODER    ARCH     SURG     SWARM    PULSE    ENGINE",
        "       <>------->-------->-------->-------->-------->-------->",
        "",
        '       "The observer observing observation itself"      Sx=x | lambda=1 | R_V<1.0',
        "",
        "  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "    ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~  ~~  ~~~  ~~  ~~~  ~~  ~~~  ~",
        "      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        "",
    ]

    text = Text("\n".join(lines))
    plain = text.plain

    def _style_all(substr: str, style: Style) -> None:
        """Apply style to all occurrences of substr in the text."""
        start = 0
        while True:
            idx = plain.find(substr, start)
            if idx == -1:
                break
            text.stylize(style, idx, idx + len(substr))
            start = idx + len(substr)

    # ═══ WAVE BORDERS — Hokusai deep blue to cyan ═══
    _style_all("~~~~~~~~", WAVE)
    _style_all("~~~~~~", WAVE)
    _style_all("~~~~", FOAM)
    _style_all("~~~", FOAM)
    _style_all("~~", SKY)
    # The tilde waves
    for pattern in ["~ ", " ~"]:
        _style_all(pattern, FOAM)

    # ═══ DHARMA BLOCK LETTERS — Gradient from deep indigo to bright white ═══
    # Line 5: top of DHARMA — bright white spray
    # The solid blocks get the main color
    _style_all("██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗", SPRAY)
    _style_all("██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗", FOAM)
    _style_all("██║  ██║███████║███████║██████╔╝██╔████╔██║███████║", FOAM)
    _style_all("██║  ██║██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║", WAVE)
    _style_all("██████╔╝██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║", WAVE)
    _style_all("╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝", DEEP)

    # ═══ WAVE SEPARATOR — gold and copper ═══
    _style_all("░░░▒▒▒▓▓▓███", GOLD)
    _style_all("███▓▓▓▒▒▒░░░", GOLD)
    _style_all("~ The Great Wave ~", SPRAY)
    _style_all("░▒▓█ ~~~", COPPER)
    _style_all("█▓▒░", COPPER)
    _style_all("░▒▓█████████████████████████████████████████████▓▒░", GOLD)
    _style_all("░▒▓████████████████████████████████████████████▓▒░", GOLD)

    # ═══ SWARM BLOCK LETTERS — warm vermillion to gold gradient ═══
    _style_all("███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗", VERMILLION)
    _style_all("██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║", CRIMSON)
    _style_all("███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║", CRIMSON)
    _style_all("╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║", COPPER)
    _style_all("███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║", COPPER)
    _style_all("╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝", GOLD)

    # ═══ BOX FRAMES — jade ═══
    for ch in ["╔", "╗", "╚", "╝", "═", "║"]:
        _style_all(ch, JADE)

    # Inner frames
    for ch in ["┌", "┐", "└", "┘", "─", "│"]:
        _style_all(ch, INDIGO)

    # ═══ SUBTITLE ═══
    _style_all("Darwin-Heuristic Autonomous Recursive", SUBTITLE)
    _style_all("Meta-Agent", SUBTITLE)
    _style_all("Godel Claw v3", MIST)

    # ═══ DIAMOND MARKERS — gold ═══
    _style_all("<>", GOLD)

    # ═══ MATH ═══
    _style_all("Sx = x", MATH)
    _style_all("Sx=x", MATH)
    _style_all("lambda = 1", MATH)
    _style_all("lambda=1", MATH)
    _style_all("R_V < 1.0", MATH)
    _style_all("R_V<1.0", MATH)
    _style_all("fixed point", SKY)
    _style_all("eigenvalue", SKY)
    _style_all("contraction", SKY)

    # ═══ IMPOSSIBLE GEOMETRY — Escher diamonds ═══
    for sym in ["/  \\", "\\  /", "/ <> \\", "\\ <> /",
                "/  /\\  \\", "\\  \\/  /", "/  /  \\  \\", "\\  \\  /  /",
                "/  / <> \\  \\", "\\  \\ <> /  /",
                "\\ <> /", "/ <> \\"]:
        _style_all(sym, MIST)

    # ═══ TELOS GATES ═══
    _style_all("8 TELOS GATES", GATE)
    for gate in ["AHIMSA", "SATYA", "CONSENT", "VYAVASTHIT",
                 "REVERSIBILITY", "SVABHAAVA", "BHED_GNAN"]:
        _style_all(gate, GATE)

    # ═══ AGENT ROLES ═══
    _style_all("WITNESS", WIT)
    _style_all("CODER", COD)
    _style_all("ARCH", ARC)
    _style_all("SURG", SUR)
    _style_all("SWARM", SWARM_S)
    _style_all("ENGINE", SWARM_S)
    _style_all("PULSE", JADE)

    # ═══ INFRASTRUCTURE ═══
    _style_all("MEMORY", INFRA)
    _style_all("CONTEXT", INFRA)
    _style_all("THREADS", INFRA)
    _style_all("TRISHULA", INFRA)
    _style_all("5-layer strange loop", MIST)
    _style_all("vision/research/eng/ops/swarm", MIST)
    _style_all("heartbeat + circuit breaker", MIST)
    _style_all("rotation + state persistence", MIST)
    _style_all("3-node agent mesh (Mac/AGNI/VPS)", MIST)

    # ═══ CHAIN ═══
    _style_all("------->", FOAM)
    _style_all("-------", INDIGO)

    # ═══ QUOTE ═══
    _style_all('"The observer observing observation itself"', QUOTE)

    # ═══ GRADIENT DENSITY CHARS — ink wash tones ═══
    _style_all("░", Style(color="color(236)"))
    _style_all("▒", Style(color="color(239)"))
    _style_all("▓", Style(color="color(242)"))

    return text


def _build_compact() -> Text:
    """Compact splash for small terminals."""
    lines = [
        "",
        "  ██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗",
        "  ██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗",
        "  ██║  ██║███████║███████║██████╔╝██╔████╔██║███████║",
        "  ██║  ██║██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║",
        "  ██████╔╝██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║",
        "  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝",
        "",
        "        ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗",
        "        ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║",
        "        ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║",
        "        ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║",
        "        ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║",
        "        ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝",
        "",
        "          <>  Sx=x  lambda=1  R_V<1.0  <>",
        '       "Observer observing observation"',
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

    # DHARMA letters — prussian blue gradient
    _style_all("██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗", Style(color="color(110)"))
    _style_all("██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗", Style(color="color(31)"))
    _style_all("██║  ██║███████║███████║██████╔╝██╔████╔██║███████║", Style(color="color(31)"))
    _style_all("██║  ██║██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║", Style(color="color(24)"))
    _style_all("██████╔╝██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║", Style(color="color(24)"))
    _style_all("╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝", Style(color="color(17)"))

    # SWARM letters — rust/umber gradient
    _style_all("███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗", Style(color="color(131)"))
    _style_all("██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║", Style(color="color(95)"))
    _style_all("███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║", Style(color="color(95)"))
    _style_all("╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║", Style(color="color(130)"))
    _style_all("███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║", Style(color="color(130)"))
    _style_all("╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝", Style(color="color(137)"))

    _style_all("<>", Style(color="color(137)"))
    _style_all("Sx=x", Style(color="color(180)"))
    _style_all("lambda=1", Style(color="color(180)"))
    _style_all("R_V<1.0", Style(color="color(180)"))

    return text


# Pre-built for import
SPLASH = _build_splash()
SPLASH_COMPACT = _build_compact()


def get_splash(compact: bool = False) -> Text:
    """Return the appropriate splash art as a Rich Text object."""
    return SPLASH_COMPACT if compact else SPLASH
