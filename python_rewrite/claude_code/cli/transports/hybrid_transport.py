"""Hybrid transport: WebSocket for reads, HTTP POST for writes.

Extends WebSocketTransport with HTTP POST for outbound messages,
providing better reliability for writes (fire-and-forget callers)
while maintaining the low-latency WebSocket read path.

Write flow:
    write(stream_event) ─→ buffer (100ms) ─→ batch POST
    write(other) ─→ flush buffered + immediate POST
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable, Optional

import httpx

from .websocket_transport import WebSocketTransport

logger = logging.getLogger(__name__)

BATCH_FLUSH_INTERVAL_S = 0.1  # 100ms
POST_TIMEOUT_S = 15.0
CLOSE_GRACE_S = 3.0


class HybridTransport(WebSocketTransport):
    """Hybrid transport: WebSocket for reads, HTTP POST for writes.

    ``stream_event`` messages accumulate for up to 100ms before being
    POSTed (reduces request count for high-volume content deltas). A
    non-stream write flushes any buffered stream_events first to preserve
    ordering.

    Serialization prevents concurrent POSTs that would cause write conflicts
    on the backend (Firestore document collisions).
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        session_id: Optional[str] = None,
        *,
        auto_reconnect: bool = True,
        refresh_headers: Optional[Callable[[], dict[str, str]]] = None,
        get_auth_token: Optional[Callable[[], Optional[str]]] = None,
        max_consecutive_failures: int = 0,
    ) -> None:
        super().__init__(
            url, headers, session_id,
            auto_reconnect=auto_reconnect,
            refresh_headers=refresh_headers,
        )
        self._get_auth_token = get_auth_token
        self._post_url = self._convert_ws_to_post_url(url)
        self._max_consecutive_failures = max_consecutive_failures

        # Stream event buffer
        self._stream_buffer: list[dict[str, Any]] = []
        self._flush_task: Optional[asyncio.Task[None]] = None

        # Serialization lock — at most one POST at a time
        self._post_lock = asyncio.Lock()
        self._post_queue: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue()
        self._drain_task: Optional[asyncio.Task[None]] = None

        # Stats
        self._dropped_batches = 0
        self._consecutive_failures = 0

    @property
    def dropped_batch_count(self) -> int:
        return self._dropped_batches

    async def write(self, message: dict[str, Any]) -> None:  # type: ignore[override]
        """Enqueue a message for HTTP POST delivery."""
        if message.get("type") == "stream_event":
            self._stream_buffer.append(message)
            if self._flush_task is None:
                self._flush_task = asyncio.create_task(self._delayed_flush())
            return

        # Non-stream: flush buffered stream_events first, then this message
        events = self._take_stream_events()
        events.append(message)
        await self._enqueue_post(events)

    async def write_batch(self, messages: list[dict[str, Any]]) -> None:
        """Write multiple messages in a single POST."""
        events = self._take_stream_events()
        events.extend(messages)
        await self._enqueue_post(events)

    def _take_stream_events(self) -> list[dict[str, Any]]:
        """Drain buffered stream events and cancel the flush timer."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        buffered = self._stream_buffer
        self._stream_buffer = []
        return buffered

    async def _delayed_flush(self) -> None:
        """Flush buffered stream_events after the batch interval."""
        await asyncio.sleep(BATCH_FLUSH_INTERVAL_S)
        self._flush_task = None
        events = self._take_stream_events()
        if events:
            await self._enqueue_post(events)

    async def _enqueue_post(self, events: list[dict[str, Any]]) -> None:
        """Add events to the POST queue."""
        if not events:
            return
        await self._post_once(events)

    async def _post_once(self, events: list[dict[str, Any]]) -> None:
        """Single HTTP POST attempt with serialization."""
        token = self._get_auth_token() if self._get_auth_token else None
        if not token:
            logger.debug("HybridTransport: No auth token for POST")
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with self._post_lock:
            try:
                async with httpx.AsyncClient(timeout=POST_TIMEOUT_S) as client:
                    resp = await client.post(
                        self._post_url,
                        headers=headers,
                        json={"events": events},
                    )
                if 200 <= resp.status_code < 300:
                    self._consecutive_failures = 0
                    return
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    logger.debug(
                        "HybridTransport: POST %d (permanent), dropping",
                        resp.status_code,
                    )
                    return
                # Retryable
                logger.debug(
                    "HybridTransport: POST %d (retryable)", resp.status_code
                )
            except Exception as exc:
                logger.debug("HybridTransport: POST error: %s", exc)

            self._consecutive_failures += 1
            if (
                self._max_consecutive_failures > 0
                and self._consecutive_failures >= self._max_consecutive_failures
            ):
                self._dropped_batches += 1
                self._consecutive_failures = 0

    def close(self) -> None:
        """Close the hybrid transport."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        self._stream_buffer.clear()
        super().close()

    @staticmethod
    def _convert_ws_to_post_url(ws_url: str) -> str:
        """Convert a WebSocket URL to the HTTP POST endpoint URL.

        From: wss://api.example.com/v2/session_ingress/ws/<session_id>
        To:   https://api.example.com/v2/session_ingress/session/<session_id>/events
        """
        url = ws_url.replace("wss://", "https://").replace("ws://", "http://")
        url = url.replace("/ws/", "/session/")
        if not url.endswith("/events"):
            url = url.rstrip("/") + "/events"
        return url
