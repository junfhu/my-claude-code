# Claude Code — Python Rewrite

**Full Python rewrite of Anthropic's Claude Code CLI (originally TypeScript/Bun)**

---

## Overview

This is a complete Python port of the leaked Claude Code source code (~524K lines TypeScript → ~45K lines Python). The rewrite preserves the full architecture and functionality while using idiomatic Python libraries.

### Architecture Mapping

| TypeScript Original | Python Rewrite |
|---|---|
| Bun runtime | Python 3.11+ |
| React + Ink (terminal UI) | Rich + Textual |
| Commander.js (CLI) | Click |
| Zod (validation) | Pydantic v2 |
| Anthropic SDK (TS) | Anthropic SDK (Python) |
| MCP SDK (TS) | MCP SDK (Python) |
| node-pty | pexpect |
| chokidar (file watching) | watchdog |
| lodash-es | Python stdlib |
| ws (WebSocket) | websockets |
| axios/undici (HTTP) | httpx |
| fuse.js (fuzzy search) | rapidfuzz |
| highlight.js | pygments |

---

## Project Structure

```
python_rewrite/
├── pyproject.toml              # Project config, dependencies
├── README.md                   # This file
└── claude_code/                # Main package (328 files, ~45K lines)
    ├── __init__.py             # Package root
    ├── main.py                 # Main CLI orchestration
    ├── query_engine.py         # Core QueryEngine class
    ├── tool.py                 # Tool base class (ABC)
    ├── tools.py                # Tool registry
    ├── command_registry.py     # Command registry
    ├── cost_tracker.py         # Token cost tracking
    ├── history.py              # Prompt history
    ├── setup.py                # Session initialization
    │
    ├── types/                  # Type definitions (Pydantic models)
    │   ├── message.py          # Message types (15 system subtypes)
    │   ├── permissions.py      # Permission types
    │   ├── hooks.py            # Hook types
    │   ├── command.py          # Command types
    │   ├── plugin.py           # Plugin types
    │   ├── tools.py            # Tool progress types
    │   └── ids.py              # Branded ID types
    │
    ├── constants/              # Constants (13 modules)
    │   ├── api_limits.py       # API limits
    │   ├── oauth.py            # OAuth config
    │   ├── tools.py            # Tool names
    │   ├── prompts.py          # System prompt sections
    │   └── ...                 # files, figures, xml, keys, etc.
    │
    ├── state/                  # State management
    │   ├── store.py            # Reactive Store[T] class
    │   ├── app_state.py        # AppState dataclass (~80 fields)
    │   ├── selectors.py        # Derived state selectors
    │   └── on_change_app_state.py  # Side effects
    │
    ├── context/                # Context system
    │   ├── context.py          # Git status, CLAUDE.md, system context
    │   ├── notifications.py    # Notification manager
    │   └── mailbox.py          # Inter-component messaging
    │
    ├── query/                  # Query pipeline
    │   ├── query.py            # Main agentic loop (async generator)
    │   ├── config.py           # QueryConfig
    │   ├── transitions.py      # Loop state machine
    │   ├── token_budget.py     # Token budget tracking
    │   └── stop_hooks.py       # Loop termination hooks
    │
    ├── tools/                  # 55 tool implementations
    │   ├── bash_tool/          # Shell execution
    │   ├── file_read_tool/     # File reading
    │   ├── file_write_tool/    # File writing
    │   ├── file_edit_tool/     # String replacement editing
    │   ├── grep_tool/          # Regex search (ripgrep)
    │   ├── glob_tool/          # Glob pattern matching
    │   ├── agent_tool/         # Sub-agent spawning
    │   ├── web_fetch_tool/     # HTTP fetch
    │   ├── web_search_tool/    # Web search
    │   ├── notebook_edit_tool/ # Jupyter editing
    │   ├── mcp_tool/           # MCP wrapper
    │   ├── todo_write_tool/    # Todo management
    │   ├── task_tools/         # Task CRUD (6 tools)
    │   ├── team_tools/         # Team management
    │   └── ...                 # 40+ more tools
    │
    ├── commands/               # 35 slash commands
    │   ├── help/               # /help
    │   ├── compact/            # /compact
    │   ├── config/             # /config
    │   ├── cost/               # /cost
    │   ├── doctor/             # /doctor
    │   ├── commit/             # /commit
    │   ├── review/             # /review
    │   ├── diff/               # /diff
    │   ├── memory/             # /memory
    │   ├── mcp/                # /mcp
    │   ├── model/              # /model
    │   ├── permissions/        # /permissions
    │   └── ...                 # 23 more commands
    │
    ├── services/               # Service layer
    │   ├── api/                # Anthropic API client
    │   │   ├── client.py       # Client factory (Direct/Bedrock/Vertex/Azure)
    │   │   ├── errors.py       # Error classification
    │   │   ├── retry.py        # Retry with exponential backoff
    │   │   ├── logging.py      # API call logging
    │   │   ├── bootstrap.py    # Bootstrap data
    │   │   └── usage.py        # Rate limit tracking
    │   ├── mcp/                # MCP client/config
    │   │   ├── client.py       # MCP client
    │   │   ├── config.py       # Server configuration
    │   │   └── types.py        # MCP types
    │   ├── compact/            # Conversation compaction
    │   ├── analytics/          # Event logging
    │   ├── session_memory/     # Session memory
    │   ├── lsp/                # Language Server Protocol
    │   ├── oauth/              # OAuth flows
    │   └── notifier.py         # OS notifications
    │
    ├── screens/                # Full-screen UI
    │   ├── repl.py             # Main REPL (Textual App)
    │   ├── setup_screen.py     # Trust/setup dialog
    │   ├── transcript_screen.py # Transcript viewer
    │   └── config_screen.py    # Config editor
    │
    ├── components/             # UI components
    │   ├── message_display.py  # Message rendering (Rich)
    │   ├── tool_display.py     # Tool output rendering
    │   ├── prompt_input.py     # Input with history/completion
    │   ├── status_bar.py       # Status bar
    │   ├── spinner.py          # Loading spinners
    │   ├── permission_prompt.py # Permission dialogs
    │   └── sidebar.py          # Todo/tasks sidebar
    │
    ├── entrypoints/            # CLI entry points
    │   └── cli.py              # Click-based CLI
    │
    ├── bridge/                 # IDE integration
    │   ├── bridge_main.py
    │   ├── bridge_api.py
    │   ├── bridge_messaging.py
    │   └── types.py
    │
    ├── coordinator/            # Multi-agent orchestration
    ├── skills/                 # Skills system
    ├── plugins/                # Plugin system
    ├── tasks/                  # Background tasks
    ├── memdir/                 # Memory (CLAUDE.md)
    ├── hooks/                  # Permission/settings hooks
    ├── keybindings/            # 50+ keybindings, vim support
    ├── vim_mode/               # Full vim engine
    ├── migrations/             # Settings migrations
    ├── server/                 # HTTP/WS server
    ├── daemon/                 # Background daemon
    ├── ssh/                    # SSH tunnels
    ├── remote/                 # Remote execution
    ├── cli/                    # CLI utilities & transports
    ├── proactive/              # Proactive agent mode
    ├── jobs/                   # Background job manager
    ├── schemas/                # Hook schemas (Pydantic)
    ├── bootstrap/              # Session state
    ├── shims/                  # Feature flags
    ├── ink/                    # Ink compatibility layer
    ├── outputstyles/           # Theme system (5 themes)
    └── voice/                  # Voice I/O
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- ripgrep (`rg`) for GrepTool
- git

### Installation

```bash
cd python_rewrite

# Install with pip
pip install -e .

# Or with uv (recommended)
uv pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

### Running

```bash
# Interactive REPL
claude

# One-shot prompt (non-interactive)
claude -p "Explain this codebase"

# Specify model
claude --model claude-sonnet-4-20250514 "Refactor main.py"

# With API key
ANTHROPIC_API_KEY=sk-ant-... claude

# Headless JSON output
claude -p --output-format json "List all functions"

# Resume last session
claude --resume
```

### REPL Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/compact` | Compress context |
| `/cost` | Show token usage |
| `/config` | Edit settings |
| `/doctor` | Diagnostics |
| `/commit` | Git commit |
| `/review` | Code review |
| `/diff` | View changes |
| `/memory` | CLAUDE.md |
| `/model` | Switch model |
| `/theme` | Change theme |
| `/vim` | Toggle vim mode |
| `/exit` | Quit |

---

## Stats

| Metric | Value |
|---|---|
| Total Python files | 328 |
| Implementation files | 189 |
| Total lines of Python | ~45,000 |
| Tool implementations | 55 |
| Slash commands | 35 |
| UI components | 7 |
| Full-screen screens | 4 |
| Service modules | 22 |
| Keybinding actions | 50+ |
| Vim mode features | Full (normal/insert/visual/command) |

---

## Key Differences from TypeScript Original

1. **No React reconciler** — Uses Textual's native widget system instead of a custom terminal React renderer
2. **No Yoga layout** — Textual handles CSS-like layout natively
3. **Async-first** — Uses Python's `asyncio` throughout (vs Node.js event loop)
4. **Pydantic v2** — Replaces Zod with Pydantic for schema validation
5. **Click CLI** — Replaces Commander.js for argument parsing
6. **Rich rendering** — Markdown, syntax highlighting, tables via Rich library
7. **Feature flags** — Environment variable based (same as TS dev mode)

---

## License

UNLICENSED — This is a research/educational port of leaked source code.
