"""
Vim mode implementation for the Claude Code input widget.

Provides a subset of vim keybindings (normal, insert, visual, and
command-line modes) that integrate with Textual's TextArea widget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from textual.events import Key


# ---------------------------------------------------------------------------
# Vim modes
# ---------------------------------------------------------------------------


class VimMode(str, Enum):
    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    VISUAL_LINE = "V-LINE"
    COMMAND = "COMMAND"
    REPLACE = "REPLACE"


# ---------------------------------------------------------------------------
# Motion / text-object types
# ---------------------------------------------------------------------------


class Motion(str, Enum):
    """Supported vim motions."""

    CHAR_LEFT = "h"
    CHAR_RIGHT = "l"
    LINE_UP = "k"
    LINE_DOWN = "j"
    WORD_FORWARD = "w"
    WORD_BACKWARD = "b"
    WORD_END = "e"
    BIGWORD_FORWARD = "W"
    BIGWORD_BACKWARD = "B"
    LINE_START = "0"
    LINE_END = "$"
    FIRST_NON_BLANK = "^"
    DOC_START = "gg"
    DOC_END = "G"
    FIND_CHAR = "f"
    FIND_CHAR_BACK = "F"
    TILL_CHAR = "t"
    TILL_CHAR_BACK = "T"


class TextObject(str, Enum):
    """Supported vim text objects."""

    INNER_WORD = "iw"
    A_WORD = "aw"
    INNER_BIGWORD = "iW"
    A_BIGWORD = "aW"
    INNER_PAREN = "i("
    A_PAREN = "a("
    INNER_BRACKET = "i["
    A_BRACKET = "a["
    INNER_BRACE = "i{"
    A_BRACE = "a{"
    INNER_QUOTE = 'i"'
    A_QUOTE = 'a"'
    INNER_SINGLE_QUOTE = "i'"
    A_SINGLE_QUOTE = "a'"
    INNER_BACKTICK = "i`"
    A_BACKTICK = "a`"


# ---------------------------------------------------------------------------
# Registers and undo stack
# ---------------------------------------------------------------------------


@dataclass
class Register:
    """A vim register (clipboard)."""

    content: str = ""
    linewise: bool = False


@dataclass
class UndoEntry:
    """A snapshot for the undo stack."""

    text: str
    cursor: Tuple[int, int]


# ---------------------------------------------------------------------------
# Vim engine
# ---------------------------------------------------------------------------


class VimEngine:
    """
    Vim emulation engine for a Textual TextArea widget.

    Manages mode transitions, motion evaluation, operator-pending state,
    count prefixes, registers, undo/redo, and command-line execution.
    """

    def __init__(self, widget: Any) -> None:
        """
        Parameters
        ----------
        widget:
            The Textual TextArea (or PromptInput) widget to control.
        """
        self._widget = widget
        self._mode: VimMode = VimMode.NORMAL
        self._pending_operator: Optional[str] = None  # "d", "c", "y", etc.
        self._count_buffer: str = ""
        self._last_find_char: Optional[str] = None
        self._last_find_direction: int = 1  # 1 forward, -1 backward
        self._registers: Dict[str, Register] = {"\"": Register()}  # default register
        self._undo_stack: List[UndoEntry] = []
        self._redo_stack: List[UndoEntry] = []
        self._command_buffer: str = ""
        self._visual_anchor: Optional[Tuple[int, int]] = None
        self._dot_keys: List[str] = []  # keys for "." repeat
        self._recording_dot: bool = False
        self._last_command_keys: List[str] = []
        self._key_buffer: str = ""  # for multi-key sequences like "gg", "dd"

        # Maximum undo entries
        self._max_undo = 100

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def mode(self) -> VimMode:
        return self._mode

    @property
    def mode_display(self) -> str:
        """Return mode string for status bar display."""
        if self._mode == VimMode.NORMAL:
            return "-- NORMAL --"
        elif self._mode == VimMode.INSERT:
            return "-- INSERT --"
        elif self._mode == VimMode.VISUAL:
            return "-- VISUAL --"
        elif self._mode == VimMode.VISUAL_LINE:
            return "-- V-LINE --"
        elif self._mode == VimMode.COMMAND:
            return f":{self._command_buffer}"
        elif self._mode == VimMode.REPLACE:
            return "-- REPLACE --"
        return ""

    @property
    def cursor(self) -> Tuple[int, int]:
        """Get current cursor position as (row, col)."""
        return self._widget.cursor_location

    @cursor.setter
    def cursor(self, pos: Tuple[int, int]) -> None:
        """Set cursor position."""
        self._widget.cursor_location = pos

    @property
    def text(self) -> str:
        return self._widget.text

    @property
    def lines(self) -> List[str]:
        return self.text.splitlines() or [""]

    @property
    def current_line(self) -> str:
        row, _ = self.cursor
        lines = self.lines
        return lines[row] if row < len(lines) else ""

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _push_undo(self) -> None:
        """Save current state to undo stack."""
        entry = UndoEntry(text=self.text, cursor=self.cursor)
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack = self._undo_stack[-self._max_undo:]
        self._redo_stack.clear()

    def _undo(self) -> None:
        """Undo the last change."""
        if not self._undo_stack:
            return
        # Save current state for redo
        self._redo_stack.append(UndoEntry(text=self.text, cursor=self.cursor))
        entry = self._undo_stack.pop()
        self._set_text(entry.text)
        self.cursor = entry.cursor

    def _redo(self) -> None:
        """Redo the last undone change."""
        if not self._redo_stack:
            return
        self._undo_stack.append(UndoEntry(text=self.text, cursor=self.cursor))
        entry = self._redo_stack.pop()
        self._set_text(entry.text)
        self.cursor = entry.cursor

    def _set_text(self, text: str) -> None:
        """Replace the widget's entire text."""
        self._widget.select_all()
        self._widget.delete_selection()
        self._widget.insert(text)

    # ------------------------------------------------------------------
    # Mode transitions
    # ------------------------------------------------------------------

    def _enter_mode(self, mode: VimMode) -> None:
        """Transition to a new vim mode."""
        old_mode = self._mode
        self._mode = mode

        if mode == VimMode.NORMAL:
            self._pending_operator = None
            self._count_buffer = ""
            self._key_buffer = ""
            self._visual_anchor = None
            # Move cursor left if it was at end of line (vim behaviour)
            row, col = self.cursor
            line = self.current_line
            if col > 0 and col >= len(line) and old_mode == VimMode.INSERT:
                self.cursor = (row, max(0, col - 1))

        elif mode == VimMode.INSERT:
            self._recording_dot = True
            self._dot_keys = []

        elif mode == VimMode.VISUAL:
            self._visual_anchor = self.cursor

        elif mode == VimMode.COMMAND:
            self._command_buffer = ""

    # ------------------------------------------------------------------
    # Main key handler
    # ------------------------------------------------------------------

    def handle_key(self, event: Key) -> bool:
        """Process a key event. Returns True if the key was consumed."""
        key = event.key

        if self._mode == VimMode.INSERT:
            return self._handle_insert_key(key)
        elif self._mode == VimMode.NORMAL:
            return self._handle_normal_key(key)
        elif self._mode == VimMode.VISUAL:
            return self._handle_visual_key(key)
        elif self._mode == VimMode.COMMAND:
            return self._handle_command_key(key, event)
        elif self._mode == VimMode.REPLACE:
            return self._handle_replace_key(key)

        return False

    # ------------------------------------------------------------------
    # Insert mode
    # ------------------------------------------------------------------

    def _handle_insert_key(self, key: str) -> bool:
        """Handle keys in insert mode."""
        if key == "escape":
            self._enter_mode(VimMode.NORMAL)
            return True
        if key == "ctrl+c":
            self._enter_mode(VimMode.NORMAL)
            return True

        # Record for "." repeat
        if self._recording_dot:
            self._dot_keys.append(key)

        # Let the widget handle all other keys normally
        return False

    # ------------------------------------------------------------------
    # Normal mode
    # ------------------------------------------------------------------

    def _handle_normal_key(self, key: str) -> bool:
        """Handle keys in normal mode."""
        # Count prefix
        if key.isdigit() and (self._count_buffer or key != "0"):
            self._count_buffer += key
            return True

        count = int(self._count_buffer) if self._count_buffer else 1
        self._count_buffer = ""

        # Multi-key sequences
        if self._key_buffer:
            combined = self._key_buffer + key
            self._key_buffer = ""
            return self._handle_multi_key(combined, count)

        # Check for multi-key prefix
        if key in ("g", "d", "c", "y", "z", ">", "<"):
            if self._pending_operator is None and key in ("d", "c", "y"):
                self._pending_operator = key
                return True
            if key == "g":
                self._key_buffer = "g"
                return True

        # Operator-pending mode
        if self._pending_operator:
            return self._handle_operator_pending(key, count)

        # Simple motions and commands
        return self._handle_normal_command(key, count)

    def _handle_normal_command(self, key: str, count: int) -> bool:
        """Handle a normal-mode command."""
        # Mode changes
        if key == "i":
            self._push_undo()
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "a":
            self._push_undo()
            row, col = self.cursor
            self.cursor = (row, min(col + 1, len(self.current_line)))
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "A":
            self._push_undo()
            row, _ = self.cursor
            self.cursor = (row, len(self.current_line))
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "I":
            self._push_undo()
            row, _ = self.cursor
            line = self.current_line
            first_non_blank = len(line) - len(line.lstrip())
            self.cursor = (row, first_non_blank)
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "o":
            self._push_undo()
            row, _ = self.cursor
            lines = self.lines
            line_end = sum(len(lines[i]) + 1 for i in range(row + 1)) - 1
            # Insert newline after current line
            self._widget.cursor_location = (row, len(self.current_line))
            self._widget.insert("\n")
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "O":
            self._push_undo()
            row, _ = self.cursor
            self._widget.cursor_location = (row, 0)
            self._widget.insert("\n")
            self._widget.cursor_location = (row, 0)
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "v":
            self._enter_mode(VimMode.VISUAL)
            return True
        if key == "V":
            self._enter_mode(VimMode.VISUAL_LINE)
            return True
        if key == "colon":
            self._enter_mode(VimMode.COMMAND)
            return True
        if key == "R":
            self._push_undo()
            self._enter_mode(VimMode.REPLACE)
            return True

        # Motions
        if key == "h":
            self._move_left(count)
            return True
        if key == "l":
            self._move_right(count)
            return True
        if key == "j":
            self._move_down(count)
            return True
        if key == "k":
            self._move_up(count)
            return True
        if key == "w":
            self._move_word_forward(count)
            return True
        if key == "b":
            self._move_word_backward(count)
            return True
        if key == "e":
            self._move_word_end(count)
            return True
        if key == "0":
            row, _ = self.cursor
            self.cursor = (row, 0)
            return True
        if key == "dollar" or key == "$":
            row, _ = self.cursor
            self.cursor = (row, max(0, len(self.current_line) - 1))
            return True
        if key == "circumflex" or key == "^":
            row, _ = self.cursor
            line = self.current_line
            first_non_blank = len(line) - len(line.lstrip())
            self.cursor = (row, first_non_blank)
            return True
        if key == "G":
            lines = self.lines
            self.cursor = (len(lines) - 1, 0)
            return True

        # Editing commands
        if key == "x":
            self._push_undo()
            self._delete_char(count)
            return True
        if key == "X":
            self._push_undo()
            self._delete_char_before(count)
            return True
        if key == "s":
            self._push_undo()
            self._delete_char(1)
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "S":
            self._push_undo()
            self._clear_line()
            self._enter_mode(VimMode.INSERT)
            return True
        if key == "r":
            # Replace single character — need next key
            self._key_buffer = "r"
            return True
        if key == "p":
            self._push_undo()
            self._paste_after()
            return True
        if key == "P":
            self._push_undo()
            self._paste_before()
            return True
        if key == "u":
            self._undo()
            return True
        if key == "ctrl+r":
            self._redo()
            return True
        if key == "period" or key == ".":
            self._repeat_last_command()
            return True
        if key == "J":
            self._push_undo()
            self._join_lines()
            return True

        # Enter submits in normal mode
        if key == "enter":
            # Submit via the widget's action
            self._widget.action_submit()
            return True

        return False

    def _handle_multi_key(self, keys: str, count: int) -> bool:
        """Handle multi-key sequences."""
        if keys == "gg":
            self.cursor = (0, 0)
            return True
        if keys == "dd":
            self._push_undo()
            self._delete_lines(count)
            return True
        if keys == "cc":
            self._push_undo()
            self._clear_line()
            self._enter_mode(VimMode.INSERT)
            return True
        if keys == "yy":
            self._yank_lines(count)
            return True
        if keys.startswith("r") and len(keys) == 2:
            self._push_undo()
            self._replace_char(keys[1])
            return True
        return False

    def _handle_operator_pending(self, key: str, count: int) -> bool:
        """Handle key in operator-pending mode (after d, c, y)."""
        op = self._pending_operator
        self._pending_operator = None

        if op == key:
            # dd, cc, yy — operate on current line
            if op == "d":
                self._push_undo()
                self._delete_lines(count)
            elif op == "c":
                self._push_undo()
                self._clear_line()
                self._enter_mode(VimMode.INSERT)
            elif op == "y":
                self._yank_lines(count)
            return True

        # Operator + motion
        start = self.cursor
        moved = self._execute_motion(key, count)
        if not moved:
            return True
        end = self.cursor

        # Ensure start <= end
        if start > end:
            start, end = end, start

        if op == "d":
            self._push_undo()
            self._delete_range(start, end)
        elif op == "c":
            self._push_undo()
            self._delete_range(start, end)
            self._enter_mode(VimMode.INSERT)
        elif op == "y":
            self._yank_range(start, end)
            self.cursor = start  # Yank doesn't move cursor

        return True

    # ------------------------------------------------------------------
    # Visual mode
    # ------------------------------------------------------------------

    def _handle_visual_key(self, key: str) -> bool:
        """Handle keys in visual mode."""
        if key == "escape":
            self._enter_mode(VimMode.NORMAL)
            return True

        # Motions (same as normal mode, but extend selection)
        if key in ("h", "l", "j", "k", "w", "b", "e", "0", "$", "^", "G"):
            self._execute_motion(key, 1)
            return True

        # Operators
        if key == "d" or key == "x":
            self._push_undo()
            if self._visual_anchor:
                start = self._visual_anchor
                end = self.cursor
                if start > end:
                    start, end = end, start
                self._delete_range(start, end)
            self._enter_mode(VimMode.NORMAL)
            return True

        if key == "y":
            if self._visual_anchor:
                start = self._visual_anchor
                end = self.cursor
                if start > end:
                    start, end = end, start
                self._yank_range(start, end)
            self._enter_mode(VimMode.NORMAL)
            return True

        if key == "c":
            self._push_undo()
            if self._visual_anchor:
                start = self._visual_anchor
                end = self.cursor
                if start > end:
                    start, end = end, start
                self._delete_range(start, end)
            self._enter_mode(VimMode.INSERT)
            return True

        return False

    # ------------------------------------------------------------------
    # Command-line mode
    # ------------------------------------------------------------------

    def _handle_command_key(self, key: str, event: Key) -> bool:
        """Handle keys in command-line mode (:)."""
        if key == "escape":
            self._enter_mode(VimMode.NORMAL)
            return True

        if key == "enter":
            self._execute_command(self._command_buffer)
            self._enter_mode(VimMode.NORMAL)
            return True

        if key == "backspace":
            if self._command_buffer:
                self._command_buffer = self._command_buffer[:-1]
            else:
                self._enter_mode(VimMode.NORMAL)
            return True

        # Append printable characters
        if len(key) == 1 and key.isprintable():
            self._command_buffer += key
            return True

        return True

    def _execute_command(self, cmd: str) -> None:
        """Execute a vim command-line command."""
        cmd = cmd.strip()
        if cmd in ("q", "quit"):
            # Request quit via the widget
            try:
                self._widget.app.exit()
            except Exception:
                pass
        elif cmd in ("w", "write"):
            # No-op for input widget
            pass
        elif cmd in ("wq", "x"):
            self._widget.action_submit()
        elif cmd == "noh":
            # Clear search highlights
            pass
        elif cmd.startswith("set "):
            # Handle set commands
            pass

    # ------------------------------------------------------------------
    # Replace mode
    # ------------------------------------------------------------------

    def _handle_replace_key(self, key: str) -> bool:
        """Handle keys in replace mode."""
        if key == "escape":
            self._enter_mode(VimMode.NORMAL)
            return True

        if len(key) == 1 and key.isprintable():
            self._replace_char(key)
            self._move_right(1)
            return True

        return False

    # ------------------------------------------------------------------
    # Motions
    # ------------------------------------------------------------------

    def _execute_motion(self, key: str, count: int) -> bool:
        """Execute a motion, returning True if the cursor moved."""
        start = self.cursor
        if key == "h":
            self._move_left(count)
        elif key == "l":
            self._move_right(count)
        elif key == "j":
            self._move_down(count)
        elif key == "k":
            self._move_up(count)
        elif key == "w":
            self._move_word_forward(count)
        elif key == "b":
            self._move_word_backward(count)
        elif key == "e":
            self._move_word_end(count)
        elif key == "0":
            row, _ = self.cursor
            self.cursor = (row, 0)
        elif key in ("$", "dollar"):
            row, _ = self.cursor
            self.cursor = (row, max(0, len(self.current_line) - 1))
        elif key in ("^", "circumflex"):
            row, _ = self.cursor
            line = self.current_line
            self.cursor = (row, len(line) - len(line.lstrip()))
        elif key == "G":
            self.cursor = (len(self.lines) - 1, 0)
        else:
            return False
        return self.cursor != start

    def _move_left(self, count: int = 1) -> None:
        row, col = self.cursor
        self.cursor = (row, max(0, col - count))

    def _move_right(self, count: int = 1) -> None:
        row, col = self.cursor
        max_col = max(0, len(self.current_line) - 1) if self._mode == VimMode.NORMAL else len(self.current_line)
        self.cursor = (row, min(max_col, col + count))

    def _move_up(self, count: int = 1) -> None:
        row, col = self.cursor
        new_row = max(0, row - count)
        new_col = min(col, max(0, len(self.lines[new_row]) - 1) if self.lines[new_row] else 0)
        self.cursor = (new_row, new_col)

    def _move_down(self, count: int = 1) -> None:
        row, col = self.cursor
        lines = self.lines
        new_row = min(len(lines) - 1, row + count)
        new_col = min(col, max(0, len(lines[new_row]) - 1) if lines[new_row] else 0)
        self.cursor = (new_row, new_col)

    def _move_word_forward(self, count: int = 1) -> None:
        """Move forward by word."""
        row, col = self.cursor
        lines = self.lines

        for _ in range(count):
            line = lines[row] if row < len(lines) else ""
            # Skip current word
            while col < len(line) and not line[col].isspace():
                col += 1
            # Skip whitespace
            while col < len(line) and line[col].isspace():
                col += 1
            # If at end of line, move to next line
            if col >= len(line) and row < len(lines) - 1:
                row += 1
                col = 0
                # Skip leading whitespace on new line
                line = lines[row]
                while col < len(line) and line[col].isspace():
                    col += 1

        self.cursor = (row, col)

    def _move_word_backward(self, count: int = 1) -> None:
        """Move backward by word."""
        row, col = self.cursor
        lines = self.lines

        for _ in range(count):
            # If at start of line, go to previous line
            if col == 0 and row > 0:
                row -= 1
                col = len(lines[row])

            line = lines[row] if row < len(lines) else ""
            col = max(0, col - 1)

            # Skip whitespace backward
            while col > 0 and line[col].isspace():
                col -= 1
            # Skip word backward
            while col > 0 and not line[col - 1].isspace():
                col -= 1

        self.cursor = (row, col)

    def _move_word_end(self, count: int = 1) -> None:
        """Move to end of word."""
        row, col = self.cursor
        lines = self.lines

        for _ in range(count):
            line = lines[row] if row < len(lines) else ""
            col += 1
            # Skip whitespace
            while col < len(line) and line[col].isspace() if col < len(line) else False:
                col += 1
            # Move to end of word
            while col < len(line) - 1 and not line[col + 1].isspace():
                col += 1
            if col >= len(line) and row < len(lines) - 1:
                row += 1
                col = 0
                line = lines[row]
                while col < len(line) and line[col].isspace():
                    col += 1
                while col < len(line) - 1 and not line[col + 1].isspace():
                    col += 1

        self.cursor = (row, min(col, max(0, len(lines[row]) - 1) if lines[row] else 0))

    # ------------------------------------------------------------------
    # Editing operations
    # ------------------------------------------------------------------

    def _delete_char(self, count: int = 1) -> None:
        """Delete character(s) at cursor (x)."""
        row, col = self.cursor
        line = self.current_line
        if col < len(line):
            end = min(col + count, len(line))
            deleted = line[col:end]
            self._registers['"'] = Register(content=deleted)
            new_line = line[:col] + line[end:]
            self._replace_line(row, new_line)
            if col >= len(new_line) and col > 0:
                self.cursor = (row, len(new_line) - 1)

    def _delete_char_before(self, count: int = 1) -> None:
        """Delete character(s) before cursor (X)."""
        row, col = self.cursor
        line = self.current_line
        start = max(0, col - count)
        if start < col:
            deleted = line[start:col]
            self._registers['"'] = Register(content=deleted)
            new_line = line[:start] + line[col:]
            self._replace_line(row, new_line)
            self.cursor = (row, start)

    def _delete_lines(self, count: int = 1) -> None:
        """Delete line(s) (dd)."""
        row, _ = self.cursor
        lines = self.lines
        end_row = min(row + count, len(lines))
        deleted = "\n".join(lines[row:end_row])
        self._registers['"'] = Register(content=deleted, linewise=True)

        remaining = lines[:row] + lines[end_row:]
        if not remaining:
            remaining = [""]
        self._set_text("\n".join(remaining))
        new_row = min(row, len(remaining) - 1)
        self.cursor = (new_row, 0)

    def _clear_line(self) -> None:
        """Clear the current line's content."""
        row, _ = self.cursor
        line = self.current_line
        self._registers['"'] = Register(content=line)
        self._replace_line(row, "")
        self.cursor = (row, 0)

    def _delete_range(
        self, start: Tuple[int, int], end: Tuple[int, int]
    ) -> None:
        """Delete text between two cursor positions."""
        text = self.text
        lines = text.splitlines(keepends=True)

        # Convert (row, col) to linear offset
        start_offset = sum(len(lines[i]) for i in range(start[0])) + start[1]
        end_offset = sum(len(lines[i]) for i in range(end[0])) + end[1] + 1

        deleted = text[start_offset:end_offset]
        self._registers['"'] = Register(content=deleted)

        new_text = text[:start_offset] + text[end_offset:]
        self._set_text(new_text)
        self.cursor = start

    def _yank_lines(self, count: int = 1) -> None:
        """Yank (copy) line(s) (yy)."""
        row, _ = self.cursor
        lines = self.lines
        end_row = min(row + count, len(lines))
        yanked = "\n".join(lines[row:end_row])
        self._registers['"'] = Register(content=yanked, linewise=True)

    def _yank_range(
        self, start: Tuple[int, int], end: Tuple[int, int]
    ) -> None:
        """Yank text between two cursor positions."""
        text = self.text
        lines = text.splitlines(keepends=True)
        start_offset = sum(len(lines[i]) for i in range(start[0])) + start[1]
        end_offset = sum(len(lines[i]) for i in range(end[0])) + end[1] + 1
        yanked = text[start_offset:end_offset]
        self._registers['"'] = Register(content=yanked)

    def _paste_after(self) -> None:
        """Paste after cursor (p)."""
        reg = self._registers.get('"', Register())
        if not reg.content:
            return

        if reg.linewise:
            row, _ = self.cursor
            lines = self.lines
            # Insert after current line
            new_lines = lines[:row + 1] + [reg.content] + lines[row + 1:]
            self._set_text("\n".join(new_lines))
            self.cursor = (row + 1, 0)
        else:
            row, col = self.cursor
            line = self.current_line
            new_line = line[:col + 1] + reg.content + line[col + 1:]
            self._replace_line(row, new_line)
            self.cursor = (row, col + len(reg.content))

    def _paste_before(self) -> None:
        """Paste before cursor (P)."""
        reg = self._registers.get('"', Register())
        if not reg.content:
            return

        if reg.linewise:
            row, _ = self.cursor
            lines = self.lines
            new_lines = lines[:row] + [reg.content] + lines[row:]
            self._set_text("\n".join(new_lines))
            self.cursor = (row, 0)
        else:
            row, col = self.cursor
            line = self.current_line
            new_line = line[:col] + reg.content + line[col:]
            self._replace_line(row, new_line)
            self.cursor = (row, col + len(reg.content) - 1)

    def _replace_char(self, ch: str) -> None:
        """Replace the character at cursor (r)."""
        row, col = self.cursor
        line = self.current_line
        if col < len(line):
            new_line = line[:col] + ch + line[col + 1:]
            self._replace_line(row, new_line)

    def _join_lines(self) -> None:
        """Join current and next line (J)."""
        row, _ = self.cursor
        lines = self.lines
        if row < len(lines) - 1:
            current = lines[row].rstrip()
            next_line = lines[row + 1].lstrip()
            joined = current + " " + next_line
            new_lines = lines[:row] + [joined] + lines[row + 2:]
            self._set_text("\n".join(new_lines))
            self.cursor = (row, len(current))

    def _replace_line(self, row: int, new_content: str) -> None:
        """Replace a single line's content."""
        lines = self.lines
        if row < len(lines):
            lines[row] = new_content
            self._set_text("\n".join(lines))

    def _repeat_last_command(self) -> None:
        """Repeat the last editing command (.)."""
        if self._last_command_keys:
            for key in self._last_command_keys:
                self.handle_key(_FakeKeyEvent(key))


# ---------------------------------------------------------------------------
# Fake key event for dot-repeat
# ---------------------------------------------------------------------------


class _FakeKeyEvent:
    """Minimal Key event stand-in for replaying recorded keystrokes."""

    __slots__ = ("key", "_prevented")

    def __init__(self, key: str) -> None:
        self.key = key
        self._prevented = False

    def prevent_default(self) -> None:
        self._prevented = True
