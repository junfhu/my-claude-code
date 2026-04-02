"""
Product URLs, environment detection, and session URL helpers.
"""

from __future__ import annotations

__all__ = [
    "PRODUCT_URL",
    "CLAUDE_AI_BASE_URL",
    "CLAUDE_AI_STAGING_BASE_URL",
    "CLAUDE_AI_LOCAL_BASE_URL",
    "is_remote_session_staging",
    "is_remote_session_local",
    "get_claude_ai_base_url",
    "get_remote_session_url",
]

# ============================================================================
# Base URLs
# ============================================================================

PRODUCT_URL: str = "https://claude.com/claude-code"

CLAUDE_AI_BASE_URL: str = "https://claude.ai"
CLAUDE_AI_STAGING_BASE_URL: str = "https://claude-ai.staging.ant.dev"
CLAUDE_AI_LOCAL_BASE_URL: str = "http://localhost:4000"

# ============================================================================
# Environment detection helpers
# ============================================================================


def is_remote_session_staging(
    session_id: str | None = None,
    ingress_url: str | None = None,
) -> bool:
    """Check if we're in a staging environment for remote sessions."""
    return (session_id is not None and "_staging_" in session_id) or (
        ingress_url is not None and "staging" in ingress_url
    )


def is_remote_session_local(
    session_id: str | None = None,
    ingress_url: str | None = None,
) -> bool:
    """Check if we're in a local-dev environment for remote sessions."""
    return (session_id is not None and "_local_" in session_id) or (
        ingress_url is not None and "localhost" in ingress_url
    )


def get_claude_ai_base_url(
    session_id: str | None = None,
    ingress_url: str | None = None,
) -> str:
    """Get the base URL for Claude AI based on environment."""
    if is_remote_session_local(session_id, ingress_url):
        return CLAUDE_AI_LOCAL_BASE_URL
    if is_remote_session_staging(session_id, ingress_url):
        return CLAUDE_AI_STAGING_BASE_URL
    return CLAUDE_AI_BASE_URL


def get_remote_session_url(
    session_id: str,
    ingress_url: str | None = None,
) -> str:
    """Get the full session URL for a remote session.

    Translates ``cse_`` → ``session_`` prefix for frontend compatibility.
    """
    # Compatibility shim: worker endpoints want `cse_*` but the frontend
    # currently routes on `session_*`.
    compat_id = session_id
    if compat_id.startswith("cse_"):
        compat_id = "session_" + compat_id[4:]

    base_url = get_claude_ai_base_url(compat_id, ingress_url)
    return f"{base_url}/code/{compat_id}"
