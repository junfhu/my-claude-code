"""
Automatic compaction triggers.

Monitors conversation state and triggers compaction when thresholds are
exceeded.  Supports multiple trigger strategies and integrates with the
query loop.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .compact import (
    CompactResult,
    CompactStats,
    auto_compact_check,
    compact_conversation,
    micro_compact,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AutoCompactConfig:
    """Configuration for automatic compaction behaviour."""

    enabled: bool = True
    threshold_tokens: int = 100_000
    max_context_tokens: int = 200_000
    preserve_tail_messages: int = 4

    # Strategy
    use_micro_compact_first: bool = True
    micro_compact_threshold: int = 80_000
    max_tool_result_chars: int = 2000

    # Cooldown
    cooldown_seconds: float = 30.0  # Min time between compactions
    max_compactions_per_session: int = 50

    # Model for summarization
    compact_model: Optional[str] = None  # defaults to conversation model


# ---------------------------------------------------------------------------
# AutoCompactor
# ---------------------------------------------------------------------------


class AutoCompactor:
    """Monitors conversation state and triggers compaction automatically.

    Usage::

        compactor = AutoCompactor(config)

        # After each turn:
        result = await compactor.check_and_compact(messages, model=model)
        if result.success:
            messages = result.new_messages
    """

    def __init__(
        self,
        config: Optional[AutoCompactConfig] = None,
        *,
        api_key: Optional[str] = None,
        provider: str = "anthropic",
        base_url: Optional[str] = None,
    ) -> None:
        self._config = config or AutoCompactConfig()
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url

        self._stats = CompactStats()
        self._last_compact_time: float = 0.0
        self._on_compact: Optional[Callable[[CompactResult], None]] = None

    @property
    def stats(self) -> CompactStats:
        return self._stats

    @property
    def config(self) -> AutoCompactConfig:
        return self._config

    def on_compact(self, callback: Callable[[CompactResult], None]) -> None:
        """Register a callback that fires when compaction completes."""
        self._on_compact = callback

    async def check_and_compact(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "",
        force: bool = False,
    ) -> "AutoCompactResult":
        """Check if compaction is needed and perform it if so.

        Args:
            messages: Current conversation messages.
            model: Model to use for summarization.
            system_prompt: Current system prompt.
            force: Force compaction regardless of thresholds.

        Returns:
            AutoCompactResult with the (possibly compacted) messages.
        """
        if not self._config.enabled and not force:
            return AutoCompactResult(
                compacted=False,
                messages=messages,
            )

        # Cooldown check
        if not force and self._is_in_cooldown():
            return AutoCompactResult(
                compacted=False,
                messages=messages,
                reason="cooldown",
            )

        # Max compactions check
        if (
            not force
            and self._stats.total_compactions >= self._config.max_compactions_per_session
        ):
            return AutoCompactResult(
                compacted=False,
                messages=messages,
                reason="max_compactions_reached",
            )

        # Check thresholds
        check = auto_compact_check(
            messages,
            threshold_tokens=self._config.threshold_tokens,
            max_context_tokens=self._config.max_context_tokens,
        )

        if not check["should_compact"] and not force:
            return AutoCompactResult(
                compacted=False,
                messages=messages,
                check_result=check,
            )

        # Try micro-compact first if configured
        if (
            self._config.use_micro_compact_first
            and check["estimated_tokens"] < self._config.threshold_tokens * 1.2
            and not force
        ):
            micro_result = await micro_compact(
                messages,
                max_tool_result_chars=self._config.max_tool_result_chars,
            )

            # Re-check after micro-compact
            recheck = auto_compact_check(
                micro_result,
                threshold_tokens=self._config.threshold_tokens,
                max_context_tokens=self._config.max_context_tokens,
            )

            if not recheck["should_compact"]:
                logger.info("Micro-compact sufficient, full compact not needed")
                return AutoCompactResult(
                    compacted=True,
                    messages=micro_result,
                    strategy="micro",
                    check_result=recheck,
                )

            # Micro wasn't enough, proceed with full compact on micro result
            messages = micro_result

        # Full compaction
        compact_model = self._config.compact_model or model

        start = time.time()
        compacted = await compact_conversation(
            messages,
            model=compact_model,
            api_key=self._api_key,
            system_prompt=system_prompt,
            preserve_tail=self._config.preserve_tail_messages,
            provider=self._provider,
            base_url=self._base_url,
        )

        elapsed_ms = (time.time() - start) * 1000

        if compacted is None:
            return AutoCompactResult(
                compacted=False,
                messages=messages,
                reason="compaction_failed",
            )

        # Update stats
        from ...query.token_budget import estimate_messages_tokens

        tokens_before = estimate_messages_tokens(messages)
        tokens_after = estimate_messages_tokens(compacted)
        tokens_saved = max(0, tokens_before - tokens_after)

        self._stats.total_compactions += 1
        self._stats.total_tokens_saved += tokens_saved
        self._stats.total_messages_removed += len(messages) - len(compacted)
        self._stats.last_compact_at = time.time()
        self._last_compact_time = time.time()

        result = CompactResult(
            success=True,
            messages_before=len(messages),
            messages_after=len(compacted),
            tokens_saved_estimate=tokens_saved,
            elapsed_ms=elapsed_ms,
        )

        if self._on_compact:
            try:
                self._on_compact(result)
            except Exception:
                logger.exception("on_compact callback error")

        logger.info(
            "Auto-compact: %d → %d messages, ~%d tokens saved in %.0fms",
            result.messages_before,
            result.messages_after,
            result.tokens_saved_estimate,
            result.elapsed_ms,
        )

        return AutoCompactResult(
            compacted=True,
            messages=compacted,
            strategy="full",
            compact_result=result,
        )

    def _is_in_cooldown(self) -> bool:
        """Whether we're within the cooldown period."""
        if self._last_compact_time == 0:
            return False
        return (time.time() - self._last_compact_time) < self._config.cooldown_seconds


@dataclass
class AutoCompactResult:
    """Result of an auto-compact check."""

    compacted: bool
    messages: List[Dict[str, Any]] = field(default_factory=list)
    strategy: Optional[str] = None  # "micro" | "full" | None
    reason: Optional[str] = None
    compact_result: Optional[CompactResult] = None
    check_result: Optional[Dict[str, Any]] = None
