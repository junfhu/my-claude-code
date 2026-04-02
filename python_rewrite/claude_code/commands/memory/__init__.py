"""
/memory — Manage persistent memory (CLAUDE.md files).

Type: local_jsx (renders memory editor).

CLAUDE.md files provide persistent instructions that are loaded into
every session.  This command lets you view and edit them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Memory file locations
# ---------------------------------------------------------------------------

_MEMORY_FILES = [
    ("User-global", Path.home() / ".claude" / "CLAUDE.md"),
    ("User-local", Path.home() / ".claude" / "CLAUDE.local.md"),
]


def _project_memory_files() -> list[tuple[str, Path]]:
    """Return project-level memory files relative to cwd."""
    cwd = Path(os.getcwd())
    return [
        ("Project", cwd / "CLAUDE.md"),
        ("Project-local", cwd / "CLAUDE.local.md"),
    ]


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/memory [edit|show|reset] [scope]``.

    - No args / show:  Display all memory files and their contents.
    - edit <scope>:    Open the specified memory file for editing.
    - reset <scope>:   Clear the specified memory file.
    """
    parts = args.strip().split() if args else []
    sub = parts[0].lower() if parts else "show"

    all_files = _MEMORY_FILES + _project_memory_files()

    if sub in ("show", "list", "ls"):
        lines: list[str] = ["Claude Memory Files", "=" * 40, ""]
        for label, path in all_files:
            exists = path.exists()
            lines.append(f"  [{label}] {path}")
            if exists:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    # Show first 5 lines as preview
                    preview = "\n".join(content.splitlines()[:5])
                    if len(content.splitlines()) > 5:
                        preview += f"\n    ... ({len(content.splitlines())} lines total)"
                    for line in preview.splitlines():
                        lines.append(f"    {line}")
                else:
                    lines.append("    (empty)")
            else:
                lines.append("    (not created)")
            lines.append("")

        return TextResult(value="\n".join(lines))

    if sub == "edit":
        scope = parts[1] if len(parts) > 1 else "project"
        target = _resolve_scope(scope, all_files)
        if target is None:
            return TextResult(
                value=f"Unknown scope {scope!r}.  "
                f"Available: {', '.join(label.lower() for label, _ in all_files)}"
            )
        label, path = target
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                f"# CLAUDE.md\n\n"
                f"This file provides guidance to Claude Code when working "
                f"with code in this repository.\n",
                encoding="utf-8",
            )
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
        return TextResult(
            value=f"Opening {path} in {editor}.\n"
            f"Run:  {editor} {path}"
        )

    if sub == "reset":
        scope = parts[1] if len(parts) > 1 else "project"
        target = _resolve_scope(scope, all_files)
        if target is None:
            return TextResult(value=f"Unknown scope {scope!r}.")
        label, path = target
        if path.exists():
            path.write_text("", encoding="utf-8")
            return TextResult(value=f"Cleared {label} memory ({path}).")
        return TextResult(value=f"{label} memory file does not exist ({path}).")

    return TextResult(
        value="Usage: /memory [show|edit|reset] [scope]\n"
        "Scopes: user-global, user-local, project, project-local"
    )


def _resolve_scope(
    scope: str,
    all_files: list[tuple[str, Path]],
) -> tuple[str, Path] | None:
    """Fuzzy-match a scope name to a memory file."""
    scope_lower = scope.lower().replace("-", "").replace("_", "")
    for label, path in all_files:
        if scope_lower in label.lower().replace("-", "").replace("_", ""):
            return label, path
    return None


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="memory",
    description="Edit Claude memory files",
    call=_execute,
)
