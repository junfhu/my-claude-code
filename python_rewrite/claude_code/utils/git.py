"""Git utility functions."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: Optional[str] = None, timeout: int = 10) -> Optional[str]:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def is_git_repo(cwd: Optional[str] = None) -> bool:
    return _run_git(["rev-parse", "--is-inside-work-tree"], cwd) == "true"


def get_git_root(cwd: Optional[str] = None) -> Optional[str]:
    return _run_git(["rev-parse", "--show-toplevel"], cwd)


def get_current_branch(cwd: Optional[str] = None) -> Optional[str]:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)


def get_current_commit(cwd: Optional[str] = None) -> Optional[str]:
    return _run_git(["rev-parse", "HEAD"], cwd)


def get_remote_url(cwd: Optional[str] = None, remote: str = "origin") -> Optional[str]:
    return _run_git(["config", "--get", f"remote.{remote}.url"], cwd)


def get_diff(cwd: Optional[str] = None, *, staged: bool = False) -> Optional[str]:
    args = ["diff"]
    if staged:
        args.append("--staged")
    return _run_git(args, cwd, timeout=30)


def get_status(cwd: Optional[str] = None) -> Optional[str]:
    return _run_git(["status", "--porcelain"], cwd)


def get_modified_files(cwd: Optional[str] = None) -> list[str]:
    status = get_status(cwd)
    if not status:
        return []
    files = []
    for line in status.split("\n"):
        if len(line) > 3:
            files.append(line[3:].strip())
    return files


def stage_files(files: list[str], cwd: Optional[str] = None) -> bool:
    result = _run_git(["add", *files], cwd)
    return result is not None


def commit(message: str, cwd: Optional[str] = None) -> Optional[str]:
    return _run_git(["commit", "-m", message], cwd, timeout=30)


def get_log(n: int = 10, cwd: Optional[str] = None) -> list[dict[str, str]]:
    output = _run_git(
        ["log", f"-{n}", "--pretty=format:%H|%an|%ae|%s|%ci"],
        cwd, timeout=15,
    )
    if not output:
        return []
    entries = []
    for line in output.split("\n"):
        parts = line.split("|", 4)
        if len(parts) == 5:
            entries.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "message": parts[3],
                "date": parts[4],
            })
    return entries


def is_path_gitignored(path: str, cwd: Optional[str] = None) -> bool:
    result = _run_git(["check-ignore", "-q", path], cwd)
    return result is not None


def create_worktree(branch: str, path: str, cwd: Optional[str] = None) -> bool:
    return _run_git(["worktree", "add", path, branch], cwd) is not None


def remove_worktree(path: str, cwd: Optional[str] = None) -> bool:
    return _run_git(["worktree", "remove", path, "--force"], cwd) is not None
