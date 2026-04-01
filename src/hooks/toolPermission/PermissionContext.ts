// =============================================================================
// PermissionContext.ts — Core permission decision context
// =============================================================================
//
// This module is the heart of the tool permission system. It provides:
//
// 1. **PermissionContext** — A frozen context object created per tool-use that
//    encapsulates all the state and methods needed to make, log, and persist
//    permission decisions (allow or deny).
//
// 2. **ResolveOnce** — A concurrency guard that ensures a permission prompt is
//    resolved exactly once, even when multiple async racers (user input, hooks,
//    classifier, bridge, channel) compete to settle the same decision.
//
// 3. **PermissionQueueOps** — A React-agnostic abstraction over the confirm
//    queue, allowing PermissionContext to push/remove/update queue entries
//    without depending on React state directly.
//
// PERMISSION DECISION FLOW (high level):
//   Tool use requested
//     → hasPermissionsToUseTool() checks config allow/deny lists
//     → If "ask", a PermissionContext is created
//     → Hooks, classifier, bridge, channel, and user input all race
//     → First to call claim()+resolve() wins; others are no-ops
//     → Decision is logged (analytics + OTel) and persisted if permanent
//
// See handlers/interactiveHandler.ts for the full racing logic.
// =============================================================================

import { feature } from 'bun:bundle'
import type { ContentBlockParam } from '@anthropic-ai/sdk/resources/messages.mjs'
import {
  type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
  logEvent,
} from 'src/services/analytics/index.js'
import { sanitizeToolNameForAnalytics } from 'src/services/analytics/metadata.js'
import type { ToolUseConfirm } from '../../components/permissions/PermissionRequest.js'
import type {
  ToolPermissionContext,
  Tool as ToolType,
  ToolUseContext,
} from '../../Tool.js'
import { awaitClassifierAutoApproval } from '../../tools/BashTool/bashPermissions.js'
import { BASH_TOOL_NAME } from '../../tools/BashTool/toolName.js'
import type { AssistantMessage } from '../../types/message.js'
import type {
  PendingClassifierCheck,
  PermissionAllowDecision,
  PermissionDecisionReason,
  PermissionDenyDecision,
} from '../../types/permissions.js'
import { setClassifierApproval } from '../../utils/classifierApprovals.js'
import { logForDebugging } from '../../utils/debug.js'
import { executePermissionRequestHooks } from '../../utils/hooks.js'
import {
  REJECT_MESSAGE,
  REJECT_MESSAGE_WITH_REASON_PREFIX,
  SUBAGENT_REJECT_MESSAGE,
  SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX,
  withMemoryCorrectionHint,
} from '../../utils/messages.js'
import type { PermissionDecision } from '../../utils/permissions/PermissionResult.js'
import {
  applyPermissionUpdates,
  persistPermissionUpdates,
  supportsPersistence,
} from '../../utils/permissions/PermissionUpdate.js'
import type { PermissionUpdate } from '../../utils/permissions/PermissionUpdateSchema.js'
import {
  logPermissionDecision,
  type PermissionDecisionArgs,
} from './permissionLogging.js'

// ---------------------------------------------------------------------------
// Source discriminators — used by analytics logging (permissionLogging.ts)
// to differentiate WHERE a permission decision came from.
// ---------------------------------------------------------------------------

// PermissionApprovalSource: identifies who approved a tool use.
//   - 'hook': A PermissionRequest hook approved it (may be permanent or temporary).
//   - 'user': The user approved it interactively (permanent = saved to settings).
//   - 'classifier': The bash safety classifier auto-approved it.
type PermissionApprovalSource =
  | { type: 'hook'; permanent?: boolean }
  | { type: 'user'; permanent: boolean }
  | { type: 'classifier' }

// PermissionRejectionSource: identifies who denied a tool use.
//   - 'hook': A PermissionRequest hook denied it.
//   - 'user_abort': The user aborted the operation (e.g., Ctrl+C).
//   - 'user_reject': The user explicitly denied it (may include feedback text).
type PermissionRejectionSource =
  | { type: 'hook' }
  | { type: 'user_abort' }
  | { type: 'user_reject'; hasFeedback: boolean }

// Generic interface for permission queue operations, decoupled from React.
// In the REPL, these are backed by React state.
// The confirm queue is the list of pending permission prompts shown to the user.
// Operations:
//   push   — Add a new permission prompt to the queue (tool wants permission).
//   remove — Remove a prompt from the queue (decision made or aborted).
//   update — Patch a queued prompt in-place (e.g., toggle classifier spinner).
type PermissionQueueOps = {
  push(item: ToolUseConfirm): void
  remove(toolUseID: string): void
  update(toolUseID: string, patch: Partial<ToolUseConfirm>): void
}

// ---------------------------------------------------------------------------
// ResolveOnce — Concurrency guard for the permission decision promise
// ---------------------------------------------------------------------------
// Multiple async paths race to settle a single permission decision:
//   - User interaction (allow/deny/abort in the terminal UI)
//   - PermissionRequest hooks (MCP extensions)
//   - Bash safety classifier (AI-based auto-approval)
//   - Bridge callbacks (claude.ai web UI responding remotely)
//   - Channel callbacks (Telegram, iMessage, etc.)
//
// ResolveOnce wraps the Promise's resolve function to ensure only the FIRST
// caller actually delivers a value. All subsequent calls are silently ignored.
//
// Two-phase guard:
//   claim()     — Atomically marks the decision as claimed. Returns true only
//                 for the first caller. Use this BEFORE any async work to close
//                 the TOCTOU window between checking isResolved() and calling
//                 resolve(). This is critical because an `await` between check
//                 and resolve would allow another racer to sneak in.
//   resolve()   — Delivers the value to the promise. Also sets claimed=true as
//                 a fallback for callers that skip claim() (synchronous paths).
//   isResolved()— Read-only check; returns true once claim() or resolve() fired.
// ---------------------------------------------------------------------------
type ResolveOnce<T> = {
  resolve(value: T): void
  isResolved(): boolean
  /**
   * Atomically check-and-mark as resolved. Returns true if this caller
   * won the race (nobody else has resolved yet), false otherwise.
   * Use this in async callbacks BEFORE awaiting, to close the window
   * between the `isResolved()` check and the actual `resolve()` call.
   */
  claim(): boolean
}

// Factory for creating ResolveOnce guards.
// `claimed` tracks whether any racer has staked ownership (via claim() or resolve()).
// `delivered` tracks whether the actual promise value has been delivered (via resolve()).
// This two-flag approach allows claim() to block future racers immediately,
// while resolve() can be called later after async work completes.
function createResolveOnce<T>(resolve: (value: T) => void): ResolveOnce<T> {
  let claimed = false   // true once any racer calls claim() or resolve()
  let delivered = false  // true once the promise value has been delivered
  return {
    resolve(value: T) {
      // Guard: only the first resolve() call delivers the value
      if (delivered) return
      delivered = true
      claimed = true  // Also mark claimed as a safety net
      resolve(value)
    },
    isResolved() {
      // Read-only: lets async callbacks bail early without side effects
      return claimed
    },
    claim() {
      // Atomic check-and-mark: returns true only for the first caller.
      // Must be called BEFORE any `await` in the callback to prevent
      // the TOCTOU race condition.
      if (claimed) return false
      claimed = true
      return true
    },
  }
}

// ---------------------------------------------------------------------------
// createPermissionContext — Factory for the per-tool-use permission context
// ---------------------------------------------------------------------------
// Created once per tool invocation that requires a permission decision.
// The returned context object is frozen (immutable) and contains:
//
// Parameters:
//   tool               — The tool definition (name, schema, validators).
//   input              — The raw input the model provided for the tool call.
//   toolUseContext      — Session-level context (abort controller, app state, options).
//   assistantMessage   — The assistant message that triggered this tool use.
//   toolUseID          — Unique identifier for this specific tool invocation.
//   setToolPermissionContext — Callback to update the app's permission context state
//                              (called after persisting permission rule changes).
//   queueOps           — Optional queue operations for managing the confirm UI queue.
//
// Methods on the returned context:
//   logDecision()       — Log a permission decision to analytics/OTel.
//   logCancelled()      — Log that this tool use was cancelled (user abort).
//   persistPermissions()— Write permission updates to disk and update app state.
//   resolveIfAborted()  — Check abort signal and resolve early if already aborted.
//   cancelAndAbort()    — Build a deny decision, optionally aborting the controller.
//   tryClassifier()     — (conditional) Run the bash safety classifier.
//   runHooks()          — Execute PermissionRequest hooks asynchronously.
//   buildAllow()        — Construct a PermissionAllowDecision object.
//   buildDeny()         — Construct a PermissionDenyDecision object.
//   handleUserAllow()   — Process a user's approval: persist + log + build allow.
//   handleHookAllow()   — Process a hook's approval: persist + log + build allow.
//   pushToQueue()       — Add a confirm entry to the UI permission queue.
//   removeFromQueue()   — Remove this tool's entry from the UI permission queue.
//   updateQueueItem()   — Patch this tool's queue entry in-place.
// ---------------------------------------------------------------------------
function createPermissionContext(
  tool: ToolType,
  input: Record<string, unknown>,
  toolUseContext: ToolUseContext,
  assistantMessage: AssistantMessage,
  toolUseID: string,
  setToolPermissionContext: (context: ToolPermissionContext) => void,
  queueOps?: PermissionQueueOps,
) {
  // Extract the message ID once — used as a correlation key in analytics events
  const messageId = assistantMessage.message.id
  const ctx = {
    // -----------------------------------------------------------------------
    // Read-only context properties — captured at creation time
    // -----------------------------------------------------------------------
    tool,
    input,
    toolUseContext,
    assistantMessage,
    messageId,
    toolUseID,

    // -----------------------------------------------------------------------
    // logDecision — Delegate to centralized permission analytics logger.
    // Allows callers to optionally override the input (e.g., when the user
    // edited the tool input before approving) and provide the prompt start
    // time for latency tracking.
    // -----------------------------------------------------------------------
    logDecision(
      args: PermissionDecisionArgs,
      opts?: {
        input?: Record<string, unknown>
        permissionPromptStartTimeMs?: number
      },
    ) {
      logPermissionDecision(
        {
          tool,
          input: opts?.input ?? input,
          toolUseContext,
          messageId,
          toolUseID,
        },
        args,
        opts?.permissionPromptStartTimeMs,
      )
    },
    // -----------------------------------------------------------------------
    // logCancelled — Fire an analytics event when the tool use is cancelled
    // (user abort or signal-driven cancellation). Distinct from reject because
    // the tool never ran and no feedback was provided.
    // -----------------------------------------------------------------------
    logCancelled() {
      logEvent('tengu_tool_use_cancelled', {
        messageID:
          messageId as AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
        toolName: sanitizeToolNameForAnalytics(tool.name),
      })
    },
    // -----------------------------------------------------------------------
    // persistPermissions — Write permission updates to disk and apply them
    // to the in-memory app state. Permission updates represent rules like
    // "always allow Edit for files in /home/user/project".
    //
    // Two-step process:
    //   1. persistPermissionUpdates() writes to ~/.claude/settings or project config
    //   2. applyPermissionUpdates() merges updates into the live app state
    //      via the setToolPermissionContext callback
    //
    // Returns true if any update was written to a persistent destination
    // (as opposed to session-only updates), so callers can log 'permanent'.
    // -----------------------------------------------------------------------
    async persistPermissions(updates: PermissionUpdate[]) {
      if (updates.length === 0) return false
      persistPermissionUpdates(updates)
      const appState = toolUseContext.getAppState()
      setToolPermissionContext(
        applyPermissionUpdates(appState.toolPermissionContext, updates),
      )
      return updates.some(update => supportsPersistence(update.destination))
    },
    // -----------------------------------------------------------------------
    // resolveIfAborted — Early-exit guard: if the abort signal has already
    // fired (e.g., user pressed Ctrl+C, or a sibling tool errored), resolve
    // the permission promise immediately with a cancel decision.
    // Returns true if it resolved (caller should stop), false to continue.
    // -----------------------------------------------------------------------
    resolveIfAborted(resolve: (decision: PermissionDecision) => void) {
      if (!toolUseContext.abortController.signal.aborted) return false
      this.logCancelled()
      resolve(this.cancelAndAbort(undefined, true))
      return true
    },
    // -----------------------------------------------------------------------
    // cancelAndAbort — Build a deny/ask decision and optionally abort the
    // session's abort controller. Used for:
    //   - User aborting (Ctrl+C / Esc)
    //   - User rejecting with optional feedback text
    //   - Hook-driven interrupts
    //
    // Behavior differs for subagents vs main agent:
    //   - Subagents use SUBAGENT_REJECT_MESSAGE (never get memory hints).
    //   - Main agent gets withMemoryCorrectionHint() to help the model learn.
    //
    // The abort controller is fired when:
    //   - isAbort is explicitly true (hard abort)
    //   - There's no feedback AND no content blocks AND it's not a subagent
    //     (i.e., a bare rejection with nothing useful to continue with)
    //
    // Returns { behavior: 'ask', message, contentBlocks } — the 'ask' behavior
    // tells the caller to pass the message back to the model as tool output.
    // -----------------------------------------------------------------------
    cancelAndAbort(
      feedback?: string,
      isAbort?: boolean,
      contentBlocks?: ContentBlockParam[],
    ): PermissionDecision {
      // Detect if this tool use is running inside a subagent
      const sub = !!toolUseContext.agentId
      // Build the rejection message: with or without user-provided feedback
      const baseMessage = feedback
        ? `${sub ? SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX : REJECT_MESSAGE_WITH_REASON_PREFIX}${feedback}`
        : sub
          ? SUBAGENT_REJECT_MESSAGE
          : REJECT_MESSAGE
      // Main-agent rejections get a memory correction hint appended so the
      // model can learn from the rejection and avoid repeating the same action
      const message = sub ? baseMessage : withMemoryCorrectionHint(baseMessage)
      // Decide whether to fire the abort controller (kills the entire turn)
      if (isAbort || (!feedback && !contentBlocks?.length && !sub)) {
        logForDebugging(
          `Aborting: tool=${tool.name} isAbort=${isAbort} hasFeedback=${!!feedback} isSubagent=${sub}`,
        )
        toolUseContext.abortController.abort()
      }
      return { behavior: 'ask', message, contentBlocks }
    },
    // -------------------------------------------------------------------
    // tryClassifier — Conditional: only present when BASH_CLASSIFIER feature
    // flag is enabled. Awaits the bash safety classifier's decision for
    // bash commands. The classifier is an AI model that evaluates whether
    // a bash command is safe to auto-approve without user interaction.
    //
    // Only applies to BASH_TOOL_NAME; returns null for all other tools
    // or if no classifier check is pending.
    //
    // When the TRANSCRIPT_CLASSIFIER feature is also enabled, matched
    // prompt rules are extracted and persisted via setClassifierApproval()
    // so subsequent identical commands can be auto-approved without
    // re-running the classifier.
    //
    // Returns a PermissionDecision (allow) if the classifier approves,
    // or null if it doesn't approve (caller falls through to next racer).
    // -------------------------------------------------------------------
    ...(feature('BASH_CLASSIFIER')
      ? {
          async tryClassifier(
            pendingClassifierCheck: PendingClassifierCheck | undefined,
            updatedInput: Record<string, unknown> | undefined,
          ): Promise<PermissionDecision | null> {
            if (tool.name !== BASH_TOOL_NAME || !pendingClassifierCheck) {
              return null  // Not a bash tool or no classifier check — skip
            }
            // Await the classifier's verdict (may take a few seconds for inference)
            const classifierDecision = await awaitClassifierAutoApproval(
              pendingClassifierCheck,
              toolUseContext.abortController.signal,
              toolUseContext.options.isNonInteractiveSession,
            )
            if (!classifierDecision) {
              return null  // Classifier didn't approve — fall through to next racer
            }
            // If the TRANSCRIPT_CLASSIFIER feature is on, extract the matched
            // prompt rule from the classifier's reason string and cache it.
            // This allows future invocations of the same command pattern to be
            // auto-approved without re-running the classifier inference.
            if (
              feature('TRANSCRIPT_CLASSIFIER') &&
              classifierDecision.type === 'classifier'
            ) {
              const matchedRule = classifierDecision.reason.match(
                /^Allowed by prompt rule: "(.+)"$/,
              )?.[1]
              if (matchedRule) {
                // Cache the matched rule so it can be checked on future tool uses
                setClassifierApproval(toolUseID, matchedRule)
              }
            }
            // Log the classifier's approval decision via the analytics pipeline
            logPermissionDecision(
              { tool, input, toolUseContext, messageId, toolUseID },
              { decision: 'accept', source: { type: 'classifier' } },
              undefined,
            )
            // Return the allow decision with the classifier's reason attached
            return {
              behavior: 'allow' as const,
              updatedInput: updatedInput ?? input,
              userModified: false,
              decisionReason: classifierDecision,
            }
          },
        }
      : {}),
    // -------------------------------------------------------------------
    // runHooks — Execute registered PermissionRequest hooks asynchronously.
    // Hooks are MCP-based extensions that can programmatically approve or
    // deny tool uses. They are iterated via an async generator — each hook
    // gets a chance to return a decision.
    //
    // Hook results are checked in order:
    //   - 'allow': Hook approved → persist any permission updates, log, return.
    //   - 'deny': Hook denied → log rejection, optionally abort, return deny.
    //   - No result: Continue to next hook.
    //
    // If no hook returns a decision, returns null so the caller can fall
    // through to the next decision source (classifier, user prompt, etc.).
    //
    // Parameters:
    //   permissionMode — Current permission mode (e.g., "plan", "auto-edit").
    //   suggestions    — Suggested permission updates from the initial check.
    //   updatedInput   — Optional modified input from a previous decision step.
    //   permissionPromptStartTimeMs — For latency tracking in analytics.
    // -------------------------------------------------------------------
    async runHooks(
      permissionMode: string | undefined,
      suggestions: PermissionUpdate[] | undefined,
      updatedInput?: Record<string, unknown>,
      permissionPromptStartTimeMs?: number,
    ): Promise<PermissionDecision | null> {
      // Iterate through each hook's results via the async generator
      for await (const hookResult of executePermissionRequestHooks(
        tool.name,
        toolUseID,
        input,
        toolUseContext,
        permissionMode,
        suggestions,
        toolUseContext.abortController.signal,
      )) {
        if (hookResult.permissionRequestResult) {
          const decision = hookResult.permissionRequestResult
          if (decision.behavior === 'allow') {
            // Hook approved: use the hook's updated input if provided,
            // otherwise fall back to the caller's updatedInput, then original input
            const finalInput = decision.updatedInput ?? updatedInput ?? input
            return await this.handleHookAllow(
              finalInput,
              decision.updatedPermissions ?? [],
              permissionPromptStartTimeMs,
            )
          } else if (decision.behavior === 'deny') {
            // Hook denied: log the rejection
            this.logDecision(
              { decision: 'reject', source: { type: 'hook' } },
              { permissionPromptStartTimeMs },
            )
            // If the hook set interrupt=true, abort the entire session turn
            if (decision.interrupt) {
              logForDebugging(
                `Hook interrupt: tool=${tool.name} hookMessage=${decision.message}`,
              )
              toolUseContext.abortController.abort()
            }
            // Return a deny decision with the hook's message and reason metadata
            return this.buildDeny(
              decision.message || 'Permission denied by hook',
              {
                type: 'hook',
                hookName: 'PermissionRequest',
                reason: decision.message,
              },
            )
          }
        }
      }
      // No hook returned a decision — return null so the caller falls through
      return null
    },
    // -------------------------------------------------------------------
    // buildAllow — Pure factory: construct a PermissionAllowDecision without
    // side effects. Does NOT log or persist — that's the caller's job.
    // Used by handleUserAllow() and handleHookAllow() after they've done
    // their own logging and persistence.
    // -------------------------------------------------------------------
    buildAllow(
      updatedInput: Record<string, unknown>,
      opts?: {
        userModified?: boolean
        decisionReason?: PermissionDecisionReason
        acceptFeedback?: string
        contentBlocks?: ContentBlockParam[]
      },
    ): PermissionAllowDecision {
      return {
        behavior: 'allow' as const,
        updatedInput,
        userModified: opts?.userModified ?? false,
        ...(opts?.decisionReason && { decisionReason: opts.decisionReason }),
        ...(opts?.acceptFeedback && { acceptFeedback: opts.acceptFeedback }),
        ...(opts?.contentBlocks &&
          opts.contentBlocks.length > 0 && {
            contentBlocks: opts.contentBlocks,
          }),
      }
    },
    // -------------------------------------------------------------------
    // buildDeny — Pure factory: construct a PermissionDenyDecision without
    // side effects. Pairs with buildAllow() for the deny case.
    // -------------------------------------------------------------------
    buildDeny(
      message: string,
      decisionReason: PermissionDecisionReason,
    ): PermissionDenyDecision {
      return { behavior: 'deny' as const, message, decisionReason }
    },
    // -------------------------------------------------------------------
    // handleUserAllow — Full approval pipeline when the USER approves:
    //   1. Persist any permission updates (e.g., "always allow Edit in /proj")
    //   2. Log the decision to analytics with source='user'
    //   3. Detect whether the user modified the input (via tool.inputsEquivalent)
    //   4. Build and return the allow decision with optional feedback text
    //
    // Called from the onAllow callback in interactiveHandler.ts and
    // the swarm worker's onAllow callback.
    // -------------------------------------------------------------------
    async handleUserAllow(
      updatedInput: Record<string, unknown>,
      permissionUpdates: PermissionUpdate[],
      feedback?: string,
      permissionPromptStartTimeMs?: number,
      contentBlocks?: ContentBlockParam[],
      decisionReason?: PermissionDecisionReason,
    ): Promise<PermissionAllowDecision> {
      // Step 1: Persist permission updates to disk and update app state
      const acceptedPermanentUpdates =
        await this.persistPermissions(permissionUpdates)
      // Step 2: Log the accept decision with permanent/temporary distinction
      this.logDecision(
        {
          decision: 'accept',
          source: { type: 'user', permanent: acceptedPermanentUpdates },
        },
        { input: updatedInput, permissionPromptStartTimeMs },
      )
      // Step 3: Check if the user modified the tool input before approving.
      // Uses the tool's custom inputsEquivalent() comparator if available.
      const userModified = tool.inputsEquivalent
        ? !tool.inputsEquivalent(input, updatedInput)
        : false
      // Step 4: Trim feedback and build the final allow decision
      const trimmedFeedback = feedback?.trim()
      return this.buildAllow(updatedInput, {
        userModified,
        decisionReason,
        acceptFeedback: trimmedFeedback || undefined,
        contentBlocks,
      })
    },
    // -------------------------------------------------------------------
    // handleHookAllow — Full approval pipeline when a HOOK approves:
    //   1. Persist any permission updates the hook provided
    //   2. Log the decision to analytics with source='hook'
    //   3. Build the allow decision with decisionReason='hook'
    //
    // Similar to handleUserAllow but simpler: hooks don't modify input,
    // don't provide feedback, and the reason is always 'PermissionRequest'.
    // -------------------------------------------------------------------
    async handleHookAllow(
      finalInput: Record<string, unknown>,
      permissionUpdates: PermissionUpdate[],
      permissionPromptStartTimeMs?: number,
    ): Promise<PermissionAllowDecision> {
      const acceptedPermanentUpdates =
        await this.persistPermissions(permissionUpdates)
      this.logDecision(
        {
          decision: 'accept',
          source: { type: 'hook', permanent: acceptedPermanentUpdates },
        },
        { input: finalInput, permissionPromptStartTimeMs },
      )
      return this.buildAllow(finalInput, {
        decisionReason: { type: 'hook', hookName: 'PermissionRequest' },
      })
    },
    // -------------------------------------------------------------------
    // Queue operations — Delegate to the PermissionQueueOps adapter.
    // These methods manage the UI confirm queue that shows pending
    // permission prompts to the user. The queue is React state in the
    // REPL but abstracted here for testability.
    // -------------------------------------------------------------------

    // pushToQueue — Add this tool's permission prompt to the confirm queue
    pushToQueue(item: ToolUseConfirm) {
      queueOps?.push(item)
    },
    // removeFromQueue — Remove this tool's entry (decision made or aborted)
    removeFromQueue() {
      queueOps?.remove(toolUseID)
    },
    // updateQueueItem — Patch this tool's queue entry (e.g., classifier spinner)
    updateQueueItem(patch: Partial<ToolUseConfirm>) {
      queueOps?.update(toolUseID, patch)
    },
  }
  // Freeze the context to prevent accidental mutation — the permission context
  // is shared across multiple async racers and must remain immutable.
  return Object.freeze(ctx)
}

// Infer the PermissionContext type from the factory's return type.
// This ensures the type stays in sync with the implementation automatically.
type PermissionContext = ReturnType<typeof createPermissionContext>

// ---------------------------------------------------------------------------
// createPermissionQueueOps — Bridge between React state and PermissionContext
// ---------------------------------------------------------------------------
// Adapts React's setToolUseConfirmQueue state setter into the generic
// PermissionQueueOps interface used by PermissionContext. Each operation
// uses functional state updates (prev => next) to avoid stale-closure bugs,
// since multiple permission prompts can be active simultaneously.
// ---------------------------------------------------------------------------

/**
 * Create a PermissionQueueOps backed by a React state setter.
 * This is the bridge between React's `setToolUseConfirmQueue` and the
 * generic queue interface used by PermissionContext.
 */
function createPermissionQueueOps(
  setToolUseConfirmQueue: React.Dispatch<
    React.SetStateAction<ToolUseConfirm[]>
  >,
): PermissionQueueOps {
  return {
    // Append a new confirm entry to the queue (immutable array spread)
    push(item: ToolUseConfirm) {
      setToolUseConfirmQueue(queue => [...queue, item])
    },
    // Remove a confirm entry by toolUseID (immutable filter)
    remove(toolUseID: string) {
      setToolUseConfirmQueue(queue =>
        queue.filter(item => item.toolUseID !== toolUseID),
      )
    },
    // Patch a confirm entry in-place by toolUseID (immutable map + spread)
    update(toolUseID: string, patch: Partial<ToolUseConfirm>) {
      setToolUseConfirmQueue(queue =>
        queue.map(item =>
          item.toolUseID === toolUseID ? { ...item, ...patch } : item,
        ),
      )
    },
  }
}

export { createPermissionContext, createPermissionQueueOps, createResolveOnce }
export type {
  PermissionContext,
  PermissionApprovalSource,
  PermissionQueueOps,
  PermissionRejectionSource,
  ResolveOnce,
}

