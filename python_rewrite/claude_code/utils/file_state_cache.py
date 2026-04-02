"""File state cache — mtime tracking for detecting file modifications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileState:
    path: str
    mtime: float
    size: int
    content_hash: Optional[str] = None


class FileStateCache:
    """Tracks file modification times to detect changes between tool calls."""

    def __init__(self) -> None:
        self._cache: dict[str, FileState] = {}

    def snapshot(self, path: str) -> Optional[FileState]:
        """Take a snapshot of a file's current state."""
        try:
            st = os.stat(path)
            state = FileState(path=path, mtime=st.st_mtime, size=st.st_size)
            self._cache[path] = state
            return state
        except OSError:
            return None

    def has_changed(self, path: str) -> bool:
        """Check if a file has changed since last snapshot."""
        cached = self._cache.get(path)
        if cached is None:
            return True
        try:
            st = os.stat(path)
            return st.st_mtime != cached.mtime or st.st_size != cached.size
        except OSError:
            return True

    def get_changed_files(self, paths: list[str]) -> list[str]:
        """Return paths that have changed since last snapshot."""
        return [p for p in paths if self.has_changed(p)]

    def update(self, path: str) -> None:
        """Update the cached state for a file."""
        self.snapshot(path)

    def remove(self, path: str) -> None:
        self._cache.pop(path, None)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def tracked_files(self) -> list[str]:
        return list(self._cache.keys())
