"""
Hook type definitions for the Claude Code hook system.

Covers hook events, callbacks, results, prompt elicitation, and
the JSON schemas that hook processes produce.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from .permissions import PermissionBehavior, PermissionUpdate

__all__ = [
    # Events
    "HookEvent",
    "HOOK_EVENTS",
    "is_hook_event",
    # Callbacks
    "HookCallback",
    "HookCallbackMatcher",
    # Prompt elicitation
    "PromptRequestOption",
    "PromptRequest",
    "PromptResponse",
    # Progress
    "HookProgress",
    "HookBlockingError",
    # Results
    "PermissionRequestResult",
    "PermissionRequestResultAllow",
    "PermissionRequestResultDeny",
    "HookResult",
    "AggregatedHookResult",
    # JSON output schemas
    "SyncHookJSONOutput",
    "AsyncHookJSONOutput",
    "HookJSONOutput",
    "is_sync_hook_json_output",
    "is_async_hook_json_output",
    # Hook-specific output variants
    "PreToolUseHookOutput",
    "UserPromptSubmitHookOutput",
    "SessionStartHookOutput",
    "SetupHookOutput",
    "SubagentStartHookOutput",
    "PostToolUseHookOutput",
    "PostToolUseFailureHookOutput",
    "PermissionDeniedHookOutput",
    "NotificationHookOutput",
    "PermissionRequestHookOutput",
    "ElicitationHookOutput",
    "ElicitationResultHookOutput",
    "CwdChangedHookOutput",
    "FileChangedHookOutput",
    "WorktreeCreateHookOutput",
    "HookSpecificOutput",
]

# ============================================================================
# Hook Events
# ============================================================================

HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
]

HOOK_EVENTS: tuple[HookEvent, ...] = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "StopFailure",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "PermissionRequest",
    "PermissionDenied",
    "Setup",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "Elicitation",
    "ElicitationResult",
    "ConfigChange",
    "WorktreeCreate",
    "WorktreeRemove",
    "InstructionsLoaded",
    "CwdChanged",
    "FileChanged",
)


def is_hook_event(value: str) -> bool:
    """Check if *value* is a valid hook event name."""
    return value in HOOK_EVENTS


# ============================================================================
# Prompt Elicitation Protocol
# ============================================================================


class PromptRequestOption(BaseModel):
    """A single option in a prompt elicitation request."""

    key: str
    label: str
    description: str | None = None


class PromptRequest(BaseModel):
    """Prompt elicitation request from a hook process.

    The ``prompt`` field doubles as the request ID.
    """

    prompt: str
    """Request ID."""
    message: str
    options: list[PromptRequestOption]


class PromptResponse(BaseModel):
    """Response to a prompt elicitation request."""

    prompt_response: str
    """Request ID (echoed back)."""
    selected: str


# ============================================================================
# Hook-Specific Output Variants
# ============================================================================


class PreToolUseHookOutput(BaseModel):
    """Hook-specific output for ``PreToolUse`` events."""

    hook_event_name: Literal["PreToolUse"] = Field(alias="hookEventName")
    permission_decision: PermissionBehavior | None = Field(
        default=None, alias="permissionDecision"
    )
    permission_decision_reason: str | None = Field(
        default=None, alias="permissionDecisionReason"
    )
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class UserPromptSubmitHookOutput(BaseModel):
    """Hook-specific output for ``UserPromptSubmit`` events."""

    hook_event_name: Literal["UserPromptSubmit"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class SessionStartHookOutput(BaseModel):
    """Hook-specific output for ``SessionStart`` events."""

    hook_event_name: Literal["SessionStart"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")
    initial_user_message: str | None = Field(
        default=None, alias="initialUserMessage"
    )
    watch_paths: list[str] | None = Field(
        default=None,
        alias="watchPaths",
        description="Absolute paths to watch for FileChanged hooks",
    )

    model_config = {"populate_by_name": True}


class SetupHookOutput(BaseModel):
    """Hook-specific output for ``Setup`` events."""

    hook_event_name: Literal["Setup"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class SubagentStartHookOutput(BaseModel):
    """Hook-specific output for ``SubagentStart`` events."""

    hook_event_name: Literal["SubagentStart"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class PostToolUseHookOutput(BaseModel):
    """Hook-specific output for ``PostToolUse`` events."""

    hook_event_name: Literal["PostToolUse"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")
    updated_mcp_tool_output: Any | None = Field(
        default=None,
        alias="updatedMCPToolOutput",
        description="Updates the output for MCP tools",
    )

    model_config = {"populate_by_name": True}


class PostToolUseFailureHookOutput(BaseModel):
    """Hook-specific output for ``PostToolUseFailure`` events."""

    hook_event_name: Literal["PostToolUseFailure"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class PermissionDeniedHookOutput(BaseModel):
    """Hook-specific output for ``PermissionDenied`` events."""

    hook_event_name: Literal["PermissionDenied"] = Field(alias="hookEventName")
    retry: bool | None = None

    model_config = {"populate_by_name": True}


class NotificationHookOutput(BaseModel):
    """Hook-specific output for ``Notification`` events."""

    hook_event_name: Literal["Notification"] = Field(alias="hookEventName")
    additional_context: str | None = Field(default=None, alias="additionalContext")

    model_config = {"populate_by_name": True}


class _PermissionRequestDecisionAllow(BaseModel):
    """Allow decision within a PermissionRequest hook output."""

    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    updated_permissions: list[PermissionUpdate] | None = Field(
        default=None, alias="updatedPermissions"
    )

    model_config = {"populate_by_name": True}


class _PermissionRequestDecisionDeny(BaseModel):
    """Deny decision within a PermissionRequest hook output."""

    behavior: Literal["deny"] = "deny"
    message: str | None = None
    interrupt: bool | None = None


class PermissionRequestHookOutput(BaseModel):
    """Hook-specific output for ``PermissionRequest`` events."""

    hook_event_name: Literal["PermissionRequest"] = Field(alias="hookEventName")
    decision: _PermissionRequestDecisionAllow | _PermissionRequestDecisionDeny

    model_config = {"populate_by_name": True}


class ElicitationHookOutput(BaseModel):
    """Hook-specific output for ``Elicitation`` events."""

    hook_event_name: Literal["Elicitation"] = Field(alias="hookEventName")
    action: Literal["accept", "decline", "cancel"] | None = None
    content: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class ElicitationResultHookOutput(BaseModel):
    """Hook-specific output for ``ElicitationResult`` events."""

    hook_event_name: Literal["ElicitationResult"] = Field(alias="hookEventName")
    action: Literal["accept", "decline", "cancel"] | None = None
    content: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class CwdChangedHookOutput(BaseModel):
    """Hook-specific output for ``CwdChanged`` events."""

    hook_event_name: Literal["CwdChanged"] = Field(alias="hookEventName")
    watch_paths: list[str] | None = Field(
        default=None,
        alias="watchPaths",
        description="Absolute paths to watch for FileChanged hooks",
    )

    model_config = {"populate_by_name": True}


class FileChangedHookOutput(BaseModel):
    """Hook-specific output for ``FileChanged`` events."""

    hook_event_name: Literal["FileChanged"] = Field(alias="hookEventName")
    watch_paths: list[str] | None = Field(
        default=None,
        alias="watchPaths",
        description="Absolute paths to watch for FileChanged hooks",
    )

    model_config = {"populate_by_name": True}


class WorktreeCreateHookOutput(BaseModel):
    """Hook-specific output for ``WorktreeCreate`` events."""

    hook_event_name: Literal["WorktreeCreate"] = Field(alias="hookEventName")
    worktree_path: str = Field(alias="worktreePath")

    model_config = {"populate_by_name": True}


HookSpecificOutput = Union[
    PreToolUseHookOutput,
    UserPromptSubmitHookOutput,
    SessionStartHookOutput,
    SetupHookOutput,
    SubagentStartHookOutput,
    PostToolUseHookOutput,
    PostToolUseFailureHookOutput,
    PermissionDeniedHookOutput,
    NotificationHookOutput,
    PermissionRequestHookOutput,
    ElicitationHookOutput,
    ElicitationResultHookOutput,
    CwdChangedHookOutput,
    FileChangedHookOutput,
    WorktreeCreateHookOutput,
]
"""Union of all hook-specific output types."""

# ============================================================================
# Hook JSON Output (sync / async)
# ============================================================================


class SyncHookJSONOutput(BaseModel):
    """Synchronous hook response JSON schema."""

    continue_: bool | None = Field(
        default=None,
        alias="continue",
        description="Whether Claude should continue after hook (default: true)",
    )
    suppress_output: bool | None = Field(
        default=None,
        alias="suppressOutput",
        description="Hide stdout from transcript (default: false)",
    )
    stop_reason: str | None = Field(
        default=None,
        alias="stopReason",
        description="Message shown when continue is false",
    )
    decision: Literal["approve", "block"] | None = None
    reason: str | None = Field(
        default=None, description="Explanation for the decision"
    )
    system_message: str | None = Field(
        default=None,
        alias="systemMessage",
        description="Warning message shown to the user",
    )
    hook_specific_output: HookSpecificOutput | None = Field(
        default=None, alias="hookSpecificOutput"
    )

    model_config = {"populate_by_name": True}


class AsyncHookJSONOutput(BaseModel):
    """Asynchronous hook response — tells the system to wait."""

    async_: Literal[True] = Field(alias="async")
    async_timeout: float | None = Field(default=None, alias="asyncTimeout")

    model_config = {"populate_by_name": True}


HookJSONOutput = SyncHookJSONOutput | AsyncHookJSONOutput
"""Union of sync and async hook JSON outputs."""


def is_sync_hook_json_output(json: HookJSONOutput) -> bool:
    """Type guard: is the hook output synchronous?"""
    return not isinstance(json, AsyncHookJSONOutput)


def is_async_hook_json_output(json: HookJSONOutput) -> bool:
    """Type guard: is the hook output asynchronous?"""
    return isinstance(json, AsyncHookJSONOutput)


# ============================================================================
# Hook Callbacks (runtime types — not Pydantic models)
# ============================================================================


class HookCallback(BaseModel):
    """Hook configuration for a callback-based hook.

    In the Python rewrite, the actual callable is injected at runtime.
    This model holds the serialisable metadata.
    """

    type: Literal["callback"] = "callback"
    timeout: float | None = None
    """Timeout in seconds for this hook."""
    internal: bool | None = None
    """Internal hooks are excluded from tengu_run_hook metrics."""

    model_config = {"populate_by_name": True}


class HookCallbackMatcher(BaseModel):
    """A matcher for routing hook events to callbacks."""

    matcher: str | None = None
    hooks: list[HookCallback]
    plugin_name: str | None = Field(default=None, alias="pluginName")

    model_config = {"populate_by_name": True}


# ============================================================================
# Progress / Errors
# ============================================================================


class HookProgress(BaseModel):
    """Progress report from a running hook."""

    type: Literal["hook_progress"] = "hook_progress"
    hook_event: HookEvent = Field(alias="hookEvent")
    hook_name: str = Field(alias="hookName")
    command: str
    prompt_text: str | None = Field(default=None, alias="promptText")
    status_message: str | None = Field(default=None, alias="statusMessage")

    model_config = {"populate_by_name": True}


class HookBlockingError(BaseModel):
    """Error that blocks further processing."""

    blocking_error: str = Field(alias="blockingError")
    command: str

    model_config = {"populate_by_name": True}


# ============================================================================
# Permission Request Results (from hooks)
# ============================================================================


class PermissionRequestResultAllow(BaseModel):
    """Permission request hook result — allow."""

    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    updated_permissions: list[PermissionUpdate] | None = Field(
        default=None, alias="updatedPermissions"
    )

    model_config = {"populate_by_name": True}


class PermissionRequestResultDeny(BaseModel):
    """Permission request hook result — deny."""

    behavior: Literal["deny"] = "deny"
    message: str | None = None
    interrupt: bool | None = None


PermissionRequestResult = PermissionRequestResultAllow | PermissionRequestResultDeny
"""Union of permission request results from hooks."""

# ============================================================================
# Hook Results
# ============================================================================


class HookResult(BaseModel):
    """Result of executing a single hook."""

    message: Any | None = None
    """Optional Message to inject into conversation."""
    system_message: Any | None = Field(default=None, alias="systemMessage")
    blocking_error: HookBlockingError | None = Field(
        default=None, alias="blockingError"
    )
    outcome: Literal["success", "blocking", "non_blocking_error", "cancelled"]
    prevent_continuation: bool | None = Field(
        default=None, alias="preventContinuation"
    )
    stop_reason: str | None = Field(default=None, alias="stopReason")
    permission_behavior: Literal["ask", "deny", "allow", "passthrough"] | None = Field(
        default=None, alias="permissionBehavior"
    )
    hook_permission_decision_reason: str | None = Field(
        default=None, alias="hookPermissionDecisionReason"
    )
    additional_context: str | None = Field(default=None, alias="additionalContext")
    initial_user_message: str | None = Field(
        default=None, alias="initialUserMessage"
    )
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    updated_mcp_tool_output: Any | None = Field(
        default=None, alias="updatedMCPToolOutput"
    )
    permission_request_result: PermissionRequestResult | None = Field(
        default=None, alias="permissionRequestResult"
    )
    retry: bool | None = None

    model_config = {"populate_by_name": True}


class AggregatedHookResult(BaseModel):
    """Aggregated result from multiple hook executions."""

    message: Any | None = None
    blocking_errors: list[HookBlockingError] | None = Field(
        default=None, alias="blockingErrors"
    )
    prevent_continuation: bool | None = Field(
        default=None, alias="preventContinuation"
    )
    stop_reason: str | None = Field(default=None, alias="stopReason")
    hook_permission_decision_reason: str | None = Field(
        default=None, alias="hookPermissionDecisionReason"
    )
    permission_behavior: (
        Literal["allow", "ask", "deny", "passthrough"] | None
    ) = Field(default=None, alias="permissionBehavior")
    additional_contexts: list[str] | None = Field(
        default=None, alias="additionalContexts"
    )
    initial_user_message: str | None = Field(
        default=None, alias="initialUserMessage"
    )
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    updated_mcp_tool_output: Any | None = Field(
        default=None, alias="updatedMCPToolOutput"
    )
    permission_request_result: PermissionRequestResult | None = Field(
        default=None, alias="permissionRequestResult"
    )
    retry: bool | None = None

    model_config = {"populate_by_name": True}
