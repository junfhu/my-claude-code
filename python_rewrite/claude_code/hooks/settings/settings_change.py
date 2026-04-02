"""
Settings file change detection.

Watches for changes to settings.json, .mcp.json, and CLAUDE.md files
and triggers reloads when they are modified.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class SettingsChangeDetector:
    """Detects changes to configuration files by tracking mtime."""

    def __init__(self) -> None:
        self._mtimes: dict[str, float] = {}
        self._callbacks: list[Callable[[str], None]] = []

    def watch(self, path: str) -> None:
        """Add a path to watch."""
        try:
            self._mtimes[path] = os.path.getmtime(path)
        except OSError:
            self._mtimes[path] = 0.0

    def on_change(self, callback: Callable[[str], None]) -> None:
        """Register a callback for file changes."""
        self._callbacks.append(callback)

    def check(self) -> list[str]:
        """Check all watched files for changes.

        Returns list of changed paths.
        """
        changed: list[str] = []
        for path, last_mtime in list(self._mtimes.items()):
            try:
                current_mtime = os.path.getmtime(path)
                if current_mtime != last_mtime:
                    self._mtimes[path] = current_mtime
                    changed.append(path)
            except OSError:
                if last_mtime != 0.0:
                    self._mtimes[path] = 0.0
                    changed.append(path)

        for path in changed:
            for callback in self._callbacks:
                try:
                    callback(path)
                except Exception as exc:
                    logger.warning("Change callback failed for %s: %s", path, exc)

        return changed

    def get_default_watch_paths(self, cwd: Optional[str] = None) -> list[str]:
        """Get the default set of paths to watch for changes."""
        paths: list[str] = []
        work_dir = cwd or os.getcwd()

        # Settings files
        config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(os.path.expanduser("~"), ".claude"),
        )
        paths.append(os.path.join(config_dir, "settings.json"))

        # MCP config
        paths.append(os.path.join(work_dir, ".mcp.json"))

        # CLAUDE.md files
        paths.append(os.path.join(work_dir, "CLAUDE.md"))
        paths.append(os.path.join(work_dir, "CLAUDE.local.md"))
        paths.append(os.path.join(work_dir, ".claude", "CLAUDE.md"))
        paths.append(os.path.join(config_dir, "CLAUDE.md"))

        return [p for p in paths if os.path.exists(p)]

    def start_watching(self, cwd: Optional[str] = None) -> None:
        """Watch all default config files."""
        for path in self.get_default_watch_paths(cwd):
            self.watch(path)
