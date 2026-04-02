"""
commands — Slash command implementations for Claude Code.

Each submodule exports a ``command`` object (a PromptCommand, LocalCommand,
or LocalJSXCommand) that the central registry in ``command_registry.py``
collects into the master command list.

Package-level imports are deliberately *lazy* — individual command modules
are only imported when ``get_all_commands()`` is called, not at package
init time.  This keeps startup fast and avoids import-time side-effects.
"""

from __future__ import annotations

# Re-export submodules so the registry can do:
#     from .commands import help, compact, ...
from . import (
    add_dir,
    advisor,
    agents,
    branch,
    bug,
    clear,
    commit,
    compact,
    config,
    cost,
    diff,
    doctor,
    exit,
    help,
    hooks,
    init,
    login,
    logout,
    mcp,
    memory,
    model,
    permissions,
    plugins,
    profile,
    project_init,
    release_notes,
    resume,
    review,
    share,
    skills,
    status,
    tasks,
    theme,
    vim,
    voice,
)

__all__ = [
    "add_dir",
    "advisor",
    "agents",
    "branch",
    "bug",
    "clear",
    "commit",
    "compact",
    "config",
    "cost",
    "diff",
    "doctor",
    "exit",
    "help",
    "hooks",
    "init",
    "login",
    "logout",
    "mcp",
    "memory",
    "model",
    "permissions",
    "plugins",
    "profile",
    "project_init",
    "release_notes",
    "resume",
    "review",
    "share",
    "skills",
    "status",
    "tasks",
    "theme",
    "vim",
    "voice",
]
