"""
OAuth flow implementation for Claude Code CLI authentication.

Handles login/logout, token refresh, authorization-code flow with PKCE,
and device-code flow for headless environments.

Mirrors src/services/oauth/client.ts + index.ts.
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
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .token_storage import OAuthTokens, get_token_storage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OAUTH_PROVIDER_KEY = "anthropic"

DEFAULT_AUTH_URL = "https://auth.anthropic.com"
DEFAULT_TOKEN_URL = "https://auth.anthropic.com/oauth/token"
DEFAULT_DEVICE_AUTH_URL = "https://auth.anthropic.com/oauth/device/code"
DEFAULT_REVOKE_URL = "https://auth.anthropic.com/oauth/revoke"
DEFAULT_CLIENT_ID = "claude-code"
DEFAULT_SCOPES = "openid offline_access"

AUTH_TIMEOUT_S = 120.0
TOKEN_REQUEST_TIMEOUT_S = 30.0


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_pkce() -> tuple[str, str]:
    """Generate (verifier, challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _find_port(preferred: int = 7870) -> int:
    import socket
    for port in [preferred, 0]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    raise RuntimeError("No available port")


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802
        qs = parse_qs(urlparse(self.path).query)
        cls = type(self)
        cls.code = (qs.get("code") or [None])[0]
        cls.state = (qs.get("state") or [None])[0]
        cls.error = (qs.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Login successful!</h2>"
            b"<p>You may close this window and return to Claude Code.</p></body></html>"
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


# ---------------------------------------------------------------------------
# OAuth configuration
# ---------------------------------------------------------------------------

def _get_oauth_config() -> dict[str, str]:
    return {
        "auth_url": os.environ.get("CLAUDE_AUTH_URL", DEFAULT_AUTH_URL),
        "token_url": os.environ.get("CLAUDE_TOKEN_URL", DEFAULT_TOKEN_URL),
        "device_auth_url": os.environ.get("CLAUDE_DEVICE_AUTH_URL", DEFAULT_DEVICE_AUTH_URL),
        "revoke_url": os.environ.get("CLAUDE_REVOKE_URL", DEFAULT_REVOKE_URL),
        "client_id": os.environ.get("CLAUDE_OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID),
        "scopes": os.environ.get("CLAUDE_OAUTH_SCOPES", DEFAULT_SCOPES),
    }


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

async def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    verifier: str,
) -> OAuthTokens:
    """Exchange an authorization code for tokens."""
    cfg = _get_oauth_config()
    async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_S) as client:
        resp = await client.post(
            cfg["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": cfg["client_id"],
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    return OAuthTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        token_type=data.get("token_type", "Bearer"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
        id_token=data.get("id_token"),
    )


# ---------------------------------------------------------------------------
# Authorization-code flow (interactive)
# ---------------------------------------------------------------------------

async def login(*, open_browser: bool = True) -> OAuthTokens:
    """Run the interactive authorization-code flow with PKCE.

    1. Start a local callback server.
    2. Open the browser for user authentication.
    3. Exchange the code for tokens.
    4. Persist tokens in storage.
    """
    cfg = _get_oauth_config()
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)
    port = _find_port()
    redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"

    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": cfg["scopes"],
    }
    auth_url = f"{cfg['auth_url']}/authorize?{urlencode(params)}"

    _OAuthCallbackHandler.code = None
    _OAuthCallbackHandler.state = None
    _OAuthCallbackHandler.error = None
    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.timeout = AUTH_TIMEOUT_S

    if open_browser:
        webbrowser.open(auth_url)
        logger.info("Opened browser for authentication. Waiting for callback …")
    else:
        logger.info("Please open this URL to authenticate:\n%s", auth_url)

    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=AUTH_TIMEOUT_S)
    server.server_close()

    if _OAuthCallbackHandler.error:
        raise RuntimeError(f"OAuth error: {_OAuthCallbackHandler.error}")
    if _OAuthCallbackHandler.code is None:
        raise TimeoutError("Authentication timed out")
    if _OAuthCallbackHandler.state != state:
        raise RuntimeError("State mismatch — possible CSRF attack")

    tokens = await _exchange_code_for_tokens(
        _OAuthCallbackHandler.code, redirect_uri, verifier
    )

    get_token_storage().put(OAUTH_PROVIDER_KEY, tokens)
    logger.info("Login successful")
    return tokens


# ---------------------------------------------------------------------------
# Device-code flow (headless)
# ---------------------------------------------------------------------------

async def login_device_code(
    poll_interval: float = 5.0,
    timeout: float = 300.0,
) -> OAuthTokens:
    """Run the device-code flow for headless environments.

    Returns tokens after the user authorises in a browser.
    """
    cfg = _get_oauth_config()

    async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_S) as client:
        # Request device code
        resp = await client.post(
            cfg["device_auth_url"],
            data={"client_id": cfg["client_id"], "scope": cfg["scopes"]},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data.get("verification_uri_complete") or data["verification_uri"]
    interval = data.get("interval", poll_interval)

    logger.info("Enter code %s at %s", user_code, verification_uri)

    # Poll for tokens
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_S) as client:
        while time.time() < deadline:
            await asyncio.sleep(interval)
            resp = await client.post(
                cfg["token_url"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": cfg["client_id"],
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                token_data = resp.json()
                if "access_token" in token_data:
                    tokens = OAuthTokens(
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token"),
                        token_type=token_data.get("token_type", "Bearer"),
                        expires_in=token_data.get("expires_in"),
                    )
                    get_token_storage().put(OAUTH_PROVIDER_KEY, tokens)
                    logger.info("Device-code login successful")
                    return tokens
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            error = body.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval = min(interval + 5, 30)
                continue
            if error in ("expired_token", "access_denied"):
                raise RuntimeError(f"Device auth failed: {error}")

    raise TimeoutError("Device-code authentication timed out")


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

async def refresh_token(key: str = OAUTH_PROVIDER_KEY) -> Optional[OAuthTokens]:
    """Refresh the stored token using the refresh_token grant.

    Returns new tokens on success, ``None`` if no refresh token available.
    """
    store = get_token_storage()
    existing = store.get(key)
    if existing is None or existing.refresh_token is None:
        return None

    cfg = _get_oauth_config()
    async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_S) as client:
        resp = await client.post(
            cfg["token_url"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": existing.refresh_token,
                "client_id": cfg["client_id"],
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if body.get("error") == "invalid_grant":
                store.delete(key)
                return None
            logger.warning("Token refresh failed: %s", resp.text)
            return None
        data = resp.json()

    tokens = OAuthTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", existing.refresh_token),
        token_type=data.get("token_type", "Bearer"),
        expires_in=data.get("expires_in"),
        scope=data.get("scope"),
        id_token=data.get("id_token"),
    )
    store.put(key, tokens)
    return tokens


async def ensure_valid_token(key: str = OAUTH_PROVIDER_KEY) -> Optional[str]:
    """Return a valid access token, refreshing if necessary."""
    store = get_token_storage()
    existing = store.get(key)
    if existing is None:
        return None
    if not existing.is_expired:
        return existing.access_token
    refreshed = await refresh_token(key)
    return refreshed.access_token if refreshed else None


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

async def logout(key: str = OAUTH_PROVIDER_KEY) -> None:
    """Revoke tokens on the server and clear local storage."""
    store = get_token_storage()
    existing = store.get(key)
    if existing is None:
        return

    cfg = _get_oauth_config()
    async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_S) as client:
        for token, hint in [
            (existing.refresh_token, "refresh_token"),
            (existing.access_token, "access_token"),
        ]:
            if token:
                try:
                    await client.post(
                        cfg["revoke_url"],
                        data={
                            "token": token,
                            "token_type_hint": hint,
                            "client_id": cfg["client_id"],
                        },
                    )
                except httpx.HTTPError:
                    logger.debug("Failed to revoke %s", hint)

    store.delete(key)
    logger.info("Logged out successfully")


def is_logged_in(key: str = OAUTH_PROVIDER_KEY) -> bool:
    """Check if valid tokens exist in storage."""
    store = get_token_storage()
    tokens = store.get(key)
    return tokens is not None and tokens.access_token is not None


def get_access_token(key: str = OAUTH_PROVIDER_KEY) -> Optional[str]:
    """Synchronously get the stored access token (may be expired)."""
    store = get_token_storage()
    tokens = store.get(key)
    return tokens.access_token if tokens else None
