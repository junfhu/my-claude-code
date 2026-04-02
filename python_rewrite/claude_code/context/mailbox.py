"""
Inter-component message passing via a Mailbox.

Provides an asynchronous message queue with:
    - ``send(msg)`` -- enqueue or immediately deliver to a waiting receiver
    - ``poll(predicate)`` -- synchronous non-blocking receive
    - ``receive(predicate)`` -- async blocking receive
    - ``subscribe(callback)`` -- change notifications

This replaces the React context-based Mailbox from the TypeScript version
with a standalone class that can be used in any context (CLI, TUI, tests).

Thread-safe: all mutations are protected by a lock.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

MessageSource = Literal["user", "teammate", "system", "tick", "task"]


@dataclass
class Message:
    """A message in the mailbox.

    Attributes:
        id: Unique message identifier.
        source: Origin of the message (``user``, ``teammate``, ``system``,
            ``tick``, ``task``).
        content: The message text.
        from_agent: Optional sender name (for teammate messages).
        color: Optional display color hint.
        timestamp: ISO 8601 timestamp string.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: MessageSource = "system"
    content: str = ""
    from_agent: str | None = None
    color: str | None = None
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z")
    )


# ---------------------------------------------------------------------------
# Predicate type
# ---------------------------------------------------------------------------

MessagePredicate = Callable[[Message], bool]

_ACCEPT_ALL: MessagePredicate = lambda _msg: True


# ---------------------------------------------------------------------------
# Waiter -- internal type for pending receive() calls
# ---------------------------------------------------------------------------

@dataclass
class _Waiter:
    predicate: MessagePredicate
    future: asyncio.Future[Message]


# ---------------------------------------------------------------------------
# Mailbox
# ---------------------------------------------------------------------------

class Mailbox:
    """Asynchronous message queue with subscriber notifications.

    The mailbox supports three consumption patterns:

    1. **Fire-and-forget send**: ``mailbox.send(msg)`` -- enqueues the
       message or immediately delivers it to a waiting ``receive()`` caller.

    2. **Synchronous poll**: ``mailbox.poll(predicate)`` -- returns the
       first matching message or ``None`` (non-blocking).

    3. **Async receive**: ``await mailbox.receive(predicate)`` -- waits
       for a matching message (blocking, returns a Future).

    Additionally, ``mailbox.subscribe(callback)`` registers a change listener
    that fires on every send/poll/receive. Returns an unsubscribe function.

    Thread-safe: all queue mutations are protected by a lock.

    Usage::

        mailbox = Mailbox()
        mailbox.send(Message(source="user", content="hello"))
        msg = mailbox.poll()
        assert msg is not None and msg.content == "hello"
    """

    def __init__(self) -> None:
        self._queue: list[Message] = []
        self._waiters: list[_Waiter] = []
        self._subscribers: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._revision: int = 0

    # -- Properties ----------------------------------------------------------

    @property
    def length(self) -> int:
        """Number of messages currently queued."""
        return len(self._queue)

    @property
    def revision(self) -> int:
        """Monotonically increasing counter, bumped on every mutation."""
        return self._revision

    # -- Public API ----------------------------------------------------------

    def send(self, msg: Message) -> None:
        """Enqueue a message or deliver it to a waiting receiver.

        If there is a ``receive()`` call waiting with a matching predicate,
        the message is delivered directly (bypassing the queue).  Otherwise
        it is appended to the queue.

        Bumps ``revision`` and notifies all subscribers.
        """
        with self._lock:
            self._revision += 1

            # Check if any waiter accepts this message
            for i, waiter in enumerate(self._waiters):
                if waiter.predicate(msg):
                    # Deliver directly to the waiting receiver
                    matched = self._waiters.pop(i)
                    # Resolve the future from the event loop thread
                    loop = matched.future.get_loop()
                    loop.call_soon_threadsafe(matched.future.set_result, msg)
                    self._notify()
                    return

            # No matching waiter -- queue the message
            self._queue.append(msg)

        self._notify()

    def poll(
        self,
        predicate: MessagePredicate | None = None,
    ) -> Message | None:
        """Synchronous non-blocking receive.

        Returns the first message matching ``predicate``, or ``None`` if
        no matching message is queued.

        The matched message is removed from the queue.
        """
        fn = predicate or _ACCEPT_ALL

        with self._lock:
            for i, msg in enumerate(self._queue):
                if fn(msg):
                    self._queue.pop(i)
                    return msg

        return None

    async def receive(
        self,
        predicate: MessagePredicate | None = None,
    ) -> Message:
        """Async blocking receive.

        Waits for a message matching ``predicate``.  If a matching message
        is already queued, it is returned immediately (without awaiting).

        Args:
            predicate: Optional filter function.  Defaults to accepting all.

        Returns:
            The first matching ``Message``.
        """
        fn = predicate or _ACCEPT_ALL

        with self._lock:
            # Check queue first
            for i, msg in enumerate(self._queue):
                if fn(msg):
                    self._queue.pop(i)
                    self._notify()
                    return msg

            # No matching message -- register a waiter
            loop = asyncio.get_running_loop()
            future: asyncio.Future[Message] = loop.create_future()
            self._waiters.append(_Waiter(predicate=fn, future=future))

        return await future

    def peek(
        self,
        predicate: MessagePredicate | None = None,
    ) -> Message | None:
        """Peek at the first matching message without removing it."""
        fn = predicate or _ACCEPT_ALL
        with self._lock:
            for msg in self._queue:
                if fn(msg):
                    return msg
        return None

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener for mailbox changes.

        Returns an unsubscribe function.
        """
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def clear(self) -> None:
        """Remove all queued messages (does not cancel pending receives)."""
        with self._lock:
            self._queue.clear()
            self._revision += 1
        self._notify()

    def cancel_all_waiters(self) -> None:
        """Cancel all pending ``receive()`` futures."""
        with self._lock:
            for waiter in self._waiters:
                if not waiter.future.done():
                    waiter.future.cancel()
            self._waiters.clear()

    # -- Internal ------------------------------------------------------------

    def _notify(self) -> None:
        """Notify all subscribers of a state change."""
        for sub in list(self._subscribers):
            try:
                sub()
            except Exception:
                pass  # Subscribers must not crash the mailbox

    def __repr__(self) -> str:
        return (
            f"Mailbox(queue={len(self._queue)}, "
            f"waiters={len(self._waiters)}, "
            f"revision={self._revision})"
        )


__all__ = [
    "Mailbox",
    "Message",
    "MessagePredicate",
    "MessageSource",
]
