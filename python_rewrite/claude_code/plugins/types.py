"""
Plugin type definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PluginStatus(str, Enum):
    LOADED = "loaded"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class PluginManifest:
    """Parsed plugin manifest (plugin.json)."""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: Optional[str] = None
    entry_point: Optional[str] = None
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    settings_schema: Optional[dict[str, Any]] = None


@dataclass
class LoadedPlugin:
    """A plugin that has been loaded from disk."""
    name: str
    source: str  # e.g. "slack@anthropic"
    manifest: PluginManifest
    status: PluginStatus = PluginStatus.LOADED
    path: Optional[str] = None
    error: Optional[str] = None
    mcp_servers: dict[str, Any] = field(default_factory=dict)

    @property
    def is_loaded(self) -> bool:
        return self.status == PluginStatus.LOADED

    @property
    def display_name(self) -> str:
        return self.manifest.description or self.name


@dataclass
class PluginError:
    """An error encountered during plugin loading."""
    plugin_name: str
    error: str
    phase: str = "load"  # load, validate, init
