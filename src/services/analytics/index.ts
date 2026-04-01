// =============================================================================
// Analytics Service — Public API for Event Logging
// =============================================================================
// This module implements the "queue-before-sink" pattern for analytics:
//
//   1. QUEUE PHASE (before app initialization completes):
//      Events are buffered in an in-memory array (eventQueue). This allows
//      code throughout the codebase to call logEvent() at import time or
//      during early startup without worrying about initialization order.
//
//   2. SINK ATTACHMENT (during app startup):
//      attachAnalyticsSink() is called with the concrete sink implementation.
//      All queued events are drained asynchronously (via queueMicrotask) to
//      avoid blocking the startup critical path.
//
//   3. LIVE PHASE (after sink is attached):
//      Events flow directly to the sink, which handles routing to:
//      - Datadog (general-access observability — PII-tagged fields stripped)
//      - First-party (1P) event logging (PII-tagged proto columns preserved)
//
// Event metadata enrichment happens in the sink (sink.ts), NOT here. This
// module is intentionally dependency-free to prevent import cycles — it's
// imported by nearly every module in the codebase.
//
// PII protection:
//   - String values in metadata are typed as `never` (via the marker types
//     below) to force explicit verification that values don't contain code
//     or file paths. Callers must cast with the long type name as an
//     acknowledgment that they've checked.
//   - _PROTO_* prefixed keys are reserved for PII-tagged columns that only
//     the 1P exporter sees. stripProtoFields() removes them before Datadog.
// =============================================================================

/**
 * Analytics service - public API for event logging
 *
 * This module serves as the main entry point for analytics events in Claude CLI.
 *
 * DESIGN: This module has NO dependencies to avoid import cycles.
 * Events are queued until attachAnalyticsSink() is called during app initialization.
 * The sink handles routing to Datadog and 1P event logging.
 */

// =============================================================================
// Marker types for PII/sensitive data protection
// =============================================================================
// These `never` types act as compile-time guardrails. Since no value can be
// assigned to `never` without an explicit cast, they force developers to
// acknowledge (via the descriptive type name) that they've verified the
// value doesn't contain sensitive information before logging it.

/**
 * Marker type for verifying analytics metadata doesn't contain sensitive data
 *
 * This type forces explicit verification that string values being logged
 * don't contain code snippets, file paths, or other sensitive information.
 *
 * Usage: `myString as AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS`
 */
export type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS = never

/**
 * Marker type for values routed to PII-tagged proto columns via `_PROTO_*`
 * payload keys. The destination BQ column has privileged access controls,
 * so unredacted values are acceptable — unlike general-access backends.
 *
 * sink.ts strips `_PROTO_*` keys before Datadog fanout; only the 1P
 * exporter (firstPartyEventLoggingExporter) sees them and hoists them to the
 * top-level proto field. A single stripProtoFields call guards all non-1P
 * sinks — no per-sink filtering to forget.
 *
 * Usage: `rawName as AnalyticsMetadata_I_VERIFIED_THIS_IS_PII_TAGGED`
 */
export type AnalyticsMetadata_I_VERIFIED_THIS_IS_PII_TAGGED = never

// =============================================================================
// stripProtoFields — Removes PII-tagged keys before general-access storage
// =============================================================================
// Keys prefixed with `_PROTO_` are intended only for the first-party (1P)
// exporter which writes them to PII-tagged BigQuery proto columns with
// restricted access controls. This function strips them before sending to
// Datadog or any other general-access backend.
//
// Optimization: returns the original object reference unchanged when no
// _PROTO_ keys are present (avoids unnecessary shallow copy).

/**
 * Strip `_PROTO_*` keys from a payload destined for general-access storage.
 * Used by:
 *   - sink.ts: before Datadog fanout (never sees PII-tagged values)
 *   - firstPartyEventLoggingExporter: defensive strip of additional_metadata
 *     after hoisting known _PROTO_* keys to proto fields — prevents a future
 *     unrecognized _PROTO_foo from silently landing in the BQ JSON blob.
 *
 * Returns the input unchanged (same reference) when no _PROTO_ keys present.
 */
export function stripProtoFields<V>(
  metadata: Record<string, V>,
): Record<string, V> {
  let result: Record<string, V> | undefined
  for (const key in metadata) {
    if (key.startsWith('_PROTO_')) {
      if (result === undefined) {
        result = { ...metadata }
      }
      delete result[key]
    }
  }
  return result ?? metadata
}

// =============================================================================
// Internal types for the event queue
// =============================================================================

// LogEventMetadata restricts values to boolean | number | undefined.
// Strings are intentionally excluded to prevent accidental logging of
// code, file paths, or other sensitive data. String values must go through
// the AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS marker type.
// Internal type for logEvent metadata - different from the enriched EventMetadata in metadata.ts
type LogEventMetadata = { [key: string]: boolean | number | undefined }

// QueuedEvent represents a single buffered event waiting for the sink.
// The `async` flag determines whether it's dispatched via logEvent or logEventAsync.
type QueuedEvent = {
  eventName: string
  metadata: LogEventMetadata
  async: boolean
}

// =============================================================================
// AnalyticsSink — Interface for the analytics backend
// =============================================================================
// The sink receives enriched events and routes them to storage backends.
// The concrete implementation (in sink.ts) handles:
//   - Event sampling (based on GrowthBook dynamic config)
//   - Metadata enrichment (session ID, user type, model, etc.)
//   - Routing to Datadog (via dogstatsd/HTTP) and first-party exporter
//   - PII field stripping for general-access backends

/**
 * Sink interface for the analytics backend
 */
export type AnalyticsSink = {
  // Fire-and-forget event logging (most common path)
  logEvent: (eventName: string, metadata: LogEventMetadata) => void
  // Awaitable event logging (used when the caller needs confirmation of delivery)
  logEventAsync: (
    eventName: string,
    metadata: LogEventMetadata,
  ) => Promise<void>
}

// =============================================================================
// Event Queue and Sink State
// =============================================================================
// The queue accumulates events during the startup phase before the sink is ready.
// Once the sink attaches, queued events are drained and future events flow directly.

// Event queue for events logged before sink is attached
// This is the core of the "queue-before-sink" pattern — events accumulate here
// during the startup phase when the sink hasn't been initialized yet.
const eventQueue: QueuedEvent[] = []

// The active analytics sink — null until attachAnalyticsSink() is called.
// All logEvent/logEventAsync calls check this before dispatching.
// Sink - initialized during app startup
let sink: AnalyticsSink | null = null

// =============================================================================
// attachAnalyticsSink — Connects the event pipeline to its backend
// =============================================================================
// This is called once during app initialization (from the preAction hook
// for subcommands, or from setup() for the default command). It:
//   1. Stores the sink reference for future direct dispatch
//   2. Drains any queued events asynchronously (via queueMicrotask)
//   3. Is idempotent — safe to call multiple times

/**
 * Attach the analytics sink that will receive all events.
 * Queued events are drained asynchronously via queueMicrotask to avoid
 * adding latency to the startup path.
 *
 * Idempotent: if a sink is already attached, this is a no-op. This allows
 * calling from both the preAction hook (for subcommands) and setup() (for
 * the default command) without coordination.
 */
export function attachAnalyticsSink(newSink: AnalyticsSink): void {
  // Idempotent guard — prevent double-attachment
  if (sink !== null) {
    return
  }
  sink = newSink

  // Drain the queue asynchronously to avoid blocking startup.
  // queueMicrotask runs after the current task completes but before any
  // I/O events, ensuring events are dispatched promptly without adding
  // latency to the synchronous startup path.
  // Drain the queue asynchronously to avoid blocking startup
  if (eventQueue.length > 0) {
    // Snapshot the queue and clear it — any events logged during drain
    // will go directly to the sink (since sink is now set).
    const queuedEvents = [...eventQueue]
    eventQueue.length = 0

    // Log queue size for ants to help debug analytics initialization timing
    if (process.env.USER_TYPE === 'ant') {
      sink.logEvent('analytics_sink_attached', {
        queued_event_count: queuedEvents.length,
      })
    }

    // Dispatch queued events in a microtask — each event is sent via the
    // appropriate method (sync or async) based on how it was originally logged.
    queueMicrotask(() => {
      for (const event of queuedEvents) {
        if (event.async) {
          void sink!.logEventAsync(event.eventName, event.metadata)
        } else {
          sink!.logEvent(event.eventName, event.metadata)
        }
      }
    })
  }
}

// =============================================================================
// logEvent — Synchronous (fire-and-forget) event logging
// =============================================================================
// The primary API for logging analytics events. Events are either:
//   - Dispatched immediately to the sink (if attached), or
//   - Queued for later dispatch (if sink hasn't been attached yet)
//
// The metadata type intentionally excludes raw strings to prevent accidental
// PII leakage. Only boolean, number, and undefined values are allowed.

/**
 * Log an event to analytics backends (synchronous)
 *
 * Events may be sampled based on the 'tengu_event_sampling_config' dynamic config.
 * When sampled, the sample_rate is added to the event metadata.
 *
 * If no sink is attached, events are queued and drained when the sink attaches.
 */
export function logEvent(
  eventName: string,
  // intentionally no strings unless AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
  // to avoid accidentally logging code/filepaths
  metadata: LogEventMetadata,
): void {
  // Queue phase: buffer events until sink is ready
  if (sink === null) {
    eventQueue.push({ eventName, metadata, async: false })
    return
  }
  // Live phase: dispatch directly to the sink
  sink.logEvent(eventName, metadata)
}

// =============================================================================
// logEventAsync — Awaitable event logging
// =============================================================================
// Same queue-or-dispatch pattern as logEvent, but returns a Promise so
// callers can await delivery confirmation. Used for critical events where
// the caller needs to ensure the event was sent (e.g. before process exit).

/**
 * Log an event to analytics backends (asynchronous)
 *
 * Events may be sampled based on the 'tengu_event_sampling_config' dynamic config.
 * When sampled, the sample_rate is added to the event metadata.
 *
 * If no sink is attached, events are queued and drained when the sink attaches.
 */
export async function logEventAsync(
  eventName: string,
  // intentionally no strings, to avoid accidentally logging code/filepaths
  metadata: LogEventMetadata,
): Promise<void> {
  // Queue phase: buffer events until sink is ready
  if (sink === null) {
    eventQueue.push({ eventName, metadata, async: true })
    return
  }
  // Live phase: dispatch directly and await confirmation
  await sink.logEventAsync(eventName, metadata)
}

// =============================================================================
// _resetForTesting — Test-only state reset
// =============================================================================
// Resets the module's internal state (sink + queue) for test isolation.
// This ensures tests start with a clean analytics state.

/**
 * Reset analytics state for testing purposes only.
 * @internal
 */
export function _resetForTesting(): void {
  sink = null
  eventQueue.length = 0
}

