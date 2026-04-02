"""
/doctor — Run environment diagnostics.

Type: local_jsx (renders diagnostic results).

Checks dependencies, API keys, git configuration, Python version, etc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Feature-flag helper
# ---------------------------------------------------------------------------

def _is_doctor_disabled() -> bool:
    return os.environ.get("DISABLE_DOCTOR_COMMAND", "").lower() in (
        "1", "true", "yes",
    )


# ---------------------------------------------------------------------------
# Diagnostic checks
# ---------------------------------------------------------------------------

def _check_binary(name: str) -> tuple[bool, str]:
    """Return (found, detail) for a CLI binary."""
    path = shutil.which(name)
    if path:
        try:
            version = subprocess.check_output(
                [name, "--version"], stderr=subprocess.STDOUT, timeout=5
            ).decode().strip().split("\n")[0]
            return True, f"{name}: {version} ({path})"
        except Exception:
            return True, f"{name}: found at {path} (version unknown)"
    return False, f"{name}: NOT FOUND"


def _check_api_key() -> tuple[bool, str]:
    """Check that an Anthropic API key is configured."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
        return True, f"ANTHROPIC_API_KEY: set ({masked})"
    # Check for OAuth-based auth
    if os.environ.get("CLAUDE_AI_SUBSCRIBER", ""):
        return True, "Auth: claude.ai OAuth session"
    return False, "ANTHROPIC_API_KEY: NOT SET"


def _check_git_repo() -> tuple[bool, str]:
    """Check whether we are inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL, timeout=5,
            ).decode().strip()
            return True, f"Git repo: {root}"
        return False, "Git repo: not inside a git repository"
    except FileNotFoundError:
        return False, "Git: binary not found"
    except Exception as exc:
        return False, f"Git: error — {exc}"


def _check_python() -> tuple[bool, str]:
    """Report Python version."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    status = "OK" if ok else "WARN: Python >= 3.10 recommended"
    return ok, f"Python: {version} ({status})"


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """Run all diagnostic checks and return a formatted report."""
    checks = [
        ("Python", _check_python()),
        ("API Key", _check_api_key()),
        ("Git", _check_git_repo()),
        ("git", _check_binary("git")),
        ("node", _check_binary("node")),
        ("gh (GitHub CLI)", _check_binary("gh")),
        ("ripgrep (rg)", _check_binary("rg")),
    ]

    lines = ["Claude Code Environment Diagnostics", "=" * 44, ""]

    all_ok = True
    for label, (ok, detail) in checks:
        icon = "\u2713" if ok else "\u2717"  # ✓ or ✗
        lines.append(f"  [{icon}] {detail}")
        if not ok:
            all_ok = False

    lines.append("")
    if all_ok:
        lines.append("All checks passed!")
    else:
        lines.append(
            "Some checks failed.  Review the items above and fix as needed."
        )

    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="doctor",
    description="Diagnose and verify your Claude Code installation and settings",
    is_enabled=lambda: not _is_doctor_disabled(),
    call=_execute,
)
