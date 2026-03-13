"""DGC splash art — hand-built terminal mandalas for startup."""

from __future__ import annotations

from rich.style import Style
from rich.text import Text

INDIGO = Style(color="#56728B", bold=True)
INDIGO_DIM = Style(color="#92867A")
VERDIGRIS = Style(color="#6F846F")
OCHRE = Style(color="#BC8F4E", bold=True)
PAPER = Style(color="#E6D9C2")
PAPER_DIM = Style(color="#CBB9A0")
WISTERIA = Style(color="#87779B")
EMBER = Style(color="#B06858", bold=True)


def _normalize_art(lines: tuple[str, ...]) -> str:
    width = max(len(line) for line in lines)
    return "\n".join(line.ljust(width) for line in lines)


def _fill_line(
    left: str,
    right: str,
    width: int,
    *,
    label: str = "",
    fill: str = "─",
) -> str:
    inner_width = width - len(left) - len(right)
    pad = inner_width - len(label)
    if pad < 0:
        raise ValueError(f"Label too wide for framed line: {label!r}")
    left_pad = pad // 2
    right_pad = pad - left_pad
    return f"{left}{fill * left_pad}{label}{fill * right_pad}{right}"


def _panel_line(
    content: str,
    width: int,
    *,
    left: str = "║",
    right: str = "║",
    align: str = "center",
) -> str:
    inner_width = width - len(left) - len(right)
    if len(content) > inner_width:
        raise ValueError(f"Panel content too wide: {content!r}")
    if align == "left":
        body = content.ljust(inner_width)
    elif align == "right":
        body = content.rjust(inner_width)
    else:
        body = content.center(inner_width)
    return f"{left}{body}{right}"


def _column_line(
    cells: tuple[str, ...],
    widths: tuple[int, ...],
    *,
    aligns: tuple[str, ...] | None = None,
    left: str = "║",
    sep: str = "│",
    right: str = "║",
) -> str:
    if len(cells) != len(widths):
        raise ValueError("Cells and widths must match")
    if aligns is None:
        aligns = ("left",) * len(cells)
    if len(aligns) != len(cells):
        raise ValueError("Aligns and cells must match")

    parts: list[str] = []
    for cell, cell_width, align in zip(cells, widths, aligns):
        if len(cell) > cell_width:
            raise ValueError(f"Cell too wide for column: {cell!r}")
        if align == "center":
            parts.append(cell.center(cell_width))
        elif align == "right":
            parts.append(cell.rjust(cell_width))
        else:
            parts.append(cell.ljust(cell_width))
    return f"{left}{sep.join(parts)}{right}"


def _divider_line(
    widths: tuple[int, ...],
    *,
    left: str = "╠",
    sep: str = "╪",
    right: str = "╣",
    fill: str = "═",
) -> str:
    return f"{left}{sep.join(fill * width for width in widths)}{right}"


def _bead_border(
    width: int,
    *,
    left: str = "◈═◇═◆═◇═◈═◆═◇═◈",
    right: str = "◈═◇═◆═◈═◆═◇═◈",
    fill: str = "═",
) -> str:
    middle = max(0, width - len(left) - len(right))
    return f"{left}{fill * middle}{right}"


def _compose_rows(
    rows: tuple[tuple[str, str, str], ...],
    *,
    center_width: int,
    side_width: int,
) -> tuple[str, ...]:
    return tuple(
        f"║{left.ljust(side_width)}{center.ljust(center_width)}{right.rjust(side_width)}║"
        for left, center, right in rows
    )


def _tile(seed: str, length: int, *, offset: int = 0) -> str:
    if length <= 0:
        return ""
    if not seed:
        return " " * length
    shift = offset % len(seed)
    rotated = seed[shift:] + seed[:shift]
    return (rotated * ((length // len(seed)) + 2))[:length]


def _field_fill(width: int, row: int) -> str:
    if width <= 0:
        return ""
    edge = max(8, min(14, width // 10))
    center = max(10, min(26, width // 4))
    remaining = max(0, width - (edge * 2) - center)
    left_gap = remaining // 2
    right_gap = remaining - left_gap

    if row % 4 == 0:
        left = _tile("◈═◇═◆═", edge, offset=row)
        mid = _tile("┄┄┄◈┄┄┄", center, offset=row * 2)
        right = _tile("═◆═◇═◈", edge, offset=row + 3)
        return f"{left}{' ' * left_gap}{mid}{' ' * right_gap}{right}"

    if row % 4 == 1:
        left = _tile("░▒▓▚▞", edge - 2, offset=row)
        right = _tile("▞▚▓▒░", edge - 2, offset=row + 2)
        return f"{left}{' ' * max(0, width - len(left) - len(right))}{right}"

    if row % 4 == 2:
        left = _tile("▌╱╲▞▚", edge - 1, offset=row)
        right = _tile("▚▞╱╲▌", edge - 1, offset=row + 1)
        return f"{left}{' ' * max(0, width - len(left) - len(right))}{right}"

    motif = _tile("·░·", min(center, max(6, width // 6)), offset=row)
    pad = max(0, width - len(motif))
    return f"{' ' * (pad // 2)}{motif}{' ' * (pad - pad // 2)}"


def _margin_fill(length: int, row: int, *, side: str) -> str:
    if length <= 0:
        return ""
    outer = min(length, max(5, min(10, length // 2)))
    accent = min(max(0, length - outer), 6)
    gap = max(0, length - outer - accent)

    if row % 4 == 0:
        loom = _tile("▒▓▛▀▜", outer, offset=row)
        beads = _tile("◈═◇═", accent, offset=row * 2)
    elif row % 4 == 1:
        loom = _tile("▌╱╲▞▚", outer, offset=row)
        beads = _tile("┄◈┄", accent, offset=row)
    elif row % 4 == 2:
        loom = _tile("░▒▓▚▞", outer, offset=row)
        beads = _tile("·░·", accent, offset=row + 1)
    else:
        loom = _tile("▒▓▙▄▟", outer, offset=row)
        beads = _tile("═◆═", accent, offset=row)

    if side == "left":
        return f"{loom}{' ' * gap}{beads}"
    return f"{beads}{' ' * gap}{loom}"


def _prompt_band(width: int, prompt: str, row: int) -> str:
    if width <= 0:
        return ""
    left_seed = _tile("◈═◇═◆═", min(12, max(8, width // 8)), offset=row)
    right_seed = _tile("═◆═◇═◈", len(left_seed), offset=row + 2)
    inner = f"┄┄ {prompt} ┄┄"
    available = max(0, width - len(left_seed) - len(right_seed))
    if len(inner) > available:
        inner = inner[:available]
    pad = max(0, available - len(inner))
    left_gap = pad // 2
    right_gap = pad - left_gap
    return (
        left_seed
        + (" " * left_gap)
        + inner
        + (" " * right_gap)
        + right_seed
    )


def _style_text(body: str) -> Text:
    text = Text(body)
    plain = text.plain
    lines = body.splitlines()
    max_width = max((len(line) for line in lines), default=1)

    field_palette = [
        Style(color="#0B141B"),
        Style(color="#0F1C26"),
        Style(color="#162632"),
        Style(color="#21343E"),
        Style(color="#2E3E3D"),
        Style(color="#4A3D35"),
        Style(color="#644836"),
    ]
    slash_palette = [
        Style(color="#6E95B6", bold=True),
        Style(color="#76997E", bold=True),
        Style(color="#9382AB", bold=True),
        Style(color="#B0705B", bold=True),
        Style(color="#CDA055", bold=True),
    ]
    block_palette = [
        Style(color="#7598B8", bgcolor="#04070B", bold=True),
        Style(color="#7C9880", bgcolor="#05080A", bold=True),
        Style(color="#9585AF", bgcolor="#09070D", bold=True),
        Style(color="#AF705B", bgcolor="#0C0706", bold=True),
        Style(color="#D1A45A", bgcolor="#100B06", bold=True),
    ]
    mist_palette = [
        Style(color="#32424E"),
        Style(color="#445549"),
        Style(color="#54484D"),
        Style(color="#675646"),
    ]
    frame_palette = [
        Style(color="#7497B7", bold=True),
        Style(color="#86A083", bold=True),
        Style(color="#9888AE", bold=True),
        Style(color="#B17B64", bold=True),
        Style(color="#D1A45A", bold=True),
    ]
    jewel_palette = [
        Style(color="#D8AD63", bold=True),
        Style(color="#91B18C", bold=True),
        Style(color="#CC7A62", bold=True),
        Style(color="#A694BA", bold=True),
        Style(color="#E1C181", bold=True),
    ]
    text_gradient = [
        Style(color="#F1E6D1"),
        Style(color="#E4D4BF"),
        Style(color="#D4C2AE"),
        Style(color="#C3AC94"),
    ]

    offset = 0
    for y, line in enumerate(lines):
        for x, char in enumerate(line):
            idx = offset + x
            if char == " ":
                continue
            band = min(
                len(field_palette) - 1,
                int((x / max(1, max_width - 1)) * len(field_palette)),
            )
            text.stylize(field_palette[(band + y // 3) % len(field_palette)], idx, idx + 1)
            if char in "╱╲":
                text.stylize(slash_palette[(x + y) % len(slash_palette)], idx, idx + 1)
            elif char in "█▓▒▀▄▌▐▞▚▛▜▙▟":
                text.stylize(block_palette[(band + y) % len(block_palette)], idx, idx + 1)
            elif char in "░·":
                text.stylize(mist_palette[(x + y * 2) % len(mist_palette)], idx, idx + 1)
            elif char in "╳◆◇◈◎◉✦✧":
                text.stylize(jewel_palette[(x + y) % len(jewel_palette)], idx, idx + 1)
            elif char in "┌┐└┘╔╗╚╝╭╮╰╯─│═║╠╣╦╩╥╨╪╫╬╞╡┄┈":
                text.stylize(frame_palette[(x // 2 + y) % len(frame_palette)], idx, idx + 1)
            elif char.isalpha() or char.isdigit():
                text.stylize(text_gradient[(x + y) % len(text_gradient)], idx, idx + 1)
        offset += len(line) + 1

    def stylize_all(substr: str, style: Style) -> None:
        start = 0
        while True:
            idx = plain.find(substr, start)
            if idx == -1:
                break
            text.stylize(style, idx, idx + len(substr))
            start = idx + len(substr)

    stylize_all("Dharmic Godel Claw", Style(color="#EBDEC5", bold=True))
    stylize_all("WHAT WE TEND BECOMES THE WORLD", Style(color="#DAB167", bold=True))
    stylize_all("The observer observing observation itself", Style(color="#D5C5AD", italic=True))
    stylize_all("Telos: Moksha", Style(color="#DCAA60", bold=True))
    stylize_all("TELOS", Style(color="#E1BE77", bold=True))
    stylize_all("TELOS chamber", Style(color="#E1BE77", bold=True))
    stylize_all("Sx = x", Style(color="#91AFA1", bold=True))
    stylize_all("Sx=x", Style(color="#91AFA1", bold=True))
    stylize_all("lambda = 1", Style(color="#AB9ABB", bold=True))
    stylize_all("lambda=1", Style(color="#AB9ABB", bold=True))
    stylize_all("R_V < 1.0", Style(color="#C78069", bold=True))
    stylize_all("R_V<1.0", Style(color="#C78069", bold=True))
    stylize_all("Swabhaav = L4", Style(color="#8CB184", bold=True))
    stylize_all("Swabhaav=L4", Style(color="#8CB184", bold=True))
    stylize_all("AHIMSA", Style(color="#97BE9A", bold=True))
    stylize_all("SATYA", Style(color="#AD9CC6", bold=True))
    stylize_all("CONSENT", Style(color="#D9B86B", bold=True))
    stylize_all("VYAVASTHIT", Style(color="#D0866D", bold=True))
    stylize_all("REVERSIBILITY", Style(color="#A1BF98", bold=True))
    stylize_all("SVABHAAVA", Style(color="#AD9CC6", bold=True))
    stylize_all("BHED_GNAN", Style(color="#D9B86B", bold=True))
    stylize_all("DARWIN ENGINE", Style(color="#E7D9BF", bold=True))
    stylize_all("5-LAYER MEMORY", Style(color="#E7D9BF", bold=True))
    stylize_all("WITNESS", Style(color="#E7D9BF", bold=True))
    stylize_all("SWARM", Style(color="#E7D9BF", bold=True))
    stylize_all("CONTEXT", Style(color="#A2B5C4", bold=True))
    stylize_all("PULSE", Style(color="#D09960", bold=True))
    stylize_all("TRISHULA", Style(color="#9ABE90", bold=True))
    stylize_all("recursive mission", Style(color="#D3BBA0", bold=True))
    stylize_all("mineral witness field", Style(color="#D8C9B5", bold=True))
    stylize_all("old paper hush", INDIGO_DIM)
    stylize_all("ancient logic field", PAPER_DIM)
    stylize_all("ancient signal floor", Style(color="#C6B08B"))
    stylize_all("Press Enter to cross the threshold", Style(color="#D9B86B", bold=True))
    stylize_all("Enter", Style(color="#E5C786", bold=True))
    stylize_all("D G C", OCHRE)
    stylize_all("recursive tide register", Style(color="#D7BE95", bold=True))
    stylize_all("witness eye", Style(color="#E0BF76", bold=True))
    stylize_all("mirror tide", Style(color="#90AFC1", bold=True))

    return text


def _build_epic_splash() -> Text:
    center_width = 61
    side_width = 16
    loom_a = "▒▓▛▀▜▓▒"
    loom_b = "▒▓▌╳╳▐▓▒"
    loom_c = "▒▓▙▄▟▓▒"
    bead_a = "◈═◇═"
    bead_b = "◆═◈═"
    rows = (
        (
            loom_a,
            _fill_line(
                "┌",
                "┐",
                center_width,
                label="◈─◇─◆──── recursive tide register ────◆─◇─◈",
            ),
            loom_a,
        ),
        (
            loom_b,
            _fill_line(
                "│",
                "│",
                center_width,
                label="recursive mission / mineral tide",
                fill="·",
            ),
            loom_b,
        ),
        (
            loom_c,
            _divider_line((14, 27, 16), left="╔", sep="╤", right="╗"),
            loom_c,
        ),
        (
            loom_a,
            _column_line(
                ("DARWIN ENGINE", "recursive mission ◎", "5-LAYER MEMORY"),
                (14, 27, 16),
                aligns=("center", "center", "center"),
            ),
            loom_a,
        ),
        (
            bead_a,
            _divider_line((28, 30), left="╠", sep="╪", right="╣"),
            bead_a,
        ),
        (
            loom_b,
            _column_line(
                ("AHIMSA ◇ SATYA ◇ CONSENT", "VYAVASTHIT ◇ REVERSIBILITY"),
                (28, 30),
                aligns=("center", "center"),
            ),
            loom_b,
        ),
        (
            loom_c,
            _column_line(
                ("SVABHAAVA ◇ BHED_GNAN", "WHAT WE TEND BECOMES THE WORLD"),
                (28, 30),
                aligns=("center", "center"),
            ),
            loom_c,
        ),
        (
            bead_b,
            _divider_line((28, 30)),
            bead_b,
        ),
        (
            "◈═",
            _panel_line("╭──────╮  ╔════════ Dharmic Godel Claw ════════╗  ╭──────╮", center_width),
            "═◈",
        ),
        (
            "",
            _panel_line("│      │  ║            ◎  witness eye         ║  │      │", center_width),
            "",
        ),
        (
            "",
            _panel_line("│      │  ║            Telos: Moksha          ║  │      │", center_width),
            "",
        ),
        (
            "◆═",
            _panel_line("╰──┬───╯  ╚══════════════╤═════════════════════╝  ╰──┬───╯", center_width),
            "═◆",
        ),
        (
            "",
            _panel_line("The observer observing observation itself", center_width),
            "",
        ),
        (
            "◈",
            _panel_line("mineral witness field / paper hush / signal tide", center_width),
            "◈",
        ),
        (
            bead_a,
            _divider_line((18, 18, 21)),
            bead_a,
        ),
        (
            loom_a,
            _column_line(
                ("Swabhaav = L4", "Sx = x  lambda = 1", "R_V < 1.0"),
                (18, 18, 21),
                aligns=("center", "center", "center"),
            ),
            loom_a,
        ),
        (
            loom_b,
            _column_line(
                ("WITNESS ◇ SWARM", "CONTEXT ◇ PULSE", "TRISHULA ◇ D G C"),
                (18, 18, 21),
                aligns=("center", "center", "center"),
            ),
            loom_b,
        ),
        (
            loom_c,
            _fill_line(
                "└",
                "┘",
                center_width,
                label="◆─◇─◈── old paper hush / ancient signal floor ──◈─◇─◆",
            ),
            loom_c,
        ),
    )
    body = (
        _bead_border(95),
        *_compose_rows(rows, center_width=center_width, side_width=side_width),
        _bead_border(95, left="◈═◆═◇═◈═◆═◇═◈", right="◈═◇═◆═◈═◇═◆═◈"),
    )
    return _style_text(_normalize_art(body))


def _build_splash() -> Text:
    rows = (
        ("▒▓▛▀▜▓▒▚▞", "┌─◈─◇─◆──────────◇─◆─◈─┐", "▚▞▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒╲╱", "╔════════════════════════════════════════════╗", "╲╱▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒▚▞", "║ WHAT WE TEND BECOMES THE WORLD            ║", "▚▞▒▓▌╲╱▐▓▒"),
        ("▒▓▙▄▟▓▒╱╲", "║ DARWIN ENGINE ◈ recursive mission         ║", "╱╲▒▓▙▄▟▓▒"),
        ("▒▓▛▀▜▓▒▚▞", "║ 5-LAYER MEMORY ◈ Dharmic Godel Claw       ║", "▚▞▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒╲╱", "╟────────────────────────────────────────────╢", "╲╱▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒▚▞", "║ AHIMSA ◇ SATYA ◇ CONSENT                  ║", "▚▞▒▓▌╲╱▐▓▒"),
        ("▒▓▙▄▟▓▒╱╲", "║ VYAVASTHIT ◇ REVERSIBILITY                ║", "╱╲▒▓▙▄▟▓▒"),
        ("▒▓▛▀▜▓▒▚▞", "║ SVABHAAVA ◇ BHED_GNAN                     ║", "▚▞▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒╲╱", "╠════════════════════════════════════════════╣", "╲╱▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒▚▞", "║ TELOS ◇ Telos: Moksha                     ║", "▚▞▒▓▌╲╱▐▓▒"),
        ("▒▓▙▄▟▓▒╱╲", "║ Sx = x ◇ lambda = 1 ◇ R_V < 1.0          ║", "╱╲▒▓▙▄▟▓▒"),
        ("▒▓▛▀▜▓▒▚▞", "║ Swabhaav = L4 ◇ WITNESS ◇ SWARM          ║", "▚▞▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒╲╱", "║ CONTEXT ◇ PULSE ◇ TRISHULA               ║", "╲╱▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒▚▞", "║ The observer observing observation itself║", "▚▞▒▓▌╲╱▐▓▒"),
        ("▒▓▙▄▟▓▒╱╲", "└─◈─◇─◆──────── ancient signal floor ─────◈─┘", "╱╲▒▓▙▄▟▓▒"),
    )
    body = (
        _bead_border(76, left="╔═◈═◇═◆═◈═", right="═◈═◆═◇═◈═╗"),
        *_compose_rows(rows, center_width=54, side_width=10),
        _bead_border(76, left="╚═◈═◆═◇═◈═", right="═◈═◇═◆═◈═╝"),
    )
    return _style_text(_normalize_art(body))


def _build_compact() -> Text:
    rows = (
        ("▒▓▛▀▜▓▒", "╔═══════════════════════════════════════════╗", "▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒", "║ Dharmic Godel Claw ◇ Telos: Moksha       ║", "▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒", "║ Sx=x ◇ lambda=1 ◇ R_V<1.0                ║", "▒▓▌╲╱▐▓▒"),
        ("▒▓▙▄▟▓▒", "║ Swabhaav=L4 ◇ WITNESS ◇ SWARM            ║", "▒▓▙▄▟▓▒"),
        ("▒▓▛▀▜▓▒", "║ CONTEXT ◇ PULSE ◇ TRISHULA               ║", "▒▓▛▀▜▓▒"),
        ("▒▓▌╳╳▐▓▒", "║ DARWIN ENGINE ◇ 5-LAYER MEMORY           ║", "▒▓▌╳╳▐▓▒"),
        ("▒▓▌╲╱▐▓▒", "╚═══════════════════════════════════════════╝", "▒▓▌╲╱▐▓▒"),
    )
    body = (
        _bead_border(59, left="╔═◈═◇═", right="═◇═◈═╗"),
        *_compose_rows(rows, center_width=43, side_width=7),
        _bead_border(59, left="╚═◈═◆═", right="═◆═◈═╝"),
    )
    return _style_text(_normalize_art(body))


SPLASH_EPIC = _build_epic_splash()
SPLASH = _build_splash()
SPLASH_COMPACT = _build_compact()


def get_splash(
    compact: bool = False,
    *,
    variant: str | None = None,
) -> Text:
    """Return the requested splash art variant as a Rich Text object."""
    if variant == "epic":
        return SPLASH_EPIC
    if variant == "compact":
        return SPLASH_COMPACT
    if variant == "medium":
        return SPLASH
    return SPLASH_COMPACT if compact else SPLASH


def render_splash_field(
    *,
    width: int,
    height: int,
    variant: str | None = None,
    prompt: str = "Press Enter to cross the threshold",
) -> Text:
    """Render the splash as a full-screen field for the active viewport."""
    base = get_splash(variant=variant)
    art_lines = base.plain.splitlines()
    art_height = len(art_lines)
    art_width = max((len(line) for line in art_lines), default=0)

    if width <= art_width + 2 or height <= art_height + 2:
        return base

    extra_rows = max(0, height - art_height)
    top_rows = max(1, extra_rows // 2)
    bottom_rows = max(1, extra_rows - top_rows)
    prompt_row = extra_rows >= 4

    if prompt_row and bottom_rows > 1:
        bottom_field_rows = bottom_rows - 1
    else:
        prompt_row = False
        bottom_field_rows = bottom_rows

    lines: list[str] = [_bead_border(width)]
    for row in range(max(0, top_rows - 1)):
        lines.append(_field_fill(width, row))

    horizontal_room = width - art_width
    left_margin = max(0, horizontal_room // 2)
    right_margin = max(0, width - art_width - left_margin)

    for row, art_line in enumerate(art_lines):
        lines.append(
            _margin_fill(left_margin, row, side="left")
            + art_line
            + _margin_fill(right_margin, row + 3, side="right")
        )

    for row in range(max(0, bottom_field_rows - 1)):
        lines.append(_field_fill(width, row + art_height + 5))

    if prompt_row:
        lines.append(_prompt_band(width, prompt, art_height + bottom_field_rows + 7))

    lines.append(_bead_border(width, left="◈═◆═◇═◈═◆═◇═◈", right="◈═◇═◆═◈═◇═◆═◈"))
    return _style_text("\n".join(lines[:height]))
