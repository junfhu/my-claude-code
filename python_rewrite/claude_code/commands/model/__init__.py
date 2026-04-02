"""
/model — Switch the AI model.

Type: local_jsx (renders model picker).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalJSXCommand, TextResult


# ---------------------------------------------------------------------------
# Known models
# ---------------------------------------------------------------------------

KNOWN_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
]

# Short aliases
MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-3-5-haiku-20241022",
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
    "opus-3": "claude-3-opus-20240229",
}

_GLOBAL_CONFIG = Path.home() / ".claude" / "config.json"


def _get_current_model() -> str:
    """Return the currently active model identifier."""
    # Env var takes precedence
    env_model = os.environ.get("ANTHROPIC_MODEL", os.environ.get("CLAUDE_MODEL", ""))
    if env_model:
        return env_model
    # Fall back to config file
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
        return data.get("model", "claude-sonnet-4-20250514")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "claude-sonnet-4-20250514"


def _set_model(model_id: str) -> None:
    """Persist model selection to global config."""
    _GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data["model"] = model_id
    _GLOBAL_CONFIG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _resolve_model(name: str) -> str:
    """Resolve a model alias or short-name to a full model ID."""
    lower = name.lower().strip()
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    # Accept full IDs as-is
    return name.strip()


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/model [name]``.

    - No args:  Show current model and list available models.
    - With arg: Switch to the specified model.
    """
    current = _get_current_model()

    if not args or not args.strip():
        lines = [f"Current model: {current}", "", "Available models:"]
        for m in KNOWN_MODELS:
            marker = "  *" if m == current else ""
            # Find alias
            alias = next((a for a, mid in MODEL_ALIASES.items() if mid == m), "")
            alias_str = f"  (/{alias})" if alias else ""
            lines.append(f"  {m}{alias_str}{marker}")
        lines.append("")
        lines.append("Usage: /model <name or alias>")
        return TextResult(value="\n".join(lines))

    resolved = _resolve_model(args)
    _set_model(resolved)

    # Update context if available
    if context is not None and hasattr(context, "set_app_state"):
        context.set_app_state(lambda s: {**s, "mainLoopModel": resolved})

    return TextResult(
        value=f"Model switched to {resolved}.\n"
        f"(was: {current})"
    )


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

def _model_description() -> str:
    current = _get_current_model()
    short = current.split("-")[1] if "-" in current else current
    return f"Set the AI model for Claude Code (currently {short})"


command = LocalJSXCommand(
    name="model",
    description="Set the AI model for Claude Code",
    argument_hint="[model]",
    call=_execute,
)
