// =============================================================================
// cost-tracker.ts — Token Cost Tracking and Reporting
// =============================================================================
// Tracks API usage costs across the entire session. Provides:
//   - Per-model token usage tracking (input, output, cache read, cache write)
//   - USD cost calculation using per-model pricing from modelCost.ts
//   - Session cost persistence (save/restore via project config for /resume)
//   - Formatted cost display for the /cost command
//   - OpenTelemetry counter integration for cost/token metrics
//   - Advisor (sub-model) usage tracking for advisor tool calls
//
// Cost flow:
//   1. Each API response includes a `Usage` object with token counts
//   2. `addToTotalSessionCost()` is called after each API response
//   3. It calculates USD cost via `calculateUSDCost()` using model pricing
//   4. Accumulates into global state (bootstrap/state.ts counters)
//   5. Records metrics via OpenTelemetry counters (cost, tokens by type)
//   6. `formatTotalCost()` renders the /cost command output
//   7. `saveCurrentSessionCosts()` persists to project config for resume
//
// The module re-exports many state accessors for convenience — most actual
// state lives in bootstrap/state.ts to be accessible before React mounts.
// =============================================================================
import type { BetaUsage as Usage } from '@anthropic-ai/sdk/resources/beta/messages/messages.mjs'
import chalk from 'chalk'
import {
  addToTotalCostState,
  addToTotalLinesChanged,
  getCostCounter,
  getModelUsage,
  getSdkBetas,
  getSessionId,
  getTokenCounter,
  getTotalAPIDuration,
  getTotalAPIDurationWithoutRetries,
  getTotalCacheCreationInputTokens,
  getTotalCacheReadInputTokens,
  getTotalCostUSD,
  getTotalDuration,
  getTotalInputTokens,
  getTotalLinesAdded,
  getTotalLinesRemoved,
  getTotalOutputTokens,
  getTotalToolDuration,
  getTotalWebSearchRequests,
  getUsageForModel,
  hasUnknownModelCost,
  resetCostState,
  resetStateForTests,
  setCostStateForRestore,
  setHasUnknownModelCost,
} from './bootstrap/state.js'
import type { ModelUsage } from './entrypoints/agentSdkTypes.js'
import {
  type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
  logEvent,
} from './services/analytics/index.js'
// Extracts advisor (sub-model) usage from an API response for recursive cost tracking
import { getAdvisorUsage } from './utils/advisor.js'
import {
  getCurrentProjectConfig,
  saveCurrentProjectConfig,
} from './utils/config.js'
// Gets context window size and max output tokens for a model (used for ModelUsage metadata)
import {
  getContextWindowForModel,
  getModelMaxOutputTokens,
} from './utils/context.js'
// Fast mode: when enabled, the API may use a faster but cheaper model variant
import { isFastModeEnabled } from './utils/fastMode.js'
import { formatDuration, formatNumber } from './utils/format.js'
import type { FpsMetrics } from './utils/fpsTracker.js'
// Maps model IDs to canonical short names for display (e.g., "claude-3-5-sonnet-20241022" → "Sonnet")
import { getCanonicalName } from './utils/model/model.js'
// Calculates the USD cost for a given model and usage using per-model pricing tables
import { calculateUSDCost } from './utils/modelCost.js'

// ─── Re-exports ──────────────────────────────────────────────────────────────
// These are re-exported from bootstrap/state.ts for convenience so consumers
// can import cost-related functions from a single module.
export {
  getTotalCostUSD as getTotalCost,
  getTotalDuration,
  getTotalAPIDuration,
  getTotalAPIDurationWithoutRetries,
  addToTotalLinesChanged,
  getTotalLinesAdded,
  getTotalLinesRemoved,
  getTotalInputTokens,
  getTotalOutputTokens,
  getTotalCacheReadInputTokens,
  getTotalCacheCreationInputTokens,
  getTotalWebSearchRequests,
  formatCost,
  hasUnknownModelCost,
  resetStateForTests,
  resetCostState,
  setHasUnknownModelCost,
  getModelUsage,
  getUsageForModel,
}

// Shape of cost state persisted to the project config file (.claude/project.json).
// Saved when switching sessions or on exit, restored when resuming a session.
type StoredCostState = {
  // Accumulated USD cost for the session
  totalCostUSD: number
  // Total time spent in API calls (including retries)
  totalAPIDuration: number
  // Total time spent in API calls (excluding retry overhead)
  totalAPIDurationWithoutRetries: number
  // Total time spent executing tools (bash, file operations, etc.)
  totalToolDuration: number
  // Lines of code added/removed across all file edits
  totalLinesAdded: number
  totalLinesRemoved: number
  // Wall-clock duration of the last completed turn
  lastDuration: number | undefined
  // Per-model token usage breakdown (keyed by model name)
  modelUsage: { [modelName: string]: ModelUsage } | undefined
}

/**
 * Gets stored cost state from project config for a specific session.
 * Returns the cost data if the session ID matches, or undefined otherwise.
 * Use this to read costs BEFORE overwriting the config with saveCurrentSessionCosts().
 */
export function getStoredSessionCosts(
  sessionId: string,
): StoredCostState | undefined {
  const projectConfig = getCurrentProjectConfig()

  // Only return costs if this is the same session that was last saved
  // This prevents loading stale costs from a different session
  if (projectConfig.lastSessionId !== sessionId) {
    return undefined
  }

  // Build model usage with context windows — enriches stored usage data
  // with current context window and max output token info (which may differ
  // from when the session was saved if models have been updated)
  let modelUsage: { [modelName: string]: ModelUsage } | undefined
  if (projectConfig.lastModelUsage) {
    modelUsage = Object.fromEntries(
      Object.entries(projectConfig.lastModelUsage).map(([model, usage]) => [
        model,
        {
          ...usage,
          contextWindow: getContextWindowForModel(model, getSdkBetas()),
          maxOutputTokens: getModelMaxOutputTokens(model).default,
        },
      ]),
    )
  }

  return {
    totalCostUSD: projectConfig.lastCost ?? 0,
    totalAPIDuration: projectConfig.lastAPIDuration ?? 0,
    totalAPIDurationWithoutRetries:
      projectConfig.lastAPIDurationWithoutRetries ?? 0,
    totalToolDuration: projectConfig.lastToolDuration ?? 0,
    totalLinesAdded: projectConfig.lastLinesAdded ?? 0,
    totalLinesRemoved: projectConfig.lastLinesRemoved ?? 0,
    lastDuration: projectConfig.lastDuration,
    modelUsage,
  }
}

/**
 * Restores cost state from project config when resuming a session.
 * Only restores if the session ID matches the last saved session.
 * @returns true if cost state was restored, false otherwise
 */
export function restoreCostStateForSession(sessionId: string): boolean {
  const data = getStoredSessionCosts(sessionId)
  if (!data) {
    return false
  }
  setCostStateForRestore(data)
  return true
}

/**
 * Saves the current session's costs to project config.
 * Call this before switching sessions to avoid losing accumulated costs.
 */
export function saveCurrentSessionCosts(fpsMetrics?: FpsMetrics): void {
  saveCurrentProjectConfig(current => ({
    ...current,
    lastCost: getTotalCostUSD(),
    lastAPIDuration: getTotalAPIDuration(),
    lastAPIDurationWithoutRetries: getTotalAPIDurationWithoutRetries(),
    lastToolDuration: getTotalToolDuration(),
    lastDuration: getTotalDuration(),
    lastLinesAdded: getTotalLinesAdded(),
    lastLinesRemoved: getTotalLinesRemoved(),
    lastTotalInputTokens: getTotalInputTokens(),
    lastTotalOutputTokens: getTotalOutputTokens(),
    lastTotalCacheCreationInputTokens: getTotalCacheCreationInputTokens(),
    lastTotalCacheReadInputTokens: getTotalCacheReadInputTokens(),
    lastTotalWebSearchRequests: getTotalWebSearchRequests(),
    lastFpsAverage: fpsMetrics?.averageFps,
    lastFpsLow1Pct: fpsMetrics?.low1PctFps,
    lastModelUsage: Object.fromEntries(
      Object.entries(getModelUsage()).map(([model, usage]) => [
        model,
        {
          inputTokens: usage.inputTokens,
          outputTokens: usage.outputTokens,
          cacheReadInputTokens: usage.cacheReadInputTokens,
          cacheCreationInputTokens: usage.cacheCreationInputTokens,
          webSearchRequests: usage.webSearchRequests,
          costUSD: usage.costUSD,
        },
      ]),
    ),
    lastSessionId: getSessionId(),
  }))
}

// Formats a USD cost value for display. Costs above $0.50 are shown with
// 2 decimal places; smaller costs use 4 decimal places for precision.
function formatCost(cost: number, maxDecimalPlaces: number = 4): string {
  return `$${cost > 0.5 ? round(cost, 100).toFixed(2) : cost.toFixed(maxDecimalPlaces)}`
}

// Formats per-model token usage into a multi-line string for the /cost command.
// Groups usage by canonical model name (e.g., multiple sonnet variants → "Sonnet")
// and shows input/output/cache read/cache write token counts with cost per model.
function formatModelUsage(): string {
  const modelUsageMap = getModelUsage()
  if (Object.keys(modelUsageMap).length === 0) {
    return 'Usage:                 0 input, 0 output, 0 cache read, 0 cache write'
  }

  // Accumulate usage by short name so that multiple model variants
  // (e.g., claude-3-5-sonnet-20241022, claude-3-5-sonnet-latest) are
  // grouped under a single canonical display name
  const usageByShortName: { [shortName: string]: ModelUsage } = {}
  for (const [model, usage] of Object.entries(modelUsageMap)) {
    const shortName = getCanonicalName(model)
    if (!usageByShortName[shortName]) {
      usageByShortName[shortName] = {
        inputTokens: 0,
        outputTokens: 0,
        cacheReadInputTokens: 0,
        cacheCreationInputTokens: 0,
        webSearchRequests: 0,
        costUSD: 0,
        contextWindow: 0,
        maxOutputTokens: 0,
      }
    }
    const accumulated = usageByShortName[shortName]
    accumulated.inputTokens += usage.inputTokens
    accumulated.outputTokens += usage.outputTokens
    accumulated.cacheReadInputTokens += usage.cacheReadInputTokens
    accumulated.cacheCreationInputTokens += usage.cacheCreationInputTokens
    accumulated.webSearchRequests += usage.webSearchRequests
    accumulated.costUSD += usage.costUSD
  }

  let result = 'Usage by model:'
  for (const [shortName, usage] of Object.entries(usageByShortName)) {
    const usageString =
      `  ${formatNumber(usage.inputTokens)} input, ` +
      `${formatNumber(usage.outputTokens)} output, ` +
      `${formatNumber(usage.cacheReadInputTokens)} cache read, ` +
      `${formatNumber(usage.cacheCreationInputTokens)} cache write` +
      (usage.webSearchRequests > 0
        ? `, ${formatNumber(usage.webSearchRequests)} web search`
        : '') +
      ` (${formatCost(usage.costUSD)})`
    result += `\n` + `${shortName}:`.padStart(21) + usageString
  }
  return result
}

// Formats the complete cost summary shown by the /cost command.
// Includes: total cost, API duration, wall-clock duration, code changes,
// per-model usage breakdown, and optional x402 payment summary.
export function formatTotalCost(): string {
  const costDisplay =
    formatCost(getTotalCostUSD()) +
    (hasUnknownModelCost()
      ? ' (costs may be inaccurate due to usage of unknown models)'
      : '')

  const modelUsageDisplay = formatModelUsage()

  // Include x402 payment summary if any payments were made
  // (x402 is a crypto payment protocol for tool access)
  let x402Display = ''
  try {
    const { formatX402Cost } = require('./services/x402/index.js') as typeof import('./services/x402/index.js')
    const x402Summary = formatX402Cost()
    if (x402Summary) {
      x402Display = '\n' + x402Summary
    }
  } catch {
    // x402 module not available, skip
  }

  return chalk.dim(
    `Total cost:            ${costDisplay}\n` +
      `Total duration (API):  ${formatDuration(getTotalAPIDuration())}
Total duration (wall): ${formatDuration(getTotalDuration())}
Total code changes:    ${getTotalLinesAdded()} ${getTotalLinesAdded() === 1 ? 'line' : 'lines'} added, ${getTotalLinesRemoved()} ${getTotalLinesRemoved() === 1 ? 'line' : 'lines'} removed
${modelUsageDisplay}${x402Display}`,
  )
}

// Rounds a number to the given precision (e.g., round(1.567, 100) → 1.57)
function round(number: number, precision: number): number {
  return Math.round(number * precision) / precision
}

// Accumulates a single API response's usage into the running per-model totals.
// Creates a new ModelUsage entry if this is the first response from this model.
// Also enriches the ModelUsage with the model's context window and max output tokens.
function addToTotalModelUsage(
  cost: number,
  usage: Usage,
  model: string,
): ModelUsage {
  // Get existing usage for this model, or initialize with zeros
  const modelUsage = getUsageForModel(model) ?? {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadInputTokens: 0,
    cacheCreationInputTokens: 0,
    webSearchRequests: 0,
    costUSD: 0,
    contextWindow: 0,
    maxOutputTokens: 0,
  }

  // Accumulate token counts from this API response
  modelUsage.inputTokens += usage.input_tokens
  modelUsage.outputTokens += usage.output_tokens
  modelUsage.cacheReadInputTokens += usage.cache_read_input_tokens ?? 0
  modelUsage.cacheCreationInputTokens += usage.cache_creation_input_tokens ?? 0
  // Web search requests are tracked under server_tool_use in the usage object
  modelUsage.webSearchRequests +=
    usage.server_tool_use?.web_search_requests ?? 0
  modelUsage.costUSD += cost
  // Set context window and max output tokens (always use current values)
  modelUsage.contextWindow = getContextWindowForModel(model, getSdkBetas())
  modelUsage.maxOutputTokens = getModelMaxOutputTokens(model).default
  return modelUsage
}

// Main entry point for recording costs after each API response.
// Called from the query pipeline after every successful API call.
//
// This function:
//   1. Accumulates per-model usage totals
//   2. Updates global cost state in bootstrap/state.ts
//   3. Records OpenTelemetry metrics (cost counter, token counters by type)
//   4. Recursively processes advisor usage (sub-model calls within the response)
//   5. Returns the total cost including advisor costs
//
// @param cost - The USD cost of this API call (calculated by the caller)
// @param usage - The token usage object from the API response
// @param model - The model name used for this API call
// @returns Total cost including any recursive advisor costs
export function addToTotalSessionCost(
  cost: number,
  usage: Usage,
  model: string,
): number {
  // Update per-model usage totals
  const modelUsage = addToTotalModelUsage(cost, usage, model)
  // Update global cost state (used by getTotalCostUSD() and the /cost command)
  addToTotalCostState(cost, modelUsage, model)

  // Build OpenTelemetry attributes — includes speed attribute in fast mode
  const attrs =
    isFastModeEnabled() && usage.speed === 'fast'
      ? { model, speed: 'fast' }
      : { model }

  // Record cost and token metrics via OpenTelemetry counters
  // These are exported to observability backends for monitoring
  getCostCounter()?.add(cost, attrs)
  getTokenCounter()?.add(usage.input_tokens, { ...attrs, type: 'input' })
  getTokenCounter()?.add(usage.output_tokens, { ...attrs, type: 'output' })
  getTokenCounter()?.add(usage.cache_read_input_tokens ?? 0, {
    ...attrs,
    type: 'cacheRead',
  })
  getTokenCounter()?.add(usage.cache_creation_input_tokens ?? 0, {
    ...attrs,
    type: 'cacheCreation',
  })

  // Track total cost including advisor sub-model usage.
  // Advisors are sub-models invoked within the main API call (e.g., for
  // internal routing or classification). Their costs are tracked separately
  // and logged as analytics events, then recursively accumulated.
  let totalCost = cost
  for (const advisorUsage of getAdvisorUsage(usage)) {
    // Calculate cost for this advisor sub-model call
    const advisorCost = calculateUSDCost(advisorUsage.model, advisorUsage)
    // Log advisor usage as a separate analytics event for monitoring
    logEvent('tengu_advisor_tool_token_usage', {
      advisor_model:
        advisorUsage.model as AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
      input_tokens: advisorUsage.input_tokens,
      output_tokens: advisorUsage.output_tokens,
      cache_read_input_tokens: advisorUsage.cache_read_input_tokens ?? 0,
      cache_creation_input_tokens:
        advisorUsage.cache_creation_input_tokens ?? 0,
      cost_usd_micros: Math.round(advisorCost * 1_000_000),
    })
    // Recursively add advisor cost to total (advisors may themselves have advisors)
    totalCost += addToTotalSessionCost(
      advisorCost,
      advisorUsage,
      advisorUsage.model,
    )
  }
  return totalCost
}

