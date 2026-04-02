"""
/agents — View and manage agent configurations.

Type: local_jsx (renders agent listing).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Agent discovery
# ---------------------------------------------------------------------------

_AGENTS_DIR = Path.home() / ".claude" / "agents"


def _discover_agents() -> list[dict[str, str]]:
    """
    Scan agent configuration directories.

    Agents are defined in JSON files under ~/.claude/agents/ or
    .claude/agents/ in the project.
    """
    agents: list[dict[str, str]] = []
    dirs = [
        _AGENTS_DIR,
        Path(os.getcwd()) / ".claude" / "agents",
    ]

    for agent_dir in dirs:
        if not agent_dir.is_dir():
            continue
        for f in sorted(agent_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                agents.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "model": data.get("model", "default"),
                    "path": str(f),
                })
            except (json.JSONDecodeError, OSError):
                agents.append({
                    "name": f.stem,
                    "description": "(config error)",
                    "model": "unknown",
                    "path": str(f),
                })

    return agents


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/agents [list|create|delete] [name]``.
    """
    parts = args.strip().split(None, 1) if args else []
    sub = parts[0].lower() if parts else "list"

    if sub in ("list", "ls", ""):
        agents = _discover_agents()
        if not agents:
            return TextResult(
                value="No agent configurations found.\n"
                "Create one in .claude/agents/<name>.json"
            )

        lines = ["Agent Configurations", "=" * 40, ""]
        for a in agents:
            lines.append(f"  {a['name']}")
            lines.append(f"    Model:       {a['model']}")
            lines.append(f"    Description: {a['description'] or '(none)'}")
            lines.append(f"    Path:        {a['path']}")
            lines.append("")
        lines.append(f"Total: {len(agents)} agent(s)")
        return TextResult(value="\n".join(lines))

    return TextResult(
        value="Usage: /agents [list|create|delete] [name]"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="agents",
    description="Manage agent configurations",
    call=_execute,
)
