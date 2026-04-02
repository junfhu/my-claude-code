"""
Bidirectional bridge messaging.

Handles inbound messages from the environments API (work items, control messages)
and outbound messages (session activity, status updates, permission responses).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

from .types import (
    BridgeConfig,
    PermissionResponseEvent,
    SessionActivity,
    SessionActivityType,
    WorkResponse,
    WorkSecret,
)
from .jwt_utils import decode_work_secret

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 30.0
HEARTBEAT_INTERVAL_S = 30.0


@dataclass
class BridgeMessaging:
    """Bidirectional messaging channel between the bridge and the environments API."""

    config: BridgeConfig
    environment_secret: str
    _http: Optional[httpx.AsyncClient] = field(default=None, repr=False)
    _polling: bool = False
    _on_work: Optional[Callable[[WorkResponse], Any]] = None
    _heartbeat_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict, repr=False)

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=POLL_TIMEOUT_S)
        self._polling = True

    async def stop(self) -> None:
        self._polling = False
        for task in self._heartbeat_tasks.values():
            task.cancel()
        self._heartbeat_tasks.clear()
        if self._http:
            await self._http.aclose()
            self._http = None

    def on_work(self, callback: Callable[[WorkResponse], Any]) -> None:
        self._on_work = callback

    # -- Polling loop --------------------------------------------------------

    async def poll_loop(self) -> None:
        """Continuously poll for work items from the environments API."""
        while self._polling:
            try:
                work = await self._poll_once()
                if work and self._on_work:
                    await self._on_work(work)
            except asyncio.CancelledError:
                break
            except httpx.HTTPError as exc:
                logger.warning("Poll error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL_S * 2)
            except Exception as exc:
                logger.error("Unexpected poll error: %s", exc)
                await asyncio.sleep(POLL_INTERVAL_S * 2)

            await asyncio.sleep(POLL_INTERVAL_S)

    async def _poll_once(self) -> Optional[WorkResponse]:
        if not self._http:
            return None
        url = (
            f"{self.config.api_base_url}/v1/environments/"
            f"{self.config.environment_id}/work"
        )
        headers = {"Authorization": f"Bearer {self.environment_secret}"}
        resp = await self._http.get(url, headers=headers)
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        data = resp.json()
        return WorkResponse(
            id=data["id"],
            type=data["type"],
            environment_id=data["environment_id"],
            state=data["state"],
            data=data["data"],
            secret=data["secret"],
            created_at=data["created_at"],
        )

    # -- Acknowledge work ----------------------------------------------------

    async def acknowledge_work(self, work_id: str, session_token: str) -> None:
        if not self._http:
            return
        url = (
            f"{self.config.api_base_url}/v1/environments/"
            f"{self.config.environment_id}/work/{work_id}/acknowledge"
        )
        resp = await self._http.post(
            url,
            headers={"Authorization": f"Bearer {session_token}"},
        )
        resp.raise_for_status()

    # -- Session activity ----------------------------------------------------

    async def send_session_activity(
        self,
        session_id: str,
        activity: SessionActivity,
        session_token: str,
    ) -> None:
        """Report session activity (what tool is running, etc.)."""
        if not self._http:
            return
        url = (
            f"{self.config.session_ingress_url}/v1/sessions/"
            f"{session_id}/activity"
        )
        await self._http.post(
            url,
            json={
                "type": activity.type.value,
                "summary": activity.summary,
                "timestamp": activity.timestamp,
            },
            headers={"Authorization": f"Bearer {session_token}"},
        )

    # -- Permission responses ------------------------------------------------

    async def send_permission_response(
        self,
        session_id: str,
        event: PermissionResponseEvent,
        session_token: str,
    ) -> None:
        if not self._http:
            return
        url = (
            f"{self.config.session_ingress_url}/v1/sessions/"
            f"{session_id}/events"
        )
        await self._http.post(
            url,
            json={"type": event.type, "response": event.response},
            headers={"Authorization": f"Bearer {session_token}"},
        )

    # -- Heartbeat -----------------------------------------------------------

    async def start_heartbeat(self, work_id: str, session_token: str) -> None:
        """Start a background heartbeat for a work item."""
        async def _heartbeat() -> None:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                try:
                    if not self._http:
                        break
                    url = (
                        f"{self.config.api_base_url}/v1/environments/"
                        f"{self.config.environment_id}/work/{work_id}/heartbeat"
                    )
                    resp = await self._http.post(
                        url,
                        headers={"Authorization": f"Bearer {session_token}"},
                    )
                    data = resp.json()
                    if not data.get("lease_extended", True):
                        logger.warning("Heartbeat: lease not extended for %s", work_id)
                        break
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.debug("Heartbeat error for %s: %s", work_id, exc)

        task = asyncio.create_task(_heartbeat())
        self._heartbeat_tasks[work_id] = task

    def stop_heartbeat(self, work_id: str) -> None:
        task = self._heartbeat_tasks.pop(work_id, None)
        if task:
            task.cancel()

    # -- Work secret decoding ------------------------------------------------

    @staticmethod
    def decode_secret(secret_b64: str) -> WorkSecret:
        raw = decode_work_secret(secret_b64)
        return WorkSecret(
            version=raw.get("version", 1),
            session_ingress_token=raw["session_ingress_token"],
            api_base_url=raw["api_base_url"],
            sources=raw.get("sources", []),
            auth=raw.get("auth", []),
            claude_code_args=raw.get("claude_code_args"),
            mcp_config=raw.get("mcp_config"),
            environment_variables=raw.get("environment_variables"),
            use_code_sessions=raw.get("use_code_sessions"),
        )
