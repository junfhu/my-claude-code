"""
Session initialization (setup).

Performs all first-run checks and environment preparation before the
interactive conversation loop starts.  Analogous to the TypeScript
``setup()`` function.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_PYTHON_VERSION = (3, 10)
MIN_RECOMMENDED_PYTHON_VERSION = (3, 11)
CLAUDE_CONFIG_DIR = Path.home() / ".claude"
CLAUDE_DATA_DIR = CLAUDE_CONFIG_DIR


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SetupResult:
    """Result of the setup phase."""

    success: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cwd: str = ""
    session_id: str = ""
    config_dir: str = ""
    elapsed_ms: float = 0.0


@dataclass
class EnvironmentInfo:
    """Captured information about the runtime environment."""

    python_version: str = ""
    platform: str = ""
    arch: str = ""
    os_name: str = ""
    shell: str = ""
    term: str = ""
    cwd: str = ""
    home: str = ""
    user: str = ""
    is_ci: bool = False
    is_docker: bool = False
    is_ssh: bool = False
    is_wsl: bool = False
    git_available: bool = False
    git_version: str = ""


# ---------------------------------------------------------------------------
# Main setup function
# ---------------------------------------------------------------------------


async def setup(
    *,
    cwd: Optional[str] = None,
    skip_version_check: bool = False,
    skip_git_check: bool = False,
    session_id: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> SetupResult:
    """Run the full session initialization sequence.

    Phases:
    1. Python version check
    2. Configuration directory setup
    3. Working directory validation
    4. Git availability check
    5. Permission validation
    6. Analytics opt-in check
    7. Session directory creation
    """
    start_time = time.time()
    result = SetupResult(success=True)
    result.config_dir = str(config_dir or CLAUDE_CONFIG_DIR)

    # ---- Phase 1: Python version check ----
    if not skip_version_check:
        ver_result = _check_python_version()
        if ver_result.get("error"):
            result.errors.append(ver_result["error"])
            result.success = False
            return result
        if ver_result.get("warning"):
            result.warnings.append(ver_result["warning"])

    # ---- Phase 2: Config directory setup ----
    try:
        _ensure_config_dirs(result.config_dir)
    except OSError as exc:
        result.errors.append(f"Cannot create config directory: {exc}")
        result.success = False
        return result

    # ---- Phase 3: Working directory ----
    resolved_cwd = _resolve_cwd(cwd)
    if resolved_cwd is None:
        result.errors.append(
            f"Working directory does not exist or is not accessible: {cwd or os.getcwd()}"
        )
        result.success = False
        return result
    result.cwd = resolved_cwd

    # ---- Phase 4: Git check ----
    if not skip_git_check:
        git_result = await _check_git()
        if not git_result["available"]:
            result.warnings.append(
                "git is not available on PATH. Some features will be limited."
            )

    # ---- Phase 5: Permission validation ----
    perm_warnings = _validate_permissions(resolved_cwd)
    result.warnings.extend(perm_warnings)

    # ---- Phase 6: Analytics opt-in ----
    _ensure_analytics_config(result.config_dir)

    # ---- Phase 7: Session directory ----
    if session_id:
        result.session_id = session_id
    else:
        import uuid

        result.session_id = str(uuid.uuid4())

    session_dir = Path(result.config_dir) / "sessions" / result.session_id
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.warnings.append(f"Cannot create session directory: {exc}")

    result.elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        "Setup completed in %.1fms cwd=%s session=%s warnings=%d",
        result.elapsed_ms,
        result.cwd,
        result.session_id,
        len(result.warnings),
    )
    return result


def get_environment_info() -> EnvironmentInfo:
    """Capture the runtime environment information."""
    info = EnvironmentInfo()
    info.python_version = platform.python_version()
    info.platform = platform.system()
    info.arch = platform.machine()
    info.os_name = os.name
    info.shell = os.environ.get("SHELL", "")
    info.term = os.environ.get("TERM", "")
    info.cwd = os.getcwd()
    info.home = str(Path.home())
    info.user = os.environ.get("USER", os.environ.get("USERNAME", ""))

    # Detect CI
    ci_vars = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "CIRCLECI", "TRAVIS")
    info.is_ci = any(os.environ.get(v) for v in ci_vars)

    # Detect Docker
    info.is_docker = (
        os.path.exists("/.dockerenv")
        or os.path.exists("/run/.containerenv")
        or _is_in_cgroup_docker()
    )

    # Detect SSH
    info.is_ssh = bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))

    # Detect WSL
    info.is_wsl = "microsoft" in platform.uname().release.lower()

    # Git
    git_path = shutil.which("git")
    info.git_available = git_path is not None
    if info.git_available:
        try:
            import subprocess

            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            info.git_version = result.stdout.strip()
        except Exception:
            info.git_version = "unknown"

    return info


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------


def _check_python_version() -> Dict[str, Optional[str]]:
    """Check the running Python version."""
    current = sys.version_info[:2]

    if current < REQUIRED_PYTHON_VERSION:
        return {
            "error": (
                f"Python {REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}+ is required, "
                f"but you are running Python {current[0]}.{current[1]}."
            ),
            "warning": None,
        }

    if current < MIN_RECOMMENDED_PYTHON_VERSION:
        return {
            "error": None,
            "warning": (
                f"Python {MIN_RECOMMENDED_PYTHON_VERSION[0]}.{MIN_RECOMMENDED_PYTHON_VERSION[1]}+ "
                f"is recommended for best performance. "
                f"You are running Python {current[0]}.{current[1]}."
            ),
        }

    return {"error": None, "warning": None}


def _ensure_config_dirs(config_dir: str) -> None:
    """Create the configuration directory tree."""
    base = Path(config_dir)
    dirs = [
        base,
        base / "sessions",
        base / "history",
        base / "costs",
        base / "logs",
        base / "memory",
        base / "settings",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _resolve_cwd(cwd: Optional[str]) -> Optional[str]:
    """Resolve and validate the working directory.

    Returns the resolved absolute path, or None if invalid.
    """
    if cwd:
        p = Path(cwd).resolve()
    else:
        try:
            p = Path.cwd().resolve()
        except OSError:
            return None

    if p.is_dir() and os.access(str(p), os.R_OK):
        return str(p)
    return None


async def _check_git() -> Dict[str, Any]:
    """Check whether git is available."""
    git_path = shutil.which("git")
    if git_path is None:
        return {"available": False, "version": None, "path": None}

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        version = stdout.decode().strip() if stdout else "unknown"
        return {"available": True, "version": version, "path": git_path}
    except (asyncio.TimeoutError, OSError):
        return {"available": False, "version": None, "path": git_path}


def _validate_permissions(cwd: str) -> List[str]:
    """Validate that we have sensible permissions in the working directory."""
    warnings: List[str] = []
    p = Path(cwd)

    if not os.access(str(p), os.W_OK):
        warnings.append(
            f"Working directory {cwd} is not writable. File operations may fail."
        )

    # Check if we're running as root (potential danger)
    if os.getuid() == 0 if hasattr(os, "getuid") else False:
        warnings.append(
            "Running as root. Be cautious with file and command operations."
        )

    # Check if the directory appears to be a system directory
    system_prefixes = ("/usr", "/bin", "/sbin", "/etc", "/var", "/boot", "/proc", "/sys")
    if any(str(p).startswith(prefix) for prefix in system_prefixes):
        warnings.append(
            f"Working directory {cwd} appears to be a system directory. "
            "Proceeding with caution."
        )

    return warnings


def _ensure_analytics_config(config_dir: str) -> None:
    """Ensure analytics config exists (default: enabled)."""
    config_path = Path(config_dir) / "settings" / "analytics.json"
    if config_path.exists():
        return

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        config_path.write_text(
            json.dumps({"enabled": True, "created_at": time.time()}, indent=2)
        )
    except OSError:
        pass


def _is_in_cgroup_docker() -> bool:
    """Check /proc/1/cgroup for docker indicators."""
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
        return "docker" in content or "containerd" in content
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Quick one-shot check for CI / headless usage
# ---------------------------------------------------------------------------


def quick_environment_check() -> Dict[str, Any]:
    """Perform a fast environment check without async or I/O-heavy operations."""
    info = get_environment_info()
    return {
        "python_ok": sys.version_info[:2] >= REQUIRED_PYTHON_VERSION,
        "python_version": info.python_version,
        "platform": info.platform,
        "is_ci": info.is_ci,
        "is_docker": info.is_docker,
        "git_available": info.git_available,
        "config_dir_exists": CLAUDE_CONFIG_DIR.exists(),
    }
