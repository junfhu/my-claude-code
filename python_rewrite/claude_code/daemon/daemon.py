"""Background daemon process for Claude Code."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

PID_FILE = "claude_daemon.pid"


def _get_pid_path() -> str:
    config_dir = os.environ.get(
        "CLAUDE_CONFIG_DIR",
        os.path.join(os.path.expanduser("~"), ".claude"),
    )
    return os.path.join(config_dir, PID_FILE)


def is_daemon_running() -> bool:
    """Check if the daemon is currently running."""
    pid_path = _get_pid_path()
    try:
        with open(pid_path) as f:
            pid = int(f.read().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


def get_daemon_pid() -> Optional[int]:
    """Get the PID of the running daemon."""
    pid_path = _get_pid_path()
    try:
        with open(pid_path) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def start_daemon() -> int:
    """Start the daemon process. Returns the PID."""
    if is_daemon_running():
        pid = get_daemon_pid()
        logger.info("Daemon already running (PID %s)", pid)
        return pid or 0

    # Fork to background
    if os.name != "nt":
        pid = os.fork()
        if pid > 0:
            # Parent: write PID and return
            _write_pid(pid)
            return pid
        # Child: create new session
        os.setsid()
        # Fork again to prevent zombie
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)
    else:
        # Windows: use subprocess
        import subprocess
        proc = subprocess.Popen(
            [sys.executable, "-m", "claude_code.daemon.daemon", "--run"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _write_pid(proc.pid)
        return proc.pid

    # We're now the daemon process
    _write_pid(os.getpid())
    _run_daemon()
    return os.getpid()


def stop_daemon() -> bool:
    """Stop the daemon process."""
    pid = get_daemon_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for exit
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        _remove_pid()
        return True
    except (ProcessLookupError, PermissionError):
        _remove_pid()
        return False


def _write_pid(pid: int) -> None:
    pid_path = _get_pid_path()
    os.makedirs(os.path.dirname(pid_path), exist_ok=True)
    with open(pid_path, "w") as f:
        f.write(str(pid))


def _remove_pid() -> None:
    try:
        os.unlink(_get_pid_path())
    except OSError:
        pass


def _run_daemon() -> None:
    """Main daemon loop."""
    logger.info("Daemon started (PID %d)", os.getpid())

    running = True

    def _handle_signal(sig: int, frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Redirect stdio
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    sys.stderr = devnull

    try:
        while running:
            time.sleep(1)
            # Daemon tasks: file watching, MCP server health checks, etc.
    except Exception:
        pass
    finally:
        _remove_pid()
        devnull.close()
