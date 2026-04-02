"""
Bridge type definitions.

Mirrors src/bridge/types.ts — protocol types for the environments API,
session management, and bridge configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Optional, Protocol

DEFAULT_SESSION_TIMEOUT_MS = 24 * 60 * 60 * 1000  # 24 hours

BRIDGE_LOGIN_INSTRUCTION = (
    "Remote Control is only available with claude.ai subscriptions. "
    "Please use `/login` to sign in with your claude.ai account."
)

BRIDGE_LOGIN_ERROR = (
    "Error: You must be logged in to use Remote Control.\n\n"
    + BRIDGE_LOGIN_INSTRUCTION
)

REMOTE_CONTROL_DISCONNECTED_MSG = "Remote Control disconnected."


class SpawnMode(str, Enum):
    """How bridge chooses session working directories."""
    SINGLE_SESSION = "single-session"
    WORKTREE = "worktree"
    SAME_DIR = "same-dir"


class BridgeWorkerType(str, Enum):
    CLAUDE_CODE = "claude_code"
    CLAUDE_CODE_ASSISTANT = "claude_code_assistant"


class SessionDoneStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class SessionActivityType(str, Enum):
    TOOL_START = "tool_start"
    TEXT = "text"
    RESULT = "result"
    ERROR = "error"


@dataclass
class SessionActivity:
    """A snapshot of what a session is doing."""
    type: SessionActivityType
    summary: str
    timestamp: float


@dataclass
class WorkData:
    type: Literal["session", "healthcheck"]
    id: str


@dataclass
class WorkResponse:
    id: str
    type: str
    environment_id: str
    state: str
    data: WorkData
    secret: str
    created_at: str


@dataclass
class WorkSecret:
    version: int
    session_ingress_token: str
    api_base_url: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    auth: list[dict[str, str]] = field(default_factory=list)
    claude_code_args: Optional[dict[str, str]] = None
    mcp_config: Any = None
    environment_variables: Optional[dict[str, str]] = None
    use_code_sessions: Optional[bool] = None


@dataclass
class BridgeConfig:
    """Configuration for a bridge instance."""
    dir: str
    machine_name: str
    branch: str
    git_repo_url: Optional[str]
    max_sessions: int
    spawn_mode: SpawnMode
    verbose: bool
    sandbox: bool
    bridge_id: str
    worker_type: str
    environment_id: str
    api_base_url: str
    session_ingress_url: str
    reuse_environment_id: Optional[str] = None
    debug_file: Optional[str] = None
    session_timeout_ms: Optional[int] = None


@dataclass
class PermissionResponseEvent:
    type: str = "control_response"
    response: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSpawnOpts:
    session_id: str
    sdk_url: str
    access_token: str
    use_ccr_v2: bool = False
    worker_epoch: Optional[int] = None
    on_first_user_message: Optional[Callable[[str], None]] = None


@dataclass
class SessionHandle:
    """Handle to a running session."""
    session_id: str
    access_token: str
    activities: list[SessionActivity] = field(default_factory=list)
    current_activity: Optional[SessionActivity] = None
    last_stderr: list[str] = field(default_factory=list)
    _done_future: Optional[Any] = field(default=None, repr=False)
    _kill_fn: Optional[Callable[[], None]] = field(default=None, repr=False)
    _force_kill_fn: Optional[Callable[[], None]] = field(default=None, repr=False)
    _write_stdin_fn: Optional[Callable[[str], None]] = field(default=None, repr=False)

    def kill(self) -> None:
        if self._kill_fn:
            self._kill_fn()

    def force_kill(self) -> None:
        if self._force_kill_fn:
            self._force_kill_fn()

    def write_stdin(self, data: str) -> None:
        if self._write_stdin_fn:
            self._write_stdin_fn(data)

    def update_access_token(self, token: str) -> None:
        self.access_token = token


class BridgeApiClient(Protocol):
    """Interface for the bridge environments API."""

    async def register_bridge_environment(
        self, config: BridgeConfig
    ) -> dict[str, str]: ...

    async def poll_for_work(
        self,
        environment_id: str,
        environment_secret: str,
        signal: Any = None,
        reclaim_older_than_ms: Optional[int] = None,
    ) -> Optional[WorkResponse]: ...

    async def acknowledge_work(
        self, environment_id: str, work_id: str, session_token: str
    ) -> None: ...

    async def stop_work(
        self, environment_id: str, work_id: str, force: bool
    ) -> None: ...

    async def deregister_environment(self, environment_id: str) -> None: ...

    async def send_permission_response_event(
        self, session_id: str, event: PermissionResponseEvent, session_token: str
    ) -> None: ...

    async def archive_session(self, session_id: str) -> None: ...

    async def reconnect_session(
        self, environment_id: str, session_id: str
    ) -> None: ...

    async def heartbeat_work(
        self, environment_id: str, work_id: str, session_token: str
    ) -> dict[str, Any]: ...
