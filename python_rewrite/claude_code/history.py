"""
Prompt history management.

Provides functions to read, write, and manage the conversation prompt
history persisted to disk.  History is stored as JSON-lines files per
session inside ``~/.claude/history/``.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HistoryEntry:
    """A single entry in the prompt history."""

    role: str  # "user" | "assistant"
    content: Any  # str or list[content blocks]
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    model: str = ""
    turn: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistorySession:
    """All entries for a single session."""

    session_id: str
    entries: List[HistoryEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cwd: str = ""
    model: str = ""


# ---------------------------------------------------------------------------
# History reader (lazy file-based reader)
# ---------------------------------------------------------------------------


class HistoryReader:
    """Lazily reads history sessions from disk.

    Returned by ``make_history_reader()``.  Supports iteration, search,
    and random access by session id.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def list_sessions(self) -> List[str]:
        """Return all session IDs with saved history, newest first."""
        if not self._directory.exists():
            return []

        sessions: List[tuple[float, str]] = []
        for p in self._directory.glob("*.jsonl"):
            session_id = p.stem
            sessions.append((p.stat().st_mtime, session_id))

        sessions.sort(reverse=True)
        return [sid for _, sid in sessions]

    def get_session(self, session_id: str) -> Optional[HistorySession]:
        """Load a single session from disk."""
        path = self._directory / f"{session_id}.jsonl"
        if not path.exists():
            return None

        entries: List[HistoryEntry] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(
                            HistoryEntry(
                                role=data.get("role", "user"),
                                content=data.get("content", ""),
                                timestamp=data.get("timestamp", 0.0),
                                session_id=data.get("session_id", session_id),
                                model=data.get("model", ""),
                                turn=data.get("turn", 0),
                                metadata=data.get("metadata", {}),
                            )
                        )
                    except json.JSONDecodeError:
                        logger.warning("Corrupt history line in %s", path)
        except OSError as exc:
            logger.warning("Cannot read history file %s: %s", path, exc)
            return None

        session = HistorySession(
            session_id=session_id,
            entries=entries,
        )
        if entries:
            session.created_at = entries[0].timestamp
            session.updated_at = entries[-1].timestamp
            session.model = entries[-1].model
        return session

    def search(
        self,
        query: str,
        *,
        max_results: int = 20,
        role: Optional[str] = None,
    ) -> List[HistoryEntry]:
        """Search across all sessions for entries containing *query*."""
        results: List[HistoryEntry] = []
        query_lower = query.lower()

        for sid in self.list_sessions():
            session = self.get_session(sid)
            if session is None:
                continue
            for entry in session.entries:
                content_str = (
                    entry.content
                    if isinstance(entry.content, str)
                    else json.dumps(entry.content)
                )
                if query_lower in content_str.lower():
                    if role is None or entry.role == role:
                        results.append(entry)
                        if len(results) >= max_results:
                            return results
        return results

    def recent_entries(self, n: int = 10) -> List[HistoryEntry]:
        """Return the *n* most recent entries across all sessions."""
        sessions = self.list_sessions()
        entries: List[HistoryEntry] = []
        for sid in sessions:
            session = self.get_session(sid)
            if session is None:
                continue
            entries.extend(session.entries)
            if len(entries) >= n * 2:
                break
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:n]


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------


def make_history_reader(directory: Optional[str] = None) -> HistoryReader:
    """Create a HistoryReader for the given (or default) directory."""
    dir_path = Path(directory) if directory else _default_history_dir()
    return HistoryReader(dir_path)


def get_history(
    session_id: str,
    directory: Optional[str] = None,
) -> Optional[HistorySession]:
    """Load a single session's history."""
    reader = make_history_reader(directory)
    return reader.get_session(session_id)


def add_to_history(
    session_id: str,
    entry: HistoryEntry,
    directory: Optional[str] = None,
) -> None:
    """Append a single entry to a session's history file."""
    dir_path = Path(directory) if directory else _default_history_dir()
    dir_path.mkdir(parents=True, exist_ok=True)

    path = dir_path / f"{session_id}.jsonl"

    record = {
        "role": entry.role,
        "content": entry.content,
        "timestamp": entry.timestamp,
        "session_id": entry.session_id or session_id,
        "model": entry.model,
        "turn": entry.turn,
        "metadata": entry.metadata,
    }

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.warning("Cannot write history for session %s: %s", session_id, exc)


def add_messages_to_history(
    session_id: str,
    messages: Sequence[Dict[str, Any]],
    *,
    model: str = "",
    directory: Optional[str] = None,
) -> None:
    """Bulk-append multiple messages (in API format) to history."""
    for i, msg in enumerate(messages):
        entry = HistoryEntry(
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            timestamp=msg.get("_meta", {}).get("timestamp", time.time()),
            session_id=session_id,
            model=model,
            turn=msg.get("_meta", {}).get("turn", i),
        )
        add_to_history(session_id, entry, directory)


def remove_last_from_history(
    session_id: str,
    directory: Optional[str] = None,
) -> bool:
    """Remove the last entry from a session's history file.

    Returns True if an entry was removed.
    """
    dir_path = Path(directory) if directory else _default_history_dir()
    path = dir_path / f"{session_id}.jsonl"

    if not path.exists():
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return False

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines[:-1])

        return True
    except OSError as exc:
        logger.warning("Cannot remove last history entry: %s", exc)
        return False


def clear_history(
    session_id: str,
    directory: Optional[str] = None,
) -> bool:
    """Delete an entire session's history file."""
    dir_path = Path(directory) if directory else _default_history_dir()
    path = dir_path / f"{session_id}.jsonl"

    if not path.exists():
        return False

    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.warning("Cannot clear history for session %s: %s", session_id, exc)
        return False


def list_all_sessions(directory: Optional[str] = None) -> List[str]:
    """Return all session IDs."""
    reader = make_history_reader(directory)
    return reader.list_sessions()


def prune_old_history(
    max_age_days: int = 30,
    directory: Optional[str] = None,
) -> int:
    """Delete history files older than *max_age_days*.

    Returns the number of files removed.
    """
    dir_path = Path(directory) if directory else _default_history_dir()
    if not dir_path.exists():
        return 0

    cutoff = time.time() - max_age_days * 86400
    removed = 0

    for p in dir_path.glob("*.jsonl"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError:
            pass

    if removed:
        logger.info("Pruned %d old history files", removed)
    return removed


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _default_history_dir() -> Path:
    """Default directory for history: ~/.claude/history/"""
    return Path.home() / ".claude" / "history"
