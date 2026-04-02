"""
Tool registry for Claude Code.

Provides:
  - ``get_all_tools()``     — instantiate every registered tool
  - ``get_tools(**kw)``     — filtered subset of tools
  - ``find_tool_by_name()`` — look up a single tool by name or alias
  - ``TOOL_CLASSES``        — ordered list of all tool classes
"""

from __future__ import annotations

from typing import Any, Optional

from claude_code.tool import Tool, find_tool_by_name as _find_tool_by_name

# ---------------------------------------------------------------------------
# Core tools (always loaded)
# ---------------------------------------------------------------------------
from claude_code.tools.bash_tool import BashTool
from claude_code.tools.file_read_tool import FileReadTool
from claude_code.tools.file_write_tool import FileWriteTool
from claude_code.tools.file_edit_tool import FileEditTool
from claude_code.tools.grep_tool import GrepTool
from claude_code.tools.glob_tool import GlobTool

# ---------------------------------------------------------------------------
# Agent / sub-agent tools
# ---------------------------------------------------------------------------
from claude_code.tools.agent_tool import AgentTool

# ---------------------------------------------------------------------------
# User interaction tools
# ---------------------------------------------------------------------------
from claude_code.tools.ask_user_question_tool import AskUserQuestionTool
from claude_code.tools.brief_tool import BriefTool
from claude_code.tools.send_message_tool import SendMessageTool

# ---------------------------------------------------------------------------
# Web tools
# ---------------------------------------------------------------------------
from claude_code.tools.web_fetch_tool import WebFetchTool
from claude_code.tools.web_search_tool import WebSearchTool
from claude_code.tools.web_browser_tool import WebBrowserTool

# ---------------------------------------------------------------------------
# Notebook / REPL tools
# ---------------------------------------------------------------------------
from claude_code.tools.notebook_edit_tool import NotebookEditTool
from claude_code.tools.repl_tool import ReplTool

# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------
from claude_code.tools.mcp_tool import McpTool
from claude_code.tools.list_mcp_resources_tool import ListMcpResourcesTool
from claude_code.tools.read_mcp_resource_tool import ReadMcpResourceTool
from claude_code.tools.mcp_auth_tool import McpAuthTool

# ---------------------------------------------------------------------------
# Task management tools
# ---------------------------------------------------------------------------
from claude_code.tools.todo_write_tool import TodoWriteTool
from claude_code.tools.task_tools import (
    TaskCreateTool,
    TaskListTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskStopTool,
    TaskOutputTool,
)

# ---------------------------------------------------------------------------
# Team tools
# ---------------------------------------------------------------------------
from claude_code.tools.team_tools import TeamCreateTool, TeamDeleteTool

# ---------------------------------------------------------------------------
# Skill tools
# ---------------------------------------------------------------------------
from claude_code.tools.skill_tool import SkillTool
from claude_code.tools.discover_skills_tool import DiscoverSkillsTool

# ---------------------------------------------------------------------------
# System / utility tools
# ---------------------------------------------------------------------------
from claude_code.tools.config_tool import ConfigTool
from claude_code.tools.sleep_tool import SleepTool
from claude_code.tools.snip_tool import SnipTool
from claude_code.tools.monitor_tool import MonitorTool
from claude_code.tools.lsp_tool import LspTool
from claude_code.tools.tool_search_tool import ToolSearchTool
from claude_code.tools.terminal_capture_tool import TerminalCaptureTool
from claude_code.tools.powershell_tool import PowerShellTool
from claude_code.tools.workflow_tool import WorkflowTool

# ---------------------------------------------------------------------------
# Planning / worktree tools
# ---------------------------------------------------------------------------
from claude_code.tools.enter_plan_mode_tool import EnterPlanModeTool
from claude_code.tools.exit_plan_mode_tool import ExitPlanModeTool
from claude_code.tools.enter_worktree_tool import EnterWorktreeTool
from claude_code.tools.exit_worktree_tool import ExitWorktreeTool
from claude_code.tools.ctx_inspect_tool import CtxInspectTool

# ---------------------------------------------------------------------------
# Review / verification tools
# ---------------------------------------------------------------------------
from claude_code.tools.review_artifact_tool import ReviewArtifactTool
from claude_code.tools.verify_plan_tool import VerifyPlanTool

# ---------------------------------------------------------------------------
# Communication tools
# ---------------------------------------------------------------------------
from claude_code.tools.list_peers_tool import ListPeersTool
from claude_code.tools.send_user_file_tool import SendUserFileTool
from claude_code.tools.push_notification_tool import PushNotificationTool
from claude_code.tools.remote_trigger_tool import RemoteTriggerTool
from claude_code.tools.subscribe_pr_tool import SubscribePrTool
from claude_code.tools.schedule_cron_tool import ScheduleCronTool

# ---------------------------------------------------------------------------
# Testing / internal tools
# ---------------------------------------------------------------------------
from claude_code.tools.overflow_test_tool import OverflowTestTool
from claude_code.tools.synthetic_output_tool import SyntheticOutputTool
from claude_code.tools.tungsten_tool import TungstenTool


# ---------------------------------------------------------------------------
# Master list of all tool classes, in canonical order.
# ---------------------------------------------------------------------------
TOOL_CLASSES: list[type[Tool]] = [
    # Core filesystem / shell
    BashTool,
    FileReadTool,
    FileWriteTool,
    FileEditTool,
    GrepTool,
    GlobTool,
    # Agent
    AgentTool,
    # User interaction
    AskUserQuestionTool,
    BriefTool,
    SendMessageTool,
    # Web
    WebFetchTool,
    WebSearchTool,
    WebBrowserTool,
    # Notebook / REPL
    NotebookEditTool,
    ReplTool,
    # MCP
    McpTool,
    ListMcpResourcesTool,
    ReadMcpResourceTool,
    McpAuthTool,
    # Tasks
    TodoWriteTool,
    TaskCreateTool,
    TaskListTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskStopTool,
    TaskOutputTool,
    # Teams
    TeamCreateTool,
    TeamDeleteTool,
    # Skills
    SkillTool,
    DiscoverSkillsTool,
    # System / utility
    ConfigTool,
    SleepTool,
    SnipTool,
    MonitorTool,
    LspTool,
    ToolSearchTool,
    TerminalCaptureTool,
    PowerShellTool,
    WorkflowTool,
    # Planning / worktree
    EnterPlanModeTool,
    ExitPlanModeTool,
    EnterWorktreeTool,
    ExitWorktreeTool,
    CtxInspectTool,
    # Review / verification
    ReviewArtifactTool,
    VerifyPlanTool,
    # Communication
    ListPeersTool,
    SendUserFileTool,
    PushNotificationTool,
    RemoteTriggerTool,
    SubscribePrTool,
    ScheduleCronTool,
    # Testing / internal
    OverflowTestTool,
    SyntheticOutputTool,
    TungstenTool,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_all_tools() -> list[Tool]:
    """Instantiate and return one instance of every registered tool."""
    return [cls() for cls in TOOL_CLASSES]


def get_tools(
    *,
    enabled_only: bool = True,
    always_load_only: bool = False,
    names: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
) -> list[Tool]:
    """Return a filtered subset of tool instances.

    Parameters
    ----------
    enabled_only:
        If ``True`` (default), skip tools whose ``is_enabled()`` returns ``False``.
    always_load_only:
        If ``True``, only return tools marked ``always_load = True``.
    names:
        If provided, only include tools whose name is in this list.
    exclude:
        If provided, exclude tools whose name is in this list.
    """
    tools: list[Tool] = []
    exclude_set = set(exclude or [])

    for cls in TOOL_CLASSES:
        instance = cls()

        if enabled_only and not instance.is_enabled():
            continue
        if always_load_only and not instance.always_load:
            continue
        if names is not None and instance.name not in names:
            continue
        if instance.name in exclude_set:
            continue

        tools.append(instance)

    return tools


def find_tool_by_name(name: str, tools: Optional[list[Tool]] = None) -> Optional[Tool]:
    """Find a tool by *name* (or alias).

    If *tools* is ``None``, searches all registered tools.
    """
    if tools is None:
        tools = get_all_tools()
    return _find_tool_by_name(tools, name)


# ---------------------------------------------------------------------------
# Convenience re-exports
# ---------------------------------------------------------------------------
__all__ = [
    # Registry functions
    "TOOL_CLASSES",
    "get_all_tools",
    "get_tools",
    "find_tool_by_name",
    # Core tools
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "GrepTool",
    "GlobTool",
    # Agent
    "AgentTool",
    # User interaction
    "AskUserQuestionTool",
    "BriefTool",
    "SendMessageTool",
    # Web
    "WebFetchTool",
    "WebSearchTool",
    "WebBrowserTool",
    # Notebook / REPL
    "NotebookEditTool",
    "ReplTool",
    # MCP
    "McpTool",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "McpAuthTool",
    # Tasks
    "TodoWriteTool",
    "TaskCreateTool",
    "TaskListTool",
    "TaskGetTool",
    "TaskUpdateTool",
    "TaskStopTool",
    "TaskOutputTool",
    # Teams
    "TeamCreateTool",
    "TeamDeleteTool",
    # Skills
    "SkillTool",
    "DiscoverSkillsTool",
    # System
    "ConfigTool",
    "SleepTool",
    "SnipTool",
    "MonitorTool",
    "LspTool",
    "ToolSearchTool",
    "TerminalCaptureTool",
    "PowerShellTool",
    "WorkflowTool",
    # Planning
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    "EnterWorktreeTool",
    "ExitWorktreeTool",
    "CtxInspectTool",
    # Review
    "ReviewArtifactTool",
    "VerifyPlanTool",
    # Communication
    "ListPeersTool",
    "SendUserFileTool",
    "PushNotificationTool",
    "RemoteTriggerTool",
    "SubscribePrTool",
    "ScheduleCronTool",
    # Testing
    "OverflowTestTool",
    "SyntheticOutputTool",
    "TungstenTool",
]
