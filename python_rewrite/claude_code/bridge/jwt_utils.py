"""
JWT utilities for bridge authentication.

Handles JWT creation, verification, and session-ingress token management.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def base64url_encode(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def base64url_decode(s: str) -> bytes:
    """Base64url-decode with padding restoration."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the payload of a JWT *without* signature verification.

    This is used for reading claims like ``exp``, ``sub``, ``session_id``
    from tokens where we trust the transport (TLS + known issuer).
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT: expected 3 parts")
    payload_b64 = parts[1]
    payload_bytes = base64url_decode(payload_b64)
    return json.loads(payload_bytes)


def is_jwt_expired(token: str, clock_skew_seconds: int = 60) -> bool:
    """Return True if the JWT's ``exp`` claim is in the past."""
    try:
        payload = decode_jwt_payload(token)
        exp = payload.get("exp")
        if exp is None:
            return False
        return time.time() > (exp - clock_skew_seconds)
    except Exception:
        return True


def get_jwt_claim(token: str, claim: str) -> Any:
    """Extract a single claim from a JWT payload."""
    payload = decode_jwt_payload(token)
    return payload.get(claim)


def create_unsigned_jwt(
    payload: dict[str, Any],
    *,
    expires_in: int = 3600,
) -> str:
    """Create an unsigned JWT (``alg: none``) for local/testing use.

    Production uses signed tokens from the server; this is only for
    local development and testing.
    """
    header = {"alg": "none", "typ": "JWT"}
    now = int(time.time())
    full_payload = {
        "iat": now,
        "exp": now + expires_in,
        **payload,
    }
    header_b64 = base64url_encode(json.dumps(header).encode())
    payload_b64 = base64url_encode(json.dumps(full_payload).encode())
    return f"{header_b64}.{payload_b64}."


def create_hmac_jwt(
    payload: dict[str, Any],
    secret: str | bytes,
    *,
    expires_in: int = 3600,
) -> str:
    """Create an HMAC-SHA256 signed JWT."""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    full_payload = {"iat": now, "exp": now + expires_in, **payload}

    header_b64 = base64url_encode(json.dumps(header).encode())
    payload_b64 = base64url_encode(json.dumps(full_payload).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    if isinstance(secret, str):
        secret = secret.encode()
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_hmac_jwt(
    token: str,
    secret: str | bytes,
    *,
    clock_skew_seconds: int = 60,
) -> dict[str, Any]:
    """Verify an HMAC-SHA256 JWT and return its payload.

    Raises ``ValueError`` if the signature is invalid or the token is expired.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")

    signing_input = f"{parts[0]}.{parts[1]}".encode()
    if isinstance(secret, str):
        secret = secret.encode()

    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    actual_sig = base64url_decode(parts[2])

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid JWT signature")

    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp is not None and time.time() > (exp + clock_skew_seconds):
        raise ValueError("JWT expired")

    return payload


def decode_work_secret(secret_b64: str) -> dict[str, Any]:
    """Decode the base64url-encoded work secret from the environments API."""
    raw = base64url_decode(secret_b64)
    return json.loads(raw)
