"""
/login — OAuth login with Anthropic account.

Type: local_jsx (renders login flow).
"""

from __future__ import annotations

import os
import webbrowser
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_login_disabled() -> bool:
    return os.environ.get("DISABLE_LOGIN_COMMAND", "").lower() in (
        "1", "true", "yes",
    )


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", ""))


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Start the OAuth login flow with Anthropic.

    Opens a browser to the Anthropic OAuth endpoint and waits for the
    callback to complete authentication.
    """
    # Check if using 3P services (Bedrock/Vertex/Foundry)
    for env_var in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        if os.environ.get(env_var, "").lower() in ("1", "true", "yes"):
            return TextResult(
                value="Login is not available when using third-party API providers."
            )

    # Placeholder OAuth flow
    oauth_url = "https://console.anthropic.com/oauth/authorize"

    try:
        webbrowser.open(oauth_url)
        return TextResult(
            value="Opening browser for Anthropic login...\n\n"
            f"If the browser didn't open, visit:\n{oauth_url}\n\n"
            "Waiting for authentication to complete..."
        )
    except Exception as exc:
        return TextResult(
            value=f"Could not open browser: {exc}\n\n"
            f"Please visit: {oauth_url}"
        )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

def _login_description() -> str:
    if _has_api_key():
        return "Switch Anthropic accounts"
    return "Sign in with your Anthropic account"


command = LocalJSXCommand(
    name="login",
    description="Sign in with your Anthropic account",
    is_enabled=lambda: not _is_login_disabled(),
    call=_execute,
)
