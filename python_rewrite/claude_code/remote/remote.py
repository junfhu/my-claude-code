"""Remote execution support — run Claude Code on remote machines."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RemoteSession:
    """Manages a remote Claude Code session over SSH."""

    def __init__(
        self,
        host: str,
        *,
        user: Optional[str] = None,
        work_dir: Optional[str] = None,
        port: int = 22,
    ) -> None:
        self.host = host
        self.user = user
        self.work_dir = work_dir or "~"
        self.port = port
        self._process: Optional[asyncio.subprocess.Process] = None

    async def start(self, prompt: Optional[str] = None) -> None:
        """Start a Claude Code session on the remote host."""
        ssh_target = f"{self.user}@{self.host}" if self.user else self.host
        remote_cmd = f"cd {self.work_dir} && claude"
        if prompt:
            remote_cmd += f" --print '{prompt}'"

        self._process = await asyncio.create_subprocess_exec(
            "ssh", "-p", str(self.port), "-t", ssh_target, remote_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def send_input(self, text: str) -> None:
        if self._process and self._process.stdin:
            self._process.stdin.write(text.encode())
            await self._process.stdin.drain()

    async def read_output(self) -> str:
        if self._process and self._process.stdout:
            data = await self._process.stdout.read(4096)
            return data.decode("utf-8", errors="replace")
        return ""

    async def stop(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
        self._process = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def wait(self) -> int:
        if self._process:
            return await self._process.wait()
        return -1


async def check_remote_claude(
    host: str,
    user: Optional[str] = None,
    port: int = 22,
) -> bool:
    """Check if Claude Code is installed on a remote host."""
    ssh_target = f"{user}@{host}" if user else host
    proc = await asyncio.create_subprocess_exec(
        "ssh", "-p", str(port), ssh_target, "which claude || which python3 -m claude_code",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return proc.returncode == 0
