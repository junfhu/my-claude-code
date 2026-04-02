"""
System prompt section constants and helpers.

This module contains the static constants and simple section builders.
The full system prompt construction logic lives in the prompt builder module.
"""

from __future__ import annotations

__all__ = [
    "CLAUDE_CODE_DOCS_MAP_URL",
    "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
    "FRONTIER_MODEL_NAME",
    "prepend_bullets",
]

# ============================================================================
# Prompt constants
# ============================================================================

CLAUDE_CODE_DOCS_MAP_URL: str = (
    "https://code.claude.com/docs/en/claude_code_docs_map.md"
)

SYSTEM_PROMPT_DYNAMIC_BOUNDARY: str = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"
"""Boundary marker separating static (cross-org cacheable) content from dynamic content.

Everything BEFORE this marker in the system prompt array can use ``scope: 'global'``.
Everything AFTER contains user/session-specific content and should not be cached.

WARNING: Do not remove or reorder this marker without updating cache logic.
"""

FRONTIER_MODEL_NAME: str = "Claude Opus 4.6"
"""The latest frontier model name, displayed in system prompts.

Update on model launch.
"""

# ============================================================================
# Helpers
# ============================================================================


def prepend_bullets(items: list[str | list[str]]) -> list[str]:
    """Convert a list of items into bullet-point strings.

    Top-level items get `` - `` prefix; nested lists get ``  - `` prefix.
    """
    result: list[str] = []
    for item in items:
        if isinstance(item, list):
            result.extend(f"  - {sub}" for sub in item)
        else:
            result.append(f" - {item}")
    return result
