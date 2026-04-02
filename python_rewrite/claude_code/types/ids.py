"""
Branded ID types for session, agent, task, and tool-use identifiers.

These use NewType to provide nominal typing in Python — preventing accidental
mixing of IDs at type-check time while remaining plain ``str`` at runtime.
"""

from __future__ import annotations

import re
from typing import NewType

__all__ = [
    "AgentId",
    "SessionId",
    "TaskId",
    "ToolUseId",
    "as_session_id",
    "as_agent_id",
    "to_agent_id",
]

# ---------------------------------------------------------------------------
# Branded types
# ---------------------------------------------------------------------------

SessionId = NewType("SessionId", str)
"""A session ID uniquely identifies a Claude Code session."""

AgentId = NewType("AgentId", str)
"""An agent ID uniquely identifies a subagent within a session."""

TaskId = NewType("TaskId", str)
"""A task ID uniquely identifies a background task."""

ToolUseId = NewType("ToolUseId", str)
"""A tool-use ID tracks a single invocation of a tool."""

# ---------------------------------------------------------------------------
# Constructors / validators
# ---------------------------------------------------------------------------

_AGENT_ID_PATTERN: re.Pattern[str] = re.compile(r"^a(?:.+-)?[0-9a-f]{16}$")


def as_session_id(raw: str) -> SessionId:
    """Cast a raw string to :class:`SessionId`.

    Prefer ``get_session_id()`` when possible.
    """
    return SessionId(raw)


def as_agent_id(raw: str) -> AgentId:
    """Cast a raw string to :class:`AgentId`.

    Prefer ``create_agent_id()`` when possible.
    """
    return AgentId(raw)


def to_agent_id(s: str) -> AgentId | None:
    """Validate and brand *s* as an :class:`AgentId`.

    Matches the format produced by ``create_agent_id()``:
    ``a`` + optional ``<label>-`` + 16 hex chars.
    Returns ``None`` if the string doesn't match.
    """
    return AgentId(s) if _AGENT_ID_PATTERN.match(s) else None
