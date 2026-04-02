"""
Bridge session runner — spawns and manages Claude Code sessions for bridge work items.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Any, Callable, Optional

from .types import (
    SessionActivity,
    SessionActivityType,
    SessionDoneStatus,
    SessionHandle,
    SessionSpawnOpts,
)

logger = logging.getLogger(__name__)

MAX_STDERR_LINES = 50
MAX_ACTIVITIES = 10


class SessionRunner:
    """Spawns Claude Code child processes for bridge sessions."""

    def __init__(self, *, sandbox: bool = False) -> None:
        self._sandbox = sandbox
        self._active: dict[str, SessionHandle] = {}

    @property
    def active_sessions(self) -> dict[str, SessionHandle]:
        return dict(self._active)

    def spawn(self, opts: SessionSpawnOpts, work_dir: str) -> SessionHandle:
        """Spawn a new Claude Code session as a child process."""
        env = {
            **os.environ,
            "CLAUDE_CODE_SESSION_ID": opts.session_id,
            "CLAUDE_CODE_SDK_URL": opts.sdk_url,
            "CLAUDE_CODE_ACCESS_TOKEN": opts.access_token,
        }
        if opts.use_ccr_v2:
            env["CLAUDE_CODE_CCR_V2"] = "1"
            if opts.worker_epoch is not None:
                env["CLAUDE_CODE_WORKER_EPOCH"] = str(opts.worker_epoch)

        cmd = [sys.executable, "-m", "claude_code", "--session-mode", "bridge"]
        if self._sandbox:
            env["CLAUDE_CODE_SANDBOX"] = "1"

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=work_dir,
            env=env,
        )

        handle = SessionHandle(
            session_id=opts.session_id,
            access_token=opts.access_token,
            _kill_fn=lambda: process.terminate(),
            _force_kill_fn=lambda: process.kill(),
            _write_stdin_fn=lambda data: (
                process.stdin.write(data.encode()) if process.stdin else None,
                process.stdin.flush() if process.stdin else None,
            ),
        )
        self._active[opts.session_id] = handle

        # Monitor process in background
        asyncio.get_event_loop().create_task(
            self._monitor(process, handle, opts)
        )
        return handle

    async def _monitor(
        self,
        process: subprocess.Popen[bytes],
        handle: SessionHandle,
        opts: SessionSpawnOpts,
    ) -> None:
        """Monitor child process stdout/stderr and update handle."""
        loop = asyncio.get_event_loop()

        async def _read_stderr() -> None:
            if process.stderr is None:
                return
            while True:
                line = await loop.run_in_executor(None, process.stderr.readline)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                handle.last_stderr.append(text)
                if len(handle.last_stderr) > MAX_STDERR_LINES:
                    handle.last_stderr = handle.last_stderr[-MAX_STDERR_LINES:]

        async def _read_stdout() -> None:
            if process.stdout is None:
                return
            first_user_msg_seen = False
            while True:
                line = await loop.run_in_executor(None, process.stdout.readline)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()

                # Parse activity updates from stdout
                if text.startswith('{"activity":'):
                    try:
                        data = __import__("json").loads(text)
                        act = data.get("activity", {})
                        activity = SessionActivity(
                            type=SessionActivityType(act.get("type", "text")),
                            summary=act.get("summary", ""),
                            timestamp=act.get("timestamp", time.time()),
                        )
                        handle.current_activity = activity
                        handle.activities.append(activity)
                        if len(handle.activities) > MAX_ACTIVITIES:
                            handle.activities = handle.activities[-MAX_ACTIVITIES:]
                    except Exception:
                        pass
                elif not first_user_msg_seen and opts.on_first_user_message:
                    first_user_msg_seen = True
                    opts.on_first_user_message(text)

        await asyncio.gather(
            _read_stdout(),
            _read_stderr(),
        )

        # Wait for process exit
        exit_code = await loop.run_in_executor(None, process.wait)
        self._active.pop(opts.session_id, None)

        logger.info(
            "Session %s exited with code %d",
            opts.session_id, exit_code,
        )

    def kill_session(self, session_id: str, *, force: bool = False) -> bool:
        """Kill a running session. Returns True if found."""
        handle = self._active.get(session_id)
        if handle is None:
            return False
        if force:
            handle.force_kill()
        else:
            handle.kill()
        return True

    async def kill_all(self) -> None:
        """Kill all active sessions."""
        for handle in list(self._active.values()):
            handle.kill()
        # Give processes time to exit
        await asyncio.sleep(1)
        for handle in list(self._active.values()):
            handle.force_kill()
        self._active.clear()
