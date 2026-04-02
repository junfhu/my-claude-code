"""SSH tunnel support for remote Claude Code sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class SSHTunnel:
    """Manages an SSH tunnel for remote development.

    Creates a reverse tunnel from a remote host to the local Claude Code
    server, enabling IDE integration over SSH.
    """

    def __init__(
        self,
        host: str,
        *,
        user: Optional[str] = None,
        port: int = 22,
        local_port: int = 7862,
        remote_port: int = 7862,
        identity_file: Optional[str] = None,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.local_port = local_port
        self.remote_port = remote_port
        self.identity_file = identity_file
        self._process: Optional[asyncio.subprocess.Process] = None

    def _build_command(self) -> list[str]:
        cmd = ["ssh", "-N", "-T"]
        if self.user:
            cmd.extend(["-l", self.user])
        cmd.extend(["-p", str(self.port)])
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
        cmd.extend([
            "-R", f"{self.remote_port}:127.0.0.1:{self.local_port}",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            self.host,
        ])
        return cmd

    async def start(self) -> None:
        cmd = self._build_command()
        logger.info("Starting SSH tunnel: %s", " ".join(cmd))
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

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


def check_ssh_agent() -> bool:
    """Check if an SSH agent is running with available keys."""
    try:
        result = subprocess.run(
            ["ssh-add", "-l"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False
