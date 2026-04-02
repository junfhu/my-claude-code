"""
Sidebar widget for Claude Code.

Displays:
  - Todo list / task tracking
  - Teammate / agent list
  - Session metadata

Can be toggled with Ctrl+T.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TodoItem:
    """Represents a single todo item."""

    __slots__ = ("id", "text", "status", "priority")

    def __init__(
        self,
        id: str,
        text: str,
        status: str = "pending",
        priority: str = "normal",
    ) -> None:
        self.id = id
        self.text = text
        self.status = status  # "pending" | "in_progress" | "completed"
        self.priority = priority  # "low" | "normal" | "high"

    @property
    def icon(self) -> str:
        icons = {
            "pending": "○",
            "in_progress": "◑",
            "completed": "●",
        }
        return icons.get(self.status, "○")

    @property
    def style(self) -> str:
        styles = {
            "pending": "white",
            "in_progress": "yellow",
            "completed": "green dim strike",
        }
        return styles.get(self.status, "white")


class TeammateInfo:
    """Represents a teammate/agent."""

    __slots__ = ("name", "role", "status")

    def __init__(self, name: str, role: str = "agent", status: str = "idle") -> None:
        self.name = name
        self.role = role
        self.status = status  # "idle" | "working" | "waiting"

    @property
    def icon(self) -> str:
        icons = {
            "idle": "💤",
            "working": "⚡",
            "waiting": "⏳",
        }
        return icons.get(self.status, "🤖")


# ---------------------------------------------------------------------------
# Sidebar sections
# ---------------------------------------------------------------------------


class TodoListSection(Static):
    """Displays the todo list."""

    DEFAULT_CSS = """
    TodoListSection {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    todos: reactive[list] = reactive(list, always_update=True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: List[TodoItem] = []

    def set_todos(self, items: List[TodoItem]) -> None:
        """Update the todo list."""
        self._items = items
        self.refresh()

    def add_todo(self, item: TodoItem) -> None:
        """Add a todo item."""
        self._items.append(item)
        self.refresh()

    def update_todo(self, id: str, status: str) -> None:
        """Update a todo item's status."""
        for item in self._items:
            if item.id == id:
                item.status = status
                break
        self.refresh()

    def remove_todo(self, id: str) -> None:
        """Remove a todo item."""
        self._items = [i for i in self._items if i.id != id]
        self.refresh()

    def render(self) -> Text:
        """Render the todo list."""
        text = Text()
        text.append("📋 Tasks\n", style="bold underline")

        if not self._items:
            text.append("  No tasks yet.\n", style="dim")
            return text

        # Group by status
        in_progress = [i for i in self._items if i.status == "in_progress"]
        pending = [i for i in self._items if i.status == "pending"]
        completed = [i for i in self._items if i.status == "completed"]

        for item in in_progress + pending:
            text.append(f"  {item.icon} ", style=item.style)
            text.append(item.text, style=item.style)
            if item.status == "in_progress":
                text.append(" ◀", style="yellow bold")
            text.append("\n")

        if completed:
            text.append(f"\n  ─── completed ({len(completed)}) ───\n", style="dim")
            for item in completed[-5:]:  # Show last 5 completed
                text.append(f"  {item.icon} ", style=item.style)
                text.append(item.text, style=item.style)
                text.append("\n")
            if len(completed) > 5:
                text.append(f"  ... {len(completed) - 5} more\n", style="dim")

        # Summary
        total = len(self._items)
        done = len(completed)
        text.append(f"\n  {done}/{total} completed", style="dim")
        if total > 0:
            pct = done / total * 100
            bar_width = 20
            filled = int(bar_width * done / total)
            bar = "█" * filled + "░" * (bar_width - filled)
            text.append(f" [{bar}] {pct:.0f}%\n", style="dim")

        return text


class TeammateSection(Static):
    """Displays the list of teammates/agents."""

    DEFAULT_CSS = """
    TeammateSection {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._teammates: List[TeammateInfo] = []

    def set_teammates(self, teammates: List[TeammateInfo]) -> None:
        """Update the teammate list."""
        self._teammates = teammates
        self.refresh()

    def render(self) -> Text:
        """Render the teammate list."""
        text = Text()
        text.append("👥 Teammates\n", style="bold underline")

        if not self._teammates:
            text.append("  No teammates.\n", style="dim")
            return text

        for tm in self._teammates:
            text.append(f"  {tm.icon} ", style="bold")
            text.append(tm.name, style="bold")
            text.append(f" ({tm.role})", style="dim")
            status_style = {
                "idle": "dim",
                "working": "yellow",
                "waiting": "cyan",
            }.get(tm.status, "dim")
            text.append(f" [{tm.status}]", style=status_style)
            text.append("\n")

        return text


class SessionInfoSection(Static):
    """Displays session metadata."""

    DEFAULT_CSS = """
    SessionInfoSection {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._info: Dict[str, str] = {}

    def set_info(self, info: Dict[str, str]) -> None:
        """Update session info."""
        self._info = info
        self.refresh()

    def render(self) -> Text:
        """Render session info."""
        text = Text()
        text.append("ℹ️  Session\n", style="bold underline")

        if not self._info:
            text.append("  No session info.\n", style="dim")
            return text

        for key, value in self._info.items():
            text.append(f"  {key}: ", style="dim")
            text.append(f"{value}\n")

        return text


# ---------------------------------------------------------------------------
# Main Sidebar widget
# ---------------------------------------------------------------------------


class Sidebar(Widget):
    """
    Sidebar panel that aggregates todo list, teammates, and session info.
    Toggled with Ctrl+T in the main REPL.
    """

    DEFAULT_CSS = """
    Sidebar {
        width: 32;
        height: 1fr;
        border-left: solid $accent;
        background: $surface;
        overflow-y: auto;
        display: none;
    }

    Sidebar.visible {
        display: block;
    }

    Sidebar .sidebar-title {
        height: 1;
        padding: 0 1;
        background: $accent;
        color: $text;
        text-align: center;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._todo_section: Optional[TodoListSection] = None
        self._teammate_section: Optional[TeammateSection] = None
        self._session_section: Optional[SessionInfoSection] = None

    def compose(self):
        """Build the sidebar layout."""
        yield Static(
            Text("Sidebar", style="bold"),
            classes="sidebar-title",
        )
        with VerticalScroll():
            yield TodoListSection(id="todo-section")
            yield TeammateSection(id="teammate-section")
            yield SessionInfoSection(id="session-section")

    def on_mount(self) -> None:
        """Cache references to child sections."""
        try:
            self._todo_section = self.query_one("#todo-section", TodoListSection)
            self._teammate_section = self.query_one("#teammate-section", TeammateSection)
            self._session_section = self.query_one("#session-section", SessionInfoSection)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_todos(self, items: List[TodoItem]) -> None:
        """Update the todo list."""
        if self._todo_section:
            self._todo_section.set_todos(items)

    def add_todo(self, item: TodoItem) -> None:
        """Add a todo item."""
        if self._todo_section:
            self._todo_section.add_todo(item)

    def update_todo(self, id: str, status: str) -> None:
        """Update a todo item's status."""
        if self._todo_section:
            self._todo_section.update_todo(id, status)

    def set_teammates(self, teammates: List[TeammateInfo]) -> None:
        """Update the teammate list."""
        if self._teammate_section:
            self._teammate_section.set_teammates(teammates)

    def set_session_info(self, info: Dict[str, str]) -> None:
        """Update session metadata."""
        if self._session_section:
            self._session_section.set_info(info)
