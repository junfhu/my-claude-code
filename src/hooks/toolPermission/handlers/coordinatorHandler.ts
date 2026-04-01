// =============================================================================
// coordinatorHandler.ts — Coordinator worker permission flow
// =============================================================================
//
// This handler is used when a coordinator worker needs a permission decision.
// Unlike the interactive handler (which races multiple sources concurrently),
// the coordinator handler runs automated checks SEQUENTIALLY before falling
// through to the interactive dialog.
//
// FLOW:
//   1. Run PermissionRequest hooks (fast, local) — if any hook decides, return.
//   2. Run bash classifier (slow, AI inference) — if it approves, return.
//   3. If neither resolved, return null → caller falls through to interactive dialog.
//
// The key difference from interactiveHandler.ts is that hooks and classifier
// are AWAITED (blocking) rather than racing against user input. This is because
// coordinator workers want to avoid showing a dialog unless necessary — the
// automated checks get a full chance to resolve first.
//
// If automated checks throw an error, the handler catches it gracefully and
// returns null so the user can still decide manually via the dialog.
// =============================================================================

import { feature } from 'bun:bundle'
import type { PendingClassifierCheck } from '../../../types/permissions.js'
import { logError } from '../../../utils/log.js'
import type { PermissionDecision } from '../../../utils/permissions/PermissionResult.js'
import type { PermissionUpdate } from '../../../utils/permissions/PermissionUpdateSchema.js'
import type { PermissionContext } from '../PermissionContext.js'

// Parameters for the coordinator permission handler.
// Contains the context, classifier check, and current permission settings.
type CoordinatorPermissionParams = {
  ctx: PermissionContext                               // Per-tool-use permission context
  pendingClassifierCheck?: PendingClassifierCheck | undefined  // Optional: classifier check to await
  updatedInput: Record<string, unknown> | undefined    // Optional: modified input from initial check
  suggestions: PermissionUpdate[] | undefined          // Optional: suggested permission rule updates
  permissionMode: string | undefined                   // Current permission mode (e.g., "plan", "auto-edit")
}

/**
 * Handles the coordinator worker permission flow.
 *
 * For coordinator workers, automated checks (hooks and classifier) are
 * awaited sequentially before falling through to the interactive dialog.
 *
 * Returns a PermissionDecision if the automated checks resolved the
 * permission, or null if the caller should fall through to the
 * interactive dialog.
 */
async function handleCoordinatorPermission(
  params: CoordinatorPermissionParams,
): Promise<PermissionDecision | null> {
  const { ctx, updatedInput, suggestions, permissionMode } = params

  try {
    // Step 1: Try permission hooks first (fast, local).
    // Hooks are awaited sequentially — if any hook returns allow/deny,
    // we return immediately without reaching the classifier.
    // 1. Try permission hooks first (fast, local)
    const hookResult = await ctx.runHooks(
      permissionMode,
      suggestions,
      updatedInput,
    )
    if (hookResult) return hookResult  // Hook decided — return immediately

    // Step 2: Try classifier (slow, AI inference — bash only).
    // Only runs if the BASH_CLASSIFIER feature flag is enabled.
    // ctx.tryClassifier is conditionally defined (see PermissionContext.ts).
    // 2. Try classifier (slow, inference -- bash only)
    const classifierResult = feature('BASH_CLASSIFIER')
      ? await ctx.tryClassifier?.(params.pendingClassifierCheck, updatedInput)
      : null
    if (classifierResult) {
      return classifierResult  // Classifier approved — return immediately
    }
  } catch (error) {
    // If automated checks fail unexpectedly, fall through to show the dialog
    // so the user can decide manually. Non-Error throws get a context prefix
    // so the log is traceable — intentionally NOT toError(), which would drop
    // the prefix.
    if (error instanceof Error) {
      logError(error)
    } else {
      logError(new Error(`Automated permission check failed: ${String(error)}`))
    }
  }

  // 3. Neither resolved (or checks failed) -- fall through to dialog below.
  // Hooks already ran, classifier already consumed.
  return null
}

export { handleCoordinatorPermission }
export type { CoordinatorPermissionParams }

