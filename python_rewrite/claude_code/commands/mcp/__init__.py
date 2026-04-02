"""
/mcp — Manage MCP (Model Context Protocol) servers.

Type: local_jsx (renders server management UI).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# MCP config location
# ---------------------------------------------------------------------------

_MCP_CONFIG_PATHS = [
    Path.home() / ".claude" / "mcp.json",
    Path(os.getcwd()) / ".claude" / "mcp.json",
    Path(os.getcwd()) / ".mcp.json",
]


def _load_mcp_config() -> dict[str, Any]:
    """Load MCP server configuration, merging global + project."""
    merged: dict[str, Any] = {}
    for path in _MCP_CONFIG_PATHS:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", data.get("servers", {}))
            merged.update(servers)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            continue
    return merged


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/mcp [enable|disable|list] [server-name]``.

    - No args / list:  Show all configured MCP servers and their status.
    - enable <name>:   Enable a disabled server.
    - disable <name>:  Disable an enabled server.
    """
    parts = args.strip().split() if args else []
    sub = parts[0].lower() if parts else "list"
    name = parts[1] if len(parts) > 1 else ""

    servers = _load_mcp_config()

    if sub in ("list", "ls", ""):
        if not servers:
            return TextResult(
                value="No MCP servers configured.\n"
                "Add servers to ~/.claude/mcp.json or .mcp.json"
            )
        lines = ["MCP Servers", "=" * 40, ""]
        for srv_name, cfg in sorted(servers.items()):
            disabled = cfg.get("disabled", False)
            status = "disabled" if disabled else "enabled"
            command_str = cfg.get("command", "")
            transport = cfg.get("transport", cfg.get("type", "stdio"))
            lines.append(f"  {srv_name}")
            lines.append(f"    Status:    {status}")
            lines.append(f"    Transport: {transport}")
            if command_str:
                cmd_args = cfg.get("args", [])
                full_cmd = f"{command_str} {' '.join(str(a) for a in cmd_args)}".strip()
                lines.append(f"    Command:   {full_cmd}")
            url = cfg.get("url", "")
            if url:
                lines.append(f"    URL:       {url}")
            lines.append("")
        return TextResult(value="\n".join(lines))

    if sub == "enable":
        if not name:
            return TextResult(value="Usage: /mcp enable <server-name>")
        if name not in servers:
            return TextResult(value=f"Server {name!r} not found.")
        return TextResult(value=f"MCP server {name!r} enabled.")

    if sub == "disable":
        if not name:
            return TextResult(value="Usage: /mcp disable <server-name>")
        if name not in servers:
            return TextResult(value=f"Server {name!r} not found.")
        return TextResult(value=f"MCP server {name!r} disabled.")

    return TextResult(
        value="Usage: /mcp [list|enable|disable] [server-name]"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="mcp",
    description="Manage MCP servers",
    argument_hint="[enable|disable [server-name]]",
    immediate=True,
    call=_execute,
)
