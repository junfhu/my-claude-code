"""
Keybinding system for Claude Code.

Manages 50+ actions across 17 contexts with support for vim mode,
custom keybinding loading from ``~/.claude/keybindings.json``, and
Textual binding integration.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from textual.binding import Binding

logger = logging.getLogger("claude_code.keybindings")


# ---------------------------------------------------------------------------
# Contexts (the 17 contexts from the original TypeScript)
# ---------------------------------------------------------------------------


class KeyContext(str, Enum):
    """Keybinding contexts — determines which bindings are active."""

    GLOBAL = "global"
    REPL = "repl"
    INPUT = "input"
    INPUT_EMPTY = "input_empty"
    INPUT_MULTILINE = "input_multiline"
    CHAT_LOG = "chat_log"
    SIDEBAR = "sidebar"
    PERMISSION_PROMPT = "permission_prompt"
    TRANSCRIPT = "transcript"
    CONFIG = "config"
    SETUP = "setup"
    SEARCH = "search"
    COMMAND_PALETTE = "command_palette"
    VIM_NORMAL = "vim_normal"
    VIM_INSERT = "vim_insert"
    VIM_VISUAL = "vim_visual"
    VIM_COMMAND = "vim_command"


# ---------------------------------------------------------------------------
# Actions (the 50+ actions)
# ---------------------------------------------------------------------------


class Action(str, Enum):
    """Named actions that can be bound to keys."""

    # Global
    QUIT = "quit"
    INTERRUPT = "interrupt"
    SHOW_HELP = "show_help"
    TOGGLE_SIDEBAR = "toggle_sidebar"
    TOGGLE_TRANSCRIPT = "toggle_transcript"
    SHOW_CONFIG = "show_config"
    SHOW_COMMAND_PALETTE = "show_command_palette"

    # Input
    SUBMIT = "submit"
    NEWLINE = "newline"
    CLEAR_INPUT = "clear_input"
    HISTORY_UP = "history_up"
    HISTORY_DOWN = "history_down"
    TAB_COMPLETE = "tab_complete"
    DELETE_WORD = "delete_word"
    DELETE_LINE = "delete_line"
    MOVE_HOME = "move_home"
    MOVE_END = "move_end"
    MOVE_WORD_LEFT = "move_word_left"
    MOVE_WORD_RIGHT = "move_word_right"
    SELECT_ALL = "select_all"
    COPY = "copy"
    PASTE = "paste"
    CUT = "cut"
    UNDO = "undo"
    REDO = "redo"

    # Chat log
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    SCROLL_TOP = "scroll_top"
    SCROLL_BOTTOM = "scroll_bottom"
    SCROLL_PAGE_UP = "scroll_page_up"
    SCROLL_PAGE_DOWN = "scroll_page_down"
    CLEAR_SCREEN = "clear_screen"
    COMPACT = "compact"

    # Permission prompt
    PERM_ALLOW = "perm_allow"
    PERM_DENY = "perm_deny"
    PERM_ALWAYS_ALLOW = "perm_always_allow"

    # Session
    RESUME_LAST = "resume_last"
    EXPORT_TRANSCRIPT = "export_transcript"
    SHOW_COST = "show_cost"
    SHOW_STATUS = "show_status"
    SHOW_DIFF = "show_diff"

    # Model
    CHANGE_MODEL = "change_model"
    TOGGLE_VIM = "toggle_vim"
    CHANGE_THEME = "change_theme"
    CHANGE_PERMISSIONS = "change_permissions"

    # Vim
    VIM_ENTER_NORMAL = "vim_enter_normal"
    VIM_ENTER_INSERT = "vim_enter_insert"
    VIM_ENTER_VISUAL = "vim_enter_visual"
    VIM_ENTER_COMMAND = "vim_enter_command"
    VIM_DELETE = "vim_delete"
    VIM_YANK = "vim_yank"
    VIM_PUT = "vim_put"
    VIM_WORD_FORWARD = "vim_word_forward"
    VIM_WORD_BACKWARD = "vim_word_backward"


# ---------------------------------------------------------------------------
# Key binding definition
# ---------------------------------------------------------------------------


@dataclass
class KeyBindingDef:
    """A single key binding definition."""

    key: str  # Textual key string (e.g. "ctrl+c", "escape", "a")
    action: Action
    context: KeyContext
    description: str = ""
    show_in_footer: bool = False
    priority: bool = False
    enabled: bool = True

    def to_textual_binding(self) -> Binding:
        """Convert to a Textual Binding."""
        return Binding(
            key=self.key,
            action=self.action.value,
            description=self.description,
            show=self.show_in_footer,
            priority=self.priority,
        )


# ---------------------------------------------------------------------------
# Default keybindings
# ---------------------------------------------------------------------------

_DEFAULT_BINDINGS: List[KeyBindingDef] = [
    # --- Global ---
    KeyBindingDef("ctrl+c", Action.INTERRUPT, KeyContext.GLOBAL, "Interrupt", show_in_footer=True, priority=True),
    KeyBindingDef("ctrl+d", Action.QUIT, KeyContext.GLOBAL, "Quit", show_in_footer=True),
    KeyBindingDef("f1", Action.SHOW_HELP, KeyContext.GLOBAL, "Help", show_in_footer=True),
    KeyBindingDef("ctrl+t", Action.TOGGLE_SIDEBAR, KeyContext.GLOBAL, "Sidebar", show_in_footer=True),
    KeyBindingDef("ctrl+r", Action.TOGGLE_TRANSCRIPT, KeyContext.GLOBAL, "Transcript"),
    KeyBindingDef("ctrl+comma", Action.SHOW_CONFIG, KeyContext.GLOBAL, "Config"),
    KeyBindingDef("ctrl+p", Action.SHOW_COMMAND_PALETTE, KeyContext.GLOBAL, "Commands"),

    # --- Input ---
    KeyBindingDef("enter", Action.SUBMIT, KeyContext.INPUT, "Submit"),
    KeyBindingDef("shift+enter", Action.NEWLINE, KeyContext.INPUT, "New line", priority=True),
    KeyBindingDef("ctrl+u", Action.CLEAR_INPUT, KeyContext.INPUT, "Clear"),
    KeyBindingDef("up", Action.HISTORY_UP, KeyContext.INPUT, "History up"),
    KeyBindingDef("down", Action.HISTORY_DOWN, KeyContext.INPUT, "History down"),
    KeyBindingDef("tab", Action.TAB_COMPLETE, KeyContext.INPUT, "Complete"),
    KeyBindingDef("ctrl+w", Action.DELETE_WORD, KeyContext.INPUT, "Delete word"),
    KeyBindingDef("ctrl+k", Action.DELETE_LINE, KeyContext.INPUT, "Delete line"),
    KeyBindingDef("ctrl+a", Action.MOVE_HOME, KeyContext.INPUT, "Home"),
    KeyBindingDef("ctrl+e", Action.MOVE_END, KeyContext.INPUT, "End"),
    KeyBindingDef("alt+left", Action.MOVE_WORD_LEFT, KeyContext.INPUT, "Word left"),
    KeyBindingDef("alt+right", Action.MOVE_WORD_RIGHT, KeyContext.INPUT, "Word right"),
    KeyBindingDef("ctrl+shift+a", Action.SELECT_ALL, KeyContext.INPUT, "Select all"),
    KeyBindingDef("ctrl+shift+c", Action.COPY, KeyContext.INPUT, "Copy"),
    KeyBindingDef("ctrl+shift+v", Action.PASTE, KeyContext.INPUT, "Paste"),
    KeyBindingDef("ctrl+shift+x", Action.CUT, KeyContext.INPUT, "Cut"),
    KeyBindingDef("ctrl+z", Action.UNDO, KeyContext.INPUT, "Undo"),
    KeyBindingDef("ctrl+shift+z", Action.REDO, KeyContext.INPUT, "Redo"),

    # --- Chat log ---
    KeyBindingDef("pageup", Action.SCROLL_PAGE_UP, KeyContext.CHAT_LOG, "Page up"),
    KeyBindingDef("pagedown", Action.SCROLL_PAGE_DOWN, KeyContext.CHAT_LOG, "Page down"),
    KeyBindingDef("home", Action.SCROLL_TOP, KeyContext.CHAT_LOG, "Top"),
    KeyBindingDef("end", Action.SCROLL_BOTTOM, KeyContext.CHAT_LOG, "Bottom"),
    KeyBindingDef("ctrl+l", Action.CLEAR_SCREEN, KeyContext.REPL, "Clear", show_in_footer=True),
    KeyBindingDef("ctrl+k", Action.COMPACT, KeyContext.REPL, "Compact"),

    # --- Permission prompt ---
    KeyBindingDef("y", Action.PERM_ALLOW, KeyContext.PERMISSION_PROMPT, "Allow", priority=True),
    KeyBindingDef("n", Action.PERM_DENY, KeyContext.PERMISSION_PROMPT, "Deny", priority=True),
    KeyBindingDef("a", Action.PERM_ALWAYS_ALLOW, KeyContext.PERMISSION_PROMPT, "Always allow", priority=True),
    KeyBindingDef("escape", Action.PERM_DENY, KeyContext.PERMISSION_PROMPT, "Deny"),

    # --- Transcript ---
    KeyBindingDef("escape", Action.QUIT, KeyContext.TRANSCRIPT, "Back"),
    KeyBindingDef("q", Action.QUIT, KeyContext.TRANSCRIPT, "Back"),
    KeyBindingDef("j", Action.SCROLL_DOWN, KeyContext.TRANSCRIPT, "Down"),
    KeyBindingDef("k", Action.SCROLL_UP, KeyContext.TRANSCRIPT, "Up"),
    KeyBindingDef("g", Action.SCROLL_TOP, KeyContext.TRANSCRIPT, "Top"),
    KeyBindingDef("G", Action.SCROLL_BOTTOM, KeyContext.TRANSCRIPT, "Bottom"),
    KeyBindingDef("e", Action.EXPORT_TRANSCRIPT, KeyContext.TRANSCRIPT, "Export"),

    # --- Config ---
    KeyBindingDef("escape", Action.QUIT, KeyContext.CONFIG, "Back"),
    KeyBindingDef("q", Action.QUIT, KeyContext.CONFIG, "Back"),
    KeyBindingDef("ctrl+s", Action.SUBMIT, KeyContext.CONFIG, "Save"),

    # --- Setup ---
    KeyBindingDef("y", Action.PERM_ALLOW, KeyContext.SETUP, "Trust"),
    KeyBindingDef("n", Action.QUIT, KeyContext.SETUP, "Quit"),
    KeyBindingDef("escape", Action.QUIT, KeyContext.SETUP, "Quit"),

    # --- Vim normal mode ---
    KeyBindingDef("i", Action.VIM_ENTER_INSERT, KeyContext.VIM_NORMAL, "Insert"),
    KeyBindingDef("a", Action.VIM_ENTER_INSERT, KeyContext.VIM_NORMAL, "Append"),
    KeyBindingDef("v", Action.VIM_ENTER_VISUAL, KeyContext.VIM_NORMAL, "Visual"),
    KeyBindingDef("colon", Action.VIM_ENTER_COMMAND, KeyContext.VIM_NORMAL, "Command"),
    KeyBindingDef("escape", Action.VIM_ENTER_NORMAL, KeyContext.VIM_INSERT, "Normal"),
    KeyBindingDef("escape", Action.VIM_ENTER_NORMAL, KeyContext.VIM_VISUAL, "Normal"),
    KeyBindingDef("escape", Action.VIM_ENTER_NORMAL, KeyContext.VIM_COMMAND, "Normal"),
    KeyBindingDef("w", Action.VIM_WORD_FORWARD, KeyContext.VIM_NORMAL, "Word forward"),
    KeyBindingDef("b", Action.VIM_WORD_BACKWARD, KeyContext.VIM_NORMAL, "Word backward"),
    KeyBindingDef("d", Action.VIM_DELETE, KeyContext.VIM_NORMAL, "Delete"),
    KeyBindingDef("y", Action.VIM_YANK, KeyContext.VIM_NORMAL, "Yank"),
    KeyBindingDef("p", Action.VIM_PUT, KeyContext.VIM_NORMAL, "Put"),
]


# ---------------------------------------------------------------------------
# Keybinding manager
# ---------------------------------------------------------------------------


class KeybindingManager:
    """
    Manages keybindings across all contexts.

    Loads defaults, merges user customisations from
    ``~/.claude/keybindings.json``, and provides lookup APIs.
    """

    def __init__(self) -> None:
        self._bindings: List[KeyBindingDef] = list(_DEFAULT_BINDINGS)
        self._by_context: Dict[KeyContext, List[KeyBindingDef]] = {}
        self._by_action: Dict[Action, List[KeyBindingDef]] = {}
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Rebuild the lookup indices."""
        self._by_context.clear()
        self._by_action.clear()
        for b in self._bindings:
            if not b.enabled:
                continue
            self._by_context.setdefault(b.context, []).append(b)
            self._by_action.setdefault(b.action, []).append(b)

    def load_user_keybindings(self, path: Optional[str] = None) -> None:
        """Load user keybinding overrides from a JSON file.

        Format::

            {
                "bindings": [
                    {"key": "ctrl+enter", "action": "submit", "context": "input"},
                    {"key": "ctrl+c", "action": "interrupt", "context": "global", "enabled": false}
                ]
            }
        """
        if path is None:
            path = os.path.expanduser("~/.claude/keybindings.json")

        if not os.path.isfile(path):
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)

            for entry in data.get("bindings", []):
                key = entry.get("key", "")
                action_name = entry.get("action", "")
                context_name = entry.get("context", "global")
                enabled = entry.get("enabled", True)
                description = entry.get("description", "")
                show = entry.get("show_in_footer", False)
                priority = entry.get("priority", False)

                try:
                    action = Action(action_name)
                    context = KeyContext(context_name)
                except ValueError:
                    logger.warning(
                        "Unknown action %r or context %r in keybindings.json",
                        action_name,
                        context_name,
                    )
                    continue

                # Find and update existing binding, or add new
                found = False
                for b in self._bindings:
                    if b.action == action and b.context == context:
                        b.key = key
                        b.enabled = enabled
                        if description:
                            b.description = description
                        b.show_in_footer = show
                        b.priority = priority
                        found = True
                        break

                if not found:
                    self._bindings.append(KeyBindingDef(
                        key=key,
                        action=action,
                        context=context,
                        description=description,
                        show_in_footer=show,
                        priority=priority,
                        enabled=enabled,
                    ))

            self._rebuild_indices()
            logger.info("Loaded user keybindings from %s", path)

        except Exception as exc:
            logger.warning("Failed to load keybindings from %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Lookup API
    # ------------------------------------------------------------------

    def get_bindings(self, context: KeyContext) -> List[KeyBindingDef]:
        """Get all bindings for a context."""
        return self._by_context.get(context, [])

    def get_binding_for_action(self, action: Action) -> Optional[KeyBindingDef]:
        """Get the first binding for an action."""
        bindings = self._by_action.get(action, [])
        return bindings[0] if bindings else None

    def get_key_for_action(self, action: Action) -> Optional[str]:
        """Get the key string for an action."""
        b = self.get_binding_for_action(action)
        return b.key if b else None

    def get_textual_bindings(self, context: KeyContext) -> List[Binding]:
        """Get Textual Binding objects for a context."""
        return [b.to_textual_binding() for b in self.get_bindings(context)]

    def get_all_bindings(self) -> List[KeyBindingDef]:
        """Get all registered bindings."""
        return [b for b in self._bindings if b.enabled]

    def get_contexts(self) -> Set[KeyContext]:
        """Get all contexts that have bindings."""
        return set(self._by_context.keys())

    def lookup(self, key: str, context: KeyContext) -> Optional[Action]:
        """Look up the action for a key in a given context.

        Falls back to GLOBAL context if no match in the specific context.
        """
        for b in self._by_context.get(context, []):
            if b.key == key:
                return b.action

        # Fallback to global
        if context != KeyContext.GLOBAL:
            for b in self._by_context.get(KeyContext.GLOBAL, []):
                if b.key == key:
                    return b.action

        return None

    def describe_bindings(self, context: Optional[KeyContext] = None) -> str:
        """Return a human-readable description of bindings."""
        lines = []
        contexts = [context] if context else sorted(self.get_contexts(), key=lambda c: c.value)

        for ctx in contexts:
            lines.append(f"\n[{ctx.value}]")
            for b in self.get_bindings(ctx):
                desc = b.description or b.action.value
                lines.append(f"  {b.key:<20} {desc}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[KeybindingManager] = None


def get_keybinding_manager() -> KeybindingManager:
    """Get or create the global keybinding manager."""
    global _manager
    if _manager is None:
        _manager = KeybindingManager()
        _manager.load_user_keybindings()
    return _manager


def get_bindings_for_context(context: KeyContext) -> List[Binding]:
    """Convenience: get Textual bindings for a context."""
    return get_keybinding_manager().get_textual_bindings(context)
