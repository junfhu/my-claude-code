"""
Remote agent task — delegates work to a remote Claude Code session via the API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

import httpx

from .task import TaskContext, TaskHandle, TaskStatus, TaskType, generate_task_id

logger = logging.getLogger(__name__)

REMOTE_TIMEOUT_S = 600.0
POLL_INTERVAL_S = 2.0


async def create_remote_agent_task(
    prompt: str,
    context: TaskContext,
    *,
    label: Optional[str] = None,
    api_base_url: Optional[str] = None,
    access_token: Optional[str] = None,
    model: Optional[str] = None,
) -> TaskHandle:
    """Create a remote agent task that delegates to a cloud-hosted Claude Code session.

    Uses the session-ingress API to create a session, send the prompt,
    and poll for results.
    """
    task_id = generate_task_id()
    handle = TaskHandle(
        task_id=task_id,
        task_type=TaskType.REMOTE_AGENT,
        label=label or prompt[:50],
    )

    base_url = (api_base_url or context.env.get("CLAUDE_API_BASE_URL", "https://api.anthropic.com")).rstrip("/")
    token = access_token or context.env.get("CLAUDE_CODE_ACCESS_TOKEN", "")

    if not token:
        handle.mark_failed("No access token for remote agent")
        return handle

    handle.mark_running()

    async def _run() -> None:
        try:
            async with httpx.AsyncClient(timeout=REMOTE_TIMEOUT_S) as client:
                # Create session
                create_resp = await client.post(
                    f"{base_url}/v1/sessions",
                    json={
                        "prompt": prompt,
                        "model": model,
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                create_resp.raise_for_status()
                session_data = create_resp.json()
                session_id = session_data.get("session_id", session_data.get("id"))

                if not session_id:
                    handle.mark_failed("No session_id in response")
                    return

                # Poll for completion
                deadline = time.time() + REMOTE_TIMEOUT_S
                while time.time() < deadline:
                    await asyncio.sleep(POLL_INTERVAL_S)
                    status_resp = await client.get(
                        f"{base_url}/v1/sessions/{session_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if status_resp.status_code == 404:
                        handle.mark_failed("Session not found")
                        return
                    status_resp.raise_for_status()
                    status_data = status_resp.json()

                    state = status_data.get("status", status_data.get("state", ""))
                    if state in ("completed", "done"):
                        output = status_data.get("output", status_data.get("result", ""))
                        if isinstance(output, dict):
                            output = json.dumps(output, indent=2)
                        handle.mark_completed(output=str(output))
                        return
                    if state in ("failed", "error"):
                        error = status_data.get("error", "Remote agent failed")
                        handle.mark_failed(str(error))
                        return
                    if state == "cancelled":
                        handle.mark_cancelled()
                        return

                handle.mark_failed("Remote agent timed out")

        except httpx.HTTPStatusError as exc:
            handle.mark_failed(f"HTTP {exc.response.status_code}: {exc.response.text[:200]}")
        except Exception as exc:
            handle.mark_failed(str(exc))

    def _kill() -> None:
        handle.mark_cancelled()

    handle._kill_fn = _kill
    asyncio.create_task(_run())
    return handle
