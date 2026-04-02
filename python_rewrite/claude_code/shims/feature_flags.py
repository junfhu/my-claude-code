"""
Feature flags -- read from environment variables at runtime.

Replaces the ``bun:bundle`` ``feature()`` macro from the TypeScript build
with a runtime environment variable lookup.  Each feature flag maps to a
``CLAUDE_CODE_<NAME>`` environment variable.

Usage::

    from claude_code.shims.feature_flags import feature

    if feature("VOICE_MODE"):
        enable_voice_input()

    if feature("BG_SESSIONS"):
        start_background_session_manager()

Feature flags are considered enabled when their environment variable is
set to one of: ``1``, ``true``, ``yes`` (case-insensitive).  Any other
value (including empty string or unset) is treated as disabled.

The mapping table below contains all known feature flags.  Unknown flags
fall back to ``CLAUDE_CODE_{name}`` as a convention, making it easy to
add new flags without modifying this file.
"""

from __future__ import annotations

import os
from typing import Final

# ---------------------------------------------------------------------------
# Feature flag -> environment variable mapping
# ---------------------------------------------------------------------------

_ENV_MAP: Final[dict[str, str]] = {
    "VOICE_MODE": "CLAUDE_CODE_VOICE_MODE",
    "BRIDGE_MODE": "CLAUDE_CODE_BRIDGE_MODE",
    "DAEMON": "CLAUDE_CODE_DAEMON",
    "BG_SESSIONS": "CLAUDE_CODE_BG_SESSIONS",
    "PROACTIVE": "CLAUDE_CODE_PROACTIVE",
    "COORDINATOR_MODE": "CLAUDE_CODE_COORDINATOR_MODE",
    "WORKFLOW_SCRIPTS": "CLAUDE_CODE_WORKFLOW_SCRIPTS",
    "ULTRAPLAN": "CLAUDE_CODE_ULTRAPLAN",
    "HISTORY_SNIP": "CLAUDE_CODE_HISTORY_SNIP",
    "MONITOR_TOOL": "CLAUDE_CODE_MONITOR_TOOL",
    "WEB_BROWSER_TOOL": "CLAUDE_CODE_WEB_BROWSER_TOOL",
    "AGENT_TRIGGERS": "CLAUDE_CODE_AGENT_TRIGGERS",
    "KAIROS": "CLAUDE_CODE_KAIROS",
    "TOKEN_BUDGET": "CLAUDE_CODE_TOKEN_BUDGET",
    "TRANSCRIPT_CLASSIFIER": "CLAUDE_CODE_TRANSCRIPT_CLASSIFIER",
    "BREAK_CACHE_COMMAND": "CLAUDE_CODE_BREAK_CACHE_COMMAND",
    "CHICAGO_MCP": "CLAUDE_CODE_CHICAGO_MCP",
    "ENABLE_AGENT_SWARMS": "CLAUDE_CODE_ENABLE_AGENT_SWARMS",
    "FAST_MODE": "CLAUDE_CODE_FAST_MODE",
    "SKILL_IMPROVEMENT": "CLAUDE_CODE_SKILL_IMPROVEMENT",
    "PROMPT_SUGGESTION": "CLAUDE_CODE_PROMPT_SUGGESTION",
    "SPECULATION": "CLAUDE_CODE_SPECULATION",
    "LSP": "CLAUDE_CODE_LSP",
}

# Values considered truthy for feature flags
_TRUTHY_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes"})


def feature(name: str) -> bool:
    """Check if a feature flag is enabled.

    Looks up the corresponding environment variable for the given feature
    name and returns ``True`` if it's set to a truthy value (``1``,
    ``true``, or ``yes``, case-insensitive).

    Args:
        name: Feature flag name (e.g. ``"VOICE_MODE"``, ``"BG_SESSIONS"``).

    Returns:
        ``True`` if the feature is enabled, ``False`` otherwise.

    Examples::

        >>> import os
        >>> os.environ["CLAUDE_CODE_VOICE_MODE"] = "1"
        >>> feature("VOICE_MODE")
        True
        >>> feature("NONEXISTENT_FLAG")
        False
    """
    env_var = _ENV_MAP.get(name, f"CLAUDE_CODE_{name}")
    return os.environ.get(env_var, "").lower() in _TRUTHY_VALUES


def is_enabled(name: str) -> bool:
    """Alias for ``feature()`` with a more descriptive name."""
    return feature(name)


def get_feature_env_var(name: str) -> str:
    """Return the environment variable name for a feature flag.

    Useful for documentation and diagnostics.

    Args:
        name: Feature flag name.

    Returns:
        The corresponding environment variable name.
    """
    return _ENV_MAP.get(name, f"CLAUDE_CODE_{name}")


def list_known_features() -> list[str]:
    """Return a sorted list of all known feature flag names."""
    return sorted(_ENV_MAP.keys())


def get_enabled_features() -> list[str]:
    """Return a sorted list of currently enabled feature flags.

    Checks all known features and returns only those that are enabled.
    """
    return sorted(name for name in _ENV_MAP if feature(name))


__all__ = [
    "feature",
    "get_enabled_features",
    "get_feature_env_var",
    "is_enabled",
    "list_known_features",
]
