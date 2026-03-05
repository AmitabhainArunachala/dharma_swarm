"""DGC warm dark theme — amber/gold palette on deep warm black.

Built for Textual 8.x Theme API. Register with ``app.register_theme(DharmaDarkTheme)``
and activate with ``app.theme = "dharma-dark"``.
"""

from __future__ import annotations

from textual.theme import Theme

DharmaDarkTheme = Theme(
    name="dharma-dark",
    primary="#D4A017",
    secondary="#8A6A1A",
    accent="#D4A017",
    warning="#E06020",
    error="#E05050",
    success="#4CAF72",
    surface="#252018",
    panel="#1c1810",
    dark=True,
    variables={
        "bg-base": "#111008",
        "bg-elevated": "#1c1810",
        "bg-surface": "#252018",
        "bg-overlay": "#2e2820",
        "text-primary": "#f0e8d8",
        "text-secondary": "#a89880",
        "text-disabled": "#5a5040",
        "accent-bright": "#D4A017",
        "accent-dim": "#8A6A1A",
        "accent-subtle": "#4A3B18",
        "thinking": "#7B68EE",
        "info": "#5090D8",
    },
)
