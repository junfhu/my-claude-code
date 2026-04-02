"""
Settings loading and persistence.

Loads, merges, and persists user/project settings from JSON files.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_config_dir() -> str:
    return os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def get_user_settings() -> dict[str, Any]:
    """Load user-level settings from ``~/.claude/settings.json``."""
    return _read_json(os.path.join(_get_config_dir(), "settings.json"))


def get_project_settings(cwd: Optional[str] = None) -> dict[str, Any]:
    """Load project-level settings from ``.claude/settings.json``."""
    work_dir = cwd or os.getcwd()
    return _read_json(os.path.join(work_dir, ".claude", "settings.json"))


def get_managed_settings() -> dict[str, Any]:
    """Load enterprise/managed settings."""
    managed_dir = os.environ.get(
        "CLAUDE_MANAGED_CONFIG_DIR",
        "/etc/claude" if os.name != "nt" else r"C:\ProgramData\Claude",
    )
    return _read_json(os.path.join(managed_dir, "settings.json"))


def merge_settings(*sources: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge settings from multiple sources.

    Later sources take precedence. Lists are concatenated, dicts are merged.
    """
    result: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_settings(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value
            else:
                result[key] = value
    return result


def get_initial_settings(cwd: Optional[str] = None) -> dict[str, Any]:
    """Load and merge settings from all sources.

    Priority: managed > user > project.
    """
    managed = get_managed_settings()
    user = get_user_settings()
    project = get_project_settings(cwd)
    return merge_settings(project, user, managed)


def save_user_setting(key: str, value: Any) -> None:
    """Save a single setting to user settings."""
    settings = get_user_settings()
    settings[key] = value
    _write_json(os.path.join(_get_config_dir(), "settings.json"), settings)


def save_project_setting(key: str, value: Any, cwd: Optional[str] = None) -> None:
    """Save a single setting to project settings."""
    work_dir = cwd or os.getcwd()
    path = os.path.join(work_dir, ".claude", "settings.json")
    settings = get_project_settings(cwd)
    settings[key] = value
    _write_json(path, settings)


def get_setting(key: str, default: Any = None, cwd: Optional[str] = None) -> Any:
    """Get a setting value from merged settings."""
    settings = get_initial_settings(cwd)
    return settings.get(key, default)
