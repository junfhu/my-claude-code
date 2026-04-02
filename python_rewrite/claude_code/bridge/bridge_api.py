"""
Bridge API client implementation.

HTTP client for the environments API — register, poll, ack, stop, heartbeat.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .types import (
    BridgeConfig,
    PermissionResponseEvent,
    WorkResponse,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 30.0


class BridgeAPIClient:
    """HTTP client for the bridge environments API."""

    def __init__(self, api_base_url: str, auth_token: str) -> None:
        self._base = api_base_url.rstrip("/")
        self._auth_token = auth_token
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)
        return self._client

    def _headers(self, token: Optional[str] = None) -> dict[str, str]:
        t = token or self._auth_token
        return {
            "Authorization": f"Bearer {t}",
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- Registration --------------------------------------------------------

    async def register_bridge_environment(
        self, config: BridgeConfig
    ) -> dict[str, str]:
        """Register a new bridge environment. Returns ``{environment_id, environment_secret}``."""
        client = await self._ensure_client()
        body: dict[str, Any] = {
            "bridge_id": config.bridge_id,
            "machine_name": config.machine_name,
            "branch": config.branch,
            "max_sessions": config.max_sessions,
            "spawn_mode": config.spawn_mode.value,
            "worker_type": config.worker_type,
        }
        if config.git_repo_url:
            body["git_repo_url"] = config.git_repo_url
        if config.reuse_environment_id:
            body["reuse_environment_id"] = config.reuse_environment_id

        resp = await client.post(
            f"{self._base}/v1/environments",
            json=body,
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "environment_id": data["environment_id"],
            "environment_secret": data["environment_secret"],
        }

    # -- Work polling --------------------------------------------------------

    async def poll_for_work(
        self,
        environment_id: str,
        environment_secret: str,
        reclaim_older_than_ms: Optional[int] = None,
    ) -> Optional[WorkResponse]:
        """Long-poll for a work item."""
        client = await self._ensure_client()
        params: dict[str, Any] = {}
        if reclaim_older_than_ms is not None:
            params["reclaim_older_than_ms"] = reclaim_older_than_ms

        resp = await client.get(
            f"{self._base}/v1/environments/{environment_id}/work",
            params=params,
            headers=self._headers(environment_secret),
        )
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        d = resp.json()
        return WorkResponse(
            id=d["id"],
            type=d["type"],
            environment_id=d["environment_id"],
            state=d["state"],
            data=d["data"],
            secret=d["secret"],
            created_at=d["created_at"],
        )

    # -- Acknowledge ---------------------------------------------------------

    async def acknowledge_work(
        self, environment_id: str, work_id: str, session_token: str
    ) -> None:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/environments/{environment_id}/work/{work_id}/acknowledge",
            headers=self._headers(session_token),
        )
        resp.raise_for_status()

    # -- Stop ----------------------------------------------------------------

    async def stop_work(
        self, environment_id: str, work_id: str, force: bool
    ) -> None:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/environments/{environment_id}/work/{work_id}/stop",
            json={"force": force},
            headers=self._headers(),
        )
        resp.raise_for_status()

    # -- Deregister ----------------------------------------------------------

    async def deregister_environment(self, environment_id: str) -> None:
        client = await self._ensure_client()
        resp = await client.delete(
            f"{self._base}/v1/environments/{environment_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()

    # -- Permission response -------------------------------------------------

    async def send_permission_response_event(
        self,
        session_id: str,
        event: PermissionResponseEvent,
        session_token: str,
    ) -> None:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/sessions/{session_id}/events",
            json={"type": event.type, "response": event.response},
            headers=self._headers(session_token),
        )
        resp.raise_for_status()

    # -- Archive / reconnect -------------------------------------------------

    async def archive_session(self, session_id: str) -> None:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/sessions/{session_id}/archive",
            headers=self._headers(),
        )
        resp.raise_for_status()

    async def reconnect_session(
        self, environment_id: str, session_id: str
    ) -> None:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/environments/{environment_id}/sessions/{session_id}/reconnect",
            headers=self._headers(),
        )
        resp.raise_for_status()

    # -- Heartbeat -----------------------------------------------------------

    async def heartbeat_work(
        self,
        environment_id: str,
        work_id: str,
        session_token: str,
    ) -> dict[str, Any]:
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._base}/v1/environments/{environment_id}/work/{work_id}/heartbeat",
            headers=self._headers(session_token),
        )
        resp.raise_for_status()
        return resp.json()
