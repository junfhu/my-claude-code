"""File history tracking for undo operations."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileSnapshot:
    """A point-in-time snapshot of a file's content."""
    path: str
    backup_path: str
    timestamp: float
    original_hash: str
    tool_use_id: Optional[str] = None
    description: str = ""


class FileHistory:
    """Tracks file modifications for undo support.

    Before any write/edit tool modifies a file, a backup is stored.
    The user can then undo changes by restoring from the backup.
    """

    def __init__(self, backup_dir: Optional[str] = None) -> None:
        if backup_dir is None:
            backup_dir = os.path.join(tempfile.gettempdir(), "claude_code_backups")
        self._backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        self._history: dict[str, list[FileSnapshot]] = {}

    def record(
        self,
        path: str,
        *,
        tool_use_id: Optional[str] = None,
        description: str = "",
    ) -> Optional[FileSnapshot]:
        """Record the current state of a file before modification.

        Returns the snapshot, or None if the file doesn't exist.
        """
        if not os.path.isfile(path):
            return None

        content_hash = self._hash_file(path)
        backup_name = f"{content_hash}_{int(time.time() * 1000)}"
        backup_path = os.path.join(self._backup_dir, backup_name)

        shutil.copy2(path, backup_path)

        snapshot = FileSnapshot(
            path=os.path.abspath(path),
            backup_path=backup_path,
            timestamp=time.time(),
            original_hash=content_hash,
            tool_use_id=tool_use_id,
            description=description,
        )

        if path not in self._history:
            self._history[path] = []
        self._history[path].append(snapshot)
        return snapshot

    def undo(self, path: str) -> Optional[FileSnapshot]:
        """Restore the most recent backup for a file.

        Returns the snapshot that was restored, or None if no history.
        """
        snapshots = self._history.get(path, [])
        if not snapshots:
            return None

        snapshot = snapshots.pop()
        if os.path.isfile(snapshot.backup_path):
            shutil.copy2(snapshot.backup_path, path)
            return snapshot
        return None

    def undo_by_tool_use(self, tool_use_id: str) -> list[FileSnapshot]:
        """Undo all file changes from a specific tool invocation."""
        restored: list[FileSnapshot] = []
        for path, snapshots in self._history.items():
            to_restore = [s for s in snapshots if s.tool_use_id == tool_use_id]
            for snapshot in reversed(to_restore):
                if os.path.isfile(snapshot.backup_path):
                    shutil.copy2(snapshot.backup_path, path)
                    snapshots.remove(snapshot)
                    restored.append(snapshot)
        return restored

    def get_history(self, path: str) -> list[FileSnapshot]:
        return list(self._history.get(path, []))

    def get_all_modified_files(self) -> list[str]:
        return list(self._history.keys())

    def cleanup(self, *, max_age_s: float = 86400) -> int:
        """Remove old backups."""
        cutoff = time.time() - max_age_s
        removed = 0
        for path, snapshots in list(self._history.items()):
            old = [s for s in snapshots if s.timestamp < cutoff]
            for s in old:
                try:
                    os.unlink(s.backup_path)
                    removed += 1
                except OSError:
                    pass
                snapshots.remove(s)
            if not snapshots:
                del self._history[path]
        return removed

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
