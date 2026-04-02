"""
/voice — Toggle voice mode.

Type: local (runs locally, returns text).

Voice mode enables speech-to-text input for the REPL.
Available only for claude.ai subscribers when the feature flag is enabled.
"""

from __future__ import annotations

import os
from typing import Any

from ...command_registry import (
    CommandAvailability,
    LocalCommand,
    TextResult,
)


# ---------------------------------------------------------------------------
# Feature flag helpers
# ---------------------------------------------------------------------------

def _is_voice_enabled() -> bool:
    """Check whether the voice mode feature is enabled."""
    return os.environ.get("VOICE_MODE", "").lower() in ("1", "true", "yes")


def _is_voice_hidden() -> bool:
    """Voice is hidden unless the feature flag is on."""
    return not _is_voice_enabled()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_voice_active = False


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """Toggle voice mode on/off."""
    global _voice_active

    _voice_active = not _voice_active

    if _voice_active:
        return TextResult(
            value="Voice mode enabled.\n"
            "Speak into your microphone — speech will be transcribed to text input.\n"
            "Use /voice again to disable."
        )
    else:
        return TextResult(value="Voice mode disabled.")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="voice",
    description="Toggle voice mode",
    availability=[CommandAvailability.CLAUDE_AI],
    is_enabled=_is_voice_enabled,
    is_hidden=_is_voice_hidden,
    supports_non_interactive=False,
    execute=_execute,
)
