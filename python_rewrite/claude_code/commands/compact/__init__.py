"""
/compact — Compress conversation context.

Type: local (runs locally, returns text).

Shrinks the conversation by asking the model for a summary and replacing
older messages with that summary.  Accepts optional custom summarization
instructions as an argument:  ``/compact [instructions]``
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from ...command_registry import LocalCommand, TextResult, CompactResult


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_compact_disabled() -> bool:
    return os.environ.get("DISABLE_COMPACT", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult | CompactResult:
    """
    Compact the current conversation.

    1.  Collect messages from the context.
    2.  If custom instructions are given, pass them to the summariser.
    3.  Call the compact service, which:
        a.  Runs micro-compaction (strip tool noise, long base64, etc.)
        b.  Asks the model for a summary.
        c.  Replaces old messages with the summary.
    4.  Return a CompactResult so the REPL can update its state.
    """
    messages: list[Any] = []
    if context is not None:
        messages = getattr(context, "messages", [])

    if not messages:
        return TextResult(value="No messages to compact.")

    custom_instructions = args.strip() if args else ""

    try:
        # Attempt session-memory compaction first (fast path)
        if not custom_instructions and context is not None:
            session_result = await _try_session_memory_compaction(messages, context)
            if session_result is not None:
                return session_result

        # Fall back to traditional compaction
        start = time.monotonic()
        result = await _compact_conversation(
            messages, context, custom_instructions
        )
        elapsed = time.monotonic() - start

        summary_text = result.get("summary", "")
        before = result.get("messages_before", len(messages))
        after = result.get("messages_after", 0)

        display = (
            f"Compacted conversation "
            f"({before} messages -> {after} messages, "
            f"{elapsed:.1f}s)"
        )
        if custom_instructions:
            display += f"\nCustom instructions: {custom_instructions}"

        return CompactResult(
            summary=summary_text,
            messages_before=before,
            messages_after=after,
            display_text=display,
        )

    except Exception as exc:
        # Surface aborts and known errors cleanly
        if context and getattr(getattr(context, "abort_controller", None), "aborted", False):
            return TextResult(value="Compaction canceled.")

        error_msg = str(exc)
        if "not enough messages" in error_msg.lower():
            return TextResult(value="Not enough messages to compact.")
        if "incomplete response" in error_msg.lower():
            return TextResult(value="Compaction failed: incomplete response from model.")

        return TextResult(value=f"Error during compaction: {error_msg}")


async def _try_session_memory_compaction(
    messages: list[Any], context: Any
) -> Optional[CompactResult]:
    """
    Attempt to compact via session-memory (cheap, no model call).

    Returns ``None`` when session-memory compaction is not applicable.
    """
    # Placeholder — real implementation wires into services.compact.session_memory
    return None


async def _compact_conversation(
    messages: list[Any],
    context: Any,
    custom_instructions: str,
) -> dict[str, Any]:
    """
    Run the full compaction pipeline.

    Placeholder — real implementation calls:
      1.  microcompact_messages()
      2.  compact_conversation() via the compact service
    """
    # Stub: return a synthetic result
    return {
        "summary": "Conversation compacted.",
        "messages_before": len(messages),
        "messages_after": 1,
    }


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="compact",
    description=(
        "Clear conversation history but keep a summary in context. "
        "Optional: /compact [instructions for summarization]"
    ),
    argument_hint="<optional custom summarization instructions>",
    is_enabled=lambda: not _is_compact_disabled(),
    supports_non_interactive=True,
    execute=_execute,
)
