"""
Notification system.

Provides a framework-agnostic notification manager for toast-style
notifications with priority queuing, timeout management, deduplication,
invalidation, and fold (merge) support.

This replaces the React ``useNotifications`` hook from the TypeScript
version with a standalone class that can be used in any context.

Design:
    - Notifications have priorities: ``immediate``, ``high``, ``medium``, ``low``
    - Only one notification is displayed at a time (``current``)
    - Others queue up and are shown in priority order
    - ``immediate`` notifications pre-empt the current notification
    - Notifications with the same ``key`` are deduplicated
    - A notification can ``invalidate`` other notifications by key
    - Notifications can ``fold`` (merge) with existing same-key notifications
    - Each notification auto-dismisses after ``timeout_ms`` (default 8s)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

class Priority(IntEnum):
    """Notification priority levels (lower number = higher priority)."""
    IMMEDIATE = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


PriorityName = Literal["immediate", "high", "medium", "low"]

_PRIORITY_MAP: dict[PriorityName, Priority] = {
    "immediate": Priority.IMMEDIATE,
    "high": Priority.HIGH,
    "medium": Priority.MEDIUM,
    "low": Priority.LOW,
}


def _resolve_priority(name: PriorityName) -> Priority:
    return _PRIORITY_MAP[name]


# ---------------------------------------------------------------------------
# Notification dataclass
# ---------------------------------------------------------------------------

# FoldFn signature: (accumulator, incoming) -> merged notification
FoldFn = Callable[["Notification", "Notification"], "Notification"]


@dataclass
class Notification:
    """A notification to display in the UI.

    Attributes:
        key: Unique identifier for deduplication and fold matching.
        priority: Display priority (``immediate``, ``high``, ``medium``, ``low``).
        text: Text content to display (mutually exclusive with ``data``).
        color: Optional theme color key for the notification text.
        data: Arbitrary payload for rich/JSX-like rendering.
        invalidates: Keys of notifications that this notification invalidates.
            Invalidated notifications are removed from the queue and, if
            currently displayed, cleared immediately.
        timeout_ms: Auto-dismiss timeout in milliseconds.  Defaults to 8000.
        fold: Optional merge function for combining same-key notifications.
            Called as ``fold(accumulator, incoming)`` when a notification with
            a matching key already exists.
        once: If True, the notification auto-removes after dismissal and
            cannot be re-added.
    """
    key: str
    priority: PriorityName = "medium"
    text: str | None = None
    color: str | None = None
    data: Any = None
    invalidates: list[str] = field(default_factory=list)
    timeout_ms: int = 8000
    fold: FoldFn | None = None
    once: bool = False


# Default auto-dismiss timeout
DEFAULT_TIMEOUT_MS = 8000


# ---------------------------------------------------------------------------
# NotificationManager
# ---------------------------------------------------------------------------

class NotificationManager:
    """Framework-agnostic notification manager.

    Manages a queue of notifications with a single ``current`` display slot.
    Provides ``add``, ``remove``, and ``subscribe`` methods for integration
    with any UI framework.

    Thread-safe: all mutations are protected by a lock.

    Usage::

        mgr = NotificationManager()
        unsub = mgr.subscribe(lambda: print("changed!"))
        mgr.add(Notification(key="hello", text="Hello!", priority="high"))
        assert mgr.current is not None
        mgr.remove("hello")
        unsub()
    """

    def __init__(self) -> None:
        self._current: Notification | None = None
        self._queue: list[Notification] = []
        self._dismissed_once_keys: set[str] = set()
        self._subscribers: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._current_timer: threading.Timer | None = None

    # -- Properties ----------------------------------------------------------

    @property
    def current(self) -> Notification | None:
        """The notification currently being displayed (or ``None``)."""
        return self._current

    @property
    def queue(self) -> list[Notification]:
        """Snapshot of the notification queue (excluding current)."""
        return list(self._queue)

    # -- Public API ----------------------------------------------------------

    def add(self, notification: Notification) -> None:
        """Add a notification to the queue or display it immediately.

        Handles:
            - Deduplication (same key already in queue/current)
            - Fold (merge same-key notifications)
            - Invalidation (remove notifications named in ``invalidates``)
            - Immediate priority (pre-empts current notification)
        """
        with self._lock:
            # Skip if this was a once-only notification that was already shown
            if notification.key in self._dismissed_once_keys:
                return

            # Process invalidations
            if notification.invalidates:
                invalidate_set = set(notification.invalidates)
                self._queue = [
                    n
                    for n in self._queue
                    if n.key not in invalidate_set
                ]
                if (
                    self._current is not None
                    and self._current.key in invalidate_set
                ):
                    self._cancel_timer()
                    self._current = None

            # Handle immediate priority
            if notification.priority == "immediate":
                self._cancel_timer()
                # Re-queue current if it's not immediate
                if self._current is not None and self._current.priority != "immediate":
                    self._queue.insert(0, self._current)
                self._current = notification
                self._start_timer(notification)
                self._notify_subscribers()
                return

            # Try to fold into current or queued notification
            if notification.fold is not None:
                if (
                    self._current is not None
                    and self._current.key == notification.key
                ):
                    self._cancel_timer()
                    self._current = notification.fold(self._current, notification)
                    self._start_timer(self._current)
                    self._notify_subscribers()
                    return

                for i, queued in enumerate(self._queue):
                    if queued.key == notification.key:
                        self._queue[i] = notification.fold(queued, notification)
                        self._notify_subscribers()
                        return

            # Deduplication: skip if already present
            if self._current is not None and self._current.key == notification.key:
                return
            if any(n.key == notification.key for n in self._queue):
                return

            # Add to queue
            self._queue.append(notification)

        # Process queue (may promote a queued item to current)
        self._process_queue()

    def remove(self, key: str) -> None:
        """Remove a notification by key (from current or queue)."""
        with self._lock:
            if self._current is not None and self._current.key == key:
                if self._current.once:
                    self._dismissed_once_keys.add(key)
                self._cancel_timer()
                self._current = None
            else:
                self._queue = [n for n in self._queue if n.key != key]

        self._process_queue()

    def clear(self) -> None:
        """Remove all notifications."""
        with self._lock:
            self._cancel_timer()
            self._current = None
            self._queue.clear()
        self._notify_subscribers()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener for notification changes.

        Returns an unsubscribe function.
        """
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    # -- Internal ------------------------------------------------------------

    def _process_queue(self) -> None:
        """Promote the highest-priority queued notification to current."""
        with self._lock:
            if self._current is not None:
                return
            if not self._queue:
                self._notify_subscribers()
                return

            # Find the highest-priority notification
            best_idx = 0
            best_priority = _resolve_priority(self._queue[0].priority)
            for i, n in enumerate(self._queue[1:], 1):
                p = _resolve_priority(n.priority)
                if p < best_priority:
                    best_priority = p
                    best_idx = i

            notification = self._queue.pop(best_idx)
            self._current = notification
            self._start_timer(notification)

        self._notify_subscribers()

    def _start_timer(self, notification: Notification) -> None:
        """Start an auto-dismiss timer for the given notification."""
        timeout_s = (notification.timeout_ms or DEFAULT_TIMEOUT_MS) / 1000.0
        timer = threading.Timer(timeout_s, self._on_timeout, args=[notification.key])
        timer.daemon = True
        timer.start()
        self._current_timer = timer

    def _cancel_timer(self) -> None:
        """Cancel the current auto-dismiss timer."""
        if self._current_timer is not None:
            self._current_timer.cancel()
            self._current_timer = None

    def _on_timeout(self, key: str) -> None:
        """Handle auto-dismiss timeout."""
        with self._lock:
            if self._current is not None and self._current.key == key:
                if self._current.once:
                    self._dismissed_once_keys.add(key)
                self._current = None
                self._current_timer = None
        self._process_queue()

    def _notify_subscribers(self) -> None:
        """Notify all subscribers of a state change."""
        for sub in list(self._subscribers):
            try:
                sub()
            except Exception:
                pass  # Subscribers should not crash the notification system


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def get_next(queue: list[Notification]) -> Notification | None:
    """Return the highest-priority notification from a queue.

    Replicates the ``getNext`` helper from the TS version.
    """
    if not queue:
        return None
    return min(queue, key=lambda n: _resolve_priority(n.priority))


__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "FoldFn",
    "Notification",
    "NotificationManager",
    "Priority",
    "PriorityName",
    "get_next",
]
