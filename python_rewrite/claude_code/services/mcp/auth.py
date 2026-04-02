"""
MCP OAuth authentication.

Handles the OAuth 2.0 authorization-code flow for remote MCP servers,
token persistence in the system keychain / secure storage, PKCE,
and server-side token revocation (RFC 7009).

Mirrors src/services/mcp/auth.ts.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .types import McpHTTPServerConfig, McpSSEServerConfig

logger = logging.getLogger(__name__)

AUTH_REQUEST_TIMEOUT_S = 30.0

# Sensitive OAuth params that must be redacted from logs
SENSITIVE_OAUTH_PARAMS = frozenset(
    {"state", "nonce", "code_challenge", "code_verifier", "code"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def redact_sensitive_url_params(url: str) -> str:
    """Redact sensitive OAuth query parameters from a URL for safe logging."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        for param in SENSITIVE_OAUTH_PARAMS:
            if param in qs:
                qs[param] = ["[REDACTED]"]
        redacted_query = urlencode(
            {k: v[0] for k, v in qs.items()}, doseq=False
        )
        return parsed._replace(query=redacted_query).geturl()
    except Exception:
        return url


def _generate_pkce() -> tuple[str, str]:
    """Generate a PKCE code verifier and its S256 challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def get_server_key(
    server_name: str,
    server_config: McpSSEServerConfig | McpHTTPServerConfig,
) -> str:
    """Unique key for server credentials based on name + config hash."""
    config_json = json.dumps(
        {
            "type": server_config.type,
            "url": server_config.url,
            "headers": server_config.headers or {},
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(config_json.encode()).hexdigest()[:16]
    return f"{server_name}|{digest}"


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

@dataclass
class OAuthTokenSet:
    """In-memory representation of persisted OAuth tokens."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[float] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    discovery_state: Optional[dict[str, Any]] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class MCPTokenStore:
    """Persist and retrieve MCP OAuth tokens.

    Default backend uses a JSON file under ``~/.claude/mcp_oauth.json``.
    On macOS this can be upgraded to Keychain.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            config_dir = os.environ.get(
                "CLAUDE_CONFIG_DIR",
                os.path.join(os.path.expanduser("~"), ".claude"),
            )
            storage_path = os.path.join(config_dir, "mcp_oauth.json")
        self._path = storage_path
        self._cache: dict[str, OAuthTokenSet] = {}
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path, "r") as fp:
                raw: dict[str, Any] = json.load(fp)
            for key, val in raw.items():
                self._cache[key] = OAuthTokenSet(**val)
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as fp:
            json.dump(
                {k: v.to_dict() for k, v in self._cache.items()},
                fp,
                indent=2,
            )

    # -- public API ----------------------------------------------------------

    def get(self, server_key: str) -> Optional[OAuthTokenSet]:
        return self._cache.get(server_key)

    def put(self, server_key: str, tokens: OAuthTokenSet) -> None:
        self._cache[server_key] = tokens
        self._save()

    def delete(self, server_key: str) -> None:
        self._cache.pop(server_key, None)
        self._save()

    def has_token(self, server_key: str) -> bool:
        ts = self._cache.get(server_key)
        return ts is not None and (
            ts.access_token is not None or ts.refresh_token is not None
        )

    def has_discovery_but_no_token(self, server_key: str) -> bool:
        ts = self._cache.get(server_key)
        return (
            ts is not None
            and ts.access_token is None
            and ts.refresh_token is None
        )


# Singleton token store
_token_store: Optional[MCPTokenStore] = None


def get_mcp_token_store() -> MCPTokenStore:
    global _token_store
    if _token_store is None:
        _token_store = MCPTokenStore()
    return _token_store


# ---------------------------------------------------------------------------
# OAuth metadata discovery
# ---------------------------------------------------------------------------

async def fetch_auth_server_metadata(
    server_url: str,
    configured_metadata_url: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Discover OAuth authorization-server metadata.

    1. If *configured_metadata_url* is provided, fetch it directly.
    2. Otherwise try RFC 9728 (protected-resource discovery) then RFC 8414.
    """
    async with httpx.AsyncClient(timeout=AUTH_REQUEST_TIMEOUT_S) as client:
        if configured_metadata_url:
            if not configured_metadata_url.startswith("https://"):
                raise ValueError(
                    f"authServerMetadataUrl must use https:// (got: {configured_metadata_url})"
                )
            resp = await client.get(
                configured_metadata_url,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

        # Try well-known discovery on the server URL
        parsed = urlparse(server_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for well_known_path in [
            f"/.well-known/oauth-authorization-server{parsed.path}",
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ]:
            try:
                resp = await client.get(
                    base + well_known_path,
                    headers={"Accept": "application/json"},
                )
                if resp.status_code == 200:
                    return resp.json()
            except httpx.HTTPError:
                continue

    return None


# ---------------------------------------------------------------------------
# Callback server (localhost) for auth-code flow
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth redirect."""

    auth_code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        qs = parse_qs(urlparse(self.path).query)
        cls = type(self)
        cls.auth_code = (qs.get("code") or [None])[0]
        cls.state = (qs.get("state") or [None])[0]
        cls.error = (qs.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Authentication successful!</h2>"
            b"<p>You may close this window.</p></body></html>"
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # suppress logging


def _find_available_port(preferred: int = 7866) -> int:
    """Find an available localhost port, preferring *preferred*."""
    import socket

    for port in [preferred, 0]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise RuntimeError("No available port for OAuth callback")


# ---------------------------------------------------------------------------
# ClaudeAuthProvider
# ---------------------------------------------------------------------------

@dataclass
class ClaudeAuthProvider:
    """Manages the OAuth flow for a single MCP server.

    Responsibilities:
    - PKCE auth-code flow via localhost redirect
    - Token refresh
    - Token revocation (RFC 7009)
    - Persistent storage of tokens
    """

    server_name: str
    server_config: McpSSEServerConfig | McpHTTPServerConfig
    _metadata: Optional[dict[str, Any]] = field(default=None, repr=False)

    @property
    def _server_key(self) -> str:
        return get_server_key(self.server_name, self.server_config)

    @property
    def _store(self) -> MCPTokenStore:
        return get_mcp_token_store()

    # -- metadata discovery --------------------------------------------------

    async def _ensure_metadata(self) -> dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        oauth_cfg = self.server_config.oauth
        meta_url = oauth_cfg.auth_server_metadata_url if oauth_cfg else None
        meta = await fetch_auth_server_metadata(self.server_config.url, meta_url)
        if meta is None:
            raise RuntimeError(
                f"Could not discover OAuth metadata for {self.server_name}"
            )
        self._metadata = meta
        return meta

    # -- token access --------------------------------------------------------

    def tokens(self) -> Optional[OAuthTokenSet]:
        return self._store.get(self._server_key)

    def has_valid_token(self) -> bool:
        ts = self.tokens()
        return ts is not None and ts.access_token is not None and not ts.is_expired

    # -- auth-code flow ------------------------------------------------------

    async def authorize_interactive(
        self,
        open_browser_fn: Any = None,
        timeout: float = 120.0,
    ) -> OAuthTokenSet:
        """Run the full OAuth authorization-code flow with PKCE.

        Opens a browser for the user to authenticate, waits for the callback
        on localhost, and exchanges the code for tokens.
        """
        meta = await self._ensure_metadata()
        verifier, challenge = _generate_pkce()
        state = secrets.token_urlsafe(32)

        oauth_cfg = self.server_config.oauth
        callback_port = (
            oauth_cfg.callback_port if oauth_cfg and oauth_cfg.callback_port else 7866
        )
        port = _find_available_port(callback_port)
        redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"

        client_id = (oauth_cfg.client_id if oauth_cfg else None) or meta.get("client_id", "claude-code")

        # Build authorization URL
        auth_endpoint = meta["authorization_endpoint"]
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": meta.get("scopes_supported", ["openid"])[0]
            if isinstance(meta.get("scopes_supported"), list)
            else "openid",
        }
        auth_url = f"{auth_endpoint}?{urlencode(params)}"

        # Start local callback server
        _CallbackHandler.auth_code = None
        _CallbackHandler.state = None
        _CallbackHandler.error = None
        server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        server.timeout = timeout

        # Open browser
        if open_browser_fn:
            open_browser_fn(auth_url)
        else:
            import webbrowser
            webbrowser.open(auth_url)

        logger.info("Waiting for OAuth callback on port %d …", port)

        # Wait for callback in a thread
        def _serve() -> None:
            server.handle_request()

        thread = Thread(target=_serve, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        server.server_close()

        if _CallbackHandler.error:
            raise RuntimeError(f"OAuth error: {_CallbackHandler.error}")
        if _CallbackHandler.auth_code is None:
            raise TimeoutError("OAuth callback timed out")
        if _CallbackHandler.state != state:
            raise RuntimeError("OAuth state mismatch — possible CSRF")

        # Exchange code for tokens
        token_endpoint = meta["token_endpoint"]
        async with httpx.AsyncClient(timeout=AUTH_REQUEST_TIMEOUT_S) as http:
            resp = await http.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": _CallbackHandler.auth_code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = None
        if "expires_in" in data:
            expires_at = time.time() + int(data["expires_in"])

        tokens = OAuthTokenSet(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            client_id=client_id,
        )
        self._store.put(self._server_key, tokens)
        return tokens

    # -- token refresh -------------------------------------------------------

    async def refresh(self) -> Optional[OAuthTokenSet]:
        """Refresh the stored token using the refresh_token grant."""
        ts = self.tokens()
        if ts is None or ts.refresh_token is None:
            return None

        try:
            meta = await self._ensure_metadata()
        except Exception:
            logger.warning("Cannot refresh: metadata discovery failed for %s", self.server_name)
            return None

        token_endpoint = meta["token_endpoint"]
        client_id = ts.client_id or "claude-code"

        body: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": ts.refresh_token,
            "client_id": client_id,
        }
        if ts.client_secret:
            body["client_secret"] = ts.client_secret

        async with httpx.AsyncClient(timeout=AUTH_REQUEST_TIMEOUT_S) as http:
            resp = await http.post(
                token_endpoint,
                data=body,
                headers={"Accept": "application/json"},
            )
            if resp.status_code >= 400:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if data.get("error") == "invalid_grant":
                    # Token permanently revoked
                    self.invalidate_credentials()
                    return None
                logger.warning("Token refresh failed for %s: %s", self.server_name, resp.text)
                return None
            data = resp.json()

        expires_at = None
        if "expires_in" in data:
            expires_at = time.time() + int(data["expires_in"])

        new_tokens = OAuthTokenSet(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token", ts.refresh_token),
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            client_id=client_id,
            client_secret=ts.client_secret,
            discovery_state=ts.discovery_state,
        )
        self._store.put(self._server_key, new_tokens)
        return new_tokens

    # -- token check & auto-refresh ------------------------------------------

    async def ensure_valid_token(self) -> Optional[str]:
        """Return a valid access token, refreshing if needed."""
        ts = self.tokens()
        if ts is None:
            return None
        if ts.access_token and not ts.is_expired:
            return ts.access_token
        refreshed = await self.refresh()
        return refreshed.access_token if refreshed else None

    # -- revocation ----------------------------------------------------------

    async def revoke(self) -> None:
        """Revoke tokens on the server and clear local storage."""
        ts = self.tokens()
        if ts is None:
            return

        try:
            meta = await self._ensure_metadata()
            revocation_endpoint = meta.get("revocation_endpoint")
            if revocation_endpoint and (ts.access_token or ts.refresh_token):
                async with httpx.AsyncClient(timeout=AUTH_REQUEST_TIMEOUT_S) as http:
                    client_id = ts.client_id or "claude-code"
                    for token, hint in [
                        (ts.refresh_token, "refresh_token"),
                        (ts.access_token, "access_token"),
                    ]:
                        if token:
                            try:
                                await http.post(
                                    revocation_endpoint,
                                    data={
                                        "token": token,
                                        "token_type_hint": hint,
                                        "client_id": client_id,
                                    },
                                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                                )
                            except httpx.HTTPError:
                                logger.debug("Failed to revoke %s for %s", hint, self.server_name)
        except Exception:
            logger.debug("Revocation metadata discovery failed for %s", self.server_name)

        self.invalidate_credentials()

    def invalidate_credentials(self) -> None:
        """Clear stored credentials without server-side revocation."""
        self._store.delete(self._server_key)
        self._metadata = None


class AuthenticationCancelledError(Exception):
    """Raised when the user cancels an interactive OAuth flow."""

    def __init__(self) -> None:
        super().__init__("Authentication was cancelled")
