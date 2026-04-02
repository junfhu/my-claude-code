"""
canUseTool hook implementation.

Determines if the agent can use a specific tool based on the current
session context, permissions, and tool availability.
"""

from __future__ import annotations

from typing import Any, Optional

from .tool_permission.tool_permission import (
    PermissionDecision,
    PermissionMode,
    check_tool_permission,
)


def can_use_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    available_tools: Optional[set[str]] = None,
    mode: PermissionMode = PermissionMode.DEFAULT,
    always_allow_rules: Optional[list[str]] = None,
    always_deny_rules: Optional[list[str]] = None,
    is_headless: bool = False,
    disabled_tools: Optional[set[str]] = None,
) -> tuple[bool, PermissionDecision, Optional[str]]:
    """Check if the agent can use a specific tool.

    Returns:
        Tuple of ``(can_use, decision, reason)``:
        - ``can_use``: Whether the tool can be used without further interaction
        - ``decision``: The permission decision (allow/deny/ask)
        - ``reason``: Human-readable reason for the decision
    """
    # Check if tool exists in available set
    if available_tools is not None and tool_name not in available_tools:
        return False, PermissionDecision.DENY, f"Tool '{tool_name}' is not available"

    # Check if tool is explicitly disabled
    if disabled_tools and tool_name in disabled_tools:
        return False, PermissionDecision.DENY, f"Tool '{tool_name}' is disabled"

    # Run permission check
    decision = check_tool_permission(
        tool_name,
        tool_input,
        mode=mode,
        always_allow_rules=always_allow_rules,
        always_deny_rules=always_deny_rules,
        is_headless=is_headless,
    )

    if decision == PermissionDecision.ALLOW:
        return True, decision, None
    elif decision == PermissionDecision.DENY:
        return False, decision, f"Tool '{tool_name}' is denied by permission rules"
    else:
        return False, decision, f"Tool '{tool_name}' requires user approval"
