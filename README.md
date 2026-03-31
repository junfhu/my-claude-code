<div align="center">

# Claude Code — Leaked Source

**The full source code of Anthropic's Claude Code CLI, leaked on March 31, 2026**

[![TypeScript](https://img.shields.io/badge/TypeScript-512K%2B_lines-3178C6?logo=typescript&logoColor=white)](#tech-stack)
[![Bun](https://img.shields.io/badge/Runtime-Bun-f472b6?logo=bun&logoColor=white)](#tech-stack)
[![React + Ink](https://img.shields.io/badge/UI-React_%2B_Ink-61DAFB?logo=react&logoColor=black)](#tech-stack)
[![Files](https://img.shields.io/badge/~1,900_files-source_only-grey)](#directory-structure)
[![MCP Server](https://img.shields.io/badge/MCP-Explorer_Server-blueviolet)](#-explore-with-mcp-server)
[![npm](https://img.shields.io/npm/v/claude-code-explorer-mcp?label=npm&color=cb3837&logo=npm)](https://www.npmjs.com/package/claude-code-explorer-mcp)

> The original unmodified leaked source is preserved in the [`backup` branch](https://github.com/nirholas/claude-code/tree/backup).

</div>

---

## Table of Contents

- [How It Leaked](#how-it-leaked)
- [What Is Claude Code?](#what-is-claude-code)
- [Usage Guide](#usage-guide)
  - [Prerequisites](#prerequisites)
  - [Building from Source](#building-from-source)
  - [Running the CLI](#running-the-cli)
  - [Configuration](#configuration)
  - [Feature Flags](#feature-flags-1)
  - [Build Modes](#build-modes)
- [High-Level Design (HLD)](#high-level-design-hld)
  - [System Overview](#system-overview)
  - [Core Pipeline](#core-pipeline)
  - [Major Subsystems](#major-subsystems)
  - [Data Flow](#data-flow)
  - [Security Model](#security-model)
  - [Extensibility Model](#extensibility-model)
- [Low-Level Design (LLD)](#low-level-design-lld)
  - [Startup Sequence](#startup-sequence)
  - [Query Pipeline Internals](#query-pipeline-internals)
  - [Tool System Internals](#tool-system-internals)
  - [State Management](#state-management)
  - [Terminal UI Layer](#terminal-ui-layer)
  - [Permission System Internals](#permission-system-internals)
  - [Service Layer Internals](#service-layer-internals)
  - [Build System Internals](#build-system-internals)
  - [Key Data Structures](#key-data-structures)
- [Documentation](#-documentation)
- [Explore with MCP Server](#-explore-with-mcp-server)
- [Directory Structure](#directory-structure)
- [Architecture](#architecture)
- [Key Files](#key-files)
- [Tech Stack](#tech-stack)
- [Design Patterns](#design-patterns)
- [GitPretty Setup](#gitpretty-setup)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)

---

## How It Leaked

[Chaofan Shou (@Fried_rice)](https://x.com/Fried_rice) discovered that the published npm package for Claude Code included a `.map` file referencing the full, unobfuscated TypeScript source — downloadable as a zip from Anthropic's R2 storage bucket.

> **"Claude code source code has been leaked via a map file in their npm registry!"**
>
> — [@Fried_rice, March 31, 2026](https://x.com/Fried_rice/status/2038894956459290963)

---

## What Is Claude Code?

Claude Code is Anthropic's official CLI tool for interacting with Claude directly from the terminal — editing files, running commands, searching codebases, managing git workflows, and more. This repository contains the leaked `src/` directory.

| | |
|---|---|
| **Leaked** | 2026-03-31 |
| **Language** | TypeScript (strict) |
| **Runtime** | [Bun](https://bun.sh) |
| **Terminal UI** | [React](https://react.dev) + [Ink](https://github.com/vadimdemedes/ink) |
| **Scale** | ~1,900 files · 512,000+ lines of code |

---

## Usage Guide

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Node.js** | >= 20 | Runtime for the built bundle |
| **Bun** | >= 1.1.0 | Build toolchain and dev mode |
| **npm** | any | Dependency installation |
| **ripgrep** | any | Required by `GrepTool` at runtime |
| **git** | any | Required by many tools and commands |

```bash
# Install Bun (if not already installed)
npm install -g bun

# Verify
bun --version   # >= 1.1.0
node --version  # >= 20
```

### Building from Source

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd claude-code

# 2. Install dependencies
bun install

# 3. Build the CLI bundle
bun run build
#   -> dist/cli.mjs  (~20 MB, single-file ESM bundle)
```

The build produces a self-contained `dist/cli.mjs` that runs on Node.js without Bun.

### Running the CLI

```bash
# --- Via the built bundle (Node.js) ---
node dist/cli.mjs --version          # Print version
node dist/cli.mjs --help             # Full help text
node dist/cli.mjs "your prompt"      # One-shot prompt (non-interactive)
node dist/cli.mjs                    # Interactive REPL

# --- Via Bun dev mode (no build step) ---
bun scripts/dev.ts --version
bun scripts/dev.ts --help
bun scripts/dev.ts "your prompt"

# --- Make it executable (optional) ---
chmod +x dist/cli.mjs
./dist/cli.mjs --help

# --- Symlink for convenience (optional) ---
ln -s "$(pwd)/dist/cli.mjs" ~/.local/bin/claude
claude --help
```

#### Authentication

The CLI requires an Anthropic API key to make LLM calls:

```bash
# Option 1: Environment variable
export ANTHROPIC_API_KEY="sk-ant-..."
node dist/cli.mjs "Hello, Claude"

# Option 2: .env file in project root
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
node dist/cli.mjs "Hello, Claude"

# Option 3: OAuth login (if configured)
node dist/cli.mjs /login
```

#### Common Usage Patterns

```bash
# Non-interactive (pipe-friendly) mode
node dist/cli.mjs -p "Explain this codebase"

# Specify a model
node dist/cli.mjs --model claude-sonnet-4-20250514 "Refactor main.ts"

# Output as JSON
node dist/cli.mjs -p --output-format json "List all functions"

# Resume a previous session
node dist/cli.mjs --resume

# Dump the system prompt (debug)
node dist/cli.mjs --dump-system-prompt

# Run environment diagnostics
node dist/cli.mjs /doctor
```

#### REPL Slash Commands

Inside the interactive REPL, type `/` to see all available commands:

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/compact` | Compress conversation context |
| `/cost` | Display token usage and cost |
| `/config` | View/edit settings |
| `/doctor` | Run environment diagnostics |
| `/commit` | Git commit with AI message |
| `/review` | Code review |
| `/diff` | View file changes |
| `/memory` | Manage persistent memory |
| `/mcp` | Manage MCP servers |
| `/skills` | Manage skills |
| `/tasks` | View background tasks |
| `/vim` | Toggle vim mode |
| `/theme` | Change color theme |
| `/share` | Share the session |
| `/resume` | Restore a previous session |
| `/exit` | Exit the REPL |

### Configuration

#### Configuration Files

| File | Scope | Purpose |
|---|---|---|
| `~/.claude/settings.json` | User-global | API keys, default model, theme, permissions |
| `.claude/settings.json` | Project | Project-specific settings |
| `CLAUDE.md` | Project | Persistent memory / project instructions |
| `~/.claude/CLAUDE.md` | User-global | Cross-project memory |
| `~/.claude/keybindings.json` | User-global | Custom keybindings |
| `.claude/mcp.json` | Project | MCP server configuration |

#### Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Anthropic |
| `CLAUDE_CODE_MODEL` | Override default model |
| `CLAUDE_CODE_SIMPLE` | Bare mode (minimal tools) |
| `CLAUDE_CODE_REMOTE` | Remote container mode |
| `DISABLE_COMPACT` | Disable auto-compaction |
| `DISABLE_AUTO_COMPACT` | Disable automatic compaction triggers |

### Feature Flags

Feature-gated functionality can be enabled at runtime via environment variables:

```bash
# Enable specific features
export CLAUDE_CODE_BRIDGE_MODE=1     # IDE bridge integration
export CLAUDE_CODE_VOICE_MODE=1      # Voice input/output
export CLAUDE_CODE_DAEMON=1          # Background daemon mode
export CLAUDE_CODE_BG_SESSIONS=1     # Background sessions (ps/logs/attach/kill)
export CLAUDE_CODE_PROACTIVE=1       # Proactive agent mode
export CLAUDE_CODE_COORDINATOR_MODE=1 # Multi-agent coordinator
export CLAUDE_CODE_WORKFLOW_SCRIPTS=1 # Workflow automation
export CLAUDE_CODE_ULTRAPLAN=1       # Ultra-planning mode
```

All flags default to `false`. In production Bun builds, these are compile-time constants for dead-code elimination; in this dev build, they read from environment variables at runtime via `src/shims/bun-bundle.ts`.

### Build Modes

```bash
# Development build (default)
bun run build

# Production build (minified)
bun run build:prod

# Watch mode (auto-rebuild on changes)
bun run build:watch

# Dev mode (no build, runs through Bun directly)
bun scripts/dev.ts [args...]

# Type checking (no emit)
bun run typecheck

# Lint
bun run lint
bun run lint:fix
```

---

## High-Level Design (HLD)

### System Overview

Claude Code is a terminal-native AI coding assistant built as a single-file ESM CLI bundle. It implements a **reactive REPL** (Read-Eval-Print Loop) that connects user input to an LLM backend, executes tool calls in a loop, and renders output via a React-based terminal UI.

```
+------------------------------------------------------------------+
|                        Claude Code CLI                            |
|                                                                   |
|  +------------------+    +------------------+    +--------------+ |
|  |  CLI Entrypoint  |--->|  Commander.js    |--->|  React/Ink   | |
|  |  (cli.tsx)       |    |  (main.tsx)      |    |  REPL UI     | |
|  +------------------+    +------------------+    +--------------+ |
|                                |                       |          |
|                                v                       v          |
|  +------------------+    +------------------+    +--------------+ |
|  |  Context         |    |  Query Engine    |<-->|  Tool System | |
|  |  Collection      |--->|  (QueryEngine.ts)|    |  (40+ tools) | |
|  +------------------+    +------------------+    +--------------+ |
|                                |                       |          |
|                                v                       v          |
|  +------------------+    +------------------+    +--------------+ |
|  |  Anthropic API   |    |  Permission      |    |  Services    | |
|  |  (SDK client)    |    |  System          |    |  MCP/LSP/... | |
|  +------------------+    +------------------+    +--------------+ |
+------------------------------------------------------------------+
```

### Core Pipeline

The system follows a pipeline model with a central event loop:

```
User Input
    |
    v
CLI Parser (Commander.js)
    |
    v
Initialization (auth, config, policies, feature flags)
    |
    v
Context Collection (git status, CLAUDE.md, memory, project info)
    |
    v
+---------- Query Loop (QueryEngine) ----------+
|                                               |
|  System Prompt + User Message                 |
|       |                                       |
|       v                                       |
|  Anthropic API (streaming)                    |
|       |                                       |
|       v                                       |
|  Response Processing                          |
|       |                                       |
|       +--- Text Block ---> Render to terminal |
|       |                                       |
|       +--- Tool Use Block ---> Permission     |
|       |                         Check         |
|       |                           |           |
|       |                           v           |
|       |                      Tool Execution   |
|       |                           |           |
|       |                           v           |
|       |                      Tool Result      |
|       |                           |           |
|       +--<--- Feed back to API ---+           |
|                                               |
|  Loop until: completed / aborted / max_turns  |
+-----------------------------------------------+
    |
    v
Terminal UI Rendering (React/Ink)
```

### Major Subsystems

| Subsystem | Location | Responsibility |
|---|---|---|
| **CLI Entrypoint** | `src/entrypoints/cli.tsx` | Bootstrap, fast-path dispatching for `--version`, `--daemon-worker`, bridge, etc. |
| **Main CLI** | `src/main.tsx` | Commander.js setup, option parsing, initialization, REPL launch |
| **Query Engine** | `src/QueryEngine.ts`, `src/query/` | LLM conversation loop, streaming, tool execution, token budgeting |
| **Tool System** | `src/Tool.ts`, `src/tools/`, `src/tools.ts` | 40+ self-contained tools with input schemas, permissions, and execution logic |
| **Command System** | `src/commands.ts`, `src/commands/` | ~80 slash commands (prompt, local, local-JSX types) |
| **Permission System** | `src/hooks/toolPermission/` | Per-tool permission checks, interactive/classifier/headless modes |
| **Terminal UI** | `src/ink/`, `src/components/`, `src/screens/` | Custom React/Ink renderer, ~400 components, 3 full-screen modes |
| **State Management** | `src/state/` | Immutable `AppState` store with React Context integration |
| **Services** | `src/services/` | API client, MCP, OAuth, LSP, analytics, compaction, memory |
| **Bridge** | `src/bridge/` | Bidirectional IDE integration (VS Code, JetBrains) |
| **Coordinator** | `src/coordinator/` | Multi-agent orchestration with teams |
| **Skills** | `src/skills/` | Reusable named workflows (16 bundled + user-defined) |
| **Plugins** | `src/plugins/` | Third-party extensibility |
| **Tasks** | `src/tasks/` | Background task management (shell, agent, teammate, dream) |
| **Memory** | `src/memdir/` | Persistent memory via `CLAUDE.md` files |
| **Voice** | `src/voice/` | Voice input/output (feature-gated) |
| **Keybindings** | `src/keybindings/` | 50+ actions, 17 contexts, chord support, vim mode |

### Data Flow

#### Interactive Session

```
1. Startup
   cli.tsx -> main() -> run()
   |-- Parallel prefetch: MDM settings, Keychain, API preconnect
   |-- init(): auth, config, trust, telemetry
   |-- setup() + getCommands() + getAgentDefinitions()  [parallel]
   |-- getSystemContext() + getUserContext()              [parallel]

2. REPL Loop (per turn)
   User types message (PromptInput component)
   |-- Message added to conversation history
   |-- QueryEngine.query(messages, tools, systemPrompt)
   |   |-- Anthropic API call (streaming)
   |   |-- For each tool_use block:
   |   |   |-- checkPermissions(tool, input)
   |   |   |-- tool.execute(input, context)
   |   |   |-- Append tool_result to messages
   |   |   |-- Continue API streaming
   |   |-- Return final assistant message
   |-- Render response in terminal (React/Ink components)
   |-- Update cost tracker
   |-- Check auto-compact threshold

3. Shutdown
   /exit or Ctrl+C -> gracefulShutdown()
   |-- Flush analytics
   |-- Close MCP connections
   |-- Write session memory
```

#### Non-Interactive Session (`-p` / `--print`)

```
CLI args -> parse prompt -> Query Engine -> stream output -> exit
  (no REPL UI, no setup screens, no keybindings)
```

### Security Model

```
+----------------------------+
|     Permission Modes       |
|                            |
|  default    Interactive    |
|             prompts for    |
|             each action    |
|                            |
|  plan       Show plan,     |
|             batch approve  |
|                            |
|  auto       ML classifier  |
|             decides        |
|                            |
|  bypass     Auto-approve   |
|             all (danger)   |
+----------------------------+
         |
         v
+----------------------------+
|     Permission Rules       |
|                            |
|  Bash(git *)      Allow    |
|  Bash(npm test)   Allow    |
|  FileEdit(/src/*) Allow    |
|  FileRead(*)      Allow    |
+----------------------------+
         |
         v
+----------------------------+
|     Enforcement Points     |
|                            |
|  - Every tool invocation   |
|  - Working directory scope |
|  - Policy limits (org)     |
|  - MCP server approval     |
+----------------------------+
```

### Extensibility Model

Claude Code is extensible at four levels:

```
Level 1: Skills       User-defined prompt + tool bundles   (~/.claude/skills/ or SKILL.md)
Level 2: Plugins      Third-party code extensions          (~/.claude/plugins/)
Level 3: MCP Servers  External tool/resource providers     (.claude/mcp.json)
Level 4: Hooks        Shell/prompt/HTTP pre/post actions   (settings.json hooks config)
```

---

## Low-Level Design (LLD)

### Startup Sequence

The full startup spans two files and is heavily optimized for latency through parallel initialization:

```
cli.tsx::main()
  |
  |-- Fast paths (zero imports):
  |   |-- --version        -> print MACRO.VERSION, return
  |   |-- --daemon-worker  -> runDaemonWorker(), return
  |   |-- bridge/rc/remote -> bridgeMain(), return
  |   |-- daemon           -> daemonMain(), return
  |   |-- ps/logs/attach   -> bg handlers, return
  |   |-- environment-runner -> environmentRunnerMain(), return
  |
  |-- Default path:
  |   import('../main.js').main()
  |
main.tsx::main()
  |-- Set security env vars (Windows PATH hijack prevention)
  |-- Install SIGINT handler
  |-- Handle URL schemes (cc://, cc+unix://)
  |
  |-- run()
      |-- Create Commander program
      |-- Register preAction hook:
      |   |-- await MDM + Keychain prefetch (started in parallel at import time)
      |   |-- init() -> auth, settings, trust, telemetry
      |   |-- initSinks() -> analytics
      |   |-- Run migrations
      |   |-- loadRemoteManagedSettings() [non-blocking]
      |   |-- loadPolicyLimits() [non-blocking]
      |
      |-- Register CLI options (50+ flags)
      |-- Register subcommands (mcp, auth, plugin, doctor, etc.)
      |
      |-- Default action handler:
          |-- Parse & validate arguments
          |-- getTools(permissionContext) -> filtered tool list
          |-- Parallel:
          |   |-- setup() -> worktree, tmux, permissions, session ID
          |   |-- getCommands() -> all available commands
          |   |-- getAgentDefinitions() -> agent configs
          |
          |-- Parallel (non-blocking):
          |   |-- getSystemContext() -> git status, branch, log
          |   |-- getUserContext() -> CLAUDE.md, memory files
          |   |-- ensureModelStringsInitialized()
          |
          |-- Interactive path:
          |   |-- createRoot() -> Ink React root
          |   |-- showSetupScreens() -> trust dialog, onboarding
          |   |-- launchRepl(root, sessionConfig, renderAndRun)
          |
          |-- renderAndRun(root, element):
              |-- root.render(element)
              |-- startDeferredPrefetches() -> bootstrap, fast mode, passes
              |-- await root.waitUntilExit()
              |-- gracefulShutdown(0)
```

### Query Pipeline Internals

#### Core Files

| File | Lines | Responsibility |
|---|---|---|
| `src/QueryEngine.ts` | ~1,300 | Standalone engine class: message history, file state, permissions, skill discovery |
| `src/query/query.ts` | ~1,730 | Main query loop: API calls, streaming, tool execution, compaction triggers |
| `src/query/config.ts` | 47 | Immutable `QueryConfig` snapshot: session ID, runtime gates |
| `src/query/transitions.ts` | 37 | Loop control: terminal states (`completed`, `aborted`, `max_turns`) vs continue states (`tool_use`, `retry`) |
| `src/query/tokenBudget.ts` | — | Token budget tracking and enforcement |
| `src/query/stopHooks.ts` | — | Hooks that can terminate the loop |

#### Query Loop State Machine

```
                    +----------+
                    |  Start   |
                    +----+-----+
                         |
                         v
                +--------+--------+
                | Build API       |
                | payload         |
                | (messages +     |
                |  system prompt  |
                |  + tools)       |
                +--------+--------+
                         |
                         v
                +--------+--------+
           +--->| Call Anthropic  |
           |    | API (streaming) |
           |    +--------+--------+
           |             |
           |             v
           |    +--------+--------+
           |    | Process response|
           |    | blocks          |
           |    +--------+--------+
           |             |
           |       +-----+------+
           |       |            |
           |       v            v
           |   text_block   tool_use_block
           |   (render)         |
           |                    v
           |           +--------+--------+
           |           | Check           |
           |           | permission      |
           |           +--------+--------+
           |                    |
           |              +-----+-----+
           |              |           |
           |              v           v
           |           Allowed     Denied
           |              |           |
           |              v           v
           |        tool.execute() error_result
           |              |           |
           |              v           v
           |         tool_result  tool_result
           |              |           |
           |              +-----+-----+
           |                    |
           |                    v
           |           Append to messages
           |                    |
           +----<--- continue --+
                                |
                         +------+------+
                         |  Terminal?  |
                         +------+------+
                                |
                          +-----+-----+
                          |           |
                          v           v
                     completed    aborted/
                                  max_turns/
                                  error
```

#### Token Budget Management

The query pipeline tracks tokens per turn and across the session:

- **Input tokens**: System prompt + conversation history + tool definitions
- **Output tokens**: LLM response text + tool calls
- **Auto-compact trigger**: When input tokens exceed threshold, fires `compact/autoCompact.ts` as a forked subagent to summarize older messages
- **Context collapse**: Feature-gated compaction strategy (`REACTIVE_COMPACT`)
- **Max output recovery**: If the API returns `max_output_tokens` stop reason, retries with a continue prompt

### Tool System Internals

#### Tool Interface

Every tool implements this contract (defined in `src/Tool.ts`):

```typescript
interface Tool {
  name: string
  description: string
  inputSchema: ZodSchema             // Zod v4 input validation
  isEnabled(context): boolean        // Feature/environment gate
  isConcurrencySafe(): boolean       // Can run in parallel?
  checkPermissions(input, context)   // Permission check
  execute(input, context): Result    // Actual implementation
  renderToolUse(input): JSX          // Terminal UI for invocation
  renderToolResult(result): JSX      // Terminal UI for result
}
```

#### Tool Registry (`src/tools.ts`)

```
getTools(permissionContext)
  |
  |-- CLAUDE_CODE_SIMPLE mode?
  |   YES -> return [BashTool, FileReadTool, FileEditTool]
  |
  |-- getAllBaseTools() -> exhaustive list of all tools
  |   |-- Filter by: deny rules, feature flags, isEnabled()
  |   |
  |   |-- Always included:
  |   |   AgentTool, BashTool, FileReadTool, FileEditTool,
  |   |   FileWriteTool, GlobTool, GrepTool, SkillTool,
  |   |   WebFetchTool, WebSearchTool, MCPTool, ...
  |   |
  |   |-- Feature-gated:
  |   |   COORDINATOR_MODE -> TeamCreateTool, TeamDeleteTool, SendMessageTool
  |   |   PROACTIVE        -> SleepTool
  |   |   WORKFLOW_SCRIPTS  -> WorkflowTool
  |   |   MONITOR_TOOL      -> MonitorTool
  |   |   ...
  |
  +-- Return filtered tool[]
```

#### Complete Tool Inventory (40 real implementations + 16 stubs)

| Category | Tool | Lines | Description |
|---|---|---|---|
| **File I/O** | `FileReadTool` | 1,184 | Read files with image/PDF/notebook processing, token estimation |
| | `FileWriteTool` | 435 | Create/overwrite files with directory creation |
| | `FileEditTool` | 626 | Partial string replacement with diff tracking, LSP integration |
| | `NotebookEditTool` | 491 | Jupyter notebook cell editing |
| **Search** | `GrepTool` | 578 | ripgrep-based content search with context lines |
| | `GlobTool` | 199 | File pattern matching with permission checking |
| | `WebSearchTool` | 436 | Web search via Claude's native capability |
| | `WebFetchTool` | 319 | Fetch URL content with markdown conversion |
| | `ToolSearchTool` | 472 | Discover deferred tools from MCP servers |
| **Execution** | `BashTool` | 1,144 | Shell execution with security validation, timeout, background support |
| | `PowerShellTool` | 1,001 | Windows PowerShell with same security model as BashTool |
| | `SkillTool` | 1,109 | Invoke skills/custom commands with permission validation |
| | `LSPTool` | 861 | Language Server Protocol (symbols, hover, references, diagnostics) |
| **Agents** | `AgentTool` | 1,398 | Sub-agent spawning with memory, color management, lifecycle |
| | `SendMessageTool` | 918 | Inter-agent/teammate/user messaging with routing |
| | `TeamCreateTool` | 241 | Create agent teams with configuration |
| | `TeamDeleteTool` | 140 | Delete teams and cleanup resources |
| **Tasks** | `TaskCreateTool` | 139 | Create background tasks |
| | `TaskUpdateTool` | 407 | Update task status and blocking relationships |
| | `TaskListTool` | 117 | List all tasks with status |
| | `TaskGetTool` | 129 | Retrieve task details by ID |
| | `TaskOutputTool` | 584 | Retrieve and display task output |
| | `TaskStopTool` | 132 | Stop running tasks |
| **Planning** | `EnterPlanModeTool` | 127 | Enter structured planning mode |
| | `ExitPlanModeTool` | 494 | Exit plan mode with approval workflow |
| | `EnterWorktreeTool` | 128 | Create git worktree for isolation |
| | `ExitWorktreeTool` | 330 | Cleanup and exit git worktree |
| **MCP** | `MCPTool` | 78 | Execute tools on connected MCP servers |
| | `McpAuthTool` | 216 | OAuth authentication for MCP servers |
| | `ListMcpResourcesTool` | 124 | List MCP server resources |
| | `ReadMcpResourceTool` | 159 | Read MCP resource contents |
| **Other** | `AskUserQuestionTool` | 266 | Multiple-choice user prompts |
| | `BriefTool` | 205 | Formatted messages with attachments |
| | `ConfigTool` | 468 | Settings management |
| | `TodoWriteTool` | 116 | Todo list management |
| | `SyntheticOutputTool` | 164 | Structured JSON output |
| | `RemoteTriggerTool` | 162 | Remote workflow trigger via HTTP |
| | `CronCreateTool` | 158 | Schedule recurring jobs |
| | `CronListTool` | 98 | List scheduled jobs |
| | `CronDeleteTool` | 96 | Delete scheduled jobs |
| **Stubs** | `WebBrowserTool`, `MonitorTool`, `SnipTool`, `WorkflowTool`, `TungstenTool`, `SleepTool`, `TerminalCaptureTool`, `PushNotificationTool`, `ReviewArtifactTool`, `SendUserFileTool`, `ListPeersTool`, `CtxInspectTool`, `OverflowTestTool`, `VerifyPlanExecutionTool`, `SubscribePRTool`, `DiscoverSkillsTool` | — | Not included in leaked source |

### State Management

#### Store Pattern (`src/state/store.ts`)

A minimal reactive store with subscribe/notify:

```typescript
// Generic Store<T> factory
interface Store<T> {
  getState(): T
  setState(updater: (prev: T) => T): void
  subscribe(listener: (state: T) => void): () => void
}
```

#### AppState (`src/state/AppStateStore.ts`, ~570 lines)

The central immutable state object containing:

```
AppState
├── settings              # User/project settings
├── model                 # Current model selection
├── uiState
│   ├── expandedView      # Expanded output mode
│   └── footerSelection   # Active footer tab
├── toolPermissionContext
│   ├── allowedTools      # Tool allow rules
│   ├── denyRules         # Tool deny rules
│   └── workingDirectories # Scoped directories
├── mcpClients            # Active MCP server connections
├── plugins               # Loaded plugins
├── agents                # Active agent definitions
├── tasks                 # Background tasks
├── bridgeState           # IDE bridge connection state
├── coordinatorState      # Multi-agent coordinator state
├── speculationState      # Prompt suggestion generation
├── remoteSessionState    # Remote session info
├── notificationQueue     # Pending notifications
└── elicitationQueue      # Pending MCP elicitations
```

State flows through the system via React Context (`src/state/AppState.tsx`) and is accessible to all components and tool execution contexts.

#### State Change Pipeline

```
setState(updater)
    |
    v
Notify subscribers
    |
    +-- React re-render (via context)
    +-- onChangeAppState() side-effects
    |   |-- Sync to CCR metadata
    |   |-- Update bridge state
    |   +-- Emit telemetry
    +-- Selector re-evaluation
```

### Terminal UI Layer

#### Architecture

The UI is built on a custom fork of [Ink](https://github.com/vadimdemedes/ink) — a React renderer for the terminal:

```
React Component Tree
        |
        v
Custom Reconciler (ink/reconciler.ts)
        |
        v
Yoga Layout Engine (ink/layout/)
        |
        v
Render Pipeline (ink/render-node-to-output.ts)
        |
        v
Screen Buffer (ink/screen.ts)
        |
        v
ANSI Output (ink/termio/)
        |
        v
stdout
```

#### Key UI Modules

| Module | Files | Purpose |
|---|---|---|
| **Reconciler** | `ink/reconciler.ts`, `ink/renderer.ts` | React-to-terminal reconciliation |
| **Layout** | `ink/layout/engine.ts`, `node.ts`, `geometry.ts`, `yoga.ts` | Flexbox layout via Yoga |
| **Rendering** | `ink/render-node-to-output.ts` (1,463 lines) | DOM-to-terminal output with incremental diff |
| **Screen** | `ink/screen.ts` (1,471 lines) | Terminal cell buffer, style management, hyperlinks |
| **Input** | `ink/parse-keypress.ts`, `ink/events/` | Keyboard/mouse parsing (Kitty protocol, xterm) |
| **Selection** | `ink/selection.ts` (893 lines) | Character/word/line selection with drag |
| **Terminal I/O** | `ink/termio/` | ANSI parser, CSI, DEC, OSC, SGR sequences |
| **Components** | `ink/components/` | Box, Text, Button, ScrollBox, Link, AlternateScreen |
| **Hooks** | `ink/hooks/` | useInput, useStdin, useTerminalFocus, useAnimationFrame |

#### Component Hierarchy

```
<App>                          # Root: stdin/stdout, raw mode, mouse tracking
  <KeybindingProvider>         # Chord-aware keybinding resolution
    <AppStateProvider>         # Global state context
      <REPL>                   # Main screen (5,006 lines)
        <LogoV2/>              # Welcome banner
        <PromptInput/>         # User input with autocomplete
        <MessageList>          # Conversation messages
          <AssistantMessage/>  # LLM response rendering
          <ToolUseMessage/>    # Tool invocation display
          <ToolResultMessage/> # Tool result display
        </MessageList>
        <BackgroundTasksBar/>  # Task status
        <CostDisplay/>         # Token cost
        <PermissionDialog/>    # Permission prompts
      </REPL>
    </AppStateProvider>
  </KeybindingProvider>
</App>
```

#### Screens

| Screen | File | Lines | Purpose |
|---|---|---|---|
| `REPL` | `src/screens/REPL.tsx` | 5,006 | Main interactive session |
| `Doctor` | `src/screens/Doctor.tsx` | 575 | Environment diagnostics |
| `ResumeConversation` | `src/screens/ResumeConversation.tsx` | — | Session selection/restore |

#### Keybinding System

17 contexts, 50+ actions, chord support:

```
Keystroke -> parseKeybinding()
    |
    v
resolveKeyWithChordState(key, contexts[], chordState)
    |
    +-- Match in active context? -> dispatch action
    +-- Partial chord match? -> update chordState, wait for next key
    +-- No match? -> pass through to input
```

Contexts are prioritized (most specific wins): e.g., `Autocomplete` > `Chat` > `Global`.

#### Vim Mode (`src/vim/`)

Full vim keybinding state machine:

```
VimState
├── INSERT mode
│   └── tracks insertedText (for dot-repeat)
└── NORMAL mode
    └── CommandState transitions:
        idle -> count -> operator -> operatorCount -> motion/find/textObj
        
Operators: d(elete), c(hange), y(ank)
Motions:   h/l/j/k, w/b/e, 0/^/$, f/F/t/T, gg/G
TextObjs:  iw, aw, i", a", i(, a(, etc.
Persistent: lastChange (dot-repeat), lastFind, register
```

### Permission System Internals

#### Permission Flow

```
Tool invocation
    |
    v
PermissionContext.checkPermissions(tool, input)
    |
    +-- Check deny rules -> DENY if matched
    |
    +-- Check allow rules -> ALLOW if matched
    |
    +-- Check working directory scope -> DENY if out of scope
    |
    +-- Permission mode?
        |
        +-- bypass -> ALLOW
        |
        +-- headless -> DENY (non-interactive)
        |
        +-- auto -> bashPermissions classifier
        |          |
        |          +-- SAFE -> ALLOW
        |          +-- UNSAFE -> prompt user
        |
        +-- default/plan -> Push to confirm queue
                           |
                           +-- Race: permission hooks vs. user input
                           |
                           +-- User approves -> ALLOW
                           |   (optionally: "always allow" persists rule)
                           |
                           +-- User denies -> DENY
```

#### Key Files

| File | Lines | Purpose |
|---|---|---|
| `hooks/toolPermission/PermissionContext.ts` | 389 | Decision context: logging, persistence, queue management |
| `hooks/toolPermission/handlers/interactiveHandler.ts` | 537 | Interactive flow: prompt racing, bridge callbacks, resolve-once guard |
| `hooks/toolPermission/handlers/coordinatorHandler.ts` | — | Multi-agent permission delegation |
| `hooks/toolPermission/handlers/swarmWorkerHandler.ts` | — | Worker agent permission requests |
| `hooks/toolPermission/permissionLogging.ts` | — | Analytics logging for decisions |
| `utils/permissions/bashPermissions.ts` | — | Async bash command safety classifier |

### Service Layer Internals

#### API Client (`src/services/api/client.ts`, 402 lines)

Supports multiple LLM backends through a unified client:

```
createClient(config)
    |
    +-- Direct Anthropic API (default)
    +-- AWS Bedrock
    +-- Azure Foundry
    +-- Google Vertex
    
Features:
    - Proxy support (https-proxy-agent)
    - Custom headers injection
    - Request ID tracking
    - Retry with exponential backoff (withRetry.ts)
    - Cost tracking per request (logging.ts)
    - Error classification (errors.ts)
```

#### MCP Client (`src/services/mcp/client.ts`, 3,349 lines)

Full Model Context Protocol client:

```
MCPClient
├── Server lifecycle (start, stop, restart)
├── Transport negotiation
│   ├── stdio
│   ├── SSE (Server-Sent Events)
│   ├── WebSocket
│   ├── HTTP (streamable)
│   └── SDK (in-process)
├── Tool discovery & execution
├── Resource listing & reading
├── Auth flows (OAuth, API key, IDP)
├── Error recovery & reconnection
├── Elicitation handling (-32042 errors)
└── Channel permissions (Telegram/iMessage relay)
```

#### Compaction Service (`src/services/compact/compact.ts`, 1,706 lines)

Conversation history compression to stay within context window:

```
Auto-compact trigger (token threshold exceeded)
    |
    v
Fork subagent with compaction prompt
    |
    v
Claude summarizes older messages
    |
    v
Replace old messages with summary
    |
    v
Insert CompactBoundary marker
    |
    v
Resume with compressed history
```

Variants: `autoCompact` (threshold-based), `microCompact` (lightweight), `snipCompact` (history projection), `reactiveCompact` (on-demand).

#### Analytics (`src/services/analytics/index.ts`)

Event pipeline with queue-before-sink pattern:

```
logEvent(event)
    |
    v
Queue (before sinks initialized)
    |
    v
initSinks() flushes queue
    |
    +-- Datadog sink
    +-- First-party event logger (PII-tagged proto fields)
    +-- GrowthBook (feature flags + A/B testing)
```

### Build System Internals

#### Build Pipeline (`scripts/build-bundle.ts`)

```
esbuild.build({
    entryPoints: ['src/entrypoints/cli.tsx'],
    bundle: true,
    platform: 'node',
    target: ['node20', 'es2022'],
    format: 'esm',
    splitting: false,         // Single-file output
    treeShaking: true,
    ...
})
```

#### Custom Plugins

| Plugin | Purpose |
|---|---|
| `stubSubpathPlugin` | Resolve `@ant/pkg/subpath` imports to CJS stub packages |
| `srcResolverPlugin` | Map `src/foo/bar.js` imports to actual `.ts`/`.tsx` files (tsconfig baseUrl) |
| `textLoaderPlugin` | Import `.md` and `.txt` files as ES modules with default text export |
| `dtsResolverPlugin` | Handle `import '../global.d.ts'` (returns empty module) |

#### Key Build Defines

```typescript
define: {
    'MACRO.VERSION': '"0.0.0-leaked"',
    'MACRO.PACKAGE_URL': '"@anthropic-ai/claude-code"',
    'process.env.USER_TYPE': '"external"',      // Eliminates Anthropic-internal code branches
    'process.env.NODE_ENV': '"development"',
}
```

#### CJS Compatibility

The bundle is ESM but some bundled packages use `require()`. The banner injects:

```javascript
import { createRequire as __cjsCreateRequire } from "module";
const require = __cjsCreateRequire(import.meta.url);
```

#### Feature Flag Shimming

Production Bun uses compile-time `bun:bundle` for dead-code elimination. This build aliases it to `src/shims/bun-bundle.ts`, which reads environment variables at runtime:

```typescript
// src/shims/bun-bundle.ts
export function feature(name: string): boolean {
    return FEATURE_FLAGS[name] ?? false
}
// Where FEATURE_FLAGS reads from process.env.CLAUDE_CODE_<FLAG>
```

All 24 feature flags: `PROACTIVE`, `KAIROS`, `KAIROS_BRIEF`, `KAIROS_GITHUB_WEBHOOKS`, `BRIDGE_MODE`, `DAEMON`, `VOICE_MODE`, `AGENT_TRIGGERS`, `MONITOR_TOOL`, `COORDINATOR_MODE`, `ABLATION_BASELINE`, `DUMP_SYSTEM_PROMPT`, `BG_SESSIONS`, `HISTORY_SNIP`, `WORKFLOW_SCRIPTS`, `CCR_REMOTE_SETUP`, `EXPERIMENTAL_SKILL_SEARCH`, `ULTRAPLAN`, `TORCH`, `UDS_INBOX`, `FORK_SUBAGENT`, `BUDDY`, `MCP_SKILLS`, `REACTIVE_COMPACT`.

### Key Data Structures

#### Message Types (`src/types/message.ts`)

```
Message (union type)
├── UserMessage          {role: 'user', content: TextBlock | ImageBlock | ...}
├── AssistantMessage     {role: 'assistant', content: TextBlock | ToolUseBlock | ThinkingBlock}
├── ToolResultMessage    {role: 'user', tool_use_id: string, content: string | ImageBlock[]}
├── SystemMessage        {type: 'system', content: string}
├── CompactBoundary      {type: 'compact_boundary', summary: string}
└── AttachmentMessage    {type: 'attachment', file: FileAttachment}
```

#### Tool Use Block

```
ToolUseBlock {
    type: 'tool_use'
    id: string           // Unique tool call ID
    name: string         // Tool name (e.g., 'BashTool')
    input: object        // Validated against tool's Zod schema
}
```

#### Query Transitions (`src/query/transitions.ts`)

```
Terminal transitions (loop exits):
  completed           # LLM finished naturally (end_turn stop reason)
  blocking_limit      # Token budget exhausted
  model_error         # Unrecoverable API error
  aborted_user        # User cancelled (Ctrl+C)
  aborted_tool        # Tool requested abort
  prompt_too_long     # Input exceeds context window
  max_turns           # Turn limit reached

Continue transitions (loop continues):
  tool_use            # LLM requested tool execution
  reactive_compact_retry  # Retry after reactive compaction
  max_output_tokens_recovery  # Retry after max output
  queued_command      # Queued slash command to process
```

#### Session Config

The main action handler builds this config before launching the REPL:

```
SessionConfig {
    tools: Tool[]
    commands: Command[]
    agentDefinitions: AgentDef[]
    mcpClients: MCPClient[]
    systemPrompt: string[]
    model: string
    effortLevel: 'low' | 'medium' | 'high'
    permissionMode: string
    sessionId: string
    initialMessages: Message[]
    pendingHookMessages: Message[]
    outputFormat: 'text' | 'json' | 'stream-json'
    budget: { maxTokens?, maxTurns?, maxCost? }
}
```

---

## Documentation

For in-depth guides, see the [`docs/`](docs/) directory:

| Guide | Description |
|-------|-------------|
| **[Architecture](docs/architecture.md)** | Core pipeline, startup sequence, state management, rendering, data flow |
| **[Tools Reference](docs/tools.md)** | Complete catalog of all ~40 agent tools with categories and permission model |
| **[Commands Reference](docs/commands.md)** | All ~85 slash commands organized by category |
| **[Subsystems Guide](docs/subsystems.md)** | Deep dives into Bridge, MCP, Permissions, Plugins, Skills, Tasks, Memory, Voice |
| **[Exploration Guide](docs/exploration-guide.md)** | How to navigate the codebase — study paths, grep patterns, key files |

Also see: [CONTRIBUTING.md](CONTRIBUTING.md) · [MCP Server README](mcp-server/README.md)

---

## Explore with MCP Server

This repo ships an [MCP server](https://modelcontextprotocol.io/) that lets any MCP-compatible client (Claude Code, Claude Desktop, VS Code Copilot, Cursor) explore the full source interactively.

### Install from npm

The MCP server is published as [`claude-code-explorer-mcp`](https://www.npmjs.com/package/claude-code-explorer-mcp) on npm — no need to clone the repo:

```bash
# Claude Code
claude mcp add claude-code-explorer -- npx -y claude-code-explorer-mcp
```

### One-liner setup (from source)

```bash
git clone https://github.com/nirholas/claude-code.git ~/claude-code \
  && cd ~/claude-code/mcp-server \
  && npm install && npm run build \
  && claude mcp add claude-code-explorer -- node ~/claude-code/mcp-server/dist/index.js
```

<details>
<summary><strong>Step-by-step setup</strong></summary>

```bash
# 1. Clone the repo
git clone https://github.com/nirholas/claude-code.git
cd claude-code/mcp-server

# 2. Install & build
npm install && npm run build

# 3. Register with Claude Code
claude mcp add claude-code-explorer -- node /absolute/path/to/claude-code/mcp-server/dist/index.js
```

Replace `/absolute/path/to/claude-code` with your actual clone path.

</details>

<details>
<summary><strong>VS Code / Cursor / Claude Desktop config</strong></summary>

**VS Code** — add to `.vscode/mcp.json`:
```json
{
  "servers": {
    "claude-code-explorer": {
      "type": "stdio",
      "command": "node",
      "args": ["${workspaceFolder}/mcp-server/dist/index.js"],
      "env": { "CLAUDE_CODE_SRC_ROOT": "${workspaceFolder}/src" }
    }
  }
}
```

**Claude Desktop** — add to your config file:
```json
{
  "mcpServers": {
    "claude-code-explorer": {
      "command": "node",
      "args": ["/absolute/path/to/claude-code/mcp-server/dist/index.js"],
      "env": { "CLAUDE_CODE_SRC_ROOT": "/absolute/path/to/claude-code/src" }
    }
  }
}
```

**Cursor** — add to `~/.cursor/mcp.json` (same format as Claude Desktop).

</details>

### Available tools & prompts

| Tool | Description |
|------|-------------|
| `list_tools` | List all ~40 agent tools with source files |
| `list_commands` | List all ~50 slash commands with source files |
| `get_tool_source` | Read full source of any tool (e.g. BashTool, FileEditTool) |
| `get_command_source` | Read source of any slash command (e.g. review, mcp) |
| `read_source_file` | Read any file from `src/` by path |
| `search_source` | Grep across the entire source tree |
| `list_directory` | Browse `src/` directories |
| `get_architecture` | High-level architecture overview |

| Prompt | Description |
|--------|-------------|
| `explain_tool` | Deep-dive into how a specific tool works |
| `explain_command` | Understand a slash command's implementation |
| `architecture_overview` | Guided tour of the full architecture |
| `how_does_it_work` | Explain any subsystem (permissions, MCP, bridge, etc.) |
| `compare_tools` | Side-by-side comparison of two tools |

**Try asking:** *"How does the BashTool work?"* · *"Search for where permissions are checked"* · *"Show me the /review command source"*

### Custom source path / Remove

```bash
# Custom source location
claude mcp add claude-code-explorer -e CLAUDE_CODE_SRC_ROOT=/path/to/src -- node /path/to/mcp-server/dist/index.js

# Remove
claude mcp remove claude-code-explorer
```

---

## Directory Structure

```
src/
├── main.tsx                 # Entrypoint — Commander.js CLI parser + React/Ink renderer
├── QueryEngine.ts           # Core LLM API caller (~46K lines)
├── Tool.ts                  # Tool type definitions (~29K lines)
├── commands.ts              # Command registry (~25K lines)
├── tools.ts                 # Tool registry
├── context.ts               # System/user context collection
├── cost-tracker.ts          # Token cost tracking
│
├── tools/                   # Agent tool implementations (~40)
├── commands/                # Slash command implementations (~50)
├── components/              # Ink UI components (~140)
├── services/                # External service integrations
├── hooks/                   # React hooks (incl. permission checks)
├── types/                   # TypeScript type definitions
├── utils/                   # Utility functions
├── screens/                 # Full-screen UIs (Doctor, REPL, Resume)
│
├── bridge/                  # IDE integration (VS Code, JetBrains)
├── coordinator/             # Multi-agent orchestration
├── plugins/                 # Plugin system
├── skills/                  # Skill system
├── server/                  # Server mode
├── remote/                  # Remote sessions
├── memdir/                  # Persistent memory directory
├── tasks/                   # Task management
├── state/                   # State management
│
├── voice/                   # Voice input
├── vim/                     # Vim mode
├── keybindings/             # Keybinding configuration
├── schemas/                 # Config schemas (Zod)
├── migrations/              # Config migrations
├── entrypoints/             # Initialization logic
├── query/                   # Query pipeline
├── ink/                     # Ink renderer wrapper
├── buddy/                   # Companion sprite (Easter egg)
├── native-ts/               # Native TypeScript utils
├── outputStyles/            # Output styling
└── upstreamproxy/           # Proxy configuration
```

---

## Architecture

### 1. Tool System

> `src/tools/` — Every tool Claude can invoke is a self-contained module with its own input schema, permission model, and execution logic.

| Tool | Description |
|---|---|
| **File I/O** | |
| `FileReadTool` | Read files (images, PDFs, notebooks) |
| `FileWriteTool` | Create / overwrite files |
| `FileEditTool` | Partial modification (string replacement) |
| `NotebookEditTool` | Jupyter notebook editing |
| **Search** | |
| `GlobTool` | File pattern matching |
| `GrepTool` | ripgrep-based content search |
| `WebSearchTool` | Web search |
| `WebFetchTool` | Fetch URL content |
| **Execution** | |
| `BashTool` | Shell command execution |
| `SkillTool` | Skill execution |
| `MCPTool` | MCP server tool invocation |
| `LSPTool` | Language Server Protocol integration |
| **Agents & Teams** | |
| `AgentTool` | Sub-agent spawning |
| `SendMessageTool` | Inter-agent messaging |
| `TeamCreateTool` / `TeamDeleteTool` | Team management |
| `TaskCreateTool` / `TaskUpdateTool` | Task management |
| **Mode & State** | |
| `EnterPlanModeTool` / `ExitPlanModeTool` | Plan mode toggle |
| `EnterWorktreeTool` / `ExitWorktreeTool` | Git worktree isolation |
| `ToolSearchTool` | Deferred tool discovery |
| `SleepTool` | Proactive mode wait |
| `CronCreateTool` | Scheduled triggers |
| `RemoteTriggerTool` | Remote trigger |
| `SyntheticOutputTool` | Structured output generation |

### 2. Command System

> `src/commands/` — User-facing slash commands invoked with `/` in the REPL.

| Command | Description | | Command | Description |
|---|---|---|---|---|
| `/commit` | Git commit | | `/memory` | Persistent memory |
| `/review` | Code review | | `/skills` | Skill management |
| `/compact` | Context compression | | `/tasks` | Task management |
| `/mcp` | MCP server management | | `/vim` | Vim mode toggle |
| `/config` | Settings | | `/diff` | View changes |
| `/doctor` | Environment diagnostics | | `/cost` | Check usage cost |
| `/login` / `/logout` | Auth | | `/theme` | Change theme |
| `/context` | Context visualization | | `/share` | Share session |
| `/pr_comments` | PR comments | | `/resume` | Restore session |
| `/desktop` | Desktop handoff | | `/mobile` | Mobile handoff |

### 3. Service Layer

> `src/services/` — External integrations and core infrastructure.

| Service | Description |
|---|---|
| `api/` | Anthropic API client, file API, bootstrap |
| `mcp/` | Model Context Protocol connection & management |
| `oauth/` | OAuth 2.0 authentication |
| `lsp/` | Language Server Protocol manager |
| `analytics/` | GrowthBook feature flags & analytics |
| `plugins/` | Plugin loader |
| `compact/` | Conversation context compression |
| `extractMemories/` | Automatic memory extraction |
| `teamMemorySync/` | Team memory synchronization |
| `tokenEstimation.ts` | Token count estimation |
| `policyLimits/` | Organization policy limits |
| `remoteManagedSettings/` | Remote managed settings |

### 4. Bridge System

> `src/bridge/` — Bidirectional communication layer connecting IDE extensions (VS Code, JetBrains) with the CLI.

Key files: `bridgeMain.ts` (main loop) · `bridgeMessaging.ts` (protocol) · `bridgePermissionCallbacks.ts` (permission callbacks) · `replBridge.ts` (REPL session) · `jwtUtils.ts` (JWT auth) · `sessionRunner.ts` (session execution)

### 5. Permission System

> `src/hooks/toolPermission/` — Checks permissions on every tool invocation.

Prompts the user for approval/denial or auto-resolves based on the configured permission mode: `default`, `plan`, `bypassPermissions`, `auto`, etc.

### 6. Feature Flags

Dead code elimination at build time via Bun's `bun:bundle`:

```typescript
import { feature } from 'bun:bundle'

const voiceCommand = feature('VOICE_MODE')
  ? require('./commands/voice/index.js').default
  : null
```

Notable flags: `PROACTIVE` · `KAIROS` · `BRIDGE_MODE` · `DAEMON` · `VOICE_MODE` · `AGENT_TRIGGERS` · `MONITOR_TOOL`

---

## Key Files

| File | Lines | Purpose |
|------|------:|---------|
| `QueryEngine.ts` | ~46K | Core LLM API engine — streaming, tool loops, thinking mode, retries, token counting |
| `Tool.ts` | ~29K | Base types/interfaces for all tools — input schemas, permissions, progress state |
| `commands.ts` | ~25K | Command registration & execution with conditional per-environment imports |
| `main.tsx` | — | CLI parser + React/Ink renderer; parallelizes MDM, keychain, and GrowthBook on startup |

---

## Tech Stack

| Category | Technology |
|---|---|
| Runtime | [Bun](https://bun.sh) |
| Language | TypeScript (strict) |
| Terminal UI | [React](https://react.dev) + [Ink](https://github.com/vadimdemedes/ink) |
| CLI Parsing | [Commander.js](https://github.com/tj/commander.js) (extra-typings) |
| Schema Validation | [Zod v4](https://zod.dev) |
| Code Search | [ripgrep](https://github.com/BurntSushi/ripgrep) (via GrepTool) |
| Protocols | [MCP SDK](https://modelcontextprotocol.io) · LSP |
| API | [Anthropic SDK](https://docs.anthropic.com) |
| Telemetry | OpenTelemetry + gRPC |
| Feature Flags | GrowthBook |
| Auth | OAuth 2.0 · JWT · macOS Keychain |

---

## Design Patterns

<details>
<summary><strong>Parallel Prefetch</strong> — Startup optimization</summary>

MDM settings, keychain reads, and API preconnect fire in parallel as side-effects before heavy module evaluation:

```typescript
// main.tsx
startMdmRawRead()
startKeychainPrefetch()
```

</details>

<details>
<summary><strong>Lazy Loading</strong> — Deferred heavy modules</summary>

OpenTelemetry (~400KB) and gRPC (~700KB) are loaded via dynamic `import()` only when needed.

</details>

<details>
<summary><strong>Agent Swarms</strong> — Multi-agent orchestration</summary>

Sub-agents spawn via `AgentTool`, with `coordinator/` handling orchestration. `TeamCreateTool` enables team-level parallel work.

</details>

<details>
<summary><strong>Skill System</strong> — Reusable workflows</summary>

Defined in `skills/` and executed through `SkillTool`. Users can add custom skills.

</details>

<details>
<summary><strong>Plugin Architecture</strong> — Extensibility</summary>

Built-in and third-party plugins loaded through the `plugins/` subsystem.

</details>

<details>
<summary><strong>Forked Subagent Pattern</strong> — Background processing</summary>

Compaction, session memory, and auto-dream run as forked processes via `runForkedAgent()`, preventing long-running background work from blocking the main conversation loop.

</details>

<details>
<summary><strong>Resolve-Once Guard</strong> — Async race safety</summary>

Permission flows use a `createResolveOnce()` pattern to prevent double-resolution when multiple async paths (user input, hooks, classifier) race to answer a permission prompt.

</details>

---

## GitPretty Setup

<details>
<summary>Show per-file emoji commit messages in GitHub's file UI</summary>

```bash
# Apply emoji commits
bash ./gitpretty-apply.sh .

# Optional: install hooks for future commits
bash ./gitpretty-apply.sh . --hooks

# Push as usual
git push origin main
```

</details>

---

## Contributing

Contributions to documentation, the MCP server, and exploration tooling are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

> **Note:** The `src/` directory is the original leaked source and should not be modified.

---

## Disclaimer

This repository archives source code leaked from Anthropic's npm registry on **2026-03-31**. All original source code is the property of [Anthropic](https://www.anthropic.com). This is not an official release and is not licensed for redistribution. Contact [nichxbt](https://www.x.com/nichxbt) for any comments.
