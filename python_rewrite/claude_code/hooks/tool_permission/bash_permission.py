"""
Bash-specific permission logic.

Parses shell commands and matches them against permission rules like
``Bash(git *)``, ``Bash(npm test)``, etc.
"""

from __future__ import annotations

import fnmatch
import logging
import re
import shlex
from typing import Optional

logger = logging.getLogger(__name__)

# Commands that are generally safe (read-only)
SAFE_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "wc", "find", "grep", "egrep", "fgrep",
    "which", "whereis", "type", "file", "stat", "date", "echo", "printf",
    "pwd", "whoami", "hostname", "uname", "env", "printenv",
    "git log", "git status", "git diff", "git show", "git branch",
    "git remote", "git tag",
    "python --version", "python3 --version", "node --version",
    "npm --version", "pip --version",
})

# Commands that are always dangerous
DANGEROUS_COMMANDS = frozenset({
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
    "chmod -R 777 /", ":(){ :|:& };:",
    "curl | sh", "curl | bash", "wget | sh", "wget | bash",
})

# Patterns for dangerous operations
DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+(-[rf]+\s+)?/(?!tmp)"),  # rm outside /tmp
    re.compile(r">\s*/etc/"),  # overwrite /etc files
    re.compile(r"chmod\s+.*\s+/(?!tmp)"),  # chmod outside /tmp
    re.compile(r"chown\s+.*\s+/(?!tmp)"),  # chown outside /tmp
    re.compile(r"\bsudo\b"),  # anything with sudo
    re.compile(r"\bsu\s"),  # switch user
    re.compile(r"curl\s.*\|\s*(bash|sh|zsh)"),  # pipe curl to shell
    re.compile(r"wget\s.*\|\s*(bash|sh|zsh)"),
]


def parse_bash_command(command: str) -> list[str]:
    """Parse a bash command string into tokens.

    Handles pipes, redirections, and subshells to extract
    the primary command(s).
    """
    # Split on pipes and semicolons to get individual commands
    commands: list[str] = []
    try:
        # Simple split on |, ;, && for individual commands
        for part in re.split(r"\s*[|;&]+\s*", command):
            part = part.strip()
            if part:
                commands.append(part)
    except Exception:
        commands = [command.strip()]

    return commands


def is_bash_command_safe(command: str) -> bool:
    """Check if a bash command is safe (read-only)."""
    normalized = command.strip().lower()

    # Check against dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            return False

    # Parse into individual commands
    parts = parse_bash_command(command)
    for part in parts:
        # Get the base command (first word)
        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()

        if not tokens:
            continue

        base_cmd = tokens[0]

        # Check if the full command or base command is in safe set
        normalized_full = " ".join(tokens[:2]).lower() if len(tokens) > 1 else base_cmd.lower()
        if normalized_full in SAFE_COMMANDS or base_cmd.lower() in {"echo", "printf", "cat", "ls", "pwd"}:
            continue

        # If any individual command is not clearly safe, the whole thing isn't
        return False

    return True


def match_bash_permission_rule(
    rule_pattern: str,
    command: str,
) -> bool:
    """Check if a bash command matches a permission rule pattern.

    Patterns:
    - ``"git *"`` — matches any git command
    - ``"npm test"`` — matches exactly npm test
    - ``"python *.py"`` — matches python with .py files
    - ``"*"`` — matches everything
    """
    if rule_pattern == "*":
        return True

    command = command.strip()

    # Try exact match first
    if fnmatch.fnmatch(command, rule_pattern):
        return True

    # Try matching just the first command in a pipeline
    parts = parse_bash_command(command)
    if parts and fnmatch.fnmatch(parts[0], rule_pattern):
        return True

    return False


def classify_bash_command(command: str) -> str:
    """Classify a bash command as safe, dangerous, or unknown.

    Returns:
        ``"safe"``, ``"dangerous"``, or ``"unknown"``
    """
    normalized = command.strip().lower()

    # Check dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            return "dangerous"

    # Check dangerous commands
    for dc in DANGEROUS_COMMANDS:
        if dc in normalized:
            return "dangerous"

    # Check safe commands
    if is_bash_command_safe(command):
        return "safe"

    return "unknown"
