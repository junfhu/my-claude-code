"""
/theme — Change the color theme.

Type: local_jsx (renders theme picker).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Available themes
# ---------------------------------------------------------------------------

THEMES = [
    "dark",
    "light",
    "dark-daltonized",
    "light-daltonized",
    "solarized-dark",
    "solarized-light",
    "monokai",
    "dracula",
    "nord",
    "gruvbox",
]

_GLOBAL_CONFIG = Path.home() / ".claude" / "config.json"


def _get_theme() -> str:
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
        return data.get("theme", "dark")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "dark"


def _set_theme(name: str) -> None:
    _GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data["theme"] = name
    _GLOBAL_CONFIG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/theme [name]``.

    - No args:  List available themes and highlight the current one.
    - With arg: Set the theme.
    """
    current = _get_theme()

    if not args or not args.strip():
        lines = ["Available Themes", "=" * 30, ""]
        for t in THEMES:
            marker = "  *" if t == current else ""
            lines.append(f"  {t}{marker}")
        lines.append("")
        lines.append(f"Current: {current}")
        lines.append("Usage: /theme <name>")
        return TextResult(value="\n".join(lines))

    name = args.strip().lower()
    if name not in THEMES:
        return TextResult(
            value=f"Unknown theme {name!r}.\n"
            f"Available: {', '.join(THEMES)}"
        )

    _set_theme(name)
    return TextResult(value=f"Theme set to {name}.")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="theme",
    description="Change the theme",
    call=_execute,
)
