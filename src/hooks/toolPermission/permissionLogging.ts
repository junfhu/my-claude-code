// =============================================================================
// permissionLogging.ts — Centralized analytics/telemetry for permission decisions
// =============================================================================
//
// Every permission approve/reject event in the system flows through the
// logPermissionDecision() function defined here. It fans out to four sinks:
//
//   1. **Statsig Analytics** — Distinct event names per source type for funnel
//      analysis (e.g., tengu_tool_use_granted_in_prompt_permanent vs _temporary).
//
//   2. **OTel Telemetry** — A single 'tool_decision' event with structured
//      attributes for backend observability and alerting.
//
//   3. **Code Edit Metrics** — An OTel counter specifically for code editing tools
//      (Edit, Write, NotebookEdit) with language attribution from file paths.
//
//   4. **ToolUseContext Decision Map** — Persists the decision on the context object
//      so downstream code (e.g., tool execution, streaming) can inspect what happened.
//
// This module also provides helpers for:
//   - sourceToString(): Flattens structured source types into string labels.
//   - isCodeEditingTool(): Checks if a tool name is in the code-editing set.
//   - buildCodeEditToolAttributes(): Derives language from file paths for OTel.
// =============================================================================

// Centralized analytics/telemetry logging for tool permission decisions.
// All permission approve/reject events flow through logPermissionDecision(),
// which fans out to Statsig analytics, OTel telemetry, and code-edit metrics.
import { feature } from 'bun:bundle'
import {
  type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
  logEvent,
} from 'src/services/analytics/index.js'
import { sanitizeToolNameForAnalytics } from 'src/services/analytics/metadata.js'
import { getCodeEditToolDecisionCounter } from '../../bootstrap/state.js'
import type { Tool as ToolType, ToolUseContext } from '../../Tool.js'
import { getLanguageName } from '../../utils/cliHighlight.js'
import { SandboxManager } from '../../utils/sandbox/sandbox-adapter.js'
import { logOTelEvent } from '../../utils/telemetry/events.js'
import type {
  PermissionApprovalSource,
  PermissionRejectionSource,
} from './PermissionContext.js'

// ---------------------------------------------------------------------------
// Context type — passed by callers to identify WHICH tool use is being logged.
// Contains the tool definition, raw input, session context, and IDs.
// ---------------------------------------------------------------------------
type PermissionLogContext = {
  tool: ToolType               // Tool definition (name, schema, getPath, etc.)
  input: unknown               // Raw tool input (may be parsed to extract file path)
  toolUseContext: ToolUseContext // Session-level context (abort controller, app state)
  messageId: string            // Correlation ID for the assistant message
  toolUseID: string            // Unique ID for this specific tool invocation
}

// Discriminated union for decision args — ensures 'accept' is always paired
// with an approval source and 'reject' with a rejection source. The 'config'
// literal is used when a tool is auto-approved/denied by settings (no human).
// Discriminated union: 'accept' pairs with approval sources, 'reject' with rejection sources
type PermissionDecisionArgs =
  | { decision: 'accept'; source: PermissionApprovalSource | 'config' }
  | { decision: 'reject'; source: PermissionRejectionSource | 'config' }

// The set of tools considered "code editing" for OTel counter metrics.
// These tools modify source files and warrant separate language-attributed tracking.
const CODE_EDITING_TOOLS = ['Edit', 'Write', 'NotebookEdit']

// Check if a tool is a code-editing tool (used for OTel counter gating)
function isCodeEditingTool(toolName: string): boolean {
  return CODE_EDITING_TOOLS.includes(toolName)
}

// ---------------------------------------------------------------------------
// buildCodeEditToolAttributes — Enriches OTel counter attributes with language
// ---------------------------------------------------------------------------
// For code-editing tools, extracts the target file path from the tool's input
// schema and resolves it to a programming language name (e.g., "TypeScript",
// "Python"). This allows OTel dashboards to break down code-edit approval/
// rejection rates by language.
//
// If the tool doesn't expose a getPath() method, or the input fails to parse,
// the language attribute is simply omitted.
// ---------------------------------------------------------------------------
// Builds OTel counter attributes for code editing tools, enriching with
// language when the tool's target file path can be extracted from input
async function buildCodeEditToolAttributes(
  tool: ToolType,
  input: unknown,
  decision: 'accept' | 'reject',
  source: string,
): Promise<Record<string, string>> {
  // Derive language from file path if the tool exposes one (e.g., Edit, Write).
  // tool.getPath() extracts the file path from the parsed input, then
  // getLanguageName() maps the file extension to a human-readable language.
  // Derive language from file path if the tool exposes one (e.g., Edit, Write)
  let language: string | undefined
  if (tool.getPath && input) {
    const parseResult = tool.inputSchema.safeParse(input)
    if (parseResult.success) {
      const filePath = tool.getPath(parseResult.data)
      if (filePath) {
        language = await getLanguageName(filePath)
      }
    }
  }

  // Return the attributes object, conditionally including language if resolved
  return {
    decision,
    source,
    tool_name: tool.name,
    ...(language && { language }),
  }
}

// ---------------------------------------------------------------------------
// sourceToString — Converts structured source types to flat string labels
// ---------------------------------------------------------------------------
// Used for both analytics metadata and OTel event attributes. The string
// representation must be stable (changing it breaks existing dashboards).
//
// Mapping:
//   classifier        → 'classifier'
//   hook              → 'hook'
//   user (permanent)  → 'user_permanent'
//   user (temporary)  → 'user_temporary'
//   user_abort        → 'user_abort'
//   user_reject       → 'user_reject'
// ---------------------------------------------------------------------------
// Flattens structured source into a string label for analytics/OTel events
function sourceToString(
  source: PermissionApprovalSource | PermissionRejectionSource,
): string {
  // Check classifier first (it's feature-gated and has its own type)
  if (
    (feature('BASH_CLASSIFIER') || feature('TRANSCRIPT_CLASSIFIER')) &&
    source.type === 'classifier'
  ) {
    return 'classifier'
  }
  // Map remaining source types to their string labels
  switch (source.type) {
    case 'hook':
      return 'hook'
    case 'user':
      return source.permanent ? 'user_permanent' : 'user_temporary'
    case 'user_abort':
      return 'user_abort'
    case 'user_reject':
      return 'user_reject'
    default:
      return 'unknown'
  }
}

// ---------------------------------------------------------------------------
// baseMetadata — Shared metadata fields included in all analytics events.
// Contains the message ID (correlation key), sanitized tool name, sandbox
// status, and optionally the wait time (how long the user was prompted).
// The wait time is only included when the user was actually prompted (not
// for auto-approved events like config or classifier decisions).
// ---------------------------------------------------------------------------
function baseMetadata(
  messageId: string,
  toolName: string,
  waitMs: number | undefined,
): { [key: string]: boolean | number | undefined } {
  return {
    messageID:
      messageId as AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
    toolName: sanitizeToolNameForAnalytics(toolName),
    sandboxEnabled: SandboxManager.isSandboxingEnabled(),
    // Only include wait time when the user was actually prompted (not auto-approved)
    ...(waitMs !== undefined && { waiting_for_user_permission_ms: waitMs }),
  }
}

// ---------------------------------------------------------------------------
// logApprovalEvent — Emits a distinct analytics event per approval source.
// ---------------------------------------------------------------------------
// Each source type gets its own event name for funnel analysis:
//   - config     → tengu_tool_use_granted_in_config (no wait time)
//   - classifier → tengu_tool_use_granted_by_classifier
//   - user       → tengu_tool_use_granted_in_prompt_permanent OR _temporary
//   - hook       → tengu_tool_use_granted_by_permission_hook
//
// Distinct event names allow each step of the permission funnel to be
// measured independently in the analytics dashboard.
// ---------------------------------------------------------------------------
// Emits a distinct analytics event name per approval source for funnel analysis
function logApprovalEvent(
  tool: ToolType,
  messageId: string,
  source: PermissionApprovalSource | 'config',
  waitMs: number | undefined,
): void {
  if (source === 'config') {
    // Auto-approved by allowlist in settings — no user wait time.
    // Config approvals never have a wait time since no prompt was shown.
    // Auto-approved by allowlist in settings -- no user wait time
    logEvent(
      'tengu_tool_use_granted_in_config',
      baseMetadata(messageId, tool.name, undefined),
    )
    return
  }
  // Classifier auto-approval (feature-gated)
  if (
    (feature('BASH_CLASSIFIER') || feature('TRANSCRIPT_CLASSIFIER')) &&
    source.type === 'classifier'
  ) {
    logEvent(
      'tengu_tool_use_granted_by_classifier',
      baseMetadata(messageId, tool.name, waitMs),
    )
    return
  }
  // User and hook approvals — use a switch to handle each source type
  switch (source.type) {
    case 'user':
      // User approval: distinguish permanent (saved to settings) vs temporary
      logEvent(
        source.permanent
          ? 'tengu_tool_use_granted_in_prompt_permanent'
          : 'tengu_tool_use_granted_in_prompt_temporary',
        baseMetadata(messageId, tool.name, waitMs),
      )
      break
    case 'hook':
      // Hook approval: includes a 'permanent' flag in metadata to track
      // whether the hook's permission update was saved to a persistent destination
      logEvent('tengu_tool_use_granted_by_permission_hook', {
        ...baseMetadata(messageId, tool.name, waitMs),
        permanent: source.permanent ?? false,
      })
      break
    default:
      break
  }
}

// ---------------------------------------------------------------------------
// logRejectionEvent — Emits analytics events for permission rejections.
// ---------------------------------------------------------------------------
// Unlike approvals (which have distinct event names per source), rejections
// share a single event name (tengu_tool_use_rejected_in_prompt) with metadata
// fields to distinguish the source type:
//   - config      → tengu_tool_use_denied_in_config (separate event)
//   - hook        → isHook=true in metadata
//   - user_reject → hasFeedback=true/false in metadata
//   - user_abort  → hasFeedback=false in metadata
//
// This design keeps the rejection funnel simple while still allowing
// breakdown by source type via metadata filtering.
// ---------------------------------------------------------------------------
// Rejections share a single event name, differentiated by metadata fields
function logRejectionEvent(
  tool: ToolType,
  messageId: string,
  source: PermissionRejectionSource | 'config',
  waitMs: number | undefined,
): void {
  if (source === 'config') {
    // Denied by denylist in settings — separate event, no wait time
    // Denied by denylist in settings
    logEvent(
      'tengu_tool_use_denied_in_config',
      baseMetadata(messageId, tool.name, undefined),
    )
    return
  }
  // All non-config rejections share one event name, differentiated by metadata.
  // Hook rejections get isHook=true; user rejections get hasFeedback flag.
  logEvent('tengu_tool_use_rejected_in_prompt', {
    ...baseMetadata(messageId, tool.name, waitMs),
    // Distinguish hook rejections from user rejections via separate fields
    ...(source.type === 'hook'
      ? { isHook: true }
      : {
          hasFeedback:
            source.type === 'user_reject' ? source.hasFeedback : false,
        }),
  })
}

// ---------------------------------------------------------------------------
// logPermissionDecision — THE single entry point for ALL permission logging.
// ---------------------------------------------------------------------------
// Called by PermissionContext methods (handleUserAllow, handleHookAllow, etc.)
// and directly by handler callbacks after every approve/reject decision.
//
// This function fans out to four logging sinks:
//
// SINK 1: Analytics Events (Statsig)
//   - Calls logApprovalEvent() or logRejectionEvent() based on the decision.
//   - These emit distinct event names for funnel analysis.
//
// SINK 2: Code Edit Tool OTel Counter
//   - Only for Edit/Write/NotebookEdit tools.
//   - Increments an OTel counter with language + decision + source attributes.
//   - Async (fire-and-forget via void) because getLanguageName() reads disk.
//
// SINK 3: ToolUseContext Decision Map
//   - Persists the decision (source, decision, timestamp) in a Map on the
//     toolUseContext so downstream code can inspect what happened to each tool use.
//
// SINK 4: OTel Event (tool_decision)
//   - A single structured event for backend observability (OpenTelemetry).
//
// Parameters:
//   ctx                         — Identifies which tool use is being logged.
//   args                        — The decision (accept/reject) and its source.
//   permissionPromptStartTimeMs — Optional: when the prompt was shown (for wait time).
// ---------------------------------------------------------------------------
// Single entry point for all permission decision logging. Called by permission
// handlers after every approve/reject. Fans out to: analytics events, OTel
// telemetry, code-edit OTel counters, and toolUseContext decision storage.
function logPermissionDecision(
  ctx: PermissionLogContext,
  args: PermissionDecisionArgs,
  permissionPromptStartTimeMs?: number,
): void {
  const { tool, input, toolUseContext, messageId, toolUseID } = ctx
  const { decision, source } = args

  // Calculate how long the user waited at the permission prompt (if applicable).
  // This is only meaningful when a prompt was actually shown to the user.
  const waiting_for_user_permission_ms =
    permissionPromptStartTimeMs !== undefined
      ? Date.now() - permissionPromptStartTimeMs
      : undefined

  // SINK 1: Log the analytics event (Statsig).
  // Dispatch to the appropriate event logger based on the decision type.
  // Log the analytics event
  if (args.decision === 'accept') {
    logApprovalEvent(
      tool,
      messageId,
      args.source,
      waiting_for_user_permission_ms,
    )
  } else {
    logRejectionEvent(
      tool,
      messageId,
      args.source,
      waiting_for_user_permission_ms,
    )
  }

  // Flatten the structured source into a string label for use in remaining sinks
  const sourceString = source === 'config' ? 'config' : sourceToString(source)

  // SINK 2: Track code editing tool metrics (OTel counter).
  // Fire-and-forget because buildCodeEditToolAttributes is async (reads file).
  // Track code editing tool metrics
  if (isCodeEditingTool(tool.name)) {
    void buildCodeEditToolAttributes(tool, input, decision, sourceString).then(
      attributes => getCodeEditToolDecisionCounter()?.add(1, attributes),
    )
  }

  // SINK 3: Persist decision on the toolUseContext so downstream code can
  // inspect what happened (e.g., StreamingToolExecutor checking if user modified input).
  // Lazily initializes the Map on first use.
  // Persist decision on the context so downstream code can inspect what happened
  if (!toolUseContext.toolDecisions) {
    toolUseContext.toolDecisions = new Map()
  }
  toolUseContext.toolDecisions.set(toolUseID, {
    source: sourceString,
    decision,
    timestamp: Date.now(),
  })

  // SINK 4: Log a structured OTel event for backend observability.
  // Contains decision, source, and sanitized tool name as attributes.
  void logOTelEvent('tool_decision', {
    decision,
    source: sourceString,
    tool_name: sanitizeToolNameForAnalytics(tool.name),
  })
}

export { isCodeEditingTool, buildCodeEditToolAttributes, logPermissionDecision }
export type { PermissionLogContext, PermissionDecisionArgs }

