"""
OAuth configuration, scopes, and URL helpers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

__all__ = [
    # Scopes
    "CLAUDE_AI_INFERENCE_SCOPE",
    "CLAUDE_AI_PROFILE_SCOPE",
    "CONSOLE_SCOPE",
    "OAUTH_BETA_HEADER",
    "CONSOLE_OAUTH_SCOPES",
    "CLAUDE_AI_OAUTH_SCOPES",
    "ALL_OAUTH_SCOPES",
    # MCP
    "MCP_CLIENT_METADATA_URL",
    # Config
    "OauthConfig",
    "get_oauth_config",
    "file_suffix_for_oauth_config",
    # Allowed base URLs
    "ALLOWED_OAUTH_BASE_URLS",
]

# ============================================================================
# Scopes
# ============================================================================

CLAUDE_AI_INFERENCE_SCOPE: str = "user:inference"
CLAUDE_AI_PROFILE_SCOPE: str = "user:profile"
CONSOLE_SCOPE: str = "org:create_api_key"
OAUTH_BETA_HEADER: str = "oauth-2025-04-20"

CONSOLE_OAUTH_SCOPES: tuple[str, ...] = (
    CONSOLE_SCOPE,
    CLAUDE_AI_PROFILE_SCOPE,
)
"""Console OAuth scopes — for API key creation via Console."""

CLAUDE_AI_OAUTH_SCOPES: tuple[str, ...] = (
    CLAUDE_AI_PROFILE_SCOPE,
    CLAUDE_AI_INFERENCE_SCOPE,
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
)
"""Claude.ai OAuth scopes — for Claude.ai subscribers (Pro/Max/Team/Enterprise)."""

ALL_OAUTH_SCOPES: tuple[str, ...] = tuple(
    dict.fromkeys([*CONSOLE_OAUTH_SCOPES, *CLAUDE_AI_OAUTH_SCOPES])
)
"""Union of all OAuth scopes used in Claude CLI."""

# ============================================================================
# MCP Client Metadata
# ============================================================================

MCP_CLIENT_METADATA_URL: str = "https://claude.ai/oauth/claude-code-client-metadata"
"""Client ID Metadata Document URL for MCP OAuth (CIMD / SEP-991)."""

# ============================================================================
# Allowed base URLs
# ============================================================================

ALLOWED_OAUTH_BASE_URLS: tuple[str, ...] = (
    "https://beacon.claude-ai.staging.ant.dev",
    "https://claude.fedstart.com",
    "https://claude-staging.fedstart.com",
)
"""Allowed base URLs for ``CLAUDE_CODE_CUSTOM_OAUTH_URL`` override.

Only FedStart/PubSec deployments are permitted to prevent OAuth tokens
from being sent to arbitrary endpoints.
"""

# ============================================================================
# OAuth Config
# ============================================================================

OauthConfigType = Literal["prod", "staging", "local"]


@dataclass(frozen=True)
class OauthConfig:
    """OAuth configuration for a specific environment."""

    base_api_url: str
    console_authorize_url: str
    claude_ai_authorize_url: str
    claude_ai_origin: str
    """The claude.ai web origin (separate from authorize URL)."""
    token_url: str
    api_key_url: str
    roles_url: str
    console_success_url: str
    claudeai_success_url: str
    manual_redirect_url: str
    client_id: str
    oauth_file_suffix: str
    mcp_proxy_url: str
    mcp_proxy_path: str


# Production OAuth configuration
_PROD_OAUTH_CONFIG = OauthConfig(
    base_api_url="https://api.anthropic.com",
    console_authorize_url="https://platform.claude.com/oauth/authorize",
    claude_ai_authorize_url="https://claude.com/cai/oauth/authorize",
    claude_ai_origin="https://claude.ai",
    token_url="https://platform.claude.com/v1/oauth/token",
    api_key_url="https://api.anthropic.com/api/oauth/claude_cli/create_api_key",
    roles_url="https://api.anthropic.com/api/oauth/claude_cli/roles",
    console_success_url="https://platform.claude.com/buy_credits?returnUrl=/oauth/code/success%3Fapp%3Dclaude-code",
    claudeai_success_url="https://platform.claude.com/oauth/code/success?app=claude-code",
    manual_redirect_url="https://platform.claude.com/oauth/code/callback",
    client_id="9d1c250a-e61b-44d9-88ed-5944d1962f5e",
    oauth_file_suffix="",
    mcp_proxy_url="https://mcp-proxy.anthropic.com",
    mcp_proxy_path="/v1/mcp/{server_id}",
)

# Staging OAuth configuration
_STAGING_OAUTH_CONFIG = OauthConfig(
    base_api_url="https://api-staging.anthropic.com",
    console_authorize_url="https://platform.staging.ant.dev/oauth/authorize",
    claude_ai_authorize_url="https://claude-ai.staging.ant.dev/oauth/authorize",
    claude_ai_origin="https://claude-ai.staging.ant.dev",
    token_url="https://platform.staging.ant.dev/v1/oauth/token",
    api_key_url="https://api-staging.anthropic.com/api/oauth/claude_cli/create_api_key",
    roles_url="https://api-staging.anthropic.com/api/oauth/claude_cli/roles",
    console_success_url="https://platform.staging.ant.dev/buy_credits?returnUrl=/oauth/code/success%3Fapp%3Dclaude-code",
    claudeai_success_url="https://platform.staging.ant.dev/oauth/code/success?app=claude-code",
    manual_redirect_url="https://platform.staging.ant.dev/oauth/code/callback",
    client_id="22422756-60c9-4084-8eb7-27705fd5cf9a",
    oauth_file_suffix="-staging-oauth",
    mcp_proxy_url="https://mcp-proxy-staging.anthropic.com",
    mcp_proxy_path="/v1/mcp/{server_id}",
)


def _is_env_truthy(value: str | None) -> bool:
    """Check if an env var value is truthy."""
    if value is None:
        return False
    return value.lower() in ("1", "true", "yes")


def _get_oauth_config_type() -> OauthConfigType:
    """Determine OAuth config type based on environment."""
    if os.environ.get("USER_TYPE") == "ant":
        if _is_env_truthy(os.environ.get("USE_LOCAL_OAUTH")):
            return "local"
        if _is_env_truthy(os.environ.get("USE_STAGING_OAUTH")):
            return "staging"
    return "prod"


def _get_local_oauth_config() -> OauthConfig:
    """Build local-dev OAuth configuration from environment."""
    api = (os.environ.get("CLAUDE_LOCAL_OAUTH_API_BASE", "http://localhost:8000")
           .rstrip("/"))
    apps = (os.environ.get("CLAUDE_LOCAL_OAUTH_APPS_BASE", "http://localhost:4000")
            .rstrip("/"))
    console_base = (os.environ.get("CLAUDE_LOCAL_OAUTH_CONSOLE_BASE", "http://localhost:3000")
                    .rstrip("/"))

    return OauthConfig(
        base_api_url=api,
        console_authorize_url=f"{console_base}/oauth/authorize",
        claude_ai_authorize_url=f"{apps}/oauth/authorize",
        claude_ai_origin=apps,
        token_url=f"{api}/v1/oauth/token",
        api_key_url=f"{api}/api/oauth/claude_cli/create_api_key",
        roles_url=f"{api}/api/oauth/claude_cli/roles",
        console_success_url=f"{console_base}/buy_credits?returnUrl=/oauth/code/success%3Fapp%3Dclaude-code",
        claudeai_success_url=f"{console_base}/oauth/code/success?app=claude-code",
        manual_redirect_url=f"{console_base}/oauth/code/callback",
        client_id="22422756-60c9-4084-8eb7-27705fd5cf9a",
        oauth_file_suffix="-local-oauth",
        mcp_proxy_url="http://localhost:8205",
        mcp_proxy_path="/v1/toolbox/shttp/mcp/{server_id}",
    )


def file_suffix_for_oauth_config() -> str:
    """Get the file suffix for the current OAuth configuration."""
    if os.environ.get("CLAUDE_CODE_CUSTOM_OAUTH_URL"):
        return "-custom-oauth"

    config_type = _get_oauth_config_type()
    if config_type == "local":
        return "-local-oauth"
    elif config_type == "staging":
        return "-staging-oauth"
    return ""


def get_oauth_config() -> OauthConfig:
    """Get the OAuth configuration for the current environment.

    Applies custom OAuth URL overrides and client ID overrides from
    environment variables.
    """
    config_type = _get_oauth_config_type()

    if config_type == "local":
        config = _get_local_oauth_config()
    elif config_type == "staging":
        config = _STAGING_OAUTH_CONFIG
    else:
        config = _PROD_OAUTH_CONFIG

    # Allow overriding all OAuth URLs to point to an approved FedStart deployment.
    oauth_base_url = os.environ.get("CLAUDE_CODE_CUSTOM_OAUTH_URL")
    if oauth_base_url:
        base = oauth_base_url.rstrip("/")
        if base not in ALLOWED_OAUTH_BASE_URLS:
            raise ValueError(
                "CLAUDE_CODE_CUSTOM_OAUTH_URL is not an approved endpoint."
            )
        config = OauthConfig(
            base_api_url=base,
            console_authorize_url=f"{base}/oauth/authorize",
            claude_ai_authorize_url=f"{base}/oauth/authorize",
            claude_ai_origin=base,
            token_url=f"{base}/v1/oauth/token",
            api_key_url=f"{base}/api/oauth/claude_cli/create_api_key",
            roles_url=f"{base}/api/oauth/claude_cli/roles",
            console_success_url=f"{base}/oauth/code/success?app=claude-code",
            claudeai_success_url=f"{base}/oauth/code/success?app=claude-code",
            manual_redirect_url=f"{base}/oauth/code/callback",
            client_id=config.client_id,
            oauth_file_suffix="-custom-oauth",
            mcp_proxy_url=config.mcp_proxy_url,
            mcp_proxy_path=config.mcp_proxy_path,
        )

    # Allow CLIENT_ID override via environment variable
    client_id_override = os.environ.get("CLAUDE_CODE_OAUTH_CLIENT_ID")
    if client_id_override:
        config = OauthConfig(
            base_api_url=config.base_api_url,
            console_authorize_url=config.console_authorize_url,
            claude_ai_authorize_url=config.claude_ai_authorize_url,
            claude_ai_origin=config.claude_ai_origin,
            token_url=config.token_url,
            api_key_url=config.api_key_url,
            roles_url=config.roles_url,
            console_success_url=config.console_success_url,
            claudeai_success_url=config.claudeai_success_url,
            manual_redirect_url=config.manual_redirect_url,
            client_id=client_id_override,
            oauth_file_suffix=config.oauth_file_suffix,
            mcp_proxy_url=config.mcp_proxy_url,
            mcp_proxy_path=config.mcp_proxy_path,
        )

    return config
