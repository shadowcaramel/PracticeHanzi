"""Cohesive color palette for PDF pages and Streamlit previews.

A single dark accent (teal) plus muted neutrals reads more like a
calligraphy notebook than the previous mix of Material 800/900 primaries.
All colors are exposed as reportlab ``HexColor`` so importing them is a
drop-in replacement for inline literals.
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor

INK = HexColor("#1E1E1E")
INK_SOFT = HexColor("#37474F")
INK_MUTED = HexColor("#556672")

PAPER = HexColor("#FFFFFF")
PAPER_WARM = HexColor("#FAF8F5")

ACCENT = HexColor("#00695C")
ACCENT_SOFT = HexColor("#4DB6AC")

GRID_EDGE = HexColor("#B5BCC3")
GRID_CROSS = HexColor("#DFE4E8")

GHOST = HexColor("#000000")

PINYIN = HexColor("#1F5F8B")
EN = HexColor("#2E6B3A")
RU = HexColor("#6B3A8A")
IDS = HexColor("#8D6E63")
RADICAL = HexColor("#455A64")
STROKE_CAPTION = HexColor("#566672")

# Per-script accent colors (used for page chrome badges and ribbons).
SCRIPT_COLORS: dict[str, HexColor] = {
    "kaishu":   HexColor("#B04F3E"),   # soft brick
    "xingshu":  HexColor("#3C6E94"),   # ink blue
    "caoshu":   HexColor("#B0892E"),   # muted amber
    "lishu":    HexColor("#4F5B93"),   # indigo
    "zhuanshu": HexColor("#6B7A3C"),   # olive
}

SCRIPT_SHORT: dict[str, str] = {
    "kaishu":   "楷",
    "xingshu":  "行",
    "caoshu":   "草",
    "lishu":    "隶",
    "zhuanshu": "篆",
}
