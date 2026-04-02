"""
Anthropic API client creation.

Provides factory functions for creating API clients that support multiple
providers: Direct (Anthropic), Bedrock, Vertex AI, and Azure.  Handles
authentication (API key, OAuth), proxy support, and custom headers.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ClientConfig:
    """Configuration for creating an Anthropic API client."""

    # Provider selection
    provider: str = "anthropic"  # anthropic | bedrock | vertex | azure

    # Auth
    api_key: Optional[str] = None
    oauth_token: Optional[str] = None

    # Endpoints
    base_url: Optional[str] = None
    api_version: Optional[str] = None

    # Bedrock-specific
    aws_region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    aws_profile: Optional[str] = None

    # Vertex-specific
    gcp_project: Optional[str] = None
    gcp_region: Optional[str] = None
    gcp_credentials: Optional[str] = None  # Path to service account JSON

    # Azure-specific
    azure_endpoint: Optional[str] = None
    azure_api_key: Optional[str] = None
    azure_deployment: Optional[str] = None
    azure_api_version: Optional[str] = None

    # Network
    timeout_seconds: float = 120.0
    max_retries: int = 2
    proxy_url: Optional[str] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)

    # Behaviour
    enable_streaming: bool = True

    @classmethod
    def from_env(cls, **overrides: Any) -> "ClientConfig":
        """Create a config from environment variables."""
        env = {
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
            "provider": os.environ.get("CLAUDE_PROVIDER", "anthropic"),
            "timeout_seconds": float(
                os.environ.get("CLAUDE_TIMEOUT_SECONDS", "120")
            ),
            "proxy_url": os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"),
            # Bedrock
            "aws_region": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
            "aws_session_token": os.environ.get("AWS_SESSION_TOKEN"),
            "aws_profile": os.environ.get("AWS_PROFILE"),
            # Vertex
            "gcp_project": os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT"),
            "gcp_region": os.environ.get("GOOGLE_CLOUD_REGION", "us-east5"),
            "gcp_credentials": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            # Azure
            "azure_endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT"),
            "azure_api_key": os.environ.get("AZURE_OPENAI_API_KEY"),
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "azure_api_version": os.environ.get("AZURE_API_VERSION", "2024-06-01"),
        }
        # Remove None values so overrides take precedence
        env = {k: v for k, v in env.items() if v is not None}
        env.update(overrides)
        return cls(**env)


# ---------------------------------------------------------------------------
# Client creation
# ---------------------------------------------------------------------------


def get_anthropic_client(
    config: Optional[ClientConfig] = None,
    *,
    async_client: bool = True,
) -> Any:
    """Create and return an Anthropic API client.

    Supports Direct, Bedrock, Vertex, and Azure providers.

    Args:
        config: Client configuration (defaults to env-based config).
        async_client: Whether to create an async client (default True).

    Returns:
        An anthropic client instance (AsyncAnthropic, AsyncAnthropicBedrock, etc.)
    """
    if config is None:
        config = ClientConfig.from_env()

    provider = config.provider.lower()

    if provider == "bedrock":
        return _create_bedrock_client(config, async_client)
    elif provider == "vertex":
        return _create_vertex_client(config, async_client)
    elif provider == "azure":
        return _create_azure_client(config, async_client)
    else:
        return _create_direct_client(config, async_client)


def _create_direct_client(config: ClientConfig, async_client: bool) -> Any:
    """Create a direct Anthropic API client."""
    import anthropic

    kwargs: Dict[str, Any] = {}

    # API key
    api_key = config.api_key
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        kwargs["api_key"] = api_key

    # Auth header for OAuth
    if config.oauth_token:
        kwargs.setdefault("default_headers", {})
        kwargs["default_headers"]["Authorization"] = f"Bearer {config.oauth_token}"

    # Base URL
    if config.base_url:
        kwargs["base_url"] = config.base_url

    # Timeout
    kwargs["timeout"] = config.timeout_seconds
    kwargs["max_retries"] = config.max_retries

    # Custom headers
    if config.custom_headers:
        kwargs.setdefault("default_headers", {})
        kwargs["default_headers"].update(config.custom_headers)

    # Proxy via httpx
    if config.proxy_url:
        import httpx

        transport = httpx.AsyncHTTPTransport(proxy=config.proxy_url) if async_client else httpx.HTTPTransport(proxy=config.proxy_url)
        if async_client:
            http_client = httpx.AsyncClient(transport=transport)
        else:
            http_client = httpx.Client(transport=transport)
        kwargs["http_client"] = http_client

    logger.debug("Creating %s Anthropic client", "async" if async_client else "sync")

    if async_client:
        return anthropic.AsyncAnthropic(**kwargs)
    return anthropic.Anthropic(**kwargs)


def _create_bedrock_client(config: ClientConfig, async_client: bool) -> Any:
    """Create an Amazon Bedrock Anthropic client."""
    import anthropic

    kwargs: Dict[str, Any] = {}

    if config.aws_region:
        kwargs["aws_region"] = config.aws_region
    if config.aws_access_key_id:
        kwargs["aws_access_key"] = config.aws_access_key_id
    if config.aws_secret_access_key:
        kwargs["aws_secret_key"] = config.aws_secret_access_key
    if config.aws_session_token:
        kwargs["aws_session_token"] = config.aws_session_token
    if config.aws_profile:
        kwargs["aws_profile"] = config.aws_profile

    kwargs["timeout"] = config.timeout_seconds
    kwargs["max_retries"] = config.max_retries

    if config.base_url:
        kwargs["base_url"] = config.base_url

    logger.debug("Creating %s Bedrock client region=%s", "async" if async_client else "sync", config.aws_region)

    if async_client:
        return anthropic.AsyncAnthropicBedrock(**kwargs)
    return anthropic.AnthropicBedrock(**kwargs)


def _create_vertex_client(config: ClientConfig, async_client: bool) -> Any:
    """Create a Google Vertex AI Anthropic client."""
    import anthropic

    kwargs: Dict[str, Any] = {}

    if config.gcp_project:
        kwargs["project_id"] = config.gcp_project
    if config.gcp_region:
        kwargs["region"] = config.gcp_region

    kwargs["timeout"] = config.timeout_seconds
    kwargs["max_retries"] = config.max_retries

    if config.base_url:
        kwargs["base_url"] = config.base_url

    logger.debug(
        "Creating %s Vertex client project=%s region=%s",
        "async" if async_client else "sync",
        config.gcp_project,
        config.gcp_region,
    )

    if async_client:
        return anthropic.AsyncAnthropicVertex(**kwargs)
    return anthropic.AnthropicVertex(**kwargs)


def _create_azure_client(config: ClientConfig, async_client: bool) -> Any:
    """Create an Azure OpenAI-compatible client for Claude.

    Note: Azure support may require a custom base_url approach since
    the anthropic SDK doesn't natively support Azure.  This provides
    the standard direct client pointed at an Azure endpoint.
    """
    import anthropic

    kwargs: Dict[str, Any] = {}

    base_url = config.azure_endpoint or config.base_url
    if base_url:
        kwargs["base_url"] = base_url

    api_key = config.azure_api_key or config.api_key
    if api_key:
        kwargs["api_key"] = api_key

    kwargs["timeout"] = config.timeout_seconds
    kwargs["max_retries"] = config.max_retries

    # Azure-specific headers
    headers = dict(config.custom_headers)
    if config.azure_api_version:
        headers["api-version"] = config.azure_api_version
    if headers:
        kwargs["default_headers"] = headers

    logger.debug("Creating %s Azure client endpoint=%s", "async" if async_client else "sync", base_url)

    if async_client:
        return anthropic.AsyncAnthropic(**kwargs)
    return anthropic.Anthropic(**kwargs)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def check_api_health(config: Optional[ClientConfig] = None) -> Dict[str, Any]:
    """Perform a lightweight API health check.

    Returns a dict with ``ok``, ``latency_ms``, ``provider``, and
    optional ``error`` fields.
    """
    import time

    if config is None:
        config = ClientConfig.from_env()

    start = time.time()
    try:
        client = get_anthropic_client(config, async_client=True)
        # Use a minimal messages call with max_tokens=1
        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1,
            messages=[{"role": "user", "content": "Hi"}],
        )
        latency_ms = (time.time() - start) * 1000
        return {
            "ok": True,
            "latency_ms": round(latency_ms, 1),
            "provider": config.provider,
            "model": getattr(response, "model", "unknown"),
        }
    except Exception as exc:
        latency_ms = (time.time() - start) * 1000
        return {
            "ok": False,
            "latency_ms": round(latency_ms, 1),
            "provider": config.provider,
            "error": str(exc),
        }
