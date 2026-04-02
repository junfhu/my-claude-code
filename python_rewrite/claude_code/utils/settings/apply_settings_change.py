"""Apply settings changes and trigger side-effects."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


_change_handlers: list[Callable[[str, Any, Any], None]] = []


def register_settings_change_handler(
    handler: Callable[[str, Any, Any], None],
) -> None:
    """Register a handler called when a setting changes.

    Handler signature: ``(key, old_value, new_value) -> None``
    """
    _change_handlers.append(handler)


def apply_settings_change(
    key: str,
    new_value: Any,
    old_value: Any = None,
) -> None:
    """Apply a settings change and notify handlers."""
    for handler in _change_handlers:
        try:
            handler(key, old_value, new_value)
        except Exception as exc:
            logger.warning("Settings change handler failed for %s: %s", key, exc)
