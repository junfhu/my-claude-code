// =============================================================================
// store.ts — Minimal, framework-agnostic reactive store factory
// =============================================================================
//
// Implements a lightweight publish/subscribe (pub-sub) state container inspired
// by the "external store" pattern popularized by Zustand and Redux. The store
// is intentionally minimal so it can be consumed by both React (via
// `useSyncExternalStore`) and non-React code (Node scripts, CLI bootstrap)
// without pulling in any UI dependencies.
//
// Architecture overview:
//   createStore(initialState, onChange?)
//       ↓
//   Store<T> { getState, setState, subscribe }
//       │
//       ├── React layer (AppState.tsx)  ←  useSyncExternalStore(store.subscribe, …)
//       └── Side-effect layer (onChangeAppState.ts) ← onChange callback
//
// Thread-safety note:
//   JavaScript is single-threaded (event-loop model), so there are no data
//   races between getState / setState / subscriber notifications. However,
//   a subscriber callback *may* call setState, which would mutate `state`
//   synchronously before subsequent listeners in the current iteration see
//   the old value. The current design allows this (no batching / queueing),
//   which keeps the implementation simple at the cost of re-entrant caution.
// =============================================================================

// A Listener is a zero-argument callback invoked whenever the store state changes.
// Listeners are typically React's internal re-render triggers registered by
// `useSyncExternalStore`, but any function can subscribe.
type Listener = () => void

// OnChange is an optional callback provided at store creation time that
// receives both the previous and next state snapshots. It fires *before*
// subscriber notifications, making it the ideal place for side-effects that
// must run once per state transition (e.g., persisting settings to disk,
// notifying external systems). See onChangeAppState.ts for the concrete
// implementation wired into the application store.
type OnChange<T> = (args: { newState: T; oldState: T }) => void

// The public interface of a store instance. Generic over the state type <T>.
//
// - getState:  Synchronous snapshot read — always returns the latest state.
// - setState:  Accepts an *updater function* (prev => next) rather than a raw
//              value. This ensures callers always derive next state from the
//              current state, avoiding stale-closure bugs. If the updater
//              returns the same reference (Object.is equality), the update is
//              a no-op — no onChange, no subscriber notifications.
// - subscribe: Registers a listener and returns an unsubscribe function.
//              Follows the contract required by React's useSyncExternalStore.
export type Store<T> = {
  getState: () => T
  setState: (updater: (prev: T) => T) => void
  subscribe: (listener: Listener) => () => void
}

// Factory function that creates a new Store<T> instance.
//
// Parameters:
//   initialState — the starting state value; becomes the first getState() result.
//   onChange     — (optional) side-effect callback invoked on every *actual*
//                 state change (i.e., when Object.is(next, prev) is false).
//                 Fires synchronously before subscriber notification so that
//                 external persistence / sync can settle before React re-renders.
//
// Returns a Store<T> object whose methods close over `state` and `listeners`.
export function createStore<T>(
  initialState: T,
  onChange?: OnChange<T>,
): Store<T> {
  // Mutable state variable — this is the single source of truth.
  // Captured via closure; only mutated inside setState.
  let state = initialState

  // Subscriber registry. Using a Set ensures O(1) add/delete and guarantees
  // each listener is registered at most once (duplicate adds are idempotent).
  const listeners = new Set<Listener>()

  return {
    // Synchronous read — returns the current state reference.
    // Because state is replaced (not mutated in-place), callers always get
    // a consistent snapshot. React's useSyncExternalStore relies on this
    // returning a stable reference between renders when nothing has changed.
    getState: () => state,

    // Updater-based state transition. The update pipeline is:
    //   1. Compute next state via updater(prev)
    //   2. Bail out early if Object.is(next, prev) — referential equality
    //      check avoids unnecessary work (same pattern as React's useState)
    //   3. Swap the state reference
    //   4. Fire the onChange callback (side-effects: persistence, CCR sync, etc.)
    //   5. Notify all subscribers (React re-renders, UI updates)
    //
    // Steps 4 and 5 are synchronous and unguarded — if onChange or a listener
    // throws, subsequent listeners in the iteration will NOT be called.
    setState: (updater: (prev: T) => T) => {
      const prev = state
      const next = updater(prev)
      // Referential equality check — if the updater returned the exact same
      // object, treat as a no-op. This is critical for performance: React
      // components using useSyncExternalStore will not re-render.
      if (Object.is(next, prev)) return
      // Commit the new state before any callbacks so that getState() inside
      // onChange or subscriber callbacks reflects the updated value.
      state = next
      // Fire the onChange side-effect handler (if provided) with both snapshots.
      // This runs before subscribers so external systems (CCR, disk persistence)
      // are updated before React re-renders read the new state.
      onChange?.({ newState: next, oldState: prev })
      // Notify all registered subscribers. In the React integration, each
      // subscriber is a hook instance that will call getState() → selector()
      // to determine whether its component needs to re-render.
      for (const listener of listeners) listener()
    },

    // Register a listener for state changes. Returns an unsubscribe function
    // that removes the listener from the Set. This signature matches the
    // contract expected by React's `useSyncExternalStore(subscribe, getSnapshot)`.
    //
    // Usage:
    //   const unsub = store.subscribe(() => console.log(store.getState()))
    //   // later…
    //   unsub()  // stops listening
    subscribe: (listener: Listener) => {
      listeners.add(listener)
      // Return a cleanup function — calling it removes this specific listener.
      // React calls this automatically when the subscribing component unmounts.
      return () => listeners.delete(listener)
    },
  }
}
