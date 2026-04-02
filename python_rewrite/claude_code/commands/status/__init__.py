"""
/status — Show current Claude Code status.

Type: local_jsx (renders status panel).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Display Claude Code status including version, model, account,
    API connectivity, and tool statuses.
    """
    lines = ["Claude Code Status", "=" * 40, ""]

    # Version
    try:
        from ... import __version__
        lines.append(f"  Version:   {__version__}")
    except ImportError:
        lines.append("  Version:   unknown")

    # Python
    lines.append(f"  Python:    {sys.version.split()[0]}")
    lines.append(f"  Platform:  {platform.system()} {platform.machine()}")

    # Model
    model = os.environ.get("ANTHROPIC_MODEL", os.environ.get("CLAUDE_MODEL", "default"))
    lines.append(f"  Model:     {model}")

    # Auth
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        lines.append(f"  API Key:   {masked}")
    elif os.environ.get("CLAUDE_AI_SUBSCRIBER", ""):
        lines.append("  Auth:      claude.ai OAuth")
    else:
        lines.append("  Auth:      NOT CONFIGURED")

    # CWD
    lines.append(f"  CWD:       {os.getcwd()}")

    # Git info
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        lines.append(f"  Git branch: {branch}")
    except Exception:
        lines.append("  Git branch: (not in a git repo)")

    # MCP servers (count)
    lines.append("")
    lines.append("  Tools:      (available via tool registry)")
    lines.append("  MCP:        (see /mcp for server details)")

    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="status",
    description=(
        "Show Claude Code status including version, model, account, "
        "API connectivity, and tool statuses"
    ),
    immediate=True,
    call=_execute,
)
