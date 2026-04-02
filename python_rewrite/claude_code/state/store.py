"""
Framework-agnostic reactive state store.

Replaces React's useSyncExternalStore pattern with a Python observable store.

Architecture overview:
    create_store(initial_state, on_change?)
        |
    Store[T] { get_state, set_state, subscribe }
        |
        +-- Side-effect layer (on_change_app_state.py) <- on_change callback
        +-- Any consumer code (CLI, TUI, tests)

Thread-safety note:
    Unlike JavaScript's single-threaded event loop, Python supports true
    multi-threading.  An RLock protects the state mutation path so that
    concurrent set_state calls are serialized.  Subscriber notifications
    fire outside the lock to avoid deadlocks when a subscriber calls
    set_state (re-entrant usage).
"""

from __future__ import annotations

import threading
from typing import TypeVar, Generic, Callable, Optional

T = TypeVar("T")

# A Listener is a zero-argument callback invoked whenever the store state
# changes.  Listeners are typically UI re-render triggers or downstream
# effect handlers.
Listener = Callable[[], None]

# OnChange receives both the previous and next state snapshots.  It fires
# *before* subscriber notifications, making it the ideal place for side
# effects that must run once per state transition (e.g. persisting settings
# to disk, notifying external systems).
OnChange = Callable[[T, T], None]


class Store(Generic[T]):
    """Observable state store with subscriber notification.

    This is a minimal pub/sub state container inspired by Zustand and Redux.
    It is intentionally framework-agnostic so it can be consumed by both
    TUI frameworks and plain CLI scripts without pulling in UI dependencies.

    Usage::

        store = create_store({"count": 0})
        unsub = store.subscribe(lambda: print(store.get_state()))
        store.set_state(lambda prev: {**prev, "count": prev["count"] + 1})
        unsub()  # stop listening
    """

    __slots__ = ("_state", "_on_change", "_listeners", "_lock")

    def __init__(
        self,
        initial_state: T,
        on_change: Optional[Callable[[T, T], None]] = None,
    ) -> None:
        self._state: T = initial_state
        self._on_change = on_change
        # Using a list (not set) preserves insertion order and allows
        # duplicate detection.  Duplicate adds are idempotent because
        # subscribe() checks membership before appending.
        self._listeners: list[Listener] = []
        self._lock = threading.RLock()

    # -- Public API ----------------------------------------------------------

    def get_state(self) -> T:
        """Synchronous read -- returns the current state reference.

        Because state is replaced (not mutated in-place), callers always get
        a consistent snapshot.
        """
        return self._state

    def set_state(self, updater: Callable[[T], T]) -> None:
        """Updater-based state transition.

        Accepts an *updater function* (prev -> next) rather than a raw value.
        This ensures callers always derive next state from the current state,
        avoiding stale-closure bugs.

        If the updater returns the same reference (``is`` identity), the
        update is a no-op -- no on_change, no subscriber notifications.

        The update pipeline is:
            1. Compute next state via updater(prev)
            2. Bail out early if next is prev (identity check)
            3. Swap the state reference
            4. Fire the on_change callback (side-effects)
            5. Notify all subscribers
        """
        # Capture the list of subscribers to notify *after* releasing the
        # lock.  This prevents deadlocks when a subscriber calls set_state.
        to_notify: list[Listener]

        with self._lock:
            prev = self._state
            next_state = updater(prev)

            # Identity check -- if the updater returned the exact same
            # object, treat as a no-op.
            if next_state is prev:
                return

            # Commit the new state before any callbacks so that
            # get_state() inside on_change or subscriber callbacks
            # reflects the updated value.
            self._state = next_state

            # Fire the on_change side-effect handler (if provided) with
            # both snapshots.  This runs before subscribers so external
            # systems (persistence, CCR sync) are updated before consumers
            # read the new state.
            if self._on_change is not None:
                self._on_change(next_state, prev)

            # Snapshot the listener list so we iterate a stable copy.
            to_notify = list(self._listeners)

        # Notify all registered subscribers outside the lock.
        for listener in to_notify:
            listener()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener for state changes.

        Returns an unsubscribe function that removes the listener.

        Usage::

            unsub = store.subscribe(my_callback)
            # later...
            unsub()  # stops listening
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass  # already removed

        return unsubscribe

    # -- Dunder helpers ------------------------------------------------------

    def __repr__(self) -> str:
        return f"Store(state={self._state!r}, listeners={len(self._listeners)})"


def create_store(
    initial_state: T,
    on_change: Optional[Callable[[T, T], None]] = None,
) -> Store[T]:
    """Factory function that creates a new ``Store[T]`` instance.

    Parameters:
        initial_state: The starting state value; becomes the first
            ``get_state()`` result.
        on_change: Optional side-effect callback invoked on every *actual*
            state change (i.e. when ``next is not prev``).  Fires
            synchronously before subscriber notification so that external
            persistence / sync can settle before consumers re-read the
            state.

    Returns:
        A new ``Store[T]`` instance.
    """
    return Store(initial_state, on_change)


__all__ = [
    "Store",
    "Listener",
    "OnChange",
    "create_store",
]
