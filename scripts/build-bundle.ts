// =============================================================================
// scripts/build-bundle.ts — esbuild-based bundler for Claude Code CLI
// =============================================================================
//
// This script bundles the entire Claude Code TypeScript codebase into a single
// self-contained ESM file (dist/cli.mjs) that can run on Node.js >= 20.
//
// Architecture:
//   src/entrypoints/cli.tsx  →  esbuild  →  dist/cli.mjs (~20 MB)
//
// The original codebase was built with Bun's native bundler, which provides:
//   - Compile-time feature flags via `bun:bundle` (dead-code elimination)
//   - Compile-time MACRO.* constant injection
//   - Native JSX/TSX support
//   - Bare `src/` import resolution via tsconfig baseUrl
//
// Since we're using esbuild instead, this script provides equivalent
// functionality through a combination of:
//   1. Custom esbuild plugins (src resolution, text loading, .d.ts handling)
//   2. Build-time `define` replacements (MACRO.*, process.env.USER_TYPE)
//   3. Module aliasing (`bun:bundle` → runtime shim)
//   4. CJS compatibility banner (for bundled packages that use require())
//
// Usage:
//   bun scripts/build-bundle.ts              # Development build
//   bun scripts/build-bundle.ts --watch      # Watch mode (auto-rebuild)
//   bun scripts/build-bundle.ts --minify     # Production build (minified)
//   bun scripts/build-bundle.ts --no-sourcemap  # Skip source maps
//
// =============================================================================

import * as esbuild from 'esbuild'
import { resolve, dirname } from 'path'
import { chmodSync, readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'

// ---------------------------------------------------------------------------
// Determine the directory containing this script.
// Three approaches tried in order:
//   1. import.meta.dir   — Bun-specific (available when run with `bun`)
//   2. import.meta.dirname — Node.js 21+ ESM feature
//   3. Manual derivation from import.meta.url — universal fallback
// ---------------------------------------------------------------------------
const __dir: string =
  (import.meta as any).dir ??
  (import.meta as any).dirname ??
  dirname(fileURLToPath(import.meta.url))

// Project root is one level up from scripts/
const ROOT = resolve(__dir, '..')

// Parse CLI flags
const watch = process.argv.includes('--watch')
const minify = process.argv.includes('--minify')
const noSourcemap = process.argv.includes('--no-sourcemap')

// Read version from package.json — injected as MACRO.VERSION at build time.
// In production Bun builds, MACRO.* are compile-time constants inlined by Bun's
// bundler. Here we replicate that via esbuild's `define` option.
const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf-8'))
const version = pkg.version || '0.0.0-dev'

// =============================================================================
// PLUGIN 1: Bare `src/` import resolver
// =============================================================================
//
// The codebase uses TypeScript's `baseUrl: "."` setting, which allows imports
// like `import { foo } from 'src/utils/bar.js'` without a leading `./`.
// esbuild doesn't natively understand this — it treats bare `src/` as a
// node_modules package.
//
// This plugin intercepts any import starting with `src/` and resolves it
// to the actual file on disk, handling three cases:
//   1. The exact path exists (e.g., src/utils/bar.js is a real .js file)
//   2. The .js extension maps to a .ts/.tsx file (TypeScript convention)
//   3. The path is a directory with an index.ts/index.tsx file
//
// Without this plugin, esbuild would fail on ~80% of the imports in the
// codebase since almost every file uses this bare `src/` import style.
// =============================================================================
const srcResolverPlugin: esbuild.Plugin = {
  name: 'src-resolver',
  setup(build) {
    // Intercept all imports that start with 'src/' (bare path, no ./ prefix)
    build.onResolve({ filter: /^src\// }, (args) => {
      // Resolve relative to project root (where tsconfig's baseUrl points)
      const basePath = resolve(ROOT, args.path)

      // Case 1: Exact path exists (rare — most .js files are actually .ts)
      if (existsSync(basePath)) {
        return { path: basePath }
      }

      // Case 2: Strip .js/.jsx extension and try TypeScript equivalents.
      // The codebase writes `import from 'src/foo/bar.js'` but the actual
      // file is `src/foo/bar.ts` — this is standard TypeScript convention
      // where .js in imports refers to the compiled output, not the source.
      const withoutExt = basePath.replace(/\.(js|jsx)$/, '')
      for (const ext of ['.ts', '.tsx', '.js', '.jsx']) {
        const candidate = withoutExt + ext
        if (existsSync(candidate)) {
          return { path: candidate }
        }
      }

      // Case 3: The import path is a directory — resolve to index file.
      // e.g., `import from 'src/services/mcp.js'` might mean
      //        `src/services/mcp/index.ts`
      const dirPath = basePath.replace(/\.(js|jsx)$/, '')
      for (const ext of ['.ts', '.tsx', '.js', '.jsx']) {
        const candidate = resolve(dirPath, 'index' + ext)
        if (existsSync(candidate)) {
          return { path: candidate }
        }
      }

      // Let esbuild handle it — will produce a clear error if truly missing
      return undefined
    })
  },
}

// =============================================================================
// PLUGIN 2: Text file loader for .md and .txt imports
// =============================================================================
//
// The codebase imports markdown and text files directly:
//   import promptText from './prompt.md'
//   import systemPrompt from '../prompts/auto_mode_system_prompt.txt'
//
// In Bun, these are handled natively. For esbuild, we need to read the file
// contents and wrap them as a JavaScript module with a default string export.
//
// This is used for:
//   - Skill SKILL.md descriptions
//   - System prompt templates
//   - Permission classifier prompts
//   - Documentation snippets bundled into the CLI
// =============================================================================
const textLoaderPlugin: esbuild.Plugin = {
  name: 'text-loader',
  setup(build) {
    build.onLoad({ filter: /\.(md|txt)$/ }, async (args) => {
      const { readFileSync } = await import('fs')
      const contents = readFileSync(args.path, 'utf-8')
      // Wrap as ES module: `export default "file contents..."`
      // JSON.stringify handles escaping of quotes, newlines, etc.
      return {
        contents: `export default ${JSON.stringify(contents)}`,
        loader: 'js',
      }
    })
  },
}

// =============================================================================
// PLUGIN 3: TypeScript declaration file (.d.ts) resolver
// =============================================================================
//
// Some source files import TypeScript declaration files directly:
//   import '../global.d.ts'
//
// These imports exist for side-effects (declaring global types) and have no
// runtime code. esbuild would choke on them since .d.ts files contain only
// type declarations.
//
// This plugin:
//   1. Redirects all .d.ts imports to src/global.d.ts (a known safe target)
//   2. Returns an empty module for that file (no runtime code needed)
//   3. Marks it as side-effect-free so tree-shaking can remove it
// =============================================================================
const dtsResolverPlugin: esbuild.Plugin = {
  name: 'dts-resolver',
  setup(build) {
    // Intercept any import ending in .d.ts
    build.onResolve({ filter: /\.d\.ts$/ }, () => ({
      path: resolve(ROOT, 'src/global.d.ts'),
      sideEffects: false,  // Safe to tree-shake away entirely
    }))
    // When esbuild tries to load global.d.ts, return empty module
    build.onLoad({ filter: /global\.d\.ts$/ }, () => ({
      contents: '',   // No runtime code — all types are erased
      loader: 'js',
    }))
  },
}

// =============================================================================
// PLUGIN 4: Stub subpath resolver for @ant/* packages
// =============================================================================
//
// The codebase imports from Anthropic-internal packages with deep subpaths:
//   import { SomeType } from '@ant/sandbox-runtime/types'
//   import { config } from '@ant/observability/config'
//
// These packages don't exist in our node_modules — we've created CJS proxy
// stubs at node_modules/@ant/<pkg>/index.js that return a Proxy object
// for any property access (allowing any named import to resolve).
//
// However, esbuild doesn't know that '@ant/sandbox-runtime/types' should
// resolve to '@ant/sandbox-runtime/index.js'. This plugin strips the
// subpath and redirects to the package root's index.js stub.
//
// Example: '@ant/foo/bar/baz' → node_modules/@ant/foo/index.js
// =============================================================================
const stubSubpathPlugin: esbuild.Plugin = {
  name: 'stub-subpath',
  setup(build) {
    // Match @ant/<pkg>/<anything> — i.e., any subpath beyond the package name
    build.onResolve({ filter: /^@ant\/[^/]+\/.+/ }, (args) => {
      // Extract the base package: '@ant/foo/bar/baz' → '@ant/foo'
      const base = args.path.split('/').slice(0, 2).join('/')
      const stubIndex = resolve(ROOT, 'node_modules', base, 'index.js')
      if (existsSync(stubIndex)) {
        return { path: stubIndex }
      }
      // No stub found — let esbuild handle (will likely error)
      return undefined
    })
  },
}

// =============================================================================
// ESBUILD CONFIGURATION
// =============================================================================
//
// Key design decisions:
//
// 1. Single-file output (splitting: false)
//    CLI tools benefit from a single self-contained file for easy distribution.
//    No dynamic import() in the output — everything is statically bundled.
//
// 2. ESM format with .mjs extension
//    The codebase uses ES modules throughout. The .mjs extension ensures
//    Node.js treats it as ESM regardless of the nearest package.json type.
//
// 3. Node.js built-ins are externalized
//    fs, path, crypto, etc. are available at runtime — no need to bundle them.
//    node-pty is also external because it's a native C++ addon that must be
//    loaded dynamically at runtime via require().
//
// 4. JSX automatic runtime
//    React 17+ automatic JSX transform — no need to `import React` in every
//    file that uses JSX.
//
// 5. Tree shaking + define replacements
//    process.env.USER_TYPE = "external" eliminates Anthropic-internal code
//    branches at build time (they check for "ant" user type).
//
// =============================================================================
const buildOptions: esbuild.BuildOptions = {
  // ── Entry point ──
  // The CLI bootstrap file that handles fast-path dispatching and loads
  // the full CLI (main.tsx) only when needed.
  entryPoints: [resolve(ROOT, 'src/entrypoints/cli.tsx')],

  bundle: true,            // Bundle all dependencies into one file
  platform: 'node',        // Target Node.js (not browser)
  target: ['node20', 'es2022'],  // Minimum Node 20, ES2022 features
  format: 'esm',           // ES modules output
  outdir: resolve(ROOT, 'dist'),
  outExtension: { '.js': '.mjs' },  // Force .mjs for Node ESM compat

  // Single-file output — no code splitting for CLI tools.
  // This means dynamic import() expressions are inlined, not split into
  // separate chunks. Trade-off: larger file but simpler distribution.
  splitting: false,

  // Plugin execution order matters:
  //   1. stubSubpathPlugin — must run first to catch @ant/* subpath imports
  //   2. srcResolverPlugin — handles bare src/ imports
  //   3. textLoaderPlugin  — handles .md/.txt imports
  //   4. dtsResolverPlugin — handles .d.ts imports (must be last resolver)
  plugins: [stubSubpathPlugin, srcResolverPlugin, textLoaderPlugin, dtsResolverPlugin],

  // Use tsconfig for additional path resolution (complements srcResolverPlugin).
  // tsconfig.json defines baseUrl: "." which tells TypeScript that bare
  // imports resolve relative to the project root.
  tsconfig: resolve(ROOT, 'tsconfig.json'),

  // ── Module aliasing ──
  // Replace `import { feature } from 'bun:bundle'` with our runtime shim.
  // In production, Bun's bundler evaluates feature() at compile time for
  // dead-code elimination. Our shim reads env vars at runtime instead.
  alias: {
    'bun:bundle': resolve(ROOT, 'src/shims/bun-bundle.ts'),
  },

  // ── External modules ──
  // These are NOT bundled — they're resolved at runtime by Node.js.
  //
  // Node.js built-ins: Available in every Node.js installation.
  // node:* prefix: Node.js >= 16 prefixed built-in syntax.
  // node-pty: Native C++ addon — cannot be bundled, must be require()'d
  //           at runtime for the terminal PTY functionality.
  external: [
    // Core Node.js built-in modules
    'fs', 'path', 'os', 'crypto', 'child_process', 'http', 'https',
    'net', 'tls', 'url', 'util', 'stream', 'events', 'buffer',
    'querystring', 'readline', 'zlib', 'assert', 'tty', 'worker_threads',
    'perf_hooks', 'async_hooks', 'dns', 'dgram', 'cluster',
    'string_decoder', 'module', 'vm', 'constants', 'domain',
    'console', 'process', 'v8', 'inspector',
    // Prefixed built-ins (node:fs, node:path, etc.)
    'node:*',
    // Native addon — must stay external (loaded via require() at runtime)
    'node-pty',
  ],

  // React 17+ automatic JSX runtime — automatically imports jsx() from
  // 'react/jsx-runtime' instead of requiring `import React from 'react'`
  // in every TSX file.
  jsx: 'automatic',

  // Source maps: external .map files for production debugging.
  // The --no-sourcemap flag disables them for smaller output.
  sourcemap: noSourcemap ? false : 'external',

  // Minification for production builds (--minify flag).
  // Reduces bundle size by ~40% but makes debugging harder.
  minify,

  // Tree shaking removes unused exports and dead code.
  // Explicitly enabled for clarity — it's on by default for ESM.
  treeShaking: true,

  // ── Compile-time constant replacements ──
  //
  // These replace literal expressions in the source code with constant values
  // at build time, enabling dead-code elimination by the minifier.
  //
  // MACRO.VERSION — Replaced everywhere `MACRO.VERSION` appears in source.
  //   In production Bun builds, Bun's bundler inlines this at compile time.
  //   We replicate that behavior with esbuild's `define`.
  //
  // MACRO.PACKAGE_URL — The npm package identifier.
  //
  // MACRO.ISSUES_EXPLAINER — Shown in error messages.
  //
  // process.env.USER_TYPE — Critical for dead-code elimination.
  //   Setting this to "external" causes all `if (userType === 'ant')` branches
  //   to be eliminated at build time, removing Anthropic-internal features
  //   that we don't have access to (internal APIs, debugging tools, etc.).
  //
  // process.env.NODE_ENV — Standard Node.js environment flag.
  //   Libraries like React use this for development vs production behavior.
  //
  define: {
    'MACRO.VERSION': JSON.stringify(version),
    'MACRO.PACKAGE_URL': JSON.stringify('@anthropic-ai/claude-code'),
    'MACRO.ISSUES_EXPLAINER': JSON.stringify(
      'report issues at https://github.com/anthropics/claude-code/issues'
    ),
    'process.env.USER_TYPE': '"external"',
    'process.env.NODE_ENV': minify ? '"production"' : '"development"',
  },

  // ── Banner: shebang + CJS require() compatibility ──
  //
  // Line 1: #!/usr/bin/env node
  //   Makes the output file directly executable: `./dist/cli.mjs`
  //
  // Lines 2-3: CJS require() polyfill for ESM
  //   Problem: Some bundled CJS packages (e.g., node-fetch inside
  //   @anthropic-ai/sdk) use require() to load Node.js built-ins.
  //   ESM modules don't have require() — it's a CJS-only global.
  //
  //   Solution: Create a require() function using Node's createRequire()
  //   utility, scoped to the bundle's URL. This allows CJS code inside
  //   the ESM bundle to call require('fs'), require('path'), etc.
  //
  //   Note: We initially tried adding __dirname/__filename to the banner
  //   but esbuild declares those itself — adding them caused conflicts.
  //
  banner: {
    js: [
      '#!/usr/bin/env node',
      'import { createRequire as __cjsCreateRequire } from "module";',
      'const require = __cjsCreateRequire(import.meta.url);',
      '',
    ].join('\n'),
  },

  // ── Extension resolution order ──
  // When an import doesn't specify an extension, try these in order.
  // .tsx/.ts first because the codebase is TypeScript-first.
  resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],

  logLevel: 'info',

  // Generate metafile for bundle analysis (written to dist/meta.json).
  // Can be visualized at https://esbuild.github.io/analyze/
  metafile: true,
}

// =============================================================================
// BUILD EXECUTION
// =============================================================================

async function main() {
  if (watch) {
    // ── Watch mode ──
    // Creates a long-lived build context that watches for file changes
    // and automatically rebuilds. Useful during development.
    const ctx = await esbuild.context(buildOptions)
    await ctx.watch()
    console.log('Watching for changes...')
  } else {
    // ── One-shot build ──
    const startTime = Date.now()
    const result = await esbuild.build(buildOptions)

    // Fail fast on build errors
    if (result.errors.length > 0) {
      console.error('Build failed')
      process.exit(1)
    }

    // Make the output file executable (chmod 755) so it can be run
    // directly as `./dist/cli.mjs` thanks to the shebang in the banner.
    const outPath = resolve(ROOT, 'dist/cli.mjs')
    try {
      chmodSync(outPath, 0o755)
    } catch {
      // chmod may fail on Windows or restrictive filesystems — non-fatal
    }

    const elapsed = Date.now() - startTime

    // Print bundle size and timing information
    if (result.metafile) {
      const text = await esbuild.analyzeMetafile(result.metafile, { verbose: false })
      const outFiles = Object.entries(result.metafile.outputs)
      for (const [file, info] of outFiles) {
        if (file.endsWith('.mjs')) {
          const sizeMB = ((info as { bytes: number }).bytes / 1024 / 1024).toFixed(2)
          console.log(`\n  ${file}: ${sizeMB} MB`)
        }
      }
      console.log(`\nBuild complete in ${elapsed}ms → dist/`)

      // Write the metafile for offline bundle analysis.
      // Upload to https://esbuild.github.io/analyze/ to visualize
      // which modules contribute the most to bundle size.
      const { writeFileSync } = await import('fs')
      writeFileSync(
        resolve(ROOT, 'dist/meta.json'),
        JSON.stringify(result.metafile),
      )
      console.log('  Metafile written to dist/meta.json')
    }
  }
}

// Entry point — run build and exit with error code on failure
main().catch(err => {
  console.error(err)
  process.exit(1)
})
