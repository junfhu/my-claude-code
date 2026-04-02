"""Structured I/O for the SDK protocol.

Provides a structured way to read and write SDK messages from stdio,
implementing the Claude Code SDK control protocol used for:
- Permission request/response (can_use_tool)
- Elicitation (form inputs from MCP servers)
- Session lifecycle events
- Bridge/IDE integration
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from typing import Any, AsyncIterable, Callable, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Pseudo-tool name for sandbox network permission forwarding
SANDBOX_NETWORK_ACCESS_TOOL_NAME = "SandboxNetworkAccess"

MAX_RESOLVED_TOOL_USE_IDS = 1000


class SDKControlRequest(BaseModel):
    """An outbound control_request message."""
    type: str = "control_request"
    request_id: str
    request: dict[str, Any]


class SDKControlResponse(BaseModel):
    """An inbound control_response message."""
    type: str = "control_response"
    response: dict[str, Any]


class StructuredIO:
    """Structured reader/writer for the SDK stdin/stdout protocol.

    Reads newline-delimited JSON from an async iterable (stdin or transport),
    correlates control_response messages with pending control_request calls,
    and yields user/assistant/system messages to the main loop.
    """

    def __init__(
        self,
        input_stream: AsyncIterable[str],
        *,
        replay_user_messages: bool = False,
    ) -> None:
        self._input = input_stream
        self._replay_user_messages = replay_user_messages
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._input_closed = False
        self._resolved_tool_use_ids: OrderedDict[str, None] = OrderedDict()
        self._prepended_lines: list[str] = []
        self._on_control_request_sent: Optional[Callable[[dict[str, Any]], None]] = None
        self._on_control_request_resolved: Optional[Callable[[str], None]] = None
        self._unexpected_response_callback: Optional[
            Callable[[dict[str, Any]], Any]
        ] = None
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def prepend_user_message(self, content: str) -> None:
        """Queue a synthetic user message to be yielded before real input."""
        msg = {
            "type": "user",
            "session_id": "",
            "message": {"role": "user", "content": content},
            "parent_tool_use_id": None,
        }
        self._prepended_lines.append(json.dumps(msg, separators=(",", ":")) + "\n")

    def set_unexpected_response_callback(
        self, callback: Optional[Callable[[dict[str, Any]], Any]]
    ) -> None:
        self._unexpected_response_callback = callback

    def set_on_control_request_sent(
        self, callback: Optional[Callable[[dict[str, Any]], None]]
    ) -> None:
        self._on_control_request_sent = callback

    def set_on_control_request_resolved(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        self._on_control_request_resolved = callback

    def _track_resolved_tool_use_id(self, request: dict[str, Any]) -> None:
        """Track a resolved tool_use_id to detect duplicates."""
        req = request.get("request", {})
        if req.get("subtype") == "can_use_tool":
            tool_use_id = req.get("tool_use_id", "")
            self._resolved_tool_use_ids[tool_use_id] = None
            while len(self._resolved_tool_use_ids) > MAX_RESOLVED_TOOL_USE_IDS:
                self._resolved_tool_use_ids.popitem(last=False)

    async def read(self) -> AsyncIterable[dict[str, Any]]:
        """Async generator that yields parsed messages from the input stream."""
        content = ""

        async def split_and_process():
            nonlocal content
            while True:
                if self._prepended_lines:
                    content = "".join(self._prepended_lines) + content
                    self._prepended_lines.clear()
                newline_pos = content.find("\n")
                if newline_pos == -1:
                    break
                line = content[:newline_pos]
                content = content[newline_pos + 1:]
                msg = await self._process_line(line)
                if msg is not None:
                    yield msg

        async for item in split_and_process():
            yield item

        async for block in self._input:
            content += block
            async for item in split_and_process():
                yield item

        if content:
            msg = await self._process_line(content)
            if msg is not None:
                yield msg

        self._input_closed = True
        # Reject all pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(
                    RuntimeError("Input stream closed before response received")
                )

    async def _process_line(self, line: str) -> Optional[dict[str, Any]]:
        """Parse a single JSON line and handle control messages."""
        if not line.strip():
            return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logger.error("Failed to parse input line: %s", line[:200])
            return None

        msg_type = message.get("type")

        if msg_type == "keep_alive":
            return None

        if msg_type == "update_environment_variables":
            import os
            for key, value in message.get("variables", {}).items():
                os.environ[key] = value
            return None

        if msg_type == "control_response":
            response = message.get("response", {})
            request_id = response.get("request_id", "")
            fut = self._pending.pop(request_id, None)

            if fut is None:
                # Check for duplicate
                resp_payload = (
                    response.get("response", {})
                    if response.get("subtype") == "success"
                    else {}
                )
                tool_use_id = resp_payload.get("toolUseID")
                if (
                    isinstance(tool_use_id, str)
                    and tool_use_id in self._resolved_tool_use_ids
                ):
                    logger.debug(
                        "Ignoring duplicate control_response for toolUseID=%s",
                        tool_use_id,
                    )
                    return None
                if self._unexpected_response_callback:
                    await self._unexpected_response_callback(message)
                return None

            # Notify bridge if needed
            if self._on_control_request_resolved:
                self._on_control_request_resolved(request_id)

            if response.get("subtype") == "error":
                fut.set_exception(RuntimeError(response.get("error", "Unknown error")))
            else:
                fut.set_result(response.get("response", {}))

            if self._replay_user_messages:
                return message
            return None

        if msg_type in ("user", "assistant", "system", "control_request"):
            return message

        logger.warning("Ignoring unknown message type: %s", msg_type)
        return None

    async def write(self, message: dict[str, Any]) -> None:
        """Write a message to the outbound queue (stdout)."""
        await self.outbound.put(message)

    async def send_request(
        self,
        request: dict[str, Any],
        *,
        request_id: Optional[str] = None,
    ) -> Any:
        """Send a control_request and wait for the matching response."""
        if self._input_closed:
            raise RuntimeError("Stream closed")

        rid = request_id or str(uuid.uuid4())
        message = {
            "type": "control_request",
            "request_id": rid,
            "request": request,
        }

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[rid] = fut

        await self.outbound.put(message)
        if request.get("subtype") == "can_use_tool" and self._on_control_request_sent:
            self._on_control_request_sent(message)

        try:
            return await fut
        finally:
            self._pending.pop(rid, None)

    def inject_control_response(self, response: dict[str, Any]) -> None:
        """Inject a control_response to resolve a pending permission request.

        Used by the bridge to feed permission responses from claude.ai.
        """
        resp = response.get("response", {})
        request_id = resp.get("request_id")
        if not request_id:
            return
        fut = self._pending.pop(request_id, None)
        if not fut:
            return

        if resp.get("subtype") == "error":
            fut.set_exception(RuntimeError(resp.get("error", "Unknown error")))
        else:
            fut.set_result(resp.get("response", {}))

    def get_pending_permission_requests(self) -> list[dict[str, Any]]:
        """Return pending can_use_tool requests for the bridge."""
        # We'd need to track the original request alongside the future.
        # Simplified version:
        return []

    async def drain_outbound(self, writer: Callable[[str], Any]) -> None:
        """Drain the outbound queue, writing each message as NDJSON."""
        while True:
            msg = await self.outbound.get()
            line = json.dumps(msg, separators=(",", ":")) + "\n"
            result = writer(line)
            if asyncio.iscoroutine(result):
                await result
