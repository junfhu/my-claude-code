"""
Full conversation transcript viewer screen.

Provides a scrollable, read-only view of the entire conversation history
with rich formatting. Accessible via Ctrl+R from the REPL.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static


# ---------------------------------------------------------------------------
# Transcript screen
# ---------------------------------------------------------------------------


class TranscriptScreen(Screen):
    """
    A full-screen, scrollable transcript of the conversation.

    Renders all messages (user, assistant, system, tool use/result)
    with proper formatting and syntax highlighting. Read-only — the
    user can scroll and then press Escape / q to return to the REPL.
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("q", "pop_screen", "Back", show=True),
        Binding("home", "scroll_top", "Top", show=False),
        Binding("end", "scroll_bottom", "Bottom", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("/", "search", "Search", show=True),
        Binding("e", "export", "Export", show=True),
    ]

    CSS = """
    TranscriptScreen {
        background: $surface;
    }

    #transcript-header {
        height: 3;
        padding: 1 2;
        background: $accent-darken-2;
        color: $text;
    }

    #transcript-log {
        height: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }

    #transcript-footer {
        height: 1;
        padding: 0 2;
        background: $accent-darken-2;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        session_id: str = "",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.messages = messages or []
        self.session_id = session_id
        self._search_term: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            self._build_header(),
            id="transcript-header",
        )
        yield RichLog(
            id="transcript-log",
            wrap=True,
            highlight=True,
            markup=True,
        )
        yield Static(
            Text.from_markup(
                f"  [dim]{len(self.messages)} messages | "
                f"Press [bold]q[/bold] or [bold]Esc[/bold] to return | "
                f"[bold]e[/bold] to export | [bold]/[/bold] to search[/dim]"
            ),
            id="transcript-footer",
        )
        yield Footer()

    def _build_header(self) -> Text:
        """Build the header text."""
        text = Text()
        text.append("📜 Conversation Transcript", style="bold")
        if self.session_id:
            text.append(f"  (session: {self.session_id})", style="dim")
        text.append(f"\n   {len(self.messages)} messages", style="dim")
        return text

    async def on_mount(self) -> None:
        """Render all messages when the screen mounts."""
        log = self.query_one("#transcript-log", RichLog)
        self._render_all_messages(log)

    def _render_all_messages(self, log: RichLog) -> None:
        """Render the complete conversation to the log."""
        for i, msg in enumerate(self.messages):
            self._render_message(log, msg, index=i)

        if not self.messages:
            log.write(Text.from_markup("[dim]No messages in this conversation.[/dim]"))

    def _render_message(
        self,
        log: RichLog,
        msg: Dict[str, Any],
        index: int = 0,
    ) -> None:
        """Render a single message to the log."""
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp")

        # Message number
        num_str = f"[dim]#{index + 1}[/dim]"

        if role == "user":
            self._render_user_message(log, content, num_str, timestamp)
        elif role == "assistant":
            self._render_assistant_message(log, content, num_str, timestamp)
        elif role == "system":
            self._render_system_message(log, content, num_str)
        elif role == "tool_use":
            self._render_tool_use_message(log, msg, num_str)
        elif role == "tool_result":
            self._render_tool_result_message(log, msg, num_str)
        else:
            log.write(Text.from_markup(f"{num_str} [dim]{role}: {content[:200]}[/dim]"))

        # Separator
        log.write(Text(""))

    def _render_user_message(
        self,
        log: RichLog,
        content: str,
        num: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Render a user message."""
        time_str = f" [dim]{timestamp}[/dim]" if timestamp else ""
        log.write(Text.from_markup(
            f"{num} [bold green]❯ You{time_str}[/bold green]"
        ))
        # User messages are typically short — render as plain text
        if "\n" in content:
            log.write(Panel(
                Text(content),
                border_style="green",
                expand=True,
                padding=(0, 1),
            ))
        else:
            log.write(Text.from_markup(f"  [bold]{_escape(content)}[/bold]"))

    def _render_assistant_message(
        self,
        log: RichLog,
        content: str,
        num: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Render an assistant message with markdown."""
        time_str = f" [dim]{timestamp}[/dim]" if timestamp else ""
        log.write(Text.from_markup(
            f"{num} [bold blue]◆ Claude{time_str}[/bold blue]"
        ))

        # Render content as markdown
        if content:
            log.write(Markdown(content))

    def _render_system_message(
        self,
        log: RichLog,
        content: str,
        num: str,
    ) -> None:
        """Render a system message."""
        log.write(Text.from_markup(
            f"{num} [dim]ℹ System: {_escape(content[:200])}[/dim]"
        ))

    def _render_tool_use_message(
        self,
        log: RichLog,
        msg: Dict[str, Any],
        num: str,
    ) -> None:
        """Render a tool use message."""
        tool_name = msg.get("name", msg.get("tool_name", "unknown"))
        tool_input = msg.get("input", msg.get("tool_input", {}))

        log.write(Text.from_markup(
            f"{num} [bold yellow]⚡ Tool: {tool_name}[/bold yellow]"
        ))

        if isinstance(tool_input, dict):
            if tool_name == "bash":
                cmd = tool_input.get("command", "")
                log.write(Panel(
                    Syntax(cmd, "bash", theme="monokai", word_wrap=True),
                    title="[dim]command[/dim]",
                    border_style="dim yellow",
                    expand=True,
                    padding=(0, 1),
                ))
            else:
                try:
                    formatted = json.dumps(tool_input, indent=2, default=str)
                    log.write(Syntax(
                        formatted, "json", theme="monokai",
                        word_wrap=True, padding=(0, 2),
                    ))
                except Exception:
                    log.write(Text(str(tool_input)[:500]))

    def _render_tool_result_message(
        self,
        log: RichLog,
        msg: Dict[str, Any],
        num: str,
    ) -> None:
        """Render a tool result message."""
        tool_name = msg.get("name", msg.get("tool_name", "unknown"))
        content = msg.get("content", msg.get("output", ""))
        is_error = msg.get("is_error", False)

        if is_error:
            log.write(Text.from_markup(
                f"{num} [red]✖ {tool_name} error: {_escape(str(content)[:200])}[/red]"
            ))
        else:
            log.write(Text.from_markup(
                f"{num} [green]✔ {tool_name} result[/green]"
            ))
            if content:
                text = str(content)
                if len(text) > 500:
                    text = text[:500] + "..."
                log.write(Panel(
                    Text(text),
                    border_style="dim green",
                    expand=True,
                    padding=(0, 1),
                ))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_scroll_top(self) -> None:
        """Scroll to the top of the transcript."""
        try:
            log = self.query_one("#transcript-log", RichLog)
            log.scroll_home()
        except Exception:
            pass

    def action_scroll_bottom(self) -> None:
        """Scroll to the bottom of the transcript."""
        try:
            log = self.query_one("#transcript-log", RichLog)
            log.scroll_end()
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            self.query_one("#transcript-log", RichLog).scroll_down()
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        try:
            self.query_one("#transcript-log", RichLog).scroll_up()
        except Exception:
            pass

    def action_search(self) -> None:
        """Search within the transcript (placeholder)."""
        # In a full implementation, this would show a search input
        # and highlight matching text in the transcript
        try:
            log = self.query_one("#transcript-log", RichLog)
            log.write(Text.from_markup("[dim]Search not yet implemented — press Esc to go back.[/dim]"))
        except Exception:
            pass

    def action_export(self) -> None:
        """Export the transcript to a file."""
        try:
            from pathlib import Path

            export_dir = Path.home() / ".claude" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = export_dir / f"transcript_{timestamp}.json"
            export_path.write_text(
                json.dumps(self.messages, indent=2, default=str)
            )

            log = self.query_one("#transcript-log", RichLog)
            log.write(Text.from_markup(
                f"\n[green]✔ Exported to {export_path}[/green]"
            ))
        except Exception as exc:
            try:
                log = self.query_one("#transcript-log", RichLog)
                log.write(Text.from_markup(f"\n[red]✖ Export failed: {exc}[/red]"))
            except Exception:
                pass

    def action_pop_screen(self) -> None:
        """Return to the REPL."""
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """Escape Rich markup characters."""
    return text.replace("[", "\\[").replace("]", "\\]")
