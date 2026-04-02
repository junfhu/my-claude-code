"""
Language Server Protocol (LSP) client.

Provides an async LSP client that can communicate with language servers
for features like diagnostics, completions, hover information, and
go-to-definition.  Used by the lsp_tool to give Claude access to
IDE-grade code intelligence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 10.0  # seconds
LSP_HEADER_ENCODING = "utf-8"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class LSPPosition:
    """A position in a text document (0-based line and character)."""

    line: int
    character: int

    def to_dict(self) -> Dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass
class LSPRange:
    """A range in a text document."""

    start: LSPPosition
    end: LSPPosition

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


@dataclass
class LSPDiagnostic:
    """A diagnostic (error/warning) from the language server."""

    range: LSPRange
    message: str
    severity: int = 1  # 1=Error, 2=Warning, 3=Info, 4=Hint
    source: str = ""
    code: Optional[str] = None

    @property
    def severity_label(self) -> str:
        labels = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
        return labels.get(self.severity, "Unknown")


@dataclass
class LSPLocation:
    """A location in a file."""

    uri: str
    range: LSPRange


@dataclass
class LSPCompletionItem:
    """A completion suggestion."""

    label: str
    kind: int = 1
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""


@dataclass
class LSPHoverResult:
    """Result of a hover request."""

    contents: str
    range: Optional[LSPRange] = None


@dataclass
class LSPServerConfig:
    """Configuration for an LSP server."""

    language: str
    command: List[str]
    args: List[str] = field(default_factory=list)
    root_uri: str = ""
    initialization_options: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LSP Client
# ---------------------------------------------------------------------------


class LSPClient:
    """Async LSP client that communicates with a language server via stdio.

    Usage::

        config = LSPServerConfig(
            language="python",
            command=["pyright-langserver", "--stdio"],
        )
        client = LSPClient(config)
        await client.start()
        diagnostics = await client.get_diagnostics("file:///path/to/file.py")
        await client.stop()
    """

    def __init__(self, config: LSPServerConfig) -> None:
        self._config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._diagnostics: Dict[str, List[LSPDiagnostic]] = {}
        self._initialized = False
        self._reader_task: Optional[asyncio.Task] = None
        self._capabilities: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def capabilities(self) -> Dict[str, Any]:
        return dict(self._capabilities)

    # ---- Lifecycle ----

    async def start(self, root_path: Optional[str] = None) -> bool:
        """Start the language server process and initialize it."""
        if self.is_running:
            return True

        cmd = self._config.command + self._config.args
        env = {**os.environ, **self._config.env} if self._config.env else None

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except (OSError, FileNotFoundError) as exc:
            logger.warning("Cannot start LSP server %s: %s", cmd[0], exc)
            return False

        # Start the reader loop
        self._reader_task = asyncio.get_event_loop().create_task(self._read_loop())

        # Send initialize request
        root_uri = self._config.root_uri
        if not root_uri and root_path:
            root_uri = Path(root_path).as_uri()

        try:
            result = await self._request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": root_uri,
                    "capabilities": {
                        "textDocument": {
                            "completion": {"completionItem": {"snippetSupport": False}},
                            "hover": {},
                            "definition": {},
                            "references": {},
                            "publishDiagnostics": {"relatedInformation": True},
                        },
                    },
                    "initializationOptions": self._config.initialization_options,
                },
                timeout=30.0,
            )

            self._capabilities = result.get("capabilities", {})
            await self._notify("initialized", {})
            self._initialized = True
            logger.info("LSP server started: %s", self._config.language)
            return True

        except Exception as exc:
            logger.warning("LSP initialization failed: %s", exc)
            await self.stop()
            return False

    async def stop(self) -> None:
        """Shut down the language server."""
        if not self.is_running:
            return

        try:
            await self._request("shutdown", None, timeout=5.0)
            await self._notify("exit", None)
        except Exception:
            pass

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
            self._process = None

        self._initialized = False
        self._pending.clear()
        logger.info("LSP server stopped: %s", self._config.language)

    # ---- LSP Methods ----

    async def get_diagnostics(self, uri: str) -> List[LSPDiagnostic]:
        """Get diagnostics for a file.

        Note: Diagnostics are pushed by the server via notifications.
        This returns the last received diagnostics for the URI.
        """
        return list(self._diagnostics.get(uri, []))

    async def get_completions(
        self,
        uri: str,
        position: LSPPosition,
    ) -> List[LSPCompletionItem]:
        """Get completion items at a position."""
        result = await self._request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": position.to_dict(),
            },
        )

        items_data = result if isinstance(result, list) else result.get("items", [])
        items: List[LSPCompletionItem] = []
        for item_data in items_data[:50]:  # Limit results
            items.append(
                LSPCompletionItem(
                    label=item_data.get("label", ""),
                    kind=item_data.get("kind", 1),
                    detail=item_data.get("detail", ""),
                    documentation=_extract_documentation(item_data),
                    insert_text=item_data.get("insertText", item_data.get("label", "")),
                )
            )
        return items

    async def get_hover(
        self,
        uri: str,
        position: LSPPosition,
    ) -> Optional[LSPHoverResult]:
        """Get hover information at a position."""
        result = await self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": position.to_dict(),
            },
        )

        if not result:
            return None

        contents = result.get("contents", "")
        if isinstance(contents, dict):
            contents = contents.get("value", str(contents))
        elif isinstance(contents, list):
            parts = []
            for c in contents:
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, dict):
                    parts.append(c.get("value", ""))
            contents = "\n\n".join(parts)

        return LSPHoverResult(contents=str(contents))

    async def get_definition(
        self,
        uri: str,
        position: LSPPosition,
    ) -> List[LSPLocation]:
        """Get definition locations for a symbol."""
        result = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": position.to_dict(),
            },
        )

        return _parse_locations(result)

    async def get_references(
        self,
        uri: str,
        position: LSPPosition,
        include_declaration: bool = True,
    ) -> List[LSPLocation]:
        """Get all references to a symbol."""
        result = await self._request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": position.to_dict(),
                "context": {"includeDeclaration": include_declaration},
            },
        )

        return _parse_locations(result)

    async def did_open(self, uri: str, language_id: str, text: str) -> None:
        """Notify the server that a file was opened."""
        await self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                }
            },
        )

    async def did_change(self, uri: str, text: str, version: int = 2) -> None:
        """Notify the server that a file changed."""
        await self._notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    async def did_close(self, uri: str) -> None:
        """Notify the server that a file was closed."""
        await self._notify(
            "textDocument/didClose",
            {"textDocument": {"uri": uri}},
        )

    # ---- Protocol layer ----

    async def _request(
        self,
        method: str,
        params: Any,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        if not self.is_running:
            raise RuntimeError("LSP server not running")

        self._request_id += 1
        req_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        self._send_message(message)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"LSP request '{method}' timed out after {timeout}s")

    async def _notify(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.is_running:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send_message(message)

    def _send_message(self, message: Dict[str, Any]) -> None:
        """Encode and send a JSON-RPC message via stdin."""
        if self._process is None or self._process.stdin is None:
            return

        body = json.dumps(message)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._process.stdin.write(header.encode(LSP_HEADER_ENCODING))
        self._process.stdin.write(body.encode(LSP_HEADER_ENCODING))

    async def _read_loop(self) -> None:
        """Background task that reads messages from the server's stdout."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                # Read headers
                content_length = 0
                while True:
                    line = await self._process.stdout.readline()
                    if not line:
                        return  # Process ended
                    line_str = line.decode(LSP_HEADER_ENCODING).strip()
                    if not line_str:
                        break  # End of headers
                    if line_str.startswith("Content-Length:"):
                        content_length = int(line_str.split(":")[1].strip())

                if content_length == 0:
                    continue

                # Read body
                body = await self._process.stdout.readexactly(content_length)
                message = json.loads(body.decode(LSP_HEADER_ENCODING))

                self._handle_message(message)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("LSP read loop error: %s", exc)

    def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle an incoming JSON-RPC message."""
        if "id" in message and "method" not in message:
            # Response
            req_id = message["id"]
            future = self._pending.pop(req_id, None)
            if future and not future.done():
                if "error" in message:
                    future.set_exception(
                        RuntimeError(
                            f"LSP error: {message['error'].get('message', 'unknown')}"
                        )
                    )
                else:
                    future.set_result(message.get("result"))
        elif "method" in message:
            # Notification or request from server
            method = message["method"]
            params = message.get("params", {})

            if method == "textDocument/publishDiagnostics":
                self._handle_diagnostics(params)
            elif method == "window/logMessage":
                log_msg = params.get("message", "")
                logger.debug("LSP server: %s", log_msg)

    def _handle_diagnostics(self, params: Dict[str, Any]) -> None:
        """Handle a publishDiagnostics notification."""
        uri = params.get("uri", "")
        diags_data = params.get("diagnostics", [])

        diagnostics: List[LSPDiagnostic] = []
        for d in diags_data:
            r = d.get("range", {})
            start = r.get("start", {})
            end = r.get("end", {})

            diagnostics.append(
                LSPDiagnostic(
                    range=LSPRange(
                        start=LSPPosition(
                            line=start.get("line", 0),
                            character=start.get("character", 0),
                        ),
                        end=LSPPosition(
                            line=end.get("line", 0),
                            character=end.get("character", 0),
                        ),
                    ),
                    message=d.get("message", ""),
                    severity=d.get("severity", 1),
                    source=d.get("source", ""),
                    code=str(d["code"]) if "code" in d else None,
                )
            )

        self._diagnostics[uri] = diagnostics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_locations(result: Any) -> List[LSPLocation]:
    """Parse location(s) from an LSP response."""
    if result is None:
        return []

    if isinstance(result, dict):
        result = [result]

    locations: List[LSPLocation] = []
    for loc_data in result:
        uri = loc_data.get("uri", loc_data.get("targetUri", ""))
        r = loc_data.get("range", loc_data.get("targetRange", {}))
        start = r.get("start", {})
        end = r.get("end", {})

        locations.append(
            LSPLocation(
                uri=uri,
                range=LSPRange(
                    start=LSPPosition(
                        line=start.get("line", 0),
                        character=start.get("character", 0),
                    ),
                    end=LSPPosition(
                        line=end.get("line", 0),
                        character=end.get("character", 0),
                    ),
                ),
            )
        )
    return locations


def _extract_documentation(item_data: Dict[str, Any]) -> str:
    """Extract documentation from a completion item."""
    doc = item_data.get("documentation", "")
    if isinstance(doc, dict):
        return doc.get("value", "")
    return str(doc) if doc else ""


# ---------------------------------------------------------------------------
# Server discovery
# ---------------------------------------------------------------------------


def discover_language_servers(cwd: str = ".") -> Dict[str, LSPServerConfig]:
    """Discover available language servers based on the project."""
    import shutil

    servers: Dict[str, LSPServerConfig] = {}
    cwd_path = Path(cwd).resolve()

    # Python
    for cmd in ("pyright-langserver", "pylsp", "python-lsp-server"):
        if shutil.which(cmd):
            servers["python"] = LSPServerConfig(
                language="python",
                command=[cmd, "--stdio"] if "pyright" in cmd else [cmd],
                root_uri=cwd_path.as_uri(),
            )
            break

    # TypeScript/JavaScript
    for cmd in ("typescript-language-server",):
        if shutil.which(cmd):
            servers["typescript"] = LSPServerConfig(
                language="typescript",
                command=[cmd, "--stdio"],
                root_uri=cwd_path.as_uri(),
            )
            break

    # Rust
    if shutil.which("rust-analyzer"):
        servers["rust"] = LSPServerConfig(
            language="rust",
            command=["rust-analyzer"],
            root_uri=cwd_path.as_uri(),
        )

    # Go
    if shutil.which("gopls"):
        servers["go"] = LSPServerConfig(
            language="go",
            command=["gopls"],
            root_uri=cwd_path.as_uri(),
        )

    return servers
