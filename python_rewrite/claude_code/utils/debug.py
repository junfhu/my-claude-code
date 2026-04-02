"""Debug utilities — conditional logging for development."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

_debug_enabled: bool | None = None

logger = logging.getLogger("claude_code.debug")


def is_debug_enabled() -> bool:
    global _debug_enabled
    if _debug_enabled is None:
        _debug_enabled = os.environ.get("CLAUDE_CODE_DEBUG", "").lower() in ("1", "true", "yes")
    return _debug_enabled


def log_for_debugging(msg: str, *args: Any, level: str = "debug") -> None:
    """Log a message only when debug mode is enabled."""
    if not is_debug_enabled():
        return
    fn = getattr(logger, level, logger.debug)
    fn(msg, *args)


def enable_debug() -> None:
    global _debug_enabled
    _debug_enabled = True
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)


def disable_debug() -> None:
    global _debug_enabled
    _debug_enabled = False
