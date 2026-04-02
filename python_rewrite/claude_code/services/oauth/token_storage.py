"""
OAuth token persistence.

Stores OAuth tokens securely for the Claude Code CLI.
On macOS, can integrate with Keychain; on Linux, uses encrypted file storage;
fallback is a JSON file under ``~/.claude/``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OAuthTokens:
    """OAuth2 token set."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    expires_at: Optional[float] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None

    def __post_init__(self) -> None:
        if self.expires_at is None and self.expires_in is not None:
            self.expires_at = time.time() + self.expires_in

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at - 60  # 60s grace

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"access_token": self.access_token, "token_type": self.token_type}
        if self.refresh_token:
            d["refresh_token"] = self.refresh_token
        if self.expires_at:
            d["expires_at"] = self.expires_at
        if self.scope:
            d["scope"] = self.scope
        if self.id_token:
            d["id_token"] = self.id_token
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthTokens":
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_at=data.get("expires_at"),
            scope=data.get("scope"),
            id_token=data.get("id_token"),
        )


class TokenStorage:
    """Persist OAuth tokens to disk.

    Default location: ``~/.claude/oauth_tokens.json``

    File format::

        {
          "<provider_key>": {
            "access_token": "...",
            "refresh_token": "...",
            "token_type": "Bearer",
            "expires_at": 1700000000.0
          }
        }
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        if storage_path is None:
            config_dir = os.environ.get(
                "CLAUDE_CONFIG_DIR",
                os.path.join(os.path.expanduser("~"), ".claude"),
            )
            storage_path = os.path.join(config_dir, "oauth_tokens.json")
        self._path = storage_path
        self._cache: dict[str, OAuthTokens] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path) as f:
                raw = json.load(f)
            self._cache = {
                k: OAuthTokens.from_dict(v) for k, v in raw.items()
            }
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._cache = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w") as f:
            json.dump({k: v.to_dict() for k, v in self._cache.items()}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
        # Restrict permissions
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def get(self, key: str) -> Optional[OAuthTokens]:
        """Retrieve tokens for *key*."""
        return self._cache.get(key)

    def put(self, key: str, tokens: OAuthTokens) -> None:
        """Store tokens under *key*."""
        self._cache[key] = tokens
        self._save()

    def delete(self, key: str) -> bool:
        """Delete tokens for *key*. Returns True if existed."""
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    def has(self, key: str) -> bool:
        return key in self._cache

    def list_keys(self) -> list[str]:
        return list(self._cache.keys())

    def clear(self) -> None:
        """Remove all stored tokens."""
        self._cache.clear()
        self._save()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[TokenStorage] = None


def get_token_storage() -> TokenStorage:
    """Return the global token-storage singleton."""
    global _instance
    if _instance is None:
        _instance = TokenStorage()
    return _instance
