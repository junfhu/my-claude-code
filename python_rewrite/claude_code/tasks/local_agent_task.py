"""
Local agent task — spawns a Claude Code sub-agent process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional

from .task import TaskContext, TaskHandle, TaskStatus, TaskType, generate_task_id

logger = logging.getLogger(__name__)


async def create_local_agent_task(
    prompt: str,
    context: TaskContext,
    *,
    label: Optional[str] = None,
    model: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
    system_prompt_extra: Optional[str] = None,
) -> TaskHandle:
    """Spawn a Claude Code sub-agent as a child process.

    The sub-agent runs with ``--print`` mode and returns structured output.
    """
    task_id = generate_task_id()
    handle = TaskHandle(
        task_id=task_id,
        task_type=TaskType.LOCAL_AGENT,
        label=label or prompt[:50],
    )

    cmd = [sys.executable, "-m", "claude_code", "--print"]
    env = {**os.environ, **context.env, "CLAUDE_CODE_TASK_ID": task_id}

    if model:
        cmd.extend(["--model", model])

    if allowed_tools:
        for tool in allowed_tools:
            cmd.extend(["--allowedTools", tool])

    # Pass prompt via stdin
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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
        try:
            full_prompt = prompt
            if system_prompt_extra:
                full_prompt = f"{system_prompt_extra}\n\n{prompt}"

            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(input=full_prompt.encode()),
                timeout=(context.timeout_ms or 600_000) / 1000.0,
            )

            output = stdout_data.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            if exit_code == 0:
                handle.mark_completed(output=output, exit_code=exit_code)
            else:
                stderr = stderr_data.decode("utf-8", errors="replace")
                handle.mark_failed(
                    f"Agent exited with code {exit_code}\n{stderr[-500:]}"
                )
                handle.exit_code = exit_code

        except asyncio.TimeoutError:
            _kill()
            handle.mark_failed("Agent task timed out")
        except Exception as exc:
            handle.mark_failed(str(exc))

    asyncio.create_task(_monitor())
    return handle
