// ─────────────────────────────────────────────────────────────────────────────
// tools.ts — Central Tool Registry for Claude Code
// ─────────────────────────────────────────────────────────────────────────────
//
// This module is the **single source of truth** for which tools the LLM agent
// can invoke.  It handles:
//
//   1. Importing every tool implementation (statically or conditionally).
//   2. Building the exhaustive base tool list  → getAllBaseTools()
//   3. Filtering that list for the active session → getTools()
//      • CLAUDE_CODE_SIMPLE ("bare") mode — minimal tool surface
//      • REPL mode — collapses primitives behind the REPL tool
//      • Feature-flag gating (COORDINATOR_MODE, PROACTIVE, KAIROS, …)
//      • Permission deny-rule filtering (blanket denies strip tools pre-prompt)
//      • isEnabled() per-tool runtime checks
//   4. Merging built-in tools with dynamic MCP tools → assembleToolPool()
//
// The import section is intentionally ordered: static ES imports first, then
// conditional `require()` calls guarded by `feature()` or `process.env` checks.
// The Bun bundler uses these guards for **dead-code elimination** — tools
// behind a disabled flag are tree-shaken from the production bundle entirely.
//
// ─────────────────────────────────────────────────────────────────────────────

// biome-ignore-all assist/source/organizeImports: ANT-ONLY import markers must not be reordered

// ── Core type imports ────────────────────────────────────────────────────────
// Tool and Tools are the base interfaces that every tool must implement.
// toolMatchesName is the canonical name-matcher used throughout the codebase.
import { toolMatchesName, type Tool, type Tools } from './Tool.js'
// ── Static tool imports ──────────────────────────────────────────────────────
// These tools are always imported (always present in the bundle).  Whether they
// actually appear in the final tool list depends on getAllBaseTools() and
// getTools() filtering — but the code is always loaded.

// Sub-agent orchestration: lets the LLM spawn child agent tasks
import { AgentTool } from './tools/AgentTool/AgentTool.js'
// Skill invocation: runs user-defined or built-in skills (workflows)
import { SkillTool } from './tools/SkillTool/SkillTool.js'
// Shell execution: runs arbitrary bash commands in a sandboxed shell
import { BashTool } from './tools/BashTool/BashTool.js'
// File I/O — edit (surgical string replacement), read, and write (full overwrite)
import { FileEditTool } from './tools/FileEditTool/FileEditTool.js'
import { FileReadTool } from './tools/FileReadTool/FileReadTool.js'
import { FileWriteTool } from './tools/FileWriteTool/FileWriteTool.js'
// File search: glob-based filename matching (e.g. **/*.ts)
import { GlobTool } from './tools/GlobTool/GlobTool.js'
// Jupyter notebook cell editing
import { NotebookEditTool } from './tools/NotebookEditTool/NotebookEditTool.js'
// HTTP fetching: retrieves web page content for the LLM
import { WebFetchTool } from './tools/WebFetchTool/WebFetchTool.js'
// Task lifecycle: signals the agent to stop the current task
import { TaskStopTool } from './tools/TaskStopTool/TaskStopTool.js'
// Brief output: produces concise summaries for the user
import { BriefTool } from './tools/BriefTool/BriefTool.js'
// ── Conditionally-loaded tools (dead-code elimination) ───────────────────────
// These tools use `require()` behind runtime guards (`process.env` or
// `feature()` from 'bun:bundle').  The Bun bundler evaluates these guards at
// build time: when a guard is statically false the entire require() and its
// transitive dependency tree are stripped from the output bundle, keeping the
// binary small.  At runtime the variables are simply `null` when disabled.
//
// Dead code elimination: conditional import for ant-only tools
/* eslint-disable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */

// REPLTool: an interactive read-eval-print-loop that wraps Bash, FileRead,
// FileEdit and others inside a VM sandbox.  Ant-internal only.
const REPLTool =
  process.env.USER_TYPE === 'ant'
    ? require('./tools/REPLTool/REPLTool.js').REPLTool
    : null
// SuggestBackgroundPRTool: suggests opening a background PR.  Ant-internal.
const SuggestBackgroundPRTool =
  process.env.USER_TYPE === 'ant'
    ? require('./tools/SuggestBackgroundPRTool/SuggestBackgroundPRTool.js')
        .SuggestBackgroundPRTool
    : null
// SleepTool: pauses execution for a duration.  Used by proactive agents and
// long-running Kairos sessions that need to wait for external events.
const SleepTool =
  feature('PROACTIVE') || feature('KAIROS')
    ? require('./tools/SleepTool/SleepTool.js').SleepTool
    : null
// Cron scheduling tools: allow the agent to create, list, and delete
// scheduled triggers (cron jobs) for automated recurring tasks.
const cronTools = feature('AGENT_TRIGGERS')
  ? [
      require('./tools/ScheduleCronTool/CronCreateTool.js').CronCreateTool,
      require('./tools/ScheduleCronTool/CronDeleteTool.js').CronDeleteTool,
      require('./tools/ScheduleCronTool/CronListTool.js').CronListTool,
    ]
  : []
// RemoteTriggerTool: lets the agent register a remote webhook trigger.
const RemoteTriggerTool = feature('AGENT_TRIGGERS_REMOTE')
  ? require('./tools/RemoteTriggerTool/RemoteTriggerTool.js').RemoteTriggerTool
  : null
// MonitorTool: allows the agent to monitor long-running processes or commands.
const MonitorTool = feature('MONITOR_TOOL')
  ? require('./tools/MonitorTool/MonitorTool.js').MonitorTool
  : null
// SendUserFileTool: sends a file to the user.  Kairos (long-running agent) only.
const SendUserFileTool = feature('KAIROS')
  ? require('./tools/SendUserFileTool/SendUserFileTool.js').SendUserFileTool
  : null
// PushNotificationTool: sends push notifications to the user's device.
// Enabled for Kairos sessions or via the dedicated KAIROS_PUSH_NOTIFICATION flag.
const PushNotificationTool =
  feature('KAIROS') || feature('KAIROS_PUSH_NOTIFICATION')
    ? require('./tools/PushNotificationTool/PushNotificationTool.js')
        .PushNotificationTool
    : null
// SubscribePRTool: subscribes to GitHub PR webhook events for realtime updates.
const SubscribePRTool = feature('KAIROS_GITHUB_WEBHOOKS')
  ? require('./tools/SubscribePRTool/SubscribePRTool.js').SubscribePRTool
  : null
/* eslint-enable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */

// ── More static tool imports (second batch) ──────────────────────────────────
// These are placed after the conditional block because biome's import organizer
// is disabled — the ANT-ONLY markers above must not be reordered.

// TaskOutputTool: produces structured output from a completed agent task
import { TaskOutputTool } from './tools/TaskOutputTool/TaskOutputTool.js'
// WebSearchTool: performs web searches and returns results to the LLM
import { WebSearchTool } from './tools/WebSearchTool/WebSearchTool.js'
// TodoWriteTool: manages a todo/checklist that the agent can update
import { TodoWriteTool } from './tools/TodoWriteTool/TodoWriteTool.js'
// Plan mode tools: allow the LLM to enter/exit a structured planning phase
import { ExitPlanModeV2Tool } from './tools/ExitPlanModeTool/ExitPlanModeV2Tool.js'
// Testing-only tool: used in the test suite to validate permission behavior
import { TestingPermissionTool } from './tools/testing/TestingPermissionTool.js'
// GrepTool: regex-based content search across files (ripgrep wrapper)
import { GrepTool } from './tools/GrepTool/GrepTool.js'
// TungstenTool: ant-internal integration with the Tungsten service
import { TungstenTool } from './tools/TungstenTool/TungstenTool.js'
// ── Lazy-loaded tools (circular dependency breakers) ─────────────────────────
// These tools are loaded via getter functions (lazy `require()`) rather than
// top-level imports to avoid circular module dependencies.
// The chain would be:  tools.ts → TeamCreateTool → … → tools.ts
// Lazy evaluation defers the require() until first call, after all modules have
// finished their initial evaluation.
//
// Lazy require to break circular dependency: tools.ts -> TeamCreateTool/TeamDeleteTool -> ... -> tools.ts
/* eslint-disable @typescript-eslint/no-require-imports */
// TeamCreateTool / TeamDeleteTool: agent swarm management — create and delete
// teams of cooperating sub-agents that share a workspace.
const getTeamCreateTool = () =>
  require('./tools/TeamCreateTool/TeamCreateTool.js')
    .TeamCreateTool as typeof import('./tools/TeamCreateTool/TeamCreateTool.js').TeamCreateTool
const getTeamDeleteTool = () =>
  require('./tools/TeamDeleteTool/TeamDeleteTool.js')
    .TeamDeleteTool as typeof import('./tools/TeamDeleteTool/TeamDeleteTool.js').TeamDeleteTool
// SendMessageTool: sends a message to another agent (peer-to-peer comms).
const getSendMessageTool = () =>
  require('./tools/SendMessageTool/SendMessageTool.js')
    .SendMessageTool as typeof import('./tools/SendMessageTool/SendMessageTool.js').SendMessageTool
/* eslint-enable @typescript-eslint/no-require-imports */

// ── Third batch of static tool imports ───────────────────────────────────────

// AskUserQuestionTool: presents a structured question to the user (MCQ-style)
import { AskUserQuestionTool } from './tools/AskUserQuestionTool/AskUserQuestionTool.js'
// LSPTool: Language Server Protocol integration (diagnostics, go-to-definition, etc.)
import { LSPTool } from './tools/LSPTool/LSPTool.js'
// MCP resource tools: list and read resources exposed by MCP (Model Context Protocol) servers
import { ListMcpResourcesTool } from './tools/ListMcpResourcesTool/ListMcpResourcesTool.js'
import { ReadMcpResourceTool } from './tools/ReadMcpResourceTool/ReadMcpResourceTool.js'
// ToolSearchTool: meta-tool that lets the LLM search for other tools by keyword
// (used when the tool list is large enough that sending all schemas is wasteful)
import { ToolSearchTool } from './tools/ToolSearchTool/ToolSearchTool.js'
// Plan mode entry: lets the LLM switch into a structured planning workflow
import { EnterPlanModeTool } from './tools/EnterPlanModeTool/EnterPlanModeTool.js'
// Worktree tools: enter/exit Git worktree isolation for parallel work
import { EnterWorktreeTool } from './tools/EnterWorktreeTool/EnterWorktreeTool.js'
import { ExitWorktreeTool } from './tools/ExitWorktreeTool/ExitWorktreeTool.js'
// ConfigTool: lets the agent read/update Claude Code configuration
import { ConfigTool } from './tools/ConfigTool/ConfigTool.js'
// Task management tools (v2): create, get, update, and list tasks.
// Gated behind isTodoV2Enabled() at registration time.
import { TaskCreateTool } from './tools/TaskCreateTool/TaskCreateTool.js'
import { TaskGetTool } from './tools/TaskGetTool/TaskGetTool.js'
import { TaskUpdateTool } from './tools/TaskUpdateTool/TaskUpdateTool.js'
import { TaskListTool } from './tools/TaskListTool/TaskListTool.js'

// ── Utility imports ──────────────────────────────────────────────────────────
// uniqBy: lodash deduplication helper — used in assembleToolPool to merge
// built-in and MCP tools, ensuring built-ins take precedence on name conflict.
import uniqBy from 'lodash-es/uniqBy.js'
// Optimistic check for whether tool-search should be offered (cheap heuristic
// evaluated once at import time; the real decision happens per-request).
import { isToolSearchEnabledOptimistic } from './utils/toolSearch.js'
// Feature check: is the v2 task management system enabled?
import { isTodoV2Enabled } from './utils/tasks.js'
// ── Second batch of conditionally-loaded tools ───────────────────────────────
// Same dead-code elimination pattern as above, but for tools that depend on
// imports defined later in the file or use different feature flag sources.

// VerifyPlanExecutionTool: optional tool that verifies planned steps were
// executed correctly.  Enabled by CLAUDE_CODE_VERIFY_PLAN env var.
// Dead code elimination: conditional import for CLAUDE_CODE_VERIFY_PLAN
/* eslint-disable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */
const VerifyPlanExecutionTool =
  process.env.CLAUDE_CODE_VERIFY_PLAN === 'true'
    ? require('./tools/VerifyPlanExecutionTool/VerifyPlanExecutionTool.js')
        .VerifyPlanExecutionTool
    : null
/* eslint-enable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */
// SYNTHETIC_OUTPUT_TOOL_NAME: a pseudo-tool name used to tag synthetic (non-LLM)
// output injected into the conversation.  Not a real tool — just a constant.
import { SYNTHETIC_OUTPUT_TOOL_NAME } from './tools/SyntheticOutputTool/SyntheticOutputTool.js'

// ── Re-exports ───────────────────────────────────────────────────────────────
// Centralized constants that define which tools are allowed/disallowed for
// different agent modes.  Consumers import them from this barrel module.
export {
  ALL_AGENT_DISALLOWED_TOOLS,
  CUSTOM_AGENT_DISALLOWED_TOOLS,
  ASYNC_AGENT_ALLOWED_TOOLS,
  COORDINATOR_MODE_ALLOWED_TOOLS,
} from './constants/tools.js'

// ── Bun-bundler feature flag primitive ───────────────────────────────────────
// `feature()` is a Bun compile-time intrinsic.  When the flag evaluates to
// false at build time the guarded `require()` is eliminated from the bundle.
import { feature } from 'bun:bundle'

// ── Third batch of conditionally-loaded tools ────────────────────────────────

// OverflowTestTool: test-only tool for overflow/edge-case testing.
// Dead code elimination: conditional import for OVERFLOW_TEST_TOOL
/* eslint-disable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */
const OverflowTestTool = feature('OVERFLOW_TEST_TOOL')
  ? require('./tools/OverflowTestTool/OverflowTestTool.js').OverflowTestTool
  : null
// CtxInspectTool: introspection/debugging tool for the context-collapse feature.
const CtxInspectTool = feature('CONTEXT_COLLAPSE')
  ? require('./tools/CtxInspectTool/CtxInspectTool.js').CtxInspectTool
  : null
// TerminalCaptureTool: captures the terminal panel's current screen state.
const TerminalCaptureTool = feature('TERMINAL_PANEL')
  ? require('./tools/TerminalCaptureTool/TerminalCaptureTool.js')
      .TerminalCaptureTool
  : null
// WebBrowserTool: a headless-browser-based tool for navigating and interacting
// with web pages (richer than WebFetchTool which just fetches raw HTML).
const WebBrowserTool = feature('WEB_BROWSER_TOOL')
  ? require('./tools/WebBrowserTool/WebBrowserTool.js').WebBrowserTool
  : null
// coordinatorModeModule: the coordinator-mode orchestration layer.
// When COORDINATOR_MODE is enabled the main agent becomes a coordinator that
// delegates work to sub-agent workers.  This module exposes
// `isCoordinatorMode()` to check if we're currently in that mode.
const coordinatorModeModule = feature('COORDINATOR_MODE')
  ? (require('./coordinator/coordinatorMode.js') as typeof import('./coordinator/coordinatorMode.js'))
  : null
// SnipTool: lets the LLM snip (truncate) old history entries to reclaim context.
const SnipTool = feature('HISTORY_SNIP')
  ? require('./tools/SnipTool/SnipTool.js').SnipTool
  : null
// ListPeersTool: lists other running agent instances reachable via UDS inbox.
const ListPeersTool = feature('UDS_INBOX')
  ? require('./tools/ListPeersTool/ListPeersTool.js').ListPeersTool
  : null
// WorkflowTool: runs user-defined workflow scripts.  The IIFE initializes
// bundled workflows before returning the tool definition.
const WorkflowTool = feature('WORKFLOW_SCRIPTS')
  ? (() => {
      require('./tools/WorkflowTool/bundled/index.js').initBundledWorkflows()
      return require('./tools/WorkflowTool/WorkflowTool.js').WorkflowTool
    })()
  : null
/* eslint-enable custom-rules/no-process-env-top-level, @typescript-eslint/no-require-imports */

// ── Permission and utility imports ───────────────────────────────────────────

// ToolPermissionContext: the per-request context object carrying permission
// rules (allow/deny lists, MCP server config, etc.) used to filter tools.
import type { ToolPermissionContext } from './Tool.js'
// getDenyRuleForTool: checks whether a specific deny rule matches a tool,
// supporting both exact names and MCP server-prefix patterns (e.g. `mcp__server`).
import { getDenyRuleForTool } from './utils/permissions/permissions.js'
// hasEmbeddedSearchTools: returns true when the Bun binary ships with embedded
// bfs/ugrep, making the standalone GlobTool/GrepTool redundant.
import { hasEmbeddedSearchTools } from './utils/embeddedTools.js'
// isEnvTruthy: helper to check if an env var is truthy ('1', 'true', etc.)
import { isEnvTruthy } from './utils/envUtils.js'
// isPowerShellToolEnabled: checks platform + config to see if PowerShell is available.
import { isPowerShellToolEnabled } from './utils/shell/shellToolUtils.js'
// isAgentSwarmsEnabled: feature check for multi-agent swarm mode.
import { isAgentSwarmsEnabled } from './utils/agentSwarmsEnabled.js'
// isWorktreeModeEnabled: feature check for Git worktree isolation mode.
import { isWorktreeModeEnabled } from './utils/worktreeModeEnabled.js'
// REPL constants: tool name, the set of tools that REPL subsumes, and the
// check for whether REPL mode is currently active.
import {
  REPL_TOOL_NAME,
  REPL_ONLY_TOOLS,
  isReplModeEnabled,
} from './tools/REPLTool/constants.js'
export { REPL_ONLY_TOOLS }
// PowerShellTool: lazy-loaded Windows PowerShell execution tool.
// Only instantiated when the platform check passes (Windows + enabled config).
/* eslint-disable @typescript-eslint/no-require-imports */
const getPowerShellTool = () => {
  if (!isPowerShellToolEnabled()) return null
  return (
    require('./tools/PowerShellTool/PowerShellTool.js') as typeof import('./tools/PowerShellTool/PowerShellTool.js')
  ).PowerShellTool
}
/* eslint-enable @typescript-eslint/no-require-imports */

// ═════════════════════════════════════════════════════════════════════════════
// TOOL PRESETS & ENUMERATION
// ═════════════════════════════════════════════════════════════════════════════
// Presets allow the CLI to expose named collections of tools via `--tools`.
// Currently only 'default' exists — it resolves to every enabled base tool.

/**
 * Predefined tool presets that can be used with --tools flag
 */
export const TOOL_PRESETS = ['default'] as const

// TypeScript union type derived from the const array for type-safe preset names.
export type ToolPreset = (typeof TOOL_PRESETS)[number]

// parseToolPreset: validates a user-supplied string against TOOL_PRESETS.
// Returns the normalized preset name or null if unrecognized.
export function parseToolPreset(preset: string): ToolPreset | null {
  const presetString = preset.toLowerCase()
  if (!TOOL_PRESETS.includes(presetString as ToolPreset)) {
    return null
  }
  return presetString as ToolPreset
}

/**
 * Get the list of tool names for a given preset
 * Filters out tools that are disabled via isEnabled() check
 * @param preset The preset name
 * @returns Array of tool names
 */
// getToolsForDefaultPreset: materializes the 'default' preset into a list of
// tool name strings.  Calls getAllBaseTools() for the full catalog, then drops
// any tool whose isEnabled() returns false (e.g. a tool might disable itself
// if a required binary is missing from PATH).
export function getToolsForDefaultPreset(): string[] {
  const tools = getAllBaseTools()
  // Evaluate isEnabled() once per tool to avoid repeated side effects
  const isEnabled = tools.map(tool => tool.isEnabled())
  return tools.filter((_, i) => isEnabled[i]).map(tool => tool.name)
}

// ═════════════════════════════════════════════════════════════════════════════
// getAllBaseTools() — EXHAUSTIVE TOOL CATALOG
// ═════════════════════════════════════════════════════════════════════════════
// Returns every tool that *could* be available given the current environment.
// Conditional entries (feature flags, env vars) are evaluated here so the
// returned array only contains tools whose prerequisites are met.
//
// This is NOT the final list sent to the LLM — getTools() further filters by
// permission deny rules, CLAUDE_CODE_SIMPLE mode, REPL mode, and isEnabled().
//
// ⚠️  The tool order here affects prompt-cache key stability.  See the Statsig
// config link in the JSDoc below — any change to this list must be mirrored
// there so the system prompt can be cached across users.

/**
 * Get the complete exhaustive list of all tools that could be available
 * in the current environment (respecting process.env flags).
 * This is the source of truth for ALL tools.
 */
/**
 * NOTE: This MUST stay in sync with https://console.statsig.com/4aF3Ewatb6xPVpCwxb5nA3/dynamic_configs/claude_code_global_system_caching, in order to cache the system prompt across users.
 */
export function getAllBaseTools(): Tools {
  return [
    // ── Core orchestration tools ───────────────────────────────────────────
    AgentTool,        // Sub-agent spawning (delegate tasks to child agents)
    TaskOutputTool,   // Structured output from a completed agent task

    // ── Shell & execution ──────────────────────────────────────────────────
    BashTool,         // Run arbitrary bash commands in the sandbox

    // ── File search (conditionally included) ───────────────────────────────
    // Ant-native builds have bfs/ugrep embedded in the bun binary (same ARGV0
    // trick as ripgrep). When available, find/grep in Claude's shell are aliased
    // to these fast tools, so the dedicated Glob/Grep tools are unnecessary.
    ...(hasEmbeddedSearchTools() ? [] : [GlobTool, GrepTool]),

    // ── Plan mode ──────────────────────────────────────────────────────────
    ExitPlanModeV2Tool, // Exit a structured planning phase

    // ── File I/O ───────────────────────────────────────────────────────────
    FileReadTool,       // Read file contents
    FileEditTool,       // Surgical string-replacement edits
    FileWriteTool,      // Full file overwrites
    NotebookEditTool,   // Jupyter notebook cell editing

    // ── Web access ─────────────────────────────────────────────────────────
    WebFetchTool,     // Fetch raw web page content
    // ── Task tracking ──────────────────────────────────────────────────────
    TodoWriteTool,    // Manage a todo/checklist visible to the user
    // ── Web search ─────────────────────────────────────────────────────────
    WebSearchTool,    // Perform web searches

    // ── Session lifecycle ──────────────────────────────────────────────────
    TaskStopTool,     // Signal the agent to stop the current task

    // ── User interaction ───────────────────────────────────────────────────
    AskUserQuestionTool, // Present structured MCQ-style questions to the user
    SkillTool,           // Invoke named skills (user-defined workflows)
    EnterPlanModeTool,   // Enter a structured planning phase

    // ── Ant-internal tools (USER_TYPE === 'ant') ───────────────────────────
    ...(process.env.USER_TYPE === 'ant' ? [ConfigTool] : []),
    ...(process.env.USER_TYPE === 'ant' ? [TungstenTool] : []),
    ...(SuggestBackgroundPRTool ? [SuggestBackgroundPRTool] : []),

    // ── Feature-gated: headless browser ────────────────────────────────────
    ...(WebBrowserTool ? [WebBrowserTool] : []),

    // ── Feature-gated: v2 task management (structured task CRUD) ──────────
    ...(isTodoV2Enabled()
      ? [TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool]
      : []),

    // ── Feature-gated: testing & debugging tools ───────────────────────────
    ...(OverflowTestTool ? [OverflowTestTool] : []),
    ...(CtxInspectTool ? [CtxInspectTool] : []),
    ...(TerminalCaptureTool ? [TerminalCaptureTool] : []),

    // ── Feature-gated: LSP integration ─────────────────────────────────────
    ...(isEnvTruthy(process.env.ENABLE_LSP_TOOL) ? [LSPTool] : []),

    // ── Feature-gated: Git worktree isolation ──────────────────────────────
    ...(isWorktreeModeEnabled() ? [EnterWorktreeTool, ExitWorktreeTool] : []),

    // ── Inter-agent communication ──────────────────────────────────────────
    getSendMessageTool(), // Always included (lazy-loaded to break circular dep)
    ...(ListPeersTool ? [ListPeersTool] : []),

    // ── Feature-gated: agent swarm management ──────────────────────────────
    ...(isAgentSwarmsEnabled()
      ? [getTeamCreateTool(), getTeamDeleteTool()]
      : []),

    // ── Feature-gated: plan verification ───────────────────────────────────
    ...(VerifyPlanExecutionTool ? [VerifyPlanExecutionTool] : []),

    // ── Feature-gated: REPL mode (ant-internal) ───────────────────────────
    ...(process.env.USER_TYPE === 'ant' && REPLTool ? [REPLTool] : []),

    // ── Feature-gated: workflow scripts ────────────────────────────────────
    ...(WorkflowTool ? [WorkflowTool] : []),

    // ── Feature-gated: proactive / long-running agent tools ───────────────
    ...(SleepTool ? [SleepTool] : []),
    ...cronTools,                                   // Cron scheduling (create/delete/list)
    ...(RemoteTriggerTool ? [RemoteTriggerTool] : []),
    ...(MonitorTool ? [MonitorTool] : []),

    // ── Output formatting ──────────────────────────────────────────────────
    BriefTool,        // Concise output summaries

    // ── Feature-gated: Kairos (long-running agent) tools ──────────────────
    ...(SendUserFileTool ? [SendUserFileTool] : []),
    ...(PushNotificationTool ? [PushNotificationTool] : []),
    ...(SubscribePRTool ? [SubscribePRTool] : []),

    // ── Platform-specific: Windows PowerShell ──────────────────────────────
    ...(getPowerShellTool() ? [getPowerShellTool()] : []),

    // ── Feature-gated: history snipping (context reclamation) ─────────────
    ...(SnipTool ? [SnipTool] : []),

    // ── Test-only tool (NODE_ENV === 'test') ───────────────────────────────
    ...(process.env.NODE_ENV === 'test' ? [TestingPermissionTool] : []),

    // ── MCP (Model Context Protocol) resource tools ───────────────────────
    // These are always registered but treated as "special" by getTools() —
    // they are excluded from the main tool list and only added back in
    // assembleToolPool when MCP servers are configured.
    ListMcpResourcesTool,
    ReadMcpResourceTool,

    // ── Meta-tool: tool search ─────────────────────────────────────────────
    // Include ToolSearchTool when tool search might be enabled (optimistic check)
    // The actual decision to defer tools happens at request time in claude.ts
    ...(isToolSearchEnabledOptimistic() ? [ToolSearchTool] : []),
  ]
}

// ═════════════════════════════════════════════════════════════════════════════
// filterToolsByDenyRules() — PERMISSION-BASED PRE-FILTERING
// ═════════════════════════════════════════════════════════════════════════════
// Removes tools that the user has explicitly denied via permission configuration.
// This runs **before** the tool schemas are sent to the LLM, so denied tools
// never appear in the prompt — they're invisible to the model, not just blocked
// at call time.
//
// The function is generic so it works for both built-in Tool objects and MCP
// tool descriptors (which carry `mcpInfo` with server/tool names).

/**
 * Filters out tools that are blanket-denied by the permission context.
 * A tool is filtered out if there's a deny rule matching its name with no
 * ruleContent (i.e., a blanket deny for that tool).
 *
 * Uses the same matcher as the runtime permission check (step 1a), so MCP
 * server-prefix rules like `mcp__server` strip all tools from that server
 * before the model sees them — not just at call time.
 */
export function filterToolsByDenyRules<
  T extends {
    name: string
    mcpInfo?: { serverName: string; toolName: string }
  },
>(tools: readonly T[], permissionContext: ToolPermissionContext): T[] {
  // getDenyRuleForTool returns a matching deny rule, or undefined if no deny
  // rule matches.  We keep the tool only when no deny rule exists.
  return tools.filter(tool => !getDenyRuleForTool(permissionContext, tool))
}

// ═════════════════════════════════════════════════════════════════════════════
// getTools() — SESSION-AWARE TOOL SELECTION
// ═════════════════════════════════════════════════════════════════════════════
// This is the **primary entry point** for determining which built-in tools the
// LLM sees in a given session.  It applies several layers of filtering on top
// of the exhaustive catalog from getAllBaseTools():
//
//   Layer 1 — Mode short-circuit:
//     • CLAUDE_CODE_SIMPLE ("bare mode"):  only Bash + FileRead + FileEdit
//       (optionally augmented with coordinator tools or collapsed into REPL).
//
//   Layer 2 — Special-tool exclusion:
//     • MCP resource tools and the synthetic output pseudo-tool are stripped
//       from the base list.  They're merged back later by assembleToolPool().
//
//   Layer 3 — Permission deny-rule filtering:
//     • Any tool that matches a blanket deny rule is removed.
//
//   Layer 4 — REPL mode collapsing:
//     • When the REPL tool is active, its primitive constituents (Bash, FileRead,
//       FileEdit, etc. — the REPL_ONLY_TOOLS set) are hidden from direct LLM
//       access because the REPL already wraps them inside a VM sandbox.
//
//   Layer 5 — Per-tool isEnabled() check:
//     • Each remaining tool's runtime isEnabled() method is called.  A tool may
//       disable itself at runtime (e.g. if a required binary isn't on PATH).
//
// The returned array is what gets serialized into the API request's `tools`
// parameter (alongside MCP tools added by assembleToolPool).

export const getTools = (permissionContext: ToolPermissionContext): Tools => {
  // ── Layer 1: CLAUDE_CODE_SIMPLE ("bare") mode ──────────────────────────
  // When set, drastically reduces the tool surface to the bare minimum:
  // Bash, FileRead, and FileEdit.  This is used for constrained environments
  // or lightweight agent configurations.
  // Simple mode: only Bash, Read, and Edit tools
  if (isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE)) {
    // --bare + REPL mode: REPL wraps Bash/Read/Edit/etc inside the VM, so
    // return REPL instead of the raw primitives. Matches the non-bare path
    // below which also hides REPL_ONLY_TOOLS when REPL is enabled.
    if (isReplModeEnabled() && REPLTool) {
      // In REPL+bare mode, the REPL tool replaces all primitive tools
      const replSimple: Tool[] = [REPLTool]
      // If coordinator mode is also active, the coordinator still needs
      // TaskStopTool and SendMessageTool for orchestration
      if (
        feature('COORDINATOR_MODE') &&
        coordinatorModeModule?.isCoordinatorMode()
      ) {
        replSimple.push(TaskStopTool, getSendMessageTool())
      }
      return filterToolsByDenyRules(replSimple, permissionContext)
    }
    // Standard bare mode: just the three core file/shell tools
    const simpleTools: Tool[] = [BashTool, FileReadTool, FileEditTool]
    // When coordinator mode is also active, include AgentTool and TaskStopTool
    // so the coordinator gets Task+TaskStop (via useMergedTools filtering) and
    // workers get Bash/Read/Edit (via filterToolsForAgent filtering).
    if (
      feature('COORDINATOR_MODE') &&
      coordinatorModeModule?.isCoordinatorMode()
    ) {
      simpleTools.push(AgentTool, TaskStopTool, getSendMessageTool())
    }
    // Apply deny-rule filtering even in bare mode
    return filterToolsByDenyRules(simpleTools, permissionContext)
  }

  // ── Layer 2: Exclude "special" tools from the base list ────────────────
  // These tools are handled separately:
  //   - MCP resource tools are merged in by assembleToolPool()
  //   - SYNTHETIC_OUTPUT_TOOL_NAME is a pseudo-tool, not a real LLM tool
  // Get all base tools and filter out special tools that get added conditionally
  const specialTools = new Set([
    ListMcpResourcesTool.name,
    ReadMcpResourceTool.name,
    SYNTHETIC_OUTPUT_TOOL_NAME,
  ])

  const tools = getAllBaseTools().filter(tool => !specialTools.has(tool.name))

  // ── Layer 3: Permission deny-rule filtering ────────────────────────────
  // Filter out tools that are denied by the deny rules
  let allowedTools = filterToolsByDenyRules(tools, permissionContext)

  // ── Layer 4: REPL mode collapsing ──────────────────────────────────────
  // When REPL mode is enabled, hide primitive tools from direct use.
  // They're still accessible inside REPL via the VM context.
  if (isReplModeEnabled()) {
    // Only collapse if the REPL tool itself survived deny-rule filtering
    const replEnabled = allowedTools.some(tool =>
      toolMatchesName(tool, REPL_TOOL_NAME),
    )
    if (replEnabled) {
      // Remove the tools that REPL subsumes (e.g. Bash, FileRead, FileEdit)
      allowedTools = allowedTools.filter(
        tool => !REPL_ONLY_TOOLS.has(tool.name),
      )
    }
  }

  // ── Layer 5: Per-tool runtime isEnabled() check ────────────────────────
  // Each tool may disable itself at runtime (e.g. missing dependency).
  // Evaluate isEnabled() once per tool to avoid repeated side effects.
  const isEnabled = allowedTools.map(_ => _.isEnabled())
  return allowedTools.filter((_, i) => isEnabled[i])
}

// ═════════════════════════════════════════════════════════════════════════════
// assembleToolPool() — FINAL TOOL POOL ASSEMBLY (built-in + MCP)
// ═════════════════════════════════════════════════════════════════════════════
// This is the function that produces the **actual tool array** sent to the
// Claude API in the `tools` parameter.  It:
//   1. Calls getTools() to get the filtered built-in tools.
//   2. Applies deny-rule filtering to the MCP tools (from connected MCP servers).
//   3. Sorts both partitions alphabetically for prompt-cache stability.
//   4. Concatenates them (built-ins first, then MCP) and deduplicates by name.
//
// The two-partition sort is intentional: built-in tools form a stable prefix
// that the server-side cache policy relies on.  Interleaving MCP tools would
// break cache keys whenever a new MCP tool is added.

/**
 * Assemble the full tool pool for a given permission context and MCP tools.
 *
 * This is the single source of truth for combining built-in tools with MCP tools.
 * Both REPL.tsx (via useMergedTools hook) and runAgent.ts (for coordinator workers)
 * use this function to ensure consistent tool pool assembly.
 *
 * The function:
 * 1. Gets built-in tools via getTools() (respects mode filtering)
 * 2. Filters MCP tools by deny rules
 * 3. Deduplicates by tool name (built-in tools take precedence)
 *
 * @param permissionContext - Permission context for filtering built-in tools
 * @param mcpTools - MCP tools from appState.mcp.tools
 * @returns Combined, deduplicated array of built-in and MCP tools
 */
export function assembleToolPool(
  permissionContext: ToolPermissionContext,
  mcpTools: Tools,
): Tools {
  // Step 1: Get session-filtered built-in tools
  const builtInTools = getTools(permissionContext)

  // Step 2: Apply deny rules to MCP tools (same filtering as built-ins)
  // Filter out MCP tools that are in the deny list
  const allowedMcpTools = filterToolsByDenyRules(mcpTools, permissionContext)

  // Step 3: Sort each partition independently, then concatenate and deduplicate.
  // Sort each partition for prompt-cache stability, keeping built-ins as a
  // contiguous prefix. The server's claude_code_system_cache_policy places a
  // global cache breakpoint after the last prefix-matched built-in tool; a flat
  // sort would interleave MCP tools into built-ins and invalidate all downstream
  // cache keys whenever an MCP tool sorts between existing built-ins. uniqBy
  // preserves insertion order, so built-ins win on name conflict.
  // Avoid Array.toSorted (Node 20+) — we support Node 18. builtInTools is
  // readonly so copy-then-sort; allowedMcpTools is a fresh .filter() result.
  const byName = (a: Tool, b: Tool) => a.name.localeCompare(b.name)
  // uniqBy keeps the first occurrence — since built-ins come first in the
  // concatenated array, they take precedence over MCP tools with the same name.
  return uniqBy(
    [...builtInTools].sort(byName).concat(allowedMcpTools.sort(byName)),
    'name',
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// getMergedTools() — SIMPLE MERGE (no dedup / no sort)
// ═════════════════════════════════════════════════════════════════════════════
// A lighter-weight merge that skips deduplication and sorting.  Used for
// contexts that just need a count or quick scan of all available tools (e.g.
// deciding whether to enable ToolSearchTool based on total tool count, or
// token-budget estimation).

/**
 * Get all tools including both built-in tools and MCP tools.
 *
 * This is the preferred function when you need the complete tools list for:
 * - Tool search threshold calculations (isToolSearchEnabled)
 * - Token counting that includes MCP tools
 * - Any context where MCP tools should be considered
 *
 * Use getTools() only when you specifically need just built-in tools.
 *
 * @param permissionContext - Permission context for filtering built-in tools
 * @param mcpTools - MCP tools from appState.mcp.tools
 * @returns Combined array of built-in and MCP tools
 */
export function getMergedTools(
  permissionContext: ToolPermissionContext,
  mcpTools: Tools,
): Tools {
  const builtInTools = getTools(permissionContext)
  // Simple concatenation — no dedup, no sort.  Caller handles any conflicts.
  return [...builtInTools, ...mcpTools]
}

