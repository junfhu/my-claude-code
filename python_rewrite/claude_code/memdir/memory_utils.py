"""
Memory utility functions.

Helpers for parsing CLAUDE.md rules, estimating token counts,
and scanning for relevant memory content.
"""

from __future__ import annotations

import re
from typing import Optional


def rough_token_estimation(text: str) -> int:
    """Rough token count estimation (~4 chars per token for English)."""
    return max(1, len(text) // 4)


def extract_rules_from_memory(content: str) -> list[str]:
    """Extract individual rules/instructions from CLAUDE.md content.

    Rules are lines that start with ``-`` or ``*`` in a markdown list,
    or lines under a ``## Rules`` / ``## Instructions`` header.
    """
    rules: list[str] = []
    in_rules_section = False

    for line in content.split("\n"):
        stripped = line.strip()

        # Check for rules section header
        if re.match(r"^#{1,3}\s+(Rules|Instructions|Guidelines|Conventions)", stripped, re.IGNORECASE):
            in_rules_section = True
            continue

        # End of section on next header
        if stripped.startswith("#") and in_rules_section:
            in_rules_section = False
            continue

        # Collect bullet points
        if in_rules_section and re.match(r"^[-*]\s+", stripped):
            rule = re.sub(r"^[-*]\s+", "", stripped)
            if rule:
                rules.append(rule)

        # Also collect top-level bullets outside sections
        if not in_rules_section and re.match(r"^[-*]\s+", stripped):
            rule = re.sub(r"^[-*]\s+", "", stripped)
            if rule and len(rule) > 10:
                rules.append(rule)

    return rules


def memory_content_for_prompt(
    files: list[tuple[str, str]],
    *,
    max_tokens: int = 25_000,
) -> str:
    """Combine memory files into a single string for the system prompt.

    Each file is wrapped with its source path for attribution.
    """
    parts: list[str] = []
    total_tokens = 0

    for path, content in files:
        tokens = rough_token_estimation(content)
        if total_tokens + tokens > max_tokens:
            remaining = max_tokens - total_tokens
            if remaining > 50:
                truncated = content[: remaining * 4]
                parts.append(f"# From {path}\n{truncated}\n[... truncated]")
            break
        parts.append(f"# From {path}\n{content}")
        total_tokens += tokens

    return "\n\n".join(parts)


def parse_memory_paths_frontmatter(content: str) -> Optional[list[str]]:
    """Parse ``paths:`` frontmatter from CLAUDE.md to determine file-scope rules.

    Returns list of glob patterns, or None if no paths restriction.
    """
    # Check for YAML-like frontmatter at the top
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    fm = match.group(1)
    for line in fm.split("\n"):
        stripped = line.strip()
        if stripped.startswith("paths:"):
            value = stripped[6:].strip()
            if value:
                patterns = [p.strip() for p in value.split(",") if p.strip()]
                if patterns and not all(p in ("**", "**/*") for p in patterns):
                    return patterns
    return None


def is_memory_file_relevant(
    memory_path: str,
    active_files: list[str],
) -> bool:
    """Check if a memory file's path restrictions match any active files."""
    content = None
    try:
        with open(memory_path, "r", encoding="utf-8") as f:
            content = f.read(500)  # Only need frontmatter
    except (OSError, UnicodeDecodeError):
        return True  # Can't read → include it

    if content is None:
        return True

    patterns = parse_memory_paths_frontmatter(content)
    if patterns is None:
        return True  # No path restriction

    import fnmatch
    for active_file in active_files:
        for pattern in patterns:
            if fnmatch.fnmatch(active_file, pattern):
                return True
    return False
