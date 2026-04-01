// QueryConfig — immutable configuration snapshot for a single query() call.
// Built once at the top of each query() invocation via buildQueryConfig().
// Provides deterministic, pure-data config that the query loop can thread
// through every iteration without re-evaluating gates or env vars mid-turn.
import { getSessionId } from '../bootstrap/state.js'
import { checkStatsigFeatureGate_CACHED_MAY_BE_STALE } from '../services/analytics/growthbook.js'
import type { SessionId } from '../types/ids.js'
import { isEnvTruthy } from '../utils/envUtils.js'

// -- config

// Immutable values snapshotted once at query() entry. Separating these from
// the per-iteration State struct and the mutable ToolUseContext makes future
// step() extraction tractable — a pure reducer can take (state, event, config)
// where config is plain data.
//
// Intentionally excludes feature() gates — those are tree-shaking boundaries
// and must stay inline at the guarded blocks for dead-code elimination.
export type QueryConfig = {
  // The unique session identifier for the current CLI session.
  // Used for analytics, dump-prompts file naming, and abort signal scoping.
  sessionId: SessionId

  // Runtime gates (env/statsig). NOT feature() gates — see above.
  gates: {
    // Statsig — CACHED_MAY_BE_STALE already admits staleness, so snapshotting
    // once per query() call stays within the existing contract.

    // Whether to overlap tool execution with model streaming (StreamingToolExecutor).
    // When true, tools begin executing as soon as their tool_use block arrives
    // from the stream, rather than waiting for the full response.
    streamingToolExecution: boolean

    // Whether to generate natural-language summaries of tool use batches
    // (e.g. "Read 3 files and ran 2 shell commands") for mobile/compact UIs.
    // Summaries are produced by a lightweight Haiku call in the background.
    emitToolUseSummaries: boolean

    // Whether the current user is an Anthropic internal user (USER_TYPE=ant).
    // Gates internal-only features like prompt dumping and enhanced error logging.
    isAnt: boolean

    // Whether the fast-mode (lower-latency, possibly smaller model) toggle is
    // available. Controlled by the CLAUDE_CODE_DISABLE_FAST_MODE env var.
    fastModeEnabled: boolean
  }
}

// buildQueryConfig — factory function that snapshots all runtime gates and
// session state into an immutable QueryConfig. Called exactly once per
// query() entry (not per loop iteration), ensuring consistent behavior
// even if a statsig gate flips mid-turn.
export function buildQueryConfig(): QueryConfig {
  return {
    sessionId: getSessionId(),
    gates: {
      // Statsig gate: controls whether StreamingToolExecutor is instantiated.
      streamingToolExecution: checkStatsigFeatureGate_CACHED_MAY_BE_STALE(
        'tengu_streaming_tool_execution2',
      ),
      // Env var: CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES controls Haiku summary generation.
      emitToolUseSummaries: isEnvTruthy(
        process.env.CLAUDE_CODE_EMIT_TOOL_USE_SUMMARIES,
      ),
      // Env var: USER_TYPE=ant identifies internal Anthropic users.
      isAnt: process.env.USER_TYPE === 'ant',
      // Inlined from fastMode.ts to avoid pulling its heavy module graph
      // (axios, settings, auth, model, oauth, config) into test shards that
      // didn't previously load it — changes init order and breaks unrelated tests.
      fastModeEnabled: !isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_FAST_MODE),
    },
  }
}

