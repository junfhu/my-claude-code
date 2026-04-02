"""
System constants: platform detection, system prompt prefixes, and attribution.
"""

from __future__ import annotations

import os
import sys

__all__ = [
    # Prefixes
    "DEFAULT_PREFIX",
    "AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX",
    "AGENT_SDK_PREFIX",
    "CLI_SYSPROMPT_PREFIXES",
    "CLISyspromptPrefix",
    "get_cli_sysprompt_prefix",
    # Attribution
    "get_attribution_header",
]

# ============================================================================
# System prompt prefixes
# ============================================================================

DEFAULT_PREFIX: str = "You are Claude Code, Anthropic's official CLI for Claude."
AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX: str = (
    "You are Claude Code, Anthropic's official CLI for Claude, "
    "running within the Claude Agent SDK."
)
AGENT_SDK_PREFIX: str = (
    "You are a Claude agent, built on Anthropic's Claude Agent SDK."
)

CLISyspromptPrefix = str
"""Type alias for CLI system prompt prefix values."""

CLI_SYSPROMPT_PREFIXES: frozenset[str] = frozenset({
    DEFAULT_PREFIX,
    AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX,
    AGENT_SDK_PREFIX,
})
"""All possible CLI sysprompt prefix values.

Used by ``split_sys_prompt_prefix`` to identify prefix blocks by content
rather than position.
"""


def get_cli_sysprompt_prefix(
    *,
    is_non_interactive: bool = False,
    has_append_system_prompt: bool = False,
) -> str:
    """Return the appropriate system prompt prefix.

    Args:
        is_non_interactive: Whether the session is non-interactive (SDK/headless).
        has_append_system_prompt: Whether there is an appended system prompt.
    """
    if is_non_interactive:
        if has_append_system_prompt:
            return AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX
        return AGENT_SDK_PREFIX
    return DEFAULT_PREFIX


# ============================================================================
# Attribution header
# ============================================================================


def get_attribution_header(fingerprint: str) -> str:
    """Build an attribution header for API requests.

    Returns a header string with ``cc_version`` (including fingerprint) and
    ``cc_entrypoint``.  Returns ``""`` if attribution is disabled.

    Args:
        fingerprint: Build fingerprint appended to the version string.
    """
    # Check env-based killswitch
    attr_env = os.environ.get("CLAUDE_CODE_ATTRIBUTION_HEADER", "").lower()
    if attr_env in ("0", "false", "no"):
        return ""

    # In the Python rewrite we read version from the package
    version_base = os.environ.get("CLAUDE_CODE_VERSION", "0.0.0-python")
    version = f"{version_base}.{fingerprint}"
    entrypoint = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "unknown")

    header = (
        f"x-anthropic-billing-header: cc_version={version}; "
        f"cc_entrypoint={entrypoint};"
    )
    return header
