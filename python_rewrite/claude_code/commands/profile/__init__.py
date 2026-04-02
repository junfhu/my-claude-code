"""
/profile — View and manage user profile settings.

Type: local (runs locally, returns text).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------

_PROFILE_PATH = Path.home() / ".claude" / "profile.json"


def _load_profile() -> dict[str, Any]:
    try:
        return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_profile(data: dict[str, Any]) -> None:
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/profile [key] [value]``.

    - No args:     Show all profile fields.
    - One arg:     Show that field.
    - Two args:    Set field = value.
    """
    parts = args.strip().split(None, 1) if args else []
    profile = _load_profile()

    if not parts:
        if not profile:
            return TextResult(
                value="No profile information set.\n"
                "Usage: /profile <key> <value>"
            )
        lines = ["User Profile", "=" * 30, ""]
        for k, v in sorted(profile.items()):
            lines.append(f"  {k}: {v}")
        return TextResult(value="\n".join(lines))

    if len(parts) == 1:
        key = parts[0]
        val = profile.get(key)
        if val is not None:
            return TextResult(value=f"{key}: {val}")
        return TextResult(value=f"Profile field {key!r} is not set.")

    key, value = parts[0], parts[1]
    profile[key] = value
    _save_profile(profile)
    return TextResult(value=f"Set profile.{key} = {value}")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="profile",
    description="View and manage user profile settings",
    execute=_execute,
)
