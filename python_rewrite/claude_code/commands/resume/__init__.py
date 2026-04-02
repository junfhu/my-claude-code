"""
/resume — Restore a previous conversation session.

Type: local_jsx (renders session picker).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Session storage
# ---------------------------------------------------------------------------

_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def _list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """
    List recent sessions from the sessions directory.

    Each session is stored as a JSON file with metadata.
    """
    if not _SESSIONS_DIR.is_dir():
        return []

    sessions: list[dict[str, Any]] = []
    for f in sorted(_SESSIONS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": f.stem,
                "title": data.get("title", "(untitled)"),
                "created": data.get("created", ""),
                "messages": data.get("messageCount", 0),
                "path": str(f),
                "cwd": data.get("cwd", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue
        if len(sessions) >= limit:
            break

    return sessions


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/resume [session-id | search term]``.

    - No args:    List recent sessions to choose from.
    - With arg:   Resume a specific session by ID or search title.
    """
    query = args.strip() if args else ""

    sessions = _list_sessions()
    if not sessions:
        return TextResult(value="No previous sessions found.")

    if query:
        # Try exact match by ID first
        for s in sessions:
            if s["id"] == query:
                return TextResult(
                    value=f"Resuming session: {s['title']} ({s['id']})\n"
                    f"Messages: {s['messages']}"
                )

        # Fuzzy search by title
        matches = [
            s for s in sessions
            if query.lower() in s["title"].lower() or query.lower() in s["id"].lower()
        ]
        if len(matches) == 1:
            s = matches[0]
            return TextResult(
                value=f"Resuming session: {s['title']} ({s['id']})\n"
                f"Messages: {s['messages']}"
            )
        if matches:
            lines = [f"Multiple sessions match {query!r}:", ""]
            for s in matches[:10]:
                lines.append(f"  {s['id']}  {s['title']}  ({s['messages']} msgs)")
            return TextResult(value="\n".join(lines))

        return TextResult(value=f"No session matching {query!r} found.")

    # List recent sessions
    lines = ["Recent Sessions", "=" * 50, ""]
    for s in sessions:
        lines.append(f"  {s['id']}  {s['title']}")
        if s["cwd"]:
            lines.append(f"    {'':>12}  cwd: {s['cwd']}  ({s['messages']} msgs)")

    lines.append("")
    lines.append("Usage: /resume <session-id or search term>")
    return TextResult(value="\n".join(lines))


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalJSXCommand(
    name="resume",
    description="Resume a previous conversation",
    aliases=["continue"],
    argument_hint="[conversation id or search term]",
    call=_execute,
)
