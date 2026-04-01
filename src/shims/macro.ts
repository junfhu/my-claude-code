// =============================================================================
// src/shims/macro.ts — Runtime shim for Bun's compile-time MACRO constants
// =============================================================================
//
// In production Bun builds, the MACRO object is a set of compile-time constants
// injected by Bun's bundler. Throughout the codebase, you'll see:
//
//   MACRO.VERSION         → "1.0.42" (the package version)
//   MACRO.PACKAGE_URL     → "@anthropic-ai/claude-code" (npm package name)
//   MACRO.ISSUES_EXPLAINER → "report issues at https://..." (error message text)
//
// Bun replaces these at compile time — they become literal string constants in
// the output bundle, with no runtime lookup needed.
//
// For our esbuild-based build, there are TWO paths:
//
// 1. Built bundle (dist/cli.mjs):
//    The build script uses esbuild's `define` option to replace MACRO.* at
//    build time, identical to how Bun does it. This file is NOT used.
//
// 2. Dev mode (bun scripts/dev.ts):
//    When running source directly through Bun without building, there's no
//    `define` pass. This file provides the MACRO object at runtime by:
//    - Reading the version from package.json
//    - Installing a MACRO global on globalThis
//
// The preload.ts shim imports this file to ensure MACRO is available before
// any application code runs.
//
// =============================================================================

// Read version from package.json at startup
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// Derive __filename from import.meta.url (ESM doesn't provide __filename)
const __filename = fileURLToPath(import.meta.url)

// Navigate from src/shims/macro.ts → project root → package.json
const pkgPath = resolve(dirname(__filename), '..', '..', 'package.json')

// Default version if package.json can't be read (e.g., in a test environment)
let version = '0.0.0-dev'
try {
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
  version = pkg.version || version
} catch {
  // Silently fall back to default — this is non-fatal
}

// ---------------------------------------------------------------------------
// The MACRO object — mirrors what Bun's bundler provides at compile time.
//
// VERSION:           Package version string (e.g., "0.0.0-leaked")
// PACKAGE_URL:       npm package identifier for update checks and telemetry
// ISSUES_EXPLAINER:  Appended to error messages to help users report bugs
// ---------------------------------------------------------------------------
const MACRO_OBJ = {
  VERSION: version,
  PACKAGE_URL: '@anthropic-ai/claude-code',
  ISSUES_EXPLAINER:
    'report issues at https://github.com/anthropics/claude-code/issues',
}

// Install MACRO as a global so it's accessible everywhere without imports.
// The codebase uses bare `MACRO.VERSION` references (no import needed) because
// Bun's bundler inlines them at compile time. In dev mode, we need this global.
;(globalThis as any).MACRO = MACRO_OBJ

export default MACRO_OBJ
