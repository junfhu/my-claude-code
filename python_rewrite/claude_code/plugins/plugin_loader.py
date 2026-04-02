"""
Plugin discovery and loading.

Loads plugins from ``~/.claude/plugins/``, validates manifests, discovers
MCP servers provided by plugins, and supports hot-reload.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .types import LoadedPlugin, PluginError, PluginManifest, PluginStatus

logger = logging.getLogger(__name__)


def _get_plugins_dir() -> str:
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    return os.path.join(config_dir, "plugins")


def _validate_manifest(raw: dict[str, Any], path: str) -> Optional[PluginManifest]:
    """Validate and parse a plugin manifest."""
    name = raw.get("name")
    if not name or not isinstance(name, str):
        logger.warning("Plugin at %s missing valid 'name'", path)
        return None

    return PluginManifest(
        name=name,
        version=str(raw.get("version", "0.0.0")),
        description=str(raw.get("description", "")),
        author=raw.get("author"),
        entry_point=raw.get("entryPoint") or raw.get("entry_point"),
        mcp_servers=raw.get("mcpServers", {}),
        skills=raw.get("skills", []),
        permissions=raw.get("permissions", []),
        settings_schema=raw.get("settingsSchema"),
    )


def load_plugin(plugin_dir: str) -> LoadedPlugin | PluginError:
    """Load a single plugin from a directory.

    Expects a ``plugin.json`` manifest file.
    """
    manifest_path = os.path.join(plugin_dir, "plugin.json")
    plugin_name = os.path.basename(plugin_dir)

    if not os.path.isfile(manifest_path):
        return PluginError(
            plugin_name=plugin_name,
            error=f"No plugin.json found in {plugin_dir}",
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return PluginError(
            plugin_name=plugin_name,
            error=f"Failed to read manifest: {exc}",
        )

    manifest = _validate_manifest(raw, manifest_path)
    if manifest is None:
        return PluginError(
            plugin_name=plugin_name,
            error="Invalid plugin manifest",
            phase="validate",
        )

    # Build MCP server configs with plugin source annotation
    source = f"{manifest.name}@{manifest.author or 'local'}"
    mcp_servers: dict[str, Any] = {}
    for server_name, server_config in manifest.mcp_servers.items():
        qualified_name = f"plugin:{manifest.name}:{server_name}"
        # Inject CLAUDE_PLUGIN_ROOT env var
        if isinstance(server_config, dict) and server_config.get("type", "stdio") == "stdio":
            env = dict(server_config.get("env", {}))
            env["CLAUDE_PLUGIN_ROOT"] = plugin_dir
            server_config = {**server_config, "env": env}
        mcp_servers[qualified_name] = server_config

    return LoadedPlugin(
        name=manifest.name,
        source=source,
        manifest=manifest,
        path=plugin_dir,
        mcp_servers=mcp_servers,
    )


def load_all_plugins(
    plugins_dir: Optional[str] = None,
) -> tuple[list[LoadedPlugin], list[PluginError]]:
    """Load all plugins from the plugins directory.

    Returns ``(loaded_plugins, errors)``.
    """
    if plugins_dir is None:
        plugins_dir = _get_plugins_dir()

    if not os.path.isdir(plugins_dir):
        return [], []

    loaded: list[LoadedPlugin] = []
    errors: list[PluginError] = []

    try:
        for entry in sorted(os.scandir(plugins_dir), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            result = load_plugin(entry.path)
            if isinstance(result, PluginError):
                errors.append(result)
            else:
                loaded.append(result)
    except OSError as exc:
        logger.warning("Failed to scan plugins dir: %s", exc)

    return loaded, errors


def get_plugin_mcp_servers(
    plugins: list[LoadedPlugin],
) -> dict[str, Any]:
    """Aggregate MCP server configs from all loaded plugins."""
    servers: dict[str, Any] = {}
    for plugin in plugins:
        if plugin.is_loaded:
            servers.update(plugin.mcp_servers)
    return servers


def reload_plugins(
    plugins_dir: Optional[str] = None,
) -> tuple[list[LoadedPlugin], list[PluginError]]:
    """Reload all plugins (hot-reload support)."""
    return load_all_plugins(plugins_dir)
