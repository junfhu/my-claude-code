"""
/vim — Toggle vim editing mode.

Type: local (runs locally, returns text).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_GLOBAL_CONFIG = Path.home() / ".claude" / "config.json"


def _get_editor_mode() -> str:
    """Read the current editor mode from global config."""
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
        mode = data.get("editorMode", "normal")
        # Backward compat: treat 'emacs' as 'normal'
        if mode == "emacs":
            mode = "normal"
        return mode
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "normal"


def _set_editor_mode(mode: str) -> None:
    """Persist the editor mode to global config."""
    _GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data["editorMode"] = mode
    _GLOBAL_CONFIG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """Toggle between vim and normal editing modes."""
    current = _get_editor_mode()
    new_mode = "vim" if current == "normal" else "normal"

    _set_editor_mode(new_mode)

    if new_mode == "vim":
        detail = "Use Escape key to toggle between INSERT and NORMAL modes."
    else:
        detail = "Using standard (readline) keyboard bindings."

    return TextResult(value=f"Editor mode set to {new_mode}. {detail}")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="vim",
    description="Toggle between Vim and Normal editing modes",
    supports_non_interactive=False,
    execute=_execute,
)
