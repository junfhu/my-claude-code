"""
/release_notes — Show release notes / changelog.

Type: local (runs locally, returns text).
"""

from __future__ import annotations

from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Release notes content
# ---------------------------------------------------------------------------

_RELEASE_NOTES = """\
Claude Code — Release Notes
============================

## Latest

- Full Python rewrite of the command system
- All slash commands ported from TypeScript
- Unified command registry with type-safe definitions
- Support for PromptCommand, LocalCommand, and LocalJSXCommand types
- Feature flag gating via environment variables
- Auth-aware command availability filtering

## Architecture

Commands are organized as:
  claude_code/
    command_registry.py   — Central registry and types
    commands/             — Individual command modules
      help/               — /help
      compact/            — /compact
      config/             — /config
      ...

Each command exports a `command` object that the registry collects.

For the full changelog, visit:
  https://github.com/anthropics/claude-code/releases
"""


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """Show release notes."""
    return TextResult(value=_RELEASE_NOTES)


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="release-notes",
    description="View release notes",
    supports_non_interactive=True,
    execute=_execute,
)
