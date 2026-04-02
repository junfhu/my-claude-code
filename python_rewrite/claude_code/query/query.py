"""
Core LLM conversation loop.

Implements the main agentic loop that drives Claude conversations.
This is the heart of the query pipeline: it sends messages to the API,
streams responses, executes tools, handles errors, and decides when
to continue or stop.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence

from ..cost_tracker import estimate_cost_usd
from .config import QueryConfig
from .stop_hooks import (
    StopHook,
    StopHookContext,
    build_stop_hook_context,
    run_stop_hooks,
)
from .token_budget import (
    TokenBudget,
    estimate_message_tokens,
    estimate_messages_tokens,
)
from .transitions import (
    LoopAction,
    LoopState,
    StopReason,
    determine_next_state,
    determine_retry_state,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class QueryParams:
    """Parameters for a single invocation of the query loop."""

    # Model
    model: str = "claude-sonnet-4-20250514"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    tools: List[Any] = field(default_factory=list)
    max_tokens: int = 16384
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stop_sequences: Optional[List[str]] = None

    # API
    api_key: Optional[str] = None
    provider: str = "anthropic"
    base_url: Optional[str] = None
    timeout_ms: int = 120_000

    # Retry
    retry_enabled: bool = True
    max_retries: int = 3

    # Hooks
    stop_hooks: List[Any] = field(default_factory=list)

    # Context
    permission_mode: str = "default"
    cwd: str = "."
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Budget
    max_budget_usd: Optional[float] = None
    max_turns: int = 100

    # Compact
    enable_compact: bool = True
    compact_threshold_tokens: int = 100_000

    # Callbacks (tool execution)
    tool_executor: Optional[Any] = None  # Callable[[ToolUseBlock], Awaitable[ToolResult]]

    # Running cost tracking (mutable, updated by the loop)
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class _State:
    """Mutable state carried through the query loop."""

    messages: List[Dict[str, Any]]
    turn_index: int = 0
    retry_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: float = field(default_factory=time.time)
    abort_requested: bool = False
    last_api_response: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def query(params: QueryParams) -> AsyncGenerator[Dict[str, Any], None]:
    """Public entry point for the query loop.

    Yields event dicts with ``type`` and ``data`` keys.
    """
    async for event in _query_loop(params):
        yield event


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _query_loop(params: QueryParams) -> AsyncGenerator[Dict[str, Any], None]:
    """Main while(True) conversation loop.

    Steps per iteration:
    1. Context management — normalize / trim messages
    2. API call with streaming
    3. Post-streaming — accumulate usage, run stop hooks
    4. Error recovery — handle 413 / max output tokens
    5. Tool execution — run tools, collect results
    6. Transition — decide continue / stop / compact / retry
    """
    state = _State(
        messages=list(params.messages),
        total_input_tokens=params.total_input_tokens,
        total_output_tokens=params.total_output_tokens,
        total_cost_usd=params.total_cost_usd,
    )

    # Token budget tracker
    budget = TokenBudget(max_context_tokens=200_000, max_output_tokens=params.max_tokens)
    budget.set_system_prompt(params.system_prompt)
    if params.tools:
        budget.set_tools(params.tools)
    for msg in state.messages:
        budget.add_message(msg)

    yield {"type": "loop_start", "data": {"session_id": params.session_id}}

    while True:
        # ---- 1. Context management ----
        normalised_messages = _normalise_messages(state.messages)

        # ---- 2. API call ----
        yield {
            "type": "turn_start",
            "data": {"turn_index": state.turn_index, "message_count": len(normalised_messages)},
        }

        api_response: Optional[Dict[str, Any]] = None
        assistant_message: Optional[Dict[str, Any]] = None
        api_error: Optional[Exception] = None

        try:
            collected_content: List[Dict[str, Any]] = []
            stop_reason_str: Optional[str] = None
            usage_data: Dict[str, int] = {}

            async for chunk in _stream_api_call(
                messages=normalised_messages,
                params=params,
            ):
                chunk_type = chunk.get("type", "")

                if chunk_type == "content_block_start":
                    block = chunk.get("content_block", {})
                    if block.get("type") == "text":
                        collected_content.append({"type": "text", "text": ""})
                        yield {"type": "text_start", "data": block}
                    elif block.get("type") == "tool_use":
                        collected_content.append({
                            "type": "tool_use",
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": {},
                            "_input_json": "",
                        })
                        yield {"type": "tool_use_start", "data": block}

                elif chunk_type == "content_block_delta":
                    delta = chunk.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "text_delta" and collected_content:
                        text = delta.get("text", "")
                        # Append to last text block
                        for block in reversed(collected_content):
                            if block.get("type") == "text":
                                block["text"] += text
                                break
                        yield {"type": "text_delta", "data": text}

                    elif delta_type == "input_json_delta" and collected_content:
                        partial_json = delta.get("partial_json", "")
                        for block in reversed(collected_content):
                            if block.get("type") == "tool_use":
                                block["_input_json"] += partial_json
                                break
                        yield {"type": "input_json_delta", "data": partial_json}

                elif chunk_type == "content_block_stop":
                    idx = chunk.get("index", len(collected_content) - 1)
                    if 0 <= idx < len(collected_content):
                        block = collected_content[idx]
                        if block.get("type") == "tool_use" and block.get("_input_json"):
                            try:
                                block["input"] = json.loads(block["_input_json"])
                            except json.JSONDecodeError:
                                block["input"] = {"_raw": block["_input_json"]}
                            del block["_input_json"]
                        elif block.get("type") == "tool_use":
                            block.pop("_input_json", None)

                elif chunk_type == "message_delta":
                    delta = chunk.get("delta", {})
                    stop_reason_str = delta.get("stop_reason", stop_reason_str)
                    u = chunk.get("usage", {})
                    if u:
                        usage_data.update(u)

                elif chunk_type == "message_start":
                    msg = chunk.get("message", {})
                    u = msg.get("usage", {})
                    if u:
                        usage_data.update(u)
                    yield {"type": "message_start", "data": msg}

                elif chunk_type == "error":
                    raise _APIError(
                        message=chunk.get("error", {}).get("message", "Unknown error"),
                        status_code=chunk.get("error", {}).get("status_code"),
                    )

            # Clean up tool_use blocks
            for block in collected_content:
                block.pop("_input_json", None)

            # Build the assistant message
            assistant_message = {
                "role": "assistant",
                "content": collected_content,
            }

            # Record usage
            if usage_data:
                input_tok = usage_data.get("input_tokens", 0)
                output_tok = usage_data.get("output_tokens", 0)
                cache_create = usage_data.get("cache_creation_input_tokens", 0)
                cache_read = usage_data.get("cache_read_input_tokens", 0)

                state.total_input_tokens += input_tok
                state.total_output_tokens += output_tok

                cost = estimate_cost_usd(
                    model=params.model,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    cache_creation_tokens=cache_create,
                    cache_read_tokens=cache_read,
                )
                state.total_cost_usd += cost

                budget.record_api_usage(input_tok, output_tok)

                yield {
                    "type": "usage",
                    "data": {
                        "input_tokens": input_tok,
                        "output_tokens": output_tok,
                        "cache_creation_input_tokens": cache_create,
                        "cache_read_input_tokens": cache_read,
                        "cost_usd": cost,
                        "total_cost_usd": state.total_cost_usd,
                    },
                }

            state.retry_count = 0  # Reset on success

        except _APIError as exc:
            api_error = exc
            logger.warning("API error on turn %d: %s", state.turn_index, exc)

        except Exception as exc:
            api_error = exc
            logger.exception("Unexpected error on turn %d", state.turn_index)

        # ---- 3. Handle API errors with retry ----
        if api_error is not None:
            status_code = getattr(api_error, "status_code", None)

            # Check for prompt-too-long (413)
            if status_code == 413 or _is_prompt_too_long(api_error):
                yield {
                    "type": "error",
                    "data": {
                        "message": "Prompt too long, attempting to compact...",
                        "status_code": 413,
                    },
                }
                # Try compaction
                compacted = await _try_compact(state.messages, params)
                if compacted is not None:
                    state.messages = compacted
                    budget.reset_messages()
                    for msg in state.messages:
                        budget.add_message(msg)
                    continue
                else:
                    yield {
                        "type": "error",
                        "data": {"message": "Cannot compact further. Aborting.", "fatal": True},
                    }
                    break

            if params.retry_enabled:
                retry_state = determine_retry_state(
                    status_code=status_code,
                    retry_count=state.retry_count,
                    max_retries=params.max_retries,
                    turn_index=state.turn_index,
                )
                if retry_state.action == LoopAction.RETRY:
                    state.retry_count += 1
                    delay_ms = retry_state.retry_after_ms or 1000
                    yield {
                        "type": "retry",
                        "data": {
                            "retry_count": state.retry_count,
                            "delay_ms": delay_ms,
                            "status_code": status_code,
                        },
                    }
                    await asyncio.sleep(delay_ms / 1000)
                    continue

            # Not retryable
            yield {
                "type": "error",
                "data": {
                    "message": str(api_error),
                    "status_code": status_code,
                    "fatal": True,
                },
            }
            break

        # ---- 4. Process assistant message ----
        if assistant_message is None:
            yield {"type": "error", "data": {"message": "No assistant message received", "fatal": True}}
            break

        # Add assistant message to state
        state.messages.append(assistant_message)
        budget.add_message(assistant_message)

        yield {"type": "message", "data": assistant_message}

        # ---- 5. Extract tool use blocks ----
        tool_uses = _extract_tool_uses(assistant_message)

        # ---- 6. Run stop hooks ----
        hook_ctx = build_stop_hook_context(
            messages=state.messages,
            turn_index=state.turn_index,
            total_input_tokens=state.total_input_tokens,
            total_output_tokens=state.total_output_tokens,
            total_cost_usd=state.total_cost_usd,
            model=params.model,
            session_id=params.session_id,
            started_at=state.started_at,
        )

        hook_result = await run_stop_hooks(params.stop_hooks, hook_ctx)
        stop_hook_msg = hook_result.reason if hook_result and hook_result.should_stop else None

        # ---- 7. Determine next state ----
        budget_remaining = None
        if params.max_budget_usd is not None:
            budget_remaining = params.max_budget_usd - state.total_cost_usd

        loop_state = determine_next_state(
            stop_reason_str=stop_reason_str,
            has_tool_use=bool(tool_uses),
            turn_index=state.turn_index,
            max_turns=params.max_turns,
            budget_remaining=budget_remaining,
            abort_requested=state.abort_requested,
            context_tokens=budget.effective_input_tokens,
            max_context_tokens=budget.max_context_tokens,
            compact_threshold=params.compact_threshold_tokens,
            stop_hook_result=stop_hook_msg,
        )

        # ---- 8. Act on the loop state ----
        if loop_state.is_terminal:
            yield {
                "type": "loop_stop",
                "data": {
                    "reason": loop_state.stop_reason.value if loop_state.stop_reason else "unknown",
                    "turn_index": state.turn_index,
                    "total_cost_usd": state.total_cost_usd,
                },
            }
            break

        if loop_state.action == LoopAction.COMPACT:
            yield {"type": "compact_start", "data": {"context_tokens": budget.effective_input_tokens}}
            compacted = await _try_compact(state.messages, params)
            if compacted is not None:
                state.messages = compacted
                budget.reset_messages()
                for msg in state.messages:
                    budget.add_message(msg)
                yield {"type": "compact_done", "data": {"new_message_count": len(state.messages)}}
            else:
                yield {"type": "compact_failed", "data": {}}
            # Continue regardless

        # ---- 9. Execute tools ----
        if tool_uses:
            tool_results: List[Dict[str, Any]] = []

            for tool_use in tool_uses:
                yield {
                    "type": "tool_use",
                    "data": {
                        "id": tool_use.get("id", ""),
                        "name": tool_use.get("name", ""),
                        "input": tool_use.get("input", {}),
                    },
                }

                # Execute via provided executor or default stub
                result = await _execute_tool(tool_use, params)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.get("id", ""),
                    "content": result.get("content", ""),
                    "is_error": result.get("is_error", False),
                })

                yield {
                    "type": "tool_result",
                    "data": {
                        "tool_use_id": tool_use.get("id", ""),
                        "name": tool_use.get("name", ""),
                        "content": result.get("content", ""),
                        "is_error": result.get("is_error", False),
                    },
                }

            # Append tool results as a user message
            tool_result_message = {
                "role": "user",
                "content": tool_results,
            }
            state.messages.append(tool_result_message)
            budget.add_message(tool_result_message)

        # ---- 10. Handle max_tokens continuation ----
        elif loop_state.stop_reason == StopReason.MAX_TOKENS:
            # Model was cut off — send a continuation prompt
            continuation_msg = {
                "role": "user",
                "content": [{"type": "text", "text": "Continue from where you left off."}],
            }
            state.messages.append(continuation_msg)
            budget.add_message(continuation_msg)
            yield {"type": "continuation", "data": {"reason": "max_tokens"}}

        else:
            # No tools and not max_tokens — shouldn't continue, but safety stop
            yield {
                "type": "loop_stop",
                "data": {
                    "reason": "no_action",
                    "turn_index": state.turn_index,
                },
            }
            break

        state.turn_index += 1

    # Final summary
    yield {
        "type": "loop_end",
        "data": {
            "turns": state.turn_index,
            "total_input_tokens": state.total_input_tokens,
            "total_output_tokens": state.total_output_tokens,
            "total_cost_usd": state.total_cost_usd,
        },
    }


# ---------------------------------------------------------------------------
# API streaming
# ---------------------------------------------------------------------------


async def _stream_api_call(
    *,
    messages: List[Dict[str, Any]],
    params: QueryParams,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Make a streaming API call to Claude and yield raw SSE chunks.

    Uses the anthropic Python SDK.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is required. Install it with: pip install anthropic"
        )

    # Build client
    client_kwargs: Dict[str, Any] = {}
    if params.api_key:
        client_kwargs["api_key"] = params.api_key
    if params.base_url:
        client_kwargs["base_url"] = params.base_url
    if params.timeout_ms:
        client_kwargs["timeout"] = params.timeout_ms / 1000

    if params.provider == "bedrock":
        client = anthropic.AsyncAnthropicBedrock(**client_kwargs)
    elif params.provider == "vertex":
        client = anthropic.AsyncAnthropicVertex(**client_kwargs)
    else:
        client = anthropic.AsyncAnthropic(**client_kwargs)

    # Build request kwargs
    request_kwargs: Dict[str, Any] = {
        "model": params.model,
        "max_tokens": params.max_tokens,
        "messages": messages,
    }

    if params.system_prompt:
        request_kwargs["system"] = params.system_prompt
    if params.tools:
        request_kwargs["tools"] = params.tools
    if params.temperature is not None:
        request_kwargs["temperature"] = params.temperature
    if params.top_p is not None:
        request_kwargs["top_p"] = params.top_p
    if params.stop_sequences:
        request_kwargs["stop_sequences"] = params.stop_sequences

    # Stream
    try:
        async with client.messages.stream(**request_kwargs) as stream:
            async for event in stream:
                yield _convert_sdk_event(event)
    except anthropic.APIStatusError as exc:
        yield {
            "type": "error",
            "error": {
                "message": str(exc),
                "status_code": exc.status_code,
            },
        }
    except anthropic.APIConnectionError as exc:
        yield {
            "type": "error",
            "error": {
                "message": f"Connection error: {exc}",
                "status_code": None,
            },
        }


def _convert_sdk_event(event: Any) -> Dict[str, Any]:
    """Convert an anthropic SDK streaming event to our dict format."""
    event_type = getattr(event, "type", "unknown")
    result: Dict[str, Any] = {"type": event_type}

    if event_type == "message_start":
        msg = getattr(event, "message", None)
        if msg:
            result["message"] = {
                "id": getattr(msg, "id", ""),
                "model": getattr(msg, "model", ""),
                "usage": _extract_usage_dict(getattr(msg, "usage", None)),
            }

    elif event_type == "content_block_start":
        block = getattr(event, "content_block", None)
        if block:
            result["content_block"] = {
                "type": getattr(block, "type", ""),
                "text": getattr(block, "text", "") if hasattr(block, "text") else "",
                "id": getattr(block, "id", "") if hasattr(block, "id") else "",
                "name": getattr(block, "name", "") if hasattr(block, "name") else "",
            }
        result["index"] = getattr(event, "index", 0)

    elif event_type == "content_block_delta":
        delta = getattr(event, "delta", None)
        if delta:
            result["delta"] = {
                "type": getattr(delta, "type", ""),
            }
            if hasattr(delta, "text"):
                result["delta"]["text"] = delta.text
            if hasattr(delta, "partial_json"):
                result["delta"]["partial_json"] = delta.partial_json
        result["index"] = getattr(event, "index", 0)

    elif event_type == "content_block_stop":
        result["index"] = getattr(event, "index", 0)

    elif event_type == "message_delta":
        delta = getattr(event, "delta", None)
        if delta:
            result["delta"] = {
                "stop_reason": getattr(delta, "stop_reason", None),
                "stop_sequence": getattr(delta, "stop_sequence", None),
            }
        result["usage"] = _extract_usage_dict(getattr(event, "usage", None))

    return result


def _extract_usage_dict(usage: Any) -> Dict[str, int]:
    """Extract usage info from an SDK usage object."""
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def _execute_tool(
    tool_use: Dict[str, Any],
    params: QueryParams,
) -> Dict[str, Any]:
    """Execute a single tool use block.

    If ``params.tool_executor`` is set, delegates to it.
    Otherwise, returns a placeholder error.
    """
    if params.tool_executor is not None:
        try:
            result = await params.tool_executor(tool_use)
            if isinstance(result, dict):
                return result
            return {"content": str(result), "is_error": False}
        except Exception as exc:
            logger.exception("Tool execution error for %s", tool_use.get("name"))
            return {"content": f"Error executing tool: {exc}", "is_error": True}

    # No executor — return a stub
    return {
        "content": f"Tool '{tool_use.get('name', 'unknown')}' execution not configured.",
        "is_error": True,
    }


# ---------------------------------------------------------------------------
# Message normalisation
# ---------------------------------------------------------------------------


def _normalise_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean up messages for the API.

    - Strips internal metadata (_meta keys)
    - Ensures alternating user/assistant roles
    - Merges adjacent same-role messages where needed
    """
    result: List[Dict[str, Any]] = []
    for msg in messages:
        cleaned = {k: v for k, v in msg.items() if not k.startswith("_")}
        # Skip empty messages
        content = cleaned.get("content", "")
        if not content and content != 0:
            continue
        result.append(cleaned)

    # Ensure we don't have consecutive same-role messages
    merged: List[Dict[str, Any]] = []
    for msg in result:
        if merged and merged[-1].get("role") == msg.get("role"):
            # Merge content
            prev_content = merged[-1].get("content", "")
            new_content = msg.get("content", "")
            merged[-1]["content"] = _merge_content(prev_content, new_content)
        else:
            merged.append(dict(msg))

    return merged


def _merge_content(a: Any, b: Any) -> Any:
    """Merge two content fields (string or list of blocks)."""
    a_list = a if isinstance(a, list) else [{"type": "text", "text": str(a)}] if a else []
    b_list = b if isinstance(b, list) else [{"type": "text", "text": str(b)}] if b else []
    return a_list + b_list


# ---------------------------------------------------------------------------
# Tool extraction
# ---------------------------------------------------------------------------


def _extract_tool_uses(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool_use blocks from an assistant message."""
    content = message.get("content", [])
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


async def _try_compact(
    messages: List[Dict[str, Any]],
    params: QueryParams,
) -> Optional[List[Dict[str, Any]]]:
    """Attempt to compact the message history.

    Returns the compacted messages list, or None if compaction fails.
    """
    try:
        from ..services.compact.compact import compact_conversation

        return await compact_conversation(
            messages=messages,
            model=params.model,
            api_key=params.api_key,
            system_prompt=params.system_prompt,
        )
    except ImportError:
        logger.warning("Compact service not available")
        return None
    except Exception as exc:
        logger.exception("Compaction failed")
        return None


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


class _APIError(Exception):
    """Internal API error with optional status code."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _is_prompt_too_long(error: Exception) -> bool:
    """Check if an error indicates the prompt is too long."""
    msg = str(error).lower()
    return any(
        phrase in msg
        for phrase in (
            "prompt is too long",
            "too many tokens",
            "context length exceeded",
            "maximum context length",
            "413",
        )
    )
