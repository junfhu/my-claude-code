"""
Tool name constants and tool-set definitions.

Centralises all tool name strings and the various allow/deny sets
used for agents, coordinators, and async execution.
"""

from __future__ import annotations

import os

__all__ = [
    # Individual tool names
    "AGENT_TOOL_NAME",
    "ASK_USER_QUESTION_TOOL_NAME",
    "BASH_TOOL_NAME",
    "CRON_CREATE_TOOL_NAME",
    "CRON_DELETE_TOOL_NAME",
    "CRON_LIST_TOOL_NAME",
    "ENTER_PLAN_MODE_TOOL_NAME",
    "ENTER_WORKTREE_TOOL_NAME",
    "EXIT_PLAN_MODE_V2_TOOL_NAME",
    "EXIT_WORKTREE_TOOL_NAME",
    "FILE_EDIT_TOOL_NAME",
    "FILE_READ_TOOL_NAME",
    "FILE_WRITE_TOOL_NAME",
    "GLOB_TOOL_NAME",
    "GREP_TOOL_NAME",
    "NOTEBOOK_EDIT_TOOL_NAME",
    "SEND_MESSAGE_TOOL_NAME",
    "SKILL_TOOL_NAME",
    "SYNTHETIC_OUTPUT_TOOL_NAME",
    "TASK_CREATE_TOOL_NAME",
    "TASK_GET_TOOL_NAME",
    "TASK_LIST_TOOL_NAME",
    "TASK_OUTPUT_TOOL_NAME",
    "TASK_STOP_TOOL_NAME",
    "TASK_UPDATE_TOOL_NAME",
    "TODO_WRITE_TOOL_NAME",
    "TOOL_SEARCH_TOOL_NAME",
    "WEB_FETCH_TOOL_NAME",
    "WEB_SEARCH_TOOL_NAME",
    "WORKFLOW_TOOL_NAME",
    # Shell tool names
    "SHELL_TOOL_NAMES",
    # Tool sets
    "ALL_AGENT_DISALLOWED_TOOLS",
    "CUSTOM_AGENT_DISALLOWED_TOOLS",
    "ASYNC_AGENT_ALLOWED_TOOLS",
    "IN_PROCESS_TEAMMATE_ALLOWED_TOOLS",
    "COORDINATOR_MODE_ALLOWED_TOOLS",
]

# ============================================================================
# Individual tool name constants
# ============================================================================

AGENT_TOOL_NAME: str = "Agent"
ASK_USER_QUESTION_TOOL_NAME: str = "AskUserQuestion"
BASH_TOOL_NAME: str = "Bash"
CRON_CREATE_TOOL_NAME: str = "ScheduleCron"
CRON_DELETE_TOOL_NAME: str = "DeleteCron"
CRON_LIST_TOOL_NAME: str = "ListCron"
ENTER_PLAN_MODE_TOOL_NAME: str = "EnterPlanMode"
ENTER_WORKTREE_TOOL_NAME: str = "EnterWorktree"
EXIT_PLAN_MODE_V2_TOOL_NAME: str = "ExitPlanMode"
EXIT_WORKTREE_TOOL_NAME: str = "ExitWorktree"
FILE_EDIT_TOOL_NAME: str = "Edit"
FILE_READ_TOOL_NAME: str = "Read"
FILE_WRITE_TOOL_NAME: str = "Write"
GLOB_TOOL_NAME: str = "Glob"
GREP_TOOL_NAME: str = "Grep"
NOTEBOOK_EDIT_TOOL_NAME: str = "NotebookEdit"
SEND_MESSAGE_TOOL_NAME: str = "SendMessage"
SKILL_TOOL_NAME: str = "Skill"
SYNTHETIC_OUTPUT_TOOL_NAME: str = "SyntheticOutput"
TASK_CREATE_TOOL_NAME: str = "TaskCreate"
TASK_GET_TOOL_NAME: str = "TaskGet"
TASK_LIST_TOOL_NAME: str = "TaskList"
TASK_OUTPUT_TOOL_NAME: str = "TaskOutput"
TASK_STOP_TOOL_NAME: str = "TaskStop"
TASK_UPDATE_TOOL_NAME: str = "TaskUpdate"
TODO_WRITE_TOOL_NAME: str = "TodoWrite"
TOOL_SEARCH_TOOL_NAME: str = "ToolSearch"
WEB_FETCH_TOOL_NAME: str = "WebFetch"
WEB_SEARCH_TOOL_NAME: str = "WebSearch"
WORKFLOW_TOOL_NAME: str = "Workflow"

# Shell tool names (the Bash tool can appear under these names)
SHELL_TOOL_NAMES: frozenset[str] = frozenset({BASH_TOOL_NAME})

# ============================================================================
# Tool sets for agent modes
# ============================================================================


def _build_agent_disallowed() -> frozenset[str]:
    """Build the set of tools disallowed in all agent contexts."""
    base = {
        TASK_OUTPUT_TOOL_NAME,
        EXIT_PLAN_MODE_V2_TOOL_NAME,
        ENTER_PLAN_MODE_TOOL_NAME,
        ASK_USER_QUESTION_TOOL_NAME,
        TASK_STOP_TOOL_NAME,
    }
    # Allow Agent tool for agents when user is ant (enables nested agents)
    if os.environ.get("USER_TYPE") != "ant":
        base.add(AGENT_TOOL_NAME)
    return frozenset(base)


ALL_AGENT_DISALLOWED_TOOLS: frozenset[str] = _build_agent_disallowed()
"""Tools disallowed in all agent contexts."""

CUSTOM_AGENT_DISALLOWED_TOOLS: frozenset[str] = ALL_AGENT_DISALLOWED_TOOLS
"""Tools disallowed in custom agent contexts."""

ASYNC_AGENT_ALLOWED_TOOLS: frozenset[str] = frozenset({
    FILE_READ_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
    TODO_WRITE_TOOL_NAME,
    GREP_TOOL_NAME,
    WEB_FETCH_TOOL_NAME,
    GLOB_TOOL_NAME,
    *SHELL_TOOL_NAMES,
    FILE_EDIT_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
    NOTEBOOK_EDIT_TOOL_NAME,
    SKILL_TOOL_NAME,
    SYNTHETIC_OUTPUT_TOOL_NAME,
    TOOL_SEARCH_TOOL_NAME,
    ENTER_WORKTREE_TOOL_NAME,
    EXIT_WORKTREE_TOOL_NAME,
})
"""Tools allowed for async agent execution."""

IN_PROCESS_TEAMMATE_ALLOWED_TOOLS: frozenset[str] = frozenset({
    TASK_CREATE_TOOL_NAME,
    TASK_GET_TOOL_NAME,
    TASK_LIST_TOOL_NAME,
    TASK_UPDATE_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
})
"""Tools allowed only for in-process teammates (not general async agents)."""

COORDINATOR_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset({
    AGENT_TOOL_NAME,
    TASK_STOP_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
    SYNTHETIC_OUTPUT_TOOL_NAME,
})
"""Tools allowed in coordinator mode — only output and agent management."""
