"""
Message type definitions for the Claude Code conversation model.

Types are discriminated unions based on the ``.type`` field.
System messages are further discriminated by ``.subtype``.

This module is pure data — no runtime dependencies beyond Pydantic.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, Field

from .permissions import PermissionMode

__all__ = [
    # Scalar / enum-like
    "MessageOrigin",
    "PartialCompactDirection",
    "SystemMessageLevel",
    # Small models
    "StopHookInfo",
    "Progress",
    "ProgressMessage",
    # Core messages
    "AssistantMessage",
    "UserMessage",
    "UserMessageContent",
    # System messages
    "SystemMessageBase",
    "SystemInformationalMessage",
    "SystemAPIErrorMessage",
    "SystemLocalCommandMessage",
    "SystemStopHookSummaryMessage",
    "SystemBridgeStatusMessage",
    "SystemTurnDurationMessage",
    "SystemThinkingMessage",
    "SystemMemorySavedMessage",
    "SystemAwaySummaryMessage",
    "SystemAgentsKilledMessage",
    "SystemCompactBoundaryMessage",
    "SystemMicrocompactBoundaryMessage",
    "SystemPermissionRetryMessage",
    "SystemScheduledTaskFireMessage",
    "SystemApiMetricsMessage",
    "SystemMessage",
    # Other messages
    "AttachmentMessage",
    "TombstoneMessage",
    "ToolUseSummaryMessage",
    # Unions
    "Message",
    "RenderableMessage",
    "NormalizedMessage",
    # Grouped display
    "GroupedToolUseMessage",
    "CollapsedReadSearchGroup",
    # Normalized
    "NormalizedAssistantMessage",
    "NormalizedUserMessage",
    # Stream / event
    "StreamEvent",
    "RequestStartEvent",
]

# ============================================================================
# Scalar / Enum-like types
# ============================================================================

MessageOrigin = Literal["agent", "teammate", "command", "system", "hook"] | None
"""Where a message originated. ``None`` means the human typed it."""

PartialCompactDirection = Literal["earlier", "later"]
"""Direction for partial compact summarization."""

SystemMessageLevel = Literal["info", "warning", "error"]
"""System message severity levels."""

# ============================================================================
# Small helper models
# ============================================================================


class StopHookInfo(BaseModel):
    """Hook execution info for stop hooks."""

    hook_name: str = Field(alias="hookName")
    execution_time: float | None = Field(default=None, alias="executionTime")
    success: bool
    error: str | None = None

    model_config = {"populate_by_name": True}


# ============================================================================
# Progress
# ============================================================================


class Progress(BaseModel):
    """Generic progress data for ongoing tool operations."""

    type: str
    """Discriminator for the specific progress variant."""

    model_config = {"extra": "allow"}


P = TypeVar("P", bound=Progress)


class ProgressMessage(BaseModel, Generic[P]):
    """Progress message for streaming tool execution updates."""

    type: Literal["progress"] = "progress"
    data: P  # type: ignore[valid-type]
    tool_use_id: str = Field(alias="toolUseID")
    parent_tool_use_id: str = Field(alias="parentToolUseID")
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = {"populate_by_name": True}


# ============================================================================
# AssistantMessage
# ============================================================================


class AssistantMessage(BaseModel):
    """A message produced by the assistant / model.

    ``message`` carries the raw API response (``BetaMessage`` dict).
    """

    type: Literal["assistant"] = "assistant"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    message: dict[str, Any]
    """Raw Anthropic API BetaMessage dict."""
    request_id: str | None = Field(default=None, alias="requestId")
    is_meta: bool | None = Field(default=None, alias="isMeta")
    is_virtual: bool | None = Field(default=None, alias="isVirtual")
    is_api_error_message: bool | None = Field(default=None, alias="isApiErrorMessage")
    api_error: str | None = Field(default=None, alias="apiError")
    error: Any | None = None
    error_details: str | None = Field(default=None, alias="errorDetails")
    advisor_model: str | None = Field(default=None, alias="advisorModel")
    agent_id: str | None = Field(default=None, alias="agentId")
    """AgentId of the agent that produced this message."""
    caller: str | None = None
    """Caller info for debugging/display."""

    model_config = {"populate_by_name": True}


# ============================================================================
# UserMessage
# ============================================================================


class UserMessageContent(BaseModel):
    """The ``message`` payload inside a :class:`UserMessage`."""

    role: Literal["user"] = "user"
    content: str | list[dict[str, Any]]

    model_config = {"populate_by_name": True}


class SummarizeMetadata(BaseModel):
    """Metadata attached when a user message is a compact summary."""

    messages_summarized: int = Field(alias="messagesSummarized")
    user_context: str | None = Field(default=None, alias="userContext")
    direction: PartialCompactDirection | None = None

    model_config = {"populate_by_name": True}


class McpMeta(BaseModel):
    """Optional MCP metadata on user messages."""

    _meta: dict[str, Any] | None = None
    structured_content: dict[str, Any] | None = Field(
        default=None, alias="structuredContent"
    )

    model_config = {"populate_by_name": True}


class UserMessage(BaseModel):
    """A message from the user (human or injected)."""

    type: Literal["user"] = "user"
    message: UserMessageContent
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_meta: bool | None = Field(default=None, alias="isMeta")
    is_visible_in_transcript_only: bool | None = Field(
        default=None, alias="isVisibleInTranscriptOnly"
    )
    is_virtual: bool | None = Field(default=None, alias="isVirtual")
    is_compact_summary: bool | None = Field(default=None, alias="isCompactSummary")
    tool_use_result: Any | None = Field(default=None, alias="toolUseResult")
    mcp_meta: McpMeta | None = Field(default=None, alias="mcpMeta")
    image_paste_ids: list[int] | None = Field(default=None, alias="imagePasteIds")
    source_tool_assistant_uuid: str | None = Field(
        default=None, alias="sourceToolAssistantUUID"
    )
    permission_mode: PermissionMode | None = Field(
        default=None, alias="permissionMode"
    )
    summarize_metadata: SummarizeMetadata | None = Field(
        default=None, alias="summarizeMetadata"
    )
    origin: MessageOrigin = None

    model_config = {"populate_by_name": True}


# ============================================================================
# SystemMessage (base) + all subtypes
# ============================================================================


class SystemMessageBase(BaseModel):
    """Base fields shared by all system messages."""

    type: Literal["system"] = "system"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_meta: bool | None = Field(default=None, alias="isMeta")
    content: str | None = None
    level: SystemMessageLevel | None = None
    tool_use_id: str | None = Field(default=None, alias="toolUseID")

    model_config = {"populate_by_name": True}


class SystemInformationalMessage(SystemMessageBase):
    """A purely informational system message."""

    subtype: Literal["informational"] = "informational"
    content: str  # type: ignore[assignment]
    level: SystemMessageLevel  # type: ignore[assignment]
    prevent_continuation: bool | None = Field(
        default=None, alias="preventContinuation"
    )


class SystemAPIErrorMessage(SystemMessageBase):
    """System message for API errors with retry info."""

    subtype: Literal["api_error"] = "api_error"
    level: Literal["error"] = "error"  # type: ignore[assignment]
    error: dict[str, Any]
    """Serialised APIError from the Anthropic SDK."""
    cause: dict[str, Any] | None = None
    retry_in_ms: int = Field(alias="retryInMs")
    retry_attempt: int = Field(alias="retryAttempt")
    max_retries: int = Field(alias="maxRetries")


class SystemLocalCommandMessage(SystemMessageBase):
    """Result of a local slash-command."""

    subtype: Literal["local_command"] = "local_command"
    content: str  # type: ignore[assignment]


class SystemStopHookSummaryMessage(SystemMessageBase):
    """Summary of stop-hook execution."""

    subtype: Literal["stop_hook_summary"] = "stop_hook_summary"
    hook_count: int = Field(alias="hookCount")
    hook_infos: list[StopHookInfo] = Field(alias="hookInfos")
    hook_errors: list[str] = Field(alias="hookErrors")
    prevented_continuation: bool = Field(alias="preventedContinuation")
    stop_reason: str | None = Field(alias="stopReason")
    has_output: bool = Field(alias="hasOutput")
    level: SystemMessageLevel  # type: ignore[assignment]
    hook_label: str | None = Field(default=None, alias="hookLabel")
    total_duration_ms: float | None = Field(default=None, alias="totalDurationMs")


class SystemBridgeStatusMessage(SystemMessageBase):
    """Bridge connection status."""

    subtype: Literal["bridge_status"] = "bridge_status"
    content: str  # type: ignore[assignment]
    url: str
    upgrade_nudge: str | None = Field(default=None, alias="upgradeNudge")


class SystemTurnDurationMessage(SystemMessageBase):
    """Timing data for a completed turn."""

    subtype: Literal["turn_duration"] = "turn_duration"
    duration_ms: float = Field(alias="durationMs")
    budget_tokens: int | None = Field(default=None, alias="budgetTokens")
    budget_limit: int | None = Field(default=None, alias="budgetLimit")
    budget_nudges: int | None = Field(default=None, alias="budgetNudges")
    message_count: int | None = Field(default=None, alias="messageCount")


class SystemThinkingMessage(SystemMessageBase):
    """Exposed thinking content from the model."""

    subtype: Literal["thinking"] = "thinking"
    content: str  # type: ignore[assignment]


class SystemMemorySavedMessage(SystemMessageBase):
    """Notification that memory was written to CLAUDE.md files."""

    subtype: Literal["memory_saved"] = "memory_saved"
    written_paths: list[str] = Field(alias="writtenPaths")


class SystemAwaySummaryMessage(SystemMessageBase):
    """Summary shown when returning after being away."""

    subtype: Literal["away_summary"] = "away_summary"
    content: str  # type: ignore[assignment]


class SystemAgentsKilledMessage(SystemMessageBase):
    """Notification that agents were killed."""

    subtype: Literal["agents_killed"] = "agents_killed"


class CompactPreservedSegment(BaseModel):
    """Preserved segment boundaries for compact operations."""

    tail_uuid: str | None = Field(default=None, alias="tailUuid")
    head_uuid: str | None = Field(default=None, alias="headUuid")

    model_config = {"populate_by_name": True}


class CompactMetadata(BaseModel):
    """Metadata about a compaction operation."""

    trigger: Literal["manual", "auto"]
    pre_tokens: int = Field(alias="preTokens")
    user_context: str | None = Field(default=None, alias="userContext")
    messages_summarized: int | None = Field(default=None, alias="messagesSummarized")
    preserved_segment: CompactPreservedSegment | None = Field(
        default=None, alias="preservedSegment"
    )

    model_config = {"populate_by_name": True}


class SystemCompactBoundaryMessage(SystemMessageBase):
    """Boundary marker for a compact summarization."""

    subtype: Literal["compact_boundary"] = "compact_boundary"
    content: str  # type: ignore[assignment]
    compact_metadata: CompactMetadata | None = Field(
        default=None, alias="compactMetadata"
    )
    logical_parent_uuid: str | None = Field(default=None, alias="logicalParentUuid")


class MicrocompactMetadata(BaseModel):
    """Metadata about a microcompact operation."""

    trigger: Literal["auto"] = "auto"
    pre_tokens: int = Field(alias="preTokens")
    tokens_saved: int = Field(alias="tokensSaved")
    compacted_tool_ids: list[str] = Field(alias="compactedToolIds")
    cleared_attachment_uuids: list[str] = Field(alias="clearedAttachmentUUIDs")

    model_config = {"populate_by_name": True}


class SystemMicrocompactBoundaryMessage(SystemMessageBase):
    """Boundary marker for a microcompact operation."""

    subtype: Literal["microcompact_boundary"] = "microcompact_boundary"
    content: str  # type: ignore[assignment]
    microcompact_metadata: MicrocompactMetadata | None = Field(
        default=None, alias="microcompactMetadata"
    )


class SystemPermissionRetryMessage(SystemMessageBase):
    """Permission retry suggestion with commands."""

    subtype: Literal["permission_retry"] = "permission_retry"
    content: str  # type: ignore[assignment]
    commands: list[str]


class SystemScheduledTaskFireMessage(SystemMessageBase):
    """Notification that a scheduled task fired."""

    subtype: Literal["scheduled_task_fire"] = "scheduled_task_fire"
    content: str  # type: ignore[assignment]


class SystemApiMetricsMessage(SystemMessageBase):
    """API performance metrics for a completed request."""

    subtype: Literal["api_metrics"] = "api_metrics"
    ttft_ms: float = Field(alias="ttftMs")
    """Time to first token in milliseconds."""
    otps: float
    """Output tokens per second."""
    is_p50: bool | None = Field(default=None, alias="isP50")
    hook_duration_ms: float | None = Field(default=None, alias="hookDurationMs")
    turn_duration_ms: float | None = Field(default=None, alias="turnDurationMs")
    tool_duration_ms: float | None = Field(default=None, alias="toolDurationMs")
    classifier_duration_ms: float | None = Field(
        default=None, alias="classifierDurationMs"
    )
    tool_count: int | None = Field(default=None, alias="toolCount")
    hook_count: int | None = Field(default=None, alias="hookCount")
    classifier_count: int | None = Field(default=None, alias="classifierCount")
    config_write_count: int | None = Field(default=None, alias="configWriteCount")


# Discriminated union of all system message subtypes.
SystemMessage = (
    SystemInformationalMessage
    | SystemAPIErrorMessage
    | SystemLocalCommandMessage
    | SystemStopHookSummaryMessage
    | SystemBridgeStatusMessage
    | SystemTurnDurationMessage
    | SystemThinkingMessage
    | SystemMemorySavedMessage
    | SystemAwaySummaryMessage
    | SystemAgentsKilledMessage
    | SystemCompactBoundaryMessage
    | SystemMicrocompactBoundaryMessage
    | SystemPermissionRetryMessage
    | SystemScheduledTaskFireMessage
    | SystemApiMetricsMessage
)

# ============================================================================
# AttachmentMessage
# ============================================================================


class AttachmentMessage(BaseModel):
    """An attachment carried alongside the conversation."""

    type: Literal["attachment"] = "attachment"
    attachment: dict[str, Any]
    """Must include a ``type`` key at minimum."""
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    is_meta: bool | None = Field(default=None, alias="isMeta")

    model_config = {"populate_by_name": True}


# ============================================================================
# TombstoneMessage
# ============================================================================


class TombstoneMessage(BaseModel):
    """A placeholder for a deleted message."""

    type: Literal["tombstone"] = "tombstone"
    original_type: Literal["assistant", "user", "system"] = Field(alias="originalType")
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = {"populate_by_name": True}


# ============================================================================
# ToolUseSummaryMessage
# ============================================================================


class ToolUseSummaryMessage(BaseModel):
    """A collapsed summary of multiple tool uses."""

    type: Literal["tool_use_summary"] = "tool_use_summary"
    summary: str
    preceding_tool_use_ids: list[str] = Field(alias="precedingToolUseIds")
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    model_config = {"populate_by_name": True}


# ============================================================================
# Discriminated Message Union
# ============================================================================

Message = Union[
    AssistantMessage,
    UserMessage,
    SystemInformationalMessage,
    SystemAPIErrorMessage,
    SystemLocalCommandMessage,
    SystemStopHookSummaryMessage,
    SystemBridgeStatusMessage,
    SystemTurnDurationMessage,
    SystemThinkingMessage,
    SystemMemorySavedMessage,
    SystemAwaySummaryMessage,
    SystemAgentsKilledMessage,
    SystemCompactBoundaryMessage,
    SystemMicrocompactBoundaryMessage,
    SystemPermissionRetryMessage,
    SystemScheduledTaskFireMessage,
    SystemApiMetricsMessage,
    AttachmentMessage,
    ProgressMessage[Progress],
    TombstoneMessage,
]
"""Union of all message types used in the conversation history."""


# ============================================================================
# Grouped / Collapsed display types
# ============================================================================


class GroupedToolUseMessage(BaseModel):
    """Grouped tool use for collapsed display."""

    type: Literal["assistant"] = "assistant"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    message: dict[str, Any]
    tool_use_count: int = Field(alias="toolUseCount")

    model_config = {"populate_by_name": True}


class CollapsedReadSearchGroup(BaseModel):
    """Collapsed group of read/search tool uses."""

    type: Literal["assistant"] = "assistant"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    message: dict[str, Any]
    collapsed_count: int = Field(alias="collapsedCount")

    model_config = {"populate_by_name": True}


# ============================================================================
# Renderable / Normalized unions
# ============================================================================

RenderableMessage = Union[
    AssistantMessage,
    UserMessage,
    SystemInformationalMessage,
    SystemAPIErrorMessage,
    SystemLocalCommandMessage,
    SystemStopHookSummaryMessage,
    SystemBridgeStatusMessage,
    SystemTurnDurationMessage,
    SystemThinkingMessage,
    SystemMemorySavedMessage,
    SystemAwaySummaryMessage,
    SystemAgentsKilledMessage,
    SystemCompactBoundaryMessage,
    SystemMicrocompactBoundaryMessage,
    SystemPermissionRetryMessage,
    SystemScheduledTaskFireMessage,
    SystemApiMetricsMessage,
    AttachmentMessage,
    GroupedToolUseMessage,
    CollapsedReadSearchGroup,
]
"""Messages that can be rendered in the UI."""


class NormalizedAssistantMessage(AssistantMessage):
    """Normalized assistant message with single content block."""

    pass


class NormalizedUserMessage(UserMessage):
    """Normalized user message with content always as array."""

    pass


NormalizedMessage = Union[
    NormalizedAssistantMessage,
    NormalizedUserMessage,
    SystemInformationalMessage,
    SystemAPIErrorMessage,
    SystemLocalCommandMessage,
    SystemStopHookSummaryMessage,
    SystemBridgeStatusMessage,
    SystemTurnDurationMessage,
    SystemThinkingMessage,
    SystemMemorySavedMessage,
    SystemAwaySummaryMessage,
    SystemAgentsKilledMessage,
    SystemCompactBoundaryMessage,
    SystemMicrocompactBoundaryMessage,
    SystemPermissionRetryMessage,
    SystemScheduledTaskFireMessage,
    SystemApiMetricsMessage,
    AttachmentMessage,
    ProgressMessage[Progress],
    TombstoneMessage,
]
"""Union of all normalized message types for API processing."""


# ============================================================================
# Stream / Event Types
# ============================================================================


class RequestStartEvent(BaseModel):
    """Event fired at the start of a stream request."""

    type: Literal["stream_request_start"] = "stream_request_start"


class StreamEvent(BaseModel):
    """Wrapper for streaming events from the Anthropic API."""

    type: Literal["stream_event"] = "stream_event"
    event: dict[str, Any]
    """Raw ``BetaRawMessageStreamEvent`` dict from the Anthropic SDK."""
    ttft_ms: float | None = Field(default=None, alias="ttftMs")

    model_config = {"populate_by_name": True}
