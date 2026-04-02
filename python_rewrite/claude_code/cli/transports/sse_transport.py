"""SSE (Server-Sent Events) transport for Claude Code.

Reads events via SSE from the CCR v2 event stream endpoint.
Writes events via HTTP POST with retry logic.
Supports automatic reconnection with exponential backoff
and Last-Event-ID for resumption after disconnection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# Reconnection config
RECONNECT_BASE_DELAY_S = 1.0
RECONNECT_MAX_DELAY_S = 30.0
RECONNECT_GIVE_UP_S = 600.0  # 10 minutes
LIVENESS_TIMEOUT_S = 45.0

PERMANENT_HTTP_CODES = {401, 403, 404}

# POST retry config
POST_MAX_RETRIES = 10
POST_BASE_DELAY_S = 0.5
POST_MAX_DELAY_S = 8.0


class SSEFrame:
    """A parsed SSE frame."""
    __slots__ = ("event", "id", "data")

    def __init__(self) -> None:
        self.event: Optional[str] = None
        self.id: Optional[str] = None
        self.data: Optional[str] = None


def parse_sse_frames(buffer: str) -> tuple[list[SSEFrame], str]:
    """Parse SSE frames from a text buffer.

    Returns (frames, remaining_buffer).
    """
    frames: list[SSEFrame] = []
    pos = 0

    while True:
        idx = buffer.find("\n\n", pos)
        if idx == -1:
            break
        raw = buffer[pos:idx]
        pos = idx + 2

        if not raw.strip():
            continue

        frame = SSEFrame()
        is_comment = False

        for line in raw.split("\n"):
            if line.startswith(":"):
                is_comment = True
                continue
            colon = line.find(":")
            if colon == -1:
                continue
            field = line[:colon]
            value = line[colon + 2:] if len(line) > colon + 1 and line[colon + 1] == " " else line[colon + 1:]

            if field == "event":
                frame.event = value
            elif field == "id":
                frame.id = value
            elif field == "data":
                frame.data = (frame.data + "\n" + value) if frame.data else value

        if frame.data or is_comment:
            frames.append(frame)

    return frames, buffer[pos:]


class StreamClientEvent:
    """Payload for ``event: client_event`` frames."""
    __slots__ = ("event_id", "sequence_num", "event_type", "source", "payload", "created_at")

    def __init__(self, data: dict[str, Any]) -> None:
        self.event_id: str = data.get("event_id", "")
        self.sequence_num: int = data.get("sequence_num", 0)
        self.event_type: str = data.get("event_type", "")
        self.source: str = data.get("source", "")
        self.payload: dict[str, Any] = data.get("payload", {})
        self.created_at: str = data.get("created_at", "")


class SSETransport:
    """Transport that uses SSE for reading and HTTP POST for writing.

    Reads events from the CCR v2 event stream; writes via HTTP POST.
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        session_id: Optional[str] = None,
        *,
        refresh_headers: Optional[Callable[[], dict[str, str]]] = None,
        get_auth_headers: Optional[Callable[[], dict[str, str]]] = None,
        initial_sequence_num: int = 0,
    ) -> None:
        self._url = url
        self._headers = dict(headers or {})
        self._session_id = session_id
        self._refresh_headers = refresh_headers
        self._get_auth_headers = get_auth_headers or (lambda: {})

        self._state = "idle"
        self._last_sequence_num = max(0, initial_sequence_num)
        self._seen_sequence_nums: set[int] = set()

        # Reconnection
        self._reconnect_attempts = 0
        self._reconnect_start_time: Optional[float] = None
        self._reconnect_task: Optional[asyncio.Task[None]] = None

        # Liveness
        self._liveness_task: Optional[asyncio.Task[None]] = None

        # POST URL derived from SSE URL
        self._post_url = self._convert_sse_to_post_url(url)

        # Callbacks
        self._on_data: Optional[Callable[[str], None]] = None
        self._on_close: Optional[Callable[[Optional[int]], None]] = None
        self._on_event: Optional[Callable[[StreamClientEvent], None]] = None

        # Abort
        self._cancel_event = asyncio.Event()

    @property
    def last_sequence_num(self) -> int:
        return self._last_sequence_num

    def on_data(self, callback: Callable[[str], None]) -> None:
        self._on_data = callback

    def on_close(self, callback: Callable[[Optional[int]], None]) -> None:
        self._on_close = callback

    def on_event(self, callback: Callable[[StreamClientEvent], None]) -> None:
        self._on_event = callback

    async def connect(self) -> None:
        """Open the SSE connection."""
        if self._state not in ("idle", "reconnecting"):
            logger.error("SSETransport: Cannot connect, state=%s", self._state)
            return

        self._state = "reconnecting"
        self._cancel_event.clear()

        sse_url = self._url
        params: dict[str, str] = {}
        if self._last_sequence_num > 0:
            params["from_sequence_num"] = str(self._last_sequence_num)

        auth_headers = self._get_auth_headers()
        headers = {
            **self._headers,
            **auth_headers,
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        }
        if self._last_sequence_num > 0:
            headers["Last-Event-ID"] = str(self._last_sequence_num)

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET", sse_url, headers=headers, params=params
                ) as response:
                    if response.status_code in PERMANENT_HTTP_CODES:
                        self._state = "closed"
                        if self._on_close:
                            self._on_close(response.status_code)
                        return

                    if response.status_code != 200:
                        self._handle_connection_error()
                        return

                    self._state = "connected"
                    self._reconnect_attempts = 0
                    self._reconnect_start_time = None
                    self._reset_liveness_timer()

                    await self._read_stream(response)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self._cancel_event.is_set():
                return
            logger.error("SSETransport: Connection error: %s", exc)
            self._handle_connection_error()

    async def _read_stream(self, response: Any) -> None:
        """Read and process the SSE stream body."""
        buffer = ""
        try:
            async for chunk in response.aiter_text():
                if self._cancel_event.is_set():
                    return
                buffer += chunk
                frames, buffer = parse_sse_frames(buffer)
                for frame in frames:
                    self._reset_liveness_timer()
                    if frame.id:
                        try:
                            seq = int(frame.id)
                            self._seen_sequence_nums.add(seq)
                            if len(self._seen_sequence_nums) > 1000:
                                threshold = self._last_sequence_num - 200
                                self._seen_sequence_nums = {
                                    s for s in self._seen_sequence_nums if s >= threshold
                                }
                            if seq > self._last_sequence_num:
                                self._last_sequence_num = seq
                        except ValueError:
                            pass
                    if frame.event and frame.data:
                        self._handle_sse_frame(frame.event, frame.data)
        except Exception as exc:
            if self._cancel_event.is_set():
                return
            logger.error("SSETransport: Stream read error: %s", exc)

        if self._state not in ("closing", "closed"):
            self._handle_connection_error()

    def _handle_sse_frame(self, event_type: str, data: str) -> None:
        if event_type != "client_event":
            logger.warning("SSETransport: Unexpected event type: %s", event_type)
            return

        try:
            ev = StreamClientEvent(json.loads(data))
        except (json.JSONDecodeError, Exception) as exc:
            logger.error("SSETransport: Parse error: %s", exc)
            return

        payload = ev.payload
        if payload and "type" in payload:
            if self._on_data:
                self._on_data(json.dumps(payload, separators=(",", ":")) + "\n")
        if self._on_event:
            self._on_event(ev)

    def _handle_connection_error(self) -> None:
        self._clear_liveness_timer()

        if self._state in ("closing", "closed"):
            return

        self._cancel_event.set()

        now = time.monotonic()
        if self._reconnect_start_time is None:
            self._reconnect_start_time = now

        elapsed = now - self._reconnect_start_time
        if elapsed < RECONNECT_GIVE_UP_S:
            if self._refresh_headers:
                fresh = self._refresh_headers()
                self._headers.update(fresh)

            self._state = "reconnecting"
            self._reconnect_attempts += 1

            base_delay = min(
                RECONNECT_BASE_DELAY_S * (2 ** (self._reconnect_attempts - 1)),
                RECONNECT_MAX_DELAY_S,
            )
            delay = max(0, base_delay + base_delay * 0.25 * (2 * random.random() - 1))

            logger.debug(
                "SSETransport: Reconnecting in %.0fms (attempt %d)",
                delay * 1000,
                self._reconnect_attempts,
            )

            self._reconnect_task = asyncio.create_task(self._delayed_reconnect(delay))
        else:
            logger.error("SSETransport: Reconnection budget exhausted")
            self._state = "closed"
            if self._on_close:
                self._on_close(None)

    async def _delayed_reconnect(self, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.connect()

    def _reset_liveness_timer(self) -> None:
        self._clear_liveness_timer()

        async def _timeout() -> None:
            await asyncio.sleep(LIVENESS_TIMEOUT_S)
            logger.error("SSETransport: Liveness timeout")
            self._cancel_event.set()
            self._handle_connection_error()

        self._liveness_task = asyncio.create_task(_timeout())

    def _clear_liveness_timer(self) -> None:
        if self._liveness_task:
            self._liveness_task.cancel()
            self._liveness_task = None

    async def write(self, message: dict[str, Any]) -> None:
        """Write a message via HTTP POST with retry."""
        auth_headers = self._get_auth_headers()
        if not auth_headers:
            return

        headers = {
            **auth_headers,
            "Content-Type": "application/json",
        }

        for attempt in range(POST_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        self._post_url,
                        headers=headers,
                        json={"events": [message]},
                    )
                if 200 <= resp.status_code < 300:
                    return
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    return  # Permanent error, don't retry
                # Retryable
            except Exception:
                pass

            delay = min(POST_BASE_DELAY_S * (2 ** attempt), POST_MAX_DELAY_S)
            jitter = delay * 0.25 * (2 * random.random() - 1)
            await asyncio.sleep(delay + jitter)

    def close(self) -> None:
        """Close the transport."""
        self._state = "closing"
        self._cancel_event.set()
        self._clear_liveness_timer()
        if self._reconnect_task:
            self._reconnect_task.cancel()
        self._state = "closed"

    @staticmethod
    def _convert_sse_to_post_url(sse_url: str) -> str:
        """Convert an SSE URL to the HTTP POST endpoint URL."""
        url = sse_url.replace("/stream/", "/session/")
        if not url.endswith("/events"):
            url = url.rstrip("/") + "/events"
        return url
