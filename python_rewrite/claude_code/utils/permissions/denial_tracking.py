"""
Denial tracking state.

Tracks tool permission denials to detect patterns (e.g. repeated
denials of the same tool) and surface helpful messages.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class DenialRecord:
    """A single denial event."""
    tool_name: str
    timestamp: float
    reason: str = ""
    input_summary: str = ""


class DenialTracker:
    """Tracks permission denials for pattern detection."""

    def __init__(self, *, window_s: float = 300.0, threshold: int = 3) -> None:
        self._denials: list[DenialRecord] = []
        self._by_tool: dict[str, list[DenialRecord]] = defaultdict(list)
        self._window = window_s
        self._threshold = threshold

    def record_denial(
        self,
        tool_name: str,
        *,
        reason: str = "",
        input_summary: str = "",
    ) -> None:
        """Record a new denial event."""
        record = DenialRecord(
            tool_name=tool_name,
            timestamp=time.time(),
            reason=reason,
            input_summary=input_summary,
        )
        self._denials.append(record)
        self._by_tool[tool_name].append(record)
        self._prune()

    def _prune(self) -> None:
        """Remove old records outside the time window."""
        cutoff = time.time() - self._window
        self._denials = [d for d in self._denials if d.timestamp >= cutoff]
        for tool in list(self._by_tool):
            self._by_tool[tool] = [
                d for d in self._by_tool[tool] if d.timestamp >= cutoff
            ]
            if not self._by_tool[tool]:
                del self._by_tool[tool]

    def is_repeatedly_denied(self, tool_name: str) -> bool:
        """Check if a tool has been denied repeatedly in the time window."""
        self._prune()
        return len(self._by_tool.get(tool_name, [])) >= self._threshold

    def get_denial_count(self, tool_name: str) -> int:
        self._prune()
        return len(self._by_tool.get(tool_name, []))

    def get_total_denials(self) -> int:
        self._prune()
        return len(self._denials)

    def get_most_denied_tools(self, n: int = 5) -> list[tuple[str, int]]:
        """Return the most frequently denied tools."""
        self._prune()
        counts = [(tool, len(records)) for tool, records in self._by_tool.items()]
        counts.sort(key=lambda x: x[1], reverse=True)
        return counts[:n]

    def clear(self) -> None:
        self._denials.clear()
        self._by_tool.clear()

    def get_suggestion(self, tool_name: str) -> str | None:
        """Return a suggestion if a tool is being repeatedly denied."""
        if not self.is_repeatedly_denied(tool_name):
            return None
        count = self.get_denial_count(tool_name)
        return (
            f"Tool '{tool_name}' has been denied {count} times. "
            f"Consider adding it to your allow list with: "
            f"claude config add allowedTools '{tool_name}'"
        )
