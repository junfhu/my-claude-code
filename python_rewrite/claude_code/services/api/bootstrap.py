"""
Bootstrap data fetching from the Anthropic API.

Fetches initial configuration, model availability, feature flags, and
account information at startup.  This data is cached for the session
and used to configure tool availability, model selection, etc.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BootstrapData:
    """Bootstrap data fetched from the API at startup."""

    # Account
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    account_tier: Optional[str] = None

    # Models
    available_models: List[str] = field(default_factory=list)
    default_model: str = "claude-sonnet-4-20250514"
    model_limits: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Feature flags
    features: Dict[str, bool] = field(default_factory=dict)

    # Rate limits
    rate_limits: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    fetched_at: float = field(default_factory=time.time)
    api_version: Optional[str] = None
    provider: str = "anthropic"

    # Cached
    _cached: bool = False

    @property
    def is_fresh(self) -> bool:
        """Whether the bootstrap data is less than 1 hour old."""
        return (time.time() - self.fetched_at) < 3600

    def has_feature(self, feature: str) -> bool:
        return self.features.get(feature, False)

    def model_context_window(self, model: str) -> int:
        limits = self.model_limits.get(model, {})
        return limits.get("context_window", 200_000)

    def model_max_output(self, model: str) -> int:
        limits = self.model_limits.get(model, {})
        return limits.get("max_output_tokens", 16384)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


async def fetch_bootstrap_data(
    *,
    api_key: Optional[str] = None,
    provider: str = "anthropic",
    base_url: Optional[str] = None,
    timeout_seconds: float = 10.0,
) -> BootstrapData:
    """Fetch bootstrap data from the API.

    This performs a lightweight API probe to determine account capabilities.
    Falls back to sensible defaults on failure.
    """
    data = BootstrapData(provider=provider)

    try:
        import anthropic

        client_kwargs: Dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        client_kwargs["timeout"] = timeout_seconds

        client = anthropic.AsyncAnthropic(**client_kwargs)

        # Probe with a minimal request to get account info
        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}],
                ),
                timeout=timeout_seconds,
            )

            # Extract info from response headers if available
            data.api_version = getattr(response, "_headers", {}).get(
                "anthropic-version", None
            )

        except asyncio.TimeoutError:
            logger.warning("Bootstrap API probe timed out after %.1fs", timeout_seconds)
        except anthropic.AuthenticationError:
            logger.warning("Bootstrap failed: invalid API key")
            data.features["auth_valid"] = False
        except anthropic.APIError as exc:
            # Still extract useful info from errors
            logger.debug("Bootstrap probe returned: %s", exc)

        # Set known models
        data.available_models = _known_models(provider)
        data.model_limits = _known_model_limits()
        data.features.setdefault("auth_valid", True)

    except ImportError:
        logger.warning("anthropic package not available for bootstrap")
        data.available_models = _known_models(provider)
        data.model_limits = _known_model_limits()

    except Exception as exc:
        logger.warning("Bootstrap data fetch failed: %s", exc)
        data.available_models = _known_models(provider)
        data.model_limits = _known_model_limits()

    data.fetched_at = time.time()
    return data


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


_cache: Optional[BootstrapData] = None


async def get_bootstrap_data(
    *,
    force_refresh: bool = False,
    **kwargs: Any,
) -> BootstrapData:
    """Get bootstrap data, using cache if available and fresh."""
    global _cache
    if _cache is not None and _cache.is_fresh and not force_refresh:
        return _cache

    _cache = await fetch_bootstrap_data(**kwargs)
    return _cache


def get_cached_bootstrap_data() -> Optional[BootstrapData]:
    """Return the cached bootstrap data (may be None)."""
    return _cache


def save_bootstrap_cache(directory: Optional[str] = None) -> None:
    """Persist bootstrap data to disk cache."""
    if _cache is None:
        return

    dir_path = Path(directory) if directory else Path.home() / ".claude" / "cache"
    dir_path.mkdir(parents=True, exist_ok=True)

    cache_file = dir_path / "bootstrap.json"
    try:
        from dataclasses import asdict
        with open(cache_file, "w") as f:
            json.dump(asdict(_cache), f, indent=2, default=str)
    except OSError as exc:
        logger.warning("Cannot save bootstrap cache: %s", exc)


def load_bootstrap_cache(directory: Optional[str] = None) -> Optional[BootstrapData]:
    """Load bootstrap data from disk cache."""
    global _cache

    dir_path = Path(directory) if directory else Path.home() / ".claude" / "cache"
    cache_file = dir_path / "bootstrap.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r") as f:
            data = json.load(f)

        bs = BootstrapData(
            account_id=data.get("account_id"),
            account_name=data.get("account_name"),
            account_tier=data.get("account_tier"),
            available_models=data.get("available_models", []),
            default_model=data.get("default_model", "claude-sonnet-4-20250514"),
            model_limits=data.get("model_limits", {}),
            features=data.get("features", {}),
            rate_limits=data.get("rate_limits", {}),
            fetched_at=data.get("fetched_at", 0),
            api_version=data.get("api_version"),
            provider=data.get("provider", "anthropic"),
            _cached=True,
        )

        if bs.is_fresh:
            _cache = bs
            return bs

        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot load bootstrap cache: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Known models / limits
# ---------------------------------------------------------------------------


def _known_models(provider: str = "anthropic") -> List[str]:
    """Return a list of known available models."""
    models = [
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
    ]
    if provider == "bedrock":
        return [f"anthropic.{m}" for m in models]
    return models


def _known_model_limits() -> Dict[str, Dict[str, int]]:
    """Return known model context windows and output limits."""
    return {
        "claude-opus-4-20250514": {
            "context_window": 200_000,
            "max_output_tokens": 32768,
        },
        "claude-sonnet-4-20250514": {
            "context_window": 200_000,
            "max_output_tokens": 16384,
        },
        "claude-3-7-sonnet-20250219": {
            "context_window": 200_000,
            "max_output_tokens": 16384,
        },
        "claude-3-5-sonnet-20241022": {
            "context_window": 200_000,
            "max_output_tokens": 8192,
        },
        "claude-3-5-haiku-20241022": {
            "context_window": 200_000,
            "max_output_tokens": 8192,
        },
        "claude-3-haiku-20240307": {
            "context_window": 200_000,
            "max_output_tokens": 4096,
        },
    }
