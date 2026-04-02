"""
MCP server configuration loading, policy filtering, and deduplication.

Mirrors src/services/mcp/config.ts — responsible for aggregating MCP server
definitions from every source (settings files, .mcp.json, CLI flags,
enterprise policy, plugins, claude.ai connectors) into a single merged map,
with policy allow/deny filtering and signature-based deduplication.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from .normalization import normalize_name_for_mcp
from .types import (
    ConfigScope,
    McpHTTPServerConfig,
    McpJsonConfig,
    McpServerConfig,
    McpSSEServerConfig,
    McpStdioServerConfig,
    McpWebSocketServerConfig,
    ScopedMcpServerConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment-variable expansion
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def expand_env_vars_in_string(value: str) -> tuple[str, list[str]]:
    """Expand ``${VAR}`` and ``$VAR`` references in *value*.

    Returns ``(expanded_string, list_of_missing_vars)``.
    """
    missing: list[str] = []

    def _replace(m: re.Match[str]) -> str:
        var = m.group(1) or m.group(2)
        val = os.environ.get(var)
        if val is None:
            missing.append(var)
            return m.group(0)  # leave unexpanded
        return val

    return _ENV_VAR_RE.sub(_replace, value), missing


def _expand_config(config: McpServerConfig) -> tuple[McpServerConfig, list[str]]:
    """Expand environment variables inside an MCP server config."""
    all_missing: list[str] = []

    def _exp(s: str) -> str:
        expanded, miss = expand_env_vars_in_string(s)
        all_missing.extend(miss)
        return expanded

    cfg_type = getattr(config, "type", None) or "stdio"

    if cfg_type in (None, "stdio") and isinstance(config, McpStdioServerConfig):
        return McpStdioServerConfig(
            type=config.type,
            command=_exp(config.command),
            args=[_exp(a) for a in config.args],
            env={k: _exp(v) for k, v in config.env.items()} if config.env else None,
        ), all_missing

    if cfg_type in ("sse", "http", "ws"):
        url = _exp(getattr(config, "url", ""))
        headers = None
        if hasattr(config, "headers") and config.headers:
            headers = {k: _exp(v) for k, v in config.headers.items()}
        if isinstance(config, McpSSEServerConfig):
            return McpSSEServerConfig(url=url, headers=headers, headers_helper=config.headers_helper, oauth=config.oauth), all_missing
        if isinstance(config, McpHTTPServerConfig):
            return McpHTTPServerConfig(url=url, headers=headers, headers_helper=config.headers_helper, oauth=config.oauth), all_missing
        if isinstance(config, McpWebSocketServerConfig):
            return McpWebSocketServerConfig(url=url, headers=headers, headers_helper=config.headers_helper), all_missing

    return config, all_missing


# ---------------------------------------------------------------------------
# Server signature (for deduplication)
# ---------------------------------------------------------------------------

_CCR_PROXY_PATH_MARKERS = ["/v2/session_ingress/shttp/mcp/", "/v2/ccr-sessions/"]


def unwrap_ccr_proxy_url(url: str) -> str:
    """If *url* is a CCR proxy URL, extract the original vendor URL from ``mcp_url``."""
    if not any(m in url for m in _CCR_PROXY_PATH_MARKERS):
        return url
    try:
        from urllib.parse import parse_qs, urlparse
        parsed = urlparse(url)
        original = parse_qs(parsed.query).get("mcp_url", [None])[0]
        return original or url
    except Exception:
        return url


def get_server_command_array(config: McpServerConfig) -> list[str] | None:
    """Extract command array from a stdio server config (or None for remote)."""
    cfg_type = getattr(config, "type", None)
    if cfg_type is not None and cfg_type != "stdio":
        return None
    if isinstance(config, McpStdioServerConfig):
        return [config.command, *config.args]
    return None


def get_server_url(config: McpServerConfig) -> str | None:
    """Extract URL from a remote server config."""
    return getattr(config, "url", None)


def get_mcp_server_signature(config: McpServerConfig) -> str | None:
    """Compute a dedup signature for an MCP server config.

    Two configs with the same signature are the same server. Returns ``None``
    only for configs with neither command nor url (sdk type).
    """
    cmd = get_server_command_array(config)
    if cmd is not None:
        return f"stdio:{json.dumps(cmd)}"
    url = get_server_url(config)
    if url:
        return f"url:{unwrap_ccr_proxy_url(url)}"
    return None


# ---------------------------------------------------------------------------
# Add scope to configs
# ---------------------------------------------------------------------------

def _add_scope(
    servers: dict[str, McpServerConfig] | None,
    scope: ConfigScope,
) -> dict[str, ScopedMcpServerConfig]:
    if not servers:
        return {}
    return {
        name: ScopedMcpServerConfig(config=cfg, scope=scope)
        for name, cfg in servers.items()
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def dedup_plugin_mcp_servers(
    plugin_servers: dict[str, ScopedMcpServerConfig],
    manual_servers: dict[str, ScopedMcpServerConfig],
) -> tuple[dict[str, ScopedMcpServerConfig], list[dict[str, str]]]:
    """Drop plugin servers whose signature matches a manual or earlier-plugin server."""
    manual_sigs: dict[str, str] = {}
    for name, scfg in manual_servers.items():
        sig = get_mcp_server_signature(scfg.config)
        if sig and sig not in manual_sigs:
            manual_sigs[sig] = name

    servers: dict[str, ScopedMcpServerConfig] = {}
    suppressed: list[dict[str, str]] = []
    seen_plugin_sigs: dict[str, str] = {}

    for name, scfg in plugin_servers.items():
        sig = get_mcp_server_signature(scfg.config)
        if sig is None:
            servers[name] = scfg
            continue
        manual_dup = manual_sigs.get(sig)
        if manual_dup is not None:
            suppressed.append({"name": name, "duplicateOf": manual_dup})
            continue
        plugin_dup = seen_plugin_sigs.get(sig)
        if plugin_dup is not None:
            suppressed.append({"name": name, "duplicateOf": plugin_dup})
            continue
        seen_plugin_sigs[sig] = name
        servers[name] = scfg

    return servers, suppressed


# ---------------------------------------------------------------------------
# Policy (allow/deny) filtering
# ---------------------------------------------------------------------------

_disabled_servers: set[str] = set()


def disable_mcp_server(name: str) -> None:
    _disabled_servers.add(name)


def enable_mcp_server(name: str) -> None:
    _disabled_servers.discard(name)


def is_mcp_server_disabled(name: str) -> bool:
    return name in _disabled_servers


def _url_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern).replace(r"\*", ".*")
    return re.compile(f"^{escaped}$")


def _url_matches_pattern(url: str, pattern: str) -> bool:
    return bool(_url_pattern_to_regex(pattern).match(url))


def filter_mcp_servers_by_policy(
    configs: dict[str, ScopedMcpServerConfig],
    *,
    allowed_servers: list[dict[str, str]] | None = None,
    denied_servers: list[dict[str, str]] | None = None,
) -> tuple[dict[str, ScopedMcpServerConfig], list[str]]:
    """Filter configs by allow/deny policy. Returns ``(allowed, blocked_names)``."""
    allowed: dict[str, ScopedMcpServerConfig] = {}
    blocked: list[str] = []

    for name, scfg in configs.items():
        cfg_type = getattr(scfg.config, "type", None)
        # SDK servers are exempt from policy
        if cfg_type == "sdk":
            allowed[name] = scfg
            continue

        # Check deny list first
        if denied_servers:
            denied = False
            for entry in denied_servers:
                if "serverName" in entry and entry["serverName"] == name:
                    denied = True
                    break
                url = get_server_url(scfg.config)
                if url and "serverUrl" in entry and _url_matches_pattern(url, entry["serverUrl"]):
                    denied = True
                    break
            if denied:
                blocked.append(name)
                continue

        # Check allow list (if any)
        if allowed_servers is not None:
            if len(allowed_servers) == 0:
                blocked.append(name)
                continue
            matched = False
            for entry in allowed_servers:
                if "serverName" in entry and entry["serverName"] == name:
                    matched = True
                    break
                url = get_server_url(scfg.config)
                if url and "serverUrl" in entry and _url_matches_pattern(url, entry["serverUrl"]):
                    matched = True
                    break
            if not matched:
                blocked.append(name)
                continue

        allowed[name] = scfg

    return allowed, blocked


# ---------------------------------------------------------------------------
# .mcp.json reading / writing
# ---------------------------------------------------------------------------

def read_mcp_json(cwd: str | None = None) -> McpJsonConfig:
    """Read ``.mcp.json`` from *cwd* (defaults to current working directory)."""
    if cwd is None:
        cwd = os.getcwd()
    path = os.path.join(cwd, ".mcp.json")
    try:
        with open(path, "r") as fp:
            raw = json.load(fp)
        return McpJsonConfig(**raw)
    except (FileNotFoundError, json.JSONDecodeError):
        return McpJsonConfig()


def write_mcp_json(config: McpJsonConfig, cwd: str | None = None) -> None:
    """Atomically write ``.mcp.json`` to *cwd*."""
    if cwd is None:
        cwd = os.getcwd()
    path = os.path.join(cwd, ".mcp.json")

    existing_mode: int | None = None
    try:
        existing_mode = os.stat(path).st_mode
    except FileNotFoundError:
        pass

    tmp_path = f"{path}.tmp.{os.getpid()}.{int(__import__('time').time() * 1000)}"
    with open(tmp_path, "w") as fp:
        json.dump(config.model_dump(), fp, indent=2)
        fp.flush()
        os.fsync(fp.fileno())

    if existing_mode is not None:
        os.chmod(tmp_path, existing_mode)

    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Enterprise / managed config
# ---------------------------------------------------------------------------

def get_enterprise_mcp_file_path() -> str:
    """Path to the managed MCP configuration file."""
    managed = os.environ.get(
        "CLAUDE_MANAGED_CONFIG_DIR",
        "/etc/claude" if os.name != "nt" else r"C:\ProgramData\Claude",
    )
    return os.path.join(managed, "managed-mcp.json")


def _load_enterprise_configs() -> dict[str, ScopedMcpServerConfig]:
    path = get_enterprise_mcp_file_path()
    try:
        with open(path, "r") as fp:
            raw = json.load(fp)
        mcp_json = McpJsonConfig(**raw)
        return _add_scope(mcp_json.mcpServers, ConfigScope.ENTERPRISE)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Config loading (main entry point)
# ---------------------------------------------------------------------------

def _load_user_config() -> dict[str, ScopedMcpServerConfig]:
    """Load MCP servers from the user-level settings file."""
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    settings_path = os.path.join(config_dir, "settings.json")
    try:
        with open(settings_path, "r") as fp:
            settings = json.load(fp)
        mcp_servers = settings.get("mcpServers", {})
        return _add_scope(mcp_servers, ConfigScope.USER)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_project_config(cwd: str | None = None) -> dict[str, ScopedMcpServerConfig]:
    """Load MCP servers from .mcp.json in the project directory."""
    mcp_json = read_mcp_json(cwd)
    return _add_scope(mcp_json.mcpServers, ConfigScope.PROJECT)


def get_all_mcp_configs(
    cwd: str | None = None,
    *,
    cli_configs: dict[str, McpServerConfig] | None = None,
    allowed_servers: list[dict[str, str]] | None = None,
    denied_servers: list[dict[str, str]] | None = None,
) -> dict[str, ScopedMcpServerConfig]:
    """Load and merge MCP configs from all sources with policy filtering.

    Sources (highest priority first):
    1. Enterprise/managed config
    2. User settings (``~/.claude/settings.json``)
    3. Project config (``.mcp.json``)
    4. CLI-provided configs
    """
    enterprise = _load_enterprise_configs()
    user = _load_user_config()
    project = _load_project_config(cwd)

    cli_scoped: dict[str, ScopedMcpServerConfig] = {}
    if cli_configs:
        cli_scoped = _add_scope(cli_configs, ConfigScope.DYNAMIC)

    # Merge: enterprise overrides user overrides project overrides CLI
    merged: dict[str, ScopedMcpServerConfig] = {}
    for source in [cli_scoped, project, user, enterprise]:
        merged.update(source)

    # Expand environment variables in all configs
    expanded: dict[str, ScopedMcpServerConfig] = {}
    for name, scfg in merged.items():
        exp_config, missing = _expand_config(scfg.config)
        if missing:
            logger.warning(
                "MCP server %s references undefined env vars: %s",
                name,
                ", ".join(missing),
            )
        expanded[name] = ScopedMcpServerConfig(
            config=exp_config,
            scope=scfg.scope,
            plugin_source=scfg.plugin_source,
        )

    # Apply policy filter
    allowed_result, blocked = filter_mcp_servers_by_policy(
        expanded,
        allowed_servers=allowed_servers,
        denied_servers=denied_servers,
    )
    if blocked:
        logger.info("MCP servers blocked by policy: %s", ", ".join(blocked))

    return allowed_result


# ---------------------------------------------------------------------------
# Server add / remove helpers
# ---------------------------------------------------------------------------

def add_mcp_server(
    name: str,
    config: McpServerConfig,
    *,
    scope: str = "project",
    cwd: str | None = None,
) -> None:
    """Add an MCP server to the appropriate config file."""
    if scope == "project":
        mcp_json = read_mcp_json(cwd)
        mcp_json.mcpServers[name] = config
        write_mcp_json(mcp_json, cwd)
    elif scope == "user":
        config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(os.path.expanduser("~"), ".claude"),
        )
        settings_path = os.path.join(config_dir, "settings.json")
        try:
            with open(settings_path, "r") as fp:
                settings = json.load(fp)
        except (FileNotFoundError, json.JSONDecodeError):
            settings = {}
        settings.setdefault("mcpServers", {})[name] = config.model_dump(exclude_none=True)
        os.makedirs(config_dir, exist_ok=True)
        with open(settings_path, "w") as fp:
            json.dump(settings, fp, indent=2)


def remove_mcp_server(
    name: str,
    *,
    scope: str = "project",
    cwd: str | None = None,
) -> bool:
    """Remove an MCP server from config. Returns ``True`` if found."""
    if scope == "project":
        mcp_json = read_mcp_json(cwd)
        if name in mcp_json.mcpServers:
            del mcp_json.mcpServers[name]
            write_mcp_json(mcp_json, cwd)
            return True
    elif scope == "user":
        config_dir = os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(os.path.expanduser("~"), ".claude"),
        )
        settings_path = os.path.join(config_dir, "settings.json")
        try:
            with open(settings_path, "r") as fp:
                settings = json.load(fp)
            if name in settings.get("mcpServers", {}):
                del settings["mcpServers"][name]
                with open(settings_path, "w") as fp:
                    json.dump(settings, fp, indent=2)
                return True
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return False
