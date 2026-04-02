"""
/logout — Sign out from Anthropic account.

Type: local_jsx (renders logout confirmation).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_logout_disabled() -> bool:
    return os.environ.get("DISABLE_LOGOUT_COMMAND", "").lower() in (
        "1", "true", "yes",
    )


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

_CREDENTIALS_PATH = Path.home() / ".claude" / "credentials.json"


async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Sign out from the Anthropic account.

    Removes stored OAuth tokens and credentials.
    """
    if _CREDENTIALS_PATH.exists():
        try:
            _CREDENTIALS_PATH.unlink()
            return TextResult(
                value="Logged out successfully.\n"
                "OAuth credentials have been removed."
            )
        except OSError as exc:
            return TextResult(value=f"Error removing credentials: {exc}")

    return TextResult(value="Not currently logged in (no credentials found).")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="logout",
    description="Sign out from your Anthropic account",
    is_enabled=lambda: not _is_logout_disabled(),
    call=_execute,
)
