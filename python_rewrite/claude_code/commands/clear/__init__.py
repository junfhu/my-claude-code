"""
/clear — Clear conversation history.

Type: local (runs locally, returns text).

Wipes the current conversation and resets the session, freeing up
context window capacity.
"""

from __future__ import annotations

from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Clear the current conversation history.

    Steps:
    1. Wipe messages from context.
    2. Clear session-level caches (cost tracker, tool state, etc.).
    3. Return confirmation text.
    """
    # Wire into context if available
    if context is not None:
        # Clear messages
        if hasattr(context, "set_messages"):
            context.set_messages(lambda _prev: [])
        # Clear session caches
        if hasattr(context, "clear_session_caches"):
            context.clear_session_caches()

    return TextResult(
        value="Conversation cleared. Starting fresh with a clean context."
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="clear",
    description="Clear conversation history and free up context",
    aliases=["reset", "new"],
    supports_non_interactive=False,
    execute=_execute,
)
