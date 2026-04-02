"""
AskUserQuestionTool – Present multiple-choice questions to the user.

Collects structured answers with optional free-text "Other" responses.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from claude_code.tool import (
    PermissionBehavior,
    PermissionDecision,
    Tool,
    ToolProgress,
    ToolResult,
    ToolUseContext,
    ValidationResult,
)
from claude_code.tools.utils import format_tool_error


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------
class QuestionOption(BaseModel):
    label: str = Field(..., description="Display text the user sees (1-5 words).")
    description: str = Field(..., description="Explanation of this option.")


class Question(BaseModel):
    question: str = Field(..., description="The full question text to display.")
    header: str = Field(..., description="Short label (max 16 chars).")
    options: list[QuestionOption] = Field(
        ..., description="2-4 answer options."
    )
    multi_select: bool = Field(False, description="Allow multiple selections.")


class AskUserQuestionInput(BaseModel):
    questions: list[Question] = Field(
        ..., description="1-4 questions to present."
    )


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class AskUserQuestionTool(Tool):
    """Present multiple-choice questions and collect answers."""

    name = "ask_user_question"
    aliases = ["ask", "question"]
    search_hint = "ask user question multiple choice"

    def get_input_schema(self) -> dict[str, Any]:
        return AskUserQuestionInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return (
            "Present multiple-choice questions to the user. "
            "1-4 questions per call, 2-4 options per question. "
            "An 'Other' free-text option is always added."
        )

    async def get_prompt(self, **kwargs: Any) -> str:
        return (
            "Use ask_user_question when you need the user to decide between "
            "options. Keep headers short (<=16 chars). Option labels 1-5 words."
        )

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        questions = input.get("questions", [])
        if not questions:
            return ValidationResult(result=False, message="At least one question is required.")
        if len(questions) > 4:
            return ValidationResult(result=False, message="Maximum 4 questions per call.")

        for q in questions:
            opts = q.get("options", [])
            if len(opts) < 2:
                return ValidationResult(result=False, message="Each question needs at least 2 options.")
            if len(opts) > 4:
                return ValidationResult(result=False, message="Maximum 4 options per question.")

        return ValidationResult(result=True)

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW, updated_input=input
        )

    async def call(
        self,
        args: dict[str, Any],
        context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = AskUserQuestionInput.model_validate(args)

        # In a full implementation, this would render the questions in the TUI
        # and wait for user input.  Return a structured request for the UI layer.
        return ToolResult(
            data={
                "type": "ask_user_question",
                "questions": [q.model_dump() for q in parsed.questions],
            }
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Question"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Asking question..."
