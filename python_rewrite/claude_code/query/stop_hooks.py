"""
Stop hooks — callables that run after each API turn and can force the
query loop to stop.

Each hook receives the current conversation state and returns a
``StopHookResult`` indicating whether the loop should continue or stop.
"""
from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class StopHookResult:
    """Result of a stop hook evaluation.

    Attributes:
        should_stop: Whether the loop should stop.
        reason: Human-readable reason (used in UI / logs).
        metadata: Arbitrary data the hook wants to attach.
    """

    should_stop: bool = False
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context passed to every hook
# ---------------------------------------------------------------------------


@dataclass
class StopHookContext:
    """Read-only snapshot of conversation state given to stop hooks."""

    messages: List[Dict[str, Any]]
    turn_index: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    model: str
    session_id: str
    elapsed_seconds: float
    last_assistant_message: Optional[Dict[str, Any]] = None
    last_tool_results: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class StopHook(abc.ABC):
    """Base class for stop hooks."""

    @abc.abstractmethod
    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        """Evaluate whether the loop should stop.

        Returns a StopHookResult.  Hooks MUST NOT mutate the context.
        """
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


class MaxTurnsStopHook(StopHook):
    """Stop after a maximum number of turns."""

    def __init__(self, max_turns: int = 100) -> None:
        self._max_turns = max_turns

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        if ctx.turn_index >= self._max_turns:
            return StopHookResult(
                should_stop=True,
                reason=f"Maximum number of turns ({self._max_turns}) reached.",
                metadata={"max_turns": self._max_turns, "turn_index": ctx.turn_index},
            )
        return StopHookResult()


class BudgetStopHook(StopHook):
    """Stop when a USD budget is exceeded."""

    def __init__(self, max_budget_usd: float) -> None:
        self._max_budget = max_budget_usd

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        if ctx.total_cost_usd >= self._max_budget:
            return StopHookResult(
                should_stop=True,
                reason=(
                    f"Budget limit of ${self._max_budget:.2f} reached "
                    f"(current: ${ctx.total_cost_usd:.4f})."
                ),
                metadata={
                    "max_budget_usd": self._max_budget,
                    "total_cost_usd": ctx.total_cost_usd,
                },
            )
        return StopHookResult()


class TimeoutStopHook(StopHook):
    """Stop after a maximum elapsed wall-clock time."""

    def __init__(self, max_seconds: float) -> None:
        self._max_seconds = max_seconds

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        if ctx.elapsed_seconds >= self._max_seconds:
            return StopHookResult(
                should_stop=True,
                reason=f"Timeout of {self._max_seconds:.0f}s reached.",
                metadata={
                    "max_seconds": self._max_seconds,
                    "elapsed_seconds": ctx.elapsed_seconds,
                },
            )
        return StopHookResult()


class TokenLimitStopHook(StopHook):
    """Stop when total tokens (input + output) exceed a limit."""

    def __init__(self, max_total_tokens: int) -> None:
        self._max_tokens = max_total_tokens

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        total = ctx.total_input_tokens + ctx.total_output_tokens
        if total >= self._max_tokens:
            return StopHookResult(
                should_stop=True,
                reason=f"Token limit of {self._max_tokens:,} reached (used: {total:,}).",
                metadata={
                    "max_tokens": self._max_tokens,
                    "total_tokens": total,
                },
            )
        return StopHookResult()


class EndTurnWithoutToolUseStopHook(StopHook):
    """Stop when the assistant ends its turn without using any tools.

    Useful for "answer-only" modes where we want a single response.
    """

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        msg = ctx.last_assistant_message
        if msg is None:
            return StopHookResult()

        content = msg.get("content", [])
        if isinstance(content, str):
            # Plain text with no tool use → stop
            return StopHookResult(
                should_stop=True,
                reason="Assistant responded without tool use.",
            )

        has_tool_use = any(
            isinstance(b, dict) and b.get("type") == "tool_use"
            for b in (content if isinstance(content, list) else [])
        )

        if not has_tool_use:
            return StopHookResult(
                should_stop=True,
                reason="Assistant responded without tool use.",
            )

        return StopHookResult()


class CustomCallbackStopHook(StopHook):
    """Wraps an arbitrary async callable as a stop hook."""

    def __init__(self, callback: Any, name: str = "custom") -> None:
        self._callback = callback
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def evaluate(self, ctx: StopHookContext) -> StopHookResult:
        try:
            result = await self._callback(ctx)
            if isinstance(result, StopHookResult):
                return result
            if isinstance(result, bool):
                return StopHookResult(should_stop=result, reason=self._name)
            if isinstance(result, str):
                return StopHookResult(should_stop=True, reason=result)
            return StopHookResult()
        except Exception as exc:
            logger.exception("Custom stop hook %s raised an error", self._name)
            return StopHookResult(
                should_stop=False,
                reason=f"Hook error: {exc}",
            )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_stop_hooks(
    hooks: Sequence[StopHook],
    ctx: StopHookContext,
) -> Optional[StopHookResult]:
    """Run all stop hooks and return the first one that says stop.

    If no hook says stop, returns ``None``.
    """
    for hook in hooks:
        try:
            result = await hook.evaluate(ctx)
            if result.should_stop:
                logger.info(
                    "Stop hook %s triggered: %s",
                    hook.name,
                    result.reason,
                )
                return result
        except Exception:
            logger.exception("Error running stop hook %s", hook.name)

    return None


def build_stop_hook_context(
    messages: List[Dict[str, Any]],
    turn_index: int,
    total_input_tokens: int,
    total_output_tokens: int,
    total_cost_usd: float,
    model: str,
    session_id: str,
    started_at: float,
) -> StopHookContext:
    """Build a StopHookContext from the current conversation state."""
    # Find the last assistant message
    last_assistant = None
    last_tool_results: List[Dict[str, Any]] = []

    for msg in reversed(messages):
        if msg.get("role") == "assistant" and last_assistant is None:
            last_assistant = msg
        elif msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        last_tool_results.append(block)
            if last_assistant is not None:
                break

    return StopHookContext(
        messages=messages,
        turn_index=turn_index,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost_usd=total_cost_usd,
        model=model,
        session_id=session_id,
        elapsed_seconds=time.time() - started_at,
        last_assistant_message=last_assistant,
        last_tool_results=last_tool_results if last_tool_results else None,
    )
