"""
Local shell task implementation.

Spawns a shell command as a child process and tracks its lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Optional

from .task import TaskContext, TaskHandle, TaskStatus, TaskType, generate_task_id

logger = logging.getLogger(__name__)

MAX_OUTPUT_SIZE = 1_000_000  # 1MB


async def create_local_shell_task(
    command: str,
    context: TaskContext,
    *,
    label: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> TaskHandle:
    """Spawn a shell command as a background task."""
    task_id = generate_task_id()
    handle = TaskHandle(
        task_id=task_id,
        task_type=TaskType.LOCAL_SHELL,
        label=label or command[:50],
    )

    env = {**os.environ, **context.env}
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=context.cwd,
        env=env,
    )

    def _kill() -> None:
        try:
            if process.returncode is None:
                process.terminate()
        except ProcessLookupError:
            pass

    handle._kill_fn = _kill
    handle.mark_running()

    async def _monitor() -> None:
        output_parts: list[str] = []
        total_size = 0

        try:
            effective_timeout = (timeout_ms or context.timeout_ms or 300_000) / 1000.0

            async def _read_output() -> None:
                nonlocal total_size
                assert process.stdout is not None
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    if total_size < MAX_OUTPUT_SIZE:
                        output_parts.append(text)
                        total_size += len(text)

            await asyncio.wait_for(_read_output(), timeout=effective_timeout)
            exit_code = await asyncio.wait_for(process.wait(), timeout=10)

            output = "".join(output_parts)
            if exit_code == 0:
                handle.mark_completed(output=output, exit_code=exit_code)
            else:
                handle.mark_failed(f"Exit code {exit_code}\n{output[-500:]}")
                handle.exit_code = exit_code

        except asyncio.TimeoutError:
            _kill()
            handle.mark_failed("Task timed out")
        except Exception as exc:
            handle.mark_failed(str(exc))

    asyncio.create_task(_monitor())
    return handle


def kill_shell_tasks(task_handles: list[TaskHandle]) -> int:
    """Kill multiple shell tasks. Returns count killed."""
    count = 0
    for handle in task_handles:
        if handle.is_running and handle.task_type == TaskType.LOCAL_SHELL:
            handle.kill()
            handle.mark_cancelled()
            count += 1
    return count
