"""
Ink compatibility layer.

The original Claude Code UI is built with React + Ink (a React renderer
for terminal UIs). This module provides a compatibility shim that
re-exports Rich and Textual primitives under names that mirror the Ink
API surface, making it easier to port existing component logic.

This is *not* a full Ink implementation — it maps the concepts used by
Claude Code's React components to their Textual/Rich equivalents.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Rich re-exports (formatting / rendering)
# ---------------------------------------------------------------------------

from rich.box import ROUNDED, HEAVY, SIMPLE, SQUARE  # noqa: F401
from rich.columns import Columns  # noqa: F401
from rich.console import Console, Group  # noqa: F401
from rich.markdown import Markdown  # noqa: F401
from rich.panel import Panel  # noqa: F401
from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: F401
from rich.syntax import Syntax  # noqa: F401
from rich.table import Table  # noqa: F401
from rich.text import Text  # noqa: F401
from rich.theme import Theme  # noqa: F401
from rich.tree import Tree  # noqa: F401

# ---------------------------------------------------------------------------
# Textual re-exports (widget / app layer)
# ---------------------------------------------------------------------------

from textual.app import App, ComposeResult  # noqa: F401
from textual.binding import Binding  # noqa: F401
from textual.containers import (  # noqa: F401
    Center,
    Container,
    Horizontal,
    Vertical,
    VerticalScroll,
)
from textual.message import Message  # noqa: F401
from textual.reactive import reactive  # noqa: F401
from textual.screen import Screen  # noqa: F401
from textual.widget import Widget  # noqa: F401
from textual.widgets import (  # noqa: F401
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    Switch,
    TextArea,
    Tree as TreeWidget,
)


# ---------------------------------------------------------------------------
# Ink-like helper types
# ---------------------------------------------------------------------------


class BoxProps:
    """
    Approximation of Ink's ``<Box>`` component props.

    Maps to Textual container styles.
    """

    def __init__(
        self,
        *,
        flex_direction: str = "column",  # "row" | "column"
        padding: int = 0,
        margin: int = 0,
        border_style: Optional[str] = None,
        width: Optional[int | str] = None,
        height: Optional[int | str] = None,
        align_items: str = "stretch",
        justify_content: str = "flex-start",
    ) -> None:
        self.flex_direction = flex_direction
        self.padding = padding
        self.margin = margin
        self.border_style = border_style
        self.width = width
        self.height = height
        self.align_items = align_items
        self.justify_content = justify_content

    def to_textual_container(self) -> type:
        """Return the appropriate Textual container class."""
        if self.flex_direction == "row":
            return Horizontal
        return Vertical


class TextProps:
    """Approximation of Ink's ``<Text>`` component props."""

    def __init__(
        self,
        *,
        color: Optional[str] = None,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        dimColor: bool = False,
        wrap: str = "wrap",  # "wrap" | "truncate" | "truncate-end"
    ) -> None:
        self.color = color
        self.bold = bold
        self.italic = italic
        self.underline = underline
        self.dimColor = dimColor
        self.wrap = wrap

    def to_rich_style(self) -> str:
        """Convert to a Rich style string."""
        parts: list[str] = []
        if self.bold:
            parts.append("bold")
        if self.italic:
            parts.append("italic")
        if self.underline:
            parts.append("underline")
        if self.dimColor:
            parts.append("dim")
        if self.color:
            parts.append(self.color)
        return " ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# React-like hooks (simplified for Python)
# ---------------------------------------------------------------------------


def use_state(initial: Any) -> tuple:
    """
    Simplified ``useState`` analogue.

    In Textual, state is managed via ``reactive`` properties on widgets.
    This function is provided for porting convenience — in production
    you should use ``reactive[T]`` on your widget class instead.
    """

    class _State:
        def __init__(self, value: Any) -> None:
            self._value = value
            self._listeners: list[Callable] = []

        @property
        def value(self) -> Any:
            return self._value

        @value.setter
        def value(self, new: Any) -> None:
            self._value = new
            for fn in self._listeners:
                fn(new)

        def on_change(self, fn: Callable) -> None:
            self._listeners.append(fn)

    state = _State(initial)
    return state.value, lambda v: setattr(state, "value", v)


def use_input(handler: Callable[[str, Any], None]) -> None:
    """
    Simplified ``useInput`` analogue.

    In Textual, key handling is done via ``on_key`` or ``BINDINGS``.
    This is a no-op stub for porting reference.
    """
    pass


# ---------------------------------------------------------------------------
# Module-level console (shared across the app)
# ---------------------------------------------------------------------------

console = Console(highlight=True, markup=True)


# ---------------------------------------------------------------------------
# Convenience render functions
# ---------------------------------------------------------------------------


def render_markdown(text: str) -> Markdown:
    """Render markdown text."""
    return Markdown(text)


def render_code(code: str, language: str = "text") -> Syntax:
    """Render syntax-highlighted code."""
    return Syntax(code, language, theme="monokai", word_wrap=True, padding=(0, 1))


def render_panel(
    content: Any,
    title: str = "",
    border_style: str = "blue",
) -> Panel:
    """Render a bordered panel."""
    return Panel(content, title=title, border_style=border_style, expand=True)
