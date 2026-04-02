"""
ReviewArtifactTool – Review generated artifacts for quality.
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


class ReviewArtifactInput(BaseModel):
    artifact_id: Optional[str] = Field(None, description="ID of a specific artifact to review.")
    artifact_type: Optional[str] = Field(None, description="Type filter: 'code', 'file', 'config'.")


class ReviewArtifactTool(Tool):
    """Review generated artifacts for quality and correctness."""

    name = "review_artifact"
    aliases: list[str] = []
    search_hint = "review artifact quality check"

    def get_input_schema(self) -> dict[str, Any]:
        return ReviewArtifactInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Review generated artifacts for quality and correctness."

    async def validate_input(self, input: dict[str, Any], context: ToolUseContext) -> ValidationResult:
        return ValidationResult(result=True)

    async def check_permissions(self, input: dict[str, Any], context: ToolUseContext) -> PermissionDecision:
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, updated_input=input)

    async def call(
        self, args: dict[str, Any], context: ToolUseContext,
        on_progress: Optional[Callable[[ToolProgress], None]] = None,
    ) -> ToolResult:
        parsed = ReviewArtifactInput.model_validate(args)
        return ToolResult(
            data={"type": "review_artifact", "artifact_id": parsed.artifact_id, "artifact_type": parsed.artifact_type}
        )

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "ReviewArtifact"
