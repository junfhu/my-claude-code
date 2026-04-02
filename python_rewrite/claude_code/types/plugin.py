"""
Plugin type definitions for the Claude Code plugin system.

Covers plugin manifests, configuration, loaded plugin metadata,
plugin errors (discriminated union), and helper utilities.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

__all__ = [
    # Config
    "PluginRepository",
    "PluginConfig",
    # Manifest / metadata
    "PluginAuthor",
    "CommandMetadata",
    "PluginManifest",
    "LoadedPlugin",
    "BuiltinPluginDefinition",
    # Components
    "PluginComponent",
    # Errors
    "PluginErrorPathNotFound",
    "PluginErrorGitAuthFailed",
    "PluginErrorGitTimeout",
    "PluginErrorNetworkError",
    "PluginErrorManifestParseError",
    "PluginErrorManifestValidationError",
    "PluginErrorPluginNotFound",
    "PluginErrorMarketplaceNotFound",
    "PluginErrorMarketplaceLoadFailed",
    "PluginErrorMcpConfigInvalid",
    "PluginErrorMcpServerSuppressedDuplicate",
    "PluginErrorLspConfigInvalid",
    "PluginErrorHookLoadFailed",
    "PluginErrorComponentLoadFailed",
    "PluginErrorMcpbDownloadFailed",
    "PluginErrorMcpbExtractFailed",
    "PluginErrorMcpbInvalidManifest",
    "PluginErrorLspServerStartFailed",
    "PluginErrorLspServerCrashed",
    "PluginErrorLspRequestTimeout",
    "PluginErrorLspRequestFailed",
    "PluginErrorMarketplaceBlockedByPolicy",
    "PluginErrorDependencyUnsatisfied",
    "PluginErrorPluginCacheMiss",
    "PluginErrorGeneric",
    "PluginError",
    "PluginLoadResult",
    "get_plugin_error_message",
]

# ============================================================================
# Plugin configuration
# ============================================================================


class PluginRepository(BaseModel):
    """A registered plugin repository."""

    url: str
    branch: str
    last_updated: str | None = Field(default=None, alias="lastUpdated")
    commit_sha: str | None = Field(default=None, alias="commitSha")

    model_config = {"populate_by_name": True}


class PluginConfig(BaseModel):
    """Top-level plugin configuration."""

    repositories: dict[str, PluginRepository]


# ============================================================================
# Plugin manifest & metadata
# ============================================================================


class PluginAuthor(BaseModel):
    """Plugin author metadata."""

    name: str
    url: str | None = None


class CommandMetadata(BaseModel):
    """Metadata for a named command within a plugin manifest."""

    description: str | None = None
    when_to_use: str | None = Field(default=None, alias="whenToUse")

    model_config = {"extra": "allow", "populate_by_name": True}


class PluginManifest(BaseModel):
    """Schema for a plugin's manifest file (``plugin.json``)."""

    name: str
    version: str | None = None
    description: str | None = None
    author: PluginAuthor | None = None
    commands: str | list[str] | dict[str, CommandMetadata] | None = None
    agents: str | list[str] | None = None
    skills: str | list[str] | None = None
    hooks: dict[str, Any] | None = None
    mcp_servers: dict[str, Any] | None = Field(default=None, alias="mcpServers")
    lsp_servers: dict[str, Any] | None = Field(default=None, alias="lspServers")
    output_styles: str | list[str] | None = Field(default=None, alias="outputStyles")
    settings: dict[str, Any] | None = None
    dependencies: list[str] | None = None

    model_config = {"extra": "allow", "populate_by_name": True}


class BuiltinPluginDefinition(BaseModel):
    """Definition for a built-in plugin that ships with the CLI."""

    name: str
    """Plugin name (used in ``{name}@builtin`` identifier)."""
    description: str
    version: str | None = None
    skills: list[dict[str, Any]] | None = None
    hooks: dict[str, Any] | None = None
    mcp_servers: dict[str, Any] | None = Field(default=None, alias="mcpServers")
    default_enabled: bool | None = Field(default=None, alias="defaultEnabled")

    model_config = {"populate_by_name": True}


class LoadedPlugin(BaseModel):
    """A fully resolved plugin ready for use."""

    name: str
    manifest: PluginManifest
    path: str
    source: str
    repository: str
    """Repository identifier, usually same as source."""
    enabled: bool | None = None
    is_builtin: bool | None = Field(default=None, alias="isBuiltin")
    sha: str | None = None
    """Git commit SHA for version pinning."""
    commands_path: str | None = Field(default=None, alias="commandsPath")
    commands_paths: list[str] | None = Field(default=None, alias="commandsPaths")
    commands_metadata: dict[str, CommandMetadata] | None = Field(
        default=None, alias="commandsMetadata"
    )
    agents_path: str | None = Field(default=None, alias="agentsPath")
    agents_paths: list[str] | None = Field(default=None, alias="agentsPaths")
    skills_path: str | None = Field(default=None, alias="skillsPath")
    skills_paths: list[str] | None = Field(default=None, alias="skillsPaths")
    output_styles_path: str | None = Field(default=None, alias="outputStylesPath")
    output_styles_paths: list[str] | None = Field(
        default=None, alias="outputStylesPaths"
    )
    hooks_config: dict[str, Any] | None = Field(default=None, alias="hooksConfig")
    mcp_servers: dict[str, Any] | None = Field(default=None, alias="mcpServers")
    lsp_servers: dict[str, Any] | None = Field(default=None, alias="lspServers")
    settings: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


# ============================================================================
# Plugin components
# ============================================================================

PluginComponent = Literal[
    "commands",
    "agents",
    "skills",
    "hooks",
    "output-styles",
]

# ============================================================================
# Plugin errors (discriminated union)
# ============================================================================


class PluginErrorPathNotFound(BaseModel):
    """Plugin error: path not found."""

    type: Literal["path-not-found"] = "path-not-found"
    source: str
    plugin: str | None = None
    path: str
    component: PluginComponent


class PluginErrorGitAuthFailed(BaseModel):
    """Plugin error: git authentication failed."""

    type: Literal["git-auth-failed"] = "git-auth-failed"
    source: str
    plugin: str | None = None
    git_url: str = Field(alias="gitUrl")
    auth_type: Literal["ssh", "https"] = Field(alias="authType")

    model_config = {"populate_by_name": True}


class PluginErrorGitTimeout(BaseModel):
    """Plugin error: git operation timeout."""

    type: Literal["git-timeout"] = "git-timeout"
    source: str
    plugin: str | None = None
    git_url: str = Field(alias="gitUrl")
    operation: Literal["clone", "pull"]

    model_config = {"populate_by_name": True}


class PluginErrorNetworkError(BaseModel):
    """Plugin error: network connectivity failure."""

    type: Literal["network-error"] = "network-error"
    source: str
    plugin: str | None = None
    url: str
    details: str | None = None


class PluginErrorManifestParseError(BaseModel):
    """Plugin error: manifest parsing failure."""

    type: Literal["manifest-parse-error"] = "manifest-parse-error"
    source: str
    plugin: str | None = None
    manifest_path: str = Field(alias="manifestPath")
    parse_error: str = Field(alias="parseError")

    model_config = {"populate_by_name": True}


class PluginErrorManifestValidationError(BaseModel):
    """Plugin error: manifest validation failure."""

    type: Literal["manifest-validation-error"] = "manifest-validation-error"
    source: str
    plugin: str | None = None
    manifest_path: str = Field(alias="manifestPath")
    validation_errors: list[str] = Field(alias="validationErrors")

    model_config = {"populate_by_name": True}


class PluginErrorPluginNotFound(BaseModel):
    """Plugin error: plugin not found in marketplace."""

    type: Literal["plugin-not-found"] = "plugin-not-found"
    source: str
    plugin_id: str = Field(alias="pluginId")
    marketplace: str

    model_config = {"populate_by_name": True}


class PluginErrorMarketplaceNotFound(BaseModel):
    """Plugin error: marketplace not found."""

    type: Literal["marketplace-not-found"] = "marketplace-not-found"
    source: str
    marketplace: str
    available_marketplaces: list[str] = Field(alias="availableMarketplaces")

    model_config = {"populate_by_name": True}


class PluginErrorMarketplaceLoadFailed(BaseModel):
    """Plugin error: marketplace load failure."""

    type: Literal["marketplace-load-failed"] = "marketplace-load-failed"
    source: str
    marketplace: str
    reason: str


class PluginErrorMcpConfigInvalid(BaseModel):
    """Plugin error: MCP server config invalid."""

    type: Literal["mcp-config-invalid"] = "mcp-config-invalid"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    validation_error: str = Field(alias="validationError")

    model_config = {"populate_by_name": True}


class PluginErrorMcpServerSuppressedDuplicate(BaseModel):
    """Plugin error: MCP server suppressed as duplicate."""

    type: Literal["mcp-server-suppressed-duplicate"] = "mcp-server-suppressed-duplicate"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    duplicate_of: str = Field(alias="duplicateOf")

    model_config = {"populate_by_name": True}


class PluginErrorLspConfigInvalid(BaseModel):
    """Plugin error: LSP server config invalid."""

    type: Literal["lsp-config-invalid"] = "lsp-config-invalid"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    validation_error: str = Field(alias="validationError")

    model_config = {"populate_by_name": True}


class PluginErrorHookLoadFailed(BaseModel):
    """Plugin error: hook load failure."""

    type: Literal["hook-load-failed"] = "hook-load-failed"
    source: str
    plugin: str
    hook_path: str = Field(alias="hookPath")
    reason: str

    model_config = {"populate_by_name": True}


class PluginErrorComponentLoadFailed(BaseModel):
    """Plugin error: component load failure."""

    type: Literal["component-load-failed"] = "component-load-failed"
    source: str
    plugin: str
    component: PluginComponent
    path: str
    reason: str


class PluginErrorMcpbDownloadFailed(BaseModel):
    """Plugin error: MCPB download failure."""

    type: Literal["mcpb-download-failed"] = "mcpb-download-failed"
    source: str
    plugin: str
    url: str
    reason: str


class PluginErrorMcpbExtractFailed(BaseModel):
    """Plugin error: MCPB extraction failure."""

    type: Literal["mcpb-extract-failed"] = "mcpb-extract-failed"
    source: str
    plugin: str
    mcpb_path: str = Field(alias="mcpbPath")
    reason: str

    model_config = {"populate_by_name": True}


class PluginErrorMcpbInvalidManifest(BaseModel):
    """Plugin error: MCPB invalid manifest."""

    type: Literal["mcpb-invalid-manifest"] = "mcpb-invalid-manifest"
    source: str
    plugin: str
    mcpb_path: str = Field(alias="mcpbPath")
    validation_error: str = Field(alias="validationError")

    model_config = {"populate_by_name": True}


class PluginErrorLspServerStartFailed(BaseModel):
    """Plugin error: LSP server start failure."""

    type: Literal["lsp-server-start-failed"] = "lsp-server-start-failed"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    reason: str

    model_config = {"populate_by_name": True}


class PluginErrorLspServerCrashed(BaseModel):
    """Plugin error: LSP server crashed."""

    type: Literal["lsp-server-crashed"] = "lsp-server-crashed"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    exit_code: int | None = Field(alias="exitCode")
    signal: str | None = None

    model_config = {"populate_by_name": True}


class PluginErrorLspRequestTimeout(BaseModel):
    """Plugin error: LSP request timeout."""

    type: Literal["lsp-request-timeout"] = "lsp-request-timeout"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    method: str
    timeout_ms: int = Field(alias="timeoutMs")

    model_config = {"populate_by_name": True}


class PluginErrorLspRequestFailed(BaseModel):
    """Plugin error: LSP request failure."""

    type: Literal["lsp-request-failed"] = "lsp-request-failed"
    source: str
    plugin: str
    server_name: str = Field(alias="serverName")
    method: str
    error: str

    model_config = {"populate_by_name": True}


class PluginErrorMarketplaceBlockedByPolicy(BaseModel):
    """Plugin error: marketplace blocked by enterprise policy."""

    type: Literal["marketplace-blocked-by-policy"] = "marketplace-blocked-by-policy"
    source: str
    plugin: str | None = None
    marketplace: str
    blocked_by_blocklist: bool | None = Field(default=None, alias="blockedByBlocklist")
    allowed_sources: list[str] = Field(alias="allowedSources")

    model_config = {"populate_by_name": True}


class PluginErrorDependencyUnsatisfied(BaseModel):
    """Plugin error: unsatisfied dependency."""

    type: Literal["dependency-unsatisfied"] = "dependency-unsatisfied"
    source: str
    plugin: str
    dependency: str
    reason: Literal["not-enabled", "not-found"]


class PluginErrorPluginCacheMiss(BaseModel):
    """Plugin error: plugin not in cache."""

    type: Literal["plugin-cache-miss"] = "plugin-cache-miss"
    source: str
    plugin: str
    install_path: str = Field(alias="installPath")

    model_config = {"populate_by_name": True}


class PluginErrorGeneric(BaseModel):
    """Generic / untyped plugin error."""

    type: Literal["generic-error"] = "generic-error"
    source: str
    plugin: str | None = None
    error: str


PluginError = Union[
    PluginErrorPathNotFound,
    PluginErrorGitAuthFailed,
    PluginErrorGitTimeout,
    PluginErrorNetworkError,
    PluginErrorManifestParseError,
    PluginErrorManifestValidationError,
    PluginErrorPluginNotFound,
    PluginErrorMarketplaceNotFound,
    PluginErrorMarketplaceLoadFailed,
    PluginErrorMcpConfigInvalid,
    PluginErrorMcpServerSuppressedDuplicate,
    PluginErrorLspConfigInvalid,
    PluginErrorHookLoadFailed,
    PluginErrorComponentLoadFailed,
    PluginErrorMcpbDownloadFailed,
    PluginErrorMcpbExtractFailed,
    PluginErrorMcpbInvalidManifest,
    PluginErrorLspServerStartFailed,
    PluginErrorLspServerCrashed,
    PluginErrorLspRequestTimeout,
    PluginErrorLspRequestFailed,
    PluginErrorMarketplaceBlockedByPolicy,
    PluginErrorDependencyUnsatisfied,
    PluginErrorPluginCacheMiss,
    PluginErrorGeneric,
]
"""Discriminated union of all plugin error types."""

# ============================================================================
# Plugin load result
# ============================================================================


class PluginLoadResult(BaseModel):
    """Result of loading plugins."""

    enabled: list[LoadedPlugin]
    disabled: list[LoadedPlugin]
    errors: list[PluginError]  # type: ignore[valid-type]


# ============================================================================
# Helper
# ============================================================================


def get_plugin_error_message(error: PluginError) -> str:  # type: ignore[arg-type]
    """Return a human-readable message for any :class:`PluginError`."""
    _t = error.type
    if _t == "generic-error":
        assert isinstance(error, PluginErrorGeneric)
        return error.error
    elif _t == "path-not-found":
        assert isinstance(error, PluginErrorPathNotFound)
        return f"Path not found: {error.path} ({error.component})"
    elif _t == "git-auth-failed":
        assert isinstance(error, PluginErrorGitAuthFailed)
        return f"Git authentication failed ({error.auth_type}): {error.git_url}"
    elif _t == "git-timeout":
        assert isinstance(error, PluginErrorGitTimeout)
        return f"Git {error.operation} timeout: {error.git_url}"
    elif _t == "network-error":
        assert isinstance(error, PluginErrorNetworkError)
        details = f" - {error.details}" if error.details else ""
        return f"Network error: {error.url}{details}"
    elif _t == "manifest-parse-error":
        assert isinstance(error, PluginErrorManifestParseError)
        return f"Manifest parse error: {error.parse_error}"
    elif _t == "manifest-validation-error":
        assert isinstance(error, PluginErrorManifestValidationError)
        return f"Manifest validation failed: {', '.join(error.validation_errors)}"
    elif _t == "plugin-not-found":
        assert isinstance(error, PluginErrorPluginNotFound)
        return f"Plugin {error.plugin_id} not found in marketplace {error.marketplace}"
    elif _t == "marketplace-not-found":
        assert isinstance(error, PluginErrorMarketplaceNotFound)
        return f"Marketplace {error.marketplace} not found"
    elif _t == "marketplace-load-failed":
        assert isinstance(error, PluginErrorMarketplaceLoadFailed)
        return f"Marketplace {error.marketplace} failed to load: {error.reason}"
    elif _t == "mcp-config-invalid":
        assert isinstance(error, PluginErrorMcpConfigInvalid)
        return f"MCP server {error.server_name} invalid: {error.validation_error}"
    elif _t == "mcp-server-suppressed-duplicate":
        assert isinstance(error, PluginErrorMcpServerSuppressedDuplicate)
        if error.duplicate_of.startswith("plugin:"):
            parts = error.duplicate_of.split(":")
            dup = f'server provided by plugin "{parts[1] if len(parts) > 1 else "?"}"'
        else:
            dup = f'already-configured "{error.duplicate_of}"'
        return f'MCP server "{error.server_name}" skipped — same command/URL as {dup}'
    elif _t == "hook-load-failed":
        assert isinstance(error, PluginErrorHookLoadFailed)
        return f"Hook load failed: {error.reason}"
    elif _t == "component-load-failed":
        assert isinstance(error, PluginErrorComponentLoadFailed)
        return f"{error.component} load failed from {error.path}: {error.reason}"
    elif _t == "mcpb-download-failed":
        assert isinstance(error, PluginErrorMcpbDownloadFailed)
        return f"Failed to download MCPB from {error.url}: {error.reason}"
    elif _t == "mcpb-extract-failed":
        assert isinstance(error, PluginErrorMcpbExtractFailed)
        return f"Failed to extract MCPB {error.mcpb_path}: {error.reason}"
    elif _t == "mcpb-invalid-manifest":
        assert isinstance(error, PluginErrorMcpbInvalidManifest)
        return f"MCPB manifest invalid at {error.mcpb_path}: {error.validation_error}"
    elif _t == "lsp-config-invalid":
        assert isinstance(error, PluginErrorLspConfigInvalid)
        return f'Plugin "{error.plugin}" has invalid LSP server config for "{error.server_name}": {error.validation_error}'
    elif _t == "lsp-server-start-failed":
        assert isinstance(error, PluginErrorLspServerStartFailed)
        return f'Plugin "{error.plugin}" failed to start LSP server "{error.server_name}": {error.reason}'
    elif _t == "lsp-server-crashed":
        assert isinstance(error, PluginErrorLspServerCrashed)
        if error.signal:
            return f'Plugin "{error.plugin}" LSP server "{error.server_name}" crashed with signal {error.signal}'
        return f'Plugin "{error.plugin}" LSP server "{error.server_name}" crashed with exit code {error.exit_code or "unknown"}'
    elif _t == "lsp-request-timeout":
        assert isinstance(error, PluginErrorLspRequestTimeout)
        return f'Plugin "{error.plugin}" LSP server "{error.server_name}" timed out on {error.method} request after {error.timeout_ms}ms'
    elif _t == "lsp-request-failed":
        assert isinstance(error, PluginErrorLspRequestFailed)
        return f'Plugin "{error.plugin}" LSP server "{error.server_name}" {error.method} request failed: {error.error}'
    elif _t == "marketplace-blocked-by-policy":
        assert isinstance(error, PluginErrorMarketplaceBlockedByPolicy)
        if error.blocked_by_blocklist:
            return f"Marketplace '{error.marketplace}' is blocked by enterprise policy"
        return f"Marketplace '{error.marketplace}' is not in the allowed marketplace list"
    elif _t == "dependency-unsatisfied":
        assert isinstance(error, PluginErrorDependencyUnsatisfied)
        hint = (
            "disabled — enable it or remove the dependency"
            if error.reason == "not-enabled"
            else "not found in any configured marketplace"
        )
        return f'Dependency "{error.dependency}" is {hint}'
    elif _t == "plugin-cache-miss":
        assert isinstance(error, PluginErrorPluginCacheMiss)
        return f'Plugin "{error.plugin}" not cached at {error.install_path} — run /plugins to refresh'
    else:
        return f"Unknown plugin error: {error.type}"
