"""
QuerySource identifies where a query originated from.

Used for analytics, retry logic, and cache control decisions.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "QuerySource",
    "KNOWN_QUERY_SOURCES",
]

QuerySource = Literal[
    "repl_main_thread",
    "sdk",
    "compact",
    "side_question",
    "agent",
    "agent:custom",
    "agent:explore",
    "agent:plan",
    "tool_use_summary",
    "advisor",
    "hook",
    "session_memory",
    "magic_docs",
    "skill_search",
    "classifier",
    "bridge",
]
"""Where a query originated from.

The TypeScript source includes ``(string & {})`` for extensibility;
in Python, callers can use ``str`` when they need to pass arbitrary values.
"""

KNOWN_QUERY_SOURCES: frozenset[str] = frozenset({
    "repl_main_thread",
    "sdk",
    "compact",
    "side_question",
    "agent",
    "agent:custom",
    "agent:explore",
    "agent:plan",
    "tool_use_summary",
    "advisor",
    "hook",
    "session_memory",
    "magic_docs",
    "skill_search",
    "classifier",
    "bridge",
})
"""Set of all known query source values, useful for runtime validation."""
