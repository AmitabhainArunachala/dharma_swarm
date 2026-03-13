"""DGC Hokusai theme — mineral pigment palette inspired by ukiyo-e woodblocks
and Kyoto nihonga (日本画) pigment shops.

Colours drawn from traditional Japanese mineral pigments:
  - Ai-iro (藍色): deep indigo-blue, Hokusai's Prussian blue
  - Bengara (弁柄): earthy red-ochre from iron oxide
  - Rokusho (緑青): verdigris green, copper patina on temple roofs
  - Sumi (墨): ink-wash greys, the backbone of suiboku-ga
  - Torinoko (鳥の子): aged washi paper cream
  - Fuji (藤): wisteria purple, late spring Kyoto
  - Kitsurubami (黄橡): persimmon tan, autumn warmth
  - Wasurenagusa (勿忘草): pale forget-me-not blue
  - Shironeri (白練): undyed silk white, clean reading surface

Built for Textual 8.x Theme API. Register with ``app.register_theme(DharmaDarkTheme)``
and activate with ``app.theme = "dharma-dark"``.
"""

from __future__ import annotations

from textual.theme import Theme

DharmaDarkTheme = Theme(
    name="dharma-dark",
    primary="#46525B",
    secondary="#A17A47",
    accent="#62725D",
    warning="#A17A47",
    error="#8C5448",
    success="#62725D",
    surface="#121117",
    panel="#0F1014",         # Kuro-cha — blackened tea
    dark=True,
    variables={
        "bg-base": "#090A0F",        # Ro-iro — lacquer black
        "bg-elevated": "#121117",
        "bg-surface": "#18171C",
        "bg-overlay": "#201E24",
        "text-primary": "#DCCFBD",
        "text-secondary": "#A89A8B",
        "text-disabled": "#676062",  # Nibi-iro — dull grey-purple
        "accent-bright": "#6A7A62",
        "accent-dim": "#46525B",
        "accent-subtle": "#313B37",
        "thinking": "#74677D",
        "info": "#46525B",
    },
)
