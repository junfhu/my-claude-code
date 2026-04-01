// =============================================================================
// swarmWorkerHandler.ts — Swarm worker permission flow handler
// =============================================================================
//
// This handler manages permission decisions for swarm worker agents. Swarm
// workers are child agents spawned by a swarm leader to parallelize work.
// Since workers don't have their own terminal UI, they forward permission
// requests to the leader via a mailbox system.
//
// FLOW:
//   1. Check if this is actually a swarm worker (if not, return null → fallback)
//   2. Try bash classifier auto-approval (if applicable) — workers await the
//      classifier result (blocking) rather than racing it against user input
//      since there's no local user to race against.
//   3. If classifier didn't approve, forward the request to the leader:
//      a. Create a permission request object
//      b. Register callbacks for leader's response BEFORE sending (avoids race)
//      c. Send the request to the leader via mailbox
//      d. Show a pending indicator while waiting
//      e. Handle abort signal in case the session ends while waiting
//   4. If the mailbox fails, return null → fallback to local handling
//
// Uses the same ResolveOnce guard pattern as interactiveHandler.ts to handle
// the race between leader response and abort signal.
// =============================================================================

import { feature } from 'bun:bundle'
import type { ContentBlockParam } from '@anthropic-ai/sdk/resources/messages.mjs'
import type { PendingClassifierCheck } from '../../../types/permissions.js'
import { isAgentSwarmsEnabled } from '../../../utils/agentSwarmsEnabled.js'
import { toError } from '../../../utils/errors.js'
import { logError } from '../../../utils/log.js'
import type { PermissionDecision } from '../../../utils/permissions/PermissionResult.js'
import type { PermissionUpdate } from '../../../utils/permissions/PermissionUpdateSchema.js'
import {
  createPermissionRequest,
  isSwarmWorker,
  sendPermissionRequestViaMailbox,
} from '../../../utils/swarm/permissionSync.js'
import { registerPermissionCallback } from '../../useSwarmPermissionPoller.js'
import type { PermissionContext } from '../PermissionContext.js'
import { createResolveOnce } from '../PermissionContext.js'

// Parameters for the swarm worker permission handler.
type SwarmWorkerPermissionParams = {
  ctx: PermissionContext                                       // Per-tool-use permission context
  description: string                                          // Human-readable description for the leader
  pendingClassifierCheck?: PendingClassifierCheck | undefined  // Optional: classifier check to try first
  updatedInput: Record<string, unknown> | undefined            // Optional: modified input from initial check
  suggestions: PermissionUpdate[] | undefined                  // Optional: suggested permission updates
}

/**
 * Handles the swarm worker permission flow.
 *
 * When running as a swarm worker:
 * 1. Tries classifier auto-approval for bash commands
 * 2. Forwards the permission request to the leader via mailbox
 * 3. Registers callbacks for when the leader responds
 * 4. Sets the pending indicator while waiting
 *
 * Returns a PermissionDecision if the classifier auto-approves,
 * or a Promise that resolves when the leader responds.
 * Returns null if swarms are not enabled or this is not a swarm worker,
 * so the caller can fall through to interactive handling.
 */
async function handleSwarmWorkerPermission(
  params: SwarmWorkerPermissionParams,
): Promise<PermissionDecision | null> {
  // Guard: exit early if swarms aren't enabled or this isn't a swarm worker.
  // Returning null tells the caller to fall through to interactive handling.
  if (!isAgentSwarmsEnabled() || !isSwarmWorker()) {
    return null
  }

  const { ctx, description, updatedInput, suggestions } = params

  // Step 1: Try classifier auto-approval before forwarding to the leader.
  // For bash commands, try classifier auto-approval before forwarding to
  // the leader. Agents await the classifier result (rather than racing it
  // against user interaction like the main agent).
  const classifierResult = feature('BASH_CLASSIFIER')
    ? await ctx.tryClassifier?.(params.pendingClassifierCheck, updatedInput)
    : null
  if (classifierResult) {
    return classifierResult  // Classifier approved — no need to bother the leader
  }

  // Step 2: Forward permission request to the leader via mailbox.
  // The mailbox is a file-based IPC mechanism between swarm workers and leader.
  // Forward permission request to the leader via mailbox
  try {
    // Helper to clear the "waiting for leader" indicator from the UI
    const clearPendingRequest = (): void =>
      ctx.toolUseContext.setAppState(prev => ({
        ...prev,
        pendingWorkerRequest: null,
      }))

    // Create a promise that resolves when the leader responds.
    // Two racers compete: the leader's response and the abort signal.
    const decision = await new Promise<PermissionDecision>(resolve => {
      // Create a resolve-once guard for the leader-response vs abort race
      const { resolve: resolveOnce, claim } = createResolveOnce(resolve)

      // Create the permission request payload for the leader
      // Create the permission request
      const request = createPermissionRequest({
        toolName: ctx.tool.name,
        toolUseId: ctx.toolUseID,
        input: ctx.input,
        description,
        permissionSuggestions: suggestions,
      })

      // IMPORTANT: Register callback BEFORE sending the request to avoid race condition
      // where leader responds before callback is registered.
      // Register callback BEFORE sending the request to avoid race condition
      // where leader responds before callback is registered
      registerPermissionCallback({
        requestId: request.id,
        toolUseId: ctx.toolUseID,
        // CALLBACK: Leader approved the tool use.
        // Uses claim() before await because handleUserAllow is async.
        async onAllow(
          allowedInput: Record<string, unknown> | undefined,
          permissionUpdates: PermissionUpdate[],
          feedback?: string,
          contentBlocks?: ContentBlockParam[],
        ) {
          if (!claim()) return // atomic check-and-mark before await
          clearPendingRequest()  // Remove the "waiting for leader" indicator

          // Merge the updated input with the original input.
          // If leader provided input, use it; otherwise use the worker's original.
          // Merge the updated input with the original input
          const finalInput =
            allowedInput && Object.keys(allowedInput).length > 0
              ? allowedInput
              : ctx.input

          // Delegate to the permission context's user-allow pipeline
          resolveOnce(
            await ctx.handleUserAllow(
              finalInput,
              permissionUpdates,
              feedback,
              undefined,
              contentBlocks,
            ),
          )
        },
        // CALLBACK: Leader denied the tool use.
        onReject(feedback?: string, contentBlocks?: ContentBlockParam[]) {
          if (!claim()) return  // Atomic race guard
          clearPendingRequest()  // Remove the "waiting for leader" indicator

          ctx.logDecision({
            decision: 'reject',
            source: { type: 'user_reject', hasFeedback: !!feedback },
          })

          // Build a deny decision with the leader's feedback
          resolveOnce(ctx.cancelAndAbort(feedback, undefined, contentBlocks))
        },
      })

      // Now that callback is registered, send the request to the leader.
      // Order matters: register callback → send request. If reversed, the leader
      // could respond before we're listening and the response would be lost.
      // Now that callback is registered, send the request to the leader
      void sendPermissionRequestViaMailbox(request)

      // Show visual indicator that we're waiting for leader approval.
      // This sets pendingWorkerRequest in app state, which the UI renders
      // as a "Waiting for approval..." status message.
      // Show visual indicator that we're waiting for leader approval
      ctx.toolUseContext.setAppState(prev => ({
        ...prev,
        pendingWorkerRequest: {
          toolName: ctx.tool.name,
          toolUseId: ctx.toolUseID,
          description,
        },
      }))

      // Abort signal handler: if the session is aborted while waiting for
      // the leader's response, resolve the promise with a cancel decision so
      // it does not hang indefinitely. This is the "abort racer" competing
      // against the leader's response callback.
      // If the abort signal fires while waiting for the leader response,
      // resolve the promise with a cancel decision so it does not hang.
      ctx.toolUseContext.abortController.signal.addEventListener(
        'abort',
        () => {
          if (!claim()) return  // Leader already responded — no-op
          clearPendingRequest()
          ctx.logCancelled()
          resolveOnce(ctx.cancelAndAbort(undefined, true))  // Hard abort
        },
        { once: true },
      )
    })

    return decision
  } catch (error) {
    // If swarm permission submission fails, fall back to local handling
    logError(toError(error))
    // Continue to local UI handling below
    return null
  }
}

export { handleSwarmWorkerPermission }
export type { SwarmWorkerPermissionParams }

