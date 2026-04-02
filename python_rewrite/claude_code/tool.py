"""
Core tool interface and base class for Claude Code.

All tools in Claude Code implement the Tool abstract base class defined here.
This module provides:
  - Tool: the ABC every tool subclasses
  - ToolResult / ValidationResult / ToolProgress: data containers
  - Helper functions for tool lookup / matching
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    TypeVar,
)

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Generic type vars used by concrete tools
# ---------------------------------------------------------------------------
Input = TypeVar("Input", bound=BaseModel)
Output = TypeVar("Output")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class InterruptBehavior(str, enum.Enum):
    """How a tool reacts when the user presses Ctrl-C."""

    BLOCK = "block"
    ALLOW = "allow"
    IGNORE = "ignore"


class PermissionBehavior(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ToolResult:
    """Result returned by ``Tool.call()``."""

    data: Any
    new_messages: list[Any] = field(default_factory=list)
    context_modifier: Optional[Callable] = None
    mcp_meta: Optional[dict[str, Any]] = None


@dataclass
class ValidationResult:
    """Returned by ``Tool.validate_input()``."""

    result: bool
    message: str = ""
    error_code: int = 0


@dataclass
class ToolProgress:
    """Progress information emitted while a tool is running."""

    tool_use_id: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionDecision:
    """Result of ``Tool.check_permissions()``."""

    behavior: PermissionBehavior = PermissionBehavior.ALLOW
    updated_input: Optional[dict[str, Any]] = None
    message: str = ""


# ---------------------------------------------------------------------------
# Placeholder for the runtime context passed into every tool call.
# The real ToolUseContext lives in the context/ package; this is a forward
# reference so tool.py can be imported stand-alone.
# ---------------------------------------------------------------------------
class ToolUseContext:
    """Minimal stub – replaced at runtime by the real context object."""

    def __init__(self, **kwargs: Any) -> None:
        self.cwd: str = kwargs.get("cwd", ".")
        self.session_id: str = kwargs.get("session_id", "")
        self.read_file_timestamps: dict[str, float] = kwargs.get(
            "read_file_timestamps", {}
        )
        self.aborted: bool = kwargs.get("aborted", False)
        self.options: dict[str, Any] = kwargs.get("options", {})
        self.tools: list["Tool"] = kwargs.get("tools", [])
        self.extra: dict[str, Any] = kwargs.get("extra", {})


# ---------------------------------------------------------------------------
# Tool base class
# ---------------------------------------------------------------------------
class Tool(abc.ABC):
    """Abstract base class that every Claude Code tool must subclass.

    Subclasses **must** implement:
      * ``call()``
      * ``get_description()``
      * ``get_input_schema()``

    Subclasses **may** override any of the other hooks to customise
    permissions, concurrency, display, etc.
    """

    # -- class-level metadata (override in subclasses) ----------------------
    name: str = ""
    aliases: list[str] = []
    search_hint: str = ""
    max_result_size_chars: int = 100_000
    strict: bool = False
    should_defer: bool = False
    always_load: bool = False

    # -----------------------------------------------------------------------
    # Abstract interface
    # -----------------------------------------------------------------------
    @abc.abstractmethod
    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        """Execute the tool and return a result."""
        ...

    @abc.abstractmethod
    async def get_description(self, input: dict[str, Any]) -> str:
        """Human-readable description of what the tool does."""
        ...

    @abc.abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """JSON-Schema dict describing the tool's accepted input."""
        ...

    # -----------------------------------------------------------------------
    # Optional hooks (reasonable defaults)
    # -----------------------------------------------------------------------
    async def get_prompt(self, **kwargs: Any) -> str:
        """Return a system-prompt fragment for this tool, if any."""
        return ""

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        """Validate *input* before execution.  Return ``ValidationResult``."""
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        """Check whether the current user/session may run this tool."""
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW, updated_input=input
        )

    # -----------------------------------------------------------------------
    # Capability flags
    # -----------------------------------------------------------------------
    def is_enabled(self) -> bool:
        """Return ``False`` to hide this tool from the current session."""
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        """Return ``True`` if concurrent invocations are OK."""
        return False

    def is_read_only(self, input: dict[str, Any]) -> bool:
        """Return ``True`` if this invocation only reads state."""
        return False

    def is_destructive(self, input: dict[str, Any]) -> bool:
        """Return ``True`` if this invocation may destroy data."""
        return False

    def interrupt_behavior(self) -> InterruptBehavior:
        """How should the runner react to Ctrl-C while this tool runs?"""
        return InterruptBehavior.BLOCK

    # -----------------------------------------------------------------------
    # Display helpers
    # -----------------------------------------------------------------------
    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        """Name shown to the user in the TUI."""
        return self.name

    def get_tool_use_summary(
        self, input: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """One-line summary for the activity log / TUI."""
        return None

    def get_activity_description(
        self, input: Optional[dict[str, Any]] = None
    ) -> Optional[str]:
        """Short verb-phrase for the spinner / status bar."""
        return None

    # -----------------------------------------------------------------------
    # Classifier / search helpers
    # -----------------------------------------------------------------------
    def to_auto_classifier_input(self, input: dict[str, Any]) -> Any:
        """Return a simplified representation for the auto-classifier."""
        return ""

    def is_search_or_read_command(
        self, input: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """If this invocation is a read/search, return metadata about it."""
        return None

    def get_path(self, input: dict[str, Any]) -> Optional[str]:
        """Return a filesystem path if this tool operates on one."""
        return None

    # -----------------------------------------------------------------------
    # Result mapping
    # -----------------------------------------------------------------------
    def map_tool_result_to_block(
        self, content: Any, tool_use_id: str
    ) -> dict[str, Any]:
        """Convert a tool result into an API tool_result block."""
        if isinstance(content, str):
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            }
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": str(content),
        }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def tool_matches_name(tool: Tool, name: str) -> bool:
    """Return ``True`` if *tool* is known by *name* (including aliases)."""
    if tool.name == name:
        return True
    return name in (tool.aliases or [])


def find_tool_by_name(tools: list[Tool], name: str) -> Optional[Tool]:
    """Find the first tool in *tools* whose name or alias matches *name*."""
    return next((t for t in tools if tool_matches_name(t, name)), None)
