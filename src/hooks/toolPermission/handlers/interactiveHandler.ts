// =============================================================================
// interactiveHandler.ts — Interactive (main-agent) permission flow handler
// =============================================================================
//
// This is the most complex permission handler. It orchestrates a multi-way race
// between up to 5 concurrent permission decision sources:
//
//   1. LOCAL USER — The user interacts with the terminal permission dialog
//      (allow/deny/abort via keyboard).
//
//   2. PERMISSION HOOKS — MCP-based extensions that can programmatically approve
//      or deny tool uses (e.g., a corporate policy hook).
//
//   3. BASH CLASSIFIER — An AI model that evaluates bash commands for safety
//      and can auto-approve safe commands (feature-flagged: BASH_CLASSIFIER).
//
//   4. BRIDGE (CCR) — The claude.ai web UI can respond to permission prompts
//      remotely when the CLI is connected via the bridge.
//
//   5. CHANNEL RELAY — External messaging channels (Telegram, iMessage, etc.)
//      can approve/deny via their MCP server connections (feature-flagged: KAIROS).
//
// RACE RESOLUTION:
//   All 5 sources share a single ResolveOnce guard (from PermissionContext.ts).
//   The first source to call claim() wins; all others silently no-op.
//   Each winning source is responsible for:
//     - Cleaning up the other sources (cancel bridge, unsubscribe channel, etc.)
//     - Removing the confirm entry from the UI queue
//     - Logging the decision
//     - Resolving the promise
//
// KEY PATTERNS:
//   - claim() before await: Every callback calls claim() BEFORE any async work
//     to atomically win the race. This prevents the TOCTOU bug where an await
//     between isResolved() and resolve() lets another racer sneak in.
//   - userInteracted flag: Once the user starts interacting with the dialog
//     (arrow keys, typing), the classifier is suppressed since the user has
//     taken ownership of the decision.
//   - Grace period: A 200ms grace period ignores accidental keypresses that
//     would prematurely cancel the classifier check.
// =============================================================================

import { feature } from 'bun:bundle'
import type { ContentBlockParam } from '@anthropic-ai/sdk/resources/messages.mjs'
import { randomUUID } from 'crypto'
import { logForDebugging } from 'src/utils/debug.js'
import { getAllowedChannels } from '../../../bootstrap/state.js'
import type { BridgePermissionCallbacks } from '../../../bridge/bridgePermissionCallbacks.js'
import { getTerminalFocused } from '../../../ink/terminal-focus-state.js'
import {
  CHANNEL_PERMISSION_REQUEST_METHOD,
  type ChannelPermissionRequestParams,
  findChannelEntry,
} from '../../../services/mcp/channelNotification.js'
import type { ChannelPermissionCallbacks } from '../../../services/mcp/channelPermissions.js'
import {
  filterPermissionRelayClients,
  shortRequestId,
  truncateForPreview,
} from '../../../services/mcp/channelPermissions.js'
import { executeAsyncClassifierCheck } from '../../../tools/BashTool/bashPermissions.js'
import { BASH_TOOL_NAME } from '../../../tools/BashTool/toolName.js'
import {
  clearClassifierChecking,
  setClassifierApproval,
  setClassifierChecking,
  setYoloClassifierApproval,
} from '../../../utils/classifierApprovals.js'
import { errorMessage } from '../../../utils/errors.js'
import type { PermissionDecision } from '../../../utils/permissions/PermissionResult.js'
import type { PermissionUpdate } from '../../../utils/permissions/PermissionUpdateSchema.js'
import { hasPermissionsToUseTool } from '../../../utils/permissions/permissions.js'
import type { PermissionContext } from '../PermissionContext.js'
import { createResolveOnce } from '../PermissionContext.js'

// Parameters for the interactive permission handler.
// All the context needed to set up the multi-way race between decision sources.
type InteractivePermissionParams = {
  ctx: PermissionContext                         // Per-tool-use permission context (frozen)
  description: string                            // Human-readable description of what the tool wants to do
  result: PermissionDecision & { behavior: 'ask' } // The initial permission check result (must be 'ask')
  awaitAutomatedChecksBeforeDialog: boolean | undefined // If true, hooks+classifier already ran (coordinator path)
  bridgeCallbacks?: BridgePermissionCallbacks    // Optional: callbacks for CCR bridge communication
  channelCallbacks?: ChannelPermissionCallbacks  // Optional: callbacks for channel relay communication
}

/**
 * Handles the interactive (main-agent) permission flow.
 *
 * Pushes a ToolUseConfirm entry to the confirm queue with callbacks:
 * onAbort, onAllow, onReject, recheckPermission, onUserInteraction.
 *
 * Runs permission hooks and bash classifier checks asynchronously in the
 * background, racing them against user interaction. Uses a resolve-once
 * guard and `userInteracted` flag to prevent multiple resolutions.
 *
 * This function does NOT return a Promise -- it sets up callbacks that
 * eventually call `resolve()` to resolve the outer promise owned by
 * the caller.
 */
function handleInteractivePermission(
  params: InteractivePermissionParams,
  resolve: (decision: PermissionDecision) => void,
): void {
  const {
    ctx,
    description,
    result,
    awaitAutomatedChecksBeforeDialog,
    bridgeCallbacks,
    channelCallbacks,
  } = params

  // ---------------------------------------------------------------------------
  // STEP 1: Initialize the resolve-once guard and race state variables
  // ---------------------------------------------------------------------------

  // Create the resolve-once guard — wraps the raw `resolve` callback with
  // claim()/isResolved() to ensure exactly one racer delivers the final decision.
  const { resolve: resolveOnce, isResolved, claim } = createResolveOnce(resolve)

  // Flag: set to true once the user interacts with the permission dialog.
  // When true, the classifier is suppressed (user has taken ownership).
  let userInteracted = false

  // Timer handle for the classifier auto-approve checkmark animation.
  // When the classifier wins, a ✓ is shown for a few seconds before removal.
  let checkmarkTransitionTimer: ReturnType<typeof setTimeout> | undefined

  // Hoisted so onDismissCheckmark (Esc during checkmark window) can also
  // remove the abort listener — not just the timer callback.
  let checkmarkAbortHandler: (() => void) | undefined

  // Generate a unique request ID for bridge communication (only if bridge is active).
  const bridgeRequestId = bridgeCallbacks ? randomUUID() : undefined

  // Hoisted so local/hook/classifier wins can remove the pending channel
  // entry. No "tell remote to dismiss" equivalent — the text sits in your
  // phone, and a stale "yes abc123" after local-resolve falls through
  // tryConsumeReply (entry gone) and gets enqueued as normal chat.
  let channelUnsubscribe: (() => void) | undefined

  // Record when the permission prompt was shown — used for latency analytics.
  const permissionPromptStartTimeMs = Date.now()

  // Use the updated input from the initial permission check if available,
  // otherwise fall back to the original input from the tool call.
  const displayInput = result.updatedInput ?? ctx.input

  // Helper: remove the "classifier running" spinner from the queue item UI.
  function clearClassifierIndicator(): void {
    if (feature('BASH_CLASSIFIER')) {
      ctx.updateQueueItem({ classifierCheckInProgress: false })
    }
  }

  // ---------------------------------------------------------------------------
  // STEP 2: Push the permission prompt to the UI confirm queue
  // ---------------------------------------------------------------------------
  // This adds a ToolUseConfirm entry to the React state queue, which renders
  // the permission dialog in the terminal UI. The entry includes callbacks
  // (onAbort, onAllow, onReject, recheckPermission, onUserInteraction) that
  // the UI invokes when the user interacts with the dialog.
  //
  // RACE SOURCE 1: LOCAL USER — These callbacks are the "user" racer in the
  // multi-way race. Each callback calls claim() to atomically win before any
  // async work, then cleans up other racers and resolves the promise.
  // ---------------------------------------------------------------------------
  ctx.pushToQueue({
    assistantMessage: ctx.assistantMessage,
    tool: ctx.tool,
    description,
    input: displayInput,
    toolUseContext: ctx.toolUseContext,
    toolUseID: ctx.toolUseID,
    permissionResult: result,
    permissionPromptStartTimeMs,
    // Show the classifier spinner in the UI only if:
    // - A classifier check is pending AND
    // - We're NOT in the coordinator path (where checks already ran before dialog)
    ...(feature('BASH_CLASSIFIER')
      ? {
          classifierCheckInProgress:
            !!result.pendingClassifierCheck &&
            !awaitAutomatedChecksBeforeDialog,
        }
      : {}),

    // -------------------------------------------------------------------------
    // CALLBACK: onUserInteraction — Fired when the user starts interacting
    // with the permission dialog (arrow keys, tab, typing feedback).
    // Suppresses the classifier auto-approve since the user has taken over.
    // -------------------------------------------------------------------------
    onUserInteraction() {
      // Called when user starts interacting with the permission dialog
      // (e.g., arrow keys, tab, typing feedback)
      // Hide the classifier indicator since auto-approve is no longer possible
      //
      // Grace period: ignore interactions in the first 200ms to prevent
      // accidental keypresses from canceling the classifier prematurely
      const GRACE_PERIOD_MS = 200
      if (Date.now() - permissionPromptStartTimeMs < GRACE_PERIOD_MS) {
        return
      }
      userInteracted = true
      clearClassifierChecking(ctx.toolUseID)
      clearClassifierIndicator()
    },
    // -------------------------------------------------------------------------
    // CALLBACK: onDismissCheckmark — Fired when the user presses Esc during
    // the classifier auto-approve checkmark animation window. Clears the
    // timer and removes the dialog immediately instead of waiting for the
    // animation to finish.
    // -------------------------------------------------------------------------
    onDismissCheckmark() {
      if (checkmarkTransitionTimer) {
        clearTimeout(checkmarkTransitionTimer)
        checkmarkTransitionTimer = undefined
        if (checkmarkAbortHandler) {
          ctx.toolUseContext.abortController.signal.removeEventListener(
            'abort',
            checkmarkAbortHandler,
          )
          checkmarkAbortHandler = undefined
        }
        ctx.removeFromQueue()
      }
    },
    // -------------------------------------------------------------------------
    // CALLBACK: onAbort — Fired when the user aborts (e.g., Ctrl+C / Esc).
    // Uses claim() to atomically win the race, then cleans up bridge/channel
    // and resolves with a cancel decision. Aborts the session.
    // -------------------------------------------------------------------------
    onAbort() {
      // claim() is the atomic race guard — if another racer already won, bail
      if (!claim()) return
      // Clean up remote decision sources (bridge and channel)
      if (bridgeCallbacks && bridgeRequestId) {
        bridgeCallbacks.sendResponse(bridgeRequestId, {
          behavior: 'deny',
          message: 'User aborted',
        })
        bridgeCallbacks.cancelRequest(bridgeRequestId)
      }
      channelUnsubscribe?.()  // Tear down channel relay listener
      ctx.logCancelled()
      // Log as user_abort (distinct from user_reject — no feedback provided)
      ctx.logDecision(
        { decision: 'reject', source: { type: 'user_abort' } },
        { permissionPromptStartTimeMs },
      )
      resolveOnce(ctx.cancelAndAbort(undefined, true))
    },
    // -------------------------------------------------------------------------
    // CALLBACK: onAllow — Fired when the user approves the tool use.
    // May include updated input (user edited the command), permission updates
    // (e.g., "always allow this"), feedback text, and content blocks.
    // Uses claim() before await because handleUserAllow() is async.
    // -------------------------------------------------------------------------
    async onAllow(
      updatedInput,
      permissionUpdates: PermissionUpdate[],
      feedback?: string,
      contentBlocks?: ContentBlockParam[],
    ) {
      if (!claim()) return // atomic check-and-mark before await

      // Notify bridge that we've handled this locally (dismiss remote prompt)
      if (bridgeCallbacks && bridgeRequestId) {
        bridgeCallbacks.sendResponse(bridgeRequestId, {
          behavior: 'allow',
          updatedInput,
          updatedPermissions: permissionUpdates,
        })
        bridgeCallbacks.cancelRequest(bridgeRequestId)
      }
      channelUnsubscribe?.()  // Tear down channel relay listener

      // Delegate to the permission context's full approval pipeline
      // (persist updates → log → build allow decision)
      resolveOnce(
        await ctx.handleUserAllow(
          updatedInput,
          permissionUpdates,
          feedback,
          permissionPromptStartTimeMs,
          contentBlocks,
          result.decisionReason,
        ),
      )
    },
    // -------------------------------------------------------------------------
    // CALLBACK: onReject — Fired when the user explicitly denies the tool use.
    // May include feedback text explaining why they denied it, which is passed
    // back to the model so it can adjust its behavior.
    // -------------------------------------------------------------------------
    onReject(feedback?: string, contentBlocks?: ContentBlockParam[]) {
      if (!claim()) return  // Atomic race guard

      // Notify bridge and tear down channel relay
      if (bridgeCallbacks && bridgeRequestId) {
        bridgeCallbacks.sendResponse(bridgeRequestId, {
          behavior: 'deny',
          message: feedback ?? 'User denied permission',
        })
        bridgeCallbacks.cancelRequest(bridgeRequestId)
      }
      channelUnsubscribe?.()

      // Log the rejection with feedback indicator for analytics
      ctx.logDecision(
        {
          decision: 'reject',
          source: { type: 'user_reject', hasFeedback: !!feedback },
        },
        { permissionPromptStartTimeMs },
      )
      // Build the deny decision (may abort the session if no feedback/content)
      resolveOnce(ctx.cancelAndAbort(feedback, undefined, contentBlocks))
    },
    // -------------------------------------------------------------------------
    // CALLBACK: recheckPermission — Re-evaluates the permission rules without
    // user interaction. Called when settings change externally (e.g., the user
    // switches permission mode via the bridge, or a config file is reloaded).
    // If the tool is now auto-allowed, the prompt is dismissed silently.
    // -------------------------------------------------------------------------
    async recheckPermission() {
      if (isResolved()) return
      // Re-run the full permission check with current settings
      const freshResult = await hasPermissionsToUseTool(
        ctx.tool,
        ctx.input,
        ctx.toolUseContext,
        ctx.assistantMessage,
        ctx.toolUseID,
      )
      if (freshResult.behavior === 'allow') {
        // Tool is now auto-allowed under the updated settings.
        // claim() (atomic check-and-mark), not isResolved() — the async
        // hasPermissionsToUseTool call above opens a window where CCR
        // could have responded in flight. Matches onAllow/onReject/hook
        // paths. cancelRequest tells CCR to dismiss its prompt — without
        // it, the web UI shows a stale prompt for a tool that's already
        // executing (particularly visible when recheck is triggered by
        // a CCR-initiated mode switch, the very case this callback exists
        // for after useReplBridge started calling it).
        if (!claim()) return  // Another racer won during the async gap
        // Clean up all remote decision sources
        if (bridgeCallbacks && bridgeRequestId) {
          bridgeCallbacks.cancelRequest(bridgeRequestId)
        }
        channelUnsubscribe?.()
        ctx.removeFromQueue()  // Dismiss the permission dialog
        // Log as 'config' since this was resolved by settings, not user action
        ctx.logDecision({ decision: 'accept', source: 'config' })
        resolveOnce(ctx.buildAllow(freshResult.updatedInput ?? ctx.input))
      }
    },
  })

  // ---------------------------------------------------------------------------
  // RACE SOURCE 2: BRIDGE (CCR) — Permission response from claude.ai web UI
  // ---------------------------------------------------------------------------
  // Race 4: Bridge permission response from CCR (claude.ai)
  // When the bridge is connected, send the permission request to CCR and
  // subscribe for a response. Whichever side (CLI or CCR) responds first
  // wins via claim().
  //
  // All tools are forwarded — CCR's generic allow/deny modal handles any
  // tool, and can return `updatedInput` when it has a dedicated renderer
  // (e.g. plan edit). Tools whose local dialog injects fields (ReviewArtifact
  // `selected`, AskUserQuestion `answers`) tolerate the field being missing
  // so generic remote approval degrades gracefully instead of throwing.
  if (bridgeCallbacks && bridgeRequestId) {
    // Send the permission request to CCR with all context needed for rendering
    bridgeCallbacks.sendRequest(
      bridgeRequestId,
      ctx.tool.name,
      displayInput,
      ctx.toolUseID,
      description,
      result.suggestions,
      result.blockedPath,
    )

    // Subscribe for the bridge's response. The signal listener ensures cleanup
    // if the session is aborted before the bridge responds.
    const signal = ctx.toolUseContext.abortController.signal
    const unsubscribe = bridgeCallbacks.onResponse(
      bridgeRequestId,
      response => {
        if (!claim()) return // Local user/hook/classifier already responded
        // Won the race! Clean up: remove abort listener, classifier, queue, channel
        signal.removeEventListener('abort', unsubscribe)
        clearClassifierChecking(ctx.toolUseID)
        clearClassifierIndicator()
        ctx.removeFromQueue()
        channelUnsubscribe?.()

        // Handle the bridge's allow/deny decision
        if (response.behavior === 'allow') {
          // Bridge approved — persist any permission updates it included
          if (response.updatedPermissions?.length) {
            void ctx.persistPermissions(response.updatedPermissions)
          }
          ctx.logDecision(
            {
              decision: 'accept',
              source: {
                type: 'user',
                permanent: !!response.updatedPermissions?.length,
              },
            },
            { permissionPromptStartTimeMs },
          )
          resolveOnce(ctx.buildAllow(response.updatedInput ?? displayInput))
        } else {
          // Bridge denied — log and abort with the bridge's feedback message
          ctx.logDecision(
            {
              decision: 'reject',
              source: {
                type: 'user_reject',
                hasFeedback: !!response.message,
              },
            },
            { permissionPromptStartTimeMs },
          )
          resolveOnce(ctx.cancelAndAbort(response.message))
        }
      },
    )

    // If the session is aborted, unsubscribe from bridge responses
    signal.addEventListener('abort', unsubscribe, { once: true })
  }

  // ---------------------------------------------------------------------------
  // RACE SOURCE 3: CHANNEL RELAY — Permission via external messaging channels
  // ---------------------------------------------------------------------------
  // Channel permission relay — races alongside the bridge block above. Send a
  // permission prompt to every active channel (Telegram, iMessage, etc.) via
  // its MCP send_message tool, then race the reply against local/bridge/hook/
  // classifier. The inbound "yes abc123" is intercepted in the notification
  // handler (useManageMCPConnections.ts) BEFORE enqueue, so it never reaches
  // Claude as a conversation turn.
  //
  // Unlike the bridge block, this still guards on `requiresUserInteraction` —
  // channel replies are pure yes/no with no `updatedInput` path. In practice
  // the guard is dead code today: all three `requiresUserInteraction` tools
  // (ExitPlanMode, AskUserQuestion, ReviewArtifact) return `isEnabled()===false`
  // when channels are configured, so they never reach this handler.
  //
  // Fire-and-forget send: if callTool fails (channel down, tool missing),
  // the subscription never fires and another racer wins. Graceful degradation
  // — the local dialog is always there as the floor.
  if (
    (feature('KAIROS') || feature('KAIROS_CHANNELS')) &&
    channelCallbacks &&
    !ctx.tool.requiresUserInteraction?.()
  ) {
    // Generate a short request ID for channel replies (e.g., "yes abc123")
    const channelRequestId = shortRequestId(ctx.toolUseID)
    // Filter MCP clients to only those in the allowed channels list
    const allowedChannels = getAllowedChannels()
    const channelClients = filterPermissionRelayClients(
      ctx.toolUseContext.getAppState().mcp.clients,
      name => findChannelEntry(name, allowedChannels) !== undefined,
    )

    if (channelClients.length > 0) {
      // Build structured permission request params.
      // Outbound is structured too (Kenneth's symmetry ask) — server owns
      // message formatting for its platform (Telegram markdown, iMessage
      // rich text, Discord embed). CC sends the RAW parts; server composes.
      // The old callTool('send_message', {text,content,message}) triple-key
      // hack is gone — no more guessing which arg name each plugin takes.
      const params: ChannelPermissionRequestParams = {
        request_id: channelRequestId,
        tool_name: ctx.tool.name,
        description,
        input_preview: truncateForPreview(displayInput),
      }

      // Fire-and-forget: send the notification to each connected channel.
      // If callTool fails (channel down, tool missing), the subscription
      // never fires and another racer wins. Graceful degradation.
      for (const client of channelClients) {
        if (client.type !== 'connected') continue // refine for TS
        void client.client
          .notification({
            method: CHANNEL_PERMISSION_REQUEST_METHOD,
            params,
          })
          .catch(e => {
            logForDebugging(
              `Channel permission_request failed for ${client.name}: ${errorMessage(e)}`,
              { level: 'error' },
            )
          })
      }

      const channelSignal = ctx.toolUseContext.abortController.signal
      // Subscribe for channel replies. Wrap so BOTH the map delete AND the
      // abort-listener teardown happen at every call site. The 6
      // channelUnsubscribe?.() sites after local/hook/classifier wins
      // previously only deleted the map entry — the dead closure stayed
      // registered on the session-scoped abort signal until the session ended.
      // Not a functional bug (Map.delete is idempotent), but it held the
      // closure alive.
      const mapUnsub = channelCallbacks.onResponse(
        channelRequestId,
        response => {
          if (!claim()) return // Another racer won
          channelUnsubscribe?.() // both: map delete + listener remove
          // Won the race! Clean up classifier and queue
          clearClassifierChecking(ctx.toolUseID)
          clearClassifierIndicator()
          ctx.removeFromQueue()
          // Also dismiss the bridge prompt if it's active
          // Bridge is the other remote — tell it we're done.
          if (bridgeCallbacks && bridgeRequestId) {
            bridgeCallbacks.cancelRequest(bridgeRequestId)
          }

          if (response.behavior === 'allow') {
            // Channel approved — always temporary (channels can't set permanent rules)
            ctx.logDecision(
              {
                decision: 'accept',
                source: { type: 'user', permanent: false },
              },
              { permissionPromptStartTimeMs },
            )
            // Use original displayInput since channels don't support input editing
            resolveOnce(ctx.buildAllow(displayInput))
          } else {
            // Channel denied — include which server denied it for debugging
            ctx.logDecision(
              {
                decision: 'reject',
                source: { type: 'user_reject', hasFeedback: false },
              },
              { permissionPromptStartTimeMs },
            )
            resolveOnce(
              ctx.cancelAndAbort(`Denied via channel ${response.fromServer}`),
            )
          }
        },
      )
      // Construct the combined unsubscribe function: removes the response
      // listener from the map AND removes the abort event listener.
      channelUnsubscribe = () => {
        mapUnsub()
        channelSignal.removeEventListener('abort', channelUnsubscribe!)
      }

      // If the session is aborted, unsubscribe from channel replies
      channelSignal.addEventListener('abort', channelUnsubscribe, {
        once: true,
      })
    }
  }

  // ---------------------------------------------------------------------------
  // RACE SOURCE 4: PERMISSION HOOKS — Async hook execution
  // ---------------------------------------------------------------------------
  // Skip hooks if they were already awaited in the coordinator branch above
  if (!awaitAutomatedChecksBeforeDialog) {
    // Execute PermissionRequest hooks asynchronously.
    // The IIFE (Immediately Invoked Function Expression) pattern allows
    // launching an async task without blocking the synchronous function body.
    // If hook returns a decision before user responds, apply it
    void (async () => {
      // Bail early if another racer already won
      if (isResolved()) return
      const currentAppState = ctx.toolUseContext.getAppState()
      const hookDecision = await ctx.runHooks(
        currentAppState.toolPermissionContext.mode,
        result.suggestions,
        result.updatedInput,
        permissionPromptStartTimeMs,
      )
      // If hook returned null (no decision), do nothing — other racers continue
      if (!hookDecision || !claim()) return
      // Hook won the race! Clean up bridge, channel, and queue
      if (bridgeCallbacks && bridgeRequestId) {
        bridgeCallbacks.cancelRequest(bridgeRequestId)
      }
      channelUnsubscribe?.()
      ctx.removeFromQueue()
      resolveOnce(hookDecision)
    })()
  }

  // ---------------------------------------------------------------------------
  // RACE SOURCE 5: BASH CLASSIFIER — AI-based auto-approval for bash commands
  // ---------------------------------------------------------------------------
  // Execute bash classifier check asynchronously (if applicable).
  // The classifier is only used for bash commands and only when the feature
  // flag is enabled. Unlike hooks, the classifier has special integration:
  //   - It shows a spinner in the UI while running (classifierCheckInProgress)
  //   - It's suppressed once the user interacts (userInteracted flag)
  //   - On approval, it shows a brief ✓ checkmark animation before dismissing
  //   - The checkmark duration depends on terminal focus (3s focused, 1s not)
  if (
    feature('BASH_CLASSIFIER') &&
    result.pendingClassifierCheck &&
    ctx.tool.name === BASH_TOOL_NAME &&
    !awaitAutomatedChecksBeforeDialog
  ) {
    // UI indicator for "classifier running" — set here (not in
    // toolExecution.ts) so commands that auto-allow via prefix rules
    // don't flash the indicator for a split second before allow returns.
    setClassifierChecking(ctx.toolUseID)

    // Launch the async classifier check with lifecycle callbacks
    void executeAsyncClassifierCheck(
      result.pendingClassifierCheck,
      ctx.toolUseContext.abortController.signal,
      ctx.toolUseContext.options.isNonInteractiveSession,
      {
        // shouldContinue: called before delivering the classifier result.
        // Returns false if another racer already won OR the user started
        // interacting, which cancels the classifier's auto-approve.
        shouldContinue: () => !isResolved() && !userInteracted,

        // onComplete: always called when the classifier finishes (approved or not).
        // Clears the spinner indicator regardless of outcome.
        onComplete: () => {
          clearClassifierChecking(ctx.toolUseID)
          clearClassifierIndicator()
        },
        // onAllow: called when the classifier approves the bash command.
        // This is the classifier's "racer" — it calls claim() to try to win.
        onAllow: decisionReason => {
          // Atomic race guard — bail if another racer already won
          if (!claim()) return
          // Clean up bridge and channel racers
          if (bridgeCallbacks && bridgeRequestId) {
            bridgeCallbacks.cancelRequest(bridgeRequestId)
          }
          channelUnsubscribe?.()
          clearClassifierChecking(ctx.toolUseID)

          // Extract the matched prompt rule from the classifier's reason
          // (e.g., "Allowed by prompt rule: \"npm install\"" → "npm install")
          const matchedRule =
            decisionReason.type === 'classifier'
              ? (decisionReason.reason.match(
                  /^Allowed by prompt rule: "(.+)"$/,
                )?.[1] ?? decisionReason.reason)
              : undefined

          // Transition the UI: replace spinner with ✓ checkmark and dim options.
          // Show auto-approved transition with dimmed options
          if (feature('TRANSCRIPT_CLASSIFIER')) {
            ctx.updateQueueItem({
              classifierCheckInProgress: false,
              classifierAutoApproved: true,
              classifierMatchedRule: matchedRule,
            })
          }

          // Cache the classifier's approval for future reuse.
          // Two types: 'auto-mode' approvals (YOLO mode) vs prompt-rule approvals.
          if (
            feature('TRANSCRIPT_CLASSIFIER') &&
            decisionReason.type === 'classifier'
          ) {
            if (decisionReason.classifier === 'auto-mode') {
              // YOLO/auto-mode: cache with the full reason string
              setYoloClassifierApproval(ctx.toolUseID, decisionReason.reason)
            } else if (matchedRule) {
              // Prompt-rule: cache with just the extracted rule text
              setClassifierApproval(ctx.toolUseID, matchedRule)
            }
          }

          // Log the classifier approval and resolve the permission promise
          ctx.logDecision(
            { decision: 'accept', source: { type: 'classifier' } },
            { permissionPromptStartTimeMs },
          )
          // Resolve immediately — the tool can start executing now
          resolveOnce(ctx.buildAllow(ctx.input, { decisionReason }))

          // Keep checkmark visible, then remove dialog.
          // 3s if terminal is focused (user can see it), 1s if not.
          // User can dismiss early with Esc via onDismissCheckmark.
          const signal = ctx.toolUseContext.abortController.signal
          // Set up abort handler: if the session is aborted during the
          // checkmark window, immediately remove the dialog. This handles
          // the case where a sibling Bash error fires (StreamingToolExecutor
          // cascades via siblingAbortController) — must drop the cosmetic ✓
          // dialog or it blocks the next queued item.
          checkmarkAbortHandler = () => {
            if (checkmarkTransitionTimer) {
              clearTimeout(checkmarkTransitionTimer)
              checkmarkTransitionTimer = undefined
              // Sibling Bash error can fire this (StreamingToolExecutor
              // cascades via siblingAbortController) — must drop the
              // cosmetic ✓ dialog or it blocks the next queued item.
              ctx.removeFromQueue()
            }
          }
          // Shorter checkmark display if terminal not focused (user isn't watching)
          const checkmarkMs = getTerminalFocused() ? 3000 : 1000
          // After the checkmark duration, clean up the timer and remove the dialog
          checkmarkTransitionTimer = setTimeout(() => {
            checkmarkTransitionTimer = undefined
            if (checkmarkAbortHandler) {
              signal.removeEventListener('abort', checkmarkAbortHandler)
              checkmarkAbortHandler = undefined
            }
            ctx.removeFromQueue()
          }, checkmarkMs)
          signal.addEventListener('abort', checkmarkAbortHandler, {
            once: true,
          })
        },
      },
    ).catch(error => {
      // Log classifier API errors for debugging but don't propagate them as interruptions
      // These errors can be network failures, rate limits, or model issues - not user cancellations
      logForDebugging(`Async classifier check failed: ${errorMessage(error)}`, {
        level: 'error',
      })
    })
  }
}

// --

export { handleInteractivePermission }
export type { InteractivePermissionParams }

