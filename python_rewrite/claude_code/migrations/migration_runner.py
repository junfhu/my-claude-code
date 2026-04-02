"""
Migration runner — applies data/settings migrations on startup.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

MIGRATION_VERSION_KEY = "_migration_version"


Migration = Callable[[dict[str, Any]], dict[str, Any]]


# Registry of migrations in order
_MIGRATIONS: list[tuple[int, str, Migration]] = []


def register_migration(version: int, description: str, fn: Migration) -> None:
    _MIGRATIONS.append((version, description, fn))
    _MIGRATIONS.sort(key=lambda m: m[0])


# -- Built-in migrations --

def _migration_001_normalize_tool_names(settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize old-style tool permission entries."""
    perms = settings.get("permissions", {})
    for key in ("allow", "deny"):
        rules = perms.get(key, [])
        perms[key] = [r.strip() for r in rules if isinstance(r, str) and r.strip()]
    settings["permissions"] = perms
    return settings


def _migration_002_mcp_server_format(settings: dict[str, Any]) -> dict[str, Any]:
    """Ensure MCP server configs have explicit type fields."""
    servers = settings.get("mcpServers", {})
    for name, config in servers.items():
        if isinstance(config, dict) and "type" not in config:
            if "command" in config:
                config["type"] = "stdio"
            elif "url" in config:
                config["type"] = "http"
    return settings


register_migration(1, "Normalize tool permission names", _migration_001_normalize_tool_names)
register_migration(2, "Add explicit MCP server types", _migration_002_mcp_server_format)


# -- Runner --

def _get_settings_path() -> str:
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    return os.path.join(config_dir, "settings.json")


def get_current_version(settings: dict[str, Any]) -> int:
    return settings.get(MIGRATION_VERSION_KEY, 0)


def run_migrations(settings_path: str | None = None) -> dict[str, Any]:
    """Run all pending migrations on the settings file.

    Returns the migrated settings dict.
    """
    path = settings_path or _get_settings_path()

    try:
        with open(path) as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    current_version = get_current_version(settings)
    applied = 0

    for version, description, fn in _MIGRATIONS:
        if version > current_version:
            logger.info("Running migration %d: %s", version, description)
            try:
                settings = fn(settings)
                settings[MIGRATION_VERSION_KEY] = version
                applied += 1
            except Exception as exc:
                logger.error("Migration %d failed: %s", version, exc)
                break

    if applied > 0:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
        logger.info("Applied %d migration(s)", applied)

    return settings
