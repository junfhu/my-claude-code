"""
Plugin execution — lifecycle hooks and event dispatch.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .types import LoadedPlugin

logger = logging.getLogger(__name__)


class PluginRunner:
    """Manages plugin lifecycle and dispatches events."""

    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}

    def register(self, plugin: LoadedPlugin) -> None:
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> bool:
        return self._plugins.pop(name, None) is not None

    @property
    def plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins.values())

    def get(self, name: str) -> Optional[LoadedPlugin]:
        return self._plugins.get(name)

    async def dispatch_event(self, event: str, data: dict[str, Any] | None = None) -> list[Any]:
        """Dispatch an event to all loaded plugins.

        Plugins can listen for events like ``tool_start``, ``tool_end``,
        ``message_start``, ``message_end``, ``session_start``, ``session_end``.
        """
        results: list[Any] = []
        for plugin in self._plugins.values():
            if not plugin.is_loaded:
                continue
            try:
                handler = getattr(plugin, f"on_{event}", None)
                if handler and callable(handler):
                    result = handler(data or {})
                    results.append(result)
            except Exception as exc:
                logger.warning(
                    "Plugin %s failed handling event %s: %s",
                    plugin.name, event, exc,
                )
        return results

    async def initialize_all(self) -> None:
        """Run initialization hooks for all registered plugins."""
        for plugin in self._plugins.values():
            if not plugin.is_loaded:
                continue
            try:
                init = getattr(plugin, "initialize", None)
                if init and callable(init):
                    init()
            except Exception as exc:
                logger.warning("Plugin %s initialization failed: %s", plugin.name, exc)
                plugin.error = str(exc)

    async def shutdown_all(self) -> None:
        """Run shutdown hooks for all registered plugins."""
        for plugin in self._plugins.values():
            try:
                shutdown = getattr(plugin, "shutdown", None)
                if shutdown and callable(shutdown):
                    shutdown()
            except Exception:
                pass
        self._plugins.clear()
