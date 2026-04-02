"""
Main REPL screen using Textual.

This is the primary interactive interface for Claude Code. It manages the
chat log, user input, tool execution feedback, permission prompts, and
the overall conversation lifecycle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog, Static

from claude_code.components.message_display import MessageRenderer
from claude_code.components.permission_prompt import PermissionPromptWidget
from claude_code.components.prompt_input import PromptInput
from claude_code.components.sidebar import Sidebar
from claude_code.components.spinner import ThinkingSpinner
from claude_code.components.status_bar import StatusBar
from claude_code.components.tool_display import ToolRenderer

logger = logging.getLogger("claude_code.repl")


# ---------------------------------------------------------------------------
# Custom messages
# ---------------------------------------------------------------------------


class AssistantChunk(Message):
    """Fired when a chunk of assistant text arrives from the stream."""

    def __init__(self, text: str, done: bool = False) -> None:
        super().__init__()
        self.text = text
        self.done = done


class ToolUseStart(Message):
    """Fired when the assistant invokes a tool."""

    def __init__(self, tool_id: str, tool_name: str, tool_input: Dict[str, Any]) -> None:
        super().__init__()
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_input = tool_input


class ToolResult(Message):
    """Fired when a tool execution completes."""

    def __init__(self, tool_id: str, tool_name: str, result: Any, is_error: bool = False) -> None:
        super().__init__()
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.result = result
        self.is_error = is_error


class PermissionRequired(Message):
    """Fired when a tool requires user permission before executing."""

    def __init__(self, tool_id: str, tool_name: str, tool_input: Dict[str, Any], risk_level: str = "medium") -> None:
        super().__init__()
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.risk_level = risk_level


class PermissionDecision(Message):
    """Fired when the user responds to a permission prompt."""

    def __init__(self, tool_id: str, decision: str) -> None:
        super().__init__()
        self.tool_id = tool_id
        self.decision = decision  # "allow" | "deny" | "always_allow"


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class ClaudeCodeApp(App):
    """The main Claude Code terminal application."""

    TITLE = "Claude Code"
    SUB_TITLE = "AI coding assistant"

    CSS = """
    Screen {
        layout: horizontal;
    }

    #main-container {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }

    #chat-log {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
        scrollbar-size: 1 1;
    }

    #thinking-container {
        height: auto;
        max-height: 3;
        padding: 0 1;
        display: none;
    }

    #thinking-container.visible {
        display: block;
    }

    #permission-container {
        height: auto;
        padding: 0 1;
        display: none;
    }

    #permission-container.visible {
        display: block;
    }

    #input-area {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 12;
        padding: 0 1;
    }

    #status-bar-container {
        dock: bottom;
        height: 1;
    }

    #sidebar {
        width: 32;
        display: none;
        border-left: solid $accent;
    }

    #sidebar.visible {
        display: block;
    }

    .user-message {
        margin: 1 0 0 0;
        padding: 0 1;
    }

    .assistant-message {
        margin: 0 0 1 0;
        padding: 0 1;
    }

    .system-message {
        color: $text-muted;
        margin: 0;
        padding: 0 1;
    }

    .tool-message {
        margin: 0;
        padding: 0 1 0 3;
    }

    .error-message {
        color: $error;
        margin: 0;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=True, priority=True),
        Binding("ctrl+d", "quit", "Quit", show=True),
        Binding("escape", "escape", "Cancel", show=False),
        Binding("ctrl+l", "clear_screen", "Clear", show=True),
        Binding("ctrl+k", "compact", "Compact", show=False),
        Binding("ctrl+t", "toggle_sidebar", "Sidebar", show=True),
        Binding("ctrl+r", "toggle_transcript", "Transcript", show=False),
        Binding("f1", "show_help", "Help", show=True),
    ]

    # Reactive state
    is_thinking: reactive[bool] = reactive(False)
    sidebar_visible: reactive[bool] = reactive(False)
    current_turn: reactive[int] = reactive(0)

    def __init__(
        self,
        config: Any = None,
        state: Any = None,
        tools: Optional[Dict[str, Any]] = None,
        commands: Optional[Dict[str, Any]] = None,
        mcp_servers: Optional[Dict[str, Any]] = None,
        telemetry: Any = None,
        initial_prompt: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.state = state
        self.tools = tools or {}
        self.commands = commands or {}
        self.mcp_servers = mcp_servers or {}
        self.telemetry = telemetry
        self.initial_prompt = initial_prompt
        self.message_renderer = MessageRenderer()
        self.tool_renderer = ToolRenderer()
        self._pending_permissions: Dict[str, asyncio.Future] = {}
        self._stream_buffer: str = ""
        self._current_stream_widget: Optional[Static] = None

    def compose(self) -> ComposeResult:
        """Build the main UI layout."""
        yield Header(show_clock=True)

        with Horizontal():
            with Vertical(id="main-container"):
                yield RichLog(
                    id="chat-log",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    min_width=40,
                )
                yield Container(
                    ThinkingSpinner(),
                    id="thinking-container",
                )
                yield Container(id="permission-container")
                yield StatusBar(
                    id="status-bar-container",
                    model=getattr(self.config, "model", "unknown"),
                    permission_mode=getattr(self.config, "permission_mode", "default"),
                )
                yield PromptInput(
                    id="input-area",
                    commands=self.commands,
                    vim_mode=getattr(self.config, "vim", False),
                )

            yield Sidebar(id="sidebar")

        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted — show welcome and process initial prompt."""
        chat_log = self.query_one("#chat-log", RichLog)

        # Welcome banner
        if not getattr(self.config, "bare", False):
            self._write_welcome(chat_log)

        # Restore previous messages if resuming
        if self.state and self.state.messages:
            for msg in self.state.messages:
                self._render_message(chat_log, msg)

        # Focus the input
        try:
            self.query_one("#input-area", PromptInput).focus()
        except NoMatches:
            pass

        # Process initial prompt if provided
        if self.initial_prompt:
            await self.handle_query(self.initial_prompt)

    def _write_welcome(self, chat_log: RichLog) -> None:
        """Write the welcome banner to the chat log."""
        model = getattr(self.config, "model", "claude-sonnet-4-20250514")
        perm = getattr(self.config, "permission_mode", "default")
        branch = getattr(self.state, "git_branch", None) if self.state else None

        welcome_lines = [
            f"[bold cyan]╭─ Claude Code[/bold cyan]",
            f"[bold cyan]│[/bold cyan]  Model: [green]{model}[/green]",
            f"[bold cyan]│[/bold cyan]  Permissions: [yellow]{perm}[/yellow]",
        ]
        if branch:
            welcome_lines.append(f"[bold cyan]│[/bold cyan]  Branch: [magenta]{branch}[/magenta]")
        welcome_lines.append(f"[bold cyan]╰─[/bold cyan] Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to quit")

        for line in welcome_lines:
            chat_log.write(Text.from_markup(line))
        chat_log.write("")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    @on(PromptInput.Submitted)
    async def on_prompt_submitted(self, event: PromptInput.Submitted) -> None:
        """Handle user input submission."""
        text = event.value.strip()
        if not text:
            return

        # Slash commands
        if text.startswith("/"):
            await self._handle_slash_command(text)
            return

        # Regular query
        await self.handle_query(text)

    async def _handle_slash_command(self, text: str) -> None:
        """Process a slash command."""
        chat_log = self.query_one("#chat-log", RichLog)
        parts = text[1:].split(None, 1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_name == "help":
            self._render_help(chat_log)
        elif cmd_name == "clear":
            chat_log.clear()
            if self.state:
                self.state.messages.clear()
                self.state.turn_count = 0
        elif cmd_name == "compact":
            self._render_system(chat_log, "Compacting conversation history...")
            if self.state:
                # Keep only the last 10 messages
                if len(self.state.messages) > 10:
                    self.state.messages = self.state.messages[-10:]
                    self._render_system(chat_log, f"Compacted to {len(self.state.messages)} messages.")
                else:
                    self._render_system(chat_log, "Nothing to compact.")
        elif cmd_name == "cost":
            self._render_cost(chat_log)
        elif cmd_name == "exit" or cmd_name == "quit":
            self.exit()
        elif cmd_name == "model":
            if cmd_args and self.config:
                self.config.model = cmd_args
                self._render_system(chat_log, f"Model changed to: {cmd_args}")
                try:
                    self.query_one("#status-bar-container", StatusBar).model = cmd_args
                except NoMatches:
                    pass
            else:
                model = getattr(self.config, "model", "unknown")
                self._render_system(chat_log, f"Current model: {model}")
        elif cmd_name == "status":
            self._render_status(chat_log)
        elif cmd_name == "diff":
            await self._show_git_diff(chat_log)
        elif cmd_name == "config":
            self.push_screen("config")
        elif cmd_name == "vim":
            try:
                prompt_input = self.query_one("#input-area", PromptInput)
                prompt_input.toggle_vim_mode()
                mode = "enabled" if prompt_input.vim_mode else "disabled"
                self._render_system(chat_log, f"Vim mode {mode}.")
            except NoMatches:
                pass
        elif cmd_name == "memory":
            self._render_system(chat_log, "Memory management: TODO")
        elif cmd_name == "permissions":
            self._render_permissions(chat_log)
        elif cmd_name in self.commands:
            self._render_system(chat_log, f"Command /{cmd_name}: not yet implemented")
        else:
            self._render_system(chat_log, f"Unknown command: /{cmd_name}. Type /help for a list.")

    async def handle_query(self, prompt: str) -> None:
        """Send a user query to the assistant and stream the response."""
        chat_log = self.query_one("#chat-log", RichLog)

        # Render user message
        self.message_renderer.render_user(chat_log, prompt)

        # Add to state
        if self.state:
            self.state.messages.append({"role": "user", "content": prompt})

        # Start thinking indicator
        self.is_thinking = True
        self._show_thinking(True)

        # Disable input during response
        try:
            prompt_input = self.query_one("#input-area", PromptInput)
            prompt_input.disabled = True
        except NoMatches:
            prompt_input = None

        try:
            await self._stream_response(chat_log, prompt)
        except asyncio.CancelledError:
            self._render_system(chat_log, "[Interrupted]")
        except Exception as exc:
            logger.exception("Error during query")
            chat_log.write(
                Text.from_markup(f"[bold red]Error:[/bold red] {exc}")
            )
        finally:
            self.is_thinking = False
            self._show_thinking(False)
            if prompt_input:
                prompt_input.disabled = False
                prompt_input.focus()

    @work(exclusive=True, group="stream")
    async def _stream_response(self, chat_log: RichLog, prompt: str) -> None:
        """Stream the assistant response.

        In production this would call the Anthropic Messages API with
        streaming enabled. Here we provide a realistic simulation that
        exercises all the UI code paths.
        """
        if self.state:
            self.state.turn_count += 1
            self.current_turn = self.state.turn_count

        # Build messages for API call
        messages = []
        if self.state:
            messages = list(self.state.messages)

        # --- Simulated streaming response ---
        # In production: async for event in client.messages.stream(...)
        assistant_text = self._generate_placeholder_response(prompt)

        # Simulate chunked streaming
        self._stream_buffer = ""
        self._current_stream_widget = Static("", classes="assistant-message")
        chat_log.write(Text(""))  # spacer

        chunks = [assistant_text[i:i + 20] for i in range(0, len(assistant_text), 20)]
        for i, chunk in enumerate(chunks):
            if self.state and self.state.interrupted:
                self.state.interrupted = False
                break
            self._stream_buffer += chunk
            # Update rendered markdown
            self.message_renderer.render_assistant_streaming(
                chat_log, self._stream_buffer, done=(i == len(chunks) - 1)
            )
            await asyncio.sleep(0.02)  # Simulate network latency

        # Finalize
        full_response = self._stream_buffer
        self._stream_buffer = ""
        self._current_stream_widget = None

        if self.state:
            self.state.messages.append({"role": "assistant", "content": full_response})
            # Simulate token counting
            self.state.total_input_tokens += len(prompt.split()) * 2
            self.state.total_output_tokens += len(full_response.split()) * 2
            self.state.total_cost_usd += (self.state.total_input_tokens * 0.000003 +
                                           self.state.total_output_tokens * 0.000015)

        # Update status bar
        self._update_status_bar()

    def _generate_placeholder_response(self, prompt: str) -> str:
        """Generate a placeholder response (replaced by real API in production)."""
        return (
            f"I received your message. In production, this would be a real response "
            f"from the Claude API to: *{prompt[:80]}*\n\n"
            f"The streaming UI, tool execution, and permission system are all "
            f"wired up and ready for the API integration."
        )

    # ------------------------------------------------------------------
    # Tool execution flow
    # ------------------------------------------------------------------

    async def execute_tool(
        self,
        tool_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Any:
        """Execute a tool, handling permissions as needed."""
        chat_log = self.query_one("#chat-log", RichLog)

        # Check permission mode
        needs_permission = self._tool_needs_permission(tool_name)

        if needs_permission:
            decision = await self._request_permission(tool_id, tool_name, tool_input)
            if decision == "deny":
                result = {"error": "Permission denied by user"}
                self.tool_renderer.render_result(chat_log, tool_name, result, is_error=True)
                return result

        # Render tool use
        self.tool_renderer.render_use(chat_log, tool_name, tool_input)

        # Execute
        try:
            result = await self._run_tool(tool_name, tool_input)
            self.tool_renderer.render_result(chat_log, tool_name, result)
            return result
        except Exception as exc:
            error_result = {"error": str(exc)}
            self.tool_renderer.render_result(chat_log, tool_name, error_result, is_error=True)
            return error_result

    def _tool_needs_permission(self, tool_name: str) -> bool:
        """Check if a tool requires explicit user permission."""
        perm_mode = getattr(self.config, "permission_mode", "default")
        if perm_mode == "full-auto":
            return False
        if perm_mode == "auto-edit":
            return tool_name in ("bash",)  # Only bash needs permission
        # Default and plan modes require permission for write operations
        write_tools = {"bash", "file_write", "file_edit", "notebook_edit"}
        if self.state:
            always_allowed = {
                k for k, v in self.state.tool_permissions.items() if v == "always"
            }
            if tool_name in always_allowed:
                return False
        return tool_name in write_tools

    async def _request_permission(
        self,
        tool_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> str:
        """Show a permission prompt and wait for the user's decision."""
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_permissions[tool_id] = future

        # Show the permission widget
        try:
            container = self.query_one("#permission-container")
            widget = PermissionPromptWidget(
                tool_id=tool_id,
                tool_name=tool_name,
                tool_input=tool_input,
                risk_level=self._assess_risk(tool_name, tool_input),
            )
            await container.mount(widget)
            container.add_class("visible")
        except NoMatches:
            return "allow"  # Fallback

        try:
            decision = await future
        finally:
            # Clean up
            try:
                container = self.query_one("#permission-container")
                container.remove_class("visible")
                await container.remove_children()
            except NoMatches:
                pass
            self._pending_permissions.pop(tool_id, None)

        # Remember "always allow"
        if decision == "always_allow" and self.state:
            self.state.tool_permissions[tool_name] = "always"
            decision = "allow"

        return decision

    def _assess_risk(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Assess the risk level of a tool invocation."""
        if tool_name == "bash":
            cmd = tool_input.get("command", "")
            dangerous = ["rm ", "sudo ", "chmod ", "chown ", "mkfs", "dd ", "> /dev/"]
            if any(d in cmd for d in dangerous):
                return "high"
            return "medium"
        if tool_name in ("file_write", "file_edit"):
            return "medium"
        return "low"

    async def _run_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Actually execute a tool. Stub — real implementation calls tool modules."""
        # Placeholder: in production, dispatch to the tool registry
        return {"status": "ok", "output": f"[Tool {tool_name} executed successfully]"}

    @on(PermissionDecision)
    def on_permission_decision(self, event: PermissionDecision) -> None:
        """Handle a permission decision from the PermissionPromptWidget."""
        future = self._pending_permissions.get(event.tool_id)
        if future and not future.done():
            future.set_result(event.decision)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_message(self, chat_log: RichLog, msg: Dict[str, Any]) -> None:
        """Render a stored message to the chat log."""
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            self.message_renderer.render_user(chat_log, content)
        elif role == "assistant":
            self.message_renderer.render_assistant(chat_log, content)
        elif role == "system":
            self.message_renderer.render_system(chat_log, content)

    def _render_system(self, chat_log: RichLog, text: str) -> None:
        """Render a system/info message."""
        self.message_renderer.render_system(chat_log, text)

    def _render_help(self, chat_log: RichLog) -> None:
        """Render the help text."""
        help_lines = [
            "[bold]Available Commands:[/bold]",
            "",
        ]
        for name, cmd in sorted(self.commands.items()):
            desc = cmd.get("description", "")
            help_lines.append(f"  [cyan]/{name:<15}[/cyan] {desc}")
        help_lines.extend([
            "",
            "[bold]Keybindings:[/bold]",
            "  [cyan]Ctrl+C[/cyan]         Interrupt current operation",
            "  [cyan]Ctrl+D[/cyan]         Quit",
            "  [cyan]Ctrl+L[/cyan]         Clear screen",
            "  [cyan]Ctrl+T[/cyan]         Toggle sidebar",
            "  [cyan]Up/Down[/cyan]        Navigate input history",
            "  [cyan]Tab[/cyan]            Complete commands",
            "  [cyan]F1[/cyan]             This help",
        ])
        for line in help_lines:
            chat_log.write(Text.from_markup(line))

    def _render_cost(self, chat_log: RichLog) -> None:
        """Render cost/usage information."""
        if not self.state:
            return
        lines = [
            "[bold]Session Usage:[/bold]",
            f"  Turns:         {self.state.turn_count}",
            f"  Input tokens:  {self.state.total_input_tokens:,}",
            f"  Output tokens: {self.state.total_output_tokens:,}",
            f"  Total cost:    ${self.state.total_cost_usd:.4f}",
        ]
        if getattr(self.config, "max_budget", None):
            remaining = self.config.max_budget - self.state.total_cost_usd
            lines.append(f"  Budget left:   ${remaining:.4f}")
        for line in lines:
            chat_log.write(Text.from_markup(line))

    def _render_status(self, chat_log: RichLog) -> None:
        """Render session status."""
        if not self.config or not self.state:
            return
        lines = [
            "[bold]Session Status:[/bold]",
            f"  Session ID:    {self.config.session_id}",
            f"  Model:         {self.config.model}",
            f"  Permission:    {self.config.permission_mode}",
            f"  Messages:      {len(self.state.messages)}",
            f"  Turns:         {self.state.turn_count}",
            f"  Git branch:    {self.state.git_branch or 'N/A'}",
            f"  Vim mode:      {'on' if self.config.vim else 'off'}",
        ]
        for line in lines:
            chat_log.write(Text.from_markup(line))

    def _render_permissions(self, chat_log: RichLog) -> None:
        """Render current tool permission state."""
        if not self.state:
            return
        chat_log.write(Text.from_markup("[bold]Tool Permissions:[/bold]"))
        if not self.state.tool_permissions:
            chat_log.write(Text.from_markup("  No custom permissions set."))
        else:
            for tool, perm in sorted(self.state.tool_permissions.items()):
                chat_log.write(Text.from_markup(f"  [cyan]{tool:<20}[/cyan] {perm}"))

    async def _show_git_diff(self, chat_log: RichLog) -> None:
        """Show git diff in the chat log."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True,
                text=True,
                cwd=getattr(self.config, "cwd", "."),
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                chat_log.write(Text.from_markup("[bold]Git Diff (stat):[/bold]"))
                chat_log.write(Syntax(result.stdout, "diff", theme="monokai"))
            else:
                chat_log.write(Text.from_markup("[dim]No changes detected.[/dim]"))
        except Exception as exc:
            chat_log.write(Text.from_markup(f"[red]Error running git diff: {exc}[/red]"))

    # ------------------------------------------------------------------
    # Thinking indicator
    # ------------------------------------------------------------------

    def _show_thinking(self, visible: bool) -> None:
        """Show or hide the thinking spinner."""
        try:
            container = self.query_one("#thinking-container")
            if visible:
                container.add_class("visible")
            else:
                container.remove_class("visible")
        except NoMatches:
            pass

    def watch_is_thinking(self, thinking: bool) -> None:
        """React to changes in thinking state."""
        self._show_thinking(thinking)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _update_status_bar(self) -> None:
        """Push latest state to the status bar."""
        try:
            bar = self.query_one("#status-bar-container", StatusBar)
            if self.state:
                bar.token_count = self.state.total_input_tokens + self.state.total_output_tokens
                bar.cost = self.state.total_cost_usd
                bar.git_branch = self.state.git_branch
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def watch_sidebar_visible(self, visible: bool) -> None:
        """Toggle sidebar visibility."""
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
            if visible:
                sidebar.add_class("visible")
            else:
                sidebar.remove_class("visible")
        except NoMatches:
            pass

    # ------------------------------------------------------------------
    # Actions (bound to keys)
    # ------------------------------------------------------------------

    def action_interrupt(self) -> None:
        """Ctrl+C — interrupt the current operation."""
        if self.is_thinking and self.state:
            self.state.interrupted = True
            self.workers.cancel_group(self, "stream")
            chat_log = self.query_one("#chat-log", RichLog)
            self._render_system(chat_log, "[Interrupted by user]")

    def action_escape(self) -> None:
        """Escape — cancel current input or dismiss prompts."""
        # Dismiss any visible permission prompt
        try:
            container = self.query_one("#permission-container")
            container.remove_class("visible")
        except NoMatches:
            pass
        # Clear input
        try:
            self.query_one("#input-area", PromptInput).clear()
        except NoMatches:
            pass

    def action_clear_screen(self) -> None:
        """Ctrl+L — clear the chat log."""
        try:
            self.query_one("#chat-log", RichLog).clear()
        except NoMatches:
            pass

    def action_compact(self) -> None:
        """Ctrl+K — compact conversation."""
        chat_log = self.query_one("#chat-log", RichLog)
        self._render_system(chat_log, "Compacting...")
        if self.state and len(self.state.messages) > 10:
            self.state.messages = self.state.messages[-10:]
            self._render_system(chat_log, f"Kept last {len(self.state.messages)} messages.")

    def action_toggle_sidebar(self) -> None:
        """Ctrl+T — toggle the sidebar."""
        self.sidebar_visible = not self.sidebar_visible

    def action_toggle_transcript(self) -> None:
        """Ctrl+R — show the full transcript."""
        from claude_code.screens.transcript_screen import TranscriptScreen

        messages = self.state.messages if self.state else []
        self.push_screen(TranscriptScreen(messages=messages))

    def action_show_help(self) -> None:
        """F1 — show help."""
        chat_log = self.query_one("#chat-log", RichLog)
        self._render_help(chat_log)
