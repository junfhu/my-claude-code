"""
Unicode figure / glyph constants used in the terminal UI.
"""

from __future__ import annotations

import sys

__all__ = [
    "BLACK_CIRCLE",
    "BULLET_OPERATOR",
    "TEARDROP_ASTERISK",
    "UP_ARROW",
    "DOWN_ARROW",
    "LIGHTNING_BOLT",
    "EFFORT_LOW",
    "EFFORT_MEDIUM",
    "EFFORT_HIGH",
    "EFFORT_MAX",
    "PLAY_ICON",
    "PAUSE_ICON",
    "REFRESH_ARROW",
    "CHANNEL_ARROW",
    "INJECTED_ARROW",
    "FORK_GLYPH",
    "DIAMOND_OPEN",
    "DIAMOND_FILLED",
    "REFERENCE_MARK",
    "FLAG_ICON",
    "BLOCKQUOTE_BAR",
    "HEAVY_HORIZONTAL",
    "BRIDGE_SPINNER_FRAMES",
    "BRIDGE_READY_INDICATOR",
    "BRIDGE_FAILED_INDICATOR",
]

# The former is better vertically aligned, but isn't usually supported on Windows/Linux
BLACK_CIRCLE: str = "\u23fa" if sys.platform == "darwin" else "\u25cf"  # ⏺ vs ●
BULLET_OPERATOR: str = "\u2219"  # ∙
TEARDROP_ASTERISK: str = "\u273b"  # ✻

UP_ARROW: str = "\u2191"  # ↑ — used for opus 1m merge notice
DOWN_ARROW: str = "\u2193"  # ↓ — used for scroll hint
LIGHTNING_BOLT: str = "\u21af"  # ↯ — used for fast mode indicator

# Effort level indicators
EFFORT_LOW: str = "\u25cb"  # ○
EFFORT_MEDIUM: str = "\u25d0"  # ◐
EFFORT_HIGH: str = "\u25cf"  # ●
EFFORT_MAX: str = "\u25c9"  # ◉ — effort level: max (Opus 4.6 only)

# Media/trigger status indicators
PLAY_ICON: str = "\u25b6"  # ▶
PAUSE_ICON: str = "\u23f8"  # ⏸

# MCP subscription indicators
REFRESH_ARROW: str = "\u21bb"  # ↻ — resource update indicator
CHANNEL_ARROW: str = "\u2190"  # ← — inbound channel message indicator
INJECTED_ARROW: str = "\u2192"  # → — cross-session injected message indicator
FORK_GLYPH: str = "\u2442"  # ⑂ — fork directive indicator

# Review status indicators (ultrareview diamond states)
DIAMOND_OPEN: str = "\u25c7"  # ◇ — running
DIAMOND_FILLED: str = "\u25c6"  # ◆ — completed/failed
REFERENCE_MARK: str = "\u203b"  # ※ — komejirushi, away-summary recap marker

# Issue flag indicator
FLAG_ICON: str = "\u2691"  # ⚑ — used for issue flag banner

# Blockquote indicator
BLOCKQUOTE_BAR: str = "\u258e"  # ▎ — left one-quarter block
HEAVY_HORIZONTAL: str = "\u2501"  # ━ — heavy box-drawing horizontal

# Bridge status indicators
BRIDGE_SPINNER_FRAMES: tuple[str, ...] = (
    "\u00b7|\u00b7",
    "\u00b7/\u00b7",
    "\u00b7\u2014\u00b7",
    "\u00b7\\\u00b7",
)
BRIDGE_READY_INDICATOR: str = "\u00b7\u2714\ufe0e\u00b7"
BRIDGE_FAILED_INDICATOR: str = "\u00d7"
