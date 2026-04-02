"""
Retry logic with exponential backoff for Anthropic API calls.

Provides an async generator wrapper that automatically retries failed API
calls with configurable backoff, jitter, and per-status-code handling.
Differentiates between 429 (rate limit) and 529 (overloaded) with separate
backoff strategies.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, Optional, TypeVar

from .errors import (
    APIErrorType,
    ClassifiedError,
    classify_api_error,
    is_retryable_error,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry behaviour."""

    max_retries: int = 3
    base_delay_ms: int = 1000
    max_delay_ms: int = 60_000
    backoff_factor: float = 2.0
    jitter_factor: float = 0.25
    persistent_mode: bool = False  # Never give up

    # Per-status overrides
    rate_limit_base_delay_ms: int = 2000      # 429
    overloaded_base_delay_ms: int = 5000      # 529
    server_error_base_delay_ms: int = 3000    # 5xx
    timeout_base_delay_ms: int = 1000

    # If True, respects Retry-After header from the API
    respect_retry_after: bool = True


@dataclass
class RetryState:
    """Mutable state tracking retries."""

    attempt: int = 0
    total_delay_ms: int = 0
    last_error: Optional[Exception] = None
    last_error_type: Optional[APIErrorType] = None
    started_at: float = field(default_factory=time.time)
    history: list = field(default_factory=list)


@dataclass
class RetryEvent:
    """An event emitted by the retry wrapper."""

    type: str  # "attempt" | "retry" | "success" | "exhausted"
    attempt: int
    delay_ms: int = 0
    error: Optional[str] = None
    error_type: Optional[str] = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# Main retry wrapper
# ---------------------------------------------------------------------------


async def with_retry(
    fn: Callable[..., Any],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> AsyncGenerator[RetryEvent, None]:
    """Execute an async function with retry logic, yielding events.

    Usage::

        async for event in with_retry(api_call, messages, config=retry_config):
            if event.type == "success":
                result = event.data
            elif event.type == "retry":
                print(f"Retrying in {event.delay_ms}ms...")
            elif event.type == "exhausted":
                print(f"All retries failed: {event.error}")

    The last yielded event is always either "success" or "exhausted".
    """
    if config is None:
        config = RetryConfig()

    state = RetryState()
    max_attempts = config.max_retries + 1 if not config.persistent_mode else float("inf")

    while state.attempt < max_attempts:
        state.attempt += 1
        elapsed = (time.time() - state.started_at) * 1000

        yield RetryEvent(
            type="attempt",
            attempt=state.attempt,
            elapsed_ms=elapsed,
        )

        try:
            result = await fn(*args, **kwargs)

            yield RetryEvent(
                type="success",
                attempt=state.attempt,
                elapsed_ms=(time.time() - state.started_at) * 1000,
            )
            return

        except Exception as exc:
            classified = classify_api_error(exc)
            state.last_error = exc
            state.last_error_type = classified.error_type
            state.history.append({
                "attempt": state.attempt,
                "error_type": classified.error_type.value,
                "message": classified.message,
                "status_code": classified.status_code,
                "timestamp": time.time(),
            })

            # Non-retryable error → bail immediately
            if not classified.retryable and not config.persistent_mode:
                yield RetryEvent(
                    type="exhausted",
                    attempt=state.attempt,
                    error=classified.message,
                    error_type=classified.error_type.value,
                    elapsed_ms=(time.time() - state.started_at) * 1000,
                )
                return

            # Calculate delay
            delay_ms = _calculate_delay(
                config=config,
                classified=classified,
                attempt=state.attempt,
            )
            state.total_delay_ms += delay_ms

            # Check if we've exhausted retries
            if state.attempt >= max_attempts:
                yield RetryEvent(
                    type="exhausted",
                    attempt=state.attempt,
                    error=classified.message,
                    error_type=classified.error_type.value,
                    elapsed_ms=(time.time() - state.started_at) * 1000,
                )
                return

            yield RetryEvent(
                type="retry",
                attempt=state.attempt,
                delay_ms=delay_ms,
                error=classified.message,
                error_type=classified.error_type.value,
                elapsed_ms=(time.time() - state.started_at) * 1000,
            )

            await asyncio.sleep(delay_ms / 1000)


async def with_retry_simple(
    fn: Callable[..., Any],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry logic, returning the result.

    Simpler API than ``with_retry()`` — doesn't yield events, just returns
    the result or raises the last error.
    """
    if config is None:
        config = RetryConfig()

    last_error: Optional[Exception] = None

    max_attempts = config.max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            classified = classify_api_error(exc)

            if not classified.retryable:
                raise

            if attempt >= max_attempts:
                raise

            delay_ms = _calculate_delay(
                config=config,
                classified=classified,
                attempt=attempt,
            )

            logger.info(
                "Retry %d/%d after %dms (error: %s)",
                attempt,
                config.max_retries,
                delay_ms,
                classified.error_type.value,
            )

            await asyncio.sleep(delay_ms / 1000)

    # Should not reach here, but just in case
    if last_error:
        raise last_error
    raise RuntimeError("Retry loop exited without result or error")


# ---------------------------------------------------------------------------
# Delay calculation
# ---------------------------------------------------------------------------


def _calculate_delay(
    *,
    config: RetryConfig,
    classified: ClassifiedError,
    attempt: int,
) -> int:
    """Calculate the retry delay in milliseconds.

    Uses exponential backoff with jitter.  Different error types get
    different base delays.
    """
    # 1. Choose base delay based on error type
    base_ms = config.base_delay_ms

    if classified.error_type == APIErrorType.RATE_LIMIT:
        base_ms = config.rate_limit_base_delay_ms
    elif classified.error_type == APIErrorType.OVERLOADED:
        base_ms = config.overloaded_base_delay_ms
    elif classified.error_type == APIErrorType.SERVER_ERROR:
        base_ms = config.server_error_base_delay_ms
    elif classified.error_type == APIErrorType.TIMEOUT:
        base_ms = config.timeout_base_delay_ms

    # 2. Check for Retry-After header
    if config.respect_retry_after and classified.retry_after_ms:
        # Use the server's suggestion if it's larger
        base_ms = max(base_ms, classified.retry_after_ms)

    # 3. Exponential backoff
    delay_ms = base_ms * (config.backoff_factor ** (attempt - 1))

    # 4. Add jitter
    if config.jitter_factor > 0:
        jitter_range = delay_ms * config.jitter_factor
        delay_ms += random.uniform(-jitter_range, jitter_range)

    # 5. Clamp to max
    delay_ms = min(delay_ms, config.max_delay_ms)
    delay_ms = max(delay_ms, 0)

    return int(delay_ms)


# ---------------------------------------------------------------------------
# Convenience: wrapping a streaming call
# ---------------------------------------------------------------------------


async def retry_streaming(
    stream_fn: Callable[..., AsyncGenerator],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> AsyncGenerator[Any, None]:
    """Retry a streaming async generator function.

    On failure, re-invokes the generator from the start.  This means
    the caller may see duplicate events if the stream partially succeeded.
    """
    if config is None:
        config = RetryConfig()

    last_error: Optional[Exception] = None
    max_attempts = config.max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async for item in stream_fn(*args, **kwargs):
                yield item
            return  # Stream completed successfully
        except Exception as exc:
            last_error = exc
            classified = classify_api_error(exc)

            if not classified.retryable or attempt >= max_attempts:
                raise

            delay_ms = _calculate_delay(
                config=config,
                classified=classified,
                attempt=attempt,
            )

            logger.info(
                "Retrying stream %d/%d after %dms",
                attempt,
                config.max_retries,
                delay_ms,
            )

            await asyncio.sleep(delay_ms / 1000)

    if last_error:
        raise last_error
