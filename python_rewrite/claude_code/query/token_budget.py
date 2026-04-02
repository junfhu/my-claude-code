"""
Token budget tracking.

Keeps track of how many tokens are available in the context window,
helps decide when to compact, and provides utilities for estimating
message sizes.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Average characters per token (approximation for English/code)
CHARS_PER_TOKEN_ESTIMATE = 3.5

# Overhead tokens for message framing, tool definitions, etc.
MESSAGE_OVERHEAD_TOKENS = 4
TOOL_DEFINITION_OVERHEAD_TOKENS = 100
SYSTEM_PROMPT_OVERHEAD_TOKENS = 10

# Minimum free tokens before we trigger compaction
MIN_FREE_TOKENS_BEFORE_COMPACT = 10_000

# Percentage of context window to target after compaction
COMPACT_TARGET_RATIO = 0.5


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TokenBudgetSnapshot:
    """Snapshot of the current token budget state."""

    max_context_tokens: int
    max_output_tokens: int
    used_input_tokens: int
    used_output_tokens: int
    estimated_message_tokens: int
    system_prompt_tokens: int
    tool_definition_tokens: int
    free_tokens: int
    utilization_ratio: float
    needs_compact: bool


@dataclass
class MessageTokenEstimate:
    """Estimated token count for a single message."""

    role: str
    estimated_tokens: int
    content_tokens: int
    overhead_tokens: int


# ---------------------------------------------------------------------------
# TokenBudget
# ---------------------------------------------------------------------------


class TokenBudget:
    """Tracks and manages the token budget for a conversation.

    The budget considers:
    - The model's context window (max_context_tokens)
    - The max output tokens per response
    - System prompt size
    - Tool definition sizes
    - Accumulated message sizes
    """

    def __init__(
        self,
        max_context_tokens: int = 200_000,
        max_output_tokens: int = 16384,
    ) -> None:
        self._max_context = max_context_tokens
        self._max_output = max_output_tokens
        self._system_prompt_tokens: int = 0
        self._tool_definition_tokens: int = 0
        self._message_token_counts: List[int] = []

        # Running total from API usage reports (authoritative)
        self._reported_input_tokens: int = 0
        self._reported_output_tokens: int = 0

    # ---- configuration ----

    def set_system_prompt(self, prompt: str) -> int:
        """Estimate and record tokens for the system prompt."""
        self._system_prompt_tokens = (
            estimate_tokens(prompt) + SYSTEM_PROMPT_OVERHEAD_TOKENS
        )
        return self._system_prompt_tokens

    def set_tools(self, tools: Sequence[Any]) -> int:
        """Estimate and record tokens for tool definitions."""
        total = 0
        for tool in tools:
            tool_str = json.dumps(tool, default=str) if not isinstance(tool, str) else tool
            total += estimate_tokens(tool_str) + TOOL_DEFINITION_OVERHEAD_TOKENS
        self._tool_definition_tokens = total
        return total

    # ---- mutation ----

    def add_message(self, message: Dict[str, Any]) -> int:
        """Estimate tokens for a message and add to the running tally."""
        tokens = estimate_message_tokens(message)
        self._message_token_counts.append(tokens)
        return tokens

    def record_api_usage(
        self,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record the authoritative token counts from an API response."""
        self._reported_input_tokens = input_tokens
        self._reported_output_tokens = output_tokens

    def remove_messages(self, count: int) -> None:
        """Remove the first *count* message token entries (e.g. after compact)."""
        self._message_token_counts = self._message_token_counts[count:]

    def reset_messages(self) -> None:
        """Clear all message token counts (e.g. after full compact)."""
        self._message_token_counts.clear()
        self._reported_input_tokens = 0
        self._reported_output_tokens = 0

    # ---- queries ----

    @property
    def max_context_tokens(self) -> int:
        return self._max_context

    @property
    def max_output_tokens(self) -> int:
        return self._max_output

    @property
    def estimated_message_tokens(self) -> int:
        """Estimated total tokens used by messages."""
        return sum(self._message_token_counts)

    @property
    def estimated_total_input(self) -> int:
        """Estimated total input tokens (messages + system + tools)."""
        return (
            self.estimated_message_tokens
            + self._system_prompt_tokens
            + self._tool_definition_tokens
        )

    @property
    def reported_input_tokens(self) -> int:
        """Last API-reported input token count."""
        return self._reported_input_tokens

    @property
    def effective_input_tokens(self) -> int:
        """Best available input token count (API-reported if available)."""
        if self._reported_input_tokens > 0:
            return self._reported_input_tokens
        return self.estimated_total_input

    @property
    def free_tokens(self) -> int:
        """Estimated tokens still available in the context window."""
        used = self.effective_input_tokens + self._max_output
        return max(0, self._max_context - used)

    @property
    def utilization_ratio(self) -> float:
        """Fraction of the context window in use (0.0 – 1.0)."""
        if self._max_context == 0:
            return 1.0
        return min(1.0, self.effective_input_tokens / self._max_context)

    @property
    def needs_compact(self) -> bool:
        """Whether the conversation should be compacted."""
        return self.free_tokens < MIN_FREE_TOKENS_BEFORE_COMPACT

    @property
    def should_auto_compact(self) -> bool:
        """Whether auto-compact threshold has been crossed."""
        return self.utilization_ratio >= 0.8

    def snapshot(self) -> TokenBudgetSnapshot:
        """Return a frozen snapshot of the current budget state."""
        return TokenBudgetSnapshot(
            max_context_tokens=self._max_context,
            max_output_tokens=self._max_output,
            used_input_tokens=self.effective_input_tokens,
            used_output_tokens=self._reported_output_tokens,
            estimated_message_tokens=self.estimated_message_tokens,
            system_prompt_tokens=self._system_prompt_tokens,
            tool_definition_tokens=self._tool_definition_tokens,
            free_tokens=self.free_tokens,
            utilization_ratio=self.utilization_ratio,
            needs_compact=self.needs_compact,
        )

    # ---- compaction helpers ----

    def tokens_to_compact(self) -> int:
        """How many message tokens should be removed by compaction."""
        if not self.needs_compact and not self.should_auto_compact:
            return 0
        target = int(self._max_context * COMPACT_TARGET_RATIO)
        current = self.effective_input_tokens
        return max(0, current - target)

    def messages_to_drop_for_target(self, target_free: int) -> int:
        """How many of the oldest messages to drop to reach *target_free* tokens."""
        needed = target_free - self.free_tokens
        if needed <= 0:
            return 0
        dropped = 0
        freed = 0
        for tokens in self._message_token_counts:
            freed += tokens
            dropped += 1
            if freed >= needed:
                break
        return dropped

    def format_budget(self) -> str:
        """Human-readable budget summary."""
        snap = self.snapshot()
        lines = [
            f"Context window: {snap.max_context_tokens:,} tokens",
            f"  System prompt: {snap.system_prompt_tokens:,}",
            f"  Tool defs:     {snap.tool_definition_tokens:,}",
            f"  Messages:      {snap.estimated_message_tokens:,}",
            f"  Max output:    {snap.max_output_tokens:,}",
            f"  Free:          {snap.free_tokens:,}",
            f"  Utilization:   {snap.utilization_ratio:.1%}",
            f"  Needs compact: {snap.needs_compact}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Rough token count estimate from character length.

    Uses 3.5 characters per token as a rule of thumb.  For more accurate
    counting, use the ``tiktoken`` or ``anthropic-tokenizer`` libraries.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN_ESTIMATE))


def estimate_message_tokens(message: Dict[str, Any]) -> int:
    """Estimate tokens for a single API message dict."""
    content = message.get("content", "")
    tokens = MESSAGE_OVERHEAD_TOKENS

    if isinstance(content, str):
        tokens += estimate_tokens(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                tokens += estimate_tokens(block)
            elif isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    tokens += estimate_tokens(block.get("text", ""))
                elif block_type == "tool_use":
                    # Tool name + JSON input
                    tokens += estimate_tokens(block.get("name", ""))
                    inp = block.get("input", {})
                    tokens += estimate_tokens(json.dumps(inp, default=str))
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        tokens += estimate_tokens(result_content)
                    elif isinstance(result_content, list):
                        for sub in result_content:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                tokens += estimate_tokens(sub.get("text", ""))
                    # tool_use_id overhead
                    tokens += 10
                elif block_type == "image":
                    # Images are roughly fixed cost
                    tokens += 1600  # ~1600 tokens for a typical image
                else:
                    tokens += estimate_tokens(json.dumps(block, default=str))
    else:
        tokens += estimate_tokens(str(content))

    return tokens


def estimate_messages_tokens(messages: Sequence[Dict[str, Any]]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(estimate_message_tokens(m) for m in messages)


def estimate_tools_tokens(tools: Sequence[Any]) -> int:
    """Estimate tokens consumed by tool definitions."""
    total = 0
    for tool in tools:
        if isinstance(tool, dict):
            total += estimate_tokens(json.dumps(tool, default=str))
        else:
            total += estimate_tokens(str(tool))
        total += TOOL_DEFINITION_OVERHEAD_TOKENS
    return total
