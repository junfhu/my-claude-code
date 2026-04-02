"""
XML tag constants used in message formatting and parsing.
"""

from __future__ import annotations

__all__ = [
    # Command metadata tags
    "COMMAND_NAME_TAG",
    "COMMAND_MESSAGE_TAG",
    "COMMAND_ARGS_TAG",
    # Terminal / bash tags
    "BASH_INPUT_TAG",
    "BASH_STDOUT_TAG",
    "BASH_STDERR_TAG",
    "LOCAL_COMMAND_STDOUT_TAG",
    "LOCAL_COMMAND_STDERR_TAG",
    "LOCAL_COMMAND_CAVEAT_TAG",
    "TERMINAL_OUTPUT_TAGS",
    # Tick
    "TICK_TAG",
    # Task notification tags
    "TASK_NOTIFICATION_TAG",
    "TASK_ID_TAG",
    "TOOL_USE_ID_TAG",
    "TASK_TYPE_TAG",
    "OUTPUT_FILE_TAG",
    "STATUS_TAG",
    "SUMMARY_TAG",
    "REASON_TAG",
    "WORKTREE_TAG",
    "WORKTREE_PATH_TAG",
    "WORKTREE_BRANCH_TAG",
    # Ultraplan
    "ULTRAPLAN_TAG",
    # Remote review
    "REMOTE_REVIEW_TAG",
    "REMOTE_REVIEW_PROGRESS_TAG",
    # Teammate / channel
    "TEAMMATE_MESSAGE_TAG",
    "CHANNEL_MESSAGE_TAG",
    "CHANNEL_TAG",
    "CROSS_SESSION_MESSAGE_TAG",
    # Fork boilerplate
    "FORK_BOILERPLATE_TAG",
    "FORK_DIRECTIVE_PREFIX",
    # Help / info args
    "COMMON_HELP_ARGS",
    "COMMON_INFO_ARGS",
]

# ============================================================================
# Command metadata tags
# ============================================================================

COMMAND_NAME_TAG: str = "command-name"
COMMAND_MESSAGE_TAG: str = "command-message"
COMMAND_ARGS_TAG: str = "command-args"

# ============================================================================
# Terminal / bash tags
# ============================================================================

BASH_INPUT_TAG: str = "bash-input"
BASH_STDOUT_TAG: str = "bash-stdout"
BASH_STDERR_TAG: str = "bash-stderr"
LOCAL_COMMAND_STDOUT_TAG: str = "local-command-stdout"
LOCAL_COMMAND_STDERR_TAG: str = "local-command-stderr"
LOCAL_COMMAND_CAVEAT_TAG: str = "local-command-caveat"

TERMINAL_OUTPUT_TAGS: tuple[str, ...] = (
    BASH_INPUT_TAG,
    BASH_STDOUT_TAG,
    BASH_STDERR_TAG,
    LOCAL_COMMAND_STDOUT_TAG,
    LOCAL_COMMAND_STDERR_TAG,
    LOCAL_COMMAND_CAVEAT_TAG,
)
"""All terminal-related tags that indicate a message is terminal output, not a user prompt."""

# ============================================================================
# Tick tag
# ============================================================================

TICK_TAG: str = "tick"

# ============================================================================
# Task notification tags
# ============================================================================

TASK_NOTIFICATION_TAG: str = "task-notification"
TASK_ID_TAG: str = "task-id"
TOOL_USE_ID_TAG: str = "tool-use-id"
TASK_TYPE_TAG: str = "task-type"
OUTPUT_FILE_TAG: str = "output-file"
STATUS_TAG: str = "status"
SUMMARY_TAG: str = "summary"
REASON_TAG: str = "reason"
WORKTREE_TAG: str = "worktree"
WORKTREE_PATH_TAG: str = "worktreePath"
WORKTREE_BRANCH_TAG: str = "worktreeBranch"

# ============================================================================
# Ultraplan
# ============================================================================

ULTRAPLAN_TAG: str = "ultraplan"

# ============================================================================
# Remote review
# ============================================================================

REMOTE_REVIEW_TAG: str = "remote-review"
"""Remote /review results (teleported review session output)."""

REMOTE_REVIEW_PROGRESS_TAG: str = "remote-review-progress"
"""run_hunt.sh heartbeat tag with orchestrator progress."""

# ============================================================================
# Teammate / channel / cross-session
# ============================================================================

TEAMMATE_MESSAGE_TAG: str = "teammate-message"
"""Swarm inter-agent communication."""

CHANNEL_MESSAGE_TAG: str = "channel-message"
"""External channel messages."""

CHANNEL_TAG: str = "channel"

CROSS_SESSION_MESSAGE_TAG: str = "cross-session-message"
"""Cross-session UDS messages (another Claude session's inbox)."""

# ============================================================================
# Fork boilerplate
# ============================================================================

FORK_BOILERPLATE_TAG: str = "fork-boilerplate"
"""Wraps the rules/format boilerplate in a fork child's first message."""

FORK_DIRECTIVE_PREFIX: str = "Your directive: "
"""Prefix before the directive text, stripped by the renderer."""

# ============================================================================
# Common argument patterns
# ============================================================================

COMMON_HELP_ARGS: tuple[str, ...] = ("help", "-h", "--help")
"""Common argument patterns for slash commands that request help."""

COMMON_INFO_ARGS: tuple[str, ...] = (
    "list",
    "show",
    "display",
    "current",
    "view",
    "get",
    "check",
    "describe",
    "print",
    "version",
    "about",
    "status",
    "?",
)
"""Common argument patterns for slash commands that request current state/info."""
