"""
command_registry.py — The central command registry for Claude Code REPL.

This module is the single source of truth for all slash commands (e.g. /help,
/compact, /config). It handles:
  1. Registering built-in commands (the get_all_commands() list)
  2. Filtering commands by availability (auth/provider) and enablement
     (feature flags, env vars)
  3. Deduplicating commands when multiple sources define the same name
  4. Exposing helpers to find, filter, and format commands for the UI

Commands come in three types:
  - PromptCommand (type: 'prompt')     — Expands into content sent to the model.
      Used by skills, custom prompts, and model-invocable commands.
  - LocalCommand (type: 'local')       — Runs locally, returns text/compact result.
      Used by commands like /compact, /cost that produce text output.
  - LocalJSXCommand (type: 'local_jsx') — Renders a TUI component (Rich/Textual).
      Used by interactive commands like /config, /mcp, /model that need UI.

Note: Named command_registry.py (not commands.py) to avoid shadowing the
commands/ package directory.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Union,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CommandType(Enum):
    """The three types of slash command."""
    PROMPT = "prompt"          # Expands to content sent to model
    LOCAL = "local"            # Runs locally, returns text
    LOCAL_JSX = "local_jsx"    # Renders TUI component (Rich/Textual)


class CommandAvailability(Enum):
    """Auth/provider environments a command can be restricted to."""
    CLAUDE_AI = "claude-ai"    # claude.ai OAuth subscriber
    CONSOLE = "console"        # Console API key user (direct api.anthropic.com)


class CommandSource(Enum):
    """Where a command was loaded from."""
    BUILTIN = "builtin"
    MCP = "mcp"
    PLUGIN = "plugin"
    BUNDLED = "bundled"
    USER = "user"
    PROJECT = "project"


class CommandLoadedFrom(Enum):
    """Physical origin of a command module."""
    COMMANDS_DEPRECATED = "commands_DEPRECATED"
    SKILLS = "skills"
    PLUGIN = "plugin"
    MANAGED = "managed"
    BUNDLED = "bundled"
    MCP = "mcp"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class TextResult:
    """Simple text output from a local command."""
    type: str = "text"
    value: str = ""


@dataclass
class CompactResult:
    """Result from a compaction command."""
    type: str = "compact"
    summary: str = ""
    messages_before: int = 0
    messages_after: int = 0
    display_text: str = ""


@dataclass
class SkipResult:
    """Sentinel — skip message display."""
    type: str = "skip"


LocalCommandResult = Union[TextResult, CompactResult, SkipResult]


# ---------------------------------------------------------------------------
# Command dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BaseCommand:
    """
    Shared metadata for every slash command.

    Fields mirror the TypeScript ``CommandBase`` type from types/command.ts.
    """
    name: str
    description: str
    type: CommandType = CommandType.LOCAL
    aliases: list[str] = field(default_factory=list)
    is_enabled: Callable[[], bool] = field(default=lambda: True)
    is_hidden: bool | Callable[[], bool] = False
    requires_auth: bool = False
    argument_hint: str = ""
    availability: list[CommandAvailability] = field(default_factory=list)
    when_to_use: str = ""
    immediate: bool = False
    is_sensitive: bool = False
    disable_model_invocation: bool = False
    user_invocable: bool = True
    source: CommandSource = CommandSource.BUILTIN
    loaded_from: Optional[CommandLoadedFrom] = None
    kind: Optional[str] = None  # e.g. "workflow"
    has_user_specified_description: bool = False
    supports_non_interactive: bool = False
    # Override display name (defaults to self.name)
    _user_facing_name: Optional[Callable[[], str]] = field(
        default=None, repr=False
    )

    # ------------------------------------------------------------------
    @property
    def hidden(self) -> bool:
        if callable(self.is_hidden):
            return self.is_hidden()
        return self.is_hidden

    @property
    def enabled(self) -> bool:
        return self.is_enabled()

    @property
    def user_facing_name(self) -> str:
        if self._user_facing_name is not None:
            return self._user_facing_name()
        return self.name


@dataclass
class PromptCommand(BaseCommand):
    """
    Command that expands to content sent to the model.

    The ``get_prompt_content`` callback receives ``(args, context)`` and must
    return a list of content-block dicts (``[{"type": "text", "text": ...}]``).
    """
    type: CommandType = field(default=CommandType.PROMPT, init=False)
    get_prompt_content: Optional[Callable[..., Any]] = None
    progress_message: str = ""
    content_length: int = 0
    allowed_tools: list[str] = field(default_factory=list)
    model: Optional[str] = None


@dataclass
class LocalCommand(BaseCommand):
    """
    Command that runs locally and returns text.

    ``execute`` receives ``(args, context)`` and returns a ``LocalCommandResult``.
    """
    type: CommandType = field(default=CommandType.LOCAL, init=False)
    execute: Optional[Callable[..., Any]] = None


@dataclass
class LocalJSXCommand(BaseCommand):
    """
    Command that renders a TUI component (Rich/Textual).

    ``call`` receives ``(on_done, context, args)`` and returns a renderable.
    """
    type: CommandType = field(default=CommandType.LOCAL_JSX, init=False)
    call: Optional[Callable[..., Any]] = None


Command = Union[PromptCommand, LocalCommand, LocalJSXCommand]


# ---------------------------------------------------------------------------
# Command registry helpers
# ---------------------------------------------------------------------------

def get_command_name(cmd: Command) -> str:
    """Return the user-visible name, falling back to ``cmd.name``."""
    return cmd.user_facing_name


def is_command_enabled(cmd: Command) -> bool:
    """Return whether the command is currently enabled."""
    return cmd.enabled


# ---------------------------------------------------------------------------
# Master command list — lazily built, cached
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def get_all_commands() -> list[Command]:
    """
    Collect and return every built-in slash command.

    This is the Python equivalent of the TypeScript ``COMMANDS()`` array.
    Imported lazily so that module-level side-effects don't fire at import
    time (config may not be loaded yet).
    """
    from .commands import (
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
        exit as exit_cmd,
        help as help_cmd,
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

    commands: list[Command] = [
        add_dir.command,
        advisor.command,
        agents.command,
        branch.command,
        bug.command,
        clear.command,
        commit.command,
        compact.command,
        config.command,
        cost.command,
        diff.command,
        doctor.command,
        exit_cmd.command,
        help_cmd.command,
        hooks.command,
        init.command,
        login.command,
        logout.command,
        mcp.command,
        memory.command,
        model.command,
        permissions.command,
        plugins.command,
        profile.command,
        project_init.command,
        release_notes.command,
        resume.command,
        review.command,
        share.command,
        skills.command,
        status.command,
        tasks.command,
        theme.command,
        vim.command,
        voice.command,
    ]

    # Filter out feature-gated / auth-gated commands
    return [c for c in commands if c is not None]


def invalidate_commands_cache() -> None:
    """Clear the cached command list so it's rebuilt on next access."""
    get_all_commands.cache_clear()


# ---------------------------------------------------------------------------
# Built-in command name set (for deduplication against external commands)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def builtin_command_names() -> set[str]:
    """Set of all built-in command names *and* aliases."""
    names: set[str] = set()
    for cmd in get_all_commands():
        names.add(cmd.name)
        names.update(cmd.aliases)
    return names


# ---------------------------------------------------------------------------
# Availability / auth gating
# ---------------------------------------------------------------------------

def _is_using_3p_services() -> bool:
    """True when running against Bedrock / Vertex / Foundry."""
    return any(
        os.environ.get(v, "").lower() in ("1", "true", "yes")
        for v in (
            "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_FOUNDRY",
        )
    )


def _is_claude_ai_subscriber() -> bool:
    """True when the user is an authenticated claude.ai subscriber."""
    return os.environ.get("CLAUDE_AI_SUBSCRIBER", "").lower() in (
        "1", "true", "yes",
    )


def meets_availability_requirement(cmd: Command) -> bool:
    """
    Filter commands by their declared ``availability``.

    Commands without ``availability`` are treated as universal.
    Not memoized — auth state can change mid-session.
    """
    if not cmd.availability:
        return True

    for avail in cmd.availability:
        if avail == CommandAvailability.CLAUDE_AI:
            if _is_claude_ai_subscriber():
                return True
        elif avail == CommandAvailability.CONSOLE:
            if not _is_claude_ai_subscriber() and not _is_using_3p_services():
                return True

    return False


# ---------------------------------------------------------------------------
# Async command loading — mirrors getCommands(cwd) from the TS code
# ---------------------------------------------------------------------------

async def get_commands(cwd: str | None = None) -> list[Command]:
    """
    Return commands available to the current user.

    Expensive loading is cached; availability/enablement checks run fresh.
    """
    all_cmds = get_all_commands()
    return [
        c for c in all_cmds
        if meets_availability_requirement(c) and is_command_enabled(c)
    ]


# ---------------------------------------------------------------------------
# Command lookup utilities
# ---------------------------------------------------------------------------

def find_command(
    command_name: str,
    commands: Sequence[Command] | None = None,
) -> Command | None:
    """
    Look up a command by name, user-facing name, or alias.

    If *commands* is ``None``, uses the full built-in list.
    """
    if commands is None:
        commands = get_all_commands()

    for cmd in commands:
        if (
            cmd.name == command_name
            or get_command_name(cmd) == command_name
            or command_name in cmd.aliases
        ):
            return cmd
    return None


def has_command(
    command_name: str,
    commands: Sequence[Command] | None = None,
) -> bool:
    """Boolean check: does a command with this name exist?"""
    return find_command(command_name, commands) is not None


def get_command(
    command_name: str,
    commands: Sequence[Command] | None = None,
) -> Command:
    """
    Strict lookup — raises ``ReferenceError`` when the command is missing.
    """
    cmd = find_command(command_name, commands)
    if cmd is None:
        if commands is None:
            commands = get_all_commands()
        available = sorted(
            (
                f"{get_command_name(c)} (aliases: {', '.join(c.aliases)})"
                if c.aliases
                else get_command_name(c)
            )
            for c in commands
        )
        raise ReferenceError(
            f"Command {command_name!r} not found.  "
            f"Available commands: {', '.join(available)}"
        )
    return cmd


# ---------------------------------------------------------------------------
# Description formatting (for typeahead / help screens)
# ---------------------------------------------------------------------------

def format_description_with_source(cmd: Command) -> str:
    """
    Format a command's description with its source annotation.

    For model-facing prompts (like SkillTool), use ``cmd.description`` directly.
    """
    if cmd.type != CommandType.PROMPT:
        return cmd.description

    if isinstance(cmd, PromptCommand):
        if cmd.kind == "workflow":
            return f"{cmd.description} (workflow)"
        if cmd.source == CommandSource.PLUGIN:
            return f"{cmd.description} (plugin)"
        if cmd.source in (CommandSource.BUILTIN, CommandSource.MCP):
            return cmd.description
        if cmd.source == CommandSource.BUNDLED:
            return f"{cmd.description} (bundled)"
        return f"{cmd.description} ({cmd.source.value})"

    return cmd.description
