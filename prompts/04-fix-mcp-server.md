# Prompt 04: Fix MCP Server Build

## Context

You are working in `/workspaces/claude-code/mcp-server/`. This is a separate sub-project that provides an MCP (Model Context Protocol) server for exploring the Claude Code source. It's a simpler, self-contained TypeScript project.

Currently `npm run build` (which runs `tsc`) fails with TypeScript errors.

## Task

1. **Run the build and capture errors**:
   ```bash
   cd /workspaces/claude-code/mcp-server
   npm run build 2>&1
   ```

2. **Fix all TypeScript errors** in `mcp-server/src/server.ts` and `mcp-server/src/index.ts`. Common issues include:
   - Duplicate function implementations
   - Missing imports
   - Type mismatches with the MCP SDK types

3. **Verify the fix**:
   ```bash
   npm run build
   ```
   Should complete with zero errors and produce output in `mcp-server/dist/`.

4. **Test the MCP server runs**:
   ```bash
   node dist/index.js --help 2>&1 || node dist/index.js 2>&1 | head -5
   ```
   It may hang waiting for stdio input (that's normal for an MCP server) — just verify it starts without crashing.

## Key Files

- `mcp-server/package.json` — build script and dependencies
- `mcp-server/tsconfig.json` — TypeScript config  
- `mcp-server/src/server.ts` — Main server logic (tools, resources, prompts)
- `mcp-server/src/index.ts` — Entrypoint (stdio transport)

## Verification

1. `cd mcp-server && npm run build` succeeds with zero errors
2. `ls mcp-server/dist/` shows compiled `.js` files
3. `node mcp-server/dist/index.js` starts without immediate crash
