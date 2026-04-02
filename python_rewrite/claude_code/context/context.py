"""
Context collection module.

This module is responsible for collecting the contextual information that
gets prepended to every conversation as part of the system prompt.  It
provides two main pieces of context:

    1. ``get_system_context()`` -- Git repository information:
       - Current branch name
       - Default/main branch name (for PR targeting)
       - Git status (modified/staged files, truncated at 2 KB)
       - Recent commit log (last 5 commits)
       - Git user name
       This context is a point-in-time snapshot taken at conversation start
       and does NOT update during the conversation.

    2. ``get_user_context()`` -- User configuration and memory files:
       - CLAUDE.md files (project-level, user-level, and from --add-dir)
       - Current date (for time-aware responses)

Both functions are memoised so they're computed once per conversation and
cached for the duration.  The memoisation cache can be cleared via
``clear_context_cache()`` (e.g. when system prompt injection changes).

Special modes:
    - CCR (Claude Code Remote): Skips git status (unnecessary overhead)
    - Bare mode (``--bare``): Skips auto-discovery of CLAUDE.md files, but
      honours explicit ``--add-dir`` directories
    - ``CLAUDE_CODE_DISABLE_CLAUDE_MDS``: Hard disable of all CLAUDE.md loading
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum characters for git status output before truncation.
# Large repos with many modified files can produce enormous status output
# that would consume too much of the context window.
MAX_STATUS_CHARS = 2000

# ---------------------------------------------------------------------------
# System prompt injection (debugging feature)
# ---------------------------------------------------------------------------

_system_prompt_injection: str | None = None


def get_system_prompt_injection() -> str | None:
    """Returns the current system prompt injection value (None if none set)."""
    return _system_prompt_injection


def set_system_prompt_injection(value: str | None) -> None:
    """Set a new system prompt injection and clear context caches.

    Allows injecting arbitrary text into the system prompt for
    cache-breaking during debugging.
    """
    global _system_prompt_injection
    _system_prompt_injection = value
    clear_context_cache()


# ---------------------------------------------------------------------------
# Internal git helpers
# ---------------------------------------------------------------------------

def _run_git(
    *args: str,
    cwd: str | None = None,
    timeout: float = 10.0,
) -> str:
    """Run a git command and return stripped stdout, or empty string on error."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _is_git_repo(cwd: str | None = None) -> bool:
    """Check if the current directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5.0,
            cwd=cwd,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _get_branch(cwd: str | None = None) -> str:
    """Get the current git branch name."""
    return _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def _get_default_branch(cwd: str | None = None) -> str:
    """Detect the default/main branch name.

    Tries origin/HEAD first, then falls back to common names.
    """
    # Try origin/HEAD
    result = _run_git(
        "symbolic-ref", "refs/remotes/origin/HEAD", "--short", cwd=cwd
    )
    if result:
        # "origin/main" -> "main"
        return result.removeprefix("origin/")

    # Fallback: check if common branch names exist
    for candidate in ("main", "master", "develop"):
        check = _run_git(
            "rev-parse", "--verify", f"refs/heads/{candidate}", cwd=cwd
        )
        if check:
            return candidate

    return "main"  # ultimate fallback


# ---------------------------------------------------------------------------
# Memoised context functions
#
# We use a simple dict-based cache that can be cleared explicitly.
# This replaces lodash memoize + .cache.clear() from the TS version.
# ---------------------------------------------------------------------------

_context_cache: dict[str, Any] = {}


def clear_context_cache() -> None:
    """Clear all memoised context caches.

    Called when:
        - A new conversation starts
        - System prompt injection changes
        - The user runs ``/clear caches``
    """
    _context_cache.clear()


# ---------------------------------------------------------------------------
# get_git_status
# ---------------------------------------------------------------------------

async def get_git_status(cwd: str | None = None) -> str | None:
    """Collect a snapshot of the current git repository state.

    Runs multiple git commands to efficiently collect:
        - Current branch (``git rev-parse --abbrev-ref HEAD``)
        - Default branch (detected from origin/HEAD or common names)
        - Working directory status (``git status --short``)
        - Last 5 commits (``git log --oneline -n 5``)
        - Git user name (``git config user.name``)

    The output is formatted as a human-readable string that becomes part of
    the system prompt.  Status output is truncated at 2 KB to prevent large
    repos from consuming too much context.

    Memoised: the git status is only collected once per conversation.

    Returns:
        Formatted git status string, or ``None`` if not in a git repo.
    """
    cache_key = "git_status"
    if cache_key in _context_cache:
        return _context_cache[cache_key]

    if os.environ.get("NODE_ENV") == "test":
        _context_cache[cache_key] = None
        return None

    start_time = time.monotonic()
    logger.debug("git_status_started")

    if not _is_git_repo(cwd):
        logger.debug(
            "git_status_skipped_not_git duration_ms=%.1f",
            (time.monotonic() - start_time) * 1000,
        )
        _context_cache[cache_key] = None
        return None

    try:
        loop = asyncio.get_running_loop()

        # Run all git commands concurrently via the thread pool
        branch_fut = loop.run_in_executor(None, _get_branch, cwd)
        main_branch_fut = loop.run_in_executor(None, _get_default_branch, cwd)
        status_fut = loop.run_in_executor(
            None,
            _run_git,
            "--no-optional-locks", "status", "--short",
        )
        log_fut = loop.run_in_executor(
            None,
            _run_git,
            "--no-optional-locks", "log", "--oneline", "-n", "5",
        )
        user_name_fut = loop.run_in_executor(
            None, _run_git, "config", "user.name"
        )

        branch, main_branch, status, log_output, user_name = await asyncio.gather(
            branch_fut, main_branch_fut, status_fut, log_fut, user_name_fut
        )

        # Truncate large status output
        if len(status) > MAX_STATUS_CHARS:
            truncated_status = (
                status[:MAX_STATUS_CHARS]
                + '\n... (truncated because it exceeds 2k characters. '
                'If you need more information, run "git status" using BashTool)'
            )
        else:
            truncated_status = status

        logger.debug(
            "git_status_completed duration_ms=%.1f truncated=%s",
            (time.monotonic() - start_time) * 1000,
            len(status) > MAX_STATUS_CHARS,
        )

        parts = [
            "This is the git status at the start of the conversation. "
            "Note that this status is a snapshot in time, and will not "
            "update during the conversation.",
            f"Current branch: {branch}",
            f"Main branch (you will usually use this for PRs): {main_branch}",
        ]
        if user_name:
            parts.append(f"Git user: {user_name}")
        parts.extend([
            f"Status:\n{truncated_status or '(clean)'}",
            f"Recent commits:\n{log_output}",
        ])

        result = "\n\n".join(parts)
        _context_cache[cache_key] = result
        return result

    except Exception:
        logger.exception(
            "git_status_failed duration_ms=%.1f",
            (time.monotonic() - start_time) * 1000,
        )
        _context_cache[cache_key] = None
        return None


# ---------------------------------------------------------------------------
# get_system_context
# ---------------------------------------------------------------------------

async def get_system_context(
    *,
    skip_git: bool = False,
) -> dict[str, str]:
    """Collect system-level context for the system prompt.

    Returns a key-value map of system context:
        - ``gitStatus``: Repository state snapshot
        - ``cacheBreaker``: Optional injection for debugging

    Args:
        skip_git: If ``True``, skip git status collection (useful for
            CCR mode or when git instructions are disabled).

    Returns:
        Dictionary of context entries (only non-null values included).
    """
    cache_key = "system_context"
    if cache_key in _context_cache:
        return _context_cache[cache_key]

    start_time = time.monotonic()
    logger.debug("system_context_started")

    # Skip git status in CCR mode or when explicitly requested
    is_remote = os.environ.get("CLAUDE_CODE_REMOTE", "").lower() in (
        "1", "true", "yes",
    )
    git_status: str | None = None
    if not is_remote and not skip_git:
        git_status = await get_git_status()

    # System prompt injection for cache breaking
    injection = get_system_prompt_injection()

    logger.debug(
        "system_context_completed duration_ms=%.1f has_git_status=%s "
        "has_injection=%s",
        (time.monotonic() - start_time) * 1000,
        git_status is not None,
        injection is not None,
    )

    result: dict[str, str] = {}
    if git_status:
        result["gitStatus"] = git_status
    if injection:
        result["cacheBreaker"] = f"[CACHE_BREAKER: {injection}]"

    _context_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# get_user_context
# ---------------------------------------------------------------------------

def _get_local_iso_date() -> str:
    """Get today's date in local ISO format (YYYY-MM-DD)."""
    return datetime.date.today().isoformat()


def _discover_claude_md_files(
    start_dir: str | None = None,
    additional_dirs: list[str] | None = None,
) -> list[Path]:
    """Discover CLAUDE.md files by walking up from start_dir.

    Looks for files named ``CLAUDE.md`` or ``.claude/settings.md`` at each
    directory level from ``start_dir`` up to the filesystem root.

    Also includes CLAUDE.md files from ``additional_dirs`` (--add-dir).

    Returns:
        List of paths to discovered memory files, in order from
        deepest (project) to shallowest (root / home).
    """
    if start_dir is None:
        start_dir = os.getcwd()

    files: list[Path] = []
    current = Path(start_dir).resolve()

    # Walk up the directory tree
    visited: set[Path] = set()
    while current not in visited:
        visited.add(current)

        # Check for CLAUDE.md
        claude_md = current / "CLAUDE.md"
        if claude_md.is_file():
            files.append(claude_md)

        # Check for .claude/settings.md
        settings_md = current / ".claude" / "settings.md"
        if settings_md.is_file():
            files.append(settings_md)

        parent = current.parent
        if parent == current:
            break
        current = parent

    # Check user home directory
    home = Path.home()
    home_claude_md = home / ".claude" / "CLAUDE.md"
    if home_claude_md.is_file() and home_claude_md not in files:
        files.append(home_claude_md)

    # Include additional directories
    if additional_dirs:
        for dir_path in additional_dirs:
            p = Path(dir_path).resolve()
            claude_md = p / "CLAUDE.md"
            if claude_md.is_file() and claude_md not in files:
                files.append(claude_md)

    return files


def _read_claude_md_files(paths: list[Path]) -> str | None:
    """Read and concatenate CLAUDE.md files.

    Returns:
        Concatenated file contents with source headers, or None if empty.
    """
    if not paths:
        return None

    sections: list[str] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                sections.append(
                    f"# From {path}\n\n{content}"
                )
        except (OSError, UnicodeDecodeError):
            logger.warning("Failed to read CLAUDE.md file: %s", path)

    return "\n\n---\n\n".join(sections) if sections else None


async def get_user_context(
    *,
    bare_mode: bool = False,
    additional_dirs: list[str] | None = None,
) -> dict[str, str]:
    """Load user configuration and memory files.

    Returns a key-value map of user-specific context:
        - ``claudeMd``: Concatenated CLAUDE.md file contents
        - ``currentDate``: Today's date in local ISO format

    Args:
        bare_mode: If ``True``, skip auto-discovery of CLAUDE.md files
            (but still honour ``additional_dirs``).
        additional_dirs: Extra directories to search for CLAUDE.md files
            (from ``--add-dir`` flag).

    Returns:
        Dictionary of context entries.
    """
    cache_key = "user_context"
    if cache_key in _context_cache:
        return _context_cache[cache_key]

    start_time = time.monotonic()
    logger.debug("user_context_started")

    # Determine whether to load CLAUDE.md files
    disable_claude_md = os.environ.get(
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS", ""
    ).lower() in ("1", "true", "yes")

    should_skip = disable_claude_md or (
        bare_mode and not additional_dirs
    )

    claude_md: str | None = None
    if not should_skip:
        if bare_mode:
            # Bare mode: only load from explicit additional_dirs
            paths = _discover_claude_md_files(
                start_dir=None, additional_dirs=additional_dirs
            )
            # Filter to only files from additional_dirs
            if additional_dirs:
                additional_set = {
                    Path(d).resolve() for d in additional_dirs
                }
                paths = [
                    p
                    for p in paths
                    if any(
                        p.resolve().is_relative_to(ad)
                        for ad in additional_set
                    )
                ]
        else:
            paths = _discover_claude_md_files(
                additional_dirs=additional_dirs
            )

        claude_md = _read_claude_md_files(paths)

    logger.debug(
        "user_context_completed duration_ms=%.1f claudemd_length=%d "
        "claudemd_disabled=%s",
        (time.monotonic() - start_time) * 1000,
        len(claude_md) if claude_md else 0,
        should_skip,
    )

    result: dict[str, str] = {}
    if claude_md:
        result["claudeMd"] = claude_md
    result["currentDate"] = f"Today's date is {_get_local_iso_date()}."

    _context_cache[cache_key] = result
    return result


__all__ = [
    "clear_context_cache",
    "get_git_status",
    "get_system_context",
    "get_system_prompt_injection",
    "get_user_context",
    "set_system_prompt_injection",
]
