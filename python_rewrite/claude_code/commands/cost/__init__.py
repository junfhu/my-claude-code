"""
/cost — Display token usage and cost breakdown.

Type: local (runs locally, returns text).
"""

from __future__ import annotations

import os
import time
from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Cost tracking (lightweight in-process tracker)
# ---------------------------------------------------------------------------

class _CostTracker:
    """
    Singleton that accumulates token counts and estimated cost.

    The real implementation will hook into the API response headers.
    """

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.session_start: float = time.monotonic()
        self.api_calls: int = 0

    # Default pricing per 1 M tokens (Claude 3.5 Sonnet-class)
    _INPUT_COST_PER_M = 3.00
    _OUTPUT_COST_PER_M = 15.00
    _CACHE_WRITE_COST_PER_M = 3.75
    _CACHE_READ_COST_PER_M = 0.30

    def record(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation: int = 0,
        cache_read: int = 0,
    ) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_creation_tokens += cache_creation
        self.cache_read_tokens += cache_read
        self.api_calls += 1
        self.total_cost_usd += (
            input_tokens * self._INPUT_COST_PER_M
            + output_tokens * self._OUTPUT_COST_PER_M
            + cache_creation * self._CACHE_WRITE_COST_PER_M
            + cache_read * self._CACHE_READ_COST_PER_M
        ) / 1_000_000

    def format(self) -> str:
        elapsed = time.monotonic() - self.session_start
        mins, secs = divmod(int(elapsed), 60)

        lines = [
            "Session Cost Summary",
            "=" * 40,
            f"  Duration:              {mins}m {secs}s",
            f"  API calls:             {self.api_calls:,}",
            "",
            "Token Usage",
            "-" * 40,
            f"  Input tokens:          {self.input_tokens:>12,}",
            f"  Output tokens:         {self.output_tokens:>12,}",
            f"  Cache creation tokens: {self.cache_creation_tokens:>12,}",
            f"  Cache read tokens:     {self.cache_read_tokens:>12,}",
            "",
            "Estimated Cost",
            "-" * 40,
            f"  Total:                 ${self.total_cost_usd:>10.4f}",
        ]
        return "\n".join(lines)


# Module-level singleton
cost_tracker = _CostTracker()


def _is_claude_ai_subscriber() -> bool:
    return os.environ.get("CLAUDE_AI_SUBSCRIBER", "").lower() in (
        "1", "true", "yes",
    )


def _is_internal_user() -> bool:
    return os.environ.get("USER_TYPE", "") == "ant"


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """Show the total cost and duration of the current session."""
    if _is_claude_ai_subscriber():
        value = (
            "You are currently using your subscription to power "
            "your Claude Code usage."
        )
        if _is_internal_user():
            value += f"\n\n[ANT-ONLY] Showing cost anyway:\n{cost_tracker.format()}"
        return TextResult(value=value)

    return TextResult(value=cost_tracker.format())


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

def _cost_is_hidden() -> bool:
    if _is_internal_user():
        return False
    return _is_claude_ai_subscriber()


command = LocalCommand(
    name="cost",
    description="Show the total cost and duration of the current session",
    is_hidden=_cost_is_hidden,
    supports_non_interactive=True,
    execute=_execute,
)
