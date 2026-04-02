"""Commit attribution tracking — tags commits made by Claude Code."""

from __future__ import annotations

import os
import subprocess
from typing import Optional

ATTRIBUTION_TRAILER = "Generated-by: Claude Code"


def setup_commit_attribution(cwd: Optional[str] = None) -> None:
    """Configure git to add attribution trailers to commits."""
    try:
        subprocess.run(
            ["git", "config", "--local", "trailer.generatedby.key", "Generated-by"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def add_attribution_to_message(message: str) -> str:
    """Add Claude Code attribution trailer to a commit message."""
    if ATTRIBUTION_TRAILER in message:
        return message
    return f"{message.rstrip()}\n\n{ATTRIBUTION_TRAILER}"


def is_claude_commit(commit_hash: str, cwd: Optional[str] = None) -> bool:
    """Check if a commit was made by Claude Code."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", commit_hash],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return ATTRIBUTION_TRAILER in (result.stdout or "")
    except Exception:
        return False


def get_claude_commits(n: int = 50, cwd: Optional[str] = None) -> list[str]:
    """Get recent commits made by Claude Code."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", f"--grep={ATTRIBUTION_TRAILER}", "--format=%H"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return [h.strip() for h in (result.stdout or "").split("\n") if h.strip()]
    except Exception:
        return []
