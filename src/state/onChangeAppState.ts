// =============================================================================
// onChangeAppState.ts — Side-effect handlers triggered on every state change
// =============================================================================
//
// This module implements the `onChange` callback wired into the store via
// `createStore(initialState, onChangeAppState)` in AppStateProvider. It is
// called synchronously by Store.setState *before* React subscriber
// notifications, which means:
//   1. External systems (CCR, disk config, SDK status) are updated before
//      any React component re-renders.
//   2. The function must be fast — it runs on every single setState call.
//
// The handler compares oldState vs newState for specific fields and
// triggers side-effects only when those fields actually changed. This
// is a centralized "diff & react" approach that replaces scattered
// manual notification calls throughout the codebase.
//
// Side-effects handled here:
//   • Permission mode → CCR external_metadata + SDK status stream
//   • mainLoopModel → settings file + bootstrap override
//   • expandedView → globalConfig persistence (showExpandedTodos / showSpinnerTree)
//   • verbose → globalConfig persistence
//   • tungstenPanelVisible → globalConfig persistence (ant-only)
//   • settings → clear auth caches + re-apply environment variables
// =============================================================================

import { setMainLoopModelOverride } from '../bootstrap/state.js'
import {
  clearApiKeyHelperCache,
  clearAwsCredentialsCache,
  clearGcpCredentialsCache,
} from '../utils/auth.js'
import { getGlobalConfig, saveGlobalConfig } from '../utils/config.js'
import { toError } from '../utils/errors.js'
import { logError } from '../utils/log.js'
import { applyConfigEnvironmentVariables } from '../utils/managedEnv.js'
import {
  permissionModeFromString,
  toExternalPermissionMode,
} from '../utils/permissions/PermissionMode.js'
import {
  notifyPermissionModeChanged,
  notifySessionMetadataChanged,
  type SessionExternalMetadata,
} from '../utils/sessionState.js'
import { updateSettingsForSource } from '../utils/settings/settings.js'
import type { AppState } from './AppStateStore.js'

// ---------------------------------------------------------------------------
// externalMetadataToAppState — Converts CCR external metadata back into an
// AppState updater function.
//
// This is the inverse of the metadata push in onChangeAppState: when a
// worker process restarts, it reads the latest external_metadata from CCR
// and uses this function to restore the AppState fields (permission_mode,
// isUltraplanMode) that were previously pushed out.
//
// Returns a state updater function compatible with store.setState().
// ---------------------------------------------------------------------------
// Inverse of the push below — restore on worker restart.
export function externalMetadataToAppState(
  metadata: SessionExternalMetadata,
): (prev: AppState) => AppState {
  return prev => ({
    ...prev,
    ...(typeof metadata.permission_mode === 'string'
      ? {
          toolPermissionContext: {
            ...prev.toolPermissionContext,
            mode: permissionModeFromString(metadata.permission_mode),
          },
        }
      : {}),
    ...(typeof metadata.is_ultraplan_mode === 'boolean'
      ? { isUltraplanMode: metadata.is_ultraplan_mode }
      : {}),
  })
}

// ---------------------------------------------------------------------------
// onChangeAppState — The main side-effect handler for state transitions.
//
// Wired as the `onChange` callback to createStore() in AppStateProvider.
// Called synchronously on every setState that produces a new state reference
// (i.e., Object.is(new, old) === false). Runs BEFORE React subscribers.
//
// Each block below handles one state field diff. The pattern is:
//   if (newState.X !== oldState.X) { /* side-effect */ }
//
// This ensures side-effects only fire when the relevant field actually changed,
// keeping the function efficient even though it runs on every state update.
// ---------------------------------------------------------------------------
export function onChangeAppState({
  newState,
  oldState,
}: {
  newState: AppState
  oldState: AppState
}) {
  // =========================================================================
  // 1. Permission mode sync → CCR + SDK
  // =========================================================================
  // toolPermissionContext.mode — single choke point for CCR/SDK mode sync.
  //
  // Prior to this block, mode changes were relayed to CCR by only 2 of 8+
  // mutation paths: a bespoke setAppState wrapper in print.ts (headless/SDK
  // mode only) and a manual notify in the set_permission_mode handler.
  // Every other path — Shift+Tab cycling, ExitPlanModePermissionRequest
  // dialog options, the /plan slash command, rewind, the REPL bridge's
  // onSetPermissionMode — mutated AppState without telling
  // CCR, leaving external_metadata.permission_mode stale and the web UI out
  // of sync with the CLI's actual mode.
  //
  // Hooking the diff here means ANY setAppState call that changes the mode
  // notifies CCR (via notifySessionMetadataChanged → ccrClient.reportMetadata)
  // and the SDK status stream (via notifyPermissionModeChanged → registered
  // in print.ts). The scattered callsites above need zero changes.
  const prevMode = oldState.toolPermissionContext.mode
  const newMode = newState.toolPermissionContext.mode
  if (prevMode !== newMode) {
    // CCR external_metadata must not receive internal-only mode names
    // (bubble, ungated auto). Externalize first — and skip
    // the CCR notify if the EXTERNAL mode didn't change (e.g.,
    // default→bubble→default is noise from CCR's POV since both
    // externalize to 'default'). The SDK channel (notifyPermissionModeChanged)
    // passes raw mode; its listener in print.ts applies its own filter.
    const prevExternal = toExternalPermissionMode(prevMode)
    const newExternal = toExternalPermissionMode(newMode)
    if (prevExternal !== newExternal) {
      // Ultraplan = first plan cycle only. The initial control_request
      // sets mode and isUltraplanMode atomically, so the flag's
      // transition gates it. null per RFC 7396 (removes the key).
      const isUltraplan =
        newExternal === 'plan' &&
        newState.isUltraplanMode &&
        !oldState.isUltraplanMode
          ? true
          : null
      notifySessionMetadataChanged({
        permission_mode: newExternal,
        is_ultraplan_mode: isUltraplan,
      })
    }
    notifyPermissionModeChanged(newMode)
  }

  // =========================================================================
  // 2. Model override → settings file + bootstrap state
  // =========================================================================

  // mainLoopModel: remove it from settings?
  // When the user clears the model override (sets to null), remove it from
  // the persisted user settings and clear the bootstrap override so the
  // server-assigned default model is used for subsequent requests.
  if (
    newState.mainLoopModel !== oldState.mainLoopModel &&
    newState.mainLoopModel === null
  ) {
    // Remove from settings
    updateSettingsForSource('userSettings', { model: undefined })
    setMainLoopModelOverride(null)
  }

  // mainLoopModel: add it to settings?
  // When the user sets a model override (via /model command, --model flag, etc.),
  // persist it to user settings and update the bootstrap override so the next
  // API request uses this model.
  if (
    newState.mainLoopModel !== oldState.mainLoopModel &&
    newState.mainLoopModel !== null
  ) {
    // Save to settings
    updateSettingsForSource('userSettings', { model: newState.mainLoopModel })
    setMainLoopModelOverride(newState.mainLoopModel)
  }

  // =========================================================================
  // 3. Expanded view → globalConfig persistence
  // =========================================================================
  // expandedView → persist as showExpandedTodos + showSpinnerTree for backwards compat
  // Maps the new unified expandedView enum to two legacy boolean config keys
  // so that the user's panel visibility preference survives across sessions.
  if (newState.expandedView !== oldState.expandedView) {
    const showExpandedTodos = newState.expandedView === 'tasks'
    const showSpinnerTree = newState.expandedView === 'teammates'
    if (
      getGlobalConfig().showExpandedTodos !== showExpandedTodos ||
      getGlobalConfig().showSpinnerTree !== showSpinnerTree
    ) {
      saveGlobalConfig(current => ({
        ...current,
        showExpandedTodos,
        showSpinnerTree,
      }))
    }
  }

  // =========================================================================
  // 4. Verbose mode → globalConfig persistence
  // =========================================================================
  // verbose
  // Persist verbose toggle to globalConfig so it survives across sessions.
  // Only writes if the config value is actually different (avoids unnecessary I/O).
  if (
    newState.verbose !== oldState.verbose &&
    getGlobalConfig().verbose !== newState.verbose
  ) {
    const verbose = newState.verbose
    saveGlobalConfig(current => ({
      ...current,
      verbose,
    }))
  }

  // =========================================================================
  // 5. Tungsten panel visibility → globalConfig persistence (ant-only)
  // =========================================================================
  // tungstenPanelVisible (ant-only tmux panel sticky toggle)
  // Only persisted for internal (ant) users. The panel visibility preference
  // is saved so the tmux panel opens/closes consistently across sessions.
  if (process.env.USER_TYPE === 'ant') {
    if (
      newState.tungstenPanelVisible !== oldState.tungstenPanelVisible &&
      newState.tungstenPanelVisible !== undefined &&
      getGlobalConfig().tungstenPanelVisible !== newState.tungstenPanelVisible
    ) {
      const tungstenPanelVisible = newState.tungstenPanelVisible
      saveGlobalConfig(current => ({ ...current, tungstenPanelVisible }))
    }
  }

  // =========================================================================
  // 6. Settings change → clear auth caches + re-apply env vars
  // =========================================================================
  // settings: clear auth-related caches when settings change
  // This ensures apiKeyHelper and AWS/GCP credential changes take effect immediately
  // When the settings object reference changes, it means the user (or a watcher)
  // modified settings. We must:
  //   a. Clear cached API key / AWS / GCP credentials so the next API call
  //      picks up the new values.
  //   b. If settings.env changed, re-apply environment variables to process.env.
  //      This is additive-only: new vars added, existing overwritten, none deleted.
  if (newState.settings !== oldState.settings) {
    try {
      clearApiKeyHelperCache()
      clearAwsCredentialsCache()
      clearGcpCredentialsCache()

      // Re-apply environment variables when settings.env changes
      // This is additive-only: new vars are added, existing may be overwritten, nothing is deleted
      if (newState.settings.env !== oldState.settings.env) {
        applyConfigEnvironmentVariables()
      }
    } catch (error) {
      logError(toError(error))
    }
  }
}

