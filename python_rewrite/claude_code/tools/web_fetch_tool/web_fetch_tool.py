"""
WebFetchTool – Fetch a web page and extract readable text.

Uses httpx for HTTP requests and extracts text from HTML.
"""

from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import urlparse

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
from claude_code.tools.utils import (
    MAX_OUTPUT_CHARS,
    extract_text_from_html,
    format_tool_error,
    truncate_output,
)


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------
class WebFetchInput(BaseModel):
    url: str = Field(..., description="The URL to fetch content from.")


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------
class WebFetchTool(Tool):
    """Fetch a web page and return its content as readable text."""

    name = "web_fetch"
    aliases = ["fetch", "curl", "webfetch"]
    search_hint = "fetch web page url http"

    def get_input_schema(self) -> dict[str, Any]:
        return WebFetchInput.model_json_schema()

    async def get_description(self, input: dict[str, Any]) -> str:
        return "Fetches a web page and returns its content as readable text."

    async def get_prompt(self, **kwargs: Any) -> str:
        return "Use web_fetch to retrieve content from a URL."

    async def validate_input(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ValidationResult:
        url = input.get("url", "")
        if not url:
            return ValidationResult(result=False, message="url is required.")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ValidationResult(
                result=False, message="Only http and https URLs are supported."
            )
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
        parsed = WebFetchInput.model_validate(args)

        try:
            import httpx
        except ImportError:
            return ToolResult(
                data=format_tool_error(
                    "httpx is not installed. Run: pip install httpx"
                )
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0
            ) as client:
                resp = await client.get(
                    parsed.url,
                    headers={"User-Agent": "ClaudeCode/1.0"},
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                data=format_tool_error(f"HTTP {exc.response.status_code}: {parsed.url}")
            )
        except httpx.RequestError as exc:
            return ToolResult(data=format_tool_error(f"Request failed: {exc}"))

        content_type = resp.headers.get("content-type", "")
        body = resp.text

        if "html" in content_type:
            body = extract_text_from_html(body)

        return ToolResult(data=truncate_output(body, MAX_OUTPUT_CHARS))

    def is_read_only(self, input: dict[str, Any]) -> bool:
        return True

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        return True

    def user_facing_name(self, input: Optional[dict[str, Any]] = None) -> str:
        return "Fetch"

    def get_tool_use_summary(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        if input:
            return f"Fetch {input.get('url', '?')}"
        return None

    def get_activity_description(self, input: Optional[dict[str, Any]] = None) -> Optional[str]:
        return "Fetching URL..."
