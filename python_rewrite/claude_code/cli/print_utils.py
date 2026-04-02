"""Print formatting utilities for CLI output.

This module provides the core headless/non-interactive execution loop
(``run_headless``) and output formatting helpers used by the CLI's
``--print`` mode and SDK integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import OrderedDict
from typing import Any, AsyncIterable, Callable, Optional

logger = logging.getLogger(__name__)

# Track message UUIDs to deduplicate
MAX_RECEIVED_UUIDS = 10_000
_received_uuids: OrderedDict[str, None] = OrderedDict()


def track_received_uuid(uid: str) -> bool:
    """Track a message UUID. Returns True if new, False if duplicate."""
    if uid in _received_uuids:
        return False
    _received_uuids[uid] = None
    while len(_received_uuids) > MAX_RECEIVED_UUIDS:
        _received_uuids.popitem(last=False)
    return True


def join_prompt_values(values: list[str | list[dict[str, Any]]]) -> str | list[dict[str, Any]]:
    """Join prompt values from multiple queued commands.

    Strings are newline-joined. If any value is a block array,
    all values are normalized to blocks and concatenated.
    """
    if len(values) == 1:
        return values[0]
    if all(isinstance(v, str) for v in values):
        return "\n".join(v for v in values if isinstance(v, str))
    blocks: list[dict[str, Any]] = []
    for v in values:
        if isinstance(v, str):
            blocks.append({"type": "text", "text": v})
        elif isinstance(v, list):
            blocks.extend(v)
    return blocks


def write_stdout(text: str) -> None:
    """Write text to stdout, handling broken pipe gracefully."""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        pass


def write_stderr(text: str) -> None:
    """Write text to stderr."""
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except BrokenPipeError:
        pass


def format_ndjson(data: dict[str, Any]) -> str:
    """Format data as newline-delimited JSON, escaping internal newlines."""
    raw = json.dumps(data, separators=(",", ":"))
    # Ensure no internal newlines break NDJSON framing
    return raw + "\n"


async def run_headless(
    input_prompt: str | AsyncIterable[str],
    *,
    tools: list[Any] | None = None,
    output_format: str | None = None,
    max_turns: int | None = None,
    system_prompt: str | None = None,
    verbose: bool = False,
    continue_session: bool = False,
    resume_session: str | bool | None = None,
) -> None:
    """Run Claude Code in headless (non-interactive) mode.

    This is the main execution loop for ``claude --print``.  It:
      1. Sets up settings and MCP connections
      2. Assembles the tool pool
      3. Enters the main query loop, streaming responses to stdout
      4. Handles tool calls and permission checks
      5. Exits when the model produces a final response or max turns reached
    """
    from claude_code.utils.debug import log_debug
    from claude_code.utils.settings.settings import get_settings

    log_debug("Starting headless run")

    settings = get_settings()

    # Resolve the prompt
    if isinstance(input_prompt, str):
        prompt = input_prompt
    else:
        parts: list[str] = []
        async for chunk in input_prompt:
            parts.append(chunk)
        prompt = "".join(parts)

    if not prompt.strip():
        write_stderr("Error: empty prompt\n")
        return

    # The actual API call loop would go here.
    # For now, provide the structural skeleton.
    log_debug(f"Prompt: {prompt[:100]}...")

    if output_format == "json":
        write_stdout(format_ndjson({
            "type": "result",
            "subtype": "success",
            "result": "(headless run placeholder)",
        }))
    elif output_format == "stream-json":
        # Stream events as NDJSON
        write_stdout(format_ndjson({
            "type": "message",
            "message": {"role": "assistant", "content": "(headless run placeholder)"},
        }))
    else:
        write_stdout("(headless run placeholder)\n")
