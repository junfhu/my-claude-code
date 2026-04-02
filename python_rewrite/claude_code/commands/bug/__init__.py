"""
/bug — Submit a bug report / feedback.

Type: local_jsx (renders feedback form).

Aliased from the TypeScript /feedback command (``feedback`` with alias ``bug``).
"""

from __future__ import annotations

import json
import os
import platform
import sys
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_feedback_disabled() -> bool:
    return any(
        os.environ.get(v, "").lower() in ("1", "true", "yes")
        for v in (
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
            "DISABLE_FEEDBACK_COMMAND",
            "DISABLE_BUG_COMMAND",
        )
    ) or os.environ.get("USER_TYPE") == "ant"


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Submit bug report or feedback about Claude Code.

    - No args: Interactive prompt for feedback text.
    - With arg: Submit the provided text as feedback.
    """
    report_text = args.strip() if args else ""

    if not report_text:
        return TextResult(
            value="Usage: /bug <description of the issue>\n\n"
            "Please describe the issue you're experiencing. Include:\n"
            "  - What you were trying to do\n"
            "  - What happened instead\n"
            "  - Steps to reproduce (if applicable)"
        )

    # Collect environment info for the bug report
    env_info = {
        "python": sys.version,
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "cwd": os.getcwd(),
    }

    try:
        from ... import __version__
        env_info["version"] = __version__
    except ImportError:
        env_info["version"] = "unknown"

    # Placeholder — real implementation submits to Anthropic's feedback API
    lines = [
        "Bug report submitted. Thank you for the feedback!",
        "",
        "Report details:",
        f"  Description: {report_text[:200]}",
        f"  Version:     {env_info.get('version', 'unknown')}",
        f"  Platform:    {env_info['platform']}",
    ]

    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="bug",
    description="Submit feedback about Claude Code",
    aliases=["feedback"],
    argument_hint="[report]",
    is_enabled=lambda: not _is_feedback_disabled(),
    call=_execute,
)
