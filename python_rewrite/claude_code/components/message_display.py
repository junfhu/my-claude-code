"""
Rich rendering for chat messages.

Provides high-quality terminal rendering of user, assistant, system,
tool-use, and tool-result messages using Rich's Markdown, Syntax,
Panel, and Text primitives.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from rich.columns import Columns
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import RichLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CODE_BLOCK_RE = re.compile(
    r"```(\w+)?\n(.*?)```",
    re.DOTALL,
)

_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def _extract_code_blocks(text: str) -> list[dict]:
    """Extract fenced code blocks from markdown text.

    Returns a list of dicts: {"lang": str|None, "code": str, "start": int, "end": int}
    """
    blocks = []
    for m in _CODE_BLOCK_RE.finditer(text):
        blocks.append({
            "lang": m.group(1),
            "code": m.group(2).rstrip("\n"),
            "start": m.start(),
            "end": m.end(),
        })
    return blocks


def _rich_syntax(code: str, language: Optional[str] = None) -> Syntax:
    """Create a Rich Syntax object with sensible defaults."""
    lang = language or "text"
    # Map common aliases
    lang_map = {
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "rb": "ruby",
        "sh": "bash",
        "shell": "bash",
        "yml": "yaml",
        "zsh": "bash",
        "dockerfile": "docker",
    }
    lang = lang_map.get(lang.lower(), lang.lower())
    return Syntax(
        code,
        lang,
        theme="monokai",
        line_numbers=len(code.splitlines()) > 5,
        word_wrap=True,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# MessageRenderer
# ---------------------------------------------------------------------------


class MessageRenderer:
    """Renders chat messages into a Textual RichLog widget."""

    # User message prefix
    USER_PREFIX = "[bold green]❯[/bold green] "
    ASSISTANT_PREFIX = "[bold blue]◆[/bold blue] "
    SYSTEM_PREFIX = "[dim]ℹ[/dim] "

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_user(self, log: RichLog, content: str) -> None:
        """Render a user message."""
        # Simple text display with prefix
        text = Text.from_markup(f"{self.USER_PREFIX}[bold]{_escape_markup(content)}[/bold]")
        log.write(text)

    def render_assistant(self, log: RichLog, content: str) -> None:
        """Render a complete assistant message with markdown and syntax highlighting."""
        renderables = self._build_assistant_renderables(content)
        for r in renderables:
            log.write(r)

    def render_assistant_streaming(
        self,
        log: RichLog,
        content: str,
        done: bool = False,
    ) -> None:
        """Render a streaming assistant message (called repeatedly as chunks arrive).

        Because RichLog doesn't support in-place updates of the last entry,
        we write the full rendered content each time the first chunk arrives
        and then rely on the caller to clear/rewrite. For simplicity in the
        streaming path we just write a new line per invocation and clear
        the previous partial render.

        In practice the REPL manages this by tracking a stream widget.
        For the simple path we just write the final version.
        """
        if done:
            self.render_assistant(log, content)
        # Intermediate chunks are handled by the REPL's stream widget

    def render_system(self, log: RichLog, content: str) -> None:
        """Render a system / info message."""
        text = Text.from_markup(f"{self.SYSTEM_PREFIX}[dim]{_escape_markup(content)}[/dim]")
        log.write(text)

    def render_error(self, log: RichLog, content: str) -> None:
        """Render an error message."""
        text = Text.from_markup(f"[bold red]✖ Error:[/bold red] {_escape_markup(content)}")
        log.write(text)

    def render_tool_use(
        self,
        log: RichLog,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> None:
        """Render a tool invocation message."""
        header = Text.from_markup(f"  [bold yellow]⚡ {tool_name}[/bold yellow]")
        log.write(header)

        # Render input parameters
        if tool_input:
            input_lines = _format_tool_input(tool_name, tool_input)
            for line in input_lines:
                log.write(line)

    def render_tool_result(
        self,
        log: RichLog,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> None:
        """Render the result of a tool execution."""
        if is_error:
            error_text = result.get("error", str(result)) if isinstance(result, dict) else str(result)
            text = Text.from_markup(f"  [red]✖ {tool_name} failed:[/red] {_escape_markup(error_text)}")
            log.write(text)
            return

        output = result.get("output", str(result)) if isinstance(result, dict) else str(result)

        # Truncate very long output
        max_lines = 50
        lines = output.splitlines()
        truncated = False
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True

        display_text = "\n".join(lines)
        if truncated:
            display_text += f"\n... ({len(output.splitlines()) - max_lines} more lines)"

        if tool_name == "bash":
            log.write(Syntax(display_text, "bash", theme="monokai", word_wrap=True))
        elif tool_name in ("file_read", "grep", "glob"):
            log.write(Panel(
                Text(display_text),
                title=f"[cyan]{tool_name}[/cyan]",
                border_style="dim",
                expand=True,
                padding=(0, 1),
            ))
        else:
            status = "[green]✔[/green]" if not is_error else "[red]✖[/red]"
            log.write(Text.from_markup(f"  {status} [dim]{_escape_markup(display_text[:200])}[/dim]"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_assistant_renderables(self, content: str) -> list:
        """Build a list of Rich renderables for an assistant message.

        We split the content at code block boundaries so that each code
        block gets proper syntax highlighting while the surrounding prose
        renders as markdown.
        """
        renderables: list = []

        # Prefix
        renderables.append(Text.from_markup(self.ASSISTANT_PREFIX))

        code_blocks = _extract_code_blocks(content)
        if not code_blocks:
            # Pure markdown
            renderables.append(Markdown(content))
            return renderables

        # Interleave prose (markdown) and code (syntax)
        last_end = 0
        for block in code_blocks:
            # Prose before code block
            prose = content[last_end:block["start"]].strip()
            if prose:
                renderables.append(Markdown(prose))
            # Code block
            renderables.append(
                Panel(
                    _rich_syntax(block["code"], block["lang"]),
                    title=f"[dim]{block['lang'] or 'code'}[/dim]",
                    border_style="dim cyan",
                    expand=True,
                    padding=(0, 0),
                )
            )
            last_end = block["end"]

        # Trailing prose after last code block
        trailing = content[last_end:].strip()
        if trailing:
            renderables.append(Markdown(trailing))

        return renderables


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _escape_markup(text: str) -> str:
    """Escape Rich markup characters in text to prevent rendering issues."""
    return text.replace("[", "\\[").replace("]", "\\]")


def _format_tool_input(tool_name: str, tool_input: Dict[str, Any]) -> list:
    """Format tool input parameters for display."""
    renderables = []

    if tool_name == "bash":
        cmd = tool_input.get("command", "")
        renderables.append(
            Panel(
                Syntax(cmd, "bash", theme="monokai", word_wrap=True),
                title="[dim]command[/dim]",
                border_style="dim yellow",
                expand=True,
                padding=(0, 1),
            )
        )
    elif tool_name in ("file_read", "glob", "grep"):
        for key, val in tool_input.items():
            renderables.append(
                Text.from_markup(f"    [dim]{key}:[/dim] {_escape_markup(str(val))}")
            )
    elif tool_name in ("file_write", "file_edit"):
        path = tool_input.get("file_path", tool_input.get("path", "unknown"))
        renderables.append(Text.from_markup(f"    [dim]path:[/dim] {_escape_markup(path)}"))
        content = tool_input.get("content", tool_input.get("new_string", ""))
        if content:
            # Show a preview of the content
            preview = content[:500]
            if len(content) > 500:
                preview += "..."
            # Try to detect language from file extension
            lang = _lang_from_path(path)
            renderables.append(
                Panel(
                    Syntax(preview, lang, theme="monokai", word_wrap=True),
                    title="[dim]content[/dim]",
                    border_style="dim yellow",
                    expand=True,
                    padding=(0, 0),
                )
            )
    else:
        # Generic display
        import json
        try:
            formatted = json.dumps(tool_input, indent=2, default=str)
            renderables.append(
                Syntax(formatted, "json", theme="monokai", word_wrap=True, padding=(0, 2))
            )
        except Exception:
            renderables.append(Text.from_markup(f"    [dim]{_escape_markup(str(tool_input))}[/dim]"))

    return renderables


def _lang_from_path(path: str) -> str:
    """Guess the language from a file path extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".jsx": "jsx",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".xml": "xml",
        ".dockerfile": "docker",
        ".tf": "hcl",
    }
    for ext, lang in ext_map.items():
        if path.lower().endswith(ext):
            return lang
    return "text"
