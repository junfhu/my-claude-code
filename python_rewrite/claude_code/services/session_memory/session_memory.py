"""
Session memory management.

Manages persistent memory that survives across conversation sessions.
Memory entries are stored as markdown files in ``~/.claude/memory/``
and can be loaded into system prompts for future conversations.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEMORY_DIR_NAME = "memory"
GLOBAL_MEMORY_FILE = "CLAUDE.md"
PROJECT_MEMORY_FILE = ".claude/CLAUDE.md"
USER_MEMORY_FILE = "user_memory.md"
MAX_MEMORY_SIZE_BYTES = 100_000  # 100KB per memory file
MAX_ENTRIES_PER_FILE = 500


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    """A single memory entry."""

    content: str
    source: str = "user"  # "user" | "assistant" | "system" | "auto"
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    priority: int = 0  # Higher = more important
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Convert to a markdown list item."""
        tag_str = ""
        if self.tags:
            tag_str = " " + " ".join(f"`{t}`" for t in self.tags)
        return f"- {self.content}{tag_str}"


@dataclass
class MemoryFile:
    """A collection of memory entries from a single file."""

    path: str
    entries: List[MemoryEntry] = field(default_factory=list)
    raw_content: str = ""
    file_type: str = "global"  # "global" | "project" | "user"


# ---------------------------------------------------------------------------
# SessionMemory manager
# ---------------------------------------------------------------------------


class SessionMemory:
    """Manages session memory across multiple sources.

    Memory sources (in priority order):
    1. Project-level: ``.claude/CLAUDE.md`` in the project root
    2. User-level: ``~/.claude/CLAUDE.md``
    3. Session-specific memories saved by the assistant
    """

    def __init__(
        self,
        cwd: str = ".",
        memory_dir: Optional[str] = None,
    ) -> None:
        self._cwd = Path(cwd).resolve()
        self._memory_dir = Path(memory_dir) if memory_dir else Path.home() / ".claude"
        self._entries: List[MemoryEntry] = []
        self._loaded = False

    def load(self) -> None:
        """Load all memory sources."""
        self._entries.clear()
        self._loaded = True

        # 1. Load project-level CLAUDE.md
        project_memory = self._cwd / PROJECT_MEMORY_FILE
        if project_memory.exists():
            entries = self._load_memory_file(project_memory, "project")
            self._entries.extend(entries)
            logger.debug("Loaded %d project memory entries", len(entries))

        # 2. Load user-level CLAUDE.md
        user_memory = self._memory_dir / GLOBAL_MEMORY_FILE
        if user_memory.exists():
            entries = self._load_memory_file(user_memory, "global")
            self._entries.extend(entries)
            logger.debug("Loaded %d global memory entries", len(entries))

        # 3. Load session memories
        session_mem_dir = self._memory_dir / MEMORY_DIR_NAME
        if session_mem_dir.exists():
            for f in sorted(session_mem_dir.glob("*.md")):
                entries = self._load_memory_file(f, "session")
                self._entries.extend(entries)

        logger.info("Total memory entries loaded: %d", len(self._entries))

    def get_context_string(self, max_tokens: int = 2000) -> str:
        """Build a context string from memory for injection into system prompt.

        Respects a rough token budget.
        """
        if not self._loaded:
            self.load()

        if not self._entries:
            return ""

        # Sort by priority (descending) then recency
        sorted_entries = sorted(
            self._entries,
            key=lambda e: (e.priority, e.updated_at),
            reverse=True,
        )

        parts: List[str] = []
        parts.append("<memory>")
        parts.append("The following are remembered notes from previous sessions:\n")

        estimated_tokens = 20  # Header overhead
        for entry in sorted_entries:
            line = entry.to_markdown()
            line_tokens = len(line) // 4  # Rough estimate
            if estimated_tokens + line_tokens > max_tokens:
                break
            parts.append(line)
            estimated_tokens += line_tokens

        parts.append("</memory>")
        return "\n".join(parts)

    def add_entry(
        self,
        content: str,
        *,
        source: str = "assistant",
        tags: Optional[List[str]] = None,
        priority: int = 0,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        entry = MemoryEntry(
            content=content,
            source=source,
            tags=tags or [],
            priority=priority,
        )
        self._entries.append(entry)
        return entry

    def remove_entry(self, content: str) -> bool:
        """Remove a memory entry by content match."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.content != content]
        return len(self._entries) < before

    def search(self, query: str) -> List[MemoryEntry]:
        """Search memory entries by keyword."""
        query_lower = query.lower()
        return [
            e for e in self._entries if query_lower in e.content.lower()
        ]

    def save(self, file_type: str = "session") -> str:
        """Save current entries to a memory file.

        Returns the path written.
        """
        if file_type == "project":
            path = self._cwd / PROJECT_MEMORY_FILE
        elif file_type == "global":
            path = self._memory_dir / GLOBAL_MEMORY_FILE
        else:
            mem_dir = self._memory_dir / MEMORY_DIR_NAME
            mem_dir.mkdir(parents=True, exist_ok=True)
            path = mem_dir / f"session_{int(time.time())}.md"

        lines: List[str] = []
        for entry in self._entries:
            if file_type == "session" and entry.source not in ("assistant", "auto"):
                continue
            lines.append(entry.to_markdown())

        content = "\n".join(lines) + "\n" if lines else ""

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            logger.info("Saved %d memory entries to %s", len(lines), path)
            return str(path)
        except OSError as exc:
            logger.warning("Cannot save memory: %s", exc)
            return ""

    @property
    def entries(self) -> List[MemoryEntry]:
        if not self._loaded:
            self.load()
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        if not self._loaded:
            self.load()
        return len(self._entries)

    # ---- Internal ----

    def _load_memory_file(
        self,
        path: Path,
        file_type: str,
    ) -> List[MemoryEntry]:
        """Parse a markdown memory file into entries."""
        try:
            content = path.read_text(encoding="utf-8")
            if len(content) > MAX_MEMORY_SIZE_BYTES:
                logger.warning(
                    "Memory file %s is too large (%d bytes), truncating",
                    path,
                    len(content),
                )
                content = content[:MAX_MEMORY_SIZE_BYTES]

            return self._parse_markdown_entries(content, file_type)
        except OSError as exc:
            logger.warning("Cannot read memory file %s: %s", path, exc)
            return []

    @staticmethod
    def _parse_markdown_entries(
        content: str,
        file_type: str,
    ) -> List[MemoryEntry]:
        """Parse markdown content into MemoryEntry objects."""
        entries: List[MemoryEntry] = []

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Parse list items
            if line.startswith("- ") or line.startswith("* "):
                text = line[2:].strip()
                if not text:
                    continue

                # Extract tags (backtick-wrapped words at the end)
                tags: List[str] = []
                tag_pattern = re.compile(r"`(\w+)`")
                tag_matches = tag_pattern.findall(text)
                if tag_matches:
                    tags = tag_matches
                    # Remove tags from content
                    text = tag_pattern.sub("", text).strip()

                entries.append(
                    MemoryEntry(
                        content=text,
                        source=file_type,
                        tags=tags,
                    )
                )
            elif not line.startswith("#"):
                # Non-list, non-header lines treated as entries too
                entries.append(
                    MemoryEntry(
                        content=line,
                        source=file_type,
                    )
                )

        return entries[:MAX_ENTRIES_PER_FILE]
