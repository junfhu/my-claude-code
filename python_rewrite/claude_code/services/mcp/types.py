"""
MCP type definitions.

Mirrors src/services/mcp/types.ts — all configuration schemas, server connection
types, resource types, and CLI serialization shapes for the MCP subsystem.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration scopes & transport enums
# ---------------------------------------------------------------------------

class ConfigScope(str, Enum):
    """Where an MCP server config was loaded from."""
    LOCAL = "local"
    USER = "user"
    PROJECT = "project"
    DYNAMIC = "dynamic"
    ENTERPRISE = "enterprise"
    CLAUDEAI = "claudeai"
    MANAGED = "managed"


class MCPTransportType(str, Enum):
    """Wire transport for talking to an MCP server."""
    STDIO = "stdio"
    SSE = "sse"
    SSE_IDE = "sse-ide"
    HTTP = "http"
    WS = "ws"
    SDK = "sdk"


# ---------------------------------------------------------------------------
# Server config models (discriminated union by `type`)
# ---------------------------------------------------------------------------

class McpOAuthConfig(BaseModel):
    """OAuth settings attached to SSE/HTTP MCP servers."""
    client_id: Optional[str] = None
    callback_port: Optional[int] = None
    auth_server_metadata_url: Optional[str] = None
    xaa: Optional[bool] = None


class McpStdioServerConfig(BaseModel):
    """Stdio-transport MCP server."""
    type: Optional[Literal["stdio"]] = None  # optional for backwards compat
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=list)
    env: Optional[dict[str, str]] = None


class McpSSEServerConfig(BaseModel):
    """SSE-transport MCP server."""
    type: Literal["sse"] = "sse"
    url: str
    headers: Optional[dict[str, str]] = None
    headers_helper: Optional[str] = None
    oauth: Optional[McpOAuthConfig] = None


class McpSSEIDEServerConfig(BaseModel):
    """IDE-extension SSE server (internal)."""
    type: Literal["sse-ide"] = "sse-ide"
    url: str
    ide_name: str
    ide_running_in_windows: Optional[bool] = None


class McpWebSocketIDEServerConfig(BaseModel):
    """IDE-extension WebSocket server (internal)."""
    type: Literal["ws-ide"] = "ws-ide"
    url: str
    ide_name: str
    auth_token: Optional[str] = None
    ide_running_in_windows: Optional[bool] = None


class McpHTTPServerConfig(BaseModel):
    """Streamable-HTTP MCP server."""
    type: Literal["http"] = "http"
    url: str
    headers: Optional[dict[str, str]] = None
    headers_helper: Optional[str] = None
    oauth: Optional[McpOAuthConfig] = None


class McpWebSocketServerConfig(BaseModel):
    """WebSocket MCP server."""
    type: Literal["ws"] = "ws"
    url: str
    headers: Optional[dict[str, str]] = None
    headers_helper: Optional[str] = None


class McpSdkServerConfig(BaseModel):
    """SDK (in-process) MCP server."""
    type: Literal["sdk"] = "sdk"
    name: str


class McpClaudeAIProxyServerConfig(BaseModel):
    """Claude.ai proxy server."""
    type: Literal["claudeai-proxy"] = "claudeai-proxy"
    url: str
    id: str


# Discriminated union of all config types
McpServerConfig = (
    McpStdioServerConfig
    | McpSSEServerConfig
    | McpSSEIDEServerConfig
    | McpWebSocketIDEServerConfig
    | McpHTTPServerConfig
    | McpWebSocketServerConfig
    | McpSdkServerConfig
    | McpClaudeAIProxyServerConfig
)


class ScopedMcpServerConfig(BaseModel):
    """An MCP server config annotated with its config scope and optional plugin source."""
    config: McpServerConfig
    scope: ConfigScope
    plugin_source: Optional[str] = None

    @property
    def type(self) -> Optional[str]:
        return getattr(self.config, "type", None)

    @property
    def url(self) -> Optional[str]:
        return getattr(self.config, "url", None)

    @property
    def command(self) -> Optional[str]:
        return getattr(self.config, "command", None)


class McpJsonConfig(BaseModel):
    """Shape of .mcp.json files."""
    mcpServers: dict[str, McpServerConfig] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Server connection states
# ---------------------------------------------------------------------------

class ServerCapabilities(BaseModel):
    """Capabilities reported by a connected MCP server."""
    tools: Optional[dict[str, Any]] = None
    resources: Optional[dict[str, Any]] = None
    prompts: Optional[dict[str, Any]] = None
    logging: Optional[dict[str, Any]] = None


class ServerInfo(BaseModel):
    """Identity of a connected MCP server."""
    name: str
    version: str


class ConnectedMCPServer(BaseModel):
    """A successfully connected MCP server."""
    name: str
    type: Literal["connected"] = "connected"
    capabilities: ServerCapabilities = Field(default_factory=ServerCapabilities)
    server_info: Optional[ServerInfo] = None
    instructions: Optional[str] = None
    config: ScopedMcpServerConfig
    # client handle stored externally – not serialised
    _client: Any = None
    _cleanup: Any = None


class FailedMCPServer(BaseModel):
    """Server that failed to connect."""
    name: str
    type: Literal["failed"] = "failed"
    config: ScopedMcpServerConfig
    error: Optional[str] = None


class NeedsAuthMCPServer(BaseModel):
    """Server awaiting OAuth authentication."""
    name: str
    type: Literal["needs-auth"] = "needs-auth"
    config: ScopedMcpServerConfig


class PendingMCPServer(BaseModel):
    """Server with connection in progress."""
    name: str
    type: Literal["pending"] = "pending"
    config: ScopedMcpServerConfig
    reconnect_attempt: Optional[int] = None
    max_reconnect_attempts: Optional[int] = None


class DisabledMCPServer(BaseModel):
    """Explicitly disabled server."""
    name: str
    type: Literal["disabled"] = "disabled"
    config: ScopedMcpServerConfig


MCPServerConnection = (
    ConnectedMCPServer
    | FailedMCPServer
    | NeedsAuthMCPServer
    | PendingMCPServer
    | DisabledMCPServer
)


# ---------------------------------------------------------------------------
# Resource types
# ---------------------------------------------------------------------------

class ServerResource(BaseModel):
    """An MCP resource annotated with its originating server name."""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    server: str


# ---------------------------------------------------------------------------
# CLI serialization
# ---------------------------------------------------------------------------

class SerializedTool(BaseModel):
    """Wire-safe representation of an MCP tool."""
    name: str
    description: str
    input_json_schema: Optional[dict[str, Any]] = None
    is_mcp: Optional[bool] = None
    original_tool_name: Optional[str] = None


class SerializedClient(BaseModel):
    """Wire-safe representation of an MCP server connection."""
    name: str
    type: Literal["connected", "failed", "needs-auth", "pending", "disabled"]
    capabilities: Optional[ServerCapabilities] = None


class MCPCliState(BaseModel):
    """Aggregate MCP state for CLI/SDK handoff."""
    clients: list[SerializedClient] = Field(default_factory=list)
    configs: dict[str, ScopedMcpServerConfig] = Field(default_factory=dict)
    tools: list[SerializedTool] = Field(default_factory=list)
    resources: dict[str, list[ServerResource]] = Field(default_factory=dict)
    normalized_names: Optional[dict[str, str]] = None
