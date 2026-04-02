"""
/config — View and edit settings.

Type: local_jsx (renders interactive config panel).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Config file resolution
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path.home() / ".claude"
_GLOBAL_CONFIG = _CONFIG_DIR / "config.json"
_PROJECT_CONFIG_NAME = ".claude" / Path("settings.json")


def _load_config(path: Path) -> dict[str, Any]:
    """Load a JSON config file, returning ``{}`` on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_config(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as pretty-printed JSON, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/config [key] [value]``.

    - No args        → list all settings
    - One arg        → show that key's value
    - Two args       → set key = value
    """
    parts = args.strip().split(None, 1) if args else []

    global_cfg = _load_config(_GLOBAL_CONFIG)

    # Project-level config (cwd)
    cwd = os.getcwd()
    project_cfg_path = Path(cwd) / _PROJECT_CONFIG_NAME
    project_cfg = _load_config(project_cfg_path)

    if len(parts) == 0:
        # List all settings
        merged = {**global_cfg, **project_cfg}
        if not merged:
            return TextResult(value="No configuration values set.")

        lines = ["Current configuration:\n"]
        lines.append("Global settings:")
        if global_cfg:
            for k, v in sorted(global_cfg.items()):
                lines.append(f"  {k} = {json.dumps(v)}")
        else:
            lines.append("  (none)")

        lines.append("\nProject settings:")
        if project_cfg:
            for k, v in sorted(project_cfg.items()):
                lines.append(f"  {k} = {json.dumps(v)}")
        else:
            lines.append("  (none)")

        lines.append(
            f"\nGlobal config:  {_GLOBAL_CONFIG}"
        )
        lines.append(f"Project config: {project_cfg_path}")
        return TextResult(value="\n".join(lines))

    if len(parts) == 1:
        key = parts[0]
        # Show a specific key
        if key in project_cfg:
            return TextResult(
                value=f"{key} = {json.dumps(project_cfg[key])} (project)"
            )
        if key in global_cfg:
            return TextResult(
                value=f"{key} = {json.dumps(global_cfg[key])} (global)"
            )
        return TextResult(value=f"Setting {key!r} is not set.")

    # Set a value
    key, raw_value = parts[0], parts[1]

    # Try to parse as JSON, fall back to string
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value

    global_cfg[key] = value
    _save_config(_GLOBAL_CONFIG, global_cfg)
    return TextResult(
        value=f"Set {key} = {json.dumps(value)} (global)"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="config",
    description="Open config panel",
    aliases=["settings"],
    call=_execute,
)
