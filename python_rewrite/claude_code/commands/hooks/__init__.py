"""
/hooks — View and manage hook configurations for tool events.

Type: local_jsx (renders hooks listing).

Hooks are deterministic shell commands that run on tool events like
``PreToolUse``, ``PostToolUse``, and ``Stop``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Hook config locations
# ---------------------------------------------------------------------------

def _load_hooks() -> list[dict[str, Any]]:
    """Load hooks from project and user settings files."""
    hooks: list[dict[str, Any]] = []

    settings_files = [
        Path.home() / ".claude" / "settings.json",
        Path(os.getcwd()) / ".claude" / "settings.json",
        Path(os.getcwd()) / ".claude" / "settings.local.json",
    ]

    for path in settings_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            hook_cfg = data.get("hooks", {})
            for event_type, event_hooks in hook_cfg.items():
                if isinstance(event_hooks, list):
                    for h in event_hooks:
                        hooks.append({
                            "event": event_type,
                            "matcher": h.get("matcher", "*"),
                            "command": h.get("command", ""),
                            "timeout": h.get("timeout", 10000),
                            "source": str(path),
                        })
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue

    return hooks


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Display all configured hooks.
    """
    hooks = _load_hooks()

    if not hooks:
        return TextResult(
            value="No hooks configured.\n\n"
            "Hooks are deterministic shell commands that run on tool events.\n"
            "Configure them in .claude/settings.json under the 'hooks' key.\n\n"
            "Example:\n"
            '  "hooks": {\n'
            '    "PostToolUse": [{\n'
            '      "matcher": "Write|Edit",\n'
            '      "command": "ruff format $FILEPATH"\n'
            "    }]\n"
            "  }"
        )

    lines = ["Hook Configurations", "=" * 50, ""]
    for h in hooks:
        lines.append(f"  Event:   {h['event']}")
        lines.append(f"  Matcher: {h['matcher']}")
        lines.append(f"  Command: {h['command']}")
        lines.append(f"  Timeout: {h['timeout']}ms")
        lines.append(f"  Source:  {h['source']}")
        lines.append("")

    lines.append(f"Total: {len(hooks)} hook(s)")
    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="hooks",
    description="View hook configurations for tool events",
    immediate=True,
    call=_execute,
)
