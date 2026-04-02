"""
Tool permission checking.

Evaluates whether a tool invocation should be allowed, denied, or
requires user confirmation based on the current permission mode,
allow-rules, and deny-rules.

Mirrors src/hooks/toolPermission/.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PermissionDecision(str, Enum):
    """Result of a permission check."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionMode(str, Enum):
    """How the agent handles tool permissions."""
    DEFAULT = "default"      # Ask for dangerous, allow safe
    PLAN = "plan"            # Read-only, ask for writes
    AUTO_ACCEPT = "auto"     # Accept all (yolo mode)
    DENY_ALL = "deny_all"    # Deny everything (headless + no rules)
    BYPASSABLE = "bypassable"  # Like default but can be bypassed


def check_tool_permission(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    mode: PermissionMode = PermissionMode.DEFAULT,
    always_allow_rules: Optional[list[str]] = None,
    always_deny_rules: Optional[list[str]] = None,
    is_headless: bool = False,
) -> PermissionDecision:
    """Check whether a tool call should be allowed.

    Decision logic:
    1. Check deny rules first (highest priority)
    2. Check allow rules
    3. Apply permission mode defaults
    """
    always_allow = always_allow_rules or []
    always_deny = always_deny_rules or []

    # Check deny rules first
    for rule in always_deny:
        if _rule_matches(rule, tool_name, tool_input):
            logger.debug("Tool %s denied by rule: %s", tool_name, rule)
            return PermissionDecision.DENY

    # Check allow rules
    for rule in always_allow:
        if _rule_matches(rule, tool_name, tool_input):
            logger.debug("Tool %s allowed by rule: %s", tool_name, rule)
            return PermissionDecision.ALLOW

    # Mode-based defaults
    if mode == PermissionMode.AUTO_ACCEPT:
        return PermissionDecision.ALLOW

    if mode == PermissionMode.DENY_ALL:
        return PermissionDecision.DENY

    if mode == PermissionMode.PLAN:
        # Plan mode: only allow read-only tools
        read_only_tools = {
            "Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch",
            "NotebookRead", "TodoRead", "ListMcpResources", "ReadMcpResource",
        }
        if tool_name in read_only_tools:
            return PermissionDecision.ALLOW
        return PermissionDecision.ASK

    if is_headless:
        return PermissionDecision.DENY

    # Default mode: safe tools are allowed, dangerous require asking
    safe_tools = {
        "Read", "Glob", "Grep", "LS", "TodoWrite",
        "ListMcpResources", "ReadMcpResource",
    }
    if tool_name in safe_tools:
        return PermissionDecision.ALLOW

    return PermissionDecision.ASK


def _rule_matches(
    rule: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> bool:
    """Check if a permission rule matches a tool invocation.

    Rules can be:
    - ``"ToolName"`` — matches any invocation of that tool
    - ``"ToolName(*)"`` — matches with any arguments
    - ``"Bash(git *)"`` — matches Bash with command matching the pattern
    - ``"Edit(src/**)"`` — matches Edit with file_path matching the pattern
    """
    # Simple tool name match
    if rule == tool_name:
        return True

    # Pattern match: ToolName(pattern)
    match = re.match(r"^(\w+)\((.+)\)$", rule)
    if not match:
        return False

    rule_tool = match.group(1)
    pattern = match.group(2)

    if rule_tool != tool_name:
        return False

    # Match based on tool type
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return _glob_match(pattern, command)
    elif tool_name in ("Edit", "Write", "MultiEdit"):
        file_path = tool_input.get("file_path", "")
        return _glob_match(pattern, file_path)
    elif tool_name in ("Read", "Glob", "Grep"):
        path = tool_input.get("path", tool_input.get("file_path", ""))
        return _glob_match(pattern, path)
    elif tool_name.startswith("mcp__"):
        # MCP tools: match by server name
        return _glob_match(pattern, tool_name)

    return pattern == "*"


def _glob_match(pattern: str, text: str) -> bool:
    """Simple glob matching with ``*`` and ``**`` support."""
    import fnmatch
    return fnmatch.fnmatch(text, pattern)
