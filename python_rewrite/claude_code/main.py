"""
Main Claude Code CLI orchestration module.

Handles initialisation of auth, config, trust, telemetry, MCP servers,
tools, commands, permission modes, and session management. Dispatches
to either the interactive REPL (Textual) or headless / print mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("claude_code")

# ---------------------------------------------------------------------------
# Default system prompt (abbreviated – production would load from file)
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = """\
You are Claude Code, an interactive CLI tool that helps users with software \
engineering tasks. You have access to tools that let you read files, write \
files, execute commands, search code, and more. Always respond with clear, \
concise explanations of what you're doing.

<environment>
Working directory: {cwd}
Platform: {platform}
Date: {date}
</environment>
"""


# ---------------------------------------------------------------------------
# Configuration data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionConfig:
    """Fully-resolved configuration for a single Claude Code session."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    model: str = "claude-sonnet-4-20250514"
    permission_mode: str = "default"
    max_turns: int = 0  # 0 = unlimited
    max_budget: Optional[float] = None
    system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    add_dirs: List[str] = field(default_factory=list)
    verbose: bool = False
    debug: bool = False
    bare: bool = False
    vim: bool = False
    profile: Optional[str] = None
    # Resolved at runtime
    api_key: Optional[str] = None
    cwd: str = field(default_factory=os.getcwd)
    session_dir: Optional[str] = None
    telemetry_enabled: bool = True


@dataclass
class SessionState:
    """Mutable runtime state for the active session."""

    messages: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    is_streaming: bool = False
    interrupted: bool = False
    tool_permissions: Dict[str, str] = field(default_factory=dict)  # tool -> "allow" | "deny" | "always"
    git_branch: Optional[str] = None
    start_time: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


def build_system_prompt(
    override: Optional[str] = None,
    append: Optional[str] = None,
    cwd: Optional[str] = None,
) -> str:
    """Build the effective system prompt.

    Parameters
    ----------
    override:
        If provided, replaces the default system prompt entirely.
    append:
        If provided, appended to the base system prompt.
    cwd:
        Working directory for template expansion.

    Returns
    -------
    str
        The fully-resolved system prompt string.
    """
    import platform as _platform
    from datetime import datetime

    base = override if override else _DEFAULT_SYSTEM_PROMPT
    # Template substitution
    base = base.replace("{cwd}", cwd or os.getcwd())
    base = base.replace("{platform}", _platform.platform())
    base = base.replace("{date}", datetime.now().strftime("%Y-%m-%d"))

    if append:
        base = base.rstrip() + "\n\n" + append
    return base


# ---------------------------------------------------------------------------
# Config / Auth / Trust helpers
# ---------------------------------------------------------------------------


def _load_config(profile: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from ~/.claude/config.json (and optional profile overlay)."""
    config: Dict[str, Any] = {}
    config_path = Path.home() / ".claude" / "config.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text())
        except Exception as exc:
            logger.warning("Failed to load config: %s", exc)

    if profile:
        profile_path = Path.home() / ".claude" / "profiles" / f"{profile}.json"
        if profile_path.is_file():
            try:
                overlay = json.loads(profile_path.read_text())
                config.update(overlay)
            except Exception as exc:
                logger.warning("Failed to load profile %s: %s", profile, exc)
    return config


def _load_project_config(cwd: str) -> Dict[str, Any]:
    """Load project-level .claude/config.json from the workspace."""
    project_config_path = Path(cwd) / ".claude" / "config.json"
    if project_config_path.is_file():
        try:
            return json.loads(project_config_path.read_text())
        except Exception:
            pass
    return {}


def _check_trust(cwd: str) -> bool:
    """Return True if the current workspace is trusted."""
    trust_file = Path.home() / ".claude" / "trust.json"
    if not trust_file.is_file():
        return False
    try:
        trust_data = json.loads(trust_file.read_text())
        trusted_dirs = trust_data.get("trusted_directories", [])
        return any(cwd.startswith(d) for d in trusted_dirs)
    except Exception:
        return False


def _trust_directory(cwd: str) -> None:
    """Add *cwd* to the trusted-directories list."""
    trust_file = Path.home() / ".claude" / "trust.json"
    trust_data: Dict[str, Any] = {}
    if trust_file.is_file():
        try:
            trust_data = json.loads(trust_file.read_text())
        except Exception:
            pass
    dirs = set(trust_data.get("trusted_directories", []))
    dirs.add(cwd)
    trust_data["trusted_directories"] = sorted(dirs)
    trust_file.parent.mkdir(parents=True, exist_ok=True)
    trust_file.write_text(json.dumps(trust_data, indent=2))


def _validate_api_key(key: Optional[str]) -> bool:
    """Quick-check that *key* looks like a valid Anthropic API key."""
    if not key:
        return False
    return key.startswith("sk-ant-") or key.startswith("sk-") or len(key) > 20


def _detect_git_branch(cwd: str) -> Optional[str]:
    """Return the current git branch (or None)."""
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


def _session_dir(session_id: str) -> Path:
    """Return the directory where a session's data is persisted."""
    d = Path.home() / ".claude" / "sessions" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_session(session_dir: Path, config: SessionConfig, state: SessionState) -> None:
    """Persist session state to disk."""
    data = {
        "session_id": config.session_id,
        "model": config.model,
        "messages": state.messages,
        "turn_count": state.turn_count,
        "total_input_tokens": state.total_input_tokens,
        "total_output_tokens": state.total_output_tokens,
        "total_cost_usd": state.total_cost_usd,
        "start_time": state.start_time,
        "cwd": config.cwd,
    }
    (session_dir / "session.json").write_text(json.dumps(data, indent=2, default=str))


def _load_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously-saved session."""
    p = Path.home() / ".claude" / "sessions" / session_id / "session.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _find_last_session() -> Optional[str]:
    """Return the session_id of the most recent session, or None."""
    sessions_root = Path.home() / ".claude" / "sessions"
    if not sessions_root.is_dir():
        return None
    # Sort by modification time, most-recent first
    candidates = sorted(
        sessions_root.iterdir(),
        key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
        reverse=True,
    )
    for d in candidates:
        if (d / "session.json").is_file():
            return d.name
    return None


# ---------------------------------------------------------------------------
# Telemetry (stub)
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """Lightweight telemetry collector (sends events to Anthropic if opted-in)."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and os.environ.get("CLAUDE_CODE_NO_TELEMETRY") != "1"
        self._events: List[Dict[str, Any]] = []

    def track(self, event_name: str, properties: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        self._events.append(
            {
                "event": event_name,
                "properties": properties or {},
                "timestamp": time.time(),
            }
        )

    async def flush(self) -> None:
        """Flush events (no-op in open-source build)."""
        self._events.clear()


# ---------------------------------------------------------------------------
# Tool / Command / MCP loader stubs
# ---------------------------------------------------------------------------


def _load_tools(config: SessionConfig) -> Dict[str, Any]:
    """Discover and return the set of available tools."""
    tools: Dict[str, Any] = {}
    # Core built-in tools
    builtin_tools = [
        "bash",
        "file_read",
        "file_write",
        "file_edit",
        "glob",
        "grep",
        "web_fetch",
        "web_search",
        "notebook_edit",
        "agent",
        "task",
        "todo_write",
        "mcp",
    ]
    for name in builtin_tools:
        tools[name] = {"name": name, "type": "builtin", "enabled": True}
    return tools


def _load_slash_commands() -> Dict[str, Any]:
    """Return the map of available slash commands."""
    commands: Dict[str, Any] = {}
    command_defs = [
        ("help", "Show help information"),
        ("clear", "Clear the conversation"),
        ("compact", "Compact conversation history"),
        ("config", "Open configuration editor"),
        ("cost", "Show token usage and cost"),
        ("diff", "Show git diff"),
        ("doctor", "Diagnose configuration issues"),
        ("exit", "Exit Claude Code"),
        ("init", "Initialize project settings"),
        ("login", "Authenticate with Anthropic"),
        ("logout", "Remove stored credentials"),
        ("model", "Change the active model"),
        ("memory", "Manage CLAUDE.md memory files"),
        ("permissions", "Manage tool permissions"),
        ("resume", "Resume a previous session"),
        ("review", "Request a code review"),
        ("status", "Show session status"),
        ("vim", "Toggle vim mode"),
        ("bug", "Report a bug"),
        ("theme", "Change color theme"),
        ("add-dir", "Add a directory to context"),
    ]
    for name, description in command_defs:
        commands[name] = {"name": name, "description": description}
    return commands


async def _init_mcp_servers(config: SessionConfig) -> Dict[str, Any]:
    """Start configured MCP servers and return their tool registrations."""
    mcp_config_path = Path.home() / ".claude" / "mcp.json"
    servers: Dict[str, Any] = {}
    if not mcp_config_path.is_file():
        return servers
    try:
        mcp_data = json.loads(mcp_config_path.read_text())
        for name, server_cfg in mcp_data.get("servers", {}).items():
            servers[name] = {
                "name": name,
                "status": "configured",
                "tools": [],
                "config": server_cfg,
            }
            logger.info("MCP server configured: %s", name)
    except Exception as exc:
        logger.warning("Failed to load MCP config: %s", exc)
    return servers


# ---------------------------------------------------------------------------
# Headless / print mode runner
# ---------------------------------------------------------------------------


async def _run_headless(
    prompt: str,
    config: SessionConfig,
    state: SessionState,
    output_format: str,
    telemetry: TelemetryCollector,
) -> None:
    """Run a single prompt in headless (non-interactive) mode and print the result."""
    from rich.console import Console

    console = Console(stderr=True)
    out_console = Console()

    with console.status("[bold cyan]Thinking...", spinner="dots"):
        # Placeholder: in production this calls the Anthropic API
        # For now, create a mock response structure
        state.messages.append({"role": "user", "content": prompt})

        # --- API call would go here ---
        assistant_text = f"[Headless mode] Received prompt: {prompt!r}"
        state.messages.append({"role": "assistant", "content": assistant_text})
        state.turn_count += 1

    if output_format == "json":
        result = {
            "role": "assistant",
            "content": assistant_text,
            "model": config.model,
            "usage": {
                "input_tokens": state.total_input_tokens,
                "output_tokens": state.total_output_tokens,
            },
        }
        out_console.print_json(json.dumps(result))
    elif output_format == "stream-json":
        for msg in state.messages:
            out_console.print_json(json.dumps(msg))
    else:
        out_console.print(assistant_text)

    telemetry.track("headless_query", {"turns": state.turn_count})


# ---------------------------------------------------------------------------
# Interactive REPL launcher
# ---------------------------------------------------------------------------


async def _run_interactive(
    config: SessionConfig,
    state: SessionState,
    tools: Dict[str, Any],
    commands: Dict[str, Any],
    mcp_servers: Dict[str, Any],
    telemetry: TelemetryCollector,
    initial_prompt: Optional[str] = None,
) -> None:
    """Launch the Textual-based interactive REPL."""
    from claude_code.screens.repl import ClaudeCodeApp

    app = ClaudeCodeApp(
        config=config,
        state=state,
        tools=tools,
        commands=commands,
        mcp_servers=mcp_servers,
        telemetry=telemetry,
        initial_prompt=initial_prompt,
    )
    await app.run_async()


# ---------------------------------------------------------------------------
# Setup screen (first-run / untrusted directory)
# ---------------------------------------------------------------------------


async def _run_setup(cwd: str) -> bool:
    """Show the setup / trust screen. Returns True if the user chose to trust."""
    from claude_code.screens.setup_screen import SetupScreen

    screen = SetupScreen(cwd=cwd)
    result = await screen.run_async()
    return getattr(screen, "trusted", False)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run(
    *,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    print_mode: bool = False,
    output_format: str = "text",
    resume: bool = False,
    resume_id: Optional[str] = None,
    permission_mode: Optional[str] = None,
    verbose: bool = False,
    debug: bool = False,
    max_turns: int = 0,
    system_prompt: Optional[str] = None,
    append_system_prompt: Optional[str] = None,
    add_dirs: Optional[List[str]] = None,
    bare: bool = False,
    max_budget: Optional[float] = None,
    profile: Optional[str] = None,
    vim: bool = False,
    boot_time: Optional[float] = None,
) -> None:
    """
    Main entry point for Claude Code.

    Called by the CLI entrypoint after argument parsing. Orchestrates the full
    lifecycle: config loading → auth → trust check → tool discovery → session
    management → REPL or headless dispatch.
    """
    # ------------------------------------------------------------------
    # 1. Logging
    # ------------------------------------------------------------------
    log_level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if boot_time:
        logger.debug("Boot → run(): %.1f ms", (time.monotonic() - boot_time) * 1000)

    # ------------------------------------------------------------------
    # 2. Load config
    # ------------------------------------------------------------------
    user_config = _load_config(profile)
    cwd = os.getcwd()
    project_config = _load_project_config(cwd)

    # Merge configs: CLI flags > project > user > defaults
    effective_model = model or project_config.get("model") or user_config.get("model") or "claude-sonnet-4-20250514"
    effective_permission = (
        permission_mode
        or project_config.get("permission_mode")
        or user_config.get("permission_mode")
        or "default"
    )

    config = SessionConfig(
        model=effective_model,
        permission_mode=effective_permission,
        max_turns=max_turns,
        max_budget=max_budget,
        system_prompt=system_prompt,
        append_system_prompt=append_system_prompt,
        add_dirs=add_dirs or [],
        verbose=verbose,
        debug=debug,
        bare=bare,
        vim=vim or user_config.get("vim_mode", False),
        profile=profile,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        cwd=cwd,
        telemetry_enabled=os.environ.get("CLAUDE_CODE_NO_TELEMETRY") != "1",
    )

    # ------------------------------------------------------------------
    # 3. Validate API key
    # ------------------------------------------------------------------
    if not _validate_api_key(config.api_key):
        if print_mode:
            import sys

            print(
                "Error: No valid API key found. Set ANTHROPIC_API_KEY or run `claude login`.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        # Interactive mode will show the setup/login screen

    # ------------------------------------------------------------------
    # 4. Trust check (interactive only)
    # ------------------------------------------------------------------
    if not print_mode and not bare:
        if not _check_trust(cwd):
            trusted = await _run_setup(cwd)
            if not trusted:
                logger.info("User declined trust — exiting.")
                return
            _trust_directory(cwd)

    # ------------------------------------------------------------------
    # 5. Session resume
    # ------------------------------------------------------------------
    state = SessionState()
    state.git_branch = _detect_git_branch(cwd)

    if resume or resume_id:
        sid = resume_id or _find_last_session()
        if sid:
            saved = _load_session(sid)
            if saved:
                config.session_id = sid
                state.messages = saved.get("messages", [])
                state.turn_count = saved.get("turn_count", 0)
                state.total_input_tokens = saved.get("total_input_tokens", 0)
                state.total_output_tokens = saved.get("total_output_tokens", 0)
                state.total_cost_usd = saved.get("total_cost_usd", 0.0)
                state.start_time = saved.get("start_time", time.time())
                logger.info("Resumed session %s (%d messages)", sid, len(state.messages))
            else:
                logger.warning("Session %s not found — starting fresh.", sid)
        else:
            logger.warning("No previous session found — starting fresh.")

    config.session_dir = str(_session_dir(config.session_id))

    # ------------------------------------------------------------------
    # 6. Telemetry
    # ------------------------------------------------------------------
    telemetry = TelemetryCollector(enabled=config.telemetry_enabled)
    telemetry.track("session_start", {"model": config.model, "mode": "headless" if print_mode else "interactive"})

    # ------------------------------------------------------------------
    # 7. Load tools, commands, MCP servers
    # ------------------------------------------------------------------
    tools = _load_tools(config)
    commands = _load_slash_commands()
    mcp_servers = await _init_mcp_servers(config)

    logger.info(
        "Session %s: model=%s, tools=%d, commands=%d, mcp=%d",
        config.session_id,
        config.model,
        len(tools),
        len(commands),
        len(mcp_servers),
    )

    # ------------------------------------------------------------------
    # 8. Dispatch
    # ------------------------------------------------------------------
    try:
        if print_mode:
            if not prompt:
                import sys

                print("Error: --print mode requires a prompt.", file=sys.stderr)
                raise SystemExit(1)
            await _run_headless(prompt, config, state, output_format, telemetry)
        else:
            await _run_interactive(
                config=config,
                state=state,
                tools=tools,
                commands=commands,
                mcp_servers=mcp_servers,
                telemetry=telemetry,
                initial_prompt=prompt,
            )
    finally:
        # ------------------------------------------------------------------
        # 9. Cleanup / persist
        # ------------------------------------------------------------------
        _save_session(Path(config.session_dir), config, state)
        telemetry.track(
            "session_end",
            {
                "turns": state.turn_count,
                "input_tokens": state.total_input_tokens,
                "output_tokens": state.total_output_tokens,
                "cost_usd": state.total_cost_usd,
                "duration_s": time.time() - state.start_time,
            },
        )
        await telemetry.flush()
        logger.info("Session %s ended. %d turns, $%.4f", config.session_id, state.turn_count, state.total_cost_usd)
