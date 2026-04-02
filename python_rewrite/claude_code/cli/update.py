"""CLI update checking and self-update mechanism."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

VERSION = "0.1.0"  # Placeholder; overridden at build time
PACKAGE_NAME = "claude-code"


async def check_for_update(channel: str = "latest") -> Optional[str]:
    """Check PyPI (or configured registry) for the latest version.

    Returns the latest version string, or None if the check fails.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://pypi.org/pypi/{PACKAGE_NAME}/json")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("info", {}).get("version")
    except Exception as exc:
        logger.debug("Update check failed: %s", exc)
    return None


def get_current_version() -> str:
    """Return the currently installed version."""
    try:
        from importlib.metadata import version

        return version("claude_code")
    except Exception:
        return VERSION


def compare_versions(current: str, latest: str) -> bool:
    """Return True if ``latest`` is newer than ``current``."""
    from packaging.version import Version

    try:
        return Version(latest) > Version(current)
    except Exception:
        # Fallback to string comparison
        return latest != current


async def update(*, channel: str = "latest") -> None:
    """Run the update flow — check for a new version, and install if available."""
    current = get_current_version()
    print(f"Current version: {current}")
    print(f"Checking for updates ({channel})...")

    latest = await check_for_update(channel)
    if not latest:
        print("Failed to check for updates.", file=sys.stderr)
        print("Possible causes:", file=sys.stderr)
        print("  • Network connectivity issues", file=sys.stderr)
        print("  • PyPI registry unreachable", file=sys.stderr)
        sys.exit(1)

    if not compare_versions(current, latest):
        print(f"Claude Code is up to date ({current})")
        return

    print(f"New version available: {latest} (current: {current})")
    print("Installing update...")

    status = install_update(latest)
    if status == "success":
        print(f"Successfully updated from {current} to {latest}")
    elif status == "no_permissions":
        print("Error: Insufficient permissions to install update", file=sys.stderr)
        print("Try: pip install --user --upgrade claude-code", file=sys.stderr)
        sys.exit(1)
    elif status == "install_failed":
        print("Error: Failed to install update", file=sys.stderr)
        print("Try: pip install --upgrade claude-code", file=sys.stderr)
        sys.exit(1)


def install_update(version: str) -> str:
    """Install a specific version of claude-code.

    Returns: 'success', 'no_permissions', or 'install_failed'.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", f"{PACKAGE_NAME}=={version}"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return "success"
        if "Permission denied" in result.stderr or "EPERM" in result.stderr:
            return "no_permissions"
        logger.error("pip install failed: %s", result.stderr)
        return "install_failed"
    except subprocess.TimeoutExpired:
        return "install_failed"
    except Exception as exc:
        logger.error("Update failed: %s", exc)
        return "install_failed"


def detect_installation_type() -> str:
    """Detect how claude-code was installed.

    Returns one of: 'pip', 'pipx', 'uv', 'development', 'unknown'.
    """
    # Check if running from a development install (editable mode)
    try:
        from importlib.metadata import packages_distributions

        dists = packages_distributions()
        if "claude_code" in dists:
            # Check for editable install markers
            import claude_code

            pkg_path = os.path.dirname(claude_code.__file__)
            if ".egg-link" in pkg_path or "site-packages" not in pkg_path:
                return "development"
    except Exception:
        pass

    # Check for pipx
    if "pipx" in sys.executable:
        return "pipx"

    # Check for uv
    if "uv" in os.environ.get("VIRTUAL_ENV", ""):
        return "uv"

    return "pip"
