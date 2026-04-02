"""
MCP name normalization utilities.

Pure functions with no external dependencies to avoid circular imports.
Mirrors src/services/mcp/normalization.ts.
"""

from __future__ import annotations

import re

# Claude.ai server names are prefixed with this string
CLAUDEAI_SERVER_PREFIX = "claude.ai "

# The API requires tool/server names to match this pattern
MCP_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Characters NOT in the allowed set
_INVALID_CHARS_RE = re.compile(r"[^a-zA-Z0-9_-]")

# Consecutive underscores
_MULTI_UNDERSCORE_RE = re.compile(r"_+")

# Leading/trailing underscores
_EDGE_UNDERSCORE_RE = re.compile(r"^_|_$")


def normalize_name_for_mcp(name: str) -> str:
    """Normalize a server name to be compatible with the API pattern ``^[a-zA-Z0-9_-]{1,64}$``.

    Replaces any invalid characters (including dots and spaces) with underscores.

    For claude.ai servers (names starting with ``"claude.ai "``), also collapses
    consecutive underscores and strips leading/trailing underscores to prevent
    interference with the ``__`` delimiter used in MCP tool names.
    """
    normalized = _INVALID_CHARS_RE.sub("_", name)
    if name.startswith(CLAUDEAI_SERVER_PREFIX):
        normalized = _MULTI_UNDERSCORE_RE.sub("_", normalized)
        normalized = _EDGE_UNDERSCORE_RE.sub("", normalized)
    return normalized[:64]  # enforce max length


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build a fully-qualified MCP tool name: ``mcp__{server}__{tool}``."""
    norm_server = normalize_name_for_mcp(server_name)
    norm_tool = _INVALID_CHARS_RE.sub("_", tool_name)[:64]
    return f"mcp__{norm_server}__{norm_tool}"


def parse_mcp_tool_name(qualified: str) -> tuple[str, str] | None:
    """Split ``mcp__{server}__{tool}`` → ``(server, tool)`` or ``None``."""
    if not qualified.startswith("mcp__"):
        return None
    rest = qualified[5:]
    idx = rest.find("__")
    if idx < 0:
        return None
    return rest[:idx], rest[idx + 2:]


def is_valid_mcp_name(name: str) -> bool:
    """Return True if *name* already satisfies the API name pattern."""
    return bool(MCP_NAME_PATTERN.match(name))
