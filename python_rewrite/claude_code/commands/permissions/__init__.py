"""
/permissions — Manage tool permission rules.

Type: local_jsx (renders permission manager).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Permission storage
# ---------------------------------------------------------------------------

_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _load_permissions() -> dict[str, list[str]]:
    """Load allow/deny rules from settings."""
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return {
            "allow": data.get("permissions", {}).get("allow", []),
            "deny": data.get("permissions", {}).get("deny", []),
        }
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"allow": [], "deny": []}


def _save_permissions(perms: dict[str, list[str]]) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data.setdefault("permissions", {})
    data["permissions"]["allow"] = perms["allow"]
    data["permissions"]["deny"] = perms["deny"]
    _SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/permissions [allow|deny|remove|list] [rule]``.
    """
    parts = args.strip().split(None, 1) if args else []
    sub = parts[0].lower() if parts else "list"
    rule = parts[1].strip() if len(parts) > 1 else ""

    perms = _load_permissions()

    if sub in ("list", "ls", ""):
        lines = ["Permission Rules", "=" * 40, ""]
        if perms["allow"]:
            lines.append("Allow rules:")
            for r in perms["allow"]:
                lines.append(f"  + {r}")
        else:
            lines.append("Allow rules: (none)")
        lines.append("")
        if perms["deny"]:
            lines.append("Deny rules:")
            for r in perms["deny"]:
                lines.append(f"  - {r}")
        else:
            lines.append("Deny rules: (none)")
        lines.append("")
        lines.append("Usage: /permissions [allow|deny|remove] <rule>")
        return TextResult(value="\n".join(lines))

    if sub == "allow":
        if not rule:
            return TextResult(value="Usage: /permissions allow <tool-pattern>")
        if rule not in perms["allow"]:
            perms["allow"].append(rule)
            _save_permissions(perms)
        return TextResult(value=f"Added allow rule: {rule}")

    if sub == "deny":
        if not rule:
            return TextResult(value="Usage: /permissions deny <tool-pattern>")
        if rule not in perms["deny"]:
            perms["deny"].append(rule)
            _save_permissions(perms)
        return TextResult(value=f"Added deny rule: {rule}")

    if sub == "remove":
        if not rule:
            return TextResult(value="Usage: /permissions remove <rule>")
        removed = False
        if rule in perms["allow"]:
            perms["allow"].remove(rule)
            removed = True
        if rule in perms["deny"]:
            perms["deny"].remove(rule)
            removed = True
        if removed:
            _save_permissions(perms)
            return TextResult(value=f"Removed rule: {rule}")
        return TextResult(value=f"Rule not found: {rule}")

    return TextResult(
        value="Usage: /permissions [list|allow|deny|remove] [rule]"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="permissions",
    description="Manage allow & deny tool permission rules",
    aliases=["allowed-tools"],
    call=_execute,
)
