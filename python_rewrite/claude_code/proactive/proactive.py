"""Proactive agent mode.

In proactive mode, Claude Code can initiate actions without user prompting —
monitoring files, running background tasks, and performing maintenance.
This module handles the lifecycle and tick loop for proactive sessions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# How often (seconds) the proactive tick fires
DEFAULT_TICK_INTERVAL = 60.0
PROACTIVE_ENV_VAR = "CLAUDE_CODE_PROACTIVE"


def is_proactive_enabled() -> bool:
    """Check if proactive mode is enabled via environment."""
    val = os.environ.get(PROACTIVE_ENV_VAR, "").lower()
    return val in ("1", "true", "yes")


class ProactiveAgent:
    """Manages the proactive agent tick loop.

    The proactive agent periodically checks for actionable conditions
    and queues synthetic prompts into the main message loop when
    intervention is needed.
    """

    def __init__(
        self,
        *,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
        on_tick: Optional[Callable[[], Any]] = None,
        enqueue_prompt: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._tick_interval = tick_interval
        self._on_tick = on_tick
        self._enqueue_prompt = enqueue_prompt
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

        # State tracking
        self._tick_count = 0
        self._last_tick_time: Optional[float] = None
        self._watchers: list[ProactiveWatcher] = []

    def add_watcher(self, watcher: ProactiveWatcher) -> None:
        """Register a proactive watcher."""
        self._watchers.append(watcher)

    async def start(self) -> None:
        """Start the proactive tick loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info("Proactive agent started (interval=%.0fs)", self._tick_interval)

    async def stop(self) -> None:
        """Stop the proactive tick loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Proactive agent stopped")

    async def _tick_loop(self) -> None:
        """Main tick loop — periodically checks watchers and fires actions."""
        while self._running:
            try:
                await asyncio.sleep(self._tick_interval)
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Proactive tick error: %s", exc)

    async def _tick(self) -> None:
        """Execute a single proactive tick."""
        self._tick_count += 1
        self._last_tick_time = time.monotonic()

        # Run custom tick callback
        if self._on_tick:
            result = self._on_tick()
            if asyncio.iscoroutine(result):
                await result

        # Check each watcher
        for watcher in self._watchers:
            try:
                action = await watcher.check()
                if action and self._enqueue_prompt:
                    self._enqueue_prompt(action)
            except Exception as exc:
                logger.error("Watcher %s error: %s", watcher.name, exc)

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def is_running(self) -> bool:
        return self._running


class ProactiveWatcher:
    """Base class for proactive watchers.

    Watchers are periodically checked during the proactive tick.
    When they detect a condition that needs attention, they return
    a prompt string to be injected into the conversation.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    async def check(self) -> Optional[str]:
        """Check for actionable conditions.

        Returns a prompt string to inject, or None.
        """
        return None


class FileChangeWatcher(ProactiveWatcher):
    """Watch for file changes in the workspace."""

    def __init__(self, watch_paths: Optional[list[str]] = None) -> None:
        super().__init__("file_change")
        self._watch_paths = watch_paths or ["."]
        self._last_check: dict[str, float] = {}

    async def check(self) -> Optional[str]:
        # File watching would use inotify/kqueue/polling
        # Simplified placeholder
        return None


class GitChangeWatcher(ProactiveWatcher):
    """Watch for git status changes."""

    def __init__(self) -> None:
        super().__init__("git_change")
        self._last_status: Optional[str] = None

    async def check(self) -> Optional[str]:
        import subprocess

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status = result.stdout.strip()
            if status and status != self._last_status:
                self._last_status = status
                # Only trigger on significant changes
                changed_files = [
                    line.split(maxsplit=1)[-1]
                    for line in status.splitlines()
                    if line.strip()
                ]
                if len(changed_files) > 5:
                    return (
                        f"<system-reminder>Detected {len(changed_files)} "
                        f"changed files in the workspace. Consider reviewing.</system-reminder>"
                    )
            self._last_status = status
        except Exception:
            pass
        return None
