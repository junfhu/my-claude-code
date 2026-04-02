"""
Event metadata enrichment.

Enriches analytics events with contextual metadata such as environment
information, git state, session details, and timing data.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metadata types
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentMetadata:
    """Metadata about the runtime environment."""

    python_version: str = ""
    os_name: str = ""
    os_version: str = ""
    arch: str = ""
    is_ci: bool = False
    is_docker: bool = False
    is_ssh: bool = False
    terminal: str = ""
    shell: str = ""
    locale: str = ""


@dataclass
class SessionMetadata:
    """Metadata about the current session."""

    session_id: str = ""
    started_at: float = 0.0
    model: str = ""
    provider: str = ""
    permission_mode: str = ""
    cwd: str = ""
    cwd_hash: str = ""  # Anonymized path hash
    is_git_repo: bool = False
    git_remote_hash: str = ""  # Anonymized remote URL hash
    tool_count: int = 0


@dataclass
class EventMetadata:
    """Full metadata for an analytics event."""

    environment: EnvironmentMetadata = field(default_factory=EnvironmentMetadata)
    session: SessionMetadata = field(default_factory=SessionMetadata)
    timing: Dict[str, float] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


_cached_env_metadata: Optional[EnvironmentMetadata] = None


def get_environment_metadata() -> EnvironmentMetadata:
    """Get environment metadata (cached after first call)."""
    global _cached_env_metadata
    if _cached_env_metadata is not None:
        return _cached_env_metadata

    meta = EnvironmentMetadata()
    meta.python_version = platform.python_version()
    meta.os_name = platform.system()
    meta.os_version = platform.release()
    meta.arch = platform.machine()
    meta.terminal = os.environ.get("TERM", "")
    meta.shell = os.environ.get("SHELL", "")
    meta.locale = os.environ.get("LANG", "")

    ci_vars = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL")
    meta.is_ci = any(os.environ.get(v) for v in ci_vars)
    meta.is_docker = os.path.exists("/.dockerenv")
    meta.is_ssh = bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))

    _cached_env_metadata = meta
    return meta


def build_session_metadata(
    *,
    session_id: str = "",
    started_at: float = 0.0,
    model: str = "",
    provider: str = "",
    permission_mode: str = "",
    cwd: str = "",
    tool_count: int = 0,
) -> SessionMetadata:
    """Build session metadata with anonymized fields."""
    meta = SessionMetadata()
    meta.session_id = session_id
    meta.started_at = started_at
    meta.model = model
    meta.provider = provider
    meta.permission_mode = permission_mode
    meta.cwd = cwd
    meta.cwd_hash = _hash_string(cwd) if cwd else ""
    meta.tool_count = tool_count

    # Check for git repo
    meta.is_git_repo = _is_git_repo(cwd)
    if meta.is_git_repo:
        remote = _get_git_remote(cwd)
        meta.git_remote_hash = _hash_string(remote) if remote else ""

    return meta


def enrich_event(
    event_properties: Dict[str, Any],
    *,
    session_id: str = "",
    model: str = "",
    cwd: str = "",
) -> Dict[str, Any]:
    """Add standard metadata to event properties.

    Returns the enriched properties dict (mutates in place).
    """
    env = get_environment_metadata()

    event_properties.setdefault("_metadata", {})
    meta = event_properties["_metadata"]

    # Environment (lightweight)
    meta["os"] = env.os_name
    meta["arch"] = env.arch
    meta["python"] = env.python_version
    meta["is_ci"] = env.is_ci

    # Session context
    if session_id:
        meta["session_id"] = session_id
    if model:
        meta["model"] = model
    if cwd:
        meta["cwd_hash"] = _hash_string(cwd)

    # Timing
    meta["event_time"] = time.time()

    return event_properties


def build_api_call_metadata(
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: float = 0.0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    stop_reason: Optional[str] = None,
    error: Optional[str] = None,
    tool_count: int = 0,
) -> Dict[str, Any]:
    """Build metadata dict for an API call event."""
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": round(latency_ms, 1),
        "stop_reason": stop_reason,
        "error": error,
        "tool_count": tool_count,
    }


def build_tool_use_metadata(
    *,
    tool_name: str,
    duration_ms: float = 0.0,
    success: bool = True,
    error: Optional[str] = None,
    input_size: int = 0,
    output_size: int = 0,
) -> Dict[str, Any]:
    """Build metadata dict for a tool use event."""
    return {
        "tool_name": tool_name,
        "duration_ms": round(duration_ms, 1),
        "success": success,
        "error": error,
        "input_size": input_size,
        "output_size": output_size,
    }


def build_session_event_metadata(
    *,
    event: str,  # "start" | "end" | "error" | "compact"
    session_id: str,
    model: str = "",
    turn_count: int = 0,
    total_cost_usd: float = 0.0,
    total_tokens: int = 0,
    duration_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Build metadata dict for a session lifecycle event."""
    return {
        "event": event,
        "session_id": session_id,
        "model": model,
        "turn_count": turn_count,
        "total_cost_usd": round(total_cost_usd, 6),
        "total_tokens": total_tokens,
        "duration_seconds": round(duration_seconds, 1),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_string(s: str) -> str:
    """Hash a string for anonymization (SHA-256, first 12 chars)."""
    if not s:
        return ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _is_git_repo(cwd: str) -> bool:
    """Check if a directory is inside a git repository."""
    if not cwd:
        return False
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _get_git_remote(cwd: str) -> str:
    """Get the git remote origin URL."""
    if not cwd:
        return ""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except (OSError, subprocess.TimeoutExpired):
        return ""
