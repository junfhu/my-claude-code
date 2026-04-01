/**
 * Transition types for the query loop.
 *
 * Every iteration of the while(true) loop in queryLoop() ends with either a
 * Terminal (return) or a Continue (state = next; continue). These types make
 * the exit/continue reasons explicit so that:
 *   1. Tests can assert which recovery path fired without inspecting messages.
 *   2. The loop body can condition behavior on the PREVIOUS iteration's
 *      transition (e.g. skip collapse drain if we already drained).
 *   3. Analytics can attribute each turn to a specific continuation reason.
 *
 * Terminal: why the loop exited (returned).
 * Continue: why the loop continued to the next iteration (not returned).
 */

/** Terminal transition — the query loop returned. */
// Each reason maps to a specific exit path in queryLoop():
export type Terminal = {
  reason:
    // Normal completion: the model finished without requesting tool use,
    // and stop hooks (if any) did not block. This is the happy path.
    | 'completed'
    // The estimated token count hit the hard blocking limit (auto-compact OFF).
    // The user must run /compact manually to continue.
    | 'blocking_limit'
    // An ImageSizeError or ImageResizeError was thrown during streaming.
    // Also used when reactive compact strips oversized media and still fails.
    | 'image_error'
    // The API call threw an unexpected error (network, auth, runtime bug).
    // The raw error is attached in the `error` field for upstream handling.
    | 'model_error'
    // The user pressed Ctrl+C (or the abort signal fired) DURING streaming,
    // before tool execution began.
    | 'aborted_streaming'
    // The user pressed Ctrl+C (or the abort signal fired) DURING tool execution,
    // after the model returned tool_use blocks.
    | 'aborted_tools'
    // The API returned a 413 prompt-too-long error and all recovery paths
    // (collapse drain, reactive compact) were exhausted or unavailable.
    | 'prompt_too_long'
    // A stop hook returned { prevent: true }, vetoing the model's response.
    // The turn ends without yielding the response to the user.
    | 'stop_hook_prevented'
    // A tool-execution hook attachment indicated hook_stopped_continuation.
    // Differs from stop_hook_prevented: this fires AFTER tools ran.
    | 'hook_stopped'
    // The turn count exceeded the caller-specified maxTurns limit.
    // An attachment message is yielded before returning so the SDK can report it.
    | 'max_turns'
    // Open union: allows downstream consumers to add custom reasons
    // without breaking the type (e.g. test-only reasons).
    | (string & {})
  // The raw error object, if this terminal was caused by an exception.
  error?: unknown
}

/** Continue transition — the loop will iterate again. */
// Each reason maps to a specific `state = next; continue` site in queryLoop():
export type Continue = {
  reason:
    // The model requested tool_use and tools have been executed.
    // The next iteration sends tool results back to the API.
    | 'tool_use'
    // Reactive compact recovered from a prompt-too-long (413) error by
    // compacting the conversation and retrying the API call.
    | 'reactive_compact_retry'
    // The model hit max_output_tokens but recovery attempts remain.
    // A synthetic "resume" user message is injected and the loop retries.
    | 'max_output_tokens_recovery'
    // The model hit max_output_tokens with the capped default (8k), so
    // the loop retries with an escalated limit (64k) — single-shot, no
    // synthetic message. Falls through to multi-turn recovery if 64k also caps.
    | 'max_output_tokens_escalate'
    // Context collapse drained staged collapses to recover from a 413.
    // The collapsed (smaller) messages are retried without a full compact.
    | 'collapse_drain_retry'
    // A stop hook returned blocking errors. The errors are appended as
    // user messages and the model is asked to fix the issues.
    | 'stop_hook_blocking'
    // The token budget auto-continue feature determined the model should
    // keep working (output tokens < budget). A nudge message is injected.
    | 'token_budget_continuation'
    // A queued command (e.g. from the message queue) was consumed as an
    // attachment and the loop continues to process the model's response.
    | 'queued_command'
    // Open union: allows downstream consumers to add custom reasons.
    | (string & {})
}
