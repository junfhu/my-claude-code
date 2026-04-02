"""
Main bridge entry point for IDE integration and remote control.

Orchestrates environment registration, work polling, session spawning,
and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from typing import Any, Optional

from .bridge_api import BridgeAPIClient
from .bridge_config import create_bridge_config
from .bridge_messaging import BridgeMessaging
from .session_runner import SessionRunner
from .types import (
    BridgeConfig,
    SessionDoneStatus,
    SessionSpawnOpts,
    WorkResponse,
    WorkSecret,
)

logger = logging.getLogger(__name__)

RECONNECT_DELAYS = [1, 2, 4, 8, 16, 30]  # seconds


class BridgeMain:
    """Main bridge orchestrator.

    Lifecycle:
    1. Register environment with the API
    2. Poll for work items (sessions)
    3. Spawn Claude Code processes for each work item
    4. Monitor sessions and report activity
    5. Graceful shutdown on SIGINT/SIGTERM
    """

    def __init__(self, config: BridgeConfig, auth_token: str) -> None:
        self.config = config
        self._api = BridgeAPIClient(config.api_base_url, auth_token)
        self._runner = SessionRunner(sandbox=config.sandbox)
        self._messaging: Optional[BridgeMessaging] = None
        self._environment_id: Optional[str] = None
        self._environment_secret: Optional[str] = None
        self._running = False
        self._reconnect_count = 0

    async def start(self) -> None:
        """Register and start the polling loop."""
        self._running = True
        self._setup_signal_handlers()

        # Register environment
        try:
            result = await self._api.register_bridge_environment(self.config)
            self._environment_id = result["environment_id"]
            self._environment_secret = result["environment_secret"]
            logger.info(
                "Registered environment %s (bridge %s)",
                self._environment_id, self.config.bridge_id,
            )
        except Exception as exc:
            logger.error("Failed to register environment: %s", exc)
            raise

        # Start messaging
        self._messaging = BridgeMessaging(
            config=self.config,
            environment_secret=self._environment_secret,
        )
        await self._messaging.start()

        # Main loop
        try:
            await self._poll_loop()
        finally:
            await self._shutdown()

    async def _poll_loop(self) -> None:
        """Continuously poll for work and spawn sessions."""
        while self._running:
            try:
                work = await self._api.poll_for_work(
                    self._environment_id,
                    self._environment_secret,
                )
                if work:
                    self._reconnect_count = 0
                    await self._handle_work(work)
                else:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Poll error: %s", exc)
                delay = RECONNECT_DELAYS[
                    min(self._reconnect_count, len(RECONNECT_DELAYS) - 1)
                ]
                self._reconnect_count += 1
                logger.info("Reconnecting in %ds…", delay)
                await asyncio.sleep(delay)

    async def _handle_work(self, work: WorkResponse) -> None:
        """Process a work item by spawning a session."""
        secret = BridgeMessaging.decode_secret(work.secret)

        active_count = len(self._runner.active_sessions)
        if active_count >= self.config.max_sessions:
            logger.warning(
                "At session limit (%d/%d), cannot spawn for work %s",
                active_count, self.config.max_sessions, work.id,
            )
            return

        # Determine working directory
        work_dir = self.config.dir

        opts = SessionSpawnOpts(
            session_id=work.data.id if hasattr(work.data, "id") else work.id,
            sdk_url=f"{self.config.session_ingress_url}/v1/sessions",
            access_token=secret.session_ingress_token,
            use_ccr_v2=secret.use_code_sessions or False,
        )

        try:
            handle = self._runner.spawn(opts, work_dir)
            logger.info("Spawned session %s", opts.session_id)

            # Acknowledge the work
            await self._api.acknowledge_work(
                self._environment_id, work.id, secret.session_ingress_token
            )

            # Start heartbeat
            if self._messaging:
                await self._messaging.start_heartbeat(
                    work.id, secret.session_ingress_token
                )
        except Exception as exc:
            logger.error("Failed to spawn session for work %s: %s", work.id, exc)

    async def _shutdown(self) -> None:
        """Graceful shutdown: kill sessions, deregister environment."""
        logger.info("Shutting down bridge …")
        self._running = False

        # Kill all sessions
        await self._runner.kill_all()

        # Stop messaging
        if self._messaging:
            await self._messaging.stop()

        # Deregister environment
        if self._environment_id:
            try:
                await self._api.deregister_environment(self._environment_id)
                logger.info("Deregistered environment %s", self._environment_id)
            except Exception as exc:
                logger.debug("Failed to deregister: %s", exc)

        await self._api.close()

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal)

    def _handle_signal(self) -> None:
        logger.info("Received shutdown signal")
        self._running = False


async def run_bridge(
    *,
    auth_token: str,
    dir: Optional[str] = None,
    max_sessions: Optional[int] = None,
    spawn_mode: Optional[str] = None,
    verbose: bool = False,
    sandbox: bool = False,
    api_base_url: Optional[str] = None,
    session_ingress_url: Optional[str] = None,
) -> None:
    """Top-level entry point for ``claude remote-control``."""
    config = create_bridge_config(
        dir=dir,
        max_sessions=max_sessions,
        spawn_mode=spawn_mode,
        verbose=verbose,
        sandbox=sandbox,
        api_base_url=api_base_url,
        session_ingress_url=session_ingress_url,
    )
    bridge = BridgeMain(config, auth_token)
    await bridge.start()
