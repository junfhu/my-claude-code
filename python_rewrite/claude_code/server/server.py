"""
HTTP/WebSocket server for IDE integration.

Provides a local server that IDEs (VS Code, JetBrains, etc.) can connect
to for real-time communication with Claude Code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_PORT = 7862


class ClaudeCodeServer:
    """Local HTTP/WebSocket server for IDE integration.

    Endpoints:
    - ``GET /health`` — health check
    - ``GET /status`` — session status
    - ``POST /message`` — send a message to the agent
    - ``WS /ws`` — WebSocket for real-time communication
    """

    def __init__(self, port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
        self.port = port
        self.host = host
        self._app: Any = None
        self._server: Any = None
        self._ws_clients: set[Any] = set()
        self._message_handler: Optional[Callable[[dict[str, Any]], Any]] = None

    def on_message(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        """Start the server."""
        try:
            from aiohttp import web
        except ImportError:
            # Fallback to basic HTTP server
            await self._start_basic()
            return

        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/status", self._handle_status)
        self._app.router.add_post("/message", self._handle_message)
        self._app.router.add_get("/ws", self._handle_ws)

        runner = web.AppRunner(self._app)
        await runner.setup()
        self._server = web.TCPSite(runner, self.host, self.port)
        await self._server.start()
        logger.info("Server started on %s:%d", self.host, self.port)

    async def _start_basic(self) -> None:
        """Start a basic asyncio HTTP server without aiohttp."""
        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            data = await reader.read(4096)
            request = data.decode("utf-8", errors="replace")
            first_line = request.split("\n")[0] if request else ""

            if "GET /health" in first_line:
                body = json.dumps({"status": "ok"})
            elif "GET /status" in first_line:
                body = json.dumps({"status": "running", "port": self.port})
            elif "POST /message" in first_line:
                # Extract body after headers
                parts = request.split("\r\n\r\n", 1)
                msg_body = parts[1] if len(parts) > 1 else "{}"
                try:
                    msg = json.loads(msg_body)
                    if self._message_handler:
                        result = await self._message_handler(msg)
                        body = json.dumps(result or {"ok": True})
                    else:
                        body = json.dumps({"error": "no handler"})
                except json.JSONDecodeError:
                    body = json.dumps({"error": "invalid JSON"})
            else:
                body = json.dumps({"error": "not found"})

            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"\r\n{body}"
            )
            writer.write(response.encode())
            await writer.drain()
            writer.close()

        self._server = await asyncio.start_server(
            handle_client, self.host, self.port
        )
        logger.info("Basic server started on %s:%d", self.host, self.port)

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web
        return web.json_response({"status": "ok"})

    async def _handle_status(self, request: Any) -> Any:
        from aiohttp import web
        return web.json_response({"status": "running", "port": self.port})

    async def _handle_message(self, request: Any) -> Any:
        from aiohttp import web
        try:
            msg = await request.json()
            if self._message_handler:
                result = await self._message_handler(msg)
                return web.json_response(result or {"ok": True})
            return web.json_response({"error": "no handler"}, status=500)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def _handle_ws(self, request: Any) -> Any:
        from aiohttp import web, WSMsgType
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if self._message_handler:
                            result = await self._message_handler(data)
                            await ws.send_json(result or {"ok": True})
                    except json.JSONDecodeError:
                        await ws.send_json({"error": "invalid JSON"})
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._ws_clients.discard(ws)
        return ws

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Send a message to all connected WebSocket clients."""
        for ws in list(self._ws_clients):
            try:
                await ws.send_json(data)
            except Exception:
                self._ws_clients.discard(ws)

    async def stop(self) -> None:
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()
        if self._server:
            if hasattr(self._server, "close"):
                self._server.close()
            self._server = None
