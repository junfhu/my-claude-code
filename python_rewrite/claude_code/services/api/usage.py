"""
Rate limit and usage information tracking.

Monitors API rate limit headers, tracks usage windows, and provides
utilities for throttling requests when approaching limits.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class RateLimitInfo:
    """Rate limit information extracted from API response headers."""

    # Request limits
    requests_limit: Optional[int] = None
    requests_remaining: Optional[int] = None
    requests_reset_at: Optional[float] = None  # Unix timestamp

    # Token limits
    tokens_limit: Optional[int] = None
    tokens_remaining: Optional[int] = None
    tokens_reset_at: Optional[float] = None

    # Input token limits
    input_tokens_limit: Optional[int] = None
    input_tokens_remaining: Optional[int] = None
    input_tokens_reset_at: Optional[float] = None

    # Output token limits
    output_tokens_limit: Optional[int] = None
    output_tokens_remaining: Optional[int] = None
    output_tokens_reset_at: Optional[float] = None

    # Retry-after
    retry_after_seconds: Optional[float] = None

    # Metadata
    extracted_at: float = field(default_factory=time.time)

    @property
    def is_rate_limited(self) -> bool:
        """True if any limit is exhausted."""
        if self.requests_remaining is not None and self.requests_remaining <= 0:
            return True
        if self.tokens_remaining is not None and self.tokens_remaining <= 0:
            return True
        if self.input_tokens_remaining is not None and self.input_tokens_remaining <= 0:
            return True
        if self.output_tokens_remaining is not None and self.output_tokens_remaining <= 0:
            return True
        return False

    @property
    def requests_utilization(self) -> Optional[float]:
        """Fraction of request limit used (0.0 to 1.0)."""
        if self.requests_limit and self.requests_remaining is not None:
            return 1.0 - (self.requests_remaining / self.requests_limit)
        return None

    @property
    def tokens_utilization(self) -> Optional[float]:
        """Fraction of token limit used."""
        if self.tokens_limit and self.tokens_remaining is not None:
            return 1.0 - (self.tokens_remaining / self.tokens_limit)
        return None

    @property
    def next_reset_seconds(self) -> Optional[float]:
        """Seconds until the next rate limit reset."""
        now = time.time()
        resets = [
            r
            for r in (
                self.requests_reset_at,
                self.tokens_reset_at,
                self.input_tokens_reset_at,
                self.output_tokens_reset_at,
            )
            if r is not None and r > now
        ]
        if resets:
            return min(resets) - now
        return None


@dataclass
class UsageWindow:
    """Token usage within a sliding time window."""

    window_seconds: float = 60.0
    _entries: List[tuple[float, int, int]] = field(default_factory=list)

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Record a usage event."""
        self._entries.append((time.time(), input_tokens, output_tokens))
        self._prune()

    def _prune(self) -> None:
        """Remove entries outside the window."""
        cutoff = time.time() - self.window_seconds
        self._entries = [(t, i, o) for t, i, o in self._entries if t >= cutoff]

    @property
    def total_input_tokens(self) -> int:
        self._prune()
        return sum(i for _, i, _ in self._entries)

    @property
    def total_output_tokens(self) -> int:
        self._prune()
        return sum(o for _, _, o in self._entries)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def request_count(self) -> int:
        self._prune()
        return len(self._entries)

    @property
    def tokens_per_minute(self) -> float:
        """Estimated tokens per minute based on current window."""
        self._prune()
        if not self._entries:
            return 0.0
        elapsed = time.time() - self._entries[0][0]
        if elapsed <= 0:
            return 0.0
        return (self.total_tokens / elapsed) * 60

    @property
    def requests_per_minute(self) -> float:
        """Estimated requests per minute based on current window."""
        self._prune()
        if not self._entries:
            return 0.0
        elapsed = time.time() - self._entries[0][0]
        if elapsed <= 0:
            return 0.0
        return (len(self._entries) / elapsed) * 60


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class UsageTracker:
    """Tracks rate limits and usage across API calls."""

    def __init__(self) -> None:
        self._last_rate_limit: Optional[RateLimitInfo] = None
        self._usage_window = UsageWindow(window_seconds=60.0)
        self._total_requests: int = 0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._throttle_until: float = 0.0

    def record_response(
        self,
        *,
        headers: Optional[Dict[str, str]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record an API response."""
        self._total_requests += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._usage_window.add(input_tokens, output_tokens)

        if headers:
            self._last_rate_limit = extract_rate_limit_info(headers)
            if self._last_rate_limit.is_rate_limited:
                logger.warning(
                    "Rate limit reached: requests_remaining=%s tokens_remaining=%s",
                    self._last_rate_limit.requests_remaining,
                    self._last_rate_limit.tokens_remaining,
                )

    def record_rate_limit_error(self, retry_after_seconds: float) -> None:
        """Record a 429 error and set throttle."""
        self._throttle_until = time.time() + retry_after_seconds

    @property
    def should_throttle(self) -> bool:
        """Whether we should wait before the next request."""
        if time.time() < self._throttle_until:
            return True
        if self._last_rate_limit and self._last_rate_limit.is_rate_limited:
            return True
        return False

    @property
    def throttle_delay_seconds(self) -> float:
        """How long to wait before the next request."""
        now = time.time()
        if now < self._throttle_until:
            return self._throttle_until - now
        if self._last_rate_limit and self._last_rate_limit.next_reset_seconds:
            return self._last_rate_limit.next_reset_seconds
        return 0.0

    @property
    def rate_limit_info(self) -> Optional[RateLimitInfo]:
        return self._last_rate_limit

    @property
    def usage_summary(self) -> Dict[str, Any]:
        """Return a usage summary."""
        return {
            "total_requests": self._total_requests,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
            "tokens_per_minute": self._usage_window.tokens_per_minute,
            "requests_per_minute": self._usage_window.requests_per_minute,
            "should_throttle": self.should_throttle,
            "throttle_delay_seconds": self.throttle_delay_seconds,
        }


# ---------------------------------------------------------------------------
# Header extraction
# ---------------------------------------------------------------------------


def extract_rate_limit_info(headers: Dict[str, str]) -> RateLimitInfo:
    """Extract rate limit information from API response headers.

    Anthropic uses headers like:
    - anthropic-ratelimit-requests-limit
    - anthropic-ratelimit-requests-remaining
    - anthropic-ratelimit-requests-reset
    - anthropic-ratelimit-tokens-limit
    - anthropic-ratelimit-tokens-remaining
    - anthropic-ratelimit-tokens-reset
    - retry-after
    """
    info = RateLimitInfo()

    def _int(key: str) -> Optional[int]:
        val = headers.get(key)
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    def _float(key: str) -> Optional[float]:
        val = headers.get(key)
        if val is not None:
            try:
                return float(val)
            except ValueError:
                pass
        return None

    def _timestamp(key: str) -> Optional[float]:
        val = headers.get(key)
        if val is not None:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.timestamp()
            except (ValueError, AttributeError):
                try:
                    return float(val)
                except ValueError:
                    pass
        return None

    prefix = "anthropic-ratelimit-"

    info.requests_limit = _int(f"{prefix}requests-limit")
    info.requests_remaining = _int(f"{prefix}requests-remaining")
    info.requests_reset_at = _timestamp(f"{prefix}requests-reset")

    info.tokens_limit = _int(f"{prefix}tokens-limit")
    info.tokens_remaining = _int(f"{prefix}tokens-remaining")
    info.tokens_reset_at = _timestamp(f"{prefix}tokens-reset")

    info.input_tokens_limit = _int(f"{prefix}input-tokens-limit")
    info.input_tokens_remaining = _int(f"{prefix}input-tokens-remaining")
    info.input_tokens_reset_at = _timestamp(f"{prefix}input-tokens-reset")

    info.output_tokens_limit = _int(f"{prefix}output-tokens-limit")
    info.output_tokens_remaining = _int(f"{prefix}output-tokens-remaining")
    info.output_tokens_reset_at = _timestamp(f"{prefix}output-tokens-reset")

    info.retry_after_seconds = _float("retry-after")

    return info
