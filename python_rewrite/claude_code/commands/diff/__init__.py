"""
/diff — View file changes (git diff).

Type: local_jsx (renders diff output).
"""

from __future__ import annotations

import subprocess
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Show uncommitted changes and per-turn diffs.

    - No args:  ``git diff`` (unstaged) + ``git diff --cached`` (staged)
    - With arg: ``git diff <arg>``  (e.g. a commit range or file path)
    """
    try:
        parts: list[str] = []

        if args and args.strip():
            # User specified a custom diff target
            result = subprocess.run(
                ["git", "diff", *args.strip().split()],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return TextResult(value=f"git diff error: {result.stderr.strip()}")
            parts.append(result.stdout if result.stdout.strip() else "(no diff)")
        else:
            # Staged changes
            staged = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True, text=True, timeout=30,
            )
            # Unstaged changes
            unstaged = subprocess.run(
                ["git", "diff"],
                capture_output=True, text=True, timeout=30,
            )

            if staged.stdout.strip():
                parts.append("=== Staged Changes ===\n" + staged.stdout)
            if unstaged.stdout.strip():
                parts.append("=== Unstaged Changes ===\n" + unstaged.stdout)

            if not parts:
                return TextResult(value="No uncommitted changes.")

        return TextResult(value="\n".join(parts))

    except FileNotFoundError:
        return TextResult(value="Error: git is not installed or not in PATH.")
    except subprocess.TimeoutExpired:
        return TextResult(value="Error: git diff timed out.")
    except Exception as exc:
        return TextResult(value=f"Error running git diff: {exc}")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="diff",
    description="View uncommitted changes and per-turn diffs",
    call=_execute,
)
