"""
AgentTool – Spawn a sub-agent to handle complex tasks.

The sub-agent runs in the same session but with its own conversation
context.  Supports both foreground (blocking) and background modes.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from claude_code.tool import (
    InterruptBehavior,
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)
from claude_code.tools.utils import format_tool_error, truncate_output, MAX_OUTPUT_CHARS


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class AgentInput(BaseModel):
    """Input schema for the Agent tool."""

    prompt: str = Field(
        ..., description="The task description / instructions for the sub-agent."
    )
    profile: str = Field(
        "subagent_general",
        description=(
            "Agent profile to use.  'subagent_explore' for read-only tasks, "
            "'subagent_general' for full-access tasks."
        ),
    )
    background: bool = Field(
        False,
        description="If True, run the agent in the background and return immediately.",
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class AgentTool(Tool):
    """Spawn a sub-agent to execute a complex, multi-step task."""

    name = "run_agent"
    aliases = ["agent", "subagent", "run_subagent"]
    search_hint = "agent subagent spawn delegate task"
    should_defer = True

    def get_input_schema(self) -> dict[str, Any]:
        return AgentInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Launch a sub-agent that can autonomously perform a complex task. "
            "The sub-agent has access to the same tools and context. "
            "Use 'subagent_explore' for read-only research and "
            "'subagent_general' for tasks that require writing."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use run_agent to delegate complex sub-tasks to an autonomous agent. "
            "Provide a clear, detailed prompt describing the task."
        )

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        prompt = input.get("prompt", "").strip()
        if not prompt:
            return ValidationResult(result=False, message="prompt is required.")
        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ASK, updated_input=input
        )

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = AgentInput.model_validate(args)

        # In a full implementation this would invoke the agent runtime.
        # For now we return a placeholder that the coordinator will intercept.
        return ToolResult(
            data={
                "type": "agent_request",
                "prompt": parsed.prompt,
                "profile": parsed.profile,
                "background": parsed.background,
            }
        )

    def interrupt_behavior(self) -> InterruptBehavior:
        return InterruptBehavior.ALLOW

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Agent"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            prompt = input.get("prompt", "")
            if len(prompt) > 60:
                prompt = prompt[:57] + "..."
            return f"Agent: {prompt}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Running sub-agent..."
