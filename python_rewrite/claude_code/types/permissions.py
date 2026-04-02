"""
Permission type definitions for the Claude Code permission system.

Covers permission modes, rules, decisions, classifier results, and the
full ``ToolPermissionContext`` needed by tool implementations.

This module is pure data with no runtime dependencies beyond Pydantic.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, Field

__all__ = [
    # Mode constants & types
    "EXTERNAL_PERMISSION_MODES",
    "INTERNAL_PERMISSION_MODES",
    "ExternalPermissionMode",
    "InternalPermissionMode",
    "PermissionMode",
    # Behavior / rule
    "PermissionBehavior",
    "PermissionRuleSource",
    "PermissionRuleValue",
    "PermissionRule",
    # Updates
    "PermissionUpdateDestination",
    "PermissionUpdateAddRules",
    "PermissionUpdateReplaceRules",
    "PermissionUpdateRemoveRules",
    "PermissionUpdateSetMode",
    "PermissionUpdateAddDirectories",
    "PermissionUpdateRemoveDirectories",
    "PermissionUpdate",
    # Working directories
    "WorkingDirectorySource",
    "AdditionalWorkingDirectory",
    # Decisions
    "PermissionCommandMetadata",
    "PermissionMetadata",
    "PendingClassifierCheck",
    "PermissionAllowDecision",
    "PermissionAskDecision",
    "PermissionDenyDecision",
    "PermissionDecision",
    "PermissionPassthroughDecision",
    "PermissionResult",
    # Decision reasons
    "PermissionDecisionReasonRule",
    "PermissionDecisionReasonMode",
    "PermissionDecisionReasonSubcommandResults",
    "PermissionDecisionReasonPermissionPromptTool",
    "PermissionDecisionReasonHook",
    "PermissionDecisionReasonAsyncAgent",
    "PermissionDecisionReasonSandboxOverride",
    "PermissionDecisionReasonClassifier",
    "PermissionDecisionReasonWorkingDir",
    "PermissionDecisionReasonSafetyCheck",
    "PermissionDecisionReasonOther",
    "PermissionDecisionReason",
    # Classifier
    "ClassifierResult",
    "ClassifierBehavior",
    "ClassifierUsage",
    "YoloClassifierResult",
    # Explainer
    "RiskLevel",
    "PermissionExplanation",
    # Context
    "ToolPermissionRulesBySource",
    "ToolPermissionContext",
]

# ============================================================================
# Permission Modes
# ============================================================================

ExternalPermissionMode = Literal[
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
]

EXTERNAL_PERMISSION_MODES: tuple[ExternalPermissionMode, ...] = (
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
)

InternalPermissionMode = Literal[
    "acceptEdits",
    "bypassPermissions",
    "default",
    "dontAsk",
    "plan",
    "auto",
    "bubble",
]

PermissionMode = InternalPermissionMode
"""Exhaustive mode union for type-checking."""

INTERNAL_PERMISSION_MODES: tuple[PermissionMode, ...] = (
    *EXTERNAL_PERMISSION_MODES,
    "auto",
)
"""Runtime-validation set: modes that are user-addressable."""

PERMISSION_MODES = INTERNAL_PERMISSION_MODES

# ============================================================================
# Permission Behaviors
# ============================================================================

PermissionBehavior = Literal["allow", "deny", "ask"]

# ============================================================================
# Permission Rules
# ============================================================================

PermissionRuleSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
]
"""Where a permission rule originated from."""


class PermissionRuleValue(BaseModel):
    """The value of a permission rule — specifies which tool and optional content."""

    tool_name: str = Field(alias="toolName")
    rule_content: str | None = Field(default=None, alias="ruleContent")

    model_config = {"populate_by_name": True}


class PermissionRule(BaseModel):
    """A permission rule with its source and behavior."""

    source: PermissionRuleSource
    rule_behavior: PermissionBehavior = Field(alias="ruleBehavior")
    rule_value: PermissionRuleValue = Field(alias="ruleValue")

    model_config = {"populate_by_name": True}


# ============================================================================
# Permission Updates
# ============================================================================

PermissionUpdateDestination = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "session",
    "cliArg",
]
"""Where a permission update should be persisted."""


class PermissionUpdateAddRules(BaseModel):
    """Add rules to a permission configuration."""

    type: Literal["addRules"] = "addRules"
    destination: PermissionUpdateDestination
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateReplaceRules(BaseModel):
    """Replace rules in a permission configuration."""

    type: Literal["replaceRules"] = "replaceRules"
    destination: PermissionUpdateDestination
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateRemoveRules(BaseModel):
    """Remove rules from a permission configuration."""

    type: Literal["removeRules"] = "removeRules"
    destination: PermissionUpdateDestination
    rules: list[PermissionRuleValue]
    behavior: PermissionBehavior


class PermissionUpdateSetMode(BaseModel):
    """Set the permission mode."""

    type: Literal["setMode"] = "setMode"
    destination: PermissionUpdateDestination
    mode: ExternalPermissionMode


class PermissionUpdateAddDirectories(BaseModel):
    """Add working directories."""

    type: Literal["addDirectories"] = "addDirectories"
    destination: PermissionUpdateDestination
    directories: list[str]


class PermissionUpdateRemoveDirectories(BaseModel):
    """Remove working directories."""

    type: Literal["removeDirectories"] = "removeDirectories"
    destination: PermissionUpdateDestination
    directories: list[str]


PermissionUpdate = Union[
    PermissionUpdateAddRules,
    PermissionUpdateReplaceRules,
    PermissionUpdateRemoveRules,
    PermissionUpdateSetMode,
    PermissionUpdateAddDirectories,
    PermissionUpdateRemoveDirectories,
]
"""Discriminated union of all permission update operations."""

# ============================================================================
# Working Directories
# ============================================================================

WorkingDirectorySource = PermissionRuleSource
"""Source of an additional working directory permission."""


class AdditionalWorkingDirectory(BaseModel):
    """An additional directory included in permission scope."""

    path: str
    source: WorkingDirectorySource


# ============================================================================
# Permission Decisions & Results
# ============================================================================


class PermissionCommandMetadata(BaseModel):
    """Minimal command shape for permission metadata.

    Intentionally a subset of the full Command type to avoid import cycles.
    """

    name: str
    description: str | None = None

    model_config = {"extra": "allow"}


PermissionMetadata = PermissionCommandMetadata | None
"""Metadata attached to permission decisions."""

Input = TypeVar("Input", bound=dict[str, Any])


class PendingClassifierCheck(BaseModel):
    """Metadata for a pending classifier check that will run asynchronously."""

    command: str
    cwd: str
    descriptions: list[str]


class PermissionAllowDecision(BaseModel, Generic[Input]):
    """Result when permission is granted."""

    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    user_modified: bool | None = Field(default=None, alias="userModified")
    decision_reason: PermissionDecisionReason | None = Field(
        default=None, alias="decisionReason"
    )
    tool_use_id: str | None = Field(default=None, alias="toolUseID")
    accept_feedback: str | None = Field(default=None, alias="acceptFeedback")
    content_blocks: list[dict[str, Any]] | None = Field(
        default=None, alias="contentBlocks"
    )

    model_config = {"populate_by_name": True}


class PermissionAskDecision(BaseModel, Generic[Input]):
    """Result when user should be prompted."""

    behavior: Literal["ask"] = "ask"
    message: str
    updated_input: dict[str, Any] | None = Field(default=None, alias="updatedInput")
    decision_reason: PermissionDecisionReason | None = Field(
        default=None, alias="decisionReason"
    )
    suggestions: list[PermissionUpdate] | None = None
    blocked_path: str | None = Field(default=None, alias="blockedPath")
    metadata: PermissionMetadata = None
    is_bash_security_check_for_misparsing: bool | None = Field(
        default=None, alias="isBashSecurityCheckForMisparsing"
    )
    pending_classifier_check: PendingClassifierCheck | None = Field(
        default=None, alias="pendingClassifierCheck"
    )
    content_blocks: list[dict[str, Any]] | None = Field(
        default=None, alias="contentBlocks"
    )

    model_config = {"populate_by_name": True}


class PermissionDenyDecision(BaseModel):
    """Result when permission is denied."""

    behavior: Literal["deny"] = "deny"
    message: str
    decision_reason: PermissionDecisionReason = Field(alias="decisionReason")
    tool_use_id: str | None = Field(default=None, alias="toolUseID")

    model_config = {"populate_by_name": True}


PermissionDecision = Union[
    PermissionAllowDecision[dict[str, Any]],
    PermissionAskDecision[dict[str, Any]],
    PermissionDenyDecision,
]
"""A permission decision — allow, ask, or deny."""


class PermissionPassthroughDecision(BaseModel):
    """Passthrough permission result — defers to the next layer."""

    behavior: Literal["passthrough"] = "passthrough"
    message: str
    decision_reason: PermissionDecisionReason | None = Field(
        default=None, alias="decisionReason"
    )
    suggestions: list[PermissionUpdate] | None = None
    blocked_path: str | None = Field(default=None, alias="blockedPath")
    pending_classifier_check: PendingClassifierCheck | None = Field(
        default=None, alias="pendingClassifierCheck"
    )

    model_config = {"populate_by_name": True}


PermissionResult = Union[
    PermissionAllowDecision[dict[str, Any]],
    PermissionAskDecision[dict[str, Any]],
    PermissionDenyDecision,
    PermissionPassthroughDecision,
]
"""Permission result with additional passthrough option."""

# ============================================================================
# Permission Decision Reasons (discriminated union)
# ============================================================================


class PermissionDecisionReasonRule(BaseModel):
    """Permission granted/denied by a specific rule."""

    type: Literal["rule"] = "rule"
    rule: PermissionRule


class PermissionDecisionReasonMode(BaseModel):
    """Permission decided by the current mode."""

    type: Literal["mode"] = "mode"
    mode: PermissionMode


class PermissionDecisionReasonSubcommandResults(BaseModel):
    """Permission decided by aggregating subcommand results."""

    type: Literal["subcommandResults"] = "subcommandResults"
    reasons: dict[str, Any]
    """Map<string, PermissionResult> serialised as dict."""


class PermissionDecisionReasonPermissionPromptTool(BaseModel):
    """Permission decided by a permission prompt tool."""

    type: Literal["permissionPromptTool"] = "permissionPromptTool"
    permission_prompt_tool_name: str = Field(alias="permissionPromptToolName")
    tool_result: Any = Field(alias="toolResult")

    model_config = {"populate_by_name": True}


class PermissionDecisionReasonHook(BaseModel):
    """Permission decided by a hook."""

    type: Literal["hook"] = "hook"
    hook_name: str = Field(alias="hookName")
    hook_source: str | None = Field(default=None, alias="hookSource")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class PermissionDecisionReasonAsyncAgent(BaseModel):
    """Permission decided by an async agent."""

    type: Literal["asyncAgent"] = "asyncAgent"
    reason: str


class PermissionDecisionReasonSandboxOverride(BaseModel):
    """Permission from a sandbox override."""

    type: Literal["sandboxOverride"] = "sandboxOverride"
    reason: Literal["excludedCommand", "dangerouslyDisableSandbox"]


class PermissionDecisionReasonClassifier(BaseModel):
    """Permission decided by a classifier."""

    type: Literal["classifier"] = "classifier"
    classifier: str
    reason: str


class PermissionDecisionReasonWorkingDir(BaseModel):
    """Permission decided by working directory rules."""

    type: Literal["workingDir"] = "workingDir"
    reason: str


class PermissionDecisionReasonSafetyCheck(BaseModel):
    """Permission decided by a safety check.

    When ``classifier_approvable`` is ``True``, auto mode lets the classifier
    evaluate this instead of forcing a prompt.
    """

    type: Literal["safetyCheck"] = "safetyCheck"
    reason: str
    classifier_approvable: bool = Field(alias="classifierApprovable")

    model_config = {"populate_by_name": True}


class PermissionDecisionReasonOther(BaseModel):
    """Catch-all permission decision reason."""

    type: Literal["other"] = "other"
    reason: str


PermissionDecisionReason = Union[
    PermissionDecisionReasonRule,
    PermissionDecisionReasonMode,
    PermissionDecisionReasonSubcommandResults,
    PermissionDecisionReasonPermissionPromptTool,
    PermissionDecisionReasonHook,
    PermissionDecisionReasonAsyncAgent,
    PermissionDecisionReasonSandboxOverride,
    PermissionDecisionReasonClassifier,
    PermissionDecisionReasonWorkingDir,
    PermissionDecisionReasonSafetyCheck,
    PermissionDecisionReasonOther,
]
"""Discriminated union explaining why a permission decision was made."""

# ============================================================================
# Bash Classifier Types
# ============================================================================

ClassifierBehavior = Literal["deny", "ask", "allow"]


class ClassifierUsage(BaseModel):
    """Token usage from a classifier API call."""

    input_tokens: int = Field(alias="inputTokens")
    output_tokens: int = Field(alias="outputTokens")
    cache_read_input_tokens: int = Field(alias="cacheReadInputTokens")
    cache_creation_input_tokens: int = Field(alias="cacheCreationInputTokens")

    model_config = {"populate_by_name": True}


class ClassifierResult(BaseModel):
    """Result from a bash command classifier."""

    matches: bool
    matched_description: str | None = Field(default=None, alias="matchedDescription")
    confidence: Literal["high", "medium", "low"]
    reason: str

    model_config = {"populate_by_name": True}


class ClassifierPromptLengths(BaseModel):
    """Character lengths of the prompt components sent to the classifier."""

    system_prompt: int = Field(alias="systemPrompt")
    tool_calls: int = Field(alias="toolCalls")
    user_prompts: int = Field(alias="userPrompts")

    model_config = {"populate_by_name": True}


class YoloClassifierResult(BaseModel):
    """Result from the YOLO (auto-approve) classifier."""

    thinking: str | None = None
    should_block: bool = Field(alias="shouldBlock")
    reason: str
    unavailable: bool | None = None
    transcript_too_long: bool | None = Field(default=None, alias="transcriptTooLong")
    """When ``True``, the classifier transcript exceeded the context window."""
    model: str
    """The model used for this classifier call."""
    usage: ClassifierUsage | None = None
    duration_ms: float | None = Field(default=None, alias="durationMs")
    prompt_lengths: ClassifierPromptLengths | None = Field(
        default=None, alias="promptLengths"
    )
    error_dump_path: str | None = Field(default=None, alias="errorDumpPath")
    stage: Literal["fast", "thinking"] | None = None
    stage1_usage: ClassifierUsage | None = Field(default=None, alias="stage1Usage")
    stage1_duration_ms: float | None = Field(default=None, alias="stage1DurationMs")
    stage1_request_id: str | None = Field(default=None, alias="stage1RequestId")
    stage1_msg_id: str | None = Field(default=None, alias="stage1MsgId")
    stage2_usage: ClassifierUsage | None = Field(default=None, alias="stage2Usage")
    stage2_duration_ms: float | None = Field(default=None, alias="stage2DurationMs")
    stage2_request_id: str | None = Field(default=None, alias="stage2RequestId")
    stage2_msg_id: str | None = Field(default=None, alias="stage2MsgId")

    model_config = {"populate_by_name": True}


# ============================================================================
# Permission Explainer Types
# ============================================================================

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


class PermissionExplanation(BaseModel):
    """Explanation of a permission's risk and reasoning."""

    risk_level: RiskLevel = Field(alias="riskLevel")
    explanation: str
    reasoning: str
    risk: str

    model_config = {"populate_by_name": True}


# ============================================================================
# Tool Permission Context
# ============================================================================

ToolPermissionRulesBySource = dict[PermissionRuleSource, list[str]]
"""Mapping of permission rules by their source."""


class ToolPermissionContext(BaseModel):
    """Context needed for permission checking in tools.

    All fields are effectively read-only (frozen model).
    """

    mode: PermissionMode
    additional_working_directories: dict[str, AdditionalWorkingDirectory] = Field(
        default_factory=dict, alias="additionalWorkingDirectories"
    )
    always_allow_rules: ToolPermissionRulesBySource = Field(
        default_factory=dict, alias="alwaysAllowRules"
    )
    always_deny_rules: ToolPermissionRulesBySource = Field(
        default_factory=dict, alias="alwaysDenyRules"
    )
    always_ask_rules: ToolPermissionRulesBySource = Field(
        default_factory=dict, alias="alwaysAskRules"
    )
    is_bypass_permissions_mode_available: bool = Field(
        default=False, alias="isBypassPermissionsModeAvailable"
    )
    stripped_dangerous_rules: ToolPermissionRulesBySource | None = Field(
        default=None, alias="strippedDangerousRules"
    )
    should_avoid_permission_prompts: bool | None = Field(
        default=None, alias="shouldAvoidPermissionPrompts"
    )
    await_automated_checks_before_dialog: bool | None = Field(
        default=None, alias="awaitAutomatedChecksBeforeDialog"
    )
    pre_plan_mode: PermissionMode | None = Field(default=None, alias="prePlanMode")

    model_config = {"frozen": True, "populate_by_name": True}
