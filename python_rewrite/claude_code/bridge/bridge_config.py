"""
Bridge configuration.

Resolves bridge configuration from CLI flags, environment variables,
and git repository metadata.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import uuid
from typing import Optional

from .types import BridgeConfig, BridgeWorkerType, SpawnMode

logger = logging.getLogger(__name__)

DEFAULT_MAX_SESSIONS = 1
DEFAULT_API_BASE_URL = "https://api.anthropic.com"
DEFAULT_SESSION_INGRESS_URL = "https://api.anthropic.com"


def _get_machine_name() -> str:
    """Best-effort machine name for bridge registration."""
    return os.environ.get("CLAUDE_MACHINE_NAME", platform.node() or "unknown")


def _get_git_branch(cwd: str) -> str:
    """Current git branch in *cwd*, or ``'unknown'``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _get_git_repo_url(cwd: str) -> Optional[str]:
    """Remote origin URL of the git repo, or ``None``."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        url = result.stdout.strip()
        return url or None
    except Exception:
        return None


def create_bridge_config(
    *,
    dir: Optional[str] = None,
    max_sessions: Optional[int] = None,
    spawn_mode: Optional[str] = None,
    verbose: bool = False,
    sandbox: bool = False,
    worker_type: Optional[str] = None,
    api_base_url: Optional[str] = None,
    session_ingress_url: Optional[str] = None,
    reuse_environment_id: Optional[str] = None,
    debug_file: Optional[str] = None,
    session_timeout_ms: Optional[int] = None,
) -> BridgeConfig:
    """Build a ``BridgeConfig`` from CLI flags and environment."""
    work_dir = dir or os.getcwd()
    api_url = api_base_url or os.environ.get("CLAUDE_API_BASE_URL", DEFAULT_API_BASE_URL)
    ingress_url = session_ingress_url or os.environ.get(
        "CLAUDE_SESSION_INGRESS_URL", api_url
    )

    mode = SpawnMode.SINGLE_SESSION
    if spawn_mode:
        try:
            mode = SpawnMode(spawn_mode)
        except ValueError:
            logger.warning("Unknown spawn mode %r, using single-session", spawn_mode)

    return BridgeConfig(
        dir=work_dir,
        machine_name=_get_machine_name(),
        branch=_get_git_branch(work_dir),
        git_repo_url=_get_git_repo_url(work_dir),
        max_sessions=max_sessions or int(os.environ.get("CLAUDE_MAX_SESSIONS", DEFAULT_MAX_SESSIONS)),
        spawn_mode=mode,
        verbose=verbose,
        sandbox=sandbox,
        bridge_id=str(uuid.uuid4()),
        worker_type=worker_type or BridgeWorkerType.CLAUDE_CODE.value,
        environment_id=str(uuid.uuid4()),
        api_base_url=api_url,
        session_ingress_url=ingress_url,
        reuse_environment_id=reuse_environment_id,
        debug_file=debug_file,
        session_timeout_ms=session_timeout_ms,
    )
