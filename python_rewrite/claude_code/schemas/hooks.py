"""
Hook configuration schemas using Pydantic.

This module defines the schema for hook configurations that allow users to
run custom commands, prompts, or agents at specific points in the CLI
lifecycle.  It replaces the Zod-based schemas from the TypeScript version.

Hook types:
    - ``BashCommandHook``: Shell command to execute
    - ``PromptHook``: LLM prompt to evaluate
    - ``AgentHook``: Agentic verifier (runs a sub-agent)
    - ``HttpHook``: HTTP POST webhook

Each hook type supports:
    - ``if_condition``: Permission rule syntax filter (e.g. ``"Bash(git *)"``).
    - ``timeout``: Per-hook timeout in seconds.
    - ``status_message``: Custom spinner text while running.
    - ``once``: Run once then auto-remove.

The ``HooksSchema`` is the top-level mapping from hook event names to lists
of ``HookMatcher`` objects, each pairing a string matcher pattern with a
list of hooks to execute.

All hook events are defined in ``HOOK_EVENTS``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, HttpUrl


# ---------------------------------------------------------------------------
# Hook event names
# ---------------------------------------------------------------------------

HOOK_EVENTS: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
    "SubagentStop",
    "PreCompact",
)

HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "Notification",
    "Stop",
    "SubagentStop",
    "PreCompact",
]

# ---------------------------------------------------------------------------
# Shell types
# ---------------------------------------------------------------------------

SHELL_TYPES: tuple[str, ...] = ("bash", "powershell")

ShellType = Literal["bash", "powershell"]


# ---------------------------------------------------------------------------
# Individual hook schemas
# ---------------------------------------------------------------------------

class BashCommandHook(BaseModel):
    """Shell command hook.

    Executes a shell command when the hook event fires.

    Attributes:
        type: Discriminator -- always ``"command"``.
        command: Shell command to execute.
        if_condition: Permission rule syntax filter (e.g. ``"Bash(git *)"``).
            Only runs if the tool call matches the pattern.
        shell: Shell interpreter.  ``"bash"`` uses ``$SHELL`` (bash/zsh/sh);
            ``"powershell"`` uses ``pwsh``.  Defaults to bash.
        timeout: Timeout in seconds for this specific command.
        status_message: Custom spinner text while hook runs.
        once: If ``True``, hook runs once and is removed after execution.
        async_exec: If ``True``, hook runs in background without blocking.
        async_rewake: If ``True``, hook runs in background and wakes the
            model on exit code 2 (blocking error).  Implies async.
    """
    type: Literal["command"] = "command"
    command: str = Field(
        ..., description="Shell command to execute"
    )
    if_condition: str | None = Field(
        None,
        alias="if",
        description=(
            'Permission rule syntax to filter when this hook runs '
            '(e.g., "Bash(git *)"). Only runs if the tool call matches '
            'the pattern.'
        ),
    )
    shell: ShellType | None = Field(
        None,
        description=(
            "Shell interpreter. 'bash' uses your $SHELL (bash/zsh/sh); "
            "'powershell' uses pwsh. Defaults to bash."
        ),
    )
    timeout: float | None = Field(
        None,
        gt=0,
        description="Timeout in seconds for this specific command",
    )
    status_message: str | None = Field(
        None,
        description="Custom status message to display in spinner while hook runs",
    )
    once: bool | None = Field(
        None,
        description="If true, hook runs once and is removed after execution",
    )
    async_exec: bool | None = Field(
        None,
        alias="async",
        description="If true, hook runs in background without blocking",
    )
    async_rewake: bool | None = Field(
        None,
        alias="asyncRewake",
        description=(
            "If true, hook runs in background and wakes the model on exit "
            "code 2 (blocking error). Implies async."
        ),
    )

    model_config = {"populate_by_name": True}


class PromptHook(BaseModel):
    """LLM prompt hook.

    Evaluates a prompt with an LLM when the hook event fires.

    Attributes:
        type: Discriminator -- always ``"prompt"``.
        prompt: Prompt to evaluate.  Use ``$ARGUMENTS`` placeholder for
            hook input JSON.
        if_condition: Permission rule syntax filter.
        timeout: Timeout in seconds.
        model: Model to use (e.g. ``"claude-sonnet-4-6"``).
            Defaults to the small fast model.
        status_message: Custom spinner text.
        once: If ``True``, hook runs once and is removed.
    """
    type: Literal["prompt"] = "prompt"
    prompt: str = Field(
        ...,
        description=(
            "Prompt to evaluate with LLM. Use $ARGUMENTS placeholder "
            "for hook input JSON."
        ),
    )
    if_condition: str | None = Field(
        None,
        alias="if",
        description=(
            'Permission rule syntax to filter when this hook runs '
            '(e.g., "Bash(git *)").'
        ),
    )
    timeout: float | None = Field(
        None,
        gt=0,
        description="Timeout in seconds for this specific prompt evaluation",
    )
    model: str | None = Field(
        None,
        description=(
            'Model to use for this prompt hook (e.g., "claude-sonnet-4-6"). '
            "If not specified, uses the default small fast model."
        ),
    )
    status_message: str | None = Field(
        None,
        description="Custom status message to display in spinner while hook runs",
    )
    once: bool | None = Field(
        None,
        description="If true, hook runs once and is removed after execution",
    )

    model_config = {"populate_by_name": True}


class AgentHook(BaseModel):
    """Agentic verifier hook.

    Runs a sub-agent to verify or act on the hook event.

    Attributes:
        type: Discriminator -- always ``"agent"``.
        prompt: Description of what to verify (e.g. ``"Verify that unit
            tests ran and passed."``).  Use ``$ARGUMENTS`` placeholder for
            hook input JSON.
        if_condition: Permission rule syntax filter.
        timeout: Timeout in seconds (default 60).
        model: Model to use (e.g. ``"claude-sonnet-4-6"``).
            Defaults to Haiku.
        status_message: Custom spinner text.
        once: If ``True``, hook runs once and is removed.
    """
    type: Literal["agent"] = "agent"
    prompt: str = Field(
        ...,
        description=(
            "Prompt describing what to verify (e.g., 'Verify that unit "
            "tests ran and passed.'). Use $ARGUMENTS placeholder for "
            "hook input JSON."
        ),
    )
    if_condition: str | None = Field(
        None,
        alias="if",
        description=(
            'Permission rule syntax to filter when this hook runs '
            '(e.g., "Bash(git *)").'
        ),
    )
    timeout: float | None = Field(
        None,
        gt=0,
        description="Timeout in seconds for agent execution (default 60)",
    )
    model: str | None = Field(
        None,
        description=(
            'Model to use for this agent hook (e.g., "claude-sonnet-4-6"). '
            "If not specified, uses Haiku."
        ),
    )
    status_message: str | None = Field(
        None,
        description="Custom status message to display in spinner while hook runs",
    )
    once: bool | None = Field(
        None,
        description="If true, hook runs once and is removed after execution",
    )

    model_config = {"populate_by_name": True}


class HttpHook(BaseModel):
    """HTTP webhook hook.

    Sends a POST request to a URL when the hook event fires.

    Attributes:
        type: Discriminator -- always ``"http"``.
        url: URL to POST the hook input JSON to.
        if_condition: Permission rule syntax filter.
        timeout: Timeout in seconds.
        headers: Additional HTTP headers.  Values may reference env vars
            using ``$VAR_NAME`` or ``${VAR_NAME}`` syntax (only variables
            listed in ``allowed_env_vars`` will be interpolated).
        allowed_env_vars: Explicit list of env var names that may be
            interpolated in header values.
        status_message: Custom spinner text.
        once: If ``True``, hook runs once and is removed.
    """
    type: Literal["http"] = "http"
    url: str = Field(
        ..., description="URL to POST the hook input JSON to"
    )
    if_condition: str | None = Field(
        None,
        alias="if",
        description=(
            'Permission rule syntax to filter when this hook runs '
            '(e.g., "Bash(git *)").'
        ),
    )
    timeout: float | None = Field(
        None,
        gt=0,
        description="Timeout in seconds for this specific request",
    )
    headers: dict[str, str] | None = Field(
        None,
        description=(
            "Additional headers to include in the request. Values may "
            "reference environment variables using $VAR_NAME or ${VAR_NAME} "
            "syntax. Only variables listed in allowedEnvVars will be "
            "interpolated."
        ),
    )
    allowed_env_vars: list[str] | None = Field(
        None,
        alias="allowedEnvVars",
        description=(
            "Explicit list of environment variable names that may be "
            "interpolated in header values. Only variables listed here will "
            "be resolved; all other $VAR references are left as empty strings."
        ),
    )
    status_message: str | None = Field(
        None,
        description="Custom status message to display in spinner while hook runs",
    )
    once: bool | None = Field(
        None,
        description="If true, hook runs once and is removed after execution",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Discriminated union of all hook types
# ---------------------------------------------------------------------------

HookCommand = Annotated[
    Union[BashCommandHook, PromptHook, AgentHook, HttpHook],
    Field(discriminator="type"),
]
"""Discriminated union of all persistable hook types.

The ``type`` field is the discriminator:
    - ``"command"`` -> ``BashCommandHook``
    - ``"prompt"``  -> ``PromptHook``
    - ``"agent"``   -> ``AgentHook``
    - ``"http"``    -> ``HttpHook``
"""


# ---------------------------------------------------------------------------
# HookMatcher -- pairs a string pattern with a list of hooks
# ---------------------------------------------------------------------------

class HookMatcher(BaseModel):
    """Matcher configuration with multiple hooks.

    Attributes:
        matcher: String pattern to match (e.g. tool names like ``"Write"``).
        hooks: List of hooks to execute when the matcher matches.
    """
    matcher: str | None = Field(
        None,
        description='String pattern to match (e.g. tool names like "Write")',
    )
    hooks: list[
        Annotated[
            Union[BashCommandHook, PromptHook, AgentHook, HttpHook],
            Field(discriminator="type"),
        ]
    ] = Field(
        ...,
        description="List of hooks to execute when the matcher matches",
    )


# ---------------------------------------------------------------------------
# HooksSchema -- top-level hooks configuration
# ---------------------------------------------------------------------------

# The key is the hook event name; the value is a list of HookMatcher objects.
HooksSchema = dict[HookEvent, list[HookMatcher]]
"""Top-level hooks configuration.

Maps hook event names to lists of ``HookMatcher`` objects::

    {
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[BashCommandHook(...)]),
        ],
        "Stop": [
            HookMatcher(hooks=[PromptHook(...)]),
        ],
    }
"""


# ---------------------------------------------------------------------------
# Convenience type aliases (matching TS exports)
# ---------------------------------------------------------------------------

HooksSettings = dict[HookEvent, list[HookMatcher]]
"""Type alias for partial hook settings (same shape as HooksSchema)."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_hooks_config(data: dict[str, Any]) -> HooksSchema:
    """Validate a raw dict as a hooks configuration.

    Raises ``pydantic.ValidationError`` if the data doesn't match the schema.
    """
    result: HooksSchema = {}
    for event_name, matchers_data in data.items():
        if event_name not in HOOK_EVENTS:
            continue  # Skip unknown events (forward compat)
        matchers: list[HookMatcher] = []
        for matcher_data in matchers_data:
            matchers.append(HookMatcher.model_validate(matcher_data))
        result[event_name] = matchers  # type: ignore[assignment]
    return result


def hooks_to_dict(hooks: HooksSchema) -> dict[str, Any]:
    """Serialize a hooks config to a plain dict for JSON serialization."""
    return {
        event: [m.model_dump(by_alias=True, exclude_none=True) for m in matchers]
        for event, matchers in hooks.items()
    }


__all__ = [
    "AgentHook",
    "BashCommandHook",
    "HOOK_EVENTS",
    "HookCommand",
    "HookEvent",
    "HookMatcher",
    "HooksSchema",
    "HooksSettings",
    "HttpHook",
    "PromptHook",
    "SHELL_TYPES",
    "ShellType",
    "hooks_to_dict",
    "validate_hooks_config",
]
