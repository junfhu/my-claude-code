"""
Tool-specific rendering for Claude Code.

Provides specialised renderers for tool outputs: bash results, file diffs,
search results, progress indicators, and generic tool output.
"""

from __future__ import annotations

import difflib
import os
from typing import Any, Dict, List, Optional, Sequence

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual.widgets import RichLog


# ---------------------------------------------------------------------------
# Tool renderer
# ---------------------------------------------------------------------------


class ToolRenderer:
    """Renders tool invocations and results into a Textual RichLog."""

    # ------------------------------------------------------------------
    # High-level API (used by REPL)
    # ------------------------------------------------------------------

    def render_use(
        self,
        log: RichLog,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> None:
        """Render a tool invocation header."""
        icon = _TOOL_ICONS.get(tool_name, "⚡")
        header = Text.from_markup(f"  [bold yellow]{icon} {tool_name}[/bold yellow]")
        log.write(header)
        self._render_input(log, tool_name, tool_input)

    def render_result(
        self,
        log: RichLog,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> None:
        """Render a tool result."""
        if is_error:
            self._render_error(log, tool_name, result)
            return

        dispatch = {
            "bash": self._render_bash_result,
            "file_read": self._render_file_read_result,
            "file_write": self._render_file_write_result,
            "file_edit": self._render_file_edit_result,
            "grep": self._render_grep_result,
            "glob": self._render_glob_result,
            "web_fetch": self._render_web_fetch_result,
            "web_search": self._render_web_search_result,
        }
        handler = dispatch.get(tool_name)
        if handler:
            handler(log, result)
        else:
            self._render_generic_result(log, tool_name, result)

    # ------------------------------------------------------------------
    # Input renderers
    # ------------------------------------------------------------------

    def _render_input(self, log: RichLog, tool_name: str, tool_input: Dict[str, Any]) -> None:
        if tool_name == "bash":
            cmd = tool_input.get("command", "")
            timeout = tool_input.get("timeout")
            title_parts = ["command"]
            if timeout:
                title_parts.append(f"timeout={timeout}s")
            log.write(Panel(
                Syntax(cmd, "bash", theme="monokai", word_wrap=True),
                title=f"[dim]{' | '.join(title_parts)}[/dim]",
                border_style="dim yellow",
                expand=True,
                padding=(0, 1),
            ))
        elif tool_name == "file_read":
            path = tool_input.get("file_path", "")
            offset = tool_input.get("offset")
            limit = tool_input.get("limit")
            parts = [f"[dim]path:[/dim] {path}"]
            if offset:
                parts.append(f"[dim]offset:[/dim] {offset}")
            if limit:
                parts.append(f"[dim]limit:[/dim] {limit}")
            for p in parts:
                log.write(Text.from_markup(f"    {p}"))
        elif tool_name in ("file_write", "file_edit"):
            path = tool_input.get("file_path", "")
            log.write(Text.from_markup(f"    [dim]path:[/dim] {path}"))
            if tool_name == "file_edit":
                old = tool_input.get("old_string", "")
                new = tool_input.get("new_string", "")
                if old and new:
                    diff_text = render_inline_diff(old, new)
                    log.write(Panel(
                        diff_text,
                        title="[dim]edit[/dim]",
                        border_style="dim yellow",
                        expand=True,
                        padding=(0, 1),
                    ))
        elif tool_name == "grep":
            pattern = tool_input.get("pattern", "")
            path = tool_input.get("path", ".")
            log.write(Text.from_markup(f"    [dim]pattern:[/dim] {pattern}"))
            log.write(Text.from_markup(f"    [dim]path:[/dim] {path}"))
        elif tool_name == "glob":
            pattern = tool_input.get("pattern", "")
            path = tool_input.get("path", ".")
            log.write(Text.from_markup(f"    [dim]pattern:[/dim] {pattern}"))
            log.write(Text.from_markup(f"    [dim]path:[/dim] {path}"))
        else:
            # Generic JSON display
            import json
            try:
                formatted = json.dumps(tool_input, indent=2, default=str)
                if len(formatted) > 500:
                    formatted = formatted[:500] + "\n..."
                log.write(Syntax(formatted, "json", theme="monokai", word_wrap=True, padding=(0, 2)))
            except Exception:
                log.write(Text.from_markup(f"    [dim]{str(tool_input)[:200]}[/dim]"))

    # ------------------------------------------------------------------
    # Result renderers
    # ------------------------------------------------------------------

    def _render_bash_result(self, log: RichLog, result: Any) -> None:
        """Render bash command output."""
        output = _extract_output(result)
        exit_code = result.get("exit_code", 0) if isinstance(result, dict) else 0
        stderr = result.get("stderr", "") if isinstance(result, dict) else ""

        if not output and not stderr:
            log.write(Text.from_markup("    [dim](no output)[/dim]"))
            return

        # Render stdout
        if output:
            rendered = render_bash_output(output, max_lines=60)
            log.write(rendered)

        # Render stderr if present
        if stderr:
            log.write(Text.from_markup("    [bold red]stderr:[/bold red]"))
            log.write(Panel(
                Text(stderr[:2000], style="red"),
                border_style="red",
                expand=True,
                padding=(0, 1),
            ))

        # Exit code indicator
        if exit_code != 0:
            log.write(Text.from_markup(f"    [red]exit code: {exit_code}[/red]"))
        else:
            log.write(Text.from_markup("    [green]✔ done[/green]"))

    def _render_file_read_result(self, log: RichLog, result: Any) -> None:
        """Render file read output with syntax highlighting."""
        output = _extract_output(result)
        path = result.get("path", "") if isinstance(result, dict) else ""

        if not output:
            log.write(Text.from_markup("    [dim](empty file)[/dim]"))
            return

        lang = _lang_from_path(path)
        lines = output.splitlines()
        truncated = len(lines) > 80
        display = "\n".join(lines[:80])
        if truncated:
            display += f"\n... ({len(lines) - 80} more lines)"

        log.write(Panel(
            Syntax(display, lang, theme="monokai", line_numbers=True, word_wrap=True),
            title=f"[cyan]{os.path.basename(path) or 'file'}[/cyan] ({len(lines)} lines)",
            border_style="dim cyan",
            expand=True,
            padding=(0, 0),
        ))

    def _render_file_write_result(self, log: RichLog, result: Any) -> None:
        """Render file write confirmation."""
        path = result.get("path", "") if isinstance(result, dict) else ""
        bytes_written = result.get("bytes_written", 0) if isinstance(result, dict) else 0
        log.write(Text.from_markup(
            f"    [green]✔ Wrote[/green] {path} [dim]({bytes_written:,} bytes)[/dim]"
        ))

    def _render_file_edit_result(self, log: RichLog, result: Any) -> None:
        """Render file edit result with diff."""
        output = _extract_output(result)
        path = result.get("path", "") if isinstance(result, dict) else ""

        if isinstance(result, dict) and "diff" in result:
            diff_text = result["diff"]
            log.write(Panel(
                Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
                title=f"[cyan]{os.path.basename(path) or 'edit'}[/cyan]",
                border_style="dim green",
                expand=True,
                padding=(0, 0),
            ))
        else:
            log.write(Text.from_markup(f"    [green]✔ Edited[/green] {path}"))

    def _render_grep_result(self, log: RichLog, result: Any) -> None:
        """Render grep/search results."""
        output = _extract_output(result)
        matches = result.get("matches", []) if isinstance(result, dict) else []

        if matches:
            rendered = render_search_results(matches)
            log.write(rendered)
        elif output:
            log.write(Panel(
                Text(output[:3000]),
                title="[cyan]search results[/cyan]",
                border_style="dim cyan",
                expand=True,
                padding=(0, 1),
            ))
        else:
            log.write(Text.from_markup("    [dim]No matches found.[/dim]"))

    def _render_glob_result(self, log: RichLog, result: Any) -> None:
        """Render glob/file listing results."""
        output = _extract_output(result)
        files = result.get("files", []) if isinstance(result, dict) else []

        if files:
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("File", style="cyan")
            for f in files[:50]:
                table.add_row(f)
            if len(files) > 50:
                table.add_row(f"... ({len(files) - 50} more)")
            log.write(Panel(table, title=f"[cyan]{len(files)} files[/cyan]", border_style="dim"))
        elif output:
            lines = output.strip().splitlines()[:50]
            for line in lines:
                log.write(Text.from_markup(f"    [cyan]{line}[/cyan]"))
            if len(output.splitlines()) > 50:
                log.write(Text.from_markup(f"    [dim]... ({len(output.splitlines()) - 50} more)[/dim]"))
        else:
            log.write(Text.from_markup("    [dim]No files found.[/dim]"))

    def _render_web_fetch_result(self, log: RichLog, result: Any) -> None:
        """Render web fetch result."""
        output = _extract_output(result)
        url = result.get("url", "") if isinstance(result, dict) else ""
        title = result.get("title", "") if isinstance(result, dict) else ""

        header_parts = []
        if title:
            header_parts.append(title)
        if url:
            header_parts.append(f"[dim]{url}[/dim]")

        if header_parts:
            log.write(Text.from_markup("    " + " — ".join(header_parts)))

        if output:
            preview = output[:1000]
            if len(output) > 1000:
                preview += "..."
            log.write(Panel(
                Text(preview),
                border_style="dim",
                expand=True,
                padding=(0, 1),
            ))

    def _render_web_search_result(self, log: RichLog, result: Any) -> None:
        """Render web search results."""
        results_list = result.get("results", []) if isinstance(result, dict) else []
        if not results_list:
            output = _extract_output(result)
            if output:
                log.write(Text(output[:1000]))
            else:
                log.write(Text.from_markup("    [dim]No results.[/dim]"))
            return

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="bold")
        table.add_column("URL", style="dim cyan")

        for i, r in enumerate(results_list[:10], 1):
            title = r.get("title", "")
            url = r.get("url", "")
            table.add_row(str(i), title, url)

        log.write(Panel(table, title="[cyan]Search Results[/cyan]", border_style="dim"))

    def _render_generic_result(self, log: RichLog, tool_name: str, result: Any) -> None:
        """Render a generic tool result."""
        output = _extract_output(result)
        if output:
            if len(output) > 500:
                output = output[:500] + "..."
            log.write(Text.from_markup(f"    [green]✔[/green] [dim]{output}[/dim]"))
        else:
            log.write(Text.from_markup(f"    [green]✔ {tool_name} completed[/green]"))

    def _render_error(self, log: RichLog, tool_name: str, result: Any) -> None:
        """Render a tool error."""
        error = result.get("error", str(result)) if isinstance(result, dict) else str(result)
        log.write(Text.from_markup(f"    [bold red]✖ {tool_name} failed:[/bold red] {error}"))


# ---------------------------------------------------------------------------
# Standalone rendering functions (used by other modules)
# ---------------------------------------------------------------------------


def render_bash_output(output: str, max_lines: int = 60) -> Panel:
    """Render bash command output with truncation and styling."""
    lines = output.splitlines()
    truncated = len(lines) > max_lines
    display = "\n".join(lines[:max_lines])
    if truncated:
        display += f"\n... ({len(lines) - max_lines} more lines)"

    return Panel(
        Syntax(display, "bash", theme="monokai", word_wrap=True),
        title=f"[dim]output ({len(lines)} lines)[/dim]" if truncated else "[dim]output[/dim]",
        border_style="dim green",
        expand=True,
        padding=(0, 1),
    )


def render_file_diff(
    old_content: str,
    new_content: str,
    filename: str = "",
    context_lines: int = 3,
) -> Panel:
    """Render a unified diff between two strings."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}" if filename else "a/file",
        tofile=f"b/{filename}" if filename else "b/file",
        n=context_lines,
    )
    diff_text = "".join(diff)

    if not diff_text:
        return Panel(
            Text("(no changes)", style="dim"),
            title=f"[cyan]{filename or 'diff'}[/cyan]",
            border_style="dim",
        )

    return Panel(
        Syntax(diff_text, "diff", theme="monokai", word_wrap=True),
        title=f"[cyan]{filename or 'diff'}[/cyan]",
        border_style="dim green",
        expand=True,
        padding=(0, 0),
    )


def render_inline_diff(old: str, new: str) -> Text:
    """Render an inline character-level diff using Rich Text."""
    result = Text()

    sm = difflib.SequenceMatcher(None, old, new)
    for op, a_start, a_end, b_start, b_end in sm.get_opcodes():
        if op == "equal":
            result.append(old[a_start:a_end])
        elif op == "delete":
            result.append(old[a_start:a_end], style="bold red strike")
        elif op == "insert":
            result.append(new[b_start:b_end], style="bold green")
        elif op == "replace":
            result.append(old[a_start:a_end], style="bold red strike")
            result.append(new[b_start:b_end], style="bold green")

    return result


def render_search_results(matches: List[Dict[str, Any]]) -> Panel:
    """Render structured search/grep results."""
    table = Table(show_header=True, box=None, padding=(0, 1), expand=True)
    table.add_column("File", style="cyan", ratio=3)
    table.add_column("Line", style="yellow", width=6, justify="right")
    table.add_column("Content", ratio=7)

    for m in matches[:50]:
        file_path = m.get("file", m.get("path", ""))
        line_num = str(m.get("line", m.get("line_number", "")))
        content = m.get("content", m.get("text", ""))
        # Truncate long content
        if len(content) > 120:
            content = content[:120] + "..."
        table.add_row(file_path, line_num, content)

    title = f"[cyan]{len(matches)} match{'es' if len(matches) != 1 else ''}[/cyan]"
    if len(matches) > 50:
        title += f" [dim](showing 50/{len(matches)})[/dim]"

    return Panel(table, title=title, border_style="dim cyan", expand=True, padding=(0, 0))


def render_progress_bar(
    completed: float,
    total: float,
    label: str = "",
    width: int = 40,
) -> Text:
    """Render a simple text-based progress bar."""
    if total <= 0:
        pct = 0.0
    else:
        pct = min(completed / total, 1.0)

    filled = int(width * pct)
    empty = width - filled
    bar = "█" * filled + "░" * empty

    result = Text()
    if label:
        result.append(f"{label} ", style="bold")
    result.append("[", style="dim")
    result.append(bar[:filled], style="green")
    result.append(bar[filled:], style="dim")
    result.append("]", style="dim")
    result.append(f" {pct:.0%}", style="bold")

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOOL_ICONS = {
    "bash": "🔧",
    "file_read": "📖",
    "file_write": "✏️",
    "file_edit": "✏️",
    "grep": "🔍",
    "glob": "📁",
    "web_fetch": "🌐",
    "web_search": "🔎",
    "notebook_edit": "📓",
    "agent": "🤖",
    "task": "📋",
    "todo_write": "✅",
    "mcp": "🔌",
}


def _extract_output(result: Any) -> str:
    """Extract the output string from various result formats."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("output", result.get("content", result.get("text", "")))
    return str(result)


def _lang_from_path(path: str) -> str:
    """Guess language from file extension."""
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "tsx", ".jsx": "jsx", ".rs": "rust", ".go": "go",
        ".java": "java", ".c": "c", ".cpp": "cpp", ".rb": "ruby",
        ".sh": "bash", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".md": "markdown", ".html": "html", ".css": "css",
        ".sql": "sql",
    }
    for ext, lang in ext_map.items():
        if path.lower().endswith(ext):
            return lang
    return "text"
