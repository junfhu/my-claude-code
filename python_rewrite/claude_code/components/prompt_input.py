"""
Prompt input widget with history, multi-line editing, slash command
completion, tab completion, and paste support.

Extends Textual's Input / TextArea to provide an IDE-like input experience
for the Claude Code REPL.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar, Dict, List, Optional

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.events import Key, Paste
from textual.message import Message
from textual.reactive import reactive
from textual.suggester import Suggester
from textual.widgets import TextArea


# ---------------------------------------------------------------------------
# Slash-command suggester
# ---------------------------------------------------------------------------


class SlashCommandSuggester(Suggester):
    """Provides completion suggestions for slash commands."""

    def __init__(self, commands: Dict[str, Any]) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._commands = commands

    async def get_suggestion(self, value: str) -> Optional[str]:
        """Return a suggestion based on the current input value."""
        if not value.startswith("/"):
            return None

        prefix = value[1:].lower()
        if not prefix:
            return None

        for cmd_name in sorted(self._commands.keys()):
            if cmd_name.startswith(prefix):
                return "/" + cmd_name

        return None


# ---------------------------------------------------------------------------
# Input history manager
# ---------------------------------------------------------------------------


class InputHistory:
    """Manages input history with persistence."""

    def __init__(self, max_size: int = 500) -> None:
        self._entries: List[str] = []
        self._max_size = max_size
        self._cursor: int = -1  # -1 means "not browsing history"
        self._pending: str = ""  # The text the user was typing before navigating

    @property
    def entries(self) -> List[str]:
        return self._entries

    def add(self, text: str) -> None:
        """Add an entry to history (dedup consecutive)."""
        text = text.strip()
        if not text:
            return
        if self._entries and self._entries[-1] == text:
            return
        self._entries.append(text)
        if len(self._entries) > self._max_size:
            self._entries = self._entries[-self._max_size:]
        self._cursor = -1
        self._pending = ""

    def navigate_up(self, current_text: str) -> Optional[str]:
        """Move up in history. Returns the history entry or None."""
        if not self._entries:
            return None

        if self._cursor == -1:
            # Entering history mode — save current text
            self._pending = current_text
            self._cursor = len(self._entries) - 1
        elif self._cursor > 0:
            self._cursor -= 1
        else:
            return None  # Already at oldest entry

        return self._entries[self._cursor]

    def navigate_down(self, current_text: str) -> Optional[str]:
        """Move down in history. Returns the history entry or pending text."""
        if self._cursor == -1:
            return None

        if self._cursor < len(self._entries) - 1:
            self._cursor += 1
            return self._entries[self._cursor]
        else:
            # Exit history mode — restore pending text
            self._cursor = -1
            return self._pending

    def reset_navigation(self) -> None:
        """Reset history browsing state."""
        self._cursor = -1
        self._pending = ""

    def search(self, prefix: str) -> List[str]:
        """Search history for entries starting with prefix."""
        if not prefix:
            return list(reversed(self._entries[-20:]))
        prefix_lower = prefix.lower()
        return [e for e in reversed(self._entries) if e.lower().startswith(prefix_lower)][:20]

    def save(self, path: str) -> None:
        """Persist history to a file."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                for entry in self._entries[-self._max_size:]:
                    f.write(entry.replace("\n", "\\n") + "\n")
        except Exception:
            pass

    def load(self, path: str) -> None:
        """Load history from a file."""
        try:
            if os.path.isfile(path):
                with open(path, "r") as f:
                    for line in f:
                        entry = line.rstrip("\n").replace("\\n", "\n")
                        if entry:
                            self._entries.append(entry)
                # Trim to max size
                if len(self._entries) > self._max_size:
                    self._entries = self._entries[-self._max_size:]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tab completer
# ---------------------------------------------------------------------------


class TabCompleter:
    """Provides tab completion for file paths and commands."""

    def __init__(self, commands: Dict[str, Any]) -> None:
        self._commands = commands
        self._completions: List[str] = []
        self._index: int = 0

    def complete(self, text: str, cursor_pos: int) -> Optional[str]:
        """Return the next tab completion, or None."""
        # Get the word at cursor
        before_cursor = text[:cursor_pos]
        words = before_cursor.split()
        if not words:
            return None

        current_word = words[-1]

        # Slash commands
        if current_word.startswith("/"):
            prefix = current_word[1:].lower()
            matches = [f"/{name}" for name in sorted(self._commands) if name.startswith(prefix)]
            if matches:
                return self._cycle(matches, current_word, text, cursor_pos)

        # File path completion
        if "/" in current_word or current_word.startswith("."):
            return self._complete_path(current_word, text, cursor_pos)

        return None

    def _complete_path(self, partial: str, full_text: str, cursor_pos: int) -> Optional[str]:
        """Complete a file path."""
        expanded = os.path.expanduser(partial)
        dirname = os.path.dirname(expanded) or "."
        basename = os.path.basename(expanded)

        try:
            entries = os.listdir(dirname)
        except OSError:
            return None

        matches = sorted([
            e for e in entries
            if e.startswith(basename) and not e.startswith(".")
        ])

        if not matches:
            return None

        completions = []
        for m in matches:
            full_path = os.path.join(dirname, m)
            if os.path.isdir(full_path):
                completions.append(full_path + "/")
            else:
                completions.append(full_path)

        return self._cycle(completions, partial, full_text, cursor_pos)

    def _cycle(
        self,
        completions: List[str],
        current_word: str,
        full_text: str,
        cursor_pos: int,
    ) -> Optional[str]:
        """Cycle through completions."""
        if completions == self._completions:
            self._index = (self._index + 1) % len(completions)
        else:
            self._completions = completions
            self._index = 0

        if not completions:
            return None

        replacement = completions[self._index]
        # Reconstruct the full text with the completion
        before = full_text[:cursor_pos]
        after = full_text[cursor_pos:]
        word_start = before.rfind(current_word)
        if word_start >= 0:
            return before[:word_start] + replacement + after
        return None

    def reset(self) -> None:
        """Reset the completion state."""
        self._completions = []
        self._index = 0


# ---------------------------------------------------------------------------
# Main prompt input widget
# ---------------------------------------------------------------------------


class PromptInput(TextArea):
    """
    Multi-line input widget with history navigation, slash command
    completion, tab completion, and vim mode support.
    """

    BINDINGS = [
        Binding("up", "history_up", "History up", show=False),
        Binding("down", "history_down", "History down", show=False),
        Binding("tab", "tab_complete", "Complete", show=False),
        Binding("enter", "submit", "Submit", show=False),
        Binding("shift+enter", "newline", "New line", show=False, priority=True),
        Binding("ctrl+u", "clear_input", "Clear", show=False),
        Binding("ctrl+a", "home", "Home", show=False),
        Binding("ctrl+e", "end", "End", show=False),
        Binding("ctrl+w", "delete_word", "Delete word", show=False),
    ]

    # Custom messages
    class Submitted(Message):
        """Fired when the user submits input (Enter on single-line, Ctrl+Enter on multi)."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    # Reactive state
    vim_mode: reactive[bool] = reactive(False)
    placeholder_text: reactive[str] = reactive("Type a message... (/ for commands)")

    def __init__(
        self,
        id: Optional[str] = None,
        commands: Optional[Dict[str, Any]] = None,
        vim_mode: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            id=id,
            language=None,
            theme="monokai",
            soft_wrap=True,
            show_line_numbers=False,
            tab_size=2,
            **kwargs,
        )
        self._commands = commands or {}
        self.vim_mode = vim_mode
        self._history = InputHistory()
        self._tab_completer = TabCompleter(self._commands)
        self._vim_engine: Any = None  # Lazily loaded

        # Load history
        history_path = os.path.expanduser("~/.claude/history")
        self._history_path = history_path
        self._history.load(history_path)

    def on_mount(self) -> None:
        """Set up the widget on mount."""
        # Initialize vim mode if enabled
        if self.vim_mode:
            self._init_vim()

    def _init_vim(self) -> None:
        """Lazily initialise the vim mode engine."""
        try:
            from claude_code.vim_mode.vim_mode import VimEngine
            self._vim_engine = VimEngine(self)
        except ImportError:
            pass

    def toggle_vim_mode(self) -> None:
        """Toggle vim mode on/off."""
        self.vim_mode = not self.vim_mode
        if self.vim_mode:
            self._init_vim()
        else:
            self._vim_engine = None

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    async def _on_key(self, event: Key) -> None:
        """Intercept key events for history, completion, and vim mode."""
        # Vim mode intercepts everything
        if self.vim_mode and self._vim_engine:
            handled = self._vim_engine.handle_key(event)
            if handled:
                event.prevent_default()
                return

        # Let parent handle the key
        await super()._on_key(event)

    def _on_paste(self, event: Paste) -> None:
        """Handle paste events — insert at cursor."""
        text = event.text
        if text:
            self.insert(text)
            self._tab_completer.reset()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_submit(self) -> None:
        """Submit the current input."""
        text = self.text.strip()
        if not text:
            return

        # Add to history
        self._history.add(text)
        self._history.save(self._history_path)

        # Post the message
        self.post_message(self.Submitted(text))

        # Clear the input
        self.clear()
        self._tab_completer.reset()
        self._history.reset_navigation()

    def action_newline(self) -> None:
        """Insert a newline (for multi-line input)."""
        self.insert("\n")

    def action_history_up(self) -> None:
        """Navigate up in history."""
        entry = self._history.navigate_up(self.text)
        if entry is not None:
            self.clear()
            self.insert(entry)

    def action_history_down(self) -> None:
        """Navigate down in history."""
        entry = self._history.navigate_down(self.text)
        if entry is not None:
            self.clear()
            self.insert(entry)

    def action_tab_complete(self) -> None:
        """Perform tab completion."""
        cursor = self.cursor_location
        # TextArea cursor is (row, col)
        text = self.text
        # Compute linear cursor position
        lines = text.splitlines(keepends=True)
        pos = sum(len(lines[i]) for i in range(cursor[0])) + cursor[1]

        result = self._tab_completer.complete(text, pos)
        if result is not None:
            self.clear()
            self.insert(result)

    def action_clear_input(self) -> None:
        """Clear the input."""
        self.clear()
        self._tab_completer.reset()
        self._history.reset_navigation()

    def action_home(self) -> None:
        """Move cursor to beginning of line."""
        row, _ = self.cursor_location
        self.cursor_location = (row, 0)

    def action_end(self) -> None:
        """Move cursor to end of line."""
        row, _ = self.cursor_location
        lines = self.text.splitlines()
        if row < len(lines):
            self.cursor_location = (row, len(lines[row]))

    def action_delete_word(self) -> None:
        """Delete the word before the cursor."""
        row, col = self.cursor_location
        lines = self.text.splitlines()
        if row >= len(lines):
            return

        line = lines[row]
        # Find word boundary
        i = col - 1
        while i >= 0 and line[i] == " ":
            i -= 1
        while i >= 0 and line[i] != " ":
            i -= 1
        i += 1

        if i < col:
            # Delete from i to col
            new_line = line[:i] + line[col:]
            lines[row] = new_line
            new_text = "\n".join(lines)
            self.clear()
            self.insert(new_text)
            self.cursor_location = (row, i)

    def clear(self) -> None:
        """Clear all text from the input."""
        self.select_all()
        self.delete_selection()
