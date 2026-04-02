"""
Command type definitions for the Claude Code slash-command system.

Commands are discriminated by the ``type`` field:
  - ``"prompt"`` — a prompt-based command (skills, MCP)
  - ``"local"`` — a local text-returning command
  - ``"local_jsx"`` — a local command producing rich output (originally JSX)
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Literal, Union

from pydantic import BaseModel, Field

__all__ = [
    # Types
    "CommandType",
    "CommandAvailability",
    "CommandResultDisplay",
    "ResumeEntrypoint",
    # Models
    "CommandBase",
    "PromptCommand",
    "LocalCommand",
    "LocalJSXCommand",
    "Command",
    "LocalCommandResultText",
    "LocalCommandResultCompact",
    "LocalCommandResultSkip",
    "LocalCommandResult",
    # Helpers
    "get_command_name",
    "is_command_enabled",
]

# ============================================================================
# Scalar / literal types
# ============================================================================

CommandType = Literal["prompt", "local", "local_jsx"]

CommandAvailability = Literal["claude-ai", "console"]
"""Auth / provider environments a command is available in."""

CommandResultDisplay = Literal["skip", "system", "user"]

ResumeEntrypoint = Literal[
    "cli_flag",
    "slash_command_picker",
    "slash_command_session_id",
    "slash_command_title",
    "fork",
]

# ============================================================================
# Local command results
# ============================================================================


class LocalCommandResultText(BaseModel):
    """Simple text result from a local command."""

    type: Literal["text"] = "text"
    value: str


class LocalCommandResultCompact(BaseModel):
    """Compaction result from a local command."""

    type: Literal["compact"] = "compact"
    compaction_result: Any = Field(alias="compactionResult")
    display_text: str | None = Field(default=None, alias="displayText")

    model_config = {"populate_by_name": True}


class LocalCommandResultSkip(BaseModel):
    """Skip / no-op result from a local command."""

    type: Literal["skip"] = "skip"


LocalCommandResult = Union[
    LocalCommandResultText,
    LocalCommandResultCompact,
    LocalCommandResultSkip,
]

# ============================================================================
# Command base & variants
# ============================================================================


class CommandBase(BaseModel):
    """Fields shared by all command types.

    ``is_enabled`` and ``user_facing_name`` are callables evaluated at runtime;
    they are stored as plain functions rather than Pydantic-validated fields.
    """

    name: str
    description: str
    has_user_specified_description: bool | None = Field(
        default=None, alias="hasUserSpecifiedDescription"
    )
    is_hidden: bool | None = Field(default=None, alias="isHidden")
    aliases: list[str] | None = None
    is_mcp: bool | None = Field(default=None, alias="isMcp")
    argument_hint: str | None = Field(default=None, alias="argumentHint")
    """Hint text for command arguments (displayed in gray after command)."""
    when_to_use: str | None = Field(default=None, alias="whenToUse")
    """Detailed usage scenarios for when to use this command."""
    version: str | None = None
    disable_model_invocation: bool | None = Field(
        default=None, alias="disableModelInvocation"
    )
    """Whether to disable this command from being invoked by models."""
    user_invocable: bool | None = Field(default=None, alias="userInvocable")
    """Whether users can invoke this skill by typing /skill-name."""
    loaded_from: (
        Literal["commands_DEPRECATED", "skills", "plugin", "managed", "bundled", "mcp"]
        | None
    ) = Field(default=None, alias="loadedFrom")
    kind: Literal["workflow"] | None = None
    """Distinguishes workflow-backed commands."""
    immediate: bool | None = None
    """If true, command executes immediately without waiting for a stop point."""
    is_sensitive: bool | None = Field(default=None, alias="isSensitive")
    """If true, args are redacted from the conversation history."""
    availability: list[CommandAvailability] | None = None

    model_config = {"populate_by_name": True}


class PromptCommand(CommandBase):
    """A prompt-based command (skill, MCP tool, etc.)."""

    type: Literal["prompt"] = "prompt"
    progress_message: str = Field(alias="progressMessage")
    content_length: int = Field(alias="contentLength")
    """Length of command content in characters (used for token estimation)."""
    arg_names: list[str] | None = Field(default=None, alias="argNames")
    allowed_tools: list[str] | None = Field(default=None, alias="allowedTools")
    model: str | None = None
    source: Literal[
        "userSettings",
        "projectSettings",
        "localSettings",
        "flagSettings",
        "policySettings",
        "builtin",
        "mcp",
        "plugin",
        "bundled",
    ]
    plugin_info: dict[str, Any] | None = Field(default=None, alias="pluginInfo")
    disable_non_interactive: bool | None = Field(
        default=None, alias="disableNonInteractive"
    )
    hooks: dict[str, Any] | None = None
    """Hooks to register when this skill is invoked."""
    skill_root: str | None = Field(default=None, alias="skillRoot")
    """Base directory for skill resources."""
    context: Literal["inline", "fork"] | None = None
    """Execution context: 'inline' (default) or 'fork' (run as sub-agent)."""
    agent: str | None = None
    """Agent type to use when forked."""
    effort: str | None = None
    paths: list[str] | None = None
    """Glob patterns for file paths this skill applies to."""


class LocalCommand(CommandBase):
    """A local text-returning command."""

    type: Literal["local"] = "local"
    supports_non_interactive: bool = Field(alias="supportsNonInteractive")

    model_config = {"populate_by_name": True}


class LocalJSXCommand(CommandBase):
    """A local command producing rich (originally JSX) output."""

    type: Literal["local_jsx"] = Field(default="local_jsx", alias="local-jsx")

    model_config = {"populate_by_name": True}


Command = Union[PromptCommand, LocalCommand, LocalJSXCommand]
"""Discriminated union of all command types."""

# ============================================================================
# Helper functions
# ============================================================================


def get_command_name(cmd: CommandBase) -> str:
    """Resolve the user-visible name, falling back to ``cmd.name``."""
    return cmd.name


def is_command_enabled(cmd: CommandBase) -> bool:
    """Resolve whether the command is enabled, defaulting to ``True``."""
    return True
