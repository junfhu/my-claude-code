"""
Output style definitions using Rich styles and themes.

Provides a unified theming system for Claude Code's terminal output.
Themes are defined as Rich ``Theme`` objects and can be selected
via ``~/.claude/config.json`` or the ``/theme`` command.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from rich.style import Style
from rich.theme import Theme


# ---------------------------------------------------------------------------
# Named colour constants
# ---------------------------------------------------------------------------

class Colors:
    """Semantic colour constants used across the UI."""

    # Brand
    CLAUDE_BLUE = "#5B9BD5"
    CLAUDE_PURPLE = "#7B68EE"
    CLAUDE_ORANGE = "#E8914D"

    # Semantic
    SUCCESS = "#28A745"
    WARNING = "#FFC107"
    ERROR = "#DC3545"
    INFO = "#17A2B8"
    MUTED = "#6C757D"

    # UI chrome
    BORDER = "#3A3A3A"
    BORDER_FOCUS = "#5B9BD5"
    SURFACE = "#1E1E1E"
    SURFACE_LIGHT = "#2D2D2D"


# ---------------------------------------------------------------------------
# Style registry
# ---------------------------------------------------------------------------

# Core named styles used by all rendering code
STYLES: Dict[str, Style] = {
    # Messages
    "user.prefix": Style(color="green", bold=True),
    "user.text": Style(bold=True),
    "assistant.prefix": Style(color="blue", bold=True),
    "assistant.text": Style(),
    "system.prefix": Style(dim=True),
    "system.text": Style(dim=True),
    "error.prefix": Style(color="red", bold=True),
    "error.text": Style(color="red"),

    # Tool rendering
    "tool.name": Style(color="yellow", bold=True),
    "tool.icon": Style(color="yellow"),
    "tool.input_key": Style(dim=True),
    "tool.input_value": Style(),
    "tool.success": Style(color="green"),
    "tool.failure": Style(color="red"),
    "tool.output": Style(),

    # Diff
    "diff.add": Style(color="green", bold=True),
    "diff.remove": Style(color="red", bold=True, strike=True),
    "diff.context": Style(dim=True),
    "diff.header": Style(color="cyan", bold=True),

    # Status bar
    "statusbar.model": Style(color="white", bold=True, bgcolor="dark_blue"),
    "statusbar.permission.default": Style(color="white", bgcolor="dark_green"),
    "statusbar.permission.plan": Style(color="white", bgcolor="dark_blue"),
    "statusbar.permission.auto_edit": Style(color="white", bgcolor="dark_magenta"),
    "statusbar.permission.full_auto": Style(color="white", bold=True, bgcolor="dark_red"),
    "statusbar.tokens": Style(color="cyan"),
    "statusbar.cost": Style(color="green"),
    "statusbar.branch": Style(color="magenta"),
    "statusbar.vim": Style(color="black", bold=True, bgcolor="yellow"),

    # Permission prompt
    "perm.risk.low": Style(color="green"),
    "perm.risk.medium": Style(color="yellow"),
    "perm.risk.high": Style(color="red", bold=True),
    "perm.header": Style(color="yellow", bold=True),

    # Sidebar
    "sidebar.title": Style(bold=True, underline=True),
    "sidebar.todo.pending": Style(color="white"),
    "sidebar.todo.in_progress": Style(color="yellow"),
    "sidebar.todo.completed": Style(color="green", dim=True, strike=True),

    # Spinner
    "spinner.frame": Style(color="cyan", bold=True),
    "spinner.label": Style(bold=True),
    "spinner.elapsed": Style(dim=True),

    # Misc
    "link": Style(color="blue", underline=True),
    "code.inline": Style(color="cyan"),
    "key": Style(color="cyan", bold=True),
    "dim": Style(dim=True),
    "bold": Style(bold=True),
}


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def _build_theme(overrides: Dict[str, Style]) -> Theme:
    """Build a Rich Theme from the base styles with overrides."""
    merged = dict(STYLES)
    merged.update(overrides)
    return Theme({k: v for k, v in merged.items()})


# Dark theme (default)
THEME_DARK = _build_theme({})

# Light theme
THEME_LIGHT = _build_theme({
    "user.prefix": Style(color="dark_green", bold=True),
    "assistant.prefix": Style(color="dark_blue", bold=True),
    "tool.name": Style(color="dark_orange", bold=True),
    "statusbar.model": Style(color="black", bold=True, bgcolor="light_blue"),
    "statusbar.tokens": Style(color="dark_cyan"),
    "statusbar.cost": Style(color="dark_green"),
    "statusbar.branch": Style(color="dark_magenta"),
})

# Monokai theme
THEME_MONOKAI = _build_theme({
    "user.prefix": Style(color="#A6E22E", bold=True),
    "assistant.prefix": Style(color="#66D9EF", bold=True),
    "tool.name": Style(color="#FD971F", bold=True),
    "error.text": Style(color="#F92672"),
    "diff.add": Style(color="#A6E22E"),
    "diff.remove": Style(color="#F92672", strike=True),
})

# Solarized theme
THEME_SOLARIZED = _build_theme({
    "user.prefix": Style(color="#859900", bold=True),
    "assistant.prefix": Style(color="#268BD2", bold=True),
    "tool.name": Style(color="#CB4B16", bold=True),
    "error.text": Style(color="#DC322F"),
    "system.text": Style(color="#657B83"),
})

# Dracula theme
THEME_DRACULA = _build_theme({
    "user.prefix": Style(color="#50FA7B", bold=True),
    "assistant.prefix": Style(color="#8BE9FD", bold=True),
    "tool.name": Style(color="#FFB86C", bold=True),
    "error.text": Style(color="#FF5555"),
    "diff.add": Style(color="#50FA7B"),
    "diff.remove": Style(color="#FF5555", strike=True),
    "link": Style(color="#BD93F9", underline=True),
})


# Theme registry
THEMES: Dict[str, Theme] = {
    "dark": THEME_DARK,
    "light": THEME_LIGHT,
    "monokai": THEME_MONOKAI,
    "solarized": THEME_SOLARIZED,
    "dracula": THEME_DRACULA,
}


def get_theme(name: str = "dark") -> Theme:
    """Get a theme by name, falling back to dark."""
    return THEMES.get(name, THEME_DARK)


def get_style(name: str) -> Style:
    """Get a named style from the base style registry."""
    return STYLES.get(name, Style())


# ---------------------------------------------------------------------------
# Textual CSS theme variables
# ---------------------------------------------------------------------------

# These map to Textual's CSS variable system and can be used in TCSS files.
TEXTUAL_CSS_VARIABLES: Dict[str, Dict[str, str]] = {
    "dark": {
        "primary": "#5B9BD5",
        "secondary": "#7B68EE",
        "accent": "#5B9BD5",
        "warning": "#FFC107",
        "error": "#DC3545",
        "success": "#28A745",
        "surface": "#1E1E1E",
        "background": "#121212",
        "text": "#E0E0E0",
        "text-muted": "#6C757D",
    },
    "light": {
        "primary": "#0D6EFD",
        "secondary": "#6610F2",
        "accent": "#0D6EFD",
        "warning": "#FFC107",
        "error": "#DC3545",
        "success": "#198754",
        "surface": "#FFFFFF",
        "background": "#F8F9FA",
        "text": "#212529",
        "text-muted": "#6C757D",
    },
}


def get_textual_variables(theme_name: str = "dark") -> Dict[str, str]:
    """Get Textual CSS variables for a theme."""
    return TEXTUAL_CSS_VARIABLES.get(theme_name, TEXTUAL_CSS_VARIABLES["dark"])
