"""
WebSearchTool – Perform web searches.

Delegates to an external search provider (configurable).
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
from claude_code.tools.utils import format_tool_error, truncate_output, MAX_OUTPUT_CHARS


class WebSearchInput(BaseModel):
    query: str = Field(..., description="The search query.")
    max_results: int = Field(10, description="Maximum number of results.")


class WebSearchTool(Tool):
    """Search the web and return results."""

    name = "web_search"
    aliases = ["search_web"]
    search_hint = "web search query internet"

    def get_input_schema(self) -> dict[str, Any]:
        return WebSearchInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Search the web and return results."

    async def get_prompt(self, **kwargs: Any) -> str:
        return "Use web_search to find information on the internet."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        if not input.get("query", "").strip():
            return ValidationResult(result=False, message="query is required.")
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
        parsed = WebSearchInput.model_validate(args)

        try:
            import httpx
        except ImportError:
            return ToolResult(
                data=format_tool_error("httpx is not installed. Run: pip install httpx")
            )

        # Use a search API if configured, otherwise return instructions
        search_api_url = context.options.get("search_api_url")
        if not search_api_url:
            return ToolResult(
                data=format_tool_error(
                    "No search API configured. Set 'search_api_url' in options."
                )
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    search_api_url,
                    params={"q": parsed.query, "max_results": parsed.max_results},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return ToolResult(data=format_tool_error(f"Search failed: {exc}"))

        results = data.get("results", [])
        if not results:
            return ToolResult(data="No results found.")

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            parts.append(f"{i}. {title}\n   {url}\n   {snippet}")

        return ToolResult(data=truncate_output("\n\n".join(parts), MAX_OUTPUT_CHARS))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Search"

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Searching the web..."
