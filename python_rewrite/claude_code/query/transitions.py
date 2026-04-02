"""
Loop control — transition states that determine whether the query loop
continues or terminates.

Each iteration of the query loop produces a ``LoopState`` that drives
the next step: continue to the next API call, yield and stop, retry,
compact, or abort.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class LoopAction(enum.Enum):
    """The action the loop should take after a completed iteration."""

    CONTINUE = "continue"          # Normal tool-use continuation
    STOP = "stop"                  # Model finished (end_turn / stop_sequence)
    RETRY = "retry"                # Transient error → retry the same API call
    COMPACT = "compact"            # Context too large → compact then continue
    ABORT = "abort"                # Fatal error → exit the loop
    WAIT_FOR_INPUT = "wait"        # Needs user input before continuing
    TRUNCATE_RETRY = "truncate"    # 413 / max_tokens → truncate context + retry


class StopReason(enum.Enum):
    """Why the loop stopped."""

    END_TURN = "end_turn"
    STOP_SEQUENCE = "stop_sequence"
    MAX_TOKENS = "max_tokens"
    TOOL_USE = "tool_use"
    MAX_TURNS = "max_turns"
    BUDGET_EXCEEDED = "budget_exceeded"
    ABORT_SIGNAL = "abort_signal"
    ERROR = "error"
    USER_CANCELLED = "user_cancelled"
    STOP_HOOK = "stop_hook"
    COMPACT_NEEDED = "compact_needed"


@dataclass
class LoopState:
    """Describes the current state of the query loop.

    Produced at the end of each iteration; consumed by the loop to decide
    whether to continue, stop, or perform a special action.
    """

    action: LoopAction
    stop_reason: Optional[StopReason] = None
    error: Optional[str] = None
    retry_after_ms: Optional[int] = None
    turn_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """True if the loop should exit."""
        return self.action in (LoopAction.STOP, LoopAction.ABORT)

    @property
    def should_continue(self) -> bool:
        """True if the loop should continue with another API call."""
        return self.action in (
            LoopAction.CONTINUE,
            LoopAction.RETRY,
            LoopAction.COMPACT,
            LoopAction.TRUNCATE_RETRY,
        )


# ---------------------------------------------------------------------------
# Transition functions — decide the next loop state
# ---------------------------------------------------------------------------


def determine_next_state(
    *,
    stop_reason_str: Optional[str],
    has_tool_use: bool,
    turn_index: int,
    max_turns: int,
    budget_remaining: Optional[float],
    abort_requested: bool,
    error: Optional[str] = None,
    context_tokens: int = 0,
    max_context_tokens: int = 200_000,
    compact_threshold: int = 100_000,
    stop_hook_result: Optional[str] = None,
) -> LoopState:
    """Determine the next loop state from the current iteration's outcome.

    This is the central decision function.  It is called after every API
    response (successful or not) and returns the state that the loop should
    transition into.
    """
    # ---- Priority 1: Abort signal ----
    if abort_requested:
        return LoopState(
            action=LoopAction.ABORT,
            stop_reason=StopReason.ABORT_SIGNAL,
            turn_index=turn_index,
        )

    # ---- Priority 2: Fatal error ----
    if error is not None:
        return LoopState(
            action=LoopAction.ABORT,
            stop_reason=StopReason.ERROR,
            error=error,
            turn_index=turn_index,
        )

    # ---- Priority 3: Stop hook said stop ----
    if stop_hook_result is not None:
        return LoopState(
            action=LoopAction.STOP,
            stop_reason=StopReason.STOP_HOOK,
            metadata={"hook_message": stop_hook_result},
            turn_index=turn_index,
        )

    # ---- Priority 4: Budget exceeded ----
    if budget_remaining is not None and budget_remaining <= 0:
        return LoopState(
            action=LoopAction.STOP,
            stop_reason=StopReason.BUDGET_EXCEEDED,
            turn_index=turn_index,
        )

    # ---- Priority 5: Max turns ----
    if turn_index >= max_turns:
        return LoopState(
            action=LoopAction.STOP,
            stop_reason=StopReason.MAX_TURNS,
            turn_index=turn_index,
        )

    # ---- Priority 6: Context needs compaction ----
    if context_tokens > 0 and context_tokens >= compact_threshold:
        if context_tokens >= max_context_tokens * 0.9:
            # Urgent — nearly at the hard limit
            return LoopState(
                action=LoopAction.COMPACT,
                stop_reason=StopReason.COMPACT_NEEDED,
                turn_index=turn_index,
                metadata={"context_tokens": context_tokens},
            )

    # ---- Priority 7: Interpret the API stop reason ----
    reason = _parse_stop_reason(stop_reason_str)

    if reason == StopReason.END_TURN:
        return LoopState(
            action=LoopAction.STOP,
            stop_reason=StopReason.END_TURN,
            turn_index=turn_index,
        )

    if reason == StopReason.STOP_SEQUENCE:
        return LoopState(
            action=LoopAction.STOP,
            stop_reason=StopReason.STOP_SEQUENCE,
            turn_index=turn_index,
        )

    if reason == StopReason.MAX_TOKENS:
        # Model was cut off — we need a continuation turn
        return LoopState(
            action=LoopAction.CONTINUE,
            stop_reason=StopReason.MAX_TOKENS,
            turn_index=turn_index,
            metadata={"max_tokens_hit": True},
        )

    if reason == StopReason.TOOL_USE or has_tool_use:
        return LoopState(
            action=LoopAction.CONTINUE,
            stop_reason=StopReason.TOOL_USE,
            turn_index=turn_index,
        )

    # Default: treat unknown stop reasons as terminal
    return LoopState(
        action=LoopAction.STOP,
        stop_reason=reason,
        turn_index=turn_index,
    )


def determine_retry_state(
    *,
    status_code: Optional[int],
    retry_count: int,
    max_retries: int,
    turn_index: int,
) -> LoopState:
    """Decide whether a failed API call should be retried.

    Returns a RETRY state with appropriate back-off, or ABORT if retries
    are exhausted.
    """
    if retry_count >= max_retries:
        return LoopState(
            action=LoopAction.ABORT,
            stop_reason=StopReason.ERROR,
            error=f"Max retries ({max_retries}) exceeded",
            turn_index=turn_index,
        )

    if status_code == 413:
        # Payload too large — truncate and retry
        return LoopState(
            action=LoopAction.TRUNCATE_RETRY,
            stop_reason=None,
            turn_index=turn_index,
            metadata={"status_code": 413},
        )

    # Calculate backoff
    base_ms = 1000
    if status_code == 529:
        # API overloaded — longer backoff
        base_ms = 5000
    elif status_code == 429:
        # Rate limited
        base_ms = 2000

    backoff_ms = base_ms * (2 ** retry_count)

    return LoopState(
        action=LoopAction.RETRY,
        retry_after_ms=backoff_ms,
        turn_index=turn_index,
        metadata={"retry_count": retry_count, "status_code": status_code},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_stop_reason(raw: Optional[str]) -> Optional[StopReason]:
    """Convert an API stop_reason string to our enum."""
    if raw is None:
        return None
    mapping = {
        "end_turn": StopReason.END_TURN,
        "stop_sequence": StopReason.STOP_SEQUENCE,
        "max_tokens": StopReason.MAX_TOKENS,
        "tool_use": StopReason.TOOL_USE,
    }
    return mapping.get(raw)


def is_terminal_stop_reason(reason: Optional[StopReason]) -> bool:
    """Check if a stop reason represents a terminal state."""
    return reason in (
        StopReason.END_TURN,
        StopReason.STOP_SEQUENCE,
        StopReason.MAX_TURNS,
        StopReason.BUDGET_EXCEEDED,
        StopReason.ABORT_SIGNAL,
        StopReason.ERROR,
        StopReason.USER_CANCELLED,
        StopReason.STOP_HOOK,
    )


def is_continuation_stop_reason(reason: Optional[StopReason]) -> bool:
    """Check if a stop reason means we should continue the loop."""
    return reason in (
        StopReason.TOOL_USE,
        StopReason.MAX_TOKENS,
    )
