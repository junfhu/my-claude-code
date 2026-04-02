"""
CLAUDE.md memory system.

Reads and writes CLAUDE.md files from project directories and
``~/.claude/``. These files contain persistent instructions, rules,
and context for the Claude Code agent.

Mirrors src/memdir/memdir.ts + paths.ts.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CLAUDE_MD_FILENAME = "CLAUDE.md"
CLAUDE_LOCAL_MD_FILENAME = "CLAUDE.local.md"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def get_user_memory_path() -> str:
    """Path to the user-global CLAUDE.md."""
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    return os.path.join(config_dir, CLAUDE_MD_FILENAME)


def get_project_memory_paths(cwd: Optional[str] = None) -> list[str]:
    """All CLAUDE.md files from cwd up to the user's home directory.

    Returns paths in order from most-specific (project) to least-specific (home).
    """
    if cwd is None:
        cwd = os.getcwd()

    paths: list[str] = []
    current = os.path.abspath(cwd)
    home = os.path.expanduser("~")

    while True:
        for name in [CLAUDE_MD_FILENAME, CLAUDE_LOCAL_MD_FILENAME]:
            candidate = os.path.join(current, name)
            if os.path.isfile(candidate):
                paths.append(candidate)

        # Also check .claude/ subdirectory
        claude_dir = os.path.join(current, ".claude")
        if os.path.isdir(claude_dir):
            for name in [CLAUDE_MD_FILENAME, CLAUDE_LOCAL_MD_FILENAME]:
                candidate = os.path.join(claude_dir, name)
                if os.path.isfile(candidate):
                    paths.append(candidate)

        parent = os.path.dirname(current)
        if parent == current or current == home:
            break
        current = parent

    return paths


def get_memory_paths(cwd: Optional[str] = None) -> list[str]:
    """All memory file paths (user + project) in priority order."""
    paths = get_project_memory_paths(cwd)
    user_path = get_user_memory_path()
    if os.path.isfile(user_path):
        paths.append(user_path)
    return paths


def get_managed_memory_path() -> Optional[str]:
    """Path to the managed/enterprise CLAUDE.md, if it exists."""
    managed_dir = os.environ.get(
        "CLAUDE_MANAGED_CONFIG_DIR",
        "/etc/claude" if os.name != "nt" else r"C:\ProgramData\Claude",
    )
    path = os.path.join(managed_dir, ".claude", CLAUDE_MD_FILENAME)
    return path if os.path.isfile(path) else None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_memory_file(path: str) -> Optional[str]:
    """Read a single memory file, returning None if it doesn't exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None


def read_memory_files(cwd: Optional[str] = None) -> list[tuple[str, str]]:
    """Read all memory files. Returns list of ``(path, content)`` tuples."""
    results: list[tuple[str, str]] = []

    # Managed (enterprise) memory
    managed = get_managed_memory_path()
    if managed:
        content = read_memory_file(managed)
        if content:
            results.append((managed, content))

    # User global memory
    user_path = get_user_memory_path()
    content = read_memory_file(user_path)
    if content:
        results.append((user_path, content))

    # Project memory files (most specific last)
    project_paths = get_project_memory_paths(cwd)
    for path in reversed(project_paths):
        content = read_memory_file(path)
        if content:
            results.append((path, content))

    return results


def filter_injected_memory_files(
    files: list[tuple[str, str]],
    *,
    max_total_chars: int = 100_000,
) -> list[tuple[str, str]]:
    """Filter memory files to fit within a token budget.

    Prioritises managed > user > project files. Truncates if needed.
    """
    filtered: list[tuple[str, str]] = []
    total = 0

    for path, content in files:
        if total + len(content) > max_total_chars:
            remaining = max_total_chars - total
            if remaining > 100:
                truncated = content[:remaining] + "\n[... truncated]"
                filtered.append((path, truncated))
            break
        filtered.append((path, content))
        total += len(content)

    return filtered


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_memory(
    content: str,
    *,
    scope: str = "project",
    cwd: Optional[str] = None,
    filename: str = CLAUDE_MD_FILENAME,
) -> str:
    """Write memory content to the appropriate CLAUDE.md file.

    Args:
        content: The markdown content to write.
        scope: ``"user"`` for global, ``"project"`` for project-level.
        cwd: Working directory for project scope.
        filename: Filename to write (default ``CLAUDE.md``).

    Returns:
        The path that was written.
    """
    if scope == "user":
        path = os.path.join(os.path.dirname(get_user_memory_path()), filename)
    else:
        base = cwd or os.getcwd()
        path = os.path.join(base, filename)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Wrote memory to %s (%d chars)", path, len(content))
    return path


def append_to_memory(
    content: str,
    *,
    scope: str = "project",
    cwd: Optional[str] = None,
) -> str:
    """Append content to the appropriate CLAUDE.md file."""
    if scope == "user":
        path = get_user_memory_path()
    else:
        path = os.path.join(cwd or os.getcwd(), CLAUDE_MD_FILENAME)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = read_memory_file(path) or ""
    new_content = existing.rstrip() + "\n\n" + content if existing.strip() else content

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return path
