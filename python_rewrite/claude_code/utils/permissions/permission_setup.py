"""
Permission system setup.

Initializes the permission system by loading rules from settings,
CLAUDE.md files, and CLI flags.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def load_permission_rules(
    cwd: Optional[str] = None,
) -> dict[str, list[str]]:
    """Load permission rules from all sources.

    Returns dict with keys: ``allow``, ``deny``, ``command`` (for Bash rules).
    """
    rules: dict[str, list[str]] = {"allow": [], "deny": [], "command": []}

    # Load from user settings
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    settings_path = os.path.join(config_dir, "settings.json")
    try:
        with open(settings_path) as f:
            settings = json.load(f)
        rules["allow"].extend(settings.get("permissions", {}).get("allow", []))
        rules["deny"].extend(settings.get("permissions", {}).get("deny", []))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Load from project settings
    work_dir = cwd or os.getcwd()
    project_settings = os.path.join(work_dir, ".claude", "settings.json")
    try:
        with open(project_settings) as f:
            ps = json.load(f)
        rules["allow"].extend(ps.get("permissions", {}).get("allow", []))
        rules["deny"].extend(ps.get("permissions", {}).get("deny", []))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Load from environment
    env_allow = os.environ.get("CLAUDE_ALLOW_TOOLS", "")
    if env_allow:
        rules["allow"].extend(t.strip() for t in env_allow.split(",") if t.strip())
    env_deny = os.environ.get("CLAUDE_DENY_TOOLS", "")
    if env_deny:
        rules["deny"].extend(t.strip() for t in env_deny.split(",") if t.strip())

    return rules


def setup_permissions(
    cwd: Optional[str] = None,
    *,
    extra_allow: Optional[list[str]] = None,
    extra_deny: Optional[list[str]] = None,
) -> dict[str, list[str]]:
    """Set up the permission system for a session."""
    rules = load_permission_rules(cwd)
    if extra_allow:
        rules["allow"].extend(extra_allow)
    if extra_deny:
        rules["deny"].extend(extra_deny)
    # Deduplicate
    rules["allow"] = list(dict.fromkeys(rules["allow"]))
    rules["deny"] = list(dict.fromkeys(rules["deny"]))
    return rules
