"""
/plugins — Manage plugins.

Type: local_jsx (renders plugin manager).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------

_PLUGINS_DIR = Path.home() / ".claude" / "plugins"


def _list_plugins() -> list[dict[str, Any]]:
    """Discover installed plugins from the plugins directory."""
    plugins: list[dict[str, Any]] = []

    if not _PLUGINS_DIR.is_dir():
        return plugins

    for entry in sorted(_PLUGINS_DIR.iterdir()):
        manifest_path = entry / "manifest.json" if entry.is_dir() else None
        if manifest_path and manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                plugins.append({
                    "name": manifest.get("name", entry.name),
                    "version": manifest.get("version", "unknown"),
                    "description": manifest.get("description", ""),
                    "enabled": manifest.get("enabled", True),
                    "path": str(entry),
                })
            except (json.JSONDecodeError, OSError):
                plugins.append({
                    "name": entry.name,
                    "version": "unknown",
                    "description": "(manifest error)",
                    "enabled": False,
                    "path": str(entry),
                })

    return plugins


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/plugins [list|install|uninstall|enable|disable] [name]``.
    """
    parts = args.strip().split(None, 1) if args else []
    sub = parts[0].lower() if parts else "list"
    name = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("list", "ls", ""):
        plugins = _list_plugins()
        if not plugins:
            return TextResult(
                value="No plugins installed.\n\n"
                "Install a plugin with: /plugins install <name>\n"
                "Browse official plugins: /plugins install <name>@claude-plugins-official"
            )

        lines = ["Installed Plugins", "=" * 40, ""]
        for p in plugins:
            status = "enabled" if p["enabled"] else "disabled"
            lines.append(f"  {p['name']} v{p['version']}  ({status})")
            if p["description"]:
                lines.append(f"    {p['description']}")
        lines.append("")
        lines.append(f"Total: {len(plugins)} plugin(s)")
        return TextResult(value="\n".join(lines))

    if sub == "install":
        if not name:
            return TextResult(value="Usage: /plugins install <plugin-name>")
        # Placeholder — real implementation downloads and installs
        return TextResult(value=f"Installing plugin {name!r}...")

    if sub == "uninstall":
        if not name:
            return TextResult(value="Usage: /plugins uninstall <plugin-name>")
        return TextResult(value=f"Uninstalling plugin {name!r}...")

    if sub == "enable":
        if not name:
            return TextResult(value="Usage: /plugins enable <plugin-name>")
        return TextResult(value=f"Plugin {name!r} enabled.")

    if sub == "disable":
        if not name:
            return TextResult(value="Usage: /plugins disable <plugin-name>")
        return TextResult(value=f"Plugin {name!r} disabled.")

    return TextResult(
        value="Usage: /plugins [list|install|uninstall|enable|disable] [name]"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="plugins",
    description="Manage plugins",
    aliases=["plugin"],
    call=_execute,
)
