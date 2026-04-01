// =============================================================================
// Context Collection Module
// =============================================================================
// This module is responsible for collecting the contextual information that
// gets prepended to every conversation as part of the system prompt. It
// provides two main pieces of context:
//
//   1. getSystemContext() — Git repository information:
//      - Current branch name
//      - Default/main branch name (for PR targeting)
//      - Git status (modified/staged files, truncated at 2KB)
//      - Recent commit log (last 5 commits)
//      - Git user name
//      This context is a point-in-time snapshot taken at conversation start
//      and does NOT update during the conversation.
//
//   2. getUserContext() — User configuration and memory files:
//      - CLAUDE.md files (project-level, user-level, and from --add-dir)
//        These files contain user-defined instructions, project context,
//        coding conventions, and other persistent guidance.
//      - Current date (for time-aware responses)
//
// Both functions are memoized (via lodash memoize) so they're computed once
// per conversation and cached for the duration. The memoization cache can be
// cleared (e.g. when system prompt injection changes).
//
// Special modes:
//   - CCR (Claude Code Remote): Skips git status (unnecessary overhead on resume)
//   - Bare mode (--bare): Skips auto-discovery of CLAUDE.md files, but honors
//     explicit --add-dir directories
//   - CLAUDE_CODE_DISABLE_CLAUDE_MDS: Hard disable of all CLAUDE.md loading
// =============================================================================

import { feature } from 'bun:bundle'
// lodash memoize — caches the result of async functions so they're only
// computed once per conversation. The .cache.clear() method allows
// invalidation when the system prompt injection changes.
import memoize from 'lodash-es/memoize.js'
import {
  getAdditionalDirectoriesForClaudeMd,
  setCachedClaudeMdContent,
} from './bootstrap/state.js'
// Provides the current date in local ISO format (e.g. "2024-01-15")
import { getLocalISODate } from './constants/common.js'
// CLAUDE.md loading pipeline:
//   - getMemoryFiles() discovers all memory files (CLAUDE.md, .claude/settings.md, etc.)
//   - filterInjectedMemoryFiles() removes server-injected memory files
//   - getClaudeMds() reads and concatenates the discovered files
import {
  filterInjectedMemoryFiles,
  getClaudeMds,
  getMemoryFiles,
} from './utils/claudemd.js'
import { logForDiagnosticsNoPII } from './utils/diagLogs.js'
import { isBareMode, isEnvTruthy } from './utils/envUtils.js'
// Git utilities — all git operations are non-throwing (return null on failure)
import { execFileNoThrow } from './utils/execFileNoThrow.js'
import { getBranch, getDefaultBranch, getIsGit, gitExe } from './utils/git.js'
// Checks user settings to determine if git instructions should be included
import { shouldIncludeGitInstructions } from './utils/gitSettings.js'
import { logError } from './utils/log.js'

// Maximum characters for git status output before truncation.
// Large repos with many modified files can produce enormous status output
// that would consume too much of the context window.
const MAX_STATUS_CHARS = 2000

// =============================================================================
// System Prompt Injection (ant-only debugging feature)
// =============================================================================
// Allows Anthropic employees to inject arbitrary text into the system prompt
// for cache-breaking during debugging. When the injection changes, both
// getUserContext and getSystemContext caches are cleared so the new injection
// takes effect immediately.

// System prompt injection for cache breaking (ant-only, ephemeral debugging state)
let systemPromptInjection: string | null = null

// Returns the current system prompt injection value (null if none set)
export function getSystemPromptInjection(): string | null {
  return systemPromptInjection
}

// Sets a new system prompt injection and immediately invalidates the
// memoized context caches so the next call picks up the new value.
export function setSystemPromptInjection(value: string | null): void {
  systemPromptInjection = value
  // Clear context caches immediately when injection changes
  getUserContext.cache.clear?.()
  getSystemContext.cache.clear?.()
}

// =============================================================================
// getGitStatus — Collects a snapshot of the current git repository state
// =============================================================================
// Runs multiple git commands in parallel to efficiently collect:
//   - Current branch (git rev-parse --abbrev-ref HEAD)
//   - Default branch (detected from origin/HEAD or common names)
//   - Working directory status (git status --short)
//   - Last 5 commits (git log --oneline -n 5)
//   - Git user name (git config user.name)
//
// The output is formatted as a human-readable string that becomes part of
// the system prompt. Status output is truncated at 2KB to prevent large
// repos from consuming too much context.
//
// Memoized: the git status is only collected once per conversation. This is
// intentional — it's a snapshot, not a live view. The model is told this
// explicitly in the output text.
export const getGitStatus = memoize(async (): Promise<string | null> => {
  if (process.env.NODE_ENV === 'test') {
    // Avoid cycles in tests — git operations can hang or produce
    // non-deterministic output in test environments
    // Avoid cycles in tests
    return null
  }

  const startTime = Date.now()
  logForDiagnosticsNoPII('info', 'git_status_started')

  // First check if we're even in a git repo. This is a fast check that
  // prevents the more expensive git commands from being run unnecessarily.
  const isGitStart = Date.now()
  const isGit = await getIsGit()
  logForDiagnosticsNoPII('info', 'git_is_git_check_completed', {
    duration_ms: Date.now() - isGitStart,
    is_git: isGit,
  })

  if (!isGit) {
    logForDiagnosticsNoPII('info', 'git_status_skipped_not_git', {
      duration_ms: Date.now() - startTime,
    })
    return null
  }

  try {
    const gitCmdsStart = Date.now()
    // Run all git commands in parallel for efficiency.
    // --no-optional-locks prevents git from acquiring the index lock,
    // which avoids contention with concurrent git operations (e.g. IDE git plugins).
    // execFileNoThrow returns empty strings on failure (non-throwing).
    const [branch, mainBranch, status, log, userName] = await Promise.all([
      getBranch(),
      getDefaultBranch(),
      execFileNoThrow(gitExe(), ['--no-optional-locks', 'status', '--short'], {
        preserveOutputOnError: false,
      }).then(({ stdout }) => stdout.trim()),
      execFileNoThrow(
        gitExe(),
        ['--no-optional-locks', 'log', '--oneline', '-n', '5'],
        {
          preserveOutputOnError: false,
        },
      ).then(({ stdout }) => stdout.trim()),
      execFileNoThrow(gitExe(), ['config', 'user.name'], {
        preserveOutputOnError: false,
      }).then(({ stdout }) => stdout.trim()),
    ])

    logForDiagnosticsNoPII('info', 'git_commands_completed', {
      duration_ms: Date.now() - gitCmdsStart,
      status_length: status.length,
    })

    // Check if status exceeds character limit and truncate if needed.
    // Repos with many modified files (e.g. after a large refactor) can produce
    // status output that would waste context window tokens. The truncation
    // message tells the model to use BashTool for the full status if needed.
    // Check if status exceeds character limit
    const truncatedStatus =
      status.length > MAX_STATUS_CHARS
        ? status.substring(0, MAX_STATUS_CHARS) +
          '\n... (truncated because it exceeds 2k characters. If you need more information, run "git status" using BashTool)'
        : status

    logForDiagnosticsNoPII('info', 'git_status_completed', {
      duration_ms: Date.now() - startTime,
      truncated: status.length > MAX_STATUS_CHARS,
    })

    // Assemble the git status into a formatted string for the system prompt.
    // The explicit "snapshot in time" note is important — it sets the model's
    // expectation that this data may become stale during the conversation.
    return [
      `This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.`,
      `Current branch: ${branch}`,
      `Main branch (you will usually use this for PRs): ${mainBranch}`,
      ...(userName ? [`Git user: ${userName}`] : []),
      `Status:\n${truncatedStatus || '(clean)'}`,
      `Recent commits:\n${log}`,
    ].join('\n\n')
  } catch (error) {
    logForDiagnosticsNoPII('error', 'git_status_failed', {
      duration_ms: Date.now() - startTime,
    })
    logError(error)
    return null
  }
})

// =============================================================================
// getSystemContext — Collects system-level context for the system prompt
// =============================================================================
// Returns a key-value map of system context that is injected into the system
// prompt at conversation start. Currently includes:
//   - gitStatus: Repository state snapshot (branch, status, recent commits)
//   - cacheBreaker: Optional injection for cache-breaking (ant-only debug feature)
//
// Memoized: computed once and cached for the conversation lifetime.
// The cache is cleared when setSystemPromptInjection() is called.

/**
 * This context is prepended to each conversation, and cached for the duration of the conversation.
 */
export const getSystemContext = memoize(
  async (): Promise<{
    [k: string]: string
  }> => {
    const startTime = Date.now()
    logForDiagnosticsNoPII('info', 'system_context_started')

    // Skip git status collection in two cases:
    //   1. CCR (Claude Code Remote) — git status adds unnecessary overhead on session resume
    //   2. Git instructions disabled by user settings
    // Skip git status in CCR (unnecessary overhead on resume) or when git instructions are disabled
    const gitStatus =
      isEnvTruthy(process.env.CLAUDE_CODE_REMOTE) ||
      !shouldIncludeGitInstructions()
        ? null
        : await getGitStatus()

    // Include system prompt injection if set (for cache breaking, ant-only).
    // This injects arbitrary text wrapped in a [CACHE_BREAKER: ...] tag,
    // which forces the prompt cache to miss (useful for debugging prompt changes).
    // Include system prompt injection if set (for cache breaking, ant-only)
    const injection = feature('BREAK_CACHE_COMMAND')
      ? getSystemPromptInjection()
      : null

    logForDiagnosticsNoPII('info', 'system_context_completed', {
      duration_ms: Date.now() - startTime,
      has_git_status: gitStatus !== null,
      has_injection: injection !== null,
    })

    // Return only non-null context entries. The spread-with-conditional pattern
    // ensures empty keys are omitted from the returned object.
    return {
      ...(gitStatus && { gitStatus }),
      ...(feature('BREAK_CACHE_COMMAND') && injection
        ? {
            cacheBreaker: `[CACHE_BREAKER: ${injection}]`,
          }
        : {}),
    }
  },
)

// =============================================================================
// getUserContext — Loads user configuration and memory files
// =============================================================================
// Returns a key-value map of user-specific context that is injected into the
// system prompt. Currently includes:
//   - claudeMd: Concatenated contents of all discovered CLAUDE.md files
//     (project-level, user-level, and from --add-dir directories).
//     These files contain user-defined instructions, coding conventions,
//     project context, and other persistent guidance for the model.
//   - currentDate: Today's date in local ISO format (for time-aware responses)
//
// CLAUDE.md discovery rules:
//   - CLAUDE_CODE_DISABLE_CLAUDE_MDS=1: Hard disable, never loads any files
//   - --bare mode: Skips auto-discovery (cwd walk) BUT honors explicit --add-dir
//   - Normal mode: Walks up from cwd to find CLAUDE.md files at each level
//
// The loaded CLAUDE.md content is also cached in bootstrap state (via
// setCachedClaudeMdContent) for the yoloClassifier to read without creating
// an import cycle.
//
// Memoized: computed once and cached for the conversation lifetime.

/**
 * This context is prepended to each conversation, and cached for the duration of the conversation.
 */
export const getUserContext = memoize(
  async (): Promise<{
    [k: string]: string
  }> => {
    const startTime = Date.now()
    logForDiagnosticsNoPII('info', 'user_context_started')

    // Determine whether to load CLAUDE.md files based on environment config.
    // Two cases disable loading:
    //   1. CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 — explicit hard disable
    //   2. --bare mode with no --add-dir — skip auto-discovery entirely
    // CLAUDE_CODE_DISABLE_CLAUDE_MDS: hard off, always.
    // --bare: skip auto-discovery (cwd walk), BUT honor explicit --add-dir.
    // --bare means "skip what I didn't ask for", not "ignore what I asked for".
    const shouldDisableClaudeMd =
      isEnvTruthy(process.env.CLAUDE_CODE_DISABLE_CLAUDE_MDS) ||
      (isBareMode() && getAdditionalDirectoriesForClaudeMd().length === 0)
    // Load and concatenate CLAUDE.md files from discovered memory file paths.
    // The pipeline: getMemoryFiles() → filterInjectedMemoryFiles() → getClaudeMds()
    //   - getMemoryFiles() discovers all memory files by walking up from cwd
    //   - filterInjectedMemoryFiles() removes server-injected files (not user-authored)
    //   - getClaudeMds() reads the files and concatenates their contents
    // Await the async I/O (readFile/readdir directory walk) so the event
    // loop yields naturally at the first fs.readFile.
    const claudeMd = shouldDisableClaudeMd
      ? null
      : getClaudeMds(filterInjectedMemoryFiles(await getMemoryFiles()))
    // Cache the loaded CLAUDE.md content for the yoloClassifier to read.
    // This avoids a direct import of claudemd.ts from yoloClassifier.ts,
    // which would create an import cycle through the permissions system.
    // Cache for the auto-mode classifier (yoloClassifier.ts reads this
    // instead of importing claudemd.ts directly, which would create a
    // cycle through permissions/filesystem → permissions → yoloClassifier).
    setCachedClaudeMdContent(claudeMd || null)

    logForDiagnosticsNoPII('info', 'user_context_completed', {
      duration_ms: Date.now() - startTime,
      claudemd_length: claudeMd?.length ?? 0,
      claudemd_disabled: Boolean(shouldDisableClaudeMd),
    })

    // Return the user context map. claudeMd is only included if non-null/non-empty.
    // currentDate is always included to give the model awareness of today's date.
    return {
      ...(claudeMd && { claudeMd }),
      currentDate: `Today's date is ${getLocalISODate()}.`,
    }
  },
)

