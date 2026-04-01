// =============================================================================
// src/shims/bun-bundle.ts — Runtime shim for Bun's compile-time feature flags
// =============================================================================
//
// In production, Claude Code is built with Bun's native bundler which provides
// a special `bun:bundle` module. The `feature()` function from this module
// evaluates to a boolean constant at COMPILE TIME, enabling dead-code
// elimination (DCE):
//
//   import { feature } from 'bun:bundle'
//
//   if (feature('VOICE_MODE')) {
//     // This entire block is removed from the bundle if VOICE_MODE is false
//     const voiceCommand = require('./commands/voice/index.js').default
//   }
//
// Since we're building with esbuild (not Bun's bundler), `bun:bundle` doesn't
// exist. The build script aliases it to this file:
//
//   alias: { 'bun:bundle': 'src/shims/bun-bundle.ts' }
//
// Instead of compile-time evaluation, our feature() reads environment variables
// at runtime. This means:
//   - Feature-gated code is NOT stripped from the bundle (slightly larger output)
//   - Features can be toggled without rebuilding (set env vars before running)
//   - All 24 feature flags default to false (safe external build defaults)
//
// To enable a feature at runtime:
//   CLAUDE_CODE_VOICE_MODE=1 node dist/cli.mjs
//   CLAUDE_CODE_BRIDGE_MODE=true node dist/cli.mjs
//
// =============================================================================

// ---------------------------------------------------------------------------
// Feature flag registry
// ---------------------------------------------------------------------------
// Each flag maps to an environment variable (CLAUDE_CODE_<FLAG_NAME>).
// The second argument to envBool() is the default when the env var is unset.
//
// Flag categories:
//   - Agent behavior:  PROACTIVE, COORDINATOR_MODE, FORK_SUBAGENT
//   - UI features:     VOICE_MODE, BUDDY, TORCH, ULTRAPLAN
//   - Infrastructure:  DAEMON, BG_SESSIONS, BRIDGE_MODE
//   - Experimental:    KAIROS, HISTORY_SNIP, REACTIVE_COMPACT, MCP_SKILLS
//   - Internal-only:   ABLATION_BASELINE (always false for external builds)
// ---------------------------------------------------------------------------
const FEATURE_FLAGS: Record<string, boolean> = {
  // Proactive agent mode — Claude takes autonomous actions without waiting for user input
  PROACTIVE: envBool('CLAUDE_CODE_PROACTIVE', false),

  // Kairos subsystem — background job scheduler and event-driven agent triggers
  KAIROS: envBool('CLAUDE_CODE_KAIROS', false),
  // Kairos brief mode — lightweight kairos with abbreviated output
  KAIROS_BRIEF: envBool('CLAUDE_CODE_KAIROS_BRIEF', false),
  // Kairos GitHub webhook integration — triggers agents on GitHub events (PR, issue, etc.)
  KAIROS_GITHUB_WEBHOOKS: envBool('CLAUDE_CODE_KAIROS_GITHUB_WEBHOOKS', false),

  // IDE bridge mode — bidirectional communication with VS Code / JetBrains extensions.
  // When enabled, the CLI can run as a backend for IDE-based interfaces,
  // routing permission prompts and UI to the IDE instead of the terminal.
  BRIDGE_MODE: envBool('CLAUDE_CODE_BRIDGE_MODE', false),

  // Background daemon mode — long-running supervisor process that manages
  // worker agents. Used for persistent agent sessions.
  DAEMON: envBool('CLAUDE_CODE_DAEMON', false),

  // Voice input/output — speech-to-text and text-to-speech for hands-free
  // interaction. Requires Anthropic OAuth token for the voice API.
  VOICE_MODE: envBool('CLAUDE_CODE_VOICE_MODE', false),

  // Agent triggers — allows agents to be triggered by external events
  // (webhooks, cron jobs, file watches, etc.)
  AGENT_TRIGGERS: envBool('CLAUDE_CODE_AGENT_TRIGGERS', false),

  // Monitor tool — real-time monitoring of MCP server status and agent activity
  MONITOR_TOOL: envBool('CLAUDE_CODE_MONITOR_TOOL', false),

  // Multi-agent coordinator mode — orchestrates teams of parallel agents
  // working on different aspects of a task. Enables TeamCreateTool,
  // TeamDeleteTool, and SendMessageTool.
  COORDINATOR_MODE: envBool('CLAUDE_CODE_COORDINATOR_MODE', false),

  // Ablation baseline — strips all advanced features for A/B testing.
  // Always false for external builds (Anthropic-internal testing only).
  ABLATION_BASELINE: false,

  // Dump system prompt — enables --dump-system-prompt CLI flag for
  // extracting the rendered system prompt (used by prompt sensitivity evals)
  DUMP_SYSTEM_PROMPT: envBool('CLAUDE_CODE_DUMP_SYSTEM_PROMPT', false),

  // Background sessions — enables `claude ps`, `claude logs`, `claude attach`,
  // `claude kill`, and the --bg/--background flags for detached sessions.
  BG_SESSIONS: envBool('CLAUDE_CODE_BG_SESSIONS', false),

  // History snip — enables conversation history snipping/projection
  // for more efficient context management across long sessions
  HISTORY_SNIP: envBool('CLAUDE_CODE_HISTORY_SNIP', false),

  // Workflow scripts — enables the WorkflowTool for defining and
  // executing multi-step automated workflows
  WORKFLOW_SCRIPTS: envBool('CLAUDE_CODE_WORKFLOW_SCRIPTS', false),

  // CCR remote setup — Claude Code Remote container environment setup
  CCR_REMOTE_SETUP: envBool('CLAUDE_CODE_CCR_REMOTE_SETUP', false),

  // Experimental skill search — enhanced skill discovery using
  // semantic search instead of simple name matching
  EXPERIMENTAL_SKILL_SEARCH: envBool('CLAUDE_CODE_EXPERIMENTAL_SKILL_SEARCH', false),

  // Ultra-planning mode — extended planning with multi-step verification
  ULTRAPLAN: envBool('CLAUDE_CODE_ULTRAPLAN', false),

  // Torch — session handoff / "passing the torch" between agents
  TORCH: envBool('CLAUDE_CODE_TORCH', false),

  // UDS inbox — Unix Domain Socket based inbox for inter-process communication
  UDS_INBOX: envBool('CLAUDE_CODE_UDS_INBOX', false),

  // Fork subagent — enables forking the current session into a sub-agent
  FORK_SUBAGENT: envBool('CLAUDE_CODE_FORK_SUBAGENT', false),

  // Buddy — companion sprite / Easter egg UI element
  BUDDY: envBool('CLAUDE_CODE_BUDDY', false),

  // MCP skills — enables creating skills from MCP server resources
  MCP_SKILLS: envBool('CLAUDE_CODE_MCP_SKILLS', false),

  // Reactive compact — on-demand compaction strategy that compresses
  // conversation history when the context window is approaching limits
  REACTIVE_COMPACT: envBool('CLAUDE_CODE_REACTIVE_COMPACT', false),
}

// ---------------------------------------------------------------------------
// Helper: parse a boolean from an environment variable.
// Accepts "1" or "true" (case-sensitive) as truthy values.
// Returns the fallback if the variable is not set (undefined).
// ---------------------------------------------------------------------------
function envBool(key: string, fallback: boolean): boolean {
  const v = process.env[key]
  if (v === undefined) return fallback
  return v === '1' || v === 'true'
}

// ---------------------------------------------------------------------------
// Public API: check if a feature flag is enabled.
//
// Usage in source code:
//   import { feature } from 'bun:bundle'
//   if (feature('VOICE_MODE')) { ... }
//
// Returns false for unknown flag names (safe default).
// ---------------------------------------------------------------------------
export function feature(name: string): boolean {
  return FEATURE_FLAGS[name] ?? false
}
