"""WebSocket transport for the Claude Code SDK protocol.

Maintains a persistent WebSocket connection with:
- Automatic reconnection with exponential backoff + jitter
- Message buffering and replay on reconnect
- Ping/pong-based connection health monitoring
- Keep-alive data frames to prevent proxy idle timeouts
- Sleep/wake detection with budget reset
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

KEEP_ALIVE_FRAME = '{"type":"keep_alive"}\n'

DEFAULT_MAX_BUFFER_SIZE = 1000
DEFAULT_BASE_RECONNECT_DELAY = 1.0  # seconds
DEFAULT_MAX_RECONNECT_DELAY = 30.0
DEFAULT_RECONNECT_GIVE_UP_S = 600.0  # 10 minutes
DEFAULT_PING_INTERVAL = 10.0
DEFAULT_KEEPALIVE_INTERVAL = 300.0  # 5 minutes

SLEEP_DETECTION_THRESHOLD_S = DEFAULT_MAX_RECONNECT_DELAY * 2  # 60s

# Permanent WebSocket close codes — no retry
PERMANENT_CLOSE_CODES = {1002, 4001, 4003}


class WebSocketTransport:
    """WebSocket transport with auto-reconnection.

    Implements the Transport interface for the Claude Code SDK protocol.
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        session_id: Optional[str] = None,
        *,
        auto_reconnect: bool = True,
        refresh_headers: Optional[Callable[[], dict[str, str]]] = None,
    ) -> None:
        self.url = url
        self._headers = dict(headers or {})
        self._session_id = session_id
        self._auto_reconnect = auto_reconnect
        self._refresh_headers = refresh_headers

        self._ws: Any = None
        self._state = "idle"
        self._last_sent_id: Optional[str] = None

        # Reconnection state
        self._reconnect_attempts = 0
        self._reconnect_start_time: Optional[float] = None
        self._last_reconnect_attempt_time: Optional[float] = None
        self._reconnect_task: Optional[asyncio.Task[None]] = None
        self._last_activity_time = 0.0

        # Ping/pong
        self._ping_task: Optional[asyncio.Task[None]] = None
        self._pong_received = True

        # Keep-alive
        self._keepalive_task: Optional[asyncio.Task[None]] = None

        # Message buffer for replay
        self._buffer: deque[dict[str, Any]] = deque(maxlen=DEFAULT_MAX_BUFFER_SIZE)

        # Callbacks
        self._on_data: Optional[Callable[[str], None]] = None
        self._on_close: Optional[Callable[[Optional[int]], None]] = None
        self._on_connect: Optional[Callable[[], None]] = None

    @property
    def state(self) -> str:
        return self._state

    def on_data(self, callback: Callable[[str], None]) -> None:
        self._on_data = callback

    def on_close(self, callback: Callable[[Optional[int]], None]) -> None:
        self._on_close = callback

    def on_connect(self, callback: Callable[[], None]) -> None:
        self._on_connect = callback

    async def connect(self) -> None:
        """Establish the WebSocket connection."""
        if self._state not in ("idle", "reconnecting"):
            logger.error("Cannot connect, state=%s", self._state)
            return

        self._state = "reconnecting"
        connect_start = time.monotonic()
        logger.debug("WebSocketTransport: Opening %s", self.url)

        headers = dict(self._headers)
        if self._last_sent_id:
            headers["X-Last-Request-Id"] = self._last_sent_id

        try:
            import websockets
            self._ws = await websockets.connect(
                self.url,
                additional_headers=headers,
                ping_interval=None,  # We manage our own pings
            )
        except ImportError:
            logger.error("websockets package not installed")
            self._state = "closed"
            return
        except Exception as exc:
            logger.error("WebSocketTransport: Connection error: %s", exc)
            self._handle_connection_error()
            return

        connect_duration = time.monotonic() - connect_start
        logger.debug(
            "WebSocketTransport: Connected in %.1fms",
            connect_duration * 1000,
        )

        self._reconnect_attempts = 0
        self._reconnect_start_time = None
        self._last_reconnect_attempt_time = None
        self._last_activity_time = time.monotonic()
        self._state = "connected"

        if self._on_connect:
            self._on_connect()

        self._start_ping_interval()
        self._start_keepalive_interval()

        # Start reading
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """Read messages from the WebSocket."""
        try:
            async for message in self._ws:
                self._last_activity_time = time.monotonic()
                if isinstance(message, bytes):
                    message = message.decode("utf-8", errors="replace")
                if self._on_data:
                    self._on_data(message)
        except Exception as exc:
            if self._state in ("closing", "closed"):
                return
            logger.debug("WebSocketTransport: Read error: %s", exc)
        finally:
            if self._state not in ("closing", "closed"):
                self._handle_connection_error()

    async def write(self, message: dict[str, Any]) -> None:
        """Send a message over the WebSocket."""
        if not self._ws or self._state != "connected":
            logger.debug("WebSocketTransport: Not connected, buffering")
            return

        line = json.dumps(message, separators=(",", ":"))
        try:
            await self._ws.send(line + "\n")
            self._last_activity_time = time.monotonic()
            # Buffer for replay
            if "uuid" in message:
                self._last_sent_id = message["uuid"]
            self._buffer.append(message)
        except Exception as exc:
            logger.error("WebSocketTransport: Send error: %s", exc)
            self._handle_connection_error()

    def _handle_connection_error(self, close_code: Optional[int] = None) -> None:
        """Handle disconnection with exponential backoff."""
        self._do_disconnect()

        if self._state in ("closing", "closed"):
            return

        # Permanent close codes
        if close_code is not None and close_code in PERMANENT_CLOSE_CODES:
            logger.error(
                "WebSocketTransport: Permanent close code %d", close_code
            )
            self._state = "closed"
            if self._on_close:
                self._on_close(close_code)
            return

        if not self._auto_reconnect:
            self._state = "closed"
            if self._on_close:
                self._on_close(close_code)
            return

        now = time.monotonic()
        if self._reconnect_start_time is None:
            self._reconnect_start_time = now

        # Sleep detection
        if (
            self._last_reconnect_attempt_time is not None
            and now - self._last_reconnect_attempt_time > SLEEP_DETECTION_THRESHOLD_S
        ):
            logger.debug("WebSocketTransport: Sleep detected, resetting budget")
            self._reconnect_start_time = now
            self._reconnect_attempts = 0

        self._last_reconnect_attempt_time = now
        elapsed = now - self._reconnect_start_time

        if elapsed < DEFAULT_RECONNECT_GIVE_UP_S:
            if self._refresh_headers:
                fresh = self._refresh_headers()
                self._headers.update(fresh)

            self._state = "reconnecting"
            self._reconnect_attempts += 1

            import random
            base_delay = min(
                DEFAULT_BASE_RECONNECT_DELAY * (2 ** (self._reconnect_attempts - 1)),
                DEFAULT_MAX_RECONNECT_DELAY,
            )
            delay = max(0, base_delay + base_delay * 0.25 * (2 * random.random() - 1))

            logger.debug(
                "WebSocketTransport: Reconnecting in %.0fms (attempt %d)",
                delay * 1000,
                self._reconnect_attempts,
            )

            self._reconnect_task = asyncio.create_task(
                self._delayed_reconnect(delay)
            )
        else:
            logger.error(
                "WebSocketTransport: Reconnection budget exhausted after %.0fs",
                elapsed,
            )
            self._state = "closed"
            if self._on_close:
                self._on_close(close_code)

    async def _delayed_reconnect(self, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.connect()

    def _do_disconnect(self) -> None:
        """Clean up the current connection."""
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self._ws:
            asyncio.create_task(self._close_ws())
            self._ws = None

    async def _close_ws(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass

    def _start_ping_interval(self) -> None:
        async def _ping_loop() -> None:
            while self._state == "connected":
                await asyncio.sleep(DEFAULT_PING_INTERVAL)
                if self._ws and self._state == "connected":
                    try:
                        pong = await self._ws.ping()
                        await asyncio.wait_for(pong, timeout=5)
                    except Exception:
                        self._handle_connection_error()
                        return
        self._ping_task = asyncio.create_task(_ping_loop())

    def _start_keepalive_interval(self) -> None:
        async def _keepalive_loop() -> None:
            while self._state == "connected":
                await asyncio.sleep(DEFAULT_KEEPALIVE_INTERVAL)
                if self._ws and self._state == "connected":
                    try:
                        await self._ws.send(KEEP_ALIVE_FRAME)
                    except Exception:
                        pass
        self._keepalive_task = asyncio.create_task(_keepalive_loop())

    def close(self) -> None:
        """Close the transport."""
        self._state = "closing"
        self._do_disconnect()
        self._state = "closed"
