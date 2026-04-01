// =============================================================================
// AppStateStore.ts — Application state type definitions and default factory
// =============================================================================
//
// This file defines the shape of the entire application state tree (AppState),
// supporting types (CompletionBoundary, SpeculationState, etc.), and a factory
// function (getDefaultAppState) that produces the initial state. It does NOT
// create the store itself — that happens in AppState.tsx via `createStore()`.
//
// The AppState type is wrapped in `DeepImmutable<…>` (with strategic exclusions
// for function-bearing sub-trees like `tasks`). This enforces immutability at
// the type level: callers cannot accidentally mutate state in-place. Instead,
// all mutations must go through `store.setState(prev => ({ ...prev, … }))`,
// which produces a new object reference and triggers the change pipeline.
//
// Key architectural decisions:
//   1. Single atom — all UI-relevant state lives in one object so that
//      selectors can derive cross-cutting concerns without prop-drilling.
//   2. DeepImmutable wrapper — compile-time guarantee that state is read-only;
//      mutations require store.setState with a new object spread.
//   3. Escape hatches — fields containing functions or mutable refs (e.g.,
//      `tasks`, `agentNameRegistry`, `mcp`) are outside the DeepImmutable
//      wrapper so they remain assignable while still being part of the atom.
//   4. Flat defaults — getDefaultAppState() returns a plain object with all
//      fields initialized, so consumers never need null-checks for top-level
//      properties.
// =============================================================================

// ---------------------------------------------------------------------------
// Imports — type-only where possible to avoid pulling runtime code into
// modules that only need the AppState shape for type-checking.
// ---------------------------------------------------------------------------
import type { Notification } from 'src/context/notifications.js'
import type { TodoList } from 'src/utils/todo/types.js'
import type { BridgePermissionCallbacks } from '../bridge/bridgePermissionCallbacks.js'
import type { Command } from '../commands.js'
import type { ChannelPermissionCallbacks } from '../services/mcp/channelPermissions.js'
import type { ElicitationRequestEvent } from '../services/mcp/elicitationHandler.js'
import type {
  MCPServerConnection,
  ServerResource,
} from '../services/mcp/types.js'
import { shouldEnablePromptSuggestion } from '../services/PromptSuggestion/promptSuggestion.js'
import {
  getEmptyToolPermissionContext,
  type Tool,
  type ToolPermissionContext,
} from '../Tool.js'
import type { TaskState } from '../tasks/types.js'
import type { AgentColorName } from '../tools/AgentTool/agentColorManager.js'
import type { AgentDefinitionsResult } from '../tools/AgentTool/loadAgentsDir.js'
import type { AllowedPrompt } from '../tools/ExitPlanModeTool/ExitPlanModeV2Tool.js'
import type { AgentId } from '../types/ids.js'
import type { Message, UserMessage } from '../types/message.js'
import type { LoadedPlugin, PluginError } from '../types/plugin.js'
import type { DeepImmutable } from '../types/utils.js'
import {
  type AttributionState,
  createEmptyAttributionState,
} from '../utils/commitAttribution.js'
import type { EffortValue } from '../utils/effort.js'
import type { FileHistoryState } from '../utils/fileHistory.js'
import type { REPLHookContext } from '../utils/hooks/postSamplingHooks.js'
import type { SessionHooksState } from '../utils/hooks/sessionHooks.js'
import type { ModelSetting } from '../utils/model/model.js'
import type { DenialTrackingState } from '../utils/permissions/denialTracking.js'
import type { PermissionMode } from '../utils/permissions/PermissionMode.js'
import { getInitialSettings } from '../utils/settings/settings.js'
import type { SettingsJson } from '../utils/settings/types.js'
import { shouldEnableThinkingByDefault } from '../utils/thinking.js'
import type { Store } from './store.js'

// ---------------------------------------------------------------------------
// CompletionBoundary — Marks the logical boundary of a completed AI turn.
// Used by the speculation engine to know when a speculative execution has
// reached a natural stopping point. Each variant captures different turn
// endings: a full model completion, a bash command execution, a file edit,
// or a denied tool invocation.
// ---------------------------------------------------------------------------
export type CompletionBoundary =
  | { type: 'complete'; completedAt: number; outputTokens: number }
  | { type: 'bash'; command: string; completedAt: number }
  | { type: 'edit'; toolName: string; filePath: string; completedAt: number }
  | {
      type: 'denied_tool'
      toolName: string
      detail: string
      completedAt: number
    }

// ---------------------------------------------------------------------------
// SpeculationResult — The output of a completed speculative execution.
// Contains the messages produced, the boundary that ended it (if any),
// and the wall-clock time saved by speculating ahead of user confirmation.
// ---------------------------------------------------------------------------
export type SpeculationResult = {
  messages: Message[]
  boundary: CompletionBoundary | null
  timeSavedMs: number
}

// ---------------------------------------------------------------------------
// SpeculationState — Tracks the lifecycle of speculative execution.
//
// The speculation system pre-executes tool calls while the user reviews
// the previous turn, then replays or discards the results depending on
// whether the user accepts. This discriminated union models two phases:
//   - 'idle':   No speculation in flight.
//   - 'active': A speculative execution is running; holds abort handle,
//               mutable refs for accumulated messages/paths, and metadata.
//
// Mutable refs (messagesRef, writtenPathsRef, contextRef) are used instead
// of immutable arrays to avoid O(n) spreads on every speculative message.
// These refs are *not* tracked by React — they exist purely for the
// speculation engine's internal bookkeeping.
// ---------------------------------------------------------------------------
export type SpeculationState =
  | { status: 'idle' }
  | {
      status: 'active'
      id: string
      abort: () => void
      startTime: number
      messagesRef: { current: Message[] } // Mutable ref - avoids array spreading per message
      writtenPathsRef: { current: Set<string> } // Mutable ref - relative paths written to overlay
      boundary: CompletionBoundary | null
      suggestionLength: number
      toolUseCount: number
      isPipelined: boolean
      contextRef: { current: REPLHookContext }
      pipelinedSuggestion?: {
        text: string
        promptId: 'user_intent' | 'stated_intent'
        generationRequestId: string | null
      } | null
    }

// Singleton idle state — reused as the default to avoid allocating a new
// object every time speculation ends. Consumers can compare via ===.
export const IDLE_SPECULATION_STATE: SpeculationState = { status: 'idle' }

// ---------------------------------------------------------------------------
// FooterItem — Identifies which interactive pill/panel is shown in the REPL
// footer bar. Used for keyboard navigation (arrow keys cycle selection) and
// for toggling panel visibility.
// ---------------------------------------------------------------------------
export type FooterItem =
  | 'tasks'
  | 'tmux'
  | 'bagel'
  | 'teams'
  | 'bridge'
  | 'companion'

// ---------------------------------------------------------------------------
// AppState — The single source of truth for the entire application.
// ---------------------------------------------------------------------------
//
// Structure:
//   The type is split into two halves joined with an intersection (&):
//
//   1. DeepImmutable<{ … }> — The bulk of the state. All fields here are
//      recursively readonly at the type level, enforcing immutable update
//      patterns (spread + override). This covers settings, UI toggles, bridge
//      state, model selection, and other serializable data.
//
//   2. { tasks, agentNameRegistry, mcp, plugins, … } — Fields that contain
//      function types, Map/Set instances, or mutable refs which cannot be
//      frozen without breaking their APIs. These are outside DeepImmutable
//      but are still part of the same AppState atom.
//
// State categories (grouped logically):
//   • Settings & model:       settings, verbose, mainLoopModel, thinkingEnabled, effortValue
//   • UI view state:          expandedView, isBriefOnly, footerSelection, activeOverlays
//   • Permissions:            toolPermissionContext, denialTracking
//   • Agent / coordinator:    selectedIPAgentIndex, coordinatorTaskIndex, viewSelectionMode
//   • Remote bridge:          replBridge* fields — always-on bidirectional bridge state machine
//   • Remote session:         remoteSessionUrl, remoteConnectionStatus, remoteBackgroundTaskCount
//   • MCP (Model Context Protocol): mcp.clients, mcp.tools, mcp.commands, mcp.resources
//   • Plugins:                plugins.enabled, plugins.disabled, plugins.errors
//   • Tasks & agents:         tasks, agentNameRegistry, teamContext, inbox
//   • Speculation:            speculation, speculationSessionTimeSavedMs, promptSuggestion
//   • Computer use (chicago): computerUseMcpState — app allowlist, grants, display targeting
//   • Ultraplan:              ultraplanLaunching, ultraplanSessionUrl, ultraplanPendingChoice
//   • Tmux (tungsten):        tungstenActiveSession, tungstenPanelVisible, etc.
//   • WebBrowser (bagel):     bagelActive, bagelUrl, bagelPanelVisible
//   • Misc:                   todos, notifications, elicitation, fileHistory, attribution
// ---------------------------------------------------------------------------
export type AppState = DeepImmutable<{
  // ---- Settings & model configuration ----
  // Merged settings from all sources (project, user, env). See SettingsJson.
  settings: SettingsJson
  // Whether verbose/debug output is enabled (toggled via --verbose or /config)
  verbose: boolean
  // The model override for the main conversation loop (alias or full name).
  // null = use the server-assigned default model.
  mainLoopModel: ModelSetting
  // Session-scoped model override (from --model CLI flag); survives /model reset.
  mainLoopModelForSession: ModelSetting
  // Text shown in the status line area of the REPL (e.g., "Thinking…")
  statusLineText: string | undefined
  // Which expandable panel is open: task list, teammate tree, or none
  expandedView: 'none' | 'tasks' | 'teammates'
  // If true, only brief/summary messages are shown (compact output mode)
  isBriefOnly: boolean
  // Optional - only present when ENABLE_AGENT_SWARMS is true (for dead code elimination)
  showTeammateMessagePreview?: boolean
  // ---- Agent / coordinator panel navigation ----
  // Index of the currently selected in-process agent in the PromptInput agent list.
  // -1 means no agent is selected (leader is active).
  selectedIPAgentIndex: number
  // CoordinatorTaskPanel selection: -1 = pill, 0 = main, 1..N = agent rows.
  // AppState (not local) so the panel can read it directly without prop-drilling
  // through PromptInput → PromptInputFooter.
  coordinatorTaskIndex: number
  viewSelectionMode: 'none' | 'selecting-agent' | 'viewing-agent'
  // Which footer pill is focused (arrow-key navigation below the prompt).
  // Lives in AppState so pill components rendered outside PromptInput
  // (CompanionSprite in REPL.tsx) can read their own focused state.
  footerSelection: FooterItem | null
  // ---- Tool permissions ----
  // Current permission mode (default, plan, auto, etc.) and related context.
  // This is the single source of truth for whether tools require approval.
  // Changes are synced to CCR and SDK via onChangeAppState.ts.
  toolPermissionContext: ToolPermissionContext
  // Transient spinner tooltip text (shown next to the loading spinner)
  spinnerTip?: string
  // Agent name from --agent CLI flag or settings (for logo display)
  agent: string | undefined
  // Assistant mode fully enabled (settings + GrowthBook gate + trust).
  // Single source of truth - computed once in main.tsx before option
  // mutation, consumers read this instead of re-calling isAssistantMode().
  kairosEnabled: boolean
  // Remote session URL for --remote mode (shown in footer indicator)
  remoteSessionUrl: string | undefined
  // Remote session WS state (`claude assistant` viewer). 'connected' means the
  // live event stream is open; 'reconnecting' = transient WS drop, backoff
  // in progress; 'disconnected' = permanent close or reconnects exhausted.
  remoteConnectionStatus:
    | 'connecting'
    | 'connected'
    | 'reconnecting'
    | 'disconnected'
  // `claude assistant`: count of background tasks (Agent calls, teammates,
  // workflows) running inside the REMOTE daemon child. Event-sourced from
  // system/task_started and system/task_notification on the WS. The local
  // AppState.tasks is always empty in viewer mode — the tasks live in a
  // different process.
  remoteBackgroundTaskCount: number
  // Always-on bridge: desired state (controlled by /config or footer toggle)
  replBridgeEnabled: boolean
  // Always-on bridge: true when activated via /remote-control command, false when config-driven
  replBridgeExplicit: boolean
  // Outbound-only mode: forward events to CCR but reject inbound prompts/control
  replBridgeOutboundOnly: boolean
  // Always-on bridge: env registered + session created (= "Ready")
  replBridgeConnected: boolean
  // Always-on bridge: ingress WebSocket is open (= "Connected" - user on claude.ai)
  replBridgeSessionActive: boolean
  // Always-on bridge: poll loop is in error backoff (= "Reconnecting")
  replBridgeReconnecting: boolean
  // Always-on bridge: connect URL for Ready state (?bridge=envId)
  replBridgeConnectUrl: string | undefined
  // Always-on bridge: session URL on claude.ai (set when connected)
  replBridgeSessionUrl: string | undefined
  // Always-on bridge: IDs for debugging (shown in dialog when --verbose)
  replBridgeEnvironmentId: string | undefined
  replBridgeSessionId: string | undefined
  // Always-on bridge: error message when connection fails (shown in BridgeDialog)
  replBridgeError: string | undefined
  // Always-on bridge: session name set via `/remote-control <name>` (used as session title)
  replBridgeInitialName: string | undefined
  // Always-on bridge: first-time remote dialog pending (set by /remote-control command)
  showRemoteCallout: boolean
  // ---- End of DeepImmutable section ----
}> & {
  // =========================================================================
  // Mutable section — fields below are NOT wrapped in DeepImmutable because
  // they contain function types (TaskState callbacks), Map/Set instances, or
  // other values that cannot be deeply frozen without breaking their APIs.
  // They are still part of the AppState atom and participate in the same
  // store.setState / subscriber notification pipeline.
  // =========================================================================

  // ---- Task management ----
  // Unified task state - excluded from DeepImmutable because TaskState contains function types
  tasks: { [taskId: string]: TaskState }
  // Name → AgentId registry populated by Agent tool when `name` is provided.
  // Latest-wins on collision. Used by SendMessage to route by name.
  agentNameRegistry: Map<string, AgentId>
  // Task ID that has been foregrounded - its messages are shown in main view
  foregroundedTaskId?: string
  // Task ID of in-process teammate whose transcript is being viewed (undefined = leader's view)
  viewingAgentTaskId?: string

  // ---- Companion (buddy) ----
  // Latest companion reaction from the friend observer (src/buddy/observer.ts)
  companionReaction?: string
  // Timestamp of last /buddy pet — CompanionSprite renders hearts while recent
  companionPetAt?: number
  // ---- MCP (Model Context Protocol) integration ----
  // TODO (ashwin): see if we can use utility-types DeepReadonly for this
  mcp: {
    // Active MCP server connections (stdio / SSE transports)
    clients: MCPServerConnection[]
    // Tools exposed by all connected MCP servers (merged into the tool palette)
    tools: Tool[]
    // Slash commands contributed by MCP servers
    commands: Command[]
    // Resources advertised by MCP servers, keyed by server name
    resources: Record<string, ServerResource[]>
    /**
     * Incremented by /reload-plugins to trigger MCP effects to re-run
     * and pick up newly-enabled plugin MCP servers. Effects read this
     * as a dependency; the value itself is not consumed.
     */
    pluginReconnectKey: number
  }
  // ---- Plugin system ----
  // Tracks loaded plugins, their commands, errors, and installation progress.
  plugins: {
    // Plugins that are loaded and active in the current session
    enabled: LoadedPlugin[]
    // Plugins that exist on disk but are not active (disabled in settings)
    disabled: LoadedPlugin[]
    // Slash commands contributed by plugins
    commands: Command[]
    /**
     * Plugin system errors collected during loading and initialization.
     * See {@link PluginError} type documentation for complete details on error
     * structure, context fields, and display format.
     */
    errors: PluginError[]
    // Installation status for background plugin/marketplace installation
    installationStatus: {
      marketplaces: Array<{
        name: string
        status: 'pending' | 'installing' | 'installed' | 'failed'
        error?: string
      }>
      plugins: Array<{
        id: string
        name: string
        status: 'pending' | 'installing' | 'installed' | 'failed'
        error?: string
      }>
    }
    /**
     * Set to true when plugin state on disk has changed (background reconcile,
     * /plugin menu install, external settings edit) and active components are
     * stale. In interactive mode, user runs /reload-plugins to consume. In
     * headless mode, refreshPluginState() auto-consumes via refreshActivePlugins().
     */
    needsRefresh: boolean
  }
  // ---- Agent definitions ----
  // Registry of available agent definitions loaded from the agents directory.
  // Contains both active (matched) agents and all discovered agents.
  agentDefinitions: AgentDefinitionsResult
  // ---- File history & attribution ----
  // Snapshot-based file history for undo/restore operations
  fileHistory: FileHistoryState
  // Commit attribution tracking — maps file edits to the agent/tool that made them
  attribution: AttributionState
  // ---- Todo lists ----
  // Per-agent todo lists, keyed by agent ID. Shown in the task panel UI.
  todos: { [agentId: string]: TodoList }
  // ---- Remote agent suggestions ----
  // Task suggestions from remote agent sessions (shown in UI for user selection)
  remoteAgentTaskSuggestions: { summary: string; task: string }[]
  // ---- Notification system ----
  // Toast-style notifications with a current display slot and a FIFO queue.
  notifications: {
    current: Notification | null
    queue: Notification[]
  }
  // ---- MCP Elicitation ----
  // Queue of pending elicitation requests from MCP servers (user input needed)
  elicitation: {
    queue: ElicitationRequestEvent[]
  }
  // ---- Thinking / reasoning controls ----
  // Whether extended thinking (chain-of-thought) is enabled for the model.
  // undefined = use default based on model capabilities.
  thinkingEnabled: boolean | undefined
  // Whether prompt suggestion (auto-complete) is enabled
  promptSuggestionEnabled: boolean
  // ---- Session hooks ----
  // Map of registered session lifecycle hooks (pre/post sampling, etc.)
  sessionHooks: SessionHooksState
  // ---- Tmux integration (codename "tungsten") ----
  // Active tmux session details — set when Tmux tool creates/attaches a session
  tungstenActiveSession?: {
    sessionName: string
    socketName: string
    target: string // The tmux target (e.g., "session:window.pane")
  }
  tungstenLastCapturedTime?: number // Timestamp when frame was captured for model
  tungstenLastCommand?: {
    command: string // The command string to display (e.g., "Enter", "echo hello")
    timestamp: number // When the command was sent
  }
  // Sticky tmux panel visibility — mirrors globalConfig.tungstenPanelVisible for reactivity.
  tungstenPanelVisible?: boolean
  // Transient auto-hide at turn end — separate from tungstenPanelVisible so the
  // pill stays in the footer (user can reopen) but the panel content doesn't take
  // screen space when idle. Cleared on next Tmux tool use or user toggle. NOT persisted.
  tungstenPanelAutoHidden?: boolean
  // WebBrowser tool (codename bagel): pill visible in footer
  bagelActive?: boolean
  // WebBrowser tool: current page URL shown in pill label
  bagelUrl?: string
  // WebBrowser tool: sticky panel visibility toggle
  bagelPanelVisible?: boolean
  // chicago MCP session state. Types inlined (not imported from
  // @ant/computer-use-mcp/types) so external typecheck passes without the
  // ant-scoped dep resolved. Shapes match `AppGrant`/`CuGrantFlags`
  // structurally — wrapper.tsx assigns via structural compatibility. Only
  // populated when feature('CHICAGO_MCP') is active.
  computerUseMcpState?: {
    // Session-scoped app allowlist. NOT persisted across resume.
    allowedApps?: readonly {
      bundleId: string
      displayName: string
      grantedAt: number
    }[]
    // Clipboard/system-key grant flags (orthogonal to allowlist).
    grantFlags?: {
      clipboardRead: boolean
      clipboardWrite: boolean
      systemKeyCombos: boolean
    }
    // Dims-only (NOT the blob) for scaleCoord after compaction. The full
    // `ScreenshotResult` including base64 is process-local in wrapper.tsx.
    lastScreenshotDims?: {
      width: number
      height: number
      displayWidth: number
      displayHeight: number
      displayId?: number
      originX?: number
      originY?: number
    }
    // Accumulated by onAppsHidden, cleared + unhidden at turn end.
    hiddenDuringTurn?: ReadonlySet<string>
    // Which display CU targets. Written back by the package's
    // `autoTargetDisplay` resolver via `onResolvedDisplayUpdated`. Persisted
    // across resume so clicks stay on the display the model last saw.
    selectedDisplayId?: number
    // True when the model explicitly picked a display via `switch_display`.
    // Makes `handleScreenshot` skip the resolver chase chain and honor
    // `selectedDisplayId` directly. Cleared on resolver writeback (pinned
    // display unplugged → Swift fell back to main) and on
    // `switch_display("auto")`.
    displayPinnedByModel?: boolean
    // Sorted comma-joined bundle-ID set the display was last auto-resolved
    // for. `handleScreenshot` only re-resolves when the allowed set has
    // changed since — keeps the resolver from yanking on every screenshot.
    displayResolvedForApps?: string
  }
  // ---- REPL tool VM context ----
  // REPL tool VM context - persists across REPL calls for state sharing
  // Holds the V8 VM context, registered custom tools, and captured console output
  // so that successive REPL tool invocations share variables and definitions.
  replContext?: {
    vmContext: import('vm').Context
    registeredTools: Map<
      string,
      {
        name: string
        description: string
        schema: Record<string, unknown>
        handler: (args: Record<string, unknown>) => Promise<unknown>
      }
    >
    console: {
      log: (...args: unknown[]) => void
      error: (...args: unknown[]) => void
      warn: (...args: unknown[]) => void
      info: (...args: unknown[]) => void
      debug: (...args: unknown[]) => void
      getStdout: () => string
      getStderr: () => string
      clear: () => void
    }
  }
  // ---- Team / swarm context ----
  // Present when this session is part of a multi-agent team (swarm). Contains
  // the team name, lead agent info, self-identity for swarm members, and a
  // registry of all teammate processes (tmux panes, worktrees, etc.).
  teamContext?: {
    teamName: string
    teamFilePath: string
    leadAgentId: string
    // Self-identity for swarm members (separate processes in tmux panes)
    // Note: This is different from toolUseContext.agentId which is for in-process subagents
    selfAgentId?: string // Swarm member's own ID (same as leadAgentId for leaders)
    selfAgentName?: string // Swarm member's name ('team-lead' for leaders)
    isLeader?: boolean // True if this swarm member is the team leader
    selfAgentColor?: string // Assigned color for UI (used by dynamically joined sessions)
    teammates: {
      [teammateId: string]: {
        name: string
        agentType?: string
        color?: string
        tmuxSessionName: string
        tmuxPaneId: string
        cwd: string
        worktreePath?: string
        spawnedAt: number
      }
    }
  }
  // Standalone agent context for non-swarm sessions with custom name/color
  standaloneAgentContext?: {
    name: string
    color?: AgentColorName
  }
  // ---- Inter-agent messaging (inbox) ----
  // Message inbox for swarm communication — teammates send messages here,
  // processed by the leader or forwarded to the appropriate agent.
  inbox: {
    messages: Array<{
      id: string
      from: string
      text: string
      timestamp: string
      status: 'pending' | 'processing' | 'processed'
      color?: string
      summary?: string
    }>
  }
  // Worker sandbox permission requests (leader side) - for network access approval
  workerSandboxPermissions: {
    queue: Array<{
      requestId: string
      workerId: string
      workerName: string
      workerColor?: string
      host: string
      createdAt: number
    }>
    selectedIndex: number
  }
  // Pending permission request on worker side (shown while waiting for leader approval)
  pendingWorkerRequest: {
    toolName: string
    toolUseId: string
    description: string
  } | null
  // Pending sandbox permission request on worker side
  pendingSandboxRequest: {
    requestId: string
    host: string
  } | null
  // ---- Prompt suggestion / speculation ----
  // Auto-generated prompt suggestion shown to the user before they type.
  // Tracks the suggestion text, when it was shown/accepted, and the generation ID.
  promptSuggestion: {
    text: string | null
    promptId: 'user_intent' | 'stated_intent' | null
    shownAt: number
    acceptedAt: number
    generationRequestId: string | null
  }
  // Current speculative execution state (idle or active). See SpeculationState above.
  speculation: SpeculationState
  // Cumulative wall-clock time saved by successful speculations in this session (ms)
  speculationSessionTimeSavedMs: number
  // ---- Skill improvement ----
  // Pending skill improvement suggestion from the model (shown in UI for review)
  skillImprovement: {
    suggestion: {
      skillName: string
      updates: { section: string; change: string; reason: string }[]
    } | null
  }
  // Auth version - incremented on login/logout to trigger re-fetching of auth-dependent data
  authVersion: number
  // Initial message to process (from CLI args or plan mode exit)
  // When set, REPL will process the message and trigger a query
  initialMessage: {
    message: UserMessage
    clearContext?: boolean
    mode?: PermissionMode
    // Session-scoped permission rules from plan mode (e.g., "run tests", "install dependencies")
    allowedPrompts?: AllowedPrompt[]
  } | null
  // Pending plan verification state (set when exiting plan mode)
  // Used by VerifyPlanExecution tool to trigger background verification
  pendingPlanVerification?: {
    plan: string
    verificationStarted: boolean
    verificationCompleted: boolean
  }
  // Denial tracking for classifier modes (YOLO, headless, etc.) - falls back to prompting when limits exceeded
  denialTracking?: DenialTrackingState
  // Active overlays (Select dialogs, etc.) for Escape key coordination
  activeOverlays: ReadonlySet<string>
  // Fast mode
  fastMode?: boolean
  // Advisor model for server-side advisor tool (undefined = disabled).
  advisorModel?: string
  // Effort value
  effortValue?: EffortValue
  // Set synchronously in launchUltraplan before the detached flow starts.
  // Prevents duplicate launches during the ~5s window before
  // ultraplanSessionUrl is set by teleportToRemote. Cleared by launchDetached
  // once the URL is set or on failure.
  ultraplanLaunching?: boolean
  // Active ultraplan CCR session URL. Set while the RemoteAgentTask runs;
  // truthy disables the keyword trigger + rainbow. Cleared when the poll
  // reaches terminal state.
  ultraplanSessionUrl?: string
  // Approved ultraplan awaiting user choice (implement here vs fresh session).
  // Set by RemoteAgentTask poll on approval; cleared by UltraplanChoiceDialog.
  ultraplanPendingChoice?: { plan: string; sessionId: string; taskId: string }
  // Pre-launch permission dialog. Set by /ultraplan (slash or keyword);
  // cleared by UltraplanLaunchDialog on choice.
  ultraplanLaunchPending?: { blurb: string }
  // Remote-harness side: set via set_permission_mode control_request,
  // pushed to CCR external_metadata.is_ultraplan_mode by onChangeAppState.
  isUltraplanMode?: boolean
  // Always-on bridge: permission callbacks for bidirectional permission checks
  replBridgePermissionCallbacks?: BridgePermissionCallbacks
  // Channel permission callbacks — permission prompts over Telegram/iMessage/etc.
  // Races against local UI + bridge + hooks + classifier via claim() in
  // interactiveHandler.ts. Constructed once in useManageMCPConnections.
  channelPermissionCallbacks?: ChannelPermissionCallbacks
}

// ---------------------------------------------------------------------------
// AppStateStore — Convenience type alias for a Store parameterized with AppState.
// This is the type used by React context and non-React consumers to reference
// the application store instance.
// ---------------------------------------------------------------------------
export type AppStateStore = Store<AppState>

// ---------------------------------------------------------------------------
// getDefaultAppState — Factory function that produces the initial AppState.
//
// Called once during store creation (in AppStateProvider or headless bootstrap)
// to provide the starting state. Every field is explicitly initialized so that
// consumers never need to null-check top-level properties.
//
// Notable behavior:
//   - Detects teammate / plan-mode context to set the initial permission mode.
//   - Reads initial settings from the merged settings cascade.
//   - Determines thinking/prompt-suggestion defaults from feature flags.
// ---------------------------------------------------------------------------
export function getDefaultAppState(): AppState {
  // Determine initial permission mode for teammates spawned with plan_mode_required
  // Use lazy require to avoid circular dependency with teammate.ts
  /* eslint-disable @typescript-eslint/no-require-imports */
  const teammateUtils =
    require('../utils/teammate.js') as typeof import('../utils/teammate.js')
  /* eslint-enable @typescript-eslint/no-require-imports */
  const initialMode: PermissionMode =
    teammateUtils.isTeammate() && teammateUtils.isPlanModeRequired()
      ? 'plan'
      : 'default'

  // Build and return the fully-initialized default state object.
  // Each field is set to a sensible zero/empty/disabled value.
  return {
    // Load merged settings from user, project, and environment sources
    settings: getInitialSettings(),
    // Start with an empty task registry
    tasks: {},
    // Start with an empty agent name → ID mapping
    agentNameRegistry: new Map(),
    verbose: false,
    mainLoopModel: null, // alias, full name (as with --model or env var), or null (default)
    mainLoopModelForSession: null,
    statusLineText: undefined,
    expandedView: 'none',
    isBriefOnly: false,
    showTeammateMessagePreview: false,
    selectedIPAgentIndex: -1,
    coordinatorTaskIndex: -1,
    viewSelectionMode: 'none',
    footerSelection: null,
    // Assistant mode starts disabled; computed in main.tsx after gate checks
    kairosEnabled: false,
    remoteSessionUrl: undefined,
    // Remote connection starts in 'connecting' and transitions based on WS events
    remoteConnectionStatus: 'connecting',
    remoteBackgroundTaskCount: 0,
    // All bridge fields start disabled/disconnected
    replBridgeEnabled: false,
    replBridgeExplicit: false,
    replBridgeOutboundOnly: false,
    replBridgeConnected: false,
    replBridgeSessionActive: false,
    replBridgeReconnecting: false,
    replBridgeConnectUrl: undefined,
    replBridgeSessionUrl: undefined,
    replBridgeEnvironmentId: undefined,
    replBridgeSessionId: undefined,
    replBridgeError: undefined,
    replBridgeInitialName: undefined,
    showRemoteCallout: false,
    // Initialize permission context with mode derived from teammate/plan detection above
    toolPermissionContext: {
      ...getEmptyToolPermissionContext(),
      mode: initialMode,
    },
    agent: undefined,
    // Start with empty agent definitions (populated during bootstrap)
    agentDefinitions: { activeAgents: [], allAgents: [] },
    // Initialize empty file history tracking
    fileHistory: {
      snapshots: [],
      trackedFiles: new Set(),
      snapshotSequence: 0,
    },
    // Initialize empty commit attribution state
    attribution: createEmptyAttributionState(),
    // Initialize empty MCP state (populated when MCP servers connect)
    mcp: {
      clients: [],
      tools: [],
      commands: [],
      resources: {},
      pluginReconnectKey: 0,
    },
    // Initialize empty plugin state (populated during plugin discovery)
    plugins: {
      enabled: [],
      disabled: [],
      commands: [],
      errors: [],
      installationStatus: {
        marketplaces: [],
        plugins: [],
      },
      needsRefresh: false,
    },
    // No todos for any agent yet
    todos: {},
    remoteAgentTaskSuggestions: [],
    // No active or queued notifications
    notifications: {
      current: null,
      queue: [],
    },
    // No pending elicitation requests
    elicitation: {
      queue: [],
    },
    // Thinking and prompt suggestion defaults are determined by feature flags
    thinkingEnabled: shouldEnableThinkingByDefault(),
    promptSuggestionEnabled: shouldEnablePromptSuggestion(),
    // Session hooks start as an empty Map
    sessionHooks: new Map(),
    // Empty inbox (no inter-agent messages)
    inbox: {
      messages: [],
    },
    // Worker sandbox permissions start with empty queue
    workerSandboxPermissions: {
      queue: [],
      selectedIndex: 0,
    },
    pendingWorkerRequest: null,
    pendingSandboxRequest: null,
    // Prompt suggestion starts empty (populated when the suggestion engine runs)
    promptSuggestion: {
      text: null,
      promptId: null,
      shownAt: 0,
      acceptedAt: 0,
      generationRequestId: null,
    },
    // Speculation starts idle (no pre-execution in flight)
    speculation: IDLE_SPECULATION_STATE,
    speculationSessionTimeSavedMs: 0,
    // No pending skill improvement suggestions
    skillImprovement: {
      suggestion: null,
    },
    // Auth version counter starts at 0 (incremented on login/logout)
    authVersion: 0,
    // No initial message to process
    initialMessage: null,
    effortValue: undefined,
    // No active UI overlays (dialogs, selects, etc.)
    activeOverlays: new Set<string>(),
    // Fast mode disabled by default
    fastMode: false,
  }
}

