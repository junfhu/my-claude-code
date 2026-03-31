// scripts/build-bundle.ts
// Usage: bun scripts/build-bundle.ts [--watch] [--minify] [--no-sourcemap]
//
// Production build: bun scripts/build-bundle.ts --minify
// Dev build:        bun scripts/build-bundle.ts
// Watch mode:       bun scripts/build-bundle.ts --watch

import * as esbuild from 'esbuild'
import { resolve, dirname } from 'path'
import { chmodSync, readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'

// Bun: import.meta.dir — Node 21+: import.meta.dirname — fallback
const __dir: string =
  (import.meta as any).dir ??
  (import.meta as any).dirname ??
  dirname(fileURLToPath(import.meta.url))

const ROOT = resolve(__dir, '..')
const watch = process.argv.includes('--watch')
const minify = process.argv.includes('--minify')
const noSourcemap = process.argv.includes('--no-sourcemap')

// Read version from package.json for MACRO injection
const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf-8'))
const version = pkg.version || '0.0.0-dev'

// ── Plugin: resolve bare 'src/' imports (tsconfig baseUrl: ".") ──
// The codebase uses `import ... from 'src/foo/bar.js'` which relies on
// TypeScript's baseUrl resolution. This plugin maps those to real TS files.
const srcResolverPlugin: esbuild.Plugin = {
  name: 'src-resolver',
  setup(build) {
    build.onResolve({ filter: /^src\// }, (args) => {
      const basePath = resolve(ROOT, args.path)

      // Already exists as-is
      if (existsSync(basePath)) {
        return { path: basePath }
      }

      // Strip .js/.jsx and try TypeScript extensions
      const withoutExt = basePath.replace(/\.(js|jsx)$/, '')
      for (const ext of ['.ts', '.tsx', '.js', '.jsx']) {
        const candidate = withoutExt + ext
        if (existsSync(candidate)) {
          return { path: candidate }
        }
      }

      // Try as directory with index file
      const dirPath = basePath.replace(/\.(js|jsx)$/, '')
      for (const ext of ['.ts', '.tsx', '.js', '.jsx']) {
        const candidate = resolve(dirPath, 'index' + ext)
        if (existsSync(candidate)) {
          return { path: candidate }
        }
      }

      // Let esbuild handle it (will error if truly missing)
      return undefined
    })
  },
}

// ── Plugin: load .md and .txt files as text modules ──
const textLoaderPlugin: esbuild.Plugin = {
  name: 'text-loader',
  setup(build) {
    build.onLoad({ filter: /\.(md|txt)$/ }, async (args) => {
      const { readFileSync } = await import('fs')
      const contents = readFileSync(args.path, 'utf-8')
      return {
        contents: `export default ${JSON.stringify(contents)}`,
        loader: 'js',
      }
    })
  },
}

// ── Plugin: resolve .d.ts imports (some files import global.d.ts) ──
const dtsResolverPlugin: esbuild.Plugin = {
  name: 'dts-resolver',
  setup(build) {
    build.onResolve({ filter: /\.d\.ts$/ }, () => ({
      path: resolve(ROOT, 'src/global.d.ts'),
      sideEffects: false,
    }))
    build.onLoad({ filter: /global\.d\.ts$/ }, () => ({
      contents: '',
      loader: 'js',
    }))
  },
}

// ── Plugin: resolve subpath imports for CJS stub packages ──
// Stub packages in node_modules use CJS (module.exports = Proxy) so esbuild
// can extract any named export. But subpath imports like '@ant/foo/types'
// need to resolve to the same index.js.
const stubSubpathPlugin: esbuild.Plugin = {
  name: 'stub-subpath',
  setup(build) {
    // @ant/* packages with subpath imports
    build.onResolve({ filter: /^@ant\/[^/]+\/.+/ }, (args) => {
      const base = args.path.split('/').slice(0, 2).join('/')
      const stubIndex = resolve(ROOT, 'node_modules', base, 'index.js')
      if (existsSync(stubIndex)) {
        return { path: stubIndex }
      }
      return undefined
    })
  },
}

const buildOptions: esbuild.BuildOptions = {
  entryPoints: [resolve(ROOT, 'src/entrypoints/cli.tsx')],
  bundle: true,
  platform: 'node',
  target: ['node20', 'es2022'],
  format: 'esm',
  outdir: resolve(ROOT, 'dist'),
  outExtension: { '.js': '.mjs' },

  // Single-file output — no code splitting for CLI tools
  splitting: false,

  plugins: [stubSubpathPlugin, srcResolverPlugin, textLoaderPlugin, dtsResolverPlugin],

  // Use tsconfig for baseUrl / paths resolution (complements plugin above)
  tsconfig: resolve(ROOT, 'tsconfig.json'),

  // Alias bun:bundle to our runtime shim
  alias: {
    'bun:bundle': resolve(ROOT, 'src/shims/bun-bundle.ts'),
  },

  // Only externalize Node.js built-in modules
  external: [
    'fs', 'path', 'os', 'crypto', 'child_process', 'http', 'https',
    'net', 'tls', 'url', 'util', 'stream', 'events', 'buffer',
    'querystring', 'readline', 'zlib', 'assert', 'tty', 'worker_threads',
    'perf_hooks', 'async_hooks', 'dns', 'dgram', 'cluster',
    'string_decoder', 'module', 'vm', 'constants', 'domain',
    'console', 'process', 'v8', 'inspector',
    'node:*',
    // node-pty must stay external — it's a native addon loaded at runtime
    'node-pty',
  ],

  jsx: 'automatic',

  // Source maps for production debugging (external .map files)
  sourcemap: noSourcemap ? false : 'external',

  // Minification for production
  minify,

  // Tree shaking (on by default, explicit for clarity)
  treeShaking: true,

  // Define replacements — inline constants at build time
  // MACRO.* — originally inlined by Bun's bundler at compile time
  // process.env.USER_TYPE — eliminates 'ant' (Anthropic-internal) code branches
  define: {
    'MACRO.VERSION': JSON.stringify(version),
    'MACRO.PACKAGE_URL': JSON.stringify('@anthropic-ai/claude-code'),
    'MACRO.ISSUES_EXPLAINER': JSON.stringify(
      'report issues at https://github.com/anthropics/claude-code/issues'
    ),
    'process.env.USER_TYPE': '"external"',
    'process.env.NODE_ENV': minify ? '"production"' : '"development"',
  },

  // Banner: shebang + CJS require compatibility for ESM bundle
  // Some bundled CJS packages (e.g. node-fetch in @anthropic-ai/sdk) use
  // require() for Node built-ins. ESM doesn't have require() by default.
  banner: {
    js: [
      '#!/usr/bin/env node',
      'import { createRequire as __cjsCreateRequire } from "module";',
      'const require = __cjsCreateRequire(import.meta.url);',
      '',
    ].join('\n'),
  },

  // Handle the .js → .ts resolution that the codebase uses
  resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],

  logLevel: 'info',

  // Metafile for bundle analysis
  metafile: true,
}

async function main() {
  if (watch) {
    const ctx = await esbuild.context(buildOptions)
    await ctx.watch()
    console.log('Watching for changes...')
  } else {
    const startTime = Date.now()
    const result = await esbuild.build(buildOptions)

    if (result.errors.length > 0) {
      console.error('Build failed')
      process.exit(1)
    }

    // Make the output executable
    const outPath = resolve(ROOT, 'dist/cli.mjs')
    try {
      chmodSync(outPath, 0o755)
    } catch {
      // chmod may fail on some platforms, non-fatal
    }

    const elapsed = Date.now() - startTime

    // Print bundle size info
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

      // Write metafile for further analysis
      const { writeFileSync } = await import('fs')
      writeFileSync(
        resolve(ROOT, 'dist/meta.json'),
        JSON.stringify(result.metafile),
      )
      console.log('  Metafile written to dist/meta.json')
    }
  }
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
