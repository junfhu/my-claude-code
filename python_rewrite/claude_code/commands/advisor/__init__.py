"""
/advisor — Configure the advisor model.

Type: local (runs locally, returns text).

The advisor is a secondary model that reviews the primary model's output
before presenting it to the user.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...command_registry import LocalCommand, TextResult


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_GLOBAL_CONFIG = Path.home() / ".claude" / "config.json"


def _can_configure_advisor() -> bool:
    """Whether the current user can configure an advisor model."""
    # In the TS source this checks against GrowthBook flags.
    # For Python rewrite, allow when env var is set or always-on for now.
    return os.environ.get("ENABLE_ADVISOR", "").lower() in (
        "1", "true", "yes",
    ) or os.environ.get("USER_TYPE", "") == "ant"


def _get_advisor_model() -> str | None:
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
        return data.get("advisorModel")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _set_advisor_model(model: str | None) -> None:
    _GLOBAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    if model is None:
        data.pop("advisorModel", None)
    else:
        data["advisorModel"] = model
    _GLOBAL_CONFIG.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

async def _execute(args: str = "", context: Any = None) -> TextResult:
    """
    Handle ``/advisor [<model>|off]``.

    - No args: Show current advisor status.
    - ``off`` / ``unset``: Disable the advisor.
    - ``<model>``: Set the advisor to the specified model.
    """
    arg = args.strip().lower() if args else ""

    if not arg:
        current = _get_advisor_model()
        if not current:
            return TextResult(
                value='Advisor: not set\n'
                'Use "/advisor <model>" to enable (e.g. "/advisor opus").'
            )
        return TextResult(
            value=f"Advisor: {current}\n"
            'Use "/advisor unset" to disable or "/advisor <model>" to change.'
        )

    if arg in ("unset", "off"):
        prev = _get_advisor_model()
        _set_advisor_model(None)
        if context is not None and hasattr(context, "set_app_state"):
            context.set_app_state(lambda s: {**s, "advisorModel": None})
        return TextResult(
            value=f"Advisor disabled (was {prev})." if prev else "Advisor already unset."
        )

    # Set advisor model
    model = args.strip()
    _set_advisor_model(model)
    if context is not None and hasattr(context, "set_app_state"):
        context.set_app_state(lambda s: {**s, "advisorModel": model})

    return TextResult(value=f"Advisor set to {model}.")


# ---------------------------------------------------------------------------
# Exported command definition
# ---------------------------------------------------------------------------

command = LocalCommand(
    name="advisor",
    description="Configure the advisor model",
    argument_hint="[<model>|off]",
    is_enabled=_can_configure_advisor,
    is_hidden=lambda: not _can_configure_advisor(),
    supports_non_interactive=True,
    execute=_execute,
)
