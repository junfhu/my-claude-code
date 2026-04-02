"""Central Tool Registry for Claude Code.

This module is the **single source of truth** for which tools the LLM agent
can invoke.  It handles:

  1. Importing every tool implementation.
  2. Building the exhaustive base tool list → ``get_all_base_tools()``
  3. Filtering for the active session → ``get_tools()``
     - Bare mode (CLAUDE_CODE_SIMPLE)
     - Permission deny-rule filtering
     - Per-tool ``is_enabled()`` checks
  4. Merging built-in tools with MCP tools → ``assemble_tool_pool()``
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ─── Tool Protocol ────────────────────────────────────────────────────────────
# Every tool in the registry must conform to this interface.

@runtime_checkable
class Tool(Protocol):
    """Protocol that every tool must implement."""

    @property
    def name(self) -> str:
        """Canonical tool name (e.g. 'Bash', 'FileRead')."""
        ...

    def is_enabled(self) -> bool:
        """Whether this tool is available in the current environment."""
        ...

    def get_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for this tool's parameters."""
        ...

    async def execute(
        self, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        """Execute the tool with the given parameters and context."""
        ...


class ToolPermissionContext:
    """Per-request context carrying permission rules (allow/deny lists, etc.)."""

    def __init__(
        self,
        *,
        deny_rules: Optional[list[dict[str, Any]]] = None,
        allow_rules: Optional[list[dict[str, Any]]] = None,
        permission_mode: str = "default",
    ) -> None:
        self.deny_rules = deny_rules or []
        self.allow_rules = allow_rules or []
        self.permission_mode = permission_mode


# ─── Built-in Tool Implementations ───────────────────────────────────────────
# Lightweight tool descriptors used until full tool modules are loaded.

class _BaseTool:
    """Base class for tool descriptors."""

    _name: str = ""
    _description: str = ""
    _always_enabled: bool = True

    @property
    def name(self) -> str:
        return self._name

    def is_enabled(self) -> bool:
        return self._always_enabled

    def get_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> Any:
        raise NotImplementedError(f"{self._name}.execute() not implemented")

    def __repr__(self) -> str:
        return f"<Tool {self._name}>"


class BashTool(_BaseTool):
    _name = "Bash"
    _description = "Run shell commands in a sandboxed bash environment."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in milliseconds"},
            },
            "required": ["command"],
        }


class FileReadTool(_BaseTool):
    _name = "Read"
    _description = "Read the contents of a file."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Line offset (1-based)"},
                "limit": {"type": "integer", "description": "Max lines to read"},
            },
            "required": ["file_path"],
        }


class FileEditTool(_BaseTool):
    _name = "Edit"
    _description = "Make surgical edits to a file using string replacement."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["file_path", "old_string", "new_string"],
        }


class FileWriteTool(_BaseTool):
    _name = "Write"
    _description = "Write content to a file (full overwrite)."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        }


class GlobTool(_BaseTool):
    _name = "Glob"
    _description = "Find files by glob pattern."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "path": {"type": "string", "description": "Search directory"},
            },
            "required": ["pattern"],
        }


class GrepTool(_BaseTool):
    _name = "Grep"
    _description = "Search file contents using regex patterns."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "Search directory"},
                "glob_pattern": {"type": "string", "description": "File filter"},
                "case_insensitive": {"type": "boolean", "default": False},
            },
            "required": ["pattern"],
        }


class AgentTool(_BaseTool):
    _name = "Agent"
    _description = "Spawn a sub-agent to handle a delegated task."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task for the sub-agent"},
            },
            "required": ["prompt"],
        }


class WebFetchTool(_BaseTool):
    _name = "WebFetch"
    _description = "Fetch content from a URL."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        }


class WebSearchTool(_BaseTool):
    _name = "WebSearch"
    _description = "Search the web and return results."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        }


class NotebookEditTool(_BaseTool):
    _name = "NotebookEdit"
    _description = "Edit a Jupyter notebook cell."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "cell_number": {"type": "integer"},
                "new_source": {"type": "string"},
                "cell_type": {"type": "string", "enum": ["code", "markdown"]},
                "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"]},
            },
            "required": ["notebook_path", "cell_number", "new_source"],
        }


class TodoWriteTool(_BaseTool):
    _name = "TodoWrite"
    _description = "Manage a todo/checklist."

    def get_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                        },
                        "required": ["id", "content", "status"],
                    },
                },
            },
            "required": ["todos"],
        }


class TaskStopTool(_BaseTool):
    _name = "TaskStop"
    _description = "Signal the agent to stop the current task."


class TaskOutputTool(_BaseTool):
    _name = "TaskOutput"
    _description = "Produce structured output from a completed agent task."


class AskUserQuestionTool(_BaseTool):
    _name = "AskUserQuestion"
    _description = "Present structured questions to the user."


class SkillTool(_BaseTool):
    _name = "Skill"
    _description = "Invoke a named skill (user-defined workflow)."


class BriefTool(_BaseTool):
    _name = "Brief"
    _description = "Produce a concise summary for the user."


class EnterPlanModeTool(_BaseTool):
    _name = "EnterPlanMode"
    _description = "Switch into a structured planning workflow."


class ExitPlanModeTool(_BaseTool):
    _name = "ExitPlanMode"
    _description = "Exit the structured planning phase."


class ListMcpResourcesTool(_BaseTool):
    _name = "ListMcpResources"
    _description = "List resources exposed by MCP servers."


class ReadMcpResourceTool(_BaseTool):
    _name = "ReadMcpResource"
    _description = "Read a resource from an MCP server."


class ToolSearchTool(_BaseTool):
    _name = "ToolSearch"
    _description = "Search available tools by keyword."

    def is_enabled(self) -> bool:
        return os.environ.get("CLAUDE_CODE_TOOL_SEARCH", "").lower() in ("1", "true")


class SendMessageTool(_BaseTool):
    _name = "SendMessage"
    _description = "Send a message to another agent."


class TeamCreateTool(_BaseTool):
    _name = "TeamCreate"
    _description = "Create a team of cooperating sub-agents."


class TeamDeleteTool(_BaseTool):
    _name = "TeamDelete"
    _description = "Delete a team of sub-agents."


class ConfigTool(_BaseTool):
    _name = "Config"
    _description = "Read or update Claude Code configuration."


class EnterWorktreeTool(_BaseTool):
    _name = "EnterWorktree"
    _description = "Enter Git worktree isolation for parallel work."


class ExitWorktreeTool(_BaseTool):
    _name = "ExitWorktree"
    _description = "Exit Git worktree isolation."


class LSPTool(_BaseTool):
    _name = "LSP"
    _description = "Language Server Protocol integration."

    def is_enabled(self) -> bool:
        return os.environ.get("ENABLE_LSP_TOOL", "").lower() in ("1", "true")


# Synthetic tool name constant
SYNTHETIC_OUTPUT_TOOL_NAME = "SyntheticOutput"

# Tool sets for agent mode filtering
ALL_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset({
    "TeamCreate", "TeamDelete", "EnterPlanMode", "ExitPlanMode",
    "AskUserQuestion",
})

CUSTOM_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset({
    "TeamCreate", "TeamDelete",
})

ASYNC_AGENT_ALLOWED_TOOLS: frozenset[str] = frozenset({
    "Bash", "Read", "Edit", "Write", "Glob", "Grep",
    "WebFetch", "WebSearch", "NotebookEdit", "Agent",
    "TaskOutput", "TaskStop", "Brief", "TodoWrite",
    "Skill", "SendMessage",
})

COORDINATOR_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset({
    "Agent", "TaskStop", "SendMessage",
})


# ─── Tool Presets ─────────────────────────────────────────────────────────────

TOOL_PRESETS = ("default",)


def parse_tool_preset(preset: str) -> Optional[str]:
    """Validate a user-supplied preset name."""
    p = preset.lower()
    return p if p in TOOL_PRESETS else None


# ─── Tool Catalog ─────────────────────────────────────────────────────────────

def get_all_base_tools() -> list[_BaseTool]:
    """Return the exhaustive list of all tools that *could* be available.

    Whether they actually appear in the final tool list depends on
    ``get_tools()`` filtering.  The tool order here affects prompt-cache
    key stability — do not reorder without cause.
    """
    tools: list[_BaseTool] = [
        # Core orchestration
        AgentTool(),
        TaskOutputTool(),
        # Shell & execution
        BashTool(),
        # File search
        GlobTool(),
        GrepTool(),
        # Plan mode
        ExitPlanModeTool(),
        # File I/O
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        NotebookEditTool(),
        # Web access
        WebFetchTool(),
        # Task tracking
        TodoWriteTool(),
        # Web search
        WebSearchTool(),
        # Session lifecycle
        TaskStopTool(),
        # User interaction
        AskUserQuestionTool(),
        SkillTool(),
        EnterPlanModeTool(),
        # Inter-agent communication
        SendMessageTool(),
        # Output formatting
        BriefTool(),
        # MCP resource tools (merged separately by assemble_tool_pool)
        ListMcpResourcesTool(),
        ReadMcpResourceTool(),
    ]

    # Feature-gated tools
    if os.environ.get("ENABLE_LSP_TOOL", "").lower() in ("1", "true"):
        tools.append(LSPTool())

    if os.environ.get("CLAUDE_CODE_TOOL_SEARCH", "").lower() in ("1", "true"):
        tools.append(ToolSearchTool())

    return tools


def get_tools_for_default_preset() -> list[str]:
    """Materialize the 'default' preset into a list of tool name strings."""
    return [t.name for t in get_all_base_tools() if t.is_enabled()]


# ─── Permission Filtering ─────────────────────────────────────────────────────

def _matches_deny_rule(
    tool: _BaseTool, rule: dict[str, Any]
) -> bool:
    """Check if a deny rule matches a tool."""
    rule_name = rule.get("name", "")
    # Exact match
    if rule_name == tool.name:
        # Blanket deny: no ruleContent means deny all uses
        return not rule.get("ruleContent")
    # MCP prefix match (e.g. "mcp__server" denies all tools from that server)
    if hasattr(tool, "mcp_info"):
        info = tool.mcp_info  # type: ignore[attr-defined]
        server_prefix = f"mcp__{info.get('serverName', '')}"
        if rule_name == server_prefix:
            return not rule.get("ruleContent")
    return False


def filter_tools_by_deny_rules(
    tools: list[Any],
    permission_context: ToolPermissionContext,
) -> list[Any]:
    """Filter out tools that are blanket-denied by the permission context.

    A tool is filtered out if there's a deny rule matching its name with
    no ruleContent (i.e., a blanket deny for that tool).

    Uses the same matcher as the runtime permission check, so MCP
    server-prefix rules like ``mcp__server`` strip all tools from that
    server before the model sees them.
    """
    if not permission_context.deny_rules:
        return list(tools)
    return [
        t for t in tools
        if not any(_matches_deny_rule(t, r) for r in permission_context.deny_rules)
    ]


# ─── Session-Aware Tool Selection ─────────────────────────────────────────────

def get_tools(permission_context: ToolPermissionContext) -> list[_BaseTool]:
    """Get the filtered built-in tools for the current session.

    Layers of filtering:
      1. Bare mode (CLAUDE_CODE_SIMPLE) — minimal tool surface
      2. Special-tool exclusion (MCP resource tools, synthetic output)
      3. Permission deny-rule filtering
      4. Per-tool ``is_enabled()`` checks
    """
    # Layer 1: Bare mode
    if os.environ.get("CLAUDE_CODE_SIMPLE", "").lower() in ("1", "true"):
        simple_tools: list[_BaseTool] = [BashTool(), FileReadTool(), FileEditTool()]
        return filter_tools_by_deny_rules(simple_tools, permission_context)

    # Layer 2: Exclude special tools
    special_names = {
        ListMcpResourcesTool._name,
        ReadMcpResourceTool._name,
        SYNTHETIC_OUTPUT_TOOL_NAME,
    }
    tools = [t for t in get_all_base_tools() if t.name not in special_names]

    # Layer 3: Deny rules
    allowed = filter_tools_by_deny_rules(tools, permission_context)

    # Layer 4: is_enabled() check
    return [t for t in allowed if t.is_enabled()]


# ─── Tool Pool Assembly ───────────────────────────────────────────────────────

def assemble_tool_pool(
    permission_context: ToolPermissionContext,
    mcp_tools: list[Any],
) -> list[Any]:
    """Assemble the full tool pool for a given permission context and MCP tools.

    This is the single source of truth for combining built-in tools with MCP tools.
    The function:
      1. Gets built-in tools via ``get_tools()``
      2. Filters MCP tools by deny rules
      3. Sorts both partitions for prompt-cache stability
      4. Deduplicates by name (built-ins take precedence)
    """
    builtin_tools = get_tools(permission_context)
    allowed_mcp = filter_tools_by_deny_rules(mcp_tools, permission_context)

    # Sort each partition independently for cache stability
    builtin_sorted = sorted(builtin_tools, key=lambda t: t.name)
    mcp_sorted = sorted(allowed_mcp, key=lambda t: getattr(t, "name", ""))

    # Deduplicate: built-ins win on name conflict
    seen: set[str] = set()
    result: list[Any] = []
    for t in builtin_sorted:
        if t.name not in seen:
            seen.add(t.name)
            result.append(t)
    for t in mcp_sorted:
        name = getattr(t, "name", "")
        if name not in seen:
            seen.add(name)
            result.append(t)

    return result


def get_merged_tools(
    permission_context: ToolPermissionContext,
    mcp_tools: list[Any],
) -> list[Any]:
    """Get all tools including built-in and MCP (no dedup / no sort).

    Lighter-weight merge for contexts that just need a count or quick scan.
    """
    return list(get_tools(permission_context)) + list(mcp_tools)
