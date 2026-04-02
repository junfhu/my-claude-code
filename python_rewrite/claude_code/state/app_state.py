"""
Application state type definitions and default factory.

This module defines the shape of the entire application state tree (AppState),
supporting types (CompletionBoundary, SpeculationState, etc.), and a factory
function (get_default_app_state) that produces the initial state.  It does NOT
create the store itself -- that happens via ``create_store()`` at bootstrap.

The AppState dataclass uses ``frozen=False`` so that state updates can be
performed via ``dataclasses.replace(state, field=new_value)`` which produces
a *new* instance, preserving immutable-update semantics at the application
layer while keeping the dataclass mutable at the Python level.

Key architectural decisions:
    1. Single atom -- all UI-relevant state lives in one object so that
       selectors can derive cross-cutting concerns without prop-drilling.
    2. Flat defaults -- ``get_default_app_state()`` returns a fully-initialised
       instance so consumers never need null-checks for top-level properties.
    3. Escape hatches -- fields containing mutable containers (dicts of tasks,
       maps, sets) are typed explicitly and documented.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Optional

from .store import Store

# ---------------------------------------------------------------------------
# Permission mode -- mirrors PermissionMode from TypeScript
# ---------------------------------------------------------------------------

class PermissionMode(str, Enum):
    """Permission mode for tool execution."""
    DEFAULT = "default"
    PLAN = "plan"
    AUTO = "auto"
    BYPASS = "bypass"
    # Internal-only modes
    BUBBLE = "bubble"
    UNGATED_AUTO = "ungated_auto"


def to_external_permission_mode(mode: PermissionMode) -> str:
    """Convert internal permission modes to external-facing names.

    Internal modes like BUBBLE and UNGATED_AUTO map to their external
    equivalents for CCR metadata and SDK status streams.
    """
    mapping: dict[PermissionMode, str] = {
        PermissionMode.BUBBLE: "default",
        PermissionMode.UNGATED_AUTO: "auto",
    }
    return mapping.get(mode, mode.value)


# ---------------------------------------------------------------------------
# ToolPermissionContext
# ---------------------------------------------------------------------------

@dataclass
class ToolPermissionContext:
    """Current permission mode and related context.

    This is the single source of truth for whether tools require approval.
    """
    mode: PermissionMode = PermissionMode.DEFAULT
    # Tool-specific permission overrides (tool_name -> allow/deny)
    tool_overrides: dict[str, bool] = field(default_factory=dict)
    # Session-scoped allowed prompts from plan mode exit
    allowed_prompts: list[dict[str, Any]] = field(default_factory=list)


def get_empty_tool_permission_context() -> ToolPermissionContext:
    """Return a fresh ToolPermissionContext with default values."""
    return ToolPermissionContext()


# ---------------------------------------------------------------------------
# CompletionBoundary -- marks the logical boundary of a completed AI turn
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompletionBoundaryComplete:
    type: Literal["complete"] = "complete"
    completed_at: float = 0.0
    output_tokens: int = 0


@dataclass(frozen=True)
class CompletionBoundaryBash:
    type: Literal["bash"] = "bash"
    command: str = ""
    completed_at: float = 0.0


@dataclass(frozen=True)
class CompletionBoundaryEdit:
    type: Literal["edit"] = "edit"
    tool_name: str = ""
    file_path: str = ""
    completed_at: float = 0.0


@dataclass(frozen=True)
class CompletionBoundaryDenied:
    type: Literal["denied_tool"] = "denied_tool"
    tool_name: str = ""
    detail: str = ""
    completed_at: float = 0.0


CompletionBoundary = (
    CompletionBoundaryComplete
    | CompletionBoundaryBash
    | CompletionBoundaryEdit
    | CompletionBoundaryDenied
)


# ---------------------------------------------------------------------------
# SpeculationState -- tracks the lifecycle of speculative execution
# ---------------------------------------------------------------------------

@dataclass
class SpeculationIdle:
    """No speculation in flight."""
    status: Literal["idle"] = "idle"


@dataclass
class SpeculationActive:
    """A speculative execution is running."""
    status: Literal["active"] = "active"
    id: str = ""
    abort: Callable[[], None] = field(default=lambda: None)
    start_time: float = 0.0
    messages_ref: list[Any] = field(default_factory=list)
    written_paths_ref: set[str] = field(default_factory=set)
    boundary: CompletionBoundary | None = None
    suggestion_length: int = 0
    tool_use_count: int = 0
    is_pipelined: bool = False
    pipelined_suggestion: dict[str, Any] | None = None


SpeculationState = SpeculationIdle | SpeculationActive

# Singleton idle state -- reused as the default to avoid allocating a new
# object every time speculation ends.
IDLE_SPECULATION_STATE: SpeculationState = SpeculationIdle()


# ---------------------------------------------------------------------------
# SpeculationResult
# ---------------------------------------------------------------------------

@dataclass
class SpeculationResult:
    """Output of a completed speculative execution."""
    messages: list[Any] = field(default_factory=list)
    boundary: CompletionBoundary | None = None
    time_saved_ms: float = 0.0


# ---------------------------------------------------------------------------
# FooterItem
# ---------------------------------------------------------------------------

FooterItem = Literal["tasks", "tmux", "bagel", "teams", "bridge", "companion"]

# ---------------------------------------------------------------------------
# ExpandedView
# ---------------------------------------------------------------------------

ExpandedView = Literal["none", "tasks", "teammates"]

# ---------------------------------------------------------------------------
# ViewSelectionMode
# ---------------------------------------------------------------------------

ViewSelectionMode = Literal["none", "selecting-agent", "viewing-agent"]

# ---------------------------------------------------------------------------
# RemoteConnectionStatus
# ---------------------------------------------------------------------------

RemoteConnectionStatus = Literal[
    "connecting", "connected", "reconnecting", "disconnected"
]


# ---------------------------------------------------------------------------
# Supporting sub-state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MCPState:
    """MCP (Model Context Protocol) integration state."""
    clients: list[Any] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)
    commands: list[Any] = field(default_factory=list)
    resources: dict[str, list[Any]] = field(default_factory=dict)
    plugin_reconnect_key: int = 0


@dataclass
class PluginInstallationStatus:
    """Installation status for background plugin/marketplace installation."""
    marketplaces: list[dict[str, Any]] = field(default_factory=list)
    plugins: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PluginsState:
    """Plugin system state."""
    enabled: list[Any] = field(default_factory=list)
    disabled: list[Any] = field(default_factory=list)
    commands: list[Any] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    installation_status: PluginInstallationStatus = field(
        default_factory=PluginInstallationStatus
    )
    needs_refresh: bool = False


@dataclass
class NotificationState:
    """Toast-style notifications with a current display slot and a FIFO queue."""
    current: Any | None = None
    queue: list[Any] = field(default_factory=list)


@dataclass
class ElicitationState:
    """Queue of pending elicitation requests from MCP servers."""
    queue: list[Any] = field(default_factory=list)


@dataclass
class InboxMessage:
    """A message in the inter-agent inbox."""
    id: str = ""
    from_agent: str = ""
    text: str = ""
    timestamp: str = ""
    status: Literal["pending", "processing", "processed"] = "pending"
    color: str | None = None
    summary: str | None = None


@dataclass
class InboxState:
    """Inter-agent messaging inbox."""
    messages: list[InboxMessage] = field(default_factory=list)


@dataclass
class WorkerSandboxPermissionRequest:
    """A sandbox permission request."""
    request_id: str = ""
    worker_id: str = ""
    worker_name: str = ""
    worker_color: str | None = None
    host: str = ""
    created_at: float = 0.0


@dataclass
class WorkerSandboxPermissions:
    """Worker sandbox permission requests (leader side)."""
    queue: list[WorkerSandboxPermissionRequest] = field(default_factory=list)
    selected_index: int = 0


@dataclass
class PromptSuggestionState:
    """Auto-generated prompt suggestion shown to the user before they type."""
    text: str | None = None
    prompt_id: Literal["user_intent", "stated_intent"] | None = None
    shown_at: float = 0.0
    accepted_at: float = 0.0
    generation_request_id: str | None = None


@dataclass
class SkillImprovementState:
    """Pending skill improvement suggestion from the model."""
    suggestion: dict[str, Any] | None = None


@dataclass
class FileHistoryState:
    """Snapshot-based file history for undo/restore operations."""
    snapshots: list[Any] = field(default_factory=list)
    tracked_files: set[str] = field(default_factory=set)
    snapshot_sequence: int = 0


@dataclass
class AttributionState:
    """Commit attribution tracking -- maps file edits to the agent/tool."""
    attributed_files: dict[str, Any] = field(default_factory=dict)


@dataclass
class PendingWorkerRequest:
    """Pending permission request on worker side."""
    tool_name: str = ""
    tool_use_id: str = ""
    description: str = ""


@dataclass
class PendingSandboxRequest:
    """Pending sandbox permission request on worker side."""
    request_id: str = ""
    host: str = ""


@dataclass
class TeamContext:
    """Multi-agent team (swarm) context."""
    team_name: str = ""
    team_file_path: str = ""
    lead_agent_id: str = ""
    self_agent_id: str | None = None
    self_agent_name: str | None = None
    is_leader: bool | None = None
    self_agent_color: str | None = None
    teammates: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class TungstenActiveSession:
    """Active tmux session details."""
    session_name: str = ""
    socket_name: str = ""
    target: str = ""


@dataclass
class TungstenLastCommand:
    """Last tmux command info."""
    command: str = ""
    timestamp: float = 0.0


@dataclass
class StandaloneAgentContext:
    """Standalone agent context for non-swarm sessions with custom name/color."""
    name: str = ""
    color: str | None = None


@dataclass
class ComputerUseMcpState:
    """Computer use MCP session state (chicago)."""
    allowed_apps: list[dict[str, Any]] = field(default_factory=list)
    grant_flags: dict[str, bool] = field(default_factory=dict)
    last_screenshot_dims: dict[str, Any] | None = None
    hidden_during_turn: set[str] = field(default_factory=set)
    selected_display_id: int | None = None
    display_pinned_by_model: bool = False
    display_resolved_for_apps: str | None = None


@dataclass
class UltraplanPendingChoice:
    """Approved ultraplan awaiting user choice."""
    plan: str = ""
    session_id: str = ""
    task_id: str = ""


@dataclass
class UltraplanLaunchPending:
    """Pre-launch permission dialog."""
    blurb: str = ""


@dataclass
class PendingPlanVerification:
    """Pending plan verification state."""
    plan: str = ""
    verification_started: bool = False
    verification_completed: bool = False


@dataclass
class AgentDefinitionsResult:
    """Registry of available agent definitions."""
    active_agents: list[Any] = field(default_factory=list)
    all_agents: list[Any] = field(default_factory=list)


@dataclass
class InitialMessage:
    """Initial message to process (from CLI args or plan mode exit)."""
    message: Any = None
    clear_context: bool = False
    mode: PermissionMode | None = None
    allowed_prompts: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Effort value
# ---------------------------------------------------------------------------

EffortValue = Literal["low", "medium", "high"] | None

# ---------------------------------------------------------------------------
# ModelSetting -- alias for the model string (or None for default)
# ---------------------------------------------------------------------------

ModelSetting = str | None


# ---------------------------------------------------------------------------
# AppState -- The single source of truth for the entire application.
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    """Complete application state tree.

    This is the single atom of UI-relevant state.  All mutations must go
    through ``store.set_state(lambda prev: dataclasses.replace(prev, ...))``,
    which produces a new object reference and triggers the change pipeline.

    Fields are grouped logically:
        - Settings & model configuration
        - UI view state
        - Permissions
        - Agent / coordinator
        - Remote bridge
        - Remote session
        - MCP (Model Context Protocol)
        - Plugins
        - Tasks & agents
        - Speculation
        - Tmux / WebBrowser
        - Misc
    """

    # ---- Settings & model configuration ----
    settings: dict[str, Any] = field(default_factory=dict)
    verbose: bool = False
    debug: bool = False
    is_main_agent: bool = True
    main_loop_model: ModelSetting = None
    main_loop_model_for_session: ModelSetting = None
    thinking_enabled: bool | None = None
    thinking_config: dict[str, Any] | None = None
    status_line_text: str | None = None

    # ---- UI view state ----
    expanded_view: ExpandedView = "none"
    is_brief_only: bool = False
    show_teammate_message_preview: bool = False
    selected_ip_agent_index: int = -1
    coordinator_task_index: int = -1
    view_selection_mode: ViewSelectionMode = "none"
    footer_selection: FooterItem | None = None

    # ---- Tool permissions ----
    tool_permission_context: ToolPermissionContext = field(
        default_factory=get_empty_tool_permission_context
    )

    # ---- Spinner / status ----
    spinner_tip: str | None = None

    # ---- Agent ----
    agent: str | None = None
    kairos_enabled: bool = False

    # ---- Remote session ----
    remote_session_url: str | None = None
    remote_connection_status: RemoteConnectionStatus = "connecting"
    remote_background_task_count: int = 0

    # ---- Always-on bridge ----
    repl_bridge_enabled: bool = False
    repl_bridge_explicit: bool = False
    repl_bridge_outbound_only: bool = False
    repl_bridge_connected: bool = False
    repl_bridge_session_active: bool = False
    repl_bridge_reconnecting: bool = False
    repl_bridge_connect_url: str | None = None
    repl_bridge_session_url: str | None = None
    repl_bridge_environment_id: str | None = None
    repl_bridge_session_id: str | None = None
    repl_bridge_error: str | None = None
    repl_bridge_initial_name: str | None = None
    show_remote_callout: bool = False

    # ---- Messages ----
    messages: list[Any] = field(default_factory=list)
    in_progress_tool_use_ids: set[str] = field(default_factory=set)

    # ---- Conversation / session ----
    conversation_id: str | None = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query_source: str = "cli"
    is_compact_in_progress: bool = False

    # ---- Turn tracking ----
    turn_count: int = 0

    # ---- Cost tracking ----
    total_cost_usd: float = 0.0
    total_api_duration_ms: float = 0.0

    # ---- Tasks ----
    tasks: dict[str, Any] = field(default_factory=dict)
    agent_name_registry: dict[str, str] = field(default_factory=dict)
    foregrounded_task_id: str | None = None
    viewing_agent_task_id: str | None = None

    # ---- MCP ----
    mcp: MCPState = field(default_factory=MCPState)

    # ---- Plugins ----
    plugins: PluginsState = field(default_factory=PluginsState)

    # ---- Agent definitions ----
    agent_definitions: AgentDefinitionsResult = field(
        default_factory=AgentDefinitionsResult
    )

    # ---- File history & attribution ----
    file_history: FileHistoryState = field(default_factory=FileHistoryState)
    attribution: AttributionState = field(default_factory=AttributionState)

    # ---- Todo lists ----
    todos: dict[str, Any] = field(default_factory=dict)

    # ---- Remote agent suggestions ----
    remote_agent_task_suggestions: list[dict[str, str]] = field(
        default_factory=list
    )

    # ---- Notification system ----
    notifications: NotificationState = field(default_factory=NotificationState)

    # ---- MCP Elicitation ----
    elicitation: ElicitationState = field(default_factory=ElicitationState)

    # ---- Prompt suggestion ----
    prompt_suggestion_enabled: bool = False
    prompt_suggestion: PromptSuggestionState = field(
        default_factory=PromptSuggestionState
    )

    # ---- Session hooks ----
    session_hooks: dict[str, Any] = field(default_factory=dict)

    # ---- Tmux integration (tungsten) ----
    tungsten_active_session: TungstenActiveSession | None = None
    tungsten_last_captured_time: float | None = None
    tungsten_last_command: TungstenLastCommand | None = None
    tungsten_panel_visible: bool | None = None
    tungsten_panel_auto_hidden: bool | None = None

    # ---- WebBrowser tool (bagel) ----
    bagel_active: bool = False
    bagel_url: str | None = None
    bagel_panel_visible: bool = False

    # ---- Computer use MCP (chicago) ----
    computer_use_mcp_state: ComputerUseMcpState | None = None

    # ---- Inter-agent messaging (inbox) ----
    inbox: InboxState = field(default_factory=InboxState)

    # ---- Worker sandbox permissions ----
    worker_sandbox_permissions: WorkerSandboxPermissions = field(
        default_factory=WorkerSandboxPermissions
    )
    pending_worker_request: PendingWorkerRequest | None = None
    pending_sandbox_request: PendingSandboxRequest | None = None

    # ---- Speculation ----
    speculation: SpeculationState = field(
        default_factory=lambda: IDLE_SPECULATION_STATE
    )
    speculation_session_time_saved_ms: float = 0.0

    # ---- Skill improvement ----
    skill_improvement: SkillImprovementState = field(
        default_factory=SkillImprovementState
    )

    # ---- Auth ----
    auth_version: int = 0

    # ---- Initial message ----
    initial_message: InitialMessage | None = None

    # ---- Denial tracking ----
    denial_tracking: dict[str, Any] | None = None

    # ---- Active overlays ----
    active_overlays: set[str] = field(default_factory=set)

    # ---- Fast mode ----
    fast_mode: bool = False

    # ---- Advisor model ----
    advisor_model: str | None = None

    # ---- Effort ----
    effort_value: EffortValue = None

    # ---- Ultraplan ----
    ultraplan_launching: bool = False
    ultraplan_session_url: str | None = None
    ultraplan_pending_choice: UltraplanPendingChoice | None = None
    ultraplan_launch_pending: UltraplanLaunchPending | None = None
    is_ultraplan_mode: bool = False

    # ---- Bridge permission callbacks (opaque) ----
    repl_bridge_permission_callbacks: Any | None = None
    channel_permission_callbacks: Any | None = None

    # ---- Team / swarm context ----
    team_context: TeamContext | None = None
    standalone_agent_context: StandaloneAgentContext | None = None

    # ---- Companion (buddy) ----
    companion_reaction: str | None = None
    companion_pet_at: float | None = None

    # ---- REPL tool VM context (opaque in Python) ----
    repl_context: Any | None = None

    # ---- Plan verification ----
    pending_plan_verification: PendingPlanVerification | None = None

    # ---- Background sessions ----
    background_sessions: dict[str, Any] = field(default_factory=dict)

    # ---- Theme ----
    theme: str = "default"
    theme_name: str = "Default"

    # ---- Completion boundaries ----
    completion_boundaries: list[CompletionBoundary] = field(
        default_factory=list
    )


# Type alias for the application store
AppStateStore = Store["AppState"]


def get_default_app_state() -> AppState:
    """Factory function that produces the initial AppState.

    Called once during store creation to provide the starting state.
    Every field is explicitly initialised so that consumers never need
    null-checks for top-level properties.

    Notable behaviour:
        - Reads initial settings from the merged settings cascade
          (placeholder: empty dict until settings system is ported).
        - Sets thinking/prompt-suggestion defaults.
    """
    return AppState(
        settings={},
        tasks={},
        agent_name_registry={},
        verbose=False,
        debug=False,
        is_main_agent=True,
        main_loop_model=None,
        main_loop_model_for_session=None,
        status_line_text=None,
        expanded_view="none",
        is_brief_only=False,
        show_teammate_message_preview=False,
        selected_ip_agent_index=-1,
        coordinator_task_index=-1,
        view_selection_mode="none",
        footer_selection=None,
        kairos_enabled=False,
        remote_session_url=None,
        remote_connection_status="connecting",
        remote_background_task_count=0,
        repl_bridge_enabled=False,
        repl_bridge_explicit=False,
        repl_bridge_outbound_only=False,
        repl_bridge_connected=False,
        repl_bridge_session_active=False,
        repl_bridge_reconnecting=False,
        repl_bridge_connect_url=None,
        repl_bridge_session_url=None,
        repl_bridge_environment_id=None,
        repl_bridge_session_id=None,
        repl_bridge_error=None,
        repl_bridge_initial_name=None,
        show_remote_callout=False,
        tool_permission_context=get_empty_tool_permission_context(),
        agent=None,
        agent_definitions=AgentDefinitionsResult(),
        file_history=FileHistoryState(),
        attribution=AttributionState(),
        mcp=MCPState(),
        plugins=PluginsState(),
        todos={},
        remote_agent_task_suggestions=[],
        notifications=NotificationState(),
        elicitation=ElicitationState(),
        thinking_enabled=None,
        prompt_suggestion_enabled=False,
        session_hooks={},
        inbox=InboxState(),
        worker_sandbox_permissions=WorkerSandboxPermissions(),
        pending_worker_request=None,
        pending_sandbox_request=None,
        prompt_suggestion=PromptSuggestionState(),
        speculation=IDLE_SPECULATION_STATE,
        speculation_session_time_saved_ms=0.0,
        skill_improvement=SkillImprovementState(),
        auth_version=0,
        initial_message=None,
        effort_value=None,
        active_overlays=set(),
        fast_mode=False,
        messages=[],
        in_progress_tool_use_ids=set(),
        conversation_id=None,
        session_id=str(uuid.uuid4()),
        query_source="cli",
        is_compact_in_progress=False,
        turn_count=0,
        total_cost_usd=0.0,
        total_api_duration_ms=0.0,
        background_sessions={},
        theme="default",
        theme_name="Default",
        completion_boundaries=[],
    )


__all__ = [
    "AppState",
    "AppStateStore",
    "AttributionState",
    "CompletionBoundary",
    "CompletionBoundaryBash",
    "CompletionBoundaryComplete",
    "CompletionBoundaryDenied",
    "CompletionBoundaryEdit",
    "ComputerUseMcpState",
    "EffortValue",
    "ElicitationState",
    "ExpandedView",
    "FileHistoryState",
    "FooterItem",
    "IDLE_SPECULATION_STATE",
    "InboxMessage",
    "InboxState",
    "InitialMessage",
    "MCPState",
    "ModelSetting",
    "NotificationState",
    "PendingPlanVerification",
    "PendingSandboxRequest",
    "PendingWorkerRequest",
    "PermissionMode",
    "PluginInstallationStatus",
    "PluginsState",
    "PromptSuggestionState",
    "RemoteConnectionStatus",
    "SkillImprovementState",
    "SpeculationActive",
    "SpeculationIdle",
    "SpeculationResult",
    "SpeculationState",
    "StandaloneAgentContext",
    "TeamContext",
    "ToolPermissionContext",
    "TungstenActiveSession",
    "TungstenLastCommand",
    "UltraplanLaunchPending",
    "UltraplanPendingChoice",
    "ViewSelectionMode",
    "WorkerSandboxPermissionRequest",
    "WorkerSandboxPermissions",
    "get_default_app_state",
    "get_empty_tool_permission_context",
    "to_external_permission_mode",
    "AgentDefinitionsResult",
]
