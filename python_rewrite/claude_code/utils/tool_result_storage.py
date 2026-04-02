"""Tool result persistence to disk.

Stores large tool results (binary blobs, images, long text) to disk
so they can be referenced by the agent without consuming context window.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Any, Optional

STORAGE_DIR_ENV = "CLAUDE_TOOL_RESULT_DIR"
MAX_INLINE_SIZE = 50_000  # Results larger than this get persisted


def _get_storage_dir() -> str:
    env_dir = os.environ.get(STORAGE_DIR_ENV)
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return env_dir
    d = os.path.join(tempfile.gettempdir(), "claude_code_tool_results")
    os.makedirs(d, exist_ok=True)
    return d


def persist_tool_result(
    content: str | bytes,
    *,
    tool_name: str = "",
    tool_use_id: str = "",
    mime_type: str = "text/plain",
    extension: str = ".txt",
) -> str:
    """Persist a tool result to disk and return the file path."""
    storage = _get_storage_dir()
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    content_hash = hashlib.sha256(content_bytes).hexdigest()[:12]
    filename = f"{tool_name}_{tool_use_id}_{content_hash}{extension}"
    filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    path = os.path.join(storage, filename)

    with open(path, "wb") as f:
        f.write(content_bytes)

    return path


def should_persist(content: str | bytes) -> bool:
    """Check if content is large enough to warrant disk persistence."""
    size = len(content) if isinstance(content, (str, bytes)) else 0
    return size > MAX_INLINE_SIZE


def get_persisted_result(path: str) -> Optional[bytes]:
    """Read a persisted tool result from disk."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def cleanup_old_results(max_age_hours: float = 24) -> int:
    """Remove tool results older than max_age_hours."""
    storage = _get_storage_dir()
    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    try:
        for entry in os.scandir(storage):
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.unlink(entry.path)
                removed += 1
    except OSError:
        pass
    return removed


def is_persist_error(exc: Exception) -> bool:
    """Check if an exception is from tool result persistence."""
    return isinstance(exc, (OSError, PermissionError))
