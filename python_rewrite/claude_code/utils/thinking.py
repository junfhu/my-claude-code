"""Thinking configuration — controls extended thinking / chain-of-thought."""

from __future__ import annotations

import os
from typing import Optional


def get_thinking_budget(model: Optional[str] = None) -> int:
    """Get the thinking token budget for the specified model."""
    env_budget = os.environ.get("CLAUDE_THINKING_BUDGET")
    if env_budget:
        try:
            return int(env_budget)
        except ValueError:
            pass

    if model and "opus" in model.lower():
        return 16000
    return 10000


def is_thinking_enabled() -> bool:
    """Check if extended thinking is enabled."""
    val = os.environ.get("CLAUDE_THINKING", "true")
    return val.lower() not in ("0", "false", "no", "off")


def get_thinking_config(model: Optional[str] = None) -> dict[str, int | str]:
    """Get the thinking configuration for API calls."""
    if not is_thinking_enabled():
        return {}
    budget = get_thinking_budget(model)
    return {"type": "enabled", "budget_tokens": budget}
