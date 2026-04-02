"""
Tool progress type definitions.

Each tool that reports streaming progress defines its own progress data shape.
``ToolProgressData`` is the discriminated union of all such shapes.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

__all__ = [
    "BashProgress",
    "AgentToolProgress",
    "MCPProgress",
    "REPLToolProgress",
    "SkillToolProgress",
    "TaskOutputProgress",
    "WebSearchProgress",
    "ToolProgressData",
]


class BashProgress(BaseModel):
    """Progress data for the Bash tool (streaming command output)."""

    type: Literal["bash"] = "bash"
    command: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    is_running: bool | None = Field(default=None, alias="isRunning")
    exit_code: int | None = Field(default=None, alias="exitCode")

    model_config = {"extra": "allow", "populate_by_name": True}


class AgentToolProgress(BaseModel):
    """Progress data for the Agent tool (sub-agent execution)."""

    type: Literal["agent"] = "agent"
    agent_id: str | None = Field(default=None, alias="agentId")
    status: str | None = None
    message: str | None = None
    tool_name: str | None = Field(default=None, alias="toolName")
    tool_input: dict[str, Any] | None = Field(default=None, alias="toolInput")

    model_config = {"extra": "allow", "populate_by_name": True}


class MCPProgress(BaseModel):
    """Progress data for MCP tool calls."""

    type: Literal["mcp"] = "mcp"
    server_name: str | None = Field(default=None, alias="serverName")
    tool_name: str | None = Field(default=None, alias="toolName")
    status: str | None = None
    progress: float | None = None
    total: float | None = None
    message: str | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class REPLToolProgress(BaseModel):
    """Progress data for the REPL tool."""

    type: Literal["repl"] = "repl"
    language: str | None = None
    code: str | None = None
    output: str | None = None
    is_running: bool | None = Field(default=None, alias="isRunning")

    model_config = {"extra": "allow", "populate_by_name": True}


class SkillToolProgress(BaseModel):
    """Progress data for the Skill tool."""

    type: Literal["skill"] = "skill"
    skill_name: str | None = Field(default=None, alias="skillName")
    status: str | None = None
    message: str | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class TaskOutputProgress(BaseModel):
    """Progress data for the TaskOutput tool."""

    type: Literal["task_output"] = "task_output"
    task_id: str | None = Field(default=None, alias="taskId")
    status: str | None = None
    output: str | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class WebSearchProgress(BaseModel):
    """Progress data for the WebSearch tool."""

    type: Literal["web_search"] = "web_search"
    query: str | None = None
    status: str | None = None
    results_count: int | None = Field(default=None, alias="resultsCount")

    model_config = {"extra": "allow", "populate_by_name": True}


ToolProgressData = Union[
    BashProgress,
    AgentToolProgress,
    MCPProgress,
    REPLToolProgress,
    SkillToolProgress,
    TaskOutputProgress,
    WebSearchProgress,
]
"""Discriminated union of all tool-specific progress data types."""
