"""
MCP client — server lifecycle, transport negotiation, tool discovery.

Mirrors src/services/mcp/client.ts — manages connections to MCP servers,
wraps discovered tools as MCPTool instances, handles OAuth auth flows,
and exposes resource listing/reading.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from .auth import (
    ClaudeAuthProvider,
    OAuthTokenSet,
    get_mcp_token_store,
    get_server_key,
)
from .config import (
    get_all_mcp_configs,
    is_mcp_server_disabled,
)
from .normalization import build_mcp_tool_name, normalize_name_for_mcp
from .types import (
    ConnectedMCPServer,
    DisabledMCPServer,
    FailedMCPServer,
    MCPCliState,
    MCPServerConnection,
    McpHTTPServerConfig,
    McpSSEServerConfig,
    McpStdioServerConfig,
    McpWebSocketServerConfig,
    McpSdkServerConfig,
    NeedsAuthMCPServer,
    PendingMCPServer,
    ScopedMcpServerConfig,
    SerializedClient,
    SerializedTool,
    ServerCapabilities,
    ServerInfo,
    ServerResource,
)

logger = logging.getLogger(__name__)

# How long to wait for a server to produce its initialization response
CONNECT_TIMEOUT_S = 30.0

# Max concurrent server connection attempts
MAX_CONCURRENT_CONNECTS = 8

# Reconnection back-off
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BASE_DELAY_S = 1.0


# ---------------------------------------------------------------------------
# Stdio transport (child process)
# ---------------------------------------------------------------------------

class StdioTransport:
    """Spawn a child process and communicate via JSON-RPC over stdin/stdout."""

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._args = args
        merged_env = {**os.environ, **(env or {})}
        self._env = merged_env
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    async def start(self) -> None:
        self._process = subprocess.Popen(
            [self._command, *self._args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env,
        )

    async def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Transport not started")

        self._request_id += 1
        msg = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            msg["params"] = params

        payload = json.dumps(msg).encode() + b"\n"
        self._process.stdin.write(payload)
        self._process.stdin.flush()

        # Read response line
        line = await asyncio.get_event_loop().run_in_executor(
            None, self._process.stdout.readline
        )
        if not line:
            raise ConnectionError("Server closed stdout")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result")

    async def close(self) -> None:
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None


# ---------------------------------------------------------------------------
# HTTP/SSE transport
# ---------------------------------------------------------------------------

class HTTPTransport:
    """Communicate with an MCP server over streamable HTTP."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        auth_provider: ClaudeAuthProvider | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._headers = headers or {}
        self._auth_provider = auth_provider
        self._session_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=CONNECT_TIMEOUT_S)

    async def _auth_headers(self) -> dict[str, str]:
        hdrs = dict(self._headers)
        if self._auth_provider:
            token = await self._auth_provider.ensure_valid_token()
            if token:
                hdrs["Authorization"] = f"Bearer {token}"
        return hdrs

    async def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise RuntimeError("Transport not started")

        body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            body["params"] = params

        hdrs = await self._auth_headers()
        hdrs["Content-Type"] = "application/json"
        hdrs["Accept"] = "application/json"

        resp = await self._client.post(self._url, json=body, headers=hdrs)
        if resp.status_code == 401 and self._auth_provider:
            # Try refresh
            refreshed = await self._auth_provider.refresh()
            if refreshed and refreshed.access_token:
                hdrs["Authorization"] = f"Bearer {refreshed.access_token}"
                resp = await self._client.post(self._url, json=body, headers=hdrs)

        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# WebSocket transport
# ---------------------------------------------------------------------------

class WebSocketTransport:
    """Communicate with an MCP server over WebSocket."""

    def __init__(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}
        self._ws: Any = None
        self._request_id = 0

    async def start(self) -> None:
        try:
            import websockets
            extra_headers = [(k, v) for k, v in self._headers.items()]
            self._ws = await websockets.connect(
                self._url, extra_headers=extra_headers
            )
        except ImportError:
            raise RuntimeError("websockets package required for WS transport")

    async def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._ws is None:
            raise RuntimeError("Transport not started")

        self._request_id += 1
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            msg["params"] = params

        await self._ws.send(json.dumps(msg))
        raw = await self._ws.recv()
        resp = json.loads(raw)
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result")

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None


# ---------------------------------------------------------------------------
# MCPTool wrapper
# ---------------------------------------------------------------------------

@dataclass
class MCPTool:
    """Wraps a single tool from an MCP server for the agent's tool registry."""

    name: str
    qualified_name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str
    _transport: Any = field(repr=False)

    async def call(self, arguments: dict[str, Any]) -> Any:
        """Invoke the tool on the MCP server."""
        result = await self._transport.send(
            "tools/call",
            {"name": self.name, "arguments": arguments},
        )
        return result


# ---------------------------------------------------------------------------
# MCPClient — manages one connection
# ---------------------------------------------------------------------------

class MCPClient:
    """Manages the lifecycle of a single MCP server connection.

    Handles:
    - Transport creation (stdio, SSE, HTTP, WebSocket)
    - Server initialization handshake
    - Tool discovery and wrapping
    - Resource listing / reading
    - OAuth authentication
    - Reconnection with exponential back-off
    """

    def __init__(
        self,
        name: str,
        config: ScopedMcpServerConfig,
        *,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self.config = config
        self._transport: StdioTransport | HTTPTransport | WebSocketTransport | None = None
        self._auth_provider: ClaudeAuthProvider | None = None
        self._capabilities: ServerCapabilities = ServerCapabilities()
        self._server_info: ServerInfo | None = None
        self._tools: list[MCPTool] = []
        self._resources: list[ServerResource] = []
        self._instructions: str | None = None
        self._connected = False
        self._on_reconnect = on_reconnect
        self._reconnect_attempt = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    @property
    def resources(self) -> list[ServerResource]:
        return list(self._resources)

    # -- transport creation --------------------------------------------------

    def _create_transport(self) -> StdioTransport | HTTPTransport | WebSocketTransport:
        cfg = self.config.config
        cfg_type = getattr(cfg, "type", None) or "stdio"

        if cfg_type in (None, "stdio") and isinstance(cfg, McpStdioServerConfig):
            return StdioTransport(cfg.command, cfg.args, cfg.env)

        if cfg_type in ("sse", "http") and isinstance(cfg, (McpSSEServerConfig, McpHTTPServerConfig)):
            if cfg.oauth:
                self._auth_provider = ClaudeAuthProvider(self.name, cfg)
            return HTTPTransport(
                cfg.url,
                cfg.headers,
                self._auth_provider,
            )

        if cfg_type == "ws" and isinstance(cfg, McpWebSocketServerConfig):
            return WebSocketTransport(cfg.url, cfg.headers)

        raise ValueError(f"Unsupported transport type: {cfg_type}")

    # -- connect / disconnect ------------------------------------------------

    async def connect(self) -> MCPServerConnection:
        """Connect to the MCP server, discover capabilities, tools, and resources."""
        if is_mcp_server_disabled(self.name):
            return DisabledMCPServer(name=self.name, config=self.config)

        # Check if auth is needed but we have no token
        cfg = self.config.config
        if isinstance(cfg, (McpSSEServerConfig, McpHTTPServerConfig)) and cfg.oauth:
            store = get_mcp_token_store()
            server_key = get_server_key(self.name, cfg)
            if store.has_discovery_but_no_token(server_key):
                return NeedsAuthMCPServer(name=self.name, config=self.config)

        try:
            self._transport = self._create_transport()
            await asyncio.wait_for(
                self._transport.start(), timeout=CONNECT_TIMEOUT_S
            )

            # Initialize handshake
            init_result = await self._transport.send("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "claude-code-python", "version": "0.1.0"},
            })

            if init_result:
                caps = init_result.get("capabilities", {})
                self._capabilities = ServerCapabilities(**{
                    k: v for k, v in caps.items()
                    if k in ServerCapabilities.model_fields
                })
                si = init_result.get("serverInfo")
                if si:
                    self._server_info = ServerInfo(**si)
                self._instructions = init_result.get("instructions")

            # Notify server initialization is complete
            await self._transport.send("notifications/initialized")

            # Discover tools
            await self._discover_tools()

            # Discover resources
            await self._discover_resources()

            self._connected = True
            self._reconnect_attempt = 0

            return ConnectedMCPServer(
                name=self.name,
                config=self.config,
                capabilities=self._capabilities,
                server_info=self._server_info,
                instructions=self._instructions,
            )
        except TimeoutError:
            logger.warning("Timeout connecting to MCP server %s", self.name)
            return FailedMCPServer(
                name=self.name, config=self.config, error="Connection timeout"
            )
        except Exception as exc:
            logger.warning("Failed to connect to MCP server %s: %s", self.name, exc)
            return FailedMCPServer(
                name=self.name, config=self.config, error=str(exc)
            )

    async def disconnect(self) -> None:
        """Cleanly shut down the connection."""
        self._connected = False
        if self._transport:
            try:
                await self._transport.close()
            except Exception:
                pass
            self._transport = None

    async def reconnect(self) -> MCPServerConnection:
        """Reconnect with exponential back-off."""
        self._reconnect_attempt += 1
        if self._reconnect_attempt > MAX_RECONNECT_ATTEMPTS:
            return FailedMCPServer(
                name=self.name,
                config=self.config,
                error=f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) exceeded",
            )

        delay = RECONNECT_BASE_DELAY_S * (2 ** (self._reconnect_attempt - 1))
        logger.info(
            "Reconnecting to %s (attempt %d/%d) in %.1fs",
            self.name, self._reconnect_attempt, MAX_RECONNECT_ATTEMPTS, delay,
        )
        await asyncio.sleep(delay)
        await self.disconnect()
        result = await self.connect()
        if isinstance(result, ConnectedMCPServer) and self._on_reconnect:
            self._on_reconnect()
        return result

    # -- tool discovery ------------------------------------------------------

    async def _discover_tools(self) -> None:
        """Query the server's tool list and wrap as MCPTool."""
        if not self._transport:
            return
        try:
            result = await self._transport.send("tools/list")
            tools_list = result.get("tools", []) if result else []
            self._tools = []
            for t in tools_list:
                tool = MCPTool(
                    name=t["name"],
                    qualified_name=build_mcp_tool_name(self.name, t["name"]),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {"type": "object"}),
                    server_name=self.name,
                    _transport=self._transport,
                )
                self._tools.append(tool)
        except Exception as exc:
            logger.warning("Failed to discover tools for %s: %s", self.name, exc)

    # -- resource discovery --------------------------------------------------

    async def _discover_resources(self) -> None:
        """Query the server's resource list."""
        if not self._transport:
            return
        if not (self._capabilities.resources):
            return
        try:
            result = await self._transport.send("resources/list")
            resources = result.get("resources", []) if result else []
            self._resources = [
                ServerResource(
                    uri=r["uri"],
                    name=r.get("name", r["uri"]),
                    description=r.get("description"),
                    mime_type=r.get("mimeType"),
                    server=self.name,
                )
                for r in resources
            ]
        except Exception as exc:
            logger.debug("Failed to list resources for %s: %s", self.name, exc)

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI from this server."""
        if not self._transport:
            raise RuntimeError(f"Not connected to {self.name}")
        result = await self._transport.send("resources/read", {"uri": uri})
        return result or {}

    # -- tool invocation -----------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by its (local, non-qualified) name."""
        if not self._transport:
            raise RuntimeError(f"Not connected to {self.name}")
        result = await self._transport.send(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )
        return result

    # -- serialization -------------------------------------------------------

    def to_serialized_client(self) -> SerializedClient:
        status = "connected" if self._connected else "failed"
        return SerializedClient(
            name=self.name,
            type=status,
            capabilities=self._capabilities if self._connected else None,
        )

    def get_serialized_tools(self) -> list[SerializedTool]:
        return [
            SerializedTool(
                name=t.qualified_name,
                description=t.description,
                input_json_schema=t.input_schema,
                is_mcp=True,
                original_tool_name=t.name,
            )
            for t in self._tools
        ]


# ---------------------------------------------------------------------------
# MCPClientManager — manages all connections
# ---------------------------------------------------------------------------

class MCPClientManager:
    """Manages all MCP server connections for a session.

    Provides batch connect/disconnect, tool aggregation, and resource access.
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._connections: dict[str, MCPServerConnection] = {}

    @property
    def clients(self) -> dict[str, MCPClient]:
        return dict(self._clients)

    @property
    def connections(self) -> dict[str, MCPServerConnection]:
        return dict(self._connections)

    @property
    def connected_names(self) -> list[str]:
        return [n for n, c in self._clients.items() if c.is_connected]

    async def connect_all(
        self,
        configs: dict[str, ScopedMcpServerConfig] | None = None,
        cwd: str | None = None,
    ) -> dict[str, MCPServerConnection]:
        """Connect to all configured MCP servers.

        If *configs* is ``None``, loads from all standard sources via
        ``get_all_mcp_configs()``.
        """
        if configs is None:
            configs = get_all_mcp_configs(cwd)

        sem = asyncio.Semaphore(MAX_CONCURRENT_CONNECTS)

        async def _connect_one(name: str, scfg: ScopedMcpServerConfig) -> None:
            async with sem:
                client = MCPClient(name, scfg)
                self._clients[name] = client
                conn = await client.connect()
                self._connections[name] = conn

        tasks = [_connect_one(n, c) for n, c in configs.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

        return dict(self._connections)

    async def disconnect_all(self) -> None:
        """Disconnect all servers."""
        tasks = [c.disconnect() for c in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()
        self._connections.clear()

    async def reconnect(self, name: str) -> MCPServerConnection:
        """Reconnect a specific server."""
        client = self._clients.get(name)
        if client is None:
            raise KeyError(f"Unknown MCP server: {name}")
        conn = await client.reconnect()
        self._connections[name] = conn
        return conn

    # -- aggregated tools / resources ----------------------------------------

    def get_all_tools(self) -> list[MCPTool]:
        """All tools across all connected servers."""
        tools: list[MCPTool] = []
        for client in self._clients.values():
            if client.is_connected:
                tools.extend(client.tools)
        return tools

    def get_all_resources(self) -> dict[str, list[ServerResource]]:
        """All resources grouped by server name."""
        result: dict[str, list[ServerResource]] = {}
        for client in self._clients.values():
            if client.is_connected and client.resources:
                result[client.name] = client.resources
        return result

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool by its fully-qualified name (``mcp__server__tool``)."""
        from .normalization import parse_mcp_tool_name
        parsed = parse_mcp_tool_name(qualified_name)
        if parsed is None:
            raise ValueError(f"Invalid MCP tool name: {qualified_name}")
        server_norm, tool_name = parsed

        for client in self._clients.values():
            if normalize_name_for_mcp(client.name) == server_norm and client.is_connected:
                return await client.call_tool(tool_name, arguments)
        raise KeyError(f"No connected server for tool: {qualified_name}")

    async def read_resource(self, server_name: str, uri: str) -> dict[str, Any]:
        """Read a resource from a specific server."""
        client = self._clients.get(server_name)
        if client is None or not client.is_connected:
            raise KeyError(f"Server not connected: {server_name}")
        return await client.read_resource(uri)

    # -- CLI state -----------------------------------------------------------

    def get_cli_state(self) -> MCPCliState:
        """Serialize entire MCP state for CLI/SDK handoff."""
        clients_list = [c.to_serialized_client() for c in self._clients.values()]
        tools_list: list[SerializedTool] = []
        for c in self._clients.values():
            tools_list.extend(c.get_serialized_tools())

        configs = {n: c.config for n, c in self._clients.items()}
        resources = self.get_all_resources()

        normalized_names: dict[str, str] = {}
        for c in self._clients.values():
            norm = normalize_name_for_mcp(c.name)
            if norm != c.name:
                normalized_names[norm] = c.name

        return MCPCliState(
            clients=clients_list,
            configs=configs,
            tools=tools_list,
            resources=resources,
            normalized_names=normalized_names or None,
        )
