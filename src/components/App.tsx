// =============================================================================
// App.tsx — Root Application Component
// =============================================================================
// This is the top-level React component for interactive Claude Code sessions.
// It establishes the React context provider hierarchy that all child components
// depend on. The nesting order matters — inner providers can access outer ones.
//
// Provider Hierarchy (outermost → innermost):
//   1. FpsMetricsProvider — exposes rendering FPS metrics for performance monitoring
//   2. StatsProvider — provides a stats store for tracking operational statistics
//   3. AppStateProvider — the main application state store (messages, tools,
//      permissions, MCP connections, etc.) with change notification callbacks
//
// The component uses the React Compiler's memoization cache (_c) to avoid
// unnecessary re-renders. Each provider layer is independently memoized:
// only the innermost changed provider and its children re-render.
//
// Note: This is the user-facing App component. There is a separate internal
// Ink App component at src/ink/components/App.js that wraps the React tree
// with Ink-specific providers (stdin, theme, focus).
// =============================================================================
import { c as _c } from "react/compiler-runtime";
import React from 'react';
// FpsMetricsProvider: makes FPS tracking data available to child components
// (used by the DevBar and /doctor diagnostics)
import { FpsMetricsProvider } from '../context/fpsMetrics.js';
// StatsProvider: provides a lightweight stats store for operational metrics
// (e.g., messages sent, tools executed, commands run)
import { StatsProvider, type StatsStore } from '../context/stats.js';
// AppStateProvider: the central state management provider — manages all
// application state including messages, tool permissions, MCP connections,
// agent definitions, plugins, and UI flags. Uses a Zustand-like store pattern.
// onChangeAppState: callback fired on every state change for side effects
// (e.g., persisting state, triggering re-renders in non-React consumers)
import { type AppState, AppStateProvider } from '../state/AppState.js';
import { onChangeAppState } from '../state/onChangeAppState.js';
import type { FpsMetrics } from '../utils/fpsTracker.js';

// Props for the root App component
type Props = {
  // Function that returns the current FPS metrics snapshot (or undefined if not yet available)
  getFpsMetrics: () => FpsMetrics | undefined;
  // Optional stats store instance — if omitted, a default is created
  stats?: StatsStore;
  // The initial application state — typically constructed during bootstrap
  initialState: AppState;
  // The child React tree to render inside the provider hierarchy
  // (usually the REPL screen component or a command-specific screen)
  children: React.ReactNode;
};

/**
 * Top-level wrapper for interactive sessions.
 * Provides FPS metrics, stats context, and app state to the component tree.
 */
export function App(t0) {
  // React Compiler memo cache — 9 slots for memoizing provider subtrees
  const $ = _c(9);
  // Destructure props from the compiler-transformed parameter
  const {
    getFpsMetrics,
    stats,
    initialState,
    children
  } = t0;
  // Memoized innermost layer: AppStateProvider wraps children
  // Only re-creates when children or initialState changes
  let t1;
  if ($[0] !== children || $[1] !== initialState) {
    t1 = <AppStateProvider initialState={initialState} onChangeAppState={onChangeAppState}>{children}</AppStateProvider>;
    $[0] = children;
    $[1] = initialState;
    $[2] = t1;
  } else {
    t1 = $[2];
  }
  // Memoized middle layer: StatsProvider wraps the AppStateProvider subtree
  // Only re-creates when stats store or inner subtree changes
  let t2;
  if ($[3] !== stats || $[4] !== t1) {
    t2 = <StatsProvider store={stats}>{t1}</StatsProvider>;
    $[3] = stats;
    $[4] = t1;
    $[5] = t2;
  } else {
    t2 = $[5];
  }
  // Memoized outermost layer: FpsMetricsProvider wraps everything
  // Only re-creates when getFpsMetrics function or inner subtree changes
  let t3;
  if ($[6] !== getFpsMetrics || $[7] !== t2) {
    t3 = <FpsMetricsProvider getFpsMetrics={getFpsMetrics}>{t2}</FpsMetricsProvider>;
    $[6] = getFpsMetrics;
    $[7] = t2;
    $[8] = t3;
  } else {
    t3 = $[8];
  }
  return t3;
}
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJuYW1lcyI6WyJSZWFjdCIsIkZwc01ldHJpY3NQcm92aWRlciIsIlN0YXRzUHJvdmlkZXIiLCJTdGF0c1N0b3JlIiwiQXBwU3RhdGUiLCJBcHBTdGF0ZVByb3ZpZGVyIiwib25DaGFuZ2VBcHBTdGF0ZSIsIkZwc01ldHJpY3MiLCJQcm9wcyIsImdldEZwc01ldHJpY3MiLCJzdGF0cyIsImluaXRpYWxTdGF0ZSIsImNoaWxkcmVuIiwiUmVhY3ROb2RlIiwiQXBwIiwidDAiLCIkIiwiX2MiLCJ0MSIsInQyIiwidDMiXSwic291cmNlcyI6WyJBcHAudHN4Il0sInNvdXJjZXNDb250ZW50IjpbImltcG9ydCBSZWFjdCBmcm9tICdyZWFjdCdcbmltcG9ydCB7IEZwc01ldHJpY3NQcm92aWRlciB9IGZyb20gJy4uL2NvbnRleHQvZnBzTWV0cmljcy5qcydcbmltcG9ydCB7IFN0YXRzUHJvdmlkZXIsIHR5cGUgU3RhdHNTdG9yZSB9IGZyb20gJy4uL2NvbnRleHQvc3RhdHMuanMnXG5pbXBvcnQgeyB0eXBlIEFwcFN0YXRlLCBBcHBTdGF0ZVByb3ZpZGVyIH0gZnJvbSAnLi4vc3RhdGUvQXBwU3RhdGUuanMnXG5pbXBvcnQgeyBvbkNoYW5nZUFwcFN0YXRlIH0gZnJvbSAnLi4vc3RhdGUvb25DaGFuZ2VBcHBTdGF0ZS5qcydcbmltcG9ydCB0eXBlIHsgRnBzTWV0cmljcyB9IGZyb20gJy4uL3V0aWxzL2Zwc1RyYWNrZXIuanMnXG5cbnR5cGUgUHJvcHMgPSB7XG4gIGdldEZwc01ldHJpY3M6ICgpID0+IEZwc01ldHJpY3MgfCB1bmRlZmluZWRcbiAgc3RhdHM/OiBTdGF0c1N0b3JlXG4gIGluaXRpYWxTdGF0ZTogQXBwU3RhdGVcbiAgY2hpbGRyZW46IFJlYWN0LlJlYWN0Tm9kZVxufVxuXG4vKipcbiAqIFRvcC1sZXZlbCB3cmFwcGVyIGZvciBpbnRlcmFjdGl2ZSBzZXNzaW9ucy5cbiAqIFByb3ZpZGVzIEZQUyBtZXRyaWNzLCBzdGF0cyBjb250ZXh0LCBhbmQgYXBwIHN0YXRlIHRvIHRoZSBjb21wb25lbnQgdHJlZS5cbiAqL1xuZXhwb3J0IGZ1bmN0aW9uIEFwcCh7XG4gIGdldEZwc01ldHJpY3MsXG4gIHN0YXRzLFxuICBpbml0aWFsU3RhdGUsXG4gIGNoaWxkcmVuLFxufTogUHJvcHMpOiBSZWFjdC5SZWFjdE5vZGUge1xuICByZXR1cm4gKFxuICAgIDxGcHNNZXRyaWNzUHJvdmlkZXIgZ2V0RnBzTWV0cmljcz17Z2V0RnBzTWV0cmljc30+XG4gICAgICA8U3RhdHNQcm92aWRlciBzdG9yZT17c3RhdHN9PlxuICAgICAgICA8QXBwU3RhdGVQcm92aWRlclxuICAgICAgICAgIGluaXRpYWxTdGF0ZT17aW5pdGlhbFN0YXRlfVxuICAgICAgICAgIG9uQ2hhbmdlQXBwU3RhdGU9e29uQ2hhbmdlQXBwU3RhdGV9XG4gICAgICAgID5cbiAgICAgICAgICB7Y2hpbGRyZW59XG4gICAgICAgIDwvQXBwU3RhdGVQcm92aWRlcj5cbiAgICAgIDwvU3RhdHNQcm92aWRlcj5cbiAgICA8L0Zwc01ldHJpY3NQcm92aWRlcj5cbiAgKVxufVxuIl0sIm1hcHBpbmdzIjoiO0FBQUEsT0FBT0EsS0FBSyxNQUFNLE9BQU87QUFDekIsU0FBU0Msa0JBQWtCLFFBQVEsMEJBQTBCO0FBQzdELFNBQVNDLGFBQWEsRUFBRSxLQUFLQyxVQUFVLFFBQVEscUJBQXFCO0FBQ3BFLFNBQVMsS0FBS0MsUUFBUSxFQUFFQyxnQkFBZ0IsUUFBUSxzQkFBc0I7QUFDdEUsU0FBU0MsZ0JBQWdCLFFBQVEsOEJBQThCO0FBQy9ELGNBQWNDLFVBQVUsUUFBUSx3QkFBd0I7QUFFeEQsS0FBS0MsS0FBSyxHQUFHO0VBQ1hDLGFBQWEsRUFBRSxHQUFHLEdBQUdGLFVBQVUsR0FBRyxTQUFTO0VBQzNDRyxLQUFLLENBQUMsRUFBRVAsVUFBVTtFQUNsQlEsWUFBWSxFQUFFUCxRQUFRO0VBQ3RCUSxRQUFRLEVBQUVaLEtBQUssQ0FBQ2EsU0FBUztBQUMzQixDQUFDOztBQUVEO0FBQ0E7QUFDQTtBQUNBO0FBQ0EsT0FBTyxTQUFBQyxJQUFBQyxFQUFBO0VBQUEsTUFBQUMsQ0FBQSxHQUFBQyxFQUFBO0VBQWE7SUFBQVIsYUFBQTtJQUFBQyxLQUFBO0lBQUFDLFlBQUE7SUFBQUM7RUFBQSxJQUFBRyxFQUtaO0VBQUEsSUFBQUcsRUFBQTtFQUFBLElBQUFGLENBQUEsUUFBQUosUUFBQSxJQUFBSSxDQUFBLFFBQUFMLFlBQUE7SUFJQU8sRUFBQSxJQUFDLGdCQUFnQixDQUNEUCxZQUFZLENBQVpBLGFBQVcsQ0FBQyxDQUNSTCxnQkFBZ0IsQ0FBaEJBLGlCQUFlLENBQUMsQ0FFakNNLFNBQU8sQ0FDVixFQUxDLGdCQUFnQixDQUtFO0lBQUFJLENBQUEsTUFBQUosUUFBQTtJQUFBSSxDQUFBLE1BQUFMLFlBQUE7SUFBQUssQ0FBQSxNQUFBRSxFQUFBO0VBQUE7SUFBQUEsRUFBQSxHQUFBRixDQUFBO0VBQUE7RUFBQSxJQUFBRyxFQUFBO0VBQUEsSUFBQUgsQ0FBQSxRQUFBTixLQUFBLElBQUFNLENBQUEsUUFBQUUsRUFBQTtJQU5yQkMsRUFBQSxJQUFDLGFBQWEsQ0FBUVQsS0FBSyxDQUFMQSxNQUFJLENBQUMsQ0FDekIsQ0FBQVEsRUFLa0IsQ0FDcEIsRUFQQyxhQUFhLENBT0U7SUFBQUYsQ0FBQSxNQUFBTixLQUFBO0lBQUFNLENBQUEsTUFBQUUsRUFBQTtJQUFBRixDQUFBLE1BQUFHLEVBQUE7RUFBQTtJQUFBQSxFQUFBLEdBQUFILENBQUE7RUFBQTtFQUFBLElBQUFJLEVBQUE7RUFBQSxJQUFBSixDQUFBLFFBQUFQLGFBQUEsSUFBQU8sQ0FBQSxRQUFBRyxFQUFBO0lBUmxCQyxFQUFBLElBQUMsa0JBQWtCLENBQWdCWCxhQUFhLENBQWJBLGNBQVksQ0FBQyxDQUM5QyxDQUFBVSxFQU9lLENBQ2pCLEVBVEMsa0JBQWtCLENBU0U7SUFBQUgsQ0FBQSxNQUFBUCxhQUFBO0lBQUFPLENBQUEsTUFBQUcsRUFBQTtJQUFBSCxDQUFBLE1BQUFJLEVBQUE7RUFBQTtJQUFBQSxFQUFBLEdBQUFKLENBQUE7RUFBQTtFQUFBLE9BVHJCSSxFQVNxQjtBQUFBIiwiaWdub3JlTGlzdCI6W119

