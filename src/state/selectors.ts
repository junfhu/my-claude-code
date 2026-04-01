// =============================================================================
// selectors.ts — Pure derived-state selectors for AppState
// =============================================================================
//
// Selectors are pure functions that compute derived values from the AppState
// atom. They encapsulate common lookup + validation patterns so that multiple
// consumers (React components, REPL logic, input routing) share one canonical
// implementation rather than duplicating task-lookup boilerplate.
//
// Design principles:
//   1. Pure — no side effects, no mutations, no I/O.
//   2. Minimal — accept only the AppState slices they need (via Pick<>),
//      so callers can pass partial mocks in tests.
//   3. Type-safe — return discriminated unions so callers can narrow with
//      pattern matching and get exhaustive checking.
//
// These selectors are NOT React hooks. They can be used in any context:
//   • Inside useAppState(selector) for reactive rendering
//   • In imperative code with store.getState()
//   • In tests with plain objects
// =============================================================================

/**
 * Selectors for deriving computed state from AppState.
 * Keep selectors pure and simple - just data extraction, no side effects.
 */

import type { InProcessTeammateTaskState } from '../tasks/InProcessTeammateTask/types.js'
import { isInProcessTeammateTask } from '../tasks/InProcessTeammateTask/types.js'
import type { LocalAgentTaskState } from '../tasks/LocalAgentTask/LocalAgentTask.js'
import type { AppState } from './AppStateStore.js'

/**
 * Get the currently viewed teammate task, if any.
 * Returns undefined if:
 * - No teammate is being viewed (viewingAgentTaskId is undefined)
 * - The task ID doesn't exist in tasks
 * - The task is not an in-process teammate task
 */
// ---------------------------------------------------------------------------
// getViewedTeammateTask — Resolves the task object for the teammate currently
// being viewed in the UI.
//
// This is a 3-step validation pipeline:
//   1. Is viewingAgentTaskId set? (are we viewing anyone?)
//   2. Does the ID map to an existing task? (guard against stale IDs)
//   3. Is that task an in-process teammate? (not a local-agent or other type)
//
// Returns the typed InProcessTeammateTaskState or undefined.
// Uses Pick<AppState, …> so callers only need to provide the two fields,
// making this easy to test with minimal mocks.
// ---------------------------------------------------------------------------
export function getViewedTeammateTask(
  appState: Pick<AppState, 'viewingAgentTaskId' | 'tasks'>,
): InProcessTeammateTaskState | undefined {
  const { viewingAgentTaskId, tasks } = appState

  // Not viewing any teammate
  if (!viewingAgentTaskId) {
    return undefined
  }

  // Look up the task
  const task = tasks[viewingAgentTaskId]
  if (!task) {
    return undefined
  }

  // Verify it's an in-process teammate task
  if (!isInProcessTeammateTask(task)) {
    return undefined
  }

  return task
}

/**
 * Return type for getActiveAgentForInput selector.
 * Discriminated union for type-safe input routing.
 */
// ---------------------------------------------------------------------------
// ActiveAgentForInput — Discriminated union describing where user input
// should be directed. The `type` discriminant enables exhaustive switch/case:
//   - 'leader':      Input goes to the main leader agent (default)
//   - 'viewed':      Input goes to the in-process teammate being viewed
//   - 'named_agent': Input goes to a local agent task (non-teammate subagent)
// ---------------------------------------------------------------------------
export type ActiveAgentForInput =
  | { type: 'leader' }
  | { type: 'viewed'; task: InProcessTeammateTaskState }
  | { type: 'named_agent'; task: LocalAgentTaskState }

/**
 * Determine where user input should be routed.
 * Returns:
 * - { type: 'leader' } when not viewing a teammate (input goes to leader)
 * - { type: 'viewed', task } when viewing an agent (input goes to that agent)
 *
 * Used by input routing logic to direct user messages to the correct agent.
 */
// ---------------------------------------------------------------------------
// getActiveAgentForInput — Determines the target agent for the next user input.
//
// Resolution order:
//   1. If viewing an in-process teammate → route to that teammate
//   2. If viewing a local agent task → route to that named agent
//   3. Otherwise → route to the leader (default behavior)
//
// This selector drives the input routing in the REPL: when a user types a
// message, the system needs to know whether to send it to the leader, a
// viewed teammate, or a named subagent. The resolution priority ensures
// that explicitly viewed agents take precedence.
// ---------------------------------------------------------------------------
export function getActiveAgentForInput(
  appState: AppState,
): ActiveAgentForInput {
  // First: check if we're viewing an in-process teammate
  const viewedTask = getViewedTeammateTask(appState)
  if (viewedTask) {
    return { type: 'viewed', task: viewedTask }
  }

  // Second: check if we're viewing a local agent task (non-teammate subagent)
  const { viewingAgentTaskId, tasks } = appState
  if (viewingAgentTaskId) {
    const task = tasks[viewingAgentTaskId]
    if (task?.type === 'local_agent') {
      return { type: 'named_agent', task }
    }
  }

  // Default: input goes to the leader
  return { type: 'leader' }
}

