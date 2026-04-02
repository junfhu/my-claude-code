"""
Event logging with queue-before-sink pattern.

Provides a structured event logging system for analytics.  Events are
queued in memory and flushed to registered sinks (file, HTTP, etc.)
asynchronously to avoid blocking the main conversation loop.
"""
from __future__ import annotations

import abc
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass
class AnalyticsEvent:
    """A single analytics event."""

    event_type: str  # e.g. "api_call", "tool_use", "error", "session_start"
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Sinks (destinations for events)
# ---------------------------------------------------------------------------


class AnalyticsSink(abc.ABC):
    """Base class for analytics sinks."""

    @abc.abstractmethod
    async def send(self, events: List[AnalyticsEvent]) -> bool:
        """Send a batch of events.  Returns True on success."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__


class FileSink(AnalyticsSink):
    """Writes analytics events to a JSONL file."""

    def __init__(self, directory: Optional[str] = None) -> None:
        self._dir = Path(directory) if directory else Path.home() / ".claude" / "analytics"

    async def send(self, events: List[AnalyticsEvent]) -> bool:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            file_path = self._dir / "events.jsonl"
            with open(file_path, "a", encoding="utf-8") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict(), default=str) + "\n")
            return True
        except OSError as exc:
            logger.warning("FileSink write failed: %s", exc)
            return False

    async def close(self) -> None:
        pass


class HttpSink(AnalyticsSink):
    """Sends analytics events to an HTTP endpoint."""

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout_seconds

    async def send(self, events: List[AnalyticsEvent]) -> bool:
        try:
            import httpx

            payload = [event.to_dict() for event in events]
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url,
                    json=payload,
                    headers=self._headers,
                )
                return 200 <= response.status_code < 300
        except ImportError:
            logger.warning("httpx not available for HttpSink")
            return False
        except Exception as exc:
            logger.debug("HttpSink send failed: %s", exc)
            return False

    async def close(self) -> None:
        pass


class CallbackSink(AnalyticsSink):
    """Sends events to a callback function."""

    def __init__(self, callback: Callable[[List[AnalyticsEvent]], None]) -> None:
        self._callback = callback

    async def send(self, events: List[AnalyticsEvent]) -> bool:
        try:
            self._callback(events)
            return True
        except Exception as exc:
            logger.warning("CallbackSink error: %s", exc)
            return False

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Analytics manager
# ---------------------------------------------------------------------------


class AnalyticsManager:
    """Manages event queuing and flushing to sinks.

    Uses a queue-before-sink pattern: events are buffered in memory
    and flushed periodically or on demand.
    """

    _instance: Optional["AnalyticsManager"] = None

    def __init__(
        self,
        *,
        flush_interval_seconds: float = 10.0,
        max_queue_size: int = 500,
        session_id: str = "",
        enabled: bool = True,
    ) -> None:
        self._queue: List[AnalyticsEvent] = []
        self._sinks: List[AnalyticsSink] = []
        self._flush_interval = flush_interval_seconds
        self._max_queue_size = max_queue_size
        self._session_id = session_id
        self._enabled = enabled
        self._flush_task: Optional[asyncio.Task] = None
        self._total_events: int = 0
        self._total_sent: int = 0
        self._total_failed: int = 0

    @classmethod
    def get_instance(cls) -> "AnalyticsManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "AnalyticsManager") -> None:
        cls._instance = instance

    # ---- Sink management ----

    def attach_sink(self, sink: AnalyticsSink) -> None:
        """Register an analytics sink."""
        self._sinks.append(sink)
        logger.debug("Attached analytics sink: %s", sink.name)

    def remove_sink(self, sink: AnalyticsSink) -> None:
        """Remove an analytics sink."""
        self._sinks = [s for s in self._sinks if s is not sink]

    # ---- Event logging ----

    def log_event(
        self,
        event_type: str,
        properties: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an analytics event (synchronous, queues for async send)."""
        if not self._enabled:
            return

        event = AnalyticsEvent(
            event_type=event_type,
            session_id=self._session_id,
            properties=properties or {},
            metadata=metadata or {},
        )

        self._queue.append(event)
        self._total_events += 1

        # Auto-flush if queue is full
        if len(self._queue) >= self._max_queue_size:
            asyncio.ensure_future(self.flush())

    async def log_event_async(
        self,
        event_type: str,
        properties: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an analytics event and immediately flush."""
        self.log_event(event_type, properties, metadata)
        await self.flush()

    # ---- Flushing ----

    async def flush(self) -> int:
        """Flush all queued events to sinks.

        Returns the number of events successfully sent.
        """
        if not self._queue or not self._sinks:
            return 0

        events = list(self._queue)
        self._queue.clear()

        sent_count = 0
        for sink in self._sinks:
            try:
                success = await sink.send(events)
                if success:
                    sent_count += len(events)
                    self._total_sent += len(events)
                else:
                    self._total_failed += len(events)
            except Exception as exc:
                logger.debug("Sink %s failed: %s", sink.name, exc)
                self._total_failed += len(events)

        return sent_count

    def start_periodic_flush(self) -> None:
        """Start a background task that flushes periodically."""
        if self._flush_task is not None:
            return

        async def _flush_loop() -> None:
            while True:
                await asyncio.sleep(self._flush_interval)
                try:
                    await self.flush()
                except Exception:
                    logger.debug("Periodic flush error", exc_info=True)

        try:
            loop = asyncio.get_running_loop()
            self._flush_task = loop.create_task(_flush_loop())
        except RuntimeError:
            logger.debug("No event loop for periodic flush")

    async def shutdown(self) -> None:
        """Flush remaining events and close all sinks."""
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None

        await self.flush()

        for sink in self._sinks:
            try:
                await sink.close()
            except Exception:
                logger.debug("Error closing sink %s", sink.name, exc_info=True)

    # ---- Properties ----

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "total_events": self._total_events,
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "queue_size": len(self._queue),
            "sink_count": len(self._sinks),
        }


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def log_event(
    event_type: str,
    properties: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an analytics event using the global manager."""
    AnalyticsManager.get_instance().log_event(event_type, properties, metadata)


async def log_event_async(
    event_type: str,
    properties: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an analytics event and immediately flush."""
    await AnalyticsManager.get_instance().log_event_async(
        event_type, properties, metadata
    )


def attach_analytics_sink(sink: AnalyticsSink) -> None:
    """Attach a sink to the global analytics manager."""
    AnalyticsManager.get_instance().attach_sink(sink)


async def flush_analytics() -> int:
    """Flush all queued analytics events."""
    return await AnalyticsManager.get_instance().flush()


async def shutdown_analytics() -> None:
    """Shut down the analytics system."""
    await AnalyticsManager.get_instance().shutdown()


def setup_default_analytics(
    *,
    session_id: str = "",
    directory: Optional[str] = None,
    enabled: bool = True,
) -> AnalyticsManager:
    """Set up the default analytics configuration.

    Creates a FileSink and installs it as the global manager.
    """
    manager = AnalyticsManager(session_id=session_id, enabled=enabled)
    manager.attach_sink(FileSink(directory))
    AnalyticsManager.set_instance(manager)
    return manager
