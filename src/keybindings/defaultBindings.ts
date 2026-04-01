// =============================================================================
// defaultBindings.ts — Default Keybinding Configuration
// =============================================================================
// Defines the complete set of default keybindings for Claude Code. These bindings
// are loaded first, then user overrides from keybindings.json are merged on top.
//
// ─── Keybinding Context Hierarchy ────────────────────────────────────────────
// Keybindings are organized into "contexts" — each context represents a UI mode
// or screen. When multiple contexts are active, bindings are resolved from the
// most specific (innermost) context first. The contexts are:
//
//   Global          — Always active. App-wide actions (ctrl+c, ctrl+l, ctrl+t, ctrl+o)
//   Chat            — Active when the prompt input is focused. Submit, mode cycle, undo
//   Autocomplete    — Active when the autocomplete dropdown is visible
//   Settings        — Active when the settings/config panel is open
//   Confirmation    — Active when a yes/no dialog is shown (permissions, etc.)
//   Tabs            — Active when tab navigation is available
//   Transcript      — Active when the transcript modal is open
//   HistorySearch   — Active when ctrl+r history search is open
//   Task            — Active when a foreground task (bash, agent) is running
//   ThemePicker     — Active when the theme picker is open
//   Scroll          — Active when the viewport is scrollable (fullscreen mode)
//   Help            — Active when the help overlay is shown
//   Attachments     — Active when image attachment navigation is active
//   Footer          — Active when the footer indicator bar has focus
//   MessageSelector — Active when the rewind message selector dialog is open
//   MessageActions  — Active when the message actions bar is visible
//   DiffDialog      — Active when the diff viewer dialog is open
//   ModelPicker     — Active when the model picker is open
//   Select          — Active when a generic select/list component has focus
//   Plugin          — Active when the plugin management dialog is open
//
// ─── Key Action Naming Convention ────────────────────────────────────────────
// Actions follow the pattern: `category:action`
//   - app:*           — Application-level actions (redraw, toggleTodos, exit)
//   - chat:*          — Chat input actions (submit, undo, cycleMode, imagePaste)
//   - history:*       — Command history navigation
//   - autocomplete:*  — Autocomplete dropdown actions
//   - confirm:*       — Confirmation dialog responses
//   - select:*        — List/select component navigation
//   - settings:*      — Settings panel actions
//   - transcript:*    — Transcript modal actions
//   - historySearch:* — History search modal actions
//   - task:*          — Running task actions (background)
//   - theme:*         — Theme picker actions
//   - scroll:*        — Viewport scrolling actions
//   - selection:*     — Text selection actions (copy)
//   - help:*          — Help overlay actions
//   - attachments:*   — Image attachment navigation
//   - footer:*        — Footer indicator navigation
//   - messageSelector:* — Rewind dialog navigation
//   - messageActions:*  — Message action bar navigation
//   - diff:*          — Diff dialog navigation
//   - modelPicker:*   — Model picker actions
//   - plugin:*        — Plugin dialog actions
//   - voice:*         — Voice mode actions
//   - tabs:*          — Tab navigation actions
// =============================================================================
import { feature } from 'bun:bundle'
// Semantic version comparison for checking runtime VT mode support
import { satisfies } from 'src/utils/semver.js'
// Checks if running under Bun runtime (vs Node.js) — affects VT mode detection
import { isRunningWithBun } from '../utils/bundledMode.js'
// Detects the current OS platform for platform-specific key bindings
import { getPlatform } from '../utils/platform.js'
import type { KeybindingBlock } from './types.js'

/**
 * Default keybindings that match current Claude Code behavior.
 * These are loaded first, then user keybindings.json overrides them.
 */

// Platform-specific image paste shortcut:
// - Windows: alt+v (ctrl+v is system paste)
// - Other platforms: ctrl+v
const IMAGE_PASTE_KEY = getPlatform() === 'windows' ? 'alt+v' : 'ctrl+v'

// Modifier-only chords (like shift+tab) may fail on Windows Terminal without VT mode
// See: https://github.com/microsoft/terminal/issues/879#issuecomment-618801651
// Node enabled VT mode in 24.2.0 / 22.17.0: https://github.com/nodejs/node/pull/58358
// Bun enabled VT mode in 1.2.23: https://github.com/oven-sh/bun/pull/21161
const SUPPORTS_TERMINAL_VT_MODE =
  getPlatform() !== 'windows' ||
  (isRunningWithBun()
    ? satisfies(process.versions.bun, '>=1.2.23')
    : satisfies(process.versions.node, '>=22.17.0 <23.0.0 || >=24.2.0'))

// Platform-specific mode cycle shortcut:
// - Windows without VT mode: meta+m (shift+tab doesn't work reliably)
// - Other platforms: shift+tab
const MODE_CYCLE_KEY = SUPPORTS_TERMINAL_VT_MODE ? 'shift+tab' : 'meta+m'

// The complete default keybinding configuration.
// Each block defines bindings for one context. The resolver walks contexts
// from most-specific to least-specific, returning the first matching binding.
// Users can override any binding in their keybindings.json file.
export const DEFAULT_BINDINGS: KeybindingBlock[] = [
  // ─── Global Context ──────────────────────────────────────────────────────
  // Always-active keybindings. These work regardless of which UI mode is active.
  // Includes: interrupt (ctrl+c), exit (ctrl+d), redraw, toggle panels, history search
  {
    context: 'Global',
    bindings: {
      // ctrl+c and ctrl+d use special time-based double-press handling.
      // They ARE defined here so the resolver can find them, but they
      // CANNOT be rebound by users - validation in reservedShortcuts.ts
      // will show an error if users try to override these keys.
      'ctrl+c': 'app:interrupt',
      'ctrl+d': 'app:exit',
      'ctrl+l': 'app:redraw',
      'ctrl+t': 'app:toggleTodos',
      'ctrl+o': 'app:toggleTranscript',
      ...(feature('KAIROS') || feature('KAIROS_BRIEF')
        ? { 'ctrl+shift+b': 'app:toggleBrief' as const }
        : {}),
      'ctrl+shift+o': 'app:toggleTeammatePreview',
      'ctrl+r': 'history:search',
      // File navigation. cmd+ bindings only fire on kitty-protocol terminals;
      // ctrl+shift is the portable fallback.
      ...(feature('QUICK_SEARCH')
        ? {
            'ctrl+shift+f': 'app:globalSearch' as const,
            'cmd+shift+f': 'app:globalSearch' as const,
            'ctrl+shift+p': 'app:quickOpen' as const,
            'cmd+shift+p': 'app:quickOpen' as const,
          }
        : {}),
      ...(feature('TERMINAL_PANEL') ? { 'meta+j': 'app:toggleTerminal' } : {}),
    },
  },
  // ─── Chat Context ──────────────────────────────────────────────────────
  // Active when the prompt input component has focus. Handles text submission,
  // mode cycling (normal → plan → bash), history navigation, undo, and
  // external editor integration. Also includes voice activation bindings.
  {
    context: 'Chat',
    bindings: {
      escape: 'chat:cancel',
      // ctrl+x chord prefix avoids shadowing readline editing keys (ctrl+a/b/e/f/...).
      'ctrl+x ctrl+k': 'chat:killAgents',
      [MODE_CYCLE_KEY]: 'chat:cycleMode',
      'meta+p': 'chat:modelPicker',
      'meta+o': 'chat:fastMode',
      'meta+t': 'chat:thinkingToggle',
      enter: 'chat:submit',
      up: 'history:previous',
      down: 'history:next',
      // Editing shortcuts (defined here, migration in progress)
      // Undo has two bindings to support different terminal behaviors:
      // - ctrl+_ for legacy terminals (send \x1f control char)
      // - ctrl+shift+- for Kitty protocol (sends physical key with modifiers)
      'ctrl+_': 'chat:undo',
      'ctrl+shift+-': 'chat:undo',
      // ctrl+x ctrl+e is the readline-native edit-and-execute-command binding.
      'ctrl+x ctrl+e': 'chat:externalEditor',
      'ctrl+g': 'chat:externalEditor',
      'ctrl+s': 'chat:stash',
      // Image paste shortcut (platform-specific key defined above)
      [IMAGE_PASTE_KEY]: 'chat:imagePaste',
      ...(feature('MESSAGE_ACTIONS')
        ? { 'shift+up': 'chat:messageActions' as const }
        : {}),
      // Voice activation (hold-to-talk). Registered so getShortcutDisplay
      // finds it without hitting the fallback analytics log. To rebind,
      // add a voice:pushToTalk entry (last wins); to disable, use /voice
      // — null-unbinding space hits a pre-existing useKeybinding.ts trap
      // where 'unbound' swallows the event (space dead for typing).
      ...(feature('VOICE_MODE') ? { space: 'voice:pushToTalk' } : {}),
    },
  },
  // ─── Autocomplete Context ──────────────────────────────────────────────
  // Active when the autocomplete suggestion dropdown is visible above the input.
  // Tab accepts, Escape dismisses, arrows navigate between suggestions.
  {
    context: 'Autocomplete',
    bindings: {
      tab: 'autocomplete:accept',
      escape: 'autocomplete:dismiss',
      up: 'autocomplete:previous',
      down: 'autocomplete:next',
    },
  },
  // ─── Settings Context ──────────────────────────────────────────────────
  // Active when the settings/config panel is open. Provides vi-style navigation
  // (j/k), Emacs-style navigation (ctrl+n/p), space to toggle, Enter to save,
  // and search via '/'. The panel uses Select actions for list navigation.
  {
    context: 'Settings',
    bindings: {
      // Settings menu uses escape only (not 'n') to dismiss
      escape: 'confirm:no',
      // Config panel list navigation (reuses Select actions)
      up: 'select:previous',
      down: 'select:next',
      k: 'select:previous',
      j: 'select:next',
      'ctrl+p': 'select:previous',
      'ctrl+n': 'select:next',
      // Toggle/activate the selected setting (space only — enter saves & closes)
      space: 'select:accept',
      // Save and close the config panel
      enter: 'settings:close',
      // Enter search mode
      '/': 'settings:search',
      // Retry loading usage data (only active on error)
      r: 'settings:retry',
    },
  },
  // ─── Confirmation Context ──────────────────────────────────────────────
  // Active when a yes/no confirmation dialog is shown (tool permissions,
  // exit confirmation, etc.). Supports y/n keys, Enter/Escape, and
  // additional navigation for multi-option dialogs.
  {
    context: 'Confirmation',
    bindings: {
      y: 'confirm:yes',
      n: 'confirm:no',
      enter: 'confirm:yes',
      escape: 'confirm:no',
      // Navigation for dialogs with lists
      up: 'confirm:previous',
      down: 'confirm:next',
      tab: 'confirm:nextField',
      space: 'confirm:toggle',
      // Cycle modes (used in file permission dialogs and teams dialog)
      'shift+tab': 'confirm:cycleMode',
      // Toggle permission explanation in permission dialogs
      'ctrl+e': 'confirm:toggleExplanation',
      // Toggle permission debug info
      'ctrl+d': 'permission:toggleDebug',
    },
  },
  // ─── Tabs Context ──────────────────────────────────────────────────────
  // Active when tab-based navigation is available (e.g., multi-panel views).
  // Tab/shift+tab and left/right arrows cycle between tabs.
  {
    context: 'Tabs',
    bindings: {
      // Tab cycling navigation
      tab: 'tabs:next',
      'shift+tab': 'tabs:previous',
      right: 'tabs:next',
      left: 'tabs:previous',
    },
  },
  // ─── Transcript Context ────────────────────────────────────────────────
  // Active when the transcript modal (ctrl+o) is open. This is a read-only
  // view of the full conversation. Supports toggle-show-all, exit, and
  // pager-style 'q' to quit (like less/tmux).
  {
    context: 'Transcript',
    bindings: {
      'ctrl+e': 'transcript:toggleShowAll',
      'ctrl+c': 'transcript:exit',
      escape: 'transcript:exit',
      // q — pager convention (less, tmux copy-mode). Transcript is a modal
      // reading view with no prompt, so q-as-literal-char has no owner.
      q: 'transcript:exit',
    },
  },
  // ─── History Search Context ────────────────────────────────────────────
  // Active when the ctrl+r reverse history search mode is open.
  // ctrl+r cycles through matches, tab/escape accepts, Enter executes,
  // and ctrl+c cancels without accepting.
  {
    context: 'HistorySearch',
    bindings: {
      'ctrl+r': 'historySearch:next',
      escape: 'historySearch:accept',
      tab: 'historySearch:accept',
      'ctrl+c': 'historySearch:cancel',
      enter: 'historySearch:execute',
    },
  },
  // ─── Task Context ──────────────────────────────────────────────────────
  // Active when a foreground task (bash command, agent) is running.
  // ctrl+b backgrounds the task so the user can continue chatting.
  {
    context: 'Task',
    bindings: {
      // Background running foreground tasks (bash commands, agents)
      // In tmux, users must press ctrl+b twice (tmux prefix escape)
      'ctrl+b': 'task:background',
    },
  },
  // ─── Theme Picker Context ──────────────────────────────────────────────
  // Active when the theme picker dialog is open.
  {
    context: 'ThemePicker',
    bindings: {
      'ctrl+t': 'theme:toggleSyntaxHighlighting',
    },
  },
  // ─── Scroll Context ────────────────────────────────────────────────────
  // Active when the viewport is scrollable (fullscreen/alt-screen mode).
  // Provides page up/down, mouse wheel, home/end, and clipboard copy
  // for text selection. Supports both standard and kitty keyboard protocol.
  {
    context: 'Scroll',
    bindings: {
      pageup: 'scroll:pageUp',
      pagedown: 'scroll:pageDown',
      wheelup: 'scroll:lineUp',
      wheeldown: 'scroll:lineDown',
      'ctrl+home': 'scroll:top',
      'ctrl+end': 'scroll:bottom',
      // Selection copy. ctrl+shift+c is standard terminal copy.
      // cmd+c only fires on terminals using the kitty keyboard
      // protocol (kitty/WezTerm/ghostty/iTerm2) where the super
      // modifier actually reaches the pty — inert elsewhere.
      // Esc-to-clear and contextual ctrl+c are handled via raw
      // useInput so they can conditionally propagate.
      'ctrl+shift+c': 'selection:copy',
      'cmd+c': 'selection:copy',
    },
  },
  // ─── Help Context ──────────────────────────────────────────────────────
  // Active when the help overlay (?) is displayed.
  {
    context: 'Help',
    bindings: {
      escape: 'help:dismiss',
    },
  },
  // ─── Attachments Context ───────────────────────────────────────────────
  // Active when the attachment tray (image/file chips) is visible above
  // the prompt. Left/right cycle through items, backspace/delete removes,
  // and down/escape exits back to the chat input.
  {
    context: 'Attachments',
    bindings: {
      right: 'attachments:next',
      left: 'attachments:previous',
      backspace: 'attachments:remove',
      delete: 'attachments:remove',
      down: 'attachments:exit',
      escape: 'attachments:exit',
    },
  },
  // ─── Footer Context ─────────────────────────────────────────────────────
  // Active when the footer indicator bar (tasks, teams, diff, loop count)
  // has focus. Arrows navigate between footer items, Enter opens, and
  // Escape clears the selection.
  {
    context: 'Footer',
    bindings: {
      up: 'footer:up',
      'ctrl+p': 'footer:up',
      down: 'footer:down',
      'ctrl+n': 'footer:down',
      right: 'footer:next',
      left: 'footer:previous',
      enter: 'footer:openSelected',
      escape: 'footer:clearSelection',
    },
  },
  // ─── MessageSelector Context ────────────────────────────────────────────
  // Active when the rewind/message selector dialog is open. Provides vim-style
  // (j/k), Emacs-style (ctrl+n/p), and arrow-key navigation. shift/meta/ctrl
  // modifiers jump to top/bottom of the message list.
  {
    context: 'MessageSelector',
    bindings: {
      up: 'messageSelector:up',
      down: 'messageSelector:down',
      k: 'messageSelector:up',
      j: 'messageSelector:down',
      'ctrl+p': 'messageSelector:up',
      'ctrl+n': 'messageSelector:down',
      'ctrl+up': 'messageSelector:top',
      'shift+up': 'messageSelector:top',
      'meta+up': 'messageSelector:top',
      'shift+k': 'messageSelector:top',
      'ctrl+down': 'messageSelector:bottom',
      'shift+down': 'messageSelector:bottom',
      'meta+down': 'messageSelector:bottom',
      'shift+j': 'messageSelector:bottom',
      enter: 'messageSelector:select',
    },
  },
  // ─── MessageActions Context ──────────────────────────────────────────────
  // Active when the message actions bar is visible (feature-flagged).
  // PromptInput unmounts while the cursor is in this context, so there are
  // no key conflicts with chat bindings. Supports vim/arrow navigation,
  // meta/super+arrow for top/bottom jumps, and shift+arrow for user-message
  // hopping. 'c' copies, 'p' pins, Enter activates the selected action.
  ...(feature('MESSAGE_ACTIONS')
    ? [
        {
          context: 'MessageActions' as const,
          bindings: {
            up: 'messageActions:prev' as const,
            down: 'messageActions:next' as const,
            k: 'messageActions:prev' as const,
            j: 'messageActions:next' as const,
            // meta = cmd on macOS; super for kitty keyboard-protocol — bind both.
            'meta+up': 'messageActions:top' as const,
            'meta+down': 'messageActions:bottom' as const,
            'super+up': 'messageActions:top' as const,
            'super+down': 'messageActions:bottom' as const,
            // Mouse selection extends on shift+arrow (ScrollKeybindingHandler:573) when present —
            // correct layered UX: esc clears selection, then shift+↑ jumps.
            'shift+up': 'messageActions:prevUser' as const,
            'shift+down': 'messageActions:nextUser' as const,
            escape: 'messageActions:escape' as const,
            'ctrl+c': 'messageActions:ctrlc' as const,
            // Mirror MESSAGE_ACTIONS. Not imported — would pull React/ink into this config module.
            enter: 'messageActions:enter' as const,
            c: 'messageActions:c' as const,
            p: 'messageActions:p' as const,
          },
        },
      ]
    : []),
  // ─── DiffDialog Context ────────────────────────────────────────────────
  // Active when the diff viewer dialog is open. Escape dismisses, left/right
  // cycle between sources (original vs modified), up/down navigate files,
  // and Enter opens a detailed view. (diff:back is handled by left arrow
  // contextually when in detail mode.)
  {
    context: 'DiffDialog',
    bindings: {
      escape: 'diff:dismiss',
      left: 'diff:previousSource',
      right: 'diff:nextSource',
      up: 'diff:previousFile',
      down: 'diff:nextFile',
      enter: 'diff:viewDetails',
      // Note: diff:back is handled by left arrow in detail mode
    },
  },
  // ─── ModelPicker Context ───────────────────────────────────────────────
  // Active when the model picker dialog is open (Anthropic-only feature).
  // Left/right arrows adjust the reasoning effort level.
  {
    context: 'ModelPicker',
    bindings: {
      left: 'modelPicker:decreaseEffort',
      right: 'modelPicker:increaseEffort',
    },
  },
  // ─── Select Context ────────────────────────────────────────────────────
  // Generic list/select component navigation. Used by /model, /resume,
  // permission prompts, and other dialogs that present a scrollable list.
  // Supports vim-style (j/k), Emacs-style (ctrl+n/p), and arrow navigation.
  {
    context: 'Select',
    bindings: {
      up: 'select:previous',
      down: 'select:next',
      j: 'select:next',
      k: 'select:previous',
      'ctrl+n': 'select:next',
      'ctrl+p': 'select:previous',
      enter: 'select:accept',
      escape: 'select:cancel',
    },
  },
  // ─── Plugin Context ────────────────────────────────────────────────────
  // Active when the plugin management dialog is open. Space toggles a
  // plugin on/off, 'i' installs the selected plugin. List navigation
  // (up/down/enter/escape) is handled by the Select context above.
  {
    context: 'Plugin',
    bindings: {
      space: 'plugin:toggle',
      i: 'plugin:install',
    },
  },
]

