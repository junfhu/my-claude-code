"""
Conversation compaction (summarization).

When the conversation grows too large for the context window, this module
summarizes older messages to free tokens while preserving essential context.
Supports full compaction, micro-compaction (tool results only), and
auto-compact triggers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Token threshold for triggering auto-compact
DEFAULT_COMPACT_THRESHOLD = 100_000

# Target utilisation after compaction (fraction of context window)
COMPACT_TARGET_RATIO = 0.5

# System prompt for the summarizer
COMPACT_SYSTEM_PROMPT = """\
You are a conversation summarizer. Your task is to create a concise but \
comprehensive summary of the conversation so far. The summary should capture:

1. The user's original request and intent
2. Key decisions and findings made during the conversation
3. All file modifications (which files were created, edited, or deleted)
4. Current state of the task (what has been done, what remains)
5. Any errors or issues encountered and how they were resolved
6. Important context needed to continue the conversation

Be factual, precise, and include specific file paths, function names, and \
code details that would be needed to continue the work. Do not include \
pleasantries or meta-commentary about the summarization."""

# Maximum tokens for the summary response
COMPACT_MAX_SUMMARY_TOKENS = 4096

# Messages from the end to always preserve (never compact)
PRESERVE_TAIL_COUNT = 4

# Minimum messages before we attempt compaction
MIN_MESSAGES_FOR_COMPACT = 8


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CompactResult:
    """Result of a compaction operation."""

    success: bool
    messages_before: int
    messages_after: int
    tokens_saved_estimate: int
    summary_text: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class CompactStats:
    """Statistics for compaction operations in this session."""

    total_compactions: int = 0
    total_tokens_saved: int = 0
    total_messages_removed: int = 0
    last_compact_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Main compaction functions
# ---------------------------------------------------------------------------


async def compact_conversation(
    messages: List[Dict[str, Any]],
    *,
    model: str = "claude-sonnet-4-20250514",
    api_key: Optional[str] = None,
    system_prompt: str = "",
    preserve_tail: int = PRESERVE_TAIL_COUNT,
    max_summary_tokens: int = COMPACT_MAX_SUMMARY_TOKENS,
    provider: str = "anthropic",
    base_url: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Compact a conversation by summarizing older messages.

    Preserves the last ``preserve_tail`` messages and replaces everything
    before with a summary.

    Returns:
        A new messages list with the compacted summary, or None on failure.
    """
    start = time.time()

    if len(messages) < MIN_MESSAGES_FOR_COMPACT:
        logger.debug("Too few messages (%d) for compaction", len(messages))
        return None

    # Split into prefix (to summarize) and tail (to preserve)
    if preserve_tail >= len(messages):
        preserve_tail = max(2, len(messages) // 2)

    prefix = messages[:-preserve_tail]
    tail = messages[-preserve_tail:]

    if not prefix:
        logger.debug("No messages to compact")
        return None

    # Build summarization request
    summary_messages = _build_summary_request(prefix, system_prompt)

    try:
        summary_text = await _call_summarizer(
            messages=summary_messages,
            model=model,
            api_key=api_key,
            max_tokens=max_summary_tokens,
            provider=provider,
            base_url=base_url,
        )
    except Exception as exc:
        logger.warning("Compact summarization failed: %s", exc)
        return None

    if not summary_text:
        logger.warning("Compact returned empty summary")
        return None

    # Build the compacted message list
    summary_message: Dict[str, Any] = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": (
                    "<conversation_summary>\n"
                    "The following is a summary of the conversation so far:\n\n"
                    f"{summary_text}\n"
                    "</conversation_summary>\n\n"
                    "Please continue from where we left off."
                ),
            }
        ],
        "_meta": {
            "is_compact_summary": True,
            "compacted_messages": len(prefix),
            "compacted_at": time.time(),
        },
    }

    result = [summary_message] + tail
    elapsed = (time.time() - start) * 1000

    logger.info(
        "Compacted %d → %d messages in %.0fms",
        len(messages),
        len(result),
        elapsed,
    )

    return result


async def micro_compact(
    messages: List[Dict[str, Any]],
    *,
    max_tool_result_chars: int = 2000,
) -> List[Dict[str, Any]]:
    """Micro-compact: truncate long tool results without summarizing.

    This is a cheaper alternative to full compaction that just trims
    excessively long tool output.
    """
    result: List[Dict[str, Any]] = []

    for msg in messages:
        content = msg.get("content", "")

        if isinstance(content, list):
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    block = _truncate_tool_result(block, max_tool_result_chars)
                new_content.append(block)
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)

    return result


def auto_compact_check(
    messages: List[Dict[str, Any]],
    *,
    threshold_tokens: int = DEFAULT_COMPACT_THRESHOLD,
    max_context_tokens: int = 200_000,
) -> Dict[str, Any]:
    """Check whether auto-compaction should trigger.

    Returns a dict with:
    - should_compact: bool
    - reason: str
    - estimated_tokens: int
    - utilization: float
    """
    from ...query.token_budget import estimate_messages_tokens

    estimated = estimate_messages_tokens(messages)
    utilization = estimated / max_context_tokens if max_context_tokens > 0 else 1.0

    should_compact = estimated >= threshold_tokens
    reason = ""

    if estimated >= max_context_tokens * 0.9:
        should_compact = True
        reason = f"Critical: {utilization:.0%} of context window used"
    elif estimated >= threshold_tokens:
        should_compact = True
        reason = f"Threshold crossed: {estimated:,} tokens estimated"
    elif len(messages) > 100:
        should_compact = True
        reason = f"Many messages: {len(messages)} messages in conversation"

    return {
        "should_compact": should_compact,
        "reason": reason,
        "estimated_tokens": estimated,
        "utilization": utilization,
        "message_count": len(messages),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_summary_request(
    messages: List[Dict[str, Any]],
    system_prompt: str,
) -> List[Dict[str, Any]]:
    """Build the messages list for the summarization API call."""
    # Serialize the conversation prefix as text
    conversation_text = _serialize_messages_for_summary(messages)

    return [
        {
            "role": "user",
            "content": (
                "Please summarize the following conversation. "
                "Focus on preserving all important context, decisions, "
                "file changes, and the current state of the task.\n\n"
                f"<conversation>\n{conversation_text}\n</conversation>"
            ),
        }
    ]


def _serialize_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
    """Convert messages to a text representation for summarization."""
    parts: List[str] = []

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        parts.append(f"[{role}]: {block.get('text', '')}")
                    elif block_type == "tool_use":
                        name = block.get("name", "unknown")
                        inp = block.get("input", {})
                        # Truncate large inputs
                        inp_str = json.dumps(inp, default=str)
                        if len(inp_str) > 500:
                            inp_str = inp_str[:500] + "..."
                        parts.append(f"[{role} tool_use: {name}]: {inp_str}")
                    elif block_type == "tool_result":
                        tool_id = block.get("tool_use_id", "")
                        result_content = block.get("content", "")
                        if isinstance(result_content, str):
                            text = result_content
                        elif isinstance(result_content, list):
                            text = " ".join(
                                b.get("text", "")
                                for b in result_content
                                if isinstance(b, dict)
                            )
                        else:
                            text = str(result_content)
                        # Truncate long results
                        if len(text) > 1000:
                            text = text[:1000] + "... [truncated]"
                        parts.append(f"[tool_result {tool_id}]: {text}")
                elif isinstance(block, str):
                    parts.append(f"[{role}]: {block}")

    return "\n\n".join(parts)


async def _call_summarizer(
    messages: List[Dict[str, Any]],
    model: str,
    api_key: Optional[str],
    max_tokens: int,
    provider: str,
    base_url: Optional[str],
) -> str:
    """Call the API to generate a summary."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required for compaction")

    client_kwargs: Dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    if provider == "bedrock":
        client = anthropic.AsyncAnthropicBedrock(**client_kwargs)
    elif provider == "vertex":
        client = anthropic.AsyncAnthropicVertex(**client_kwargs)
    else:
        client = anthropic.AsyncAnthropic(**client_kwargs)

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=COMPACT_SYSTEM_PROMPT,
        messages=messages,
    )

    # Extract text from response
    text_parts: List[str] = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)

    return "\n".join(text_parts)


def _truncate_tool_result(
    block: Dict[str, Any],
    max_chars: int,
) -> Dict[str, Any]:
    """Truncate a tool_result block's content if too long."""
    result = dict(block)
    content = result.get("content", "")

    if isinstance(content, str):
        if len(content) > max_chars:
            result["content"] = (
                content[:max_chars]
                + f"\n\n... [truncated {len(content) - max_chars} characters]"
            )
    elif isinstance(content, list):
        new_content = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if len(text) > max_chars:
                    item = dict(item)
                    item["text"] = (
                        text[:max_chars]
                        + f"\n\n... [truncated {len(text) - max_chars} characters]"
                    )
            new_content.append(item)
        result["content"] = new_content

    return result
