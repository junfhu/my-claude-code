// =============================================================================
// src/shims/preload.ts — Bootstrap shim loaded before any application code
// =============================================================================
//
// This file must be imported/evaluated BEFORE any Claude Code application code
// runs. It sets up the runtime environment that the codebase expects:
//
// 1. MACRO global (via macro.ts):
//    Installs globalThis.MACRO with VERSION, PACKAGE_URL, and ISSUES_EXPLAINER.
//    Required because the codebase uses bare `MACRO.VERSION` references
//    everywhere — in production Bun builds, these are inlined at compile time,
//    but in dev mode we need the global to exist at runtime.
//
// 2. bun:bundle (NOT imported here):
//    The `feature()` function from `bun:bundle` is resolved via the build
//    script's alias configuration, not through this preload. Each source file
//    imports it directly: `import { feature } from 'bun:bundle'`
//
// Loading order:
//   preload.ts → macro.ts → (globalThis.MACRO is now available)
//                         → application code starts importing
//
// =============================================================================

import './macro.js'
// bun:bundle is resolved via the build alias, not imported here
