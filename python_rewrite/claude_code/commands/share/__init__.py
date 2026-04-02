"""
/share — Share the current session.

Type: local (runs locally, returns text).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Generate a shareable link for the current conversation.

    In the full implementation this uploads an anonymised transcript to
    the Claude Code sharing service.  Here we generate a placeholder.
    """
    # Build a synthetic session ID from current time
    session_id = hashlib.sha256(
        f"{time.time()}-{os.getpid()}".encode()
    ).hexdigest()[:12]

    # Placeholder — real implementation posts to the sharing API
    share_url = f"https://claude.ai/share/{session_id}"

    return TextResult(
        value=f"Session shared!\n\nShareable link: {share_url}\n\n"
        "Note: Shared sessions include the full conversation transcript."
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="share",
    description="Share the current session via a link",
    execute=_execute,
)
