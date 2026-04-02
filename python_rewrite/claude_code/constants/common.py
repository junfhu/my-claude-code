"""
Common date/time utility functions.

These provide session-stable date strings used in prompts and caching.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache

__all__ = [
    "get_local_iso_date",
    "get_session_start_date",
    "get_local_month_year",
]


def get_local_iso_date() -> str:
    """Return the local date in ``YYYY-MM-DD`` format.

    Respects the ``CLAUDE_CODE_OVERRIDE_DATE`` environment variable for testing.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        return override

    today = date.today()
    return today.isoformat()


@lru_cache(maxsize=1)
def get_session_start_date() -> str:
    """Memoised version of :func:`get_local_iso_date`.

    Captures the date once at session start for prompt-cache stability.
    The main interactive path gets this behaviour via memoised user context;
    simple mode (``--bare``) calls ``get_system_prompt`` per-request and needs
    an explicit memoised date to avoid busting the cached prefix at midnight.
    """
    return get_local_iso_date()


def get_local_month_year() -> str:
    """Return ``"Month YYYY"`` (e.g. ``"February 2026"``) in the local timezone.

    Changes monthly, not daily — used in tool prompts to minimise cache busting.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        dt = datetime.fromisoformat(override)
    else:
        dt = datetime.now()
    return dt.strftime("%B %Y")
