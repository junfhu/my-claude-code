"""
Status bar widget showing model, token count, cost, permission mode,
git branch, and other session metadata.
"""

from __future__ import annotations

from typing import Optional

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class StatusBar(Static):
    """
    A single-line status bar that displays key session information.

    Layout (left → right):
        [model] | [permission_mode] | [tokens] | [$cost] | [git_branch] | [vim]
    """

    # Reactive properties that trigger re-render
    model: reactive[str] = reactive("claude-sonnet-4-20250514")
    permission_mode: reactive[str] = reactive("default")
    token_count: reactive[int] = reactive(0)
    cost: reactive[float] = reactive(0.0)
    git_branch: reactive[Optional[str]] = reactive(None)
    vim_mode: reactive[bool] = reactive(False)
    is_streaming: reactive[bool] = reactive(False)
    session_id: reactive[str] = reactive("")
    max_budget: reactive[Optional[float]] = reactive(None)

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $accent-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        id: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        permission_mode: str = "default",
        **kwargs,
    ) -> None:
        super().__init__(id=id, **kwargs)
        self.model = model
        self.permission_mode = permission_mode

    def render(self) -> Text:
        """Render the status bar content."""
        parts: list[tuple[str, str]] = []

        # Model name (abbreviated)
        model_short = self._abbreviate_model(self.model)
        parts.append((f" {model_short} ", "bold white on dark_blue"))

        # Permission mode
        perm_style = self._permission_style(self.permission_mode)
        parts.append((f" {self.permission_mode} ", perm_style))

        # Token count
        if self.token_count > 0:
            token_str = self._format_tokens(self.token_count)
            parts.append((f" ⊘ {token_str} ", "cyan"))

        # Cost
        if self.cost > 0:
            cost_str = f"${self.cost:.4f}"
            if self.max_budget:
                remaining = self.max_budget - self.cost
                cost_str += f" / ${self.max_budget:.2f}"
                if remaining < self.max_budget * 0.1:
                    parts.append((f" {cost_str} ", "bold red"))
                else:
                    parts.append((f" {cost_str} ", "green"))
            else:
                parts.append((f" {cost_str} ", "green"))

        # Git branch
        if self.git_branch:
            parts.append((f"  {self.git_branch} ", "magenta"))

        # Vim mode indicator
        if self.vim_mode:
            parts.append((" VIM ", "bold black on yellow"))

        # Streaming indicator
        if self.is_streaming:
            parts.append((" ● streaming ", "bold yellow"))

        # Build the Text object
        text = Text()
        for content, style in parts:
            text.append(content, style=style)

        # Pad to fill width
        available = self.size.width - text.cell_len
        if available > 0:
            text.append(" " * available)

        return text

    # ------------------------------------------------------------------
    # Watchers — any reactive change triggers re-render
    # ------------------------------------------------------------------

    def watch_model(self) -> None:
        self.refresh()

    def watch_permission_mode(self) -> None:
        self.refresh()

    def watch_token_count(self) -> None:
        self.refresh()

    def watch_cost(self) -> None:
        self.refresh()

    def watch_git_branch(self) -> None:
        self.refresh()

    def watch_vim_mode(self) -> None:
        self.refresh()

    def watch_is_streaming(self) -> None:
        self.refresh()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _abbreviate_model(model: str) -> str:
        """Abbreviate long model names for the status bar."""
        abbreviations = {
            "claude-sonnet-4-20250514": "Sonnet 4",
            "claude-opus-4-20250514": "Opus 4",
            "claude-3-5-sonnet-20241022": "Sonnet 3.5",
            "claude-3-5-haiku-20241022": "Haiku 3.5",
            "claude-3-opus-20240229": "Opus 3",
        }
        return abbreviations.get(model, model.split("/")[-1][:20])

    @staticmethod
    def _format_tokens(count: int) -> str:
        """Format a token count for display."""
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}k"
        return str(count)

    @staticmethod
    def _permission_style(mode: str) -> str:
        """Return a Rich style string based on permission mode."""
        styles = {
            "default": "white on dark_green",
            "plan": "white on dark_blue",
            "auto-edit": "white on dark_magenta",
            "full-auto": "bold white on dark_red",
        }
        return styles.get(mode, "white on grey50")
