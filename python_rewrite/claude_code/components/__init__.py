"""
Components package — Textual widgets for Claude Code.
"""

from claude_code.components.message_display import MessageRenderer
from claude_code.components.tool_display import ToolRenderer
from claude_code.components.prompt_input import PromptInput
from claude_code.components.status_bar import StatusBar
from claude_code.components.spinner import ThinkingSpinner, InlineSpinner
from claude_code.components.permission_prompt import PermissionPromptWidget
from claude_code.components.sidebar import Sidebar, TodoItem, TeammateInfo

__all__ = [
    "MessageRenderer",
    "ToolRenderer",
    "PromptInput",
    "StatusBar",
    "ThinkingSpinner",
    "InlineSpinner",
    "PermissionPromptWidget",
    "Sidebar",
    "TodoItem",
    "TeammateInfo",
]
